from pathlib import Path


def read(path: str) -> str:
    return Path(path).read_text(encoding='utf-8')


def write(path: str, text: str) -> None:
    Path(path).write_text(text, encoding='utf-8')


progress_path = 'backend/app/services/academic/progress_email.py'
progress = read(progress_path)

anchor = "CMS_LEARNER_DASHBOARD_URL = 'https://edx.cms.fpl.edu.vn/learner-dashboard/'\n\n\ndef plain_text_mail_template(value: str) -> str:\n"
replacement = """CMS_LEARNER_DASHBOARD_URL = 'https://edx.cms.fpl.edu.vn/learner-dashboard/'
_STUDENT_NAME_TOKEN = '{{tên sinh viên}}'
_STUDENT_CODE_TOKEN = '{{maHs}}'


def render_recipient_body_text(
    value: str,
    *,
    full_name: str | None,
    student_code: str | None,
) -> str:
    \"\"\"Resolve AI-owned recipient variables before handing HTML to Mail Send.\"\"\"
    body = str(value or '')
    clean_name = str(full_name or '').strip()
    clean_code = str(student_code or '').strip()
    if _STUDENT_NAME_TOKEN in body and not clean_name:
        raise ValueError('missing_full_name_for_progress_email')
    if _STUDENT_CODE_TOKEN in body and not clean_code:
        raise ValueError('missing_student_code_for_progress_email')
    return body.replace(_STUDENT_NAME_TOKEN, clean_name).replace(_STUDENT_CODE_TOKEN, clean_code)


def plain_text_mail_template(value: str) -> str:
"""
if anchor not in progress:
    raise SystemExit('progress-email renderer anchor not found')
progress = progress.replace(anchor, replacement, 1)

old_resolve = """        current_candidate_ids = {item['student_id'] for item in result['selected_candidates']}
        emails = [str(item['private_email']) for item in result['deliverable']]
        return {
            'emails': emails,
            'selected_count': len(selected_student_ids),
            'eligible_after_refresh_count': len(result['selected_candidates']),
            'deliverable_count': len(emails),
            'caught_up_or_no_longer_late_count': len(selected_student_ids - current_candidate_ids),
            'missing_email_count': int(result['issue_counts'].get('missing_email', 0)),
            'inactive_student_count': int(result['issue_counts'].get('inactive_student', 0)),
            'duplicate_email_count': int(result['issue_counts'].get('duplicate_email', 0)),
            'stale_after_refresh_count': int(result['issue_counts'].get('stale_after_refresh', 0)),
        }
"""
new_resolve = """        current_candidate_ids = {item['student_id'] for item in result['selected_candidates']}
        recipients = [
            {
                'student_id': str(item['student_id']),
                'student_code': item.get('student_code'),
                'full_name': item.get('full_name'),
                'private_email': str(item['private_email']),
            }
            for item in result['deliverable']
            if item.get('private_email')
        ]
        return {
            'recipients': recipients,
            'selected_count': len(selected_student_ids),
            'eligible_after_refresh_count': len(result['selected_candidates']),
            'deliverable_count': len(recipients),
            'caught_up_or_no_longer_late_count': len(selected_student_ids - current_candidate_ids),
            'missing_email_count': int(result['issue_counts'].get('missing_email', 0)),
            'inactive_student_count': int(result['issue_counts'].get('inactive_student', 0)),
            'duplicate_email_count': int(result['issue_counts'].get('duplicate_email', 0)),
            'stale_after_refresh_count': int(result['issue_counts'].get('stale_after_refresh', 0)),
        }
"""
if old_resolve not in progress:
    raise SystemExit('resolve_selected_after_refresh block not found')
progress = progress.replace(old_resolve, new_resolve, 1)
write(progress_path, progress)

worker_path = 'backend/app/worker.py'
worker = read(worker_path)
start_marker = "@celery_app.task(name='academic_progress_email_task', acks_late=False)\n"
end_marker = "\ndef _enqueue_academic_class_sync_child_job(\n"
start = worker.find(start_marker)
end = worker.find(end_marker, start)
if start < 0 or end < 0:
    raise SystemExit('academic_progress_email_task block not found')

