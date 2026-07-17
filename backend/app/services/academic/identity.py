from __future__ import annotations

import math
from datetime import datetime
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.rbac import UserContext
from app.models.academic import (
    AcademicClass,
    AcademicClassStudent,
    AcademicStudent,
    AcademicStudentLearningSnapshot,
    AcademicSubject,
    AcademicTeacherAssignment,
    AcademicTerm,
    OpenEdXUserMapping,
)
from app.services.academic.helpers import _boolish, _page
from app.services.openedx_student_insight import normalize_username


class AcademicIdentityReconciliationWorkflowService:
    """RollNumber identity reconciliation, cleanup, and manual mapping import.

    This workflow isolates identity migration/reconciliation from the large
    AcademicService while keeping public route contracts unchanged. It contains
    both read-only reports and the explicitly guarded UAT cleanup/manual import
    mutations. Low-level shared helpers such as `_student_cms_username` and
    `_upsert_mapping` remain on the parent service and are accessed by
    delegation to avoid rewriting identity semantics.
    """

    def __init__(self, db: Session, parent: Any):
        self.db = db
        self.parent = parent
        self.rbac = getattr(parent, 'rbac', None)

    def __getattr__(self, name: str) -> Any:
        return getattr(self.parent, name)

    def _identity_reconciliation_status(self, student: AcademicStudent, mapping: OpenEdXUserMapping | None, *, duplicate_code_count: int = 0, duplicate_canonical_mapping_count: int = 0) -> dict[str, Any]:
            """Dry-run identity reconciliation for the RollNumber CMS username policy.

            v25.9.16.7.2.50 intentionally does not mutate Open edX users.  It
            classifies each learner so production admins can see whether an old AP
            username/email based CMS user exists before running new RollNumber based
            create/enroll flows.
            """
            canonical_username = self._student_cms_username(student)
            canonical_lookup = normalize_username(canonical_username)
            ap_username = normalize_username(student.username)
            student_code = str(student.student_code or '').strip()
            openedx_username = normalize_username(mapping.openedx_username if mapping else '')
            match_status = str(mapping.match_status if mapping else 'not_checked').lower()
            openedx_is_active = mapping.openedx_is_active if mapping else None
            blockers: list[str] = []
            warnings: list[str] = []
            action = 'run_cms_user_sync'
            status_value = 'READY_FOR_ROLLNUMBER'
            severity = 'warning'
            can_enroll = False

            if not student_code:
                status_value = 'MISSING_ROLLNUMBER'
                severity = 'blocker'
                blockers.append('Sinh viên thiếu RollNumber/student_code nên không thể tạo username CMS chuẩn FEID.')
                action = 'fix_ap_student_code'
            elif duplicate_code_count > 1:
                status_value = 'DUPLICATE_ROLLNUMBER'
                severity = 'blocker'
                blockers.append('RollNumber/student_code bị trùng trong AI Server; không được tự map hoặc enroll cho tới khi dữ liệu AP được làm sạch.')
                action = 'fix_duplicate_rollnumber'
            elif mapping and duplicate_canonical_mapping_count > 1:
                status_value = 'DUPLICATE_CMS_MAPPING'
                severity = 'blocker'
                blockers.append('Nhiều mapping nội bộ đang trỏ tới cùng username CMS canonical; cần kiểm tra trước khi chạy enrollment.')
                action = 'review_duplicate_cms_mapping'
            elif mapping and openedx_username == canonical_lookup and match_status == 'matched' and openedx_is_active is not False:
                status_value = 'OK'
                severity = 'info'
                can_enroll = True
                action = 'none'
            elif mapping and openedx_username == canonical_lookup and openedx_is_active is False:
                status_value = 'CANONICAL_INACTIVE'
                severity = 'warning'
                warnings.append('Mapping đã đúng RollNumber nhưng user CMS đang inactive hoặc connector trả inactive.')
                action = 'review_cms_user_active_status'
            elif mapping and openedx_username and openedx_username == ap_username and canonical_lookup != ap_username:
                status_value = 'LEGACY_AP_USERNAME'
                severity = 'blocker'
                blockers.append('Mapping hiện tại dùng AP username/email cũ thay vì RollNumber. Nếu chạy tạo mới ngay có thể sinh user CMS trùng người học.')
                action = 'review_legacy_user_before_rollnumber_sync'
            elif mapping and openedx_username and openedx_username != canonical_lookup:
                status_value = 'CMS_USERNAME_MISMATCH'
                severity = 'blocker'
                blockers.append('Mapping CMS hiện tại không khớp RollNumber cũng không khớp AP username; cần kiểm tra tay.')
                action = 'manual_identity_review'
            elif mapping and match_status in {'missing', 'manual_required', 'not_checked'}:
                status_value = 'READY_FOR_ROLLNUMBER'
                severity = 'warning'
                warnings.append('Chưa có mapping CMS chính xác; lần đồng bộ tiếp theo sẽ dùng RollNumber để tạo/kiểm tra user CMS.')
                action = 'run_cms_user_sync'
            elif not mapping:
                status_value = 'MISSING_MAPPING'
                severity = 'warning'
                warnings.append('Chưa có bản ghi mapping CMS; lần đồng bộ tiếp theo sẽ dùng RollNumber để tạo/kiểm tra user CMS.')
                action = 'run_cms_user_sync'

            return {
                'student_id': student.id,
                'student_code': student.student_code,
                'full_name': student.full_name,
                'email': student.email,
                'ap_username': ap_username,
                'canonical_username': canonical_username,
                'openedx_username': mapping.openedx_username if mapping else None,
                'openedx_user_id': mapping.openedx_user_id if mapping else None,
                'openedx_is_active': openedx_is_active,
                'match_status': mapping.match_status if mapping else 'not_checked',
                'match_method': mapping.match_method if mapping else 'not_checked',
                'status': status_value,
                'severity': severity,
                'can_enroll': can_enroll,
                'recommended_action': action,
                'blockers': blockers,
                'warnings': warnings,
                'duplicate_rollnumber_count': duplicate_code_count,
                'duplicate_canonical_mapping_count': duplicate_canonical_mapping_count,
            }

    def identity_reconciliation_for_class(
            self,
            user: UserContext,
            class_id: str,
            *,
            status_filter: str | None = None,
            page: int = 1,
            page_size: int = 200,
        ) -> dict[str, Any]:
            """Return a dry-run RollNumber identity audit for one class.

            This is deliberately read-only.  It helps admins detect legacy CMS users
            created from AP usernames before the RollNumber policy is used for broad
            enrollment or learning sync.
            """
            self.assert_can_access_class(user, class_id)
            cls = self.db.get(AcademicClass, class_id)
            if not cls:
                raise HTTPException(status_code=404, detail='Không tìm thấy lớp')
            page, page_size = _page(page, page_size)
            status_filter_value = str(status_filter or 'all').strip().upper()

            roster_rows = self.db.query(AcademicStudent, OpenEdXUserMapping).join(
                AcademicClassStudent,
                AcademicClassStudent.student_id == AcademicStudent.id,
            ).outerjoin(
                OpenEdXUserMapping,
                OpenEdXUserMapping.student_id == AcademicStudent.id,
            ).filter(AcademicClassStudent.class_id == class_id).order_by(AcademicStudent.student_code.asc().nullslast(), AcademicStudent.username.asc()).all()

            code_values = [str(student.student_code or '').strip().lower() for student, _mapping in roster_rows if str(student.student_code or '').strip()]
            code_counts: dict[str, int] = {}
            for code in code_values:
                code_counts[code] = code_counts.get(code, 0) + 1
            mapping_user_values = [normalize_username(mapping.openedx_username) for _student, mapping in roster_rows if mapping and normalize_username(mapping.openedx_username)]
            mapping_user_counts: dict[str, int] = {}
            for username in mapping_user_values:
                mapping_user_counts[username] = mapping_user_counts.get(username, 0) + 1

            rows: list[dict[str, Any]] = []
            counts: dict[str, int] = {
                'total': 0,
                'ok': 0,
                'blocker': 0,
                'warning': 0,
                'info': 0,
                'legacy_ap_username': 0,
                'duplicate_rollnumber': 0,
                'duplicate_cms_mapping': 0,
                'missing_rollnumber': 0,
                'missing_mapping': 0,
                'ready_for_rollnumber': 0,
                'cms_username_mismatch': 0,
                'canonical_inactive': 0,
                'can_enroll': 0,
            }
            for student, mapping in roster_rows:
                canonical = self._student_cms_username(student)
                row = self._identity_reconciliation_status(
                    student,
                    mapping,
                    duplicate_code_count=code_counts.get(str(student.student_code or '').strip().lower(), 0),
                    duplicate_canonical_mapping_count=mapping_user_counts.get(canonical, 0),
                )
                if status_filter_value != 'ALL' and str(row.get('status') or '').upper() != status_filter_value:
                    continue
                rows.append(row)
                counts['total'] += 1
                severity = str(row.get('severity') or 'info').lower()
                counts[severity] = counts.get(severity, 0) + 1
                status_key = str(row.get('status') or '').lower()
                counts[status_key] = counts.get(status_key, 0) + 1
                if row.get('can_enroll'):
                    counts['can_enroll'] += 1

            total_filtered = len(rows)
            start = (page - 1) * page_size
            page_rows = rows[start:start + page_size]
            primary_status = 'ready'
            if counts.get('blocker', 0) > 0:
                primary_status = 'blocked'
            elif counts.get('warning', 0) > 0:
                primary_status = 'needs_sync'
            summary_message = 'Identity CMS/Open edX đã sẵn sàng theo RollNumber.'
            if primary_status == 'blocked':
                summary_message = 'Có rủi ro identity trước production. Cần xử lý blocker trước khi chạy enroll/sync diện rộng.'
            elif primary_status == 'needs_sync':
                summary_message = 'Có sinh viên chưa có mapping CMS; có thể chạy Đồng bộ full CMS để tạo/kiểm tra bằng RollNumber nếu không có blocker.'

            return {
                'ok': True,
                'class_id': class_id,
                'class_code': cls.class_code,
                'status': primary_status,
                'message': summary_message,
                'policy': 'rollnumber_canonical_username',
                'dry_run': True,
                'mutation_performed': False,
                'counts': counts,
                'total': total_filtered,
                'page': page,
                'page_size': page_size,
                'total_pages': max(1, math.ceil(total_filtered / page_size)) if total_filtered else 1,
                'has_next': start + page_size < total_filtered,
                'items': page_rows,
                'next_actions': self._identity_reconciliation_next_actions(counts),
            }

    def cleanup_identity_reconciliation_for_class(self, user: UserContext, class_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
            """UAT-only cleanup of wrong AI Server identity mappings.

            This deliberately deletes only AI Server data (openedx_user_mappings and
            optional stale class learning snapshots). It never deletes Open edX
            Django users. After cleanup, operators should run Đồng bộ full CMS so the
            connector recreates/checks the learner by RollNumber/student_code.
            """
            self.assert_can_access_class(user, class_id)
            cls = self.db.get(AcademicClass, class_id)
            if not cls:
                raise HTTPException(status_code=404, detail='Không tìm thấy lớp')
            payload = payload or {}
            dry_run = bool(payload.get('dry_run', True))
            confirm_phrase = str(payload.get('confirm_phrase') or '').strip()
            required_phrase = str(getattr(settings, 'academic_identity_cleanup_confirm_phrase', 'DELETE_WRONG_UAT_IDENTITY') or 'DELETE_WRONG_UAT_IDENTITY')
            destructive_allowed = bool(getattr(settings, 'academic_identity_cleanup_allow_destructive', False))
            env_value = str(getattr(settings, 'app_env', '') or '').strip().lower()
            if env_value in {'dev', 'local', 'test', 'testing', 'uat', 'staging'}:
                destructive_allowed = True
            selected_statuses = {
                str(item or '').strip().upper()
                for item in (payload.get('statuses') or ['LEGACY_AP_USERNAME', 'CMS_USERNAME_MISMATCH', 'DUPLICATE_CMS_MAPPING', 'CANONICAL_INACTIVE'])
                if str(item or '').strip()
            }
            allowed_statuses = {'LEGACY_AP_USERNAME', 'CMS_USERNAME_MISMATCH', 'DUPLICATE_CMS_MAPPING', 'CANONICAL_INACTIVE', 'READY_FOR_ROLLNUMBER'}
            selected_statuses = selected_statuses & allowed_statuses
            if not selected_statuses:
                selected_statuses = {'LEGACY_AP_USERNAME', 'CMS_USERNAME_MISMATCH', 'DUPLICATE_CMS_MAPPING', 'CANONICAL_INACTIVE'}
            student_id_filter = {str(item).strip() for item in (payload.get('student_ids') or []) if str(item).strip()}
            delete_snapshots = bool(payload.get('delete_wrong_learning_snapshots', True))
            if not dry_run:
                if not destructive_allowed:
                    raise HTTPException(
                        status_code=403,
                        detail='Chưa bật ACADEMIC_IDENTITY_CLEANUP_ALLOW_DESTRUCTIVE=true hoặc APP_ENV=uat/staging/dev/test cho thao tác xóa identity UAT.',
                    )
                if confirm_phrase != required_phrase:
                    raise HTTPException(
                        status_code=400,
                        detail=f'Thiếu confirm_phrase chính xác: {required_phrase}',
                    )

            roster_rows = self.db.query(AcademicStudent, OpenEdXUserMapping).join(
                AcademicClassStudent,
                AcademicClassStudent.student_id == AcademicStudent.id,
            ).outerjoin(
                OpenEdXUserMapping,
                OpenEdXUserMapping.student_id == AcademicStudent.id,
            ).filter(AcademicClassStudent.class_id == class_id).order_by(AcademicStudent.student_code.asc().nullslast(), AcademicStudent.username.asc()).all()

            code_values = [str(student.student_code or '').strip().lower() for student, _mapping in roster_rows if str(student.student_code or '').strip()]
            code_counts: dict[str, int] = {}
            for code in code_values:
                code_counts[code] = code_counts.get(code, 0) + 1
            mapping_user_values = [normalize_username(mapping.openedx_username) for _student, mapping in roster_rows if mapping and normalize_username(mapping.openedx_username)]
            mapping_user_counts: dict[str, int] = {}
            for username in mapping_user_values:
                mapping_user_counts[username] = mapping_user_counts.get(username, 0) + 1

            counts: dict[str, int] = {
                'candidates': 0,
                'mapping_delete_candidates': 0,
                'snapshot_delete_candidates': 0,
                'mappings_deleted': 0,
                'snapshots_deleted': 0,
                'skipped': 0,
            }
            items: list[dict[str, Any]] = []
            skipped: list[dict[str, Any]] = []
            deleted_mapping_ids: list[str] = []
            deleted_snapshot_ids: list[str] = []

            for student, mapping in roster_rows:
                if student_id_filter and student.id not in student_id_filter:
                    continue
                canonical = self._student_cms_username(student)
                row = self._identity_reconciliation_status(
                    student,
                    mapping,
                    duplicate_code_count=code_counts.get(str(student.student_code or '').strip().lower(), 0),
                    duplicate_canonical_mapping_count=mapping_user_counts.get(canonical, 0),
                )
                status_value = str(row.get('status') or '').upper()
                if status_value not in selected_statuses:
                    continue
                if status_value in {'MISSING_ROLLNUMBER', 'DUPLICATE_ROLLNUMBER'}:
                    skipped.append({'student_id': student.id, 'student_code': student.student_code, 'status': status_value, 'reason': 'Không xóa mapping khi RollNumber thiếu/trùng; phải sửa dữ liệu AP trước.'})
                    counts['skipped'] += 1
                    continue
                if mapping is None:
                    skipped.append({'student_id': student.id, 'student_code': student.student_code, 'status': status_value, 'reason': 'Không có mapping nội bộ để xóa.'})
                    counts['skipped'] += 1
                    continue
                counts['candidates'] += 1
                counts['mapping_delete_candidates'] += 1
                snapshot_query = self.db.query(AcademicStudentLearningSnapshot).filter(
                    AcademicStudentLearningSnapshot.class_id == class_id,
                    AcademicStudentLearningSnapshot.student_id == student.id,
                )
                if canonical:
                    snapshot_query = snapshot_query.filter(or_(
                        AcademicStudentLearningSnapshot.openedx_username.is_(None),
                        func.lower(AcademicStudentLearningSnapshot.openedx_username) != canonical,
                    ))
                stale_snapshots = snapshot_query.all() if delete_snapshots else []
                counts['snapshot_delete_candidates'] += len(stale_snapshots)
                cleanup_item = dict(row)
                cleanup_item['mapping_id'] = mapping.id
                cleanup_item['stale_snapshot_count'] = len(stale_snapshots)
                cleanup_item['cleanup_action'] = 'delete_mapping_and_stale_snapshots' if delete_snapshots else 'delete_mapping_only'
                items.append(cleanup_item)
                if not dry_run:
                    for snapshot in stale_snapshots:
                        deleted_snapshot_ids.append(snapshot.id)
                        self.db.delete(snapshot)
                        counts['snapshots_deleted'] += 1
                    deleted_mapping_ids.append(mapping.id)
                    self.db.delete(mapping)
                    counts['mappings_deleted'] += 1

            if not dry_run:
                self.db.commit()

            message = 'Dry-run cleanup identity UAT: chưa xóa dữ liệu.' if dry_run else 'Đã xóa mapping/snapshot identity sai trong AI Server cho UAT.'
            next_actions = [
                'Kiểm tra lại identity reconciliation sau cleanup.',
                'Chạy Đồng bộ full CMS để tạo/kiểm tra user CMS bằng RollNumber.',
                'Sau khi mapping OK, chạy Ghi danh CMS/Cập nhật điểm nếu cần.',
            ]
            return {
                'ok': True,
                'class_id': class_id,
                'class_code': cls.class_code,
                'dry_run': dry_run,
                'mutation_performed': not dry_run,
                'destructive_allowed': destructive_allowed,
                'confirm_phrase_required': required_phrase,
                'policy': 'uat_rollnumber_identity_cleanup',
                'counts': counts,
                'deleted_mapping_ids': deleted_mapping_ids,
                'deleted_snapshot_ids': deleted_snapshot_ids,
                'skipped': skipped[:200],
                'items': items[:500],
                'message': message,
                'next_actions': next_actions,
            }

    def _identity_reconciliation_next_actions(self, counts: dict[str, int]) -> list[str]:
            actions: list[str] = []
            if counts.get('duplicate_rollnumber', 0):
                actions.append('Làm sạch dữ liệu AP: RollNumber/student_code đang bị trùng.')
            if counts.get('legacy_ap_username', 0):
                actions.append('Kiểm tra user CMS legacy đang dùng AP username/email trước khi tạo user RollNumber để tránh trùng người học.')
            if counts.get('cms_username_mismatch', 0) or counts.get('duplicate_cms_mapping', 0):
                actions.append('Rà soát mapping CMS thủ công cho các dòng mismatch/duplicate.')
            if counts.get('missing_rollnumber', 0):
                actions.append('Bổ sung RollNumber/student_code từ AP/FEID trước khi chạy đồng bộ diện rộng.')
            if counts.get('missing_mapping', 0) or counts.get('ready_for_rollnumber', 0):
                actions.append('Chạy Đồng bộ full CMS để tạo/kiểm tra user CMS bằng RollNumber cho các dòng chưa có mapping.')
            if not actions:
                actions.append('Có thể tiếp tục enrollment/cập nhật điểm theo mapping RollNumber hiện tại.')
            return actions

    def rollnumber_identity_migration_report(
            self,
            user: UserContext,
            *,
            class_id: str | None = None,
            term_id: str | None = None,
            campus: str | None = None,
            branch: str | None = None,
            subject_id: str | None = None,
            status_filter: str | None = None,
            page: int = 1,
            page_size: int = 200,
        ) -> dict[str, Any]:
            """Read-only RollNumber identity migration assistant.

            v25.9.16.7.2.64.13 intentionally does not mutate mappings or Open edX
            users.  It is a scoped, paginated dry-run report for UAT/pilot planning
            after the CMS username policy switched from AP username/email to
            RollNumber/student_code.
            """
            page, page_size = _page(page, page_size)
            class_id_value = str(class_id or '').strip() or None
            if class_id_value:
                self.assert_can_access_class(user, class_id_value)

            query = self.db.query(
                AcademicClass,
                AcademicSubject,
                AcademicTerm,
                AcademicStudent,
                OpenEdXUserMapping,
            ).join(
                AcademicSubject, AcademicSubject.id == AcademicClass.subject_id
            ).join(
                AcademicTerm, AcademicTerm.id == AcademicClass.term_id
            ).join(
                AcademicClassStudent, AcademicClassStudent.class_id == AcademicClass.id
            ).join(
                AcademicStudent, AcademicStudent.id == AcademicClassStudent.student_id
            ).outerjoin(
                OpenEdXUserMapping, OpenEdXUserMapping.student_id == AcademicStudent.id
            ).filter(
                AcademicStudent.active.is_(True),
            )

            if class_id_value:
                query = query.filter(AcademicClass.id == class_id_value)
            if term_id:
                query = query.filter(AcademicClass.term_id == str(term_id).strip())
            if subject_id:
                query = query.filter(AcademicClass.subject_id == str(subject_id).strip())
            if campus and str(campus).strip().lower() not in {'all', '*'}:
                query = query.filter(func.lower(AcademicClass.campus) == str(campus).strip().lower())
            if branch and str(branch).strip().lower() not in {'all', '*'}:
                query = query.filter(func.lower(AcademicClass.branch) == str(branch).strip().lower())

            decision = self.access_decision(user)
            if not decision.unrestricted and not class_id_value:
                scope_conditions = []
                if decision.campus_codes:
                    scope_conditions.append(func.lower(AcademicClass.campus).in_(decision.campus_codes))
                if decision.subject_codes:
                    scope_conditions.append(func.lower(AcademicSubject.subject_code).in_(decision.subject_codes))
                if decision.teacher_ids:
                    teacher_class_rows = self.db.query(AcademicTeacherAssignment.class_id).filter(
                        AcademicTeacherAssignment.teacher_id.in_(decision.teacher_ids)
                    ).all()
                    teacher_class_ids = [row[0] for row in teacher_class_rows if row and row[0]]
                    if teacher_class_ids:
                        scope_conditions.append(AcademicClass.id.in_(teacher_class_ids))
                if not scope_conditions:
                    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='Bạn chưa được phân quyền cơ sở/môn hoặc AP phân công lớp nào trên AI Server')
                query = query.filter(or_(*scope_conditions))

            query = query.order_by(
                AcademicTerm.start_date.desc().nullslast(),
                AcademicSubject.subject_code.asc(),
                AcademicClass.class_code.asc(),
                AcademicStudent.student_code.asc().nullslast(),
                AcademicStudent.username.asc(),
            )
            raw_rows = query.limit(20000).all()

            code_counts: dict[str, int] = {}
            mapping_user_counts: dict[str, int] = {}
            for _cls, _subject, _term, student, mapping in raw_rows:
                code = str(student.student_code or '').strip().lower()
                if code:
                    code_counts[code] = code_counts.get(code, 0) + 1
                mapped = normalize_username(mapping.openedx_username if mapping else '')
                if mapped:
                    mapping_user_counts[mapped] = mapping_user_counts.get(mapped, 0) + 1

            filter_value = str(status_filter or 'all').strip().upper()
            items: list[dict[str, Any]] = []
            counts: dict[str, int] = {}
            severity_counts: dict[str, int] = {'info': 0, 'warning': 0, 'blocker': 0}
            for cls, subject, term, student, mapping in raw_rows:
                canonical = self._student_cms_username(student)
                row = self._identity_reconciliation_status(
                    student,
                    mapping,
                    duplicate_code_count=code_counts.get(str(student.student_code or '').strip().lower(), 0),
                    duplicate_canonical_mapping_count=mapping_user_counts.get(canonical, 0),
                )
                status_value = str(row.get('status') or '').upper()
                severity_value = str(row.get('severity') or 'info').lower()
                if filter_value not in {'', 'ALL'}:
                    if filter_value == 'BLOCKERS' and severity_value != 'blocker':
                        continue
                    if filter_value == 'WARNINGS' and severity_value != 'warning':
                        continue
                    if filter_value not in {'BLOCKERS', 'WARNINGS'} and status_value != filter_value:
                        continue
                counts[status_value.lower()] = counts.get(status_value.lower(), 0) + 1
                severity_counts[severity_value] = severity_counts.get(severity_value, 0) + 1
                items.append({
                    **row,
                    'class_id': cls.id,
                    'class_code': cls.class_code,
                    'class_name': cls.class_name,
                    'term_id': term.id,
                    'term_name': term.term_name,
                    'subject_id': subject.id,
                    'subject_code': subject.subject_code,
                    'subject_name': subject.subject_name,
                    'campus': cls.campus,
                    'branch': cls.branch,
                })

            total = len(items)
            start = (page - 1) * page_size
            paged = items[start:start + page_size]
            total_pages = max(1, math.ceil(total / page_size)) if total else 1
            blocker_count = int(severity_counts.get('blocker', 0) or 0)
            warning_count = int(severity_counts.get('warning', 0) or 0)
            if blocker_count:
                report_status = 'BLOCKED'
                message = f'Có {blocker_count} blocker identity RollNumber cần xử lý trước khi đồng bộ/enroll diện rộng.'
            elif warning_count:
                report_status = 'READY_WITH_WARNINGS'
                message = f'Không có blocker, còn {warning_count} cảnh báo. Có thể pilot có kiểm soát sau khi review.'
            else:
                report_status = 'READY'
                message = 'Mapping identity RollNumber trong phạm vi kiểm tra đã sẵn sàng cho đồng bộ/enroll.'

            next_actions = self._identity_reconciliation_next_actions(counts)
            if blocker_count:
                next_actions.insert(0, 'Không chạy Đồng bộ full CMS diện rộng cho tới khi các dòng blocker được xử lý hoặc cleanup UAT có kiểm soát.')
            elif warning_count:
                next_actions.insert(0, 'Chạy thử Đồng bộ full CMS trên một lớp pilot trước khi mở rộng toàn bộ học kỳ/cơ sở.')
            else:
                next_actions.insert(0, 'Có thể tiếp tục CMS sync/enrollment theo username RollNumber trong phạm vi đã kiểm tra.')

            return {
                'ok': True,
                'status': report_status,
                'message': message,
                'policy': 'rollnumber_identity_migration_assistant',
                'dry_run': True,
                'mutation_performed': False,
                'scope': {
                    'class_id': class_id_value,
                    'term_id': str(term_id or '').strip() or None,
                    'campus': str(campus or '').strip() or None,
                    'branch': str(branch or '').strip() or None,
                    'subject_id': str(subject_id or '').strip() or None,
                    'status_filter': filter_value or 'ALL',
                    'max_scanned_rows': 20000,
                },
                'counts': counts,
                'severity_counts': severity_counts,
                'total': total,
                'scanned': len(raw_rows),
                'page': page,
                'page_size': page_size,
                'total_pages': total_pages,
                'has_next': page < total_pages,
                'items': paged,
                'next_actions': next_actions[:10],
                'export_hints': {
                    'script': 'scripts/rollnumber-identity-migration-report.sh',
                    'endpoint': '/api/academic/identity/rollnumber-migration',
                    'safe': 'read_only_no_openedx_mutation',
                    'filters': ['class_id', 'term_id', 'campus', 'branch', 'subject_id', 'status_filter'],
                },
            }

    def import_openedx_user_mappings(self, records: list[dict[str, Any]], *, requested_by: str | None = None) -> dict[str, Any]:
            now = datetime.utcnow()
            total = len(records)
            counters = {'matched': 0, 'inactive': 0, 'missing_student': 0, 'invalid': 0, 'updated': 0}
            errors: list[dict[str, Any]] = []
            for index, record in enumerate(records, start=1):
                ap_username = normalize_username(record.get('ap_username') or record.get('username') or record.get('apUserName'))
                student_code = str(record.get('student_code') or record.get('studentCode') or record.get('ap_student_code') or '').strip()
                if not ap_username and not student_code:
                    counters['invalid'] += 1
                    errors.append({'row': index, 'message': 'Thiếu ap_username hoặc student_code'})
                    continue
                student_query = self.db.query(AcademicStudent)
                if ap_username:
                    student = student_query.filter(func.lower(AcademicStudent.username) == ap_username).first()
                else:
                    student = None
                if not student and student_code:
                    student = self.db.query(AcademicStudent).filter(func.lower(AcademicStudent.student_code) == student_code.lower()).first()
                if not student:
                    counters['missing_student'] += 1
                    errors.append({'row': index, 'ap_username': ap_username, 'student_code': student_code, 'message': 'Không tìm thấy sinh viên AP trong AI Server'})
                    continue
                openedx_username = str(record.get('openedx_username') or record.get('openedxUsername') or record.get('username') or '').strip()
                openedx_user_id = str(record.get('openedx_user_id') or record.get('user_id') or record.get('id') or '').strip()
                is_active_raw = record.get('is_active', record.get('openedx_is_active', True))
                is_active = _boolish(is_active_raw)
                status_value = 'matched' if openedx_username or openedx_user_id else 'manual_required'
                if status_value == 'matched' and is_active is False:
                    status_value = 'inactive'
                result = {
                    'openedx_user_id': openedx_user_id or None,
                    'openedx_username': openedx_username or self._student_cms_username(student) or None,
                    'openedx_email': record.get('openedx_email') or record.get('email'),
                    'is_active': True if is_active is None else is_active,
                    'match_status': status_value,
                    'match_method': 'manual',
                    'note': str(record.get('note') or f'Imported by {requested_by or "system"} at {now.isoformat()}')[:4000],
                }
                mapping = self._upsert_mapping(student, result, source='manual_import')
                counters[mapping.match_status] = counters.get(mapping.match_status, 0) + 1
                counters['updated'] += 1
            self.db.commit()
            return {'ok': True, 'total': total, 'counters': counters, 'errors': errors[:100]}
