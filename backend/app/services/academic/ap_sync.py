from __future__ import annotations

from typing import Any
import hashlib
import json

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.errors import public_http_exception
from app.core.json_safe import json_safe_value
from app.core.rbac import UserContext
from app.models.academic import AcademicSyncRun
from app.schemas.academic import AcademicAPSyncIn, AcademicImportFromJsonIn, AcademicSyncCounters
from app.services.ap_academic_sync import AcademicImportService
from app.services.audit_log import AuditErrorType, log_audit


class AcademicAPSyncWorkflowService:
    """AP import/sync orchestration extracted from the academic route.

    This workflow keeps the external API response shape unchanged while moving
    AP sync/import orchestration out of the large route file.  It is intentionally
    thin around AcademicImportService: no schema changes, no new DB tables, and no
    change to Celery task semantics.
    """

    def __init__(self, db: Session):
        self.db = db
        self.importer = AcademicImportService(db)

    def sync_campuses_from_ap(self, *, branch: str, user: UserContext) -> list[Any]:
        try:
            items = self.importer.sync_campuses_from_ap(branch=branch)
            log_audit(
                self.db,
                action='academic.campus.sync_from_ap',
                status='success',
                message='Đồng bộ danh sách cơ sở từ AP thành công',
                user=user,
                target_type='academic_campus',
                target_id='bulk',
                metadata={'branch': branch, 'count': len(items)},
            )
            return items
        except HTTPException:
            raise
        except Exception as exc:  # pragma: no cover - defensive wrapper
            self.db.rollback()
            message = str(exc) or 'Không đồng bộ được danh sách cơ sở từ AP CMS.'
            log_audit(
                self.db,
                action='academic.campus.sync_from_ap',
                status='failed',
                error_type=AuditErrorType.EXTERNAL_SERVICE_ERROR,
                message=message,
                user=user,
                target_type='academic_campus',
                target_id='bulk',
                metadata={'branch': branch},
            )
            raise HTTPException(status_code=502, detail=f'Đồng bộ danh sách cơ sở từ AP CMS thất bại: {message}') from exc

    def get_sync_options(
        self,
        *,
        term_name: str | None,
        branch: str,
        campus: str | None,
        include_subjects: bool,
    ) -> dict[str, Any]:
        return self.importer.get_ap_sync_options(
            term_name=term_name or None,
            branch=branch,
            campus=campus,
            include_subjects=include_subjects,
        )

    def sync_from_json(self, payload: AcademicImportFromJsonIn, *, user: UserContext) -> dict[str, Any]:
        run = self.importer.create_run(
            source=payload.source or 'ap_json',
            mode='json',
            requested_by=user.user_id,
            campus=payload.campus,
            branch=payload.branch,
        )
        try:
            counters = self.importer.import_payload(payload.payload, run=run, campus=payload.campus, branch=payload.branch)
            run = self.importer.finish_run(run, counters)
            log_audit(
                self.db,
                action='academic.ap.import_json',
                status='success',
                message='Đồng bộ dữ liệu AP từ JSON thành công',
                user=user,
                target_type='academic_sync_run',
                target_id=run.id,
                metadata={'counters': counters.as_dict(), 'campus': payload.campus, 'branch': payload.branch},
            )
            return {'ok': True, 'message': 'Đã import dữ liệu AP từ JSON', 'sync_run': run, 'counters': counters.as_dict()}
        except Exception as exc:
            self.db.rollback()
            run = self.importer.finish_run(run, error=str(exc))
            log_audit(
                self.db,
                action='academic.ap.import_json',
                status='failed',
                error_type=AuditErrorType.SYSTEM_ERROR,
                message=str(exc),
                user=user,
                target_type='academic_sync_run',
                target_id=run.id,
            )
            raise public_http_exception(
                status_code=400,
                code='ACADEMIC_IMPORT_FAILED',
                message='Không thể hoàn tất import dữ liệu học vụ.',
                logger_name=__name__,
            ) from exc

    @staticmethod
    def _normalized_ap_request(payload: AcademicAPSyncIn, *, require_explicit_targets: bool = True) -> dict[str, Any]:
        branch = (payload.branch or 'poly').strip().lower() or 'poly'
        if branch not in {'poly', 'ptcd'}:
            raise HTTPException(status_code=422, detail='Hệ AP chỉ hỗ trợ poly hoặc ptcd.')
        term_name = (payload.term_name or '').strip()
        if not term_name:
            raise HTTPException(status_code=422, detail='Vui lòng chọn kỳ trước khi đồng bộ AP.')
        scope = (payload.sync_scope or 'all').strip().lower() or 'all'
        if scope not in {'all', 'campus', 'subject'}:
            raise HTTPException(status_code=422, detail='Phạm vi đồng bộ AP không hợp lệ.')
        campuses = sorted({str(item).strip().lower() for item in (payload.campuses or []) if str(item).strip()})
        campus = str(payload.campus or '').strip().lower() or None
        if campus and campus not in campuses:
            campuses.append(campus)
            campuses.sort()
        subject_codes = sorted({str(item).strip().upper() for item in (payload.subject_codes or []) if str(item).strip()})
        if require_explicit_targets and scope in {'all', 'campus'} and not campuses:
            raise HTTPException(status_code=422, detail='Phạm vi đồng bộ chưa có cơ sở.')
        if require_explicit_targets and scope == 'subject' and (not campuses or not subject_codes):
            raise HTTPException(status_code=422, detail='Đồng bộ theo môn cần ít nhất một cơ sở và một mã môn.')
        return {
            'term_name': term_name,
            'sync_scope': scope,
            'campus': campus,
            'campuses': campuses,
            'branch': branch,
            'subject_codes': subject_codes,
            'max_subjects': int(payload.max_subjects or 0),
            'dry_run': bool(payload.dry_run),
        }

    @staticmethod
    def _ap_request_fingerprint(request_json: dict[str, Any]) -> str:
        raw = json.dumps(request_json, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode('utf-8')
        return hashlib.sha256(raw).hexdigest()

    def _acquire_enqueue_scope_lock(self, *, term_name: str, branch: str) -> None:
        """Serialize AP job creation for one term/branch on PostgreSQL.

        Without this lock, two operators clicking at nearly the same moment can
        both observe no active row and enqueue overlapping imports. The advisory
        transaction lock is released by the commit performed when the run row is
        created. Non-PostgreSQL test/development databases safely skip it.
        """
        bind = self.db.get_bind()
        if not bind or bind.dialect.name != 'postgresql':
            return
        digest = hashlib.sha256(f'ap-sync:{branch}:{term_name}'.encode('utf-8')).digest()
        lock_key = int.from_bytes(digest[:8], byteorder='big', signed=True)
        self.db.execute(text('SELECT pg_advisory_xact_lock(:lock_key)'), {'lock_key': lock_key})

    def enqueue_sync_from_ap_job(self, payload: AcademicAPSyncIn, *, user: UserContext) -> dict[str, Any]:
        request_json = json_safe_value(self._normalized_ap_request(payload))
        request_fingerprint = self._ap_request_fingerprint(request_json)
        branch = str(request_json['branch'])
        term_name = str(request_json['term_name'])
        scope = str(request_json['sync_scope'])
        self._acquire_enqueue_scope_lock(term_name=term_name, branch=branch)
        active = (
            self.db.query(AcademicSyncRun)
            .filter(
                AcademicSyncRun.source == 'ap',
                AcademicSyncRun.status.in_(['queued', 'running']),
                AcademicSyncRun.term_name == term_name,
                AcademicSyncRun.branch == branch,
            )
            .order_by(AcademicSyncRun.created_at.desc())
            .first()
        )
        if active:
            active_data = active.counters_json if isinstance(active.counters_json, dict) else {}
            active_request = active_data.get('request') if isinstance(active_data.get('request'), dict) else {}
            active_fingerprint = str(active_data.get('request_fingerprint') or '')
            if not active_fingerprint and active_request:
                try:
                    active_request = self._normalized_ap_request(
                        AcademicAPSyncIn(**active_request),
                        require_explicit_targets=False,
                    )
                except Exception:
                    # Keep old malformed payload visible as a conflicting job; do
                    # not silently reuse it for a new normalized request.
                    pass
                active_fingerprint = self._ap_request_fingerprint(active_request)
            if active_fingerprint == request_fingerprint:
                return {
                    'ok': True,
                    'message': 'Job đồng bộ AP cùng phạm vi đang chạy. Hệ thống tiếp tục theo dõi job hiện tại.',
                    'sync_run': active,
                    'counters': AcademicSyncCounters(),
                }
            raise HTTPException(
                status_code=409,
                detail='Đang có job AP khác phạm vi chạy trong cùng kỳ và hệ. Hãy chờ job hiện tại hoàn tất để tránh dữ liệu giao nhau.',
            )

        run = self.importer.create_run(
            source='ap',
            mode=f'api_{scope}_job_dry_run' if request_json['dry_run'] else f'api_{scope}_job',
            requested_by=user.user_id,
            term_name=term_name,
            campus=','.join(request_json['campuses'][:10]) if request_json['campuses'] else request_json['campus'],
            branch=branch,
            status='queued',
            counters_json={
                'request': request_json,
                'request_fingerprint': request_fingerprint,
                'progress': {'current': 0, 'total': 1, 'label': 'Đã đưa job đồng bộ AP vào hàng đợi', 'updated_at': None},
            },
        )
        try:
            from app.worker import academic_ap_sync_task
            async_result = academic_ap_sync_task.delay(run.id)
            data = run.counters_json if isinstance(run.counters_json, dict) else {}
            data['enqueue'] = {'task_name': 'academic_ap_sync_task', 'celery_task_id': getattr(async_result, 'id', None)}
            run.counters_json = json_safe_value(data)
            self.db.add(run)
            self.db.commit()
            self.db.refresh(run)
        except Exception as exc:
            run.status = 'failed'
            run.error_message = f'Không đưa job đồng bộ AP vào Celery/Redis: {exc}'[:4000]
            self.db.add(run)
            self.db.commit()
            self.db.refresh(run)
            raise HTTPException(status_code=503, detail='Không đưa job đồng bộ AP vào hàng đợi. Kiểm tra Redis/worker rồi thử lại.') from exc

        log_audit(
            self.db,
            action='academic.ap.sync_api.enqueue',
            status='success',
            message='Đã đưa job đồng bộ AP vào hàng đợi',
            user=user,
            target_type='academic_sync_run',
            target_id=run.id,
            metadata={**request_json, 'request_fingerprint': request_fingerprint},
        )
        return {'ok': True, 'message': 'Đã đưa job đồng bộ AP vào hàng đợi. Trạng thái sẽ tự cập nhật.', 'sync_run': run, 'counters': AcademicSyncCounters()}

    def list_sync_jobs(self, *, term_name: str = '', branch: str = '', status_filter: str = 'active', limit: int = 10) -> list[AcademicSyncRun]:
        query = self.db.query(AcademicSyncRun).filter(AcademicSyncRun.source == 'ap')
        if term_name.strip():
            query = query.filter(AcademicSyncRun.term_name == term_name.strip())
        if branch.strip():
            query = query.filter(AcademicSyncRun.branch == branch.strip().lower())
        if status_filter == 'active':
            query = query.filter(AcademicSyncRun.status.in_(['queued', 'running']))
        elif status_filter and status_filter != 'all':
            query = query.filter(AcademicSyncRun.status == status_filter)
        return query.order_by(AcademicSyncRun.created_at.desc()).limit(limit).all()

    def get_sync_job(self, run_id: str) -> AcademicSyncRun:
        run = self.db.get(AcademicSyncRun, run_id)
        if not run or run.source != 'ap':
            raise HTTPException(status_code=404, detail='Không tìm thấy job đồng bộ AP')
        return run

    def sync_from_ap(self, payload: AcademicAPSyncIn, *, user: UserContext) -> dict[str, Any]:
        run, counters = self.importer.sync_from_ap(
            requested_by=user.user_id,
            term_name=payload.term_name,
            campus=payload.campus,
            branch=payload.branch,
            subject_codes=payload.subject_codes,
            max_subjects=payload.max_subjects,
            dry_run=payload.dry_run,
            sync_scope=payload.sync_scope,
            campuses=payload.campuses,
        )
        status_value = 'success' if run.status == 'completed' else 'failed'
        log_audit(
            self.db,
            action='academic.ap.sync_api',
            status=status_value,
            error_type=None if status_value == 'success' else AuditErrorType.EXTERNAL_SERVICE_ERROR,
            message='Đồng bộ dữ liệu AP qua API hoàn tất' if status_value == 'success' else run.error_message,
            user=user,
            target_type='academic_sync_run',
            target_id=run.id,
            metadata={
                'term_name': payload.term_name,
                'sync_scope': payload.sync_scope,
                'campus': payload.campus,
                'campuses': payload.campuses,
                'branch': payload.branch,
                'subject_count': len(payload.subject_codes),
                'dry_run': payload.dry_run,
                'counters': counters.as_dict(),
            },
        )
        if run.status != 'completed':
            raise HTTPException(status_code=502, detail=run.error_message or 'Đồng bộ AP thất bại')
        return {'ok': True, 'message': 'Đã đồng bộ dữ liệu AP', 'sync_run': run, 'counters': counters.as_dict()}