new_task = r'''@celery_app.task(name='academic_progress_email_task', acks_late=False)
def academic_progress_email_task(job_id: str):
    """Refresh CMS progress, personalize each reminder locally, then track Mail Send."""
    from app.models.academic import AcademicBulkOperationJob, AcademicClassStudent
    from app.services.academic.progress_email import (
        AcademicProgressEmailService,
        plain_text_mail_template,
        render_recipient_body_text,
    )
    from app.services.academic_service import AcademicService
    from app.services.audit_log import AuditErrorType, log_audit
    from app.services.mailsend_proxy import MailSendProxyClient, MailSendProxyError

    db = SessionLocal()
    try:
        job = db.get(AcademicBulkOperationJob, job_id)
        if not job:
            return {'ok': False, 'error': 'job_not_found'}
        if job.job_type != 'progress_reminder_email':
            raise RuntimeError(f'Unsupported progress email job_type: {job.job_type}')
        if job.status not in {'queued', 'running'}:
            return job.result_json or {'ok': job.status == 'completed', 'status': job.status}

        request = job.request_json if isinstance(job.request_json, dict) else {}
        class_id = str(request.get('class_id') or '').strip()
        approved_class_id = str(request.get('approved_class_id') or '').strip()
        if not class_id or approved_class_id != class_id:
            raise PermissionError('Job gửi mail không có phạm vi lớp hợp lệ.')
        selected_ids = {
            str(item).strip()
            for item in (request.get('student_ids') or [])
            if str(item or '').strip()
        }
        max_recipients = max(1, min(1000, int(settings.mailsend_max_recipients or 1000)))
        if not selected_ids or len(selected_ids) > max_recipients:
            raise ValueError('Danh sách sinh viên gửi mail không hợp lệ.')
        subject = ' '.join(str(request.get('subject') or '').replace('\r', ' ').replace('\n', ' ').split())
        body_text = str(request.get('body_template') or '').strip()
        if not subject or len(subject) > 200 or not body_text or len(body_text) > 12000:
            raise ValueError('Tiêu đề hoặc nội dung mail không hợp lệ.')
        if not settings.mailsend_enabled or not str(settings.mailsend_proxy_api_key or '').strip():
            raise MailSendProxyError(
                'MAILSEND_NOT_CONFIGURED',
                'AI Server chưa được cấu hình Mail Send ProxyKey.',
            )

        worker_user = _worker_user_from_request_json(
            request,
            fallback_user_id=job.requested_by,
            source='celery_academic_progress_email_job',
            job_id=job.id,
        )
        academic = AcademicService(db)
        academic.assert_can_access_class(worker_user, class_id)
        progress_service = AcademicProgressEmailService(db)
        existing_result = dict(job.result_json or {}) if isinstance(job.result_json, dict) else {}
        legacy_session_id = str(existing_result.get('mail_send_session_id') or '').strip()

        job.status = 'running'
        job.started_at = job.started_at or datetime.utcnow()
        job.updated_at = datetime.utcnow()
        job.progress_total = 100
        job.progress_current = 70 if legacy_session_id else 10
        job.progress_label = 'Đang theo dõi Mail Send' if legacy_session_id else 'Đang lấy tiến độ CMS mới nhất'
        db.add(job)
        db.commit()

        # Finish a session created by the pre-personalization implementation
        # without submitting duplicate mail after a rolling deployment.
        if legacy_session_id and not existing_result.get('mail_send_deliveries'):
            client = MailSendProxyClient()
            terminal = client.wait_for_terminal(legacy_session_id)
            terminal_status = str(terminal.get('status') or '').upper()
            if terminal_status != 'COMPLETED':
                raise MailSendProxyError(
                    f'MAILSEND_{terminal_status or "FAILED"}',
                    f'Mail Send kết thúc với trạng thái {terminal_status or "không xác định"}.',
                )
            sent_count = int(terminal.get('sent_count') or 0)
            failed_count = int(terminal.get('failed_count') or 0)
            final_result = json_safe_value({
                **existing_result,
                'ok': True,
                'mail_send_status': 'COMPLETED',
                'mail_send_confirmed': True,
                'sent_count': sent_count,
                'failed_count': failed_count,
                'message': 'Mail Send đã xác nhận session cũ hoàn tất.',
            })
            job = db.get(AcademicBulkOperationJob, job_id)
            job.status = 'completed'
            job.progress_current = 100
            job.progress_total = 100
            job.progress_label = f'Đã gửi {sent_count} email' + (f' · {failed_count} lỗi' if failed_count else '')
            job.result_json = final_result
            job.error_message = None
            job.finished_at = datetime.utcnow()
            job.updated_at = datetime.utcnow()
            db.add(job)
            db.commit()
            return final_result

        refresh_started: datetime | None = None
        refresh_started_raw = str(existing_result.get('cms_refresh_started_at') or '').strip()
        if bool(existing_result.get('cms_refresh_confirmed')) and refresh_started_raw:
            try:
                refresh_started = datetime.fromisoformat(refresh_started_raw)
            except ValueError:
                refresh_started = None

        if refresh_started is None:
            refresh_started = datetime.utcnow()
            roster_size = int(
                db.query(AcademicClassStudent)
                .filter(AcademicClassStudent.class_id == class_id)
                .count()
            )
            configured_max = max(1, int(settings.academic_class_sync_max_students or 5000))
            if roster_size > configured_max:
                raise ValueError(
                    f'Lớp có {roster_size} sinh viên, vượt giới hạn đồng bộ {configured_max}.'
                )
            sync_result = academic.sync_class_learning_insight(
                worker_user,
                class_id,
                force=True,
                limit=max(1, roster_size),
            )
            job = db.get(AcademicBulkOperationJob, job_id)
            job.progress_current = 45
            job.progress_label = 'Đang loại sinh viên đã bắt kịp tiến độ'
            job.updated_at = datetime.utcnow()
            job.result_json = json_safe_value({
                **existing_result,
                'selected_count': len(selected_ids),
                'cms_refresh_confirmed': True,
                'cms_refresh_started_at': refresh_started.isoformat(),
                'cms_refreshed_count': int(sync_result.get('updated') or 0),
                'mail_send_status': 'NOT_CREATED',
                'mail_send_confirmed': False,
            })
            db.add(job)
            db.commit()
            existing_result = dict(job.result_json or {})

        resolved = progress_service.resolve_selected_after_refresh(
            worker_user,
            class_id,
            selected_student_ids=selected_ids,
            minimum_synced_at=refresh_started,
        )
        recipients = list(resolved.pop('recipients'))
        delivery_summary = json_safe_value(resolved)
        if not recipients:
            result = json_safe_value({
                'ok': True,
                **delivery_summary,
                'cms_refresh_confirmed': True,
                'cms_refresh_started_at': refresh_started.isoformat(),
                'cms_refreshed_count': int(existing_result.get('cms_refreshed_count') or 0),
                'mail_send_status': 'NOT_CREATED',
                'mail_send_confirmed': False,
                'message': 'Không còn sinh viên đủ điều kiện gửi sau khi cập nhật tiến độ CMS.',
            })
            job = db.get(AcademicBulkOperationJob, job_id)
            job.status = 'completed'
            job.progress_current = 100
            job.progress_total = 100
            job.progress_label = 'Không còn sinh viên chậm tiến độ cần gửi'
            job.result_json = result
            job.error_message = None
            job.finished_at = datetime.utcnow()
            job.updated_at = datetime.utcnow()
            db.add(job)
            db.commit()
            try:
                log_audit(
                    db,
                    action='academic.progress_email.no_recipients_after_refresh',
                    status='success',
                    message=job.progress_label,
                    user=None,
                    target_type='academic_bulk_operation_job',
                    target_id=job.id,
                    metadata=json_safe_value({
                        'class_id': class_id,
                        'requested_by': job.requested_by,
                        **delivery_summary,
                        'recipient_addresses_logged': False,
                    }),
                )
            except Exception:
                logger.exception('Could not write no-recipient progress email audit for job %s', job_id)
            return result

        current_job = db.get(AcademicBulkOperationJob, job_id)
        current_result = dict(current_job.result_json or {}) if isinstance(current_job.result_json, dict) else {}
        raw_states = current_result.get('mail_send_deliveries')
        delivery_states: dict[str, dict[str, Any]] = {}
        if isinstance(raw_states, list):
            for item in raw_states:
                if not isinstance(item, dict):
                    continue
                student_id = str(item.get('student_id') or '').strip()
                if student_id:
                    delivery_states[student_id] = dict(item)

        client = MailSendProxyClient()
        processed = 0
        total = len(recipients)
        sent_count = 0
        failed_count = 0
        personalization_missing_count = 0

        def persist_states(*, label: str, status: str = 'RUNNING') -> None:
            current = db.get(AcademicBulkOperationJob, job_id)
            if not current:
                return
            current_result = dict(current.result_json or {}) if isinstance(current.result_json, dict) else {}
            current_result.update({
                **delivery_summary,
                'cms_refresh_confirmed': True,
                'cms_refresh_started_at': refresh_started.isoformat(),
                'mail_send_deliveries': list(delivery_states.values()),
                'mail_send_status': status,
                'mail_send_confirmed': False,
                'sent_count': sent_count,
                'failed_count': failed_count,
                'personalization_missing_count': personalization_missing_count,
            })
            current.result_json = json_safe_value(current_result)
            current.progress_current = min(95, 55 + int((processed / max(1, total)) * 40))
            current.progress_label = label[:255]
            current.updated_at = datetime.utcnow()
            db.add(current)
            db.commit()

        for recipient in recipients:
            student_id = str(recipient.get('student_id') or '').strip()
            recipient_email = str(recipient.get('private_email') or '').strip().lower()
            state = delivery_states.get(student_id, {'student_id': student_id})
            delivery_states[student_id] = state

            if str(state.get('status') or '').upper() == 'COMPLETED':
                sent_count += int(state.get('sent_count') or 1)
                failed_count += int(state.get('failed_count') or 0)
                processed += 1
                continue

            session_id = str(state.get('session_id') or '').strip()
            if not session_id:
                try:
                    personalized_text = render_recipient_body_text(
                        body_text,
                        full_name=recipient.get('full_name'),
                        student_code=recipient.get('student_code'),
                    )
                except ValueError as exc:
                    state.update({
                        'status': 'PERSONALIZATION_MISSING',
                        'error_code': str(exc),
                    })
                    personalization_missing_count += 1
                    failed_count += 1
                    processed += 1
                    persist_states(label=f'Đã xử lý {processed}/{total} sinh viên')
                    continue

                try:
                    created = client.create_bulk_session(
                        subject=subject,
                        body_template=plain_text_mail_template(personalized_text),
                        emails=[recipient_email],
                    )
                except MailSendProxyError as exc:
                    state.update({
                        'status': 'CREATE_FAILED',
                        'error_code': exc.code,
                    })
                    failed_count += 1
                    processed += 1
                    persist_states(label=f'Đã xử lý {processed}/{total} sinh viên')
                    continue

                session_id = str(created['session_id'])
                state.update({
                    'session_id': session_id,
                    'status': str(created.get('status') or 'QUEUED').upper(),
                })
                # Persist the session before polling so retry/resume never creates
                # a duplicate email for this student.
                persist_states(label=f'Mail Send đã nhận {processed + 1}/{total} session')

            try:
                terminal = client.wait_for_terminal(session_id)
                terminal_status = str(terminal.get('status') or '').upper()
                state.update({
                    'status': terminal_status or 'UNKNOWN',
                    'sent_count': int(terminal.get('sent_count') or 0),
                    'failed_count': int(terminal.get('failed_count') or 0),
                })
                if terminal_status == 'COMPLETED':
                    sent_count += int(terminal.get('sent_count')) if terminal.get('sent_count') is not None else 1
                    failed_count += int(terminal.get('failed_count') or 0)
                else:
                    failed_count += max(1, int(terminal.get('failed_count') or 0))
            except MailSendProxyError as exc:
                state.update({
                    'status': 'POLL_FAILED',
                    'error_code': exc.code,
                })
                failed_count += 1

            processed += 1
            persist_states(label=f'Đã xử lý {processed}/{total} sinh viên')

        all_failed = sent_count <= 0 and failed_count > 0
        final_status = 'FAILED' if all_failed else ('COMPLETED_WITH_ERRORS' if failed_count else 'COMPLETED')
        final_result = json_safe_value({
            **(db.get(AcademicBulkOperationJob, job_id).result_json or {}),
            'ok': not all_failed,
            **delivery_summary,
            'mail_send_deliveries': list(delivery_states.values()),
            'mail_send_status': final_status,
            'mail_send_confirmed': True,
            'sent_count': sent_count,
            'failed_count': failed_count,
            'personalization_missing_count': personalization_missing_count,
            'message': (
                'Không gửi được email nào.'
                if all_failed
                else f'Đã xử lý {total} sinh viên qua Mail Send.'
            ),
        })
        job = db.get(AcademicBulkOperationJob, job_id)
        job.status = 'failed' if all_failed else 'completed'
        job.progress_current = 100
        job.progress_total = 100
        job.progress_label = f'Đã gửi {sent_count} email'
        if failed_count:
            job.progress_label += f' · {failed_count} lỗi'
        job.result_json = final_result
        job.error_message = 'Không gửi được email nào.' if all_failed else None
        job.finished_at = datetime.utcnow()
        job.updated_at = datetime.utcnow()
        db.add(job)
        db.commit()
        try:
            log_audit(
                db,
                action='academic.progress_email.completed' if not all_failed else 'academic.progress_email.failed',
                status='success' if not all_failed else 'failed',
                error_type=None if not all_failed else AuditErrorType.EXTERNAL_SERVICE_ERROR,
                message=job.progress_label,
                user=None,
                target_type='academic_bulk_operation_job',
                target_id=job.id,
                metadata=json_safe_value({
                    'class_id': class_id,
                    'requested_by': job.requested_by,
                    'selected_count': len(selected_ids),
                    'deliverable_count': delivery_summary.get('deliverable_count'),
                    'personalized_session_count': len(delivery_states),
                    'sent_count': sent_count,
                    'failed_count': failed_count,
                    'personalization_missing_count': personalization_missing_count,
                    'recipient_addresses_logged': False,
                }),
            )
        except Exception:
            logger.exception('Could not write progress email audit for job %s', job_id)
        return final_result
    except Exception as exc:
        db.rollback()
        job = db.get(AcademicBulkOperationJob, job_id)
        if isinstance(exc, MailSendProxyError):
            error_code = exc.code
            public_message = str(exc)
            error_type = AuditErrorType.EXTERNAL_SERVICE_ERROR
        else:
            error_code = 'PROGRESS_EMAIL_FAILED'
            public_message = 'Không thể gửi nhắc tiến độ. Vui lòng kiểm tra dữ liệu CMS và cấu hình Mail Send.'
            error_type = AuditErrorType.SYSTEM_ERROR
            logger.exception('academic_progress_email_task failed for job %s', job_id)
        if job:
            previous = dict(job.result_json or {}) if isinstance(job.result_json, dict) else {}
            job.status = 'failed'
            job.progress_total = 100
            job.progress_label = 'Gửi nhắc tiến độ thất bại'
            job.error_message = public_message[:4000]
            job.result_json = json_safe_value({
                **previous,
                'ok': False,
                'code': error_code,
                'message': public_message,
                'mail_send_confirmed': False,
            })
            job.finished_at = datetime.utcnow()
            job.updated_at = datetime.utcnow()
            db.add(job)
            db.commit()
            try:
                log_audit(
                    db,
                    action='academic.progress_email.failed',
                    status='failed',
                    error_type=error_type,
                    message=public_message,
                    user=None,
                    target_type='academic_bulk_operation_job',
                    target_id=job.id,
                    metadata=json_safe_value({
                        'class_id': (job.request_json or {}).get('class_id') if isinstance(job.request_json, dict) else None,
                        'error_code': error_code,
                        'personalized_session_count': len(previous.get('mail_send_deliveries') or []),
                        'recipient_addresses_logged': False,
                    }),
                )
            except Exception:
                pass
        raise
    finally:
        db.close()

'''
worker = worker[:start] + new_task + worker[end + 1:]
write(worker_path, worker)

context_path = 'MASTER_CONTEXT_DASH_CMS.md'
context = read(context_path)
addendum = """

## Addendum 2026-09-15 — AI-side progress email personalization

- AI Server tự resolve `{{tên sinh viên}}` từ `AcademicStudent.full_name` và `{{maHs}}` từ `AcademicStudent.student_code` trước khi render HTML/gửi Mail Send.
- Vì Mail Send nhận một `bodyTemplate` cho mỗi bulk session, progress reminder tạo một session cho từng recipient để nội dung được personalize đúng người. Session được persist trước khi poll để retry/resume không gửi trùng.
- `mail_send_deliveries` chỉ lưu `student_id`, `session_id`, trạng thái và counters; không lưu email thật hoặc body đã personalize. Email thật chỉ tồn tại trong memory/backend khi gọi Mail Send.
- Recipient thiếu dữ liệu cho một placeholder đang được dùng sẽ bị đánh dấu `PERSONALIZATION_MISSING` và không gửi template còn nguyên biến.
"""
if '## Addendum 2026-09-15 — AI-side progress email personalization' not in context:
    write(context_path, context.rstrip() + addendum + '\n')
