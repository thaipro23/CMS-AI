from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from fastapi import HTTPException
from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.rbac import UserContext
from app.models.academic import (
    AcademicClass,
    AcademicClassCourseMapping,
    AcademicCourseMapping,
    AcademicClassStudent,
    AcademicStudent,
    AcademicStudentLearningSnapshot,
    AcademicSubject,
    AcademicTeacher,
    AcademicTerm,
    OpenEdXUserMapping,
)
from app.services.academic.helpers import _boolish, _derive_mapping_status, _json_safe_value, _validation_result
from app.services.openedx_student_insight import OpenEdXConnectorClient, normalize_username


class AcademicSyncEnrollmentWorkflowService:
    """CMS identity, enrollment, learning sync, and full CMS flow.

    This workflow is intentionally separated from AcademicService after the
    Student Ops access/roster split. It keeps public response shapes and sync
    semantics unchanged while isolating mutation-heavy Open edX connector flows.
    Low-level helpers that are still shared with other workflows remain on the
    parent service and are accessed through ``__getattr__``.
    """

    def __init__(self, db: Session, parent: Any):
        self.db = db
        self.parent = parent
        self.rbac = getattr(parent, 'rbac', None)
        self.CONNECTOR_MIN_CONTRACT_VERSION = getattr(parent, 'CONNECTOR_MIN_CONTRACT_VERSION', 'learning-sync/v25.9.16.5.98')
        self.CONNECTOR_MIN_RUNTIME_VERSION = getattr(parent, 'CONNECTOR_MIN_RUNTIME_VERSION', '25.9.16.5.98')

    def __getattr__(self, name: str) -> Any:
        return getattr(self.parent, name)

def _student_rollnumber(self, student: AcademicStudent) -> str:
        """Return the authoritative AP RollNumber without changing its case."""
        return str(student.student_code or '').strip()

def _student_cms_username(self, student: AcademicStudent) -> str:
        """Canonical CMS/Open edX username for students.

        RollNumber/student_code is the only allowed student username source.  Its
        original case is preserved when a new Open edX user is created, e.g.
        ``PH12345`` remains ``PH12345``.  AP username/email is metadata only and
        must never be used as a fallback CMS username.
        """
        return self._student_rollnumber(student)

def _student_cms_email(self, student: AcademicStudent) -> str | None:
        synced_email = str(student.email or '').strip()
        if synced_email:
            return synced_email
        username = self._student_cms_username(student)
        return f'{username}@fpt.edu.vn' if username else None

def _student_cms_payload(self, student: AcademicStudent, *, create_missing: bool, openedx_user_id: str | None = None) -> dict[str, Any]:
        cms_username = self._student_cms_username(student)
        return {
            'student_code': student.student_code,
            'roll_number': student.student_code,
            # AP username is retained only for diagnostics/audit correlation.
            'ap_username': normalize_username(student.username),
            'username': cms_username,
            'openedx_username': cms_username,
            'openedx_user_id': openedx_user_id,
            'person_type': 'student',
            'role': 'student',
            'email': self._student_cms_email(student),
            'full_name': student.full_name,
            'create_missing': bool(create_missing and cms_username),
            'identity_source': 'rollnumber',
        }

def _upsert_teacher_cms_metadata(self, teacher: AcademicTeacher, result: dict[str, Any] | None) -> str:
        now = datetime.utcnow()
        result = result or {}
        status_value, _method, _confidence, _note = _derive_mapping_status(result)
        existing = teacher.metadata_json if isinstance(teacher.metadata_json, dict) else {}
        teacher.metadata_json = {
            **_json_safe_value(existing),
            'cms_user': {
                'status': status_value,
                'openedx_user_id': str(result.get('openedx_user_id') or result.get('user_id') or '').strip() or None,
                'openedx_username': str(result.get('openedx_username') or result.get('username') or '').strip() or None,
                'openedx_email': str(result.get('openedx_email') or result.get('email') or '').strip() or None,
                'openedx_is_active': _boolish(result.get('openedx_is_active', result.get('is_active'))),
                'match_method': str(result.get('match_method') or '').strip() or None,
                'created': _boolish(result.get('created')),
                'note': str(result.get('note') or '')[:1000],
                'last_resolved_at': now.isoformat(),
            }
        }
        teacher.updated_at = now
        self.db.add(teacher)
        return status_value

def resolve_class_openedx_users(self, user: UserContext, class_id: str, *, force: bool = False, limit: int = 1000, auto_enroll: bool = True, create_missing: bool | None = None) -> dict[str, Any]:
        self.assert_can_access_class(user, class_id)
        limit = max(1, min(500, int(limit or 500)))
        query = self.db.query(AcademicStudent, OpenEdXUserMapping).join(
            AcademicClassStudent,
            AcademicClassStudent.student_id == AcademicStudent.id,
        ).outerjoin(OpenEdXUserMapping, OpenEdXUserMapping.student_id == AcademicStudent.id).filter(
            AcademicClassStudent.class_id == class_id,
        ).order_by(AcademicStudent.username.asc()).limit(limit)
        rows = query.all()
        if not force:
            # Re-resolve legacy AP-username mappings. Only an active matched mapping
            # whose username equals RollNumber case-insensitively is already final.
            rows = [
                (student, mapping)
                for student, mapping in rows
                if not (
                    mapping
                    and mapping.match_status == 'matched'
                    and self._student_rollnumber(student)
                    and normalize_username(mapping.openedx_username or '') == normalize_username(self._student_rollnumber(student))
                    and mapping.openedx_is_active is not False
                )
            ]

        teacher_payload = self._teacher_payload_for_class(class_id)
        if not rows and not teacher_payload:
            return {'ok': True, 'class_id': class_id, 'total': 0, 'updated': 0, 'counts': {}, 'message': 'Không có sinh viên/giảng viên cần kiểm tra đồng bộ CMS', 'teachers': {'total': 0, 'updated': 0, 'counts': {}}}

        client = OpenEdXConnectorClient()
        batch_size = max(1, min(getattr(settings, 'openedx_connector_max_batch_size', settings.openedx_student_insight_max_batch_size), 100))
        updated = 0
        counts: dict[str, int] = {}
        effective_create_missing = (
            bool(getattr(settings, 'academic_auto_create_cms_users', True))
            if create_missing is None
            else bool(create_missing)
        )

        # Students: RollNumber/student_code is the only canonical CMS username.
        # Missing RollNumber is a blocking data error: do not call the connector,
        # do not create a user, and do not enroll through an AP username fallback.
        valid_rows: list[tuple[AcademicStudent, OpenEdXUserMapping | None]] = []
        for student, mapping in rows:
            roll_number = self._student_rollnumber(student)
            if roll_number:
                valid_rows.append((student, mapping))
                continue
            result = {
                'student_code': None,
                'roll_number': None,
                'ap_username': normalize_username(student.username),
                'username': None,
                'openedx_username': None,
                'exists': False,
                'created': False,
                'match_status': 'missing_student_code',
                'match_method': 'validation_failed',
                'note': 'Thiếu RollNumber/student_code nên không tạo user CMS/Open edX và không enroll',
            }
            mapping_row = self._upsert_mapping(student, result, source='openedx_connector')
            counts[mapping_row.match_status] = counts.get(mapping_row.match_status, 0) + 1
            updated += 1
        if rows:
            self.db.flush()

        for start in range(0, len(valid_rows), batch_size):
            chunk = valid_rows[start:start + batch_size]
            payload = [self._student_cms_payload(student, create_missing=effective_create_missing) for student, _mapping in chunk]
            results = client.resolve_users(payload, create_missing=effective_create_missing)
            result_by_username = {normalize_username(item.get('username') or item.get('openedx_username')): item for item in results if normalize_username(item.get('username') or item.get('openedx_username'))}
            result_by_code = {normalize_username(item.get('student_code') or item.get('roll_number')): item for item in results if normalize_username(item.get('student_code') or item.get('roll_number'))}
            for student, _mapping in chunk:
                cms_username = self._student_cms_username(student)
                lookup_username = normalize_username(cms_username)
                result = result_by_username.get(lookup_username)
                if result is None:
                    result = result_by_code.get(lookup_username)
                if result is None:
                    result = {
                        'student_code': student.student_code,
                        'roll_number': student.student_code,
                        'ap_username': normalize_username(student.username),
                        'username': cms_username,
                        'openedx_username': cms_username,
                        'exists': False,
                        'match_status': 'missing',
                        'match_method': 'not_found',
                        'note': 'Open edX plugin không trả user cho RollNumber/student_code này',
                    }
                mapping = self._upsert_mapping(student, result, source='openedx_connector')
                counts[mapping.match_status] = counts.get(mapping.match_status, 0) + 1
                if result.get('created') is True:
                    counts['created_user'] = counts.get('created_user', 0) + 1
                updated += 1
            self.db.flush()

        # Teachers: AP only provides values such as teacher="ngocnb61". Create
        # username/email/first_name/last_name deterministically in the plugin.
        teacher_counts: dict[str, int] = {}
        teacher_updated = 0
        if teacher_payload:
            for start in range(0, len(teacher_payload), batch_size):
                chunk = teacher_payload[start:start + batch_size]
                results = client.resolve_users([payload for _teacher, payload in chunk], create_missing=effective_create_missing)
                result_by_username = {normalize_username(item.get('username') or item.get('openedx_username') or item.get('ap_username')): item for item in results if normalize_username(item.get('username') or item.get('openedx_username') or item.get('ap_username'))}
                for teacher, payload in chunk:
                    username = normalize_username(payload.get('username'))
                    result = result_by_username.get(username) or {
                        'ap_username': username,
                        'username': username,
                        'person_type': 'teacher',
                        'exists': False,
                        'match_status': 'missing',
                        'match_method': 'not_found',
                        'note': 'Open edX plugin không trả user cho giảng viên này',
                    }
                    status_value = self._upsert_teacher_cms_metadata(teacher, result)
                    teacher_counts[status_value] = teacher_counts.get(status_value, 0) + 1
                    counts[f'teacher_{status_value}'] = counts.get(f'teacher_{status_value}', 0) + 1
                    if result.get('created') is True:
                        teacher_counts['created_user'] = teacher_counts.get('created_user', 0) + 1
                        counts['teacher_created_user'] = counts.get('teacher_created_user', 0) + 1
                    teacher_updated += 1
                self.db.flush()

        self.db.commit()
        enrollment_result = None
        if auto_enroll and getattr(settings, 'academic_auto_enroll_after_cms_sync', True):
            try:
                # Auto-enroll mapped students and add mapped/created teachers to Course Staff.
                enrollment_result = self.sync_class_course_enrollment(user, class_id, force=False, limit=limit)
                for key, value in (enrollment_result.get('counts') or {}).items():
                    counts[f'enrollment_{key}'] = int(value or 0)
            except HTTPException as exc:
                enrollment_result = {'ok': False, 'message': str(exc.detail)}
                counts['enrollment_skipped'] = counts.get('enrollment_skipped', 0) + 1
            except Exception as exc:
                enrollment_result = {'ok': False, 'message': str(exc)}
                counts['enrollment_failed'] = counts.get('enrollment_failed', 0) + 1
        message = 'Đã kiểm tra đồng bộ CMS theo RollNumber/student_code; tự tạo tài khoản CMS nếu chưa tồn tại'
        if enrollment_result:
            if enrollment_result.get('ok'):
                message += '; đã tự enroll sinh viên và gán giảng viên vào Course CMS nếu lớp đã map course'
            else:
                message += f"; chưa auto-enroll/gán giảng viên được: {enrollment_result.get('message')}"
        return {
            'ok': True,
            'class_id': class_id,
            'total': len(rows),
            'updated': updated,
            'counts': counts,
            'message': message,
            'enrollment': enrollment_result,
            'teachers': {'total': len(teacher_payload), 'updated': teacher_updated, 'counts': teacher_counts},
        }

def _upsert_enrollment_snapshot(self, *, class_id: str, student: AcademicStudent, course_id: str, result: dict[str, Any], source: str) -> AcademicStudentLearningSnapshot:
        """Update only enrollment fields without wiping progress/grade snapshots."""
        now = datetime.utcnow()
        snapshot = self.db.query(AcademicStudentLearningSnapshot).filter(
            AcademicStudentLearningSnapshot.class_id == class_id,
            AcademicStudentLearningSnapshot.student_id == student.id,
            AcademicStudentLearningSnapshot.openedx_course_id == course_id,
        ).first()
        if not snapshot:
            snapshot = AcademicStudentLearningSnapshot(class_id=class_id, student_id=student.id, openedx_course_id=course_id, created_at=now)
        enrollment = result.get('enrollment') if isinstance(result.get('enrollment'), dict) else {}
        raw_status = str(result.get('enrollment_status') or enrollment.get('status') or result.get('status') or '').strip().lower()
        is_enrolled = result.get('is_enrolled')
        if is_enrolled is None:
            is_enrolled = enrollment.get('is_enrolled')
        if raw_status in {'enrolled', 'already_enrolled', 'created', 'reactivated'} or is_enrolled is True:
            status_value = 'enrolled'
        elif raw_status in {'missing_user', 'inactive_user', 'not_mapped', 'failed', 'skipped'}:
            status_value = raw_status
        elif raw_status:
            status_value = raw_status
        else:
            status_value = 'unknown'
        snapshot.openedx_username = str(result.get('openedx_username') or result.get('username') or self._student_cms_username(student) or '').strip() or snapshot.openedx_username
        snapshot.openedx_user_id = str(result.get('openedx_user_id') or result.get('user_id') or '').strip() or snapshot.openedx_user_id
        snapshot.enrollment_status = status_value[:50]
        snapshot.enrollment_mode = str(result.get('enrollment_mode') or enrollment.get('mode') or '').strip()[:50] or snapshot.enrollment_mode
        existing_raw = snapshot.raw_json if isinstance(snapshot.raw_json, dict) else {}
        snapshot.raw_json = {**_json_safe_value(existing_raw), 'enrollment_source': source, 'enrollment_payload': _json_safe_value(result)}
        snapshot.enrollment_synced_at = now
        if snapshot.last_synced_at is None:
            snapshot.last_synced_at = now
        snapshot.updated_at = now
        self.db.add(snapshot)
        return snapshot

def sync_class_course_enrollment(self, user: UserContext, class_id: str, *, force: bool = False, limit: int = 1000, mode: str | None = None) -> dict[str, Any]:
        """Enroll AP students and add AP teachers to the mapped CMS/Open edX course.

        Students are enrolled only after exact RollNumber/student_code -> CMS user mapping.
        Teachers are resolved/created from AP teacher username and granted Course
        Staff in the course. No fuzzy matching is used.
        """
        self.assert_can_access_class(user, class_id)
        cls = self.db.get(AcademicClass, class_id)
        if not cls:
            raise HTTPException(status_code=404, detail='Không tìm thấy lớp')
        mapping = self.effective_course_mapping_for_class(cls)
        if not mapping or not mapping.openedx_course_id:
            raise HTTPException(status_code=400, detail='Lớp chưa có Course CMS nên chưa thể tự enrollment/gán giảng viên')
        course_id = mapping.openedx_course_id
        cohort_name = self._cohort_for_class_mapping(cls, mapping) or cls.class_code
        limit = max(1, min(500, int(limit or 500)))

        # Enrollment is self-healing: always resolve/create CMS users by the
        # authoritative RollNumber before querying mappings.  Full CMS sync must
        # not depend on a separate operator action or on the optional env flag.
        try:
            self.resolve_class_openedx_users(
                user,
                class_id,
                force=force,
                limit=limit,
                auto_enroll=False,
                create_missing=True,
            )
        except HTTPException:
            raise
        except Exception as exc:
            raise RuntimeError(f'Không tạo/kiểm tra được tài khoản CMS trước khi enrollment: {exc}') from exc

        self.db.expire_all()

        def matched_rows() -> list[tuple[AcademicStudent, OpenEdXUserMapping, AcademicStudentLearningSnapshot | None]]:
            query = self.db.query(AcademicStudent, OpenEdXUserMapping, AcademicStudentLearningSnapshot).join(
                AcademicClassStudent,
                AcademicClassStudent.student_id == AcademicStudent.id,
            ).join(OpenEdXUserMapping, OpenEdXUserMapping.student_id == AcademicStudent.id).outerjoin(
                AcademicStudentLearningSnapshot,
                and_(
                    AcademicStudentLearningSnapshot.class_id == class_id,
                    AcademicStudentLearningSnapshot.student_id == AcademicStudent.id,
                    AcademicStudentLearningSnapshot.openedx_course_id == course_id,
                ),
            ).filter(
                AcademicClassStudent.class_id == class_id,
                OpenEdXUserMapping.match_status == 'matched',
                or_(OpenEdXUserMapping.openedx_is_active.is_(None), OpenEdXUserMapping.openedx_is_active.is_(True)),
                or_(OpenEdXUserMapping.openedx_username.isnot(None), OpenEdXUserMapping.openedx_user_id.isnot(None)),
            ).order_by(AcademicStudent.username.asc()).limit(limit)
            return [
                (student, mapping_row, snapshot)
                for student, mapping_row, snapshot in query.all()
                if self._student_rollnumber(student)
                and normalize_username(mapping_row.openedx_username or '') == normalize_username(self._student_rollnumber(student))
            ]

        rows = matched_rows()
        matched_student_count = len(rows)
        if not force:
            rows = [(student, mapping_row, snapshot) for student, mapping_row, snapshot in rows if not snapshot or snapshot.enrollment_status not in {'enrolled'}]

        class_student_count = self.db.query(func.count(AcademicClassStudent.id)).filter(AcademicClassStudent.class_id == class_id).scalar() or 0
        missing_rollnumber_count = self.db.query(func.count(AcademicClassStudent.id)).join(
            AcademicStudent, AcademicStudent.id == AcademicClassStudent.student_id,
        ).filter(
            AcademicClassStudent.class_id == class_id,
            or_(AcademicStudent.student_code.is_(None), func.trim(AcademicStudent.student_code) == ''),
        ).scalar() or 0
        if int(class_student_count) > 0 and matched_student_count == 0:
            # One forced retry covers stale legacy mappings and partial connector
            # responses without asking the operator to run a separate action.
            retry_result = self.resolve_class_openedx_users(
                user,
                class_id,
                force=True,
                limit=limit,
                auto_enroll=False,
                create_missing=True,
            )
            self.db.expire_all()
            rows = matched_rows()
            matched_student_count = len(rows)
            if not force:
                rows = [
                    (student, mapping_row, snapshot)
                    for student, mapping_row, snapshot in rows
                    if not snapshot or snapshot.enrollment_status not in {'enrolled'}
                ]
            if matched_student_count == 0:
                retry_counts = retry_result.get('counts') or {}
                missing_hint = f' Có {int(missing_rollnumber_count)} sinh viên thiếu RollNumber/student_code và đã bị chặn tạo user/enroll.' if missing_rollnumber_count else ''
                raise HTTPException(
                    status_code=400,
                    detail=(
                        'Đồng bộ full đã tự chạy bước tạo/kiểm tra user CMS nhưng vẫn không có mapping RollNumber hợp lệ. '
                        f'Kết quả tạo user: {retry_counts}.' + missing_hint +
                        ' Hãy kiểm tra openedx-connector-plugin, HMAC và quyền tạo auth_user/UserProfile.'
                    ),
                )

        teacher_payload = self._teacher_payload_for_class(class_id) if getattr(settings, 'academic_auto_add_teachers_to_course', True) else []
        if not rows and not teacher_payload:
            summary = self._learning_summary_for_class_course(class_id, course_id)
            return {'ok': True, 'class_id': class_id, 'openedx_course_id': course_id, 'total': 0, 'updated': 0, 'processed': 0, 'verified': 0, 'counts': {}, 'message': 'Không có sinh viên/giảng viên cần xử lý Course CMS', 'learning_summary': summary, 'teachers': {'total': 0, 'updated': 0, 'processed': 0, 'verified': 0, 'counts': {}}}
        client = OpenEdXConnectorClient()
        batch_size = max(1, min(getattr(settings, 'openedx_connector_max_batch_size', settings.openedx_student_insight_max_batch_size), 100))
        counts: dict[str, int] = {}
        processed = 0
        updated = 0
        verified = 0
        failed_messages: list[str] = []
        teacher_counts: dict[str, int] = {}
        teacher_processed = 0
        teacher_updated = 0
        teacher_verified = 0
        enrollment_mode = (mode or getattr(settings, 'openedx_connector_default_enrollment_mode', getattr(settings, 'openedx_student_insight_default_enrollment_mode', 'audit')) or 'audit').strip() or 'audit'
        # Enrollment keeps create_missing enabled as a final safety net. The
        # resolve step above should already have created users, but the connector
        # can recover a single missing user atomically during enrollment.
        create_missing = True

        for start in range(0, len(rows), batch_size):
            chunk = rows[start:start + batch_size]
            payload = []
            for student, mapping_row, _snapshot in chunk:
                payload.append(self._student_cms_payload(
                    student,
                    create_missing=create_missing,
                    openedx_user_id=mapping_row.openedx_user_id,
                ))
            results = client.enroll_users(course_id=course_id, cohort_name=cohort_name, students=payload, mode=enrollment_mode, force=force, create_missing=create_missing)
            by_username = {normalize_username(item.get('username') or item.get('openedx_username') or item.get('ap_username')): item for item in results if normalize_username(item.get('username') or item.get('openedx_username') or item.get('ap_username'))}
            by_code = {str(item.get('student_code') or item.get('roll_number') or '').strip().lower(): item for item in results if str(item.get('student_code') or item.get('roll_number') or '').strip()}
            for student, mapping_row, _snapshot in chunk:
                key = self._student_cms_username(student)
                lookup_key = normalize_username(key)
                result = by_username.get(lookup_key) or by_username.get(normalize_username(mapping_row.openedx_username or ''))
                if result is None and student.student_code:
                    result = by_code.get(str(student.student_code).strip().lower())
                if result is None:
                    result = {
                        'student_code': student.student_code,
                        'roll_number': student.student_code,
                        'ap_username': normalize_username(student.username),
                        'username': key,
                        'openedx_username': key,
                        'enrollment_status': 'unknown',
                        'message': 'Plugin không trả kết quả enrollment cho sinh viên này',
                    }
                snapshot = self._upsert_enrollment_snapshot(class_id=class_id, student=student, course_id=course_id, result=result, source='openedx_connector_enrollment')
                raw_status = str(result.get('status') or result.get('enrollment_status') or snapshot.enrollment_status or 'unknown').strip().lower()
                is_enrolled = _boolish(result.get('is_enrolled')) or str(result.get('enrollment_status') or '').strip().lower() == 'enrolled'
                status_value = 'enrolled' if is_enrolled else raw_status
                counts[status_value] = counts.get(status_value, 0) + 1
                processed += 1
                if is_enrolled:
                    updated += 1
                    if result.get('verified_after_write') is not False:
                        verified += 1
                else:
                    message = str(result.get('message') or '').strip()
                    if message and len(failed_messages) < 5:
                        failed_messages.append(f"{student.username}: {message}")
            self.db.flush()

        # Add teachers to Course Staff. Teachers are not stored in student learning
        # snapshots; their status is kept in academic_teachers.metadata_json.
        if teacher_payload:
            for start in range(0, len(teacher_payload), batch_size):
                chunk = teacher_payload[start:start + batch_size]
                teacher_items = [payload for _teacher, payload in chunk]
                results = client.enroll_users(course_id=course_id, cohort_name=cohort_name, students=[], teachers=teacher_items, mode=enrollment_mode, force=force, create_missing=create_missing)
                result_by_username = {normalize_username(item.get('username') or item.get('openedx_username') or item.get('ap_username')): item for item in results if normalize_username(item.get('username') or item.get('openedx_username') or item.get('ap_username'))}
                for teacher, payload in chunk:
                    username = normalize_username(payload.get('username'))
                    result = result_by_username.get(username) or {'username': username, 'status': 'unknown', 'message': 'Plugin không trả kết quả gán giảng viên'}
                    existing = teacher.metadata_json if isinstance(teacher.metadata_json, dict) else {}
                    teacher.metadata_json = {
                        **_json_safe_value(existing),
                        'course_staff': {
                            'openedx_course_id': course_id,
                            'status': str(result.get('status') or result.get('enrollment_status') or 'unknown'),
                            'openedx_user_id': str(result.get('openedx_user_id') or result.get('user_id') or '').strip() or None,
                            'openedx_username': str(result.get('openedx_username') or result.get('username') or '').strip() or None,
                            'openedx_email': str(result.get('openedx_email') or result.get('email') or '').strip() or None,
                            'created_user': _boolish(result.get('created_user', result.get('created'))),
                            'message': str(result.get('message') or '')[:1000],
                            'last_synced_at': datetime.utcnow().isoformat(),
                        }
                    }
                    teacher.updated_at = datetime.utcnow()
                    self.db.add(teacher)
                    status_value = str(result.get('status') or result.get('enrollment_status') or 'unknown')
                    teacher_success = status_value in {'already_course_staff', 'course_staff_added'} or str(result.get('course_role') or '').strip().lower() == 'staff'
                    teacher_counts[status_value] = teacher_counts.get(status_value, 0) + 1
                    counts[f'teacher_{status_value}'] = counts.get(f'teacher_{status_value}', 0) + 1
                    teacher_processed += 1
                    if teacher_success:
                        teacher_updated += 1
                        if result.get('verified_after_write') is not False:
                            teacher_verified += 1
                    else:
                        message = str(result.get('message') or '').strip()
                        if message and len(failed_messages) < 5:
                            failed_messages.append(f"GV {username}: {message}")
                self.db.flush()

        if rows and updated == 0:
            self.db.commit()
            detail = '; '.join(failed_messages) if failed_messages else f"counts={counts}"
            raise RuntimeError(f'Enrollment Course CMS không có sinh viên nào được xác nhận enrolled trên Open edX sau khi gọi connector. {detail}')

        self.db.commit()
        summary = self._learning_summary_for_class_course(class_id, course_id)
        return {
            'ok': True,
            'class_id': class_id,
            'openedx_course_id': course_id,
            'total': len(rows),
            'processed': processed,
            'updated': updated,
            'verified': verified,
            'counts': counts,
            'message': f'Enrollment Course CMS hoàn tất: {updated}/{len(rows)} sinh viên được Open edX xác nhận enrolled; {teacher_updated}/{len(teacher_payload)} giảng viên được gán Course Staff.',
            'learning_summary': summary,
            'teachers': {'total': len(teacher_payload), 'processed': teacher_processed, 'updated': teacher_updated, 'verified': teacher_verified, 'counts': teacher_counts},
        }

def sync_class_learning_insight(self, user: UserContext, class_id: str, *, force: bool = False, limit: int = 1000) -> dict[str, Any]:
        self.assert_can_access_class(user, class_id)
        cls = self.db.get(AcademicClass, class_id)
        if not cls:
            raise HTTPException(status_code=404, detail='Không tìm thấy lớp')
        mapping = self.effective_course_mapping_for_class(cls)
        if not mapping or not mapping.openedx_course_id:
            raise HTTPException(status_code=400, detail='Lớp chưa có Course CMS. Hãy map Course CMS trước khi cập nhật tiến độ/điểm.')
        course_id = mapping.openedx_course_id
        cohort_name = self._cohort_for_class_mapping(cls, mapping) or cls.class_code
        limit = max(1, min(500, int(limit or 500)))
        # v25.9.16.5.85: Cập nhật điểm is read-only against CMS/Open edX.
        # It must not create CMS accounts and must not enroll learners. Full CMS
        # sync is the only flow that creates/checks users + enrolls + then reads
        # progress/grades.
        query = self.db.query(AcademicStudent, OpenEdXUserMapping, AcademicStudentLearningSnapshot).join(
            AcademicClassStudent,
            AcademicClassStudent.student_id == AcademicStudent.id,
        ).outerjoin(OpenEdXUserMapping, OpenEdXUserMapping.student_id == AcademicStudent.id).outerjoin(
            AcademicStudentLearningSnapshot,
            and_(
                AcademicStudentLearningSnapshot.class_id == class_id,
                AcademicStudentLearningSnapshot.student_id == AcademicStudent.id,
                AcademicStudentLearningSnapshot.openedx_course_id == course_id,
            ),
        ).filter(AcademicClassStudent.class_id == class_id).order_by(AcademicStudent.username.asc()).limit(limit)
        rows = [
            (student, mapping_row, snapshot)
            for student, mapping_row, snapshot in query.all()
            if self._student_rollnumber(student)
            and (
                mapping_row is None
                or not mapping_row.openedx_username
                or normalize_username(mapping_row.openedx_username) == normalize_username(self._student_rollnumber(student))
            )
        ]
        if not force:
            rows = [(student, mapping_row, snapshot) for student, mapping_row, snapshot in rows if not self._snapshot_has_learning_payload(snapshot)]
        if not rows:
            summary = self._learning_summary_for_class_course(class_id, course_id)
            return {'ok': True, 'updated': 0, 'message': 'Không có sinh viên cần cập nhật học tập CMS', **summary}
        client = OpenEdXConnectorClient()
        batch_size = max(1, min(getattr(settings, 'openedx_connector_max_batch_size', settings.openedx_student_insight_max_batch_size), 100))
        updated = 0
        connector_enrolled_seen = 0
        connector_progress_seen = 0
        connector_grade_seen = 0
        connector_component_seen = 0
        connector_missing_result = 0
        connector_plugin_learning_counts: dict[str, int] = {}
        connector_plugin_diagnostics: dict[str, Any] = {}
        for start in range(0, len(rows), batch_size):
            chunk = rows[start:start + batch_size]
            payload = []
            for student, mapping_row, _snapshot in chunk:
                payload.append(self._student_cms_payload(
                    student,
                    create_missing=False,
                    openedx_user_id=mapping_row.openedx_user_id if mapping_row else None,
                ))
            analytics_payload = client.class_analytics_payload(course_id=course_id, cohort_name=cohort_name, students=payload)
            self._validate_connector_learning_contract(analytics_payload, course_id=course_id)
            results = analytics_payload.get('results') or []
            batch_learning_counts = analytics_payload.get('learning_counts') if isinstance(analytics_payload.get('learning_counts'), dict) else {}
            batch_diagnostics = analytics_payload.get('diagnostics') if isinstance(analytics_payload.get('diagnostics'), dict) else {}
            batch_diagnostics = {
                **batch_diagnostics,
                'connector_version': analytics_payload.get('connector_version'),
                'connector_contract_version': analytics_payload.get('connector_contract_version'),
                'progress_contract': analytics_payload.get('progress_contract') if isinstance(analytics_payload.get('progress_contract'), dict) else {},
            }
            for key, value in batch_learning_counts.items():
                if isinstance(value, (int, float)):
                    connector_plugin_learning_counts[key] = int(connector_plugin_learning_counts.get(key, 0) or 0) + int(value or 0)
            if batch_diagnostics:
                connector_plugin_diagnostics = {**connector_plugin_diagnostics, **_json_safe_value(batch_diagnostics)}
            by_username = {normalize_username(item.get('username') or item.get('openedx_username') or item.get('ap_username')): item for item in results if normalize_username(item.get('username') or item.get('openedx_username') or item.get('ap_username'))}
            by_code = {str(item.get('student_code') or item.get('roll_number') or '').strip().lower(): item for item in results if str(item.get('student_code') or item.get('roll_number') or '').strip()}
            for student, mapping_row, _snapshot in chunk:
                key = self._student_cms_username(student)
                lookup_key = normalize_username(key)
                result = by_username.get(lookup_key) or by_username.get(normalize_username(mapping_row.openedx_username if mapping_row else ''))
                if result is None and student.student_code:
                    result = by_code.get(str(student.student_code).strip().lower())
                if result is None:
                    connector_missing_result += 1
                    result = {
                        'student_code': student.student_code,
                        'roll_number': student.student_code,
                        'ap_username': normalize_username(student.username),
                        'username': key,
                        'openedx_username': key,
                        'enrollment_status': 'unknown',
                        'note': 'Plugin không trả dữ liệu học tập cho sinh viên này',
                    }
                enrollment_payload = result.get('enrollment') if isinstance(result.get('enrollment'), dict) else {}
                enrollment_status_raw = str(result.get('enrollment_status') or enrollment_payload.get('status') or '').strip().lower()
                if enrollment_status_raw in {'enrolled', 'already_enrolled', 'created', 'reactivated'} or _boolish(result.get('is_enrolled')) or enrollment_payload.get('is_enrolled') is True:
                    connector_enrolled_seen += 1
                progress_payload = result.get('progress') if isinstance(result.get('progress'), dict) else {}
                grade_payload = result.get('grade') if isinstance(result.get('grade'), dict) else {}
                if result.get('progress_percent') is not None or progress_payload.get('percent') is not None or result.get('completed_blocks') is not None or progress_payload.get('completed_blocks') is not None:
                    connector_progress_seen += 1
                if result.get('grade_percent') is not None or grade_payload.get('percent') is not None:
                    connector_grade_seen += 1
                if self._component_scores_from_payload(result):
                    connector_component_seen += 1
                self._upsert_learning_snapshot(class_id=class_id, student=student, course_id=course_id, result=result, source='openedx_connector')
                updated += 1
            self.db.flush()
        self.db.commit()
        if updated > 0 and connector_enrolled_seen <= 0:
            raise RuntimeError('Cập nhật tiến độ/điểm không có sinh viên nào được connector xác nhận enrolled trên Open edX. Hãy chạy lại Enrollment Course CMS và kiểm tra CourseEnrollment trước khi lấy điểm.')
        summary = self._learning_summary_for_class_course(class_id, course_id)
        teacher_report_cache_invalidated = self._invalidate_teacher_report_cache_for_class(class_id, reason='learning_sync')
        if teacher_report_cache_invalidated:
            self.db.commit()
        connector_counts = {
            'checked': int(updated),
            'enrolled_seen': int(connector_enrolled_seen),
            'with_progress': int(connector_progress_seen),
            'with_total_grade': int(connector_grade_seen),
            'with_component_grades': int(connector_component_seen),
            'missing_result': int(connector_missing_result),
            'read_only_no_enroll': 1,
            'plugin_connector_version_ok': 1 if self._version_at_least(connector_plugin_diagnostics.get('connector_version'), self.CONNECTOR_MIN_RUNTIME_VERSION) else 0,
            'plugin_student_module_available': 1 if connector_plugin_diagnostics.get('student_module_model_available') is True else 0,
        }
        if connector_plugin_learning_counts:
            connector_counts['plugin_enrolled'] = int(connector_plugin_learning_counts.get('enrolled') or 0)
            connector_counts['plugin_with_progress'] = int(connector_plugin_learning_counts.get('with_progress') or 0)
            connector_counts['plugin_with_progress_percent'] = int(connector_plugin_learning_counts.get('with_progress_percent') or 0)
            connector_counts['plugin_with_student_module_blocks'] = int(connector_plugin_learning_counts.get('with_student_module_blocks') or 0)
            connector_counts['plugin_with_total_grade'] = int(connector_plugin_learning_counts.get('with_total_grade') or 0)
            connector_counts['plugin_with_component_grades'] = int(connector_plugin_learning_counts.get('with_component_grades') or 0)
        if connector_grade_seen or connector_component_seen or connector_progress_seen:
            message = f'Đã cập nhật tiến độ/điểm CMS cho lớp: enrolled {connector_enrolled_seen}/{updated}, progress {connector_progress_seen}, điểm tổng {connector_grade_seen}, điểm thành phần {connector_component_seen}.'
        else:
            message = f'Đã kiểm tra học tập CMS: {connector_enrolled_seen}/{updated} sinh viên đã enrolled nhưng Open edX chưa có progress/grade/subsection grade để hiển thị.'
        return {
            'ok': True,
            'updated': updated,
            'connector_counts': connector_counts,
            'connector_diagnostics': connector_plugin_diagnostics,
            'cache_invalidated': {'teacher_report_rows': teacher_report_cache_invalidated, 'reason': 'learning_sync'},
            'message': message,
            **summary,
        }

def _try_auto_map_course_for_class(self, user: UserContext, cls: AcademicClass) -> dict[str, Any]:
        """Best-effort safe course mapping for full Student Progress sync.

        It only creates a subject-term mapping when CMS/Open edX API returns one safe candidate for the subject + term. It never creates a fake Course CMS and never creates accounts before mapping exists.
        """
        current = self.effective_course_mapping_for_class(cls)
        if current and current.openedx_course_id:
            return {
                'ok': True,
                'status': 'already_mapped',
                'openedx_course_id': current.openedx_course_id,
                'mapping_source': 'class_override' if isinstance(current, AcademicClassCourseMapping) else 'subject_term_mapping',
                'mapping': self._class_course_mapping_item(current) if isinstance(current, AcademicClassCourseMapping) else self._course_mapping_item(current),
                'message': 'Lớp đã có Course CMS mapping.',
            }
        if not getattr(settings, 'academic_auto_map_course_before_cms_sync', True):
            return {'ok': False, 'status': 'mapping_required', 'openedx_course_id': None, 'mapping': None, 'message': 'Lớp chưa có Course CMS mapping.'}
        subject = self.db.get(AcademicSubject, cls.subject_id)
        if not subject:
            return {'ok': False, 'status': 'subject_missing', 'openedx_course_id': None, 'mapping': None, 'message': 'Không tìm thấy môn AP để auto-map Course CMS.'}
        branch_value = (cls.branch or subject.branch or '').strip().lower() or None
        suggested = self.suggested_course_id_for_scope(cls.term_id, cls.subject_id)
        lookup = self._find_openedx_course_candidate_for_scope(term=self.db.get(AcademicTerm, cls.term_id), subject=subject, suggested=suggested, allow_external=True)
        candidate = lookup.get('candidate')
        count = int(lookup.get('count') or 0)
        title = lookup.get('title')
        source = str(lookup.get('source') or 'cms_openedx_api')
        if count != 1 or not candidate:
            status_value = 'course_not_found' if count == 0 else 'multiple_course_candidates'
            return {
                'ok': False,
                'status': status_value,
                'openedx_course_id': None,
                'suggested_openedx_course_id': suggested,
                'candidate_count': count,
                'candidate_source': source,
                'candidates': lookup.get('candidates') or [],
                'mapping': None,
                'message': 'Chưa tìm thấy đúng một Course CMS khớp mã môn/kỳ qua API CMS/Open edX. Chưa tạo tài khoản CMS; hãy kiểm tra kết nối API CMS/Open edX hoặc map Course CMS thủ công trước khi chạy tạo user/enroll/lấy điểm.',
            }
        mapping = self._auto_create_subject_course_mapping_if_safe(
            user,
            term_id=cls.term_id,
            subject_id=cls.subject_id,
            branch_value=branch_value,
            candidate=candidate,
            suggested=suggested,
            openedx_course_title=title,
            candidate_source=source,
            commit=True,
        )
        if not mapping:
            return {'ok': False, 'status': 'mapping_validation_failed', 'openedx_course_id': None, 'suggested_openedx_course_id': suggested, 'mapping': None, 'message': 'Course CMS khớp mã nhưng không đạt điều kiện mapping an toàn.'}
        return {
            'ok': True,
            'status': 'auto_mapped',
            'openedx_course_id': mapping.openedx_course_id,
            'suggested_openedx_course_id': suggested,
            'mapping': self._course_mapping_item(mapping),
            'message': 'Đã tự động map môn/kỳ với Course CMS khớp chính xác.',
        }

def sync_class_full_cms_flow(
        self,
        user: UserContext,
        class_id: str,
        *,
        force: bool = False,
        limit: int = 1000,
        mode: str | None = None,
        auto_map_course: bool = True,
        sync_learning: bool = True,
    ) -> dict[str, Any]:
        """Run the production Student Progress flow for a class.

        Order is intentionally strict and map-first:
          1. Resolve or safely auto-map Course CMS.
          2. If Course CMS is still missing, stop without creating CMS accounts.
          3. Resolve/create CMS accounts from RollNumber only after mapping exists.
          4. Enroll learners and add teachers as Course Staff.
          5. Pull progress, total grade and component/quiz grades.
        """
        self.assert_can_access_class(user, class_id)
        cls = self.db.get(AcademicClass, class_id)
        if not cls:
            raise HTTPException(status_code=404, detail='Không tìm thấy lớp')
        limit = max(1, min(500, int(limit or 500)))
        counts: dict[str, int] = {}

        mapping_result = self._try_auto_map_course_for_class(user, cls) if auto_map_course else {'ok': False, 'status': 'mapping_required', 'openedx_course_id': None, 'mapping': None, 'message': 'Auto-map Course CMS bị tắt cho lần chạy này.'}
        mapping = self.effective_course_mapping_for_class(cls)
        course_id = mapping.openedx_course_id if mapping else None
        if not course_id:
            return {
                'ok': True,
                'class_id': class_id,
                'openedx_course_id': None,
                'status': 'mapping_required_no_cms_user_created',
                'message': 'Lớp chưa map Course CMS nên hệ thống chưa tạo tài khoản CMS, chưa enroll và chưa lấy điểm. Hãy map Course CMS trước rồi chạy lại Đồng bộ full CMS.',
                'mapping': mapping_result,
                'cms_users': None,
                'enrollment': None,
                'learning': None,
                'counts': counts,
                'learning_summary': self._learning_summary_for_class_course(class_id, None),
            }

        cms_result = self.resolve_class_openedx_users(
            user,
            class_id,
            force=True if force else False,
            limit=limit,
            auto_enroll=False,
            create_missing=True,
        )
        for key, value in (cms_result.get('counts') or {}).items():
            counts[f'cms_{key}'] = int(value or 0)
        teacher_counts = ((cms_result.get('teachers') or {}).get('counts') or {}) if isinstance(cms_result.get('teachers'), dict) else {}
        for key, value in teacher_counts.items():
            counts[f'teacher_cms_{key}'] = int(value or 0)

        enrollment_result = self.sync_class_course_enrollment(user, class_id, force=force, limit=limit, mode=mode)
        for key, value in (enrollment_result.get('counts') or {}).items():
            counts[f'enrollment_{key}'] = int(value or 0)
        enroll_teacher_counts = ((enrollment_result.get('teachers') or {}).get('counts') or {}) if isinstance(enrollment_result.get('teachers'), dict) else {}
        for key, value in enroll_teacher_counts.items():
            counts[f'teacher_enrollment_{key}'] = int(value or 0)

        learning_result = None
        if sync_learning and getattr(settings, 'academic_full_sync_learning_after_enrollment', True):
            learning_result = self.sync_class_learning_insight(user, class_id, force=force, limit=limit)
            for key, value in (learning_result.get('counts') or {}).items():
                counts[f'learning_{key}'] = int(value or 0)

        summary = self._learning_summary_for_class_course(class_id, course_id)
        teacher_report_cache_invalidated = self._invalidate_teacher_report_cache_for_class(class_id, reason='full_cms_sync')
        if teacher_report_cache_invalidated:
            self.db.commit()
        message = 'Full CMS sync hoàn tất: đã tạo/kiểm tra user CMS, enroll Course CMS và cập nhật tiến độ/điểm.' if learning_result else 'Full CMS sync hoàn tất: đã tạo/kiểm tra user CMS và enroll Course CMS.'
        return {
            'ok': True,
            'class_id': class_id,
            'openedx_course_id': course_id,
            'status': 'completed',
            'message': message,
            'mapping': mapping_result,
            'cms_users': cms_result,
            'enrollment': enrollment_result,
            'learning': learning_result,
            'counts': counts,
            'learning_summary': summary,
            'cache_invalidated': {'teacher_report_rows': teacher_report_cache_invalidated, 'reason': 'full_cms_sync'},
        }


# Bind extracted workflow functions back to the service class.
# The functions are kept module-level to minimize diff noise from the original
# AcademicService extraction while preserving normal bound-method semantics.
AcademicSyncEnrollmentWorkflowService._student_rollnumber = _student_rollnumber
AcademicSyncEnrollmentWorkflowService._student_cms_username = _student_cms_username
AcademicSyncEnrollmentWorkflowService._student_cms_email = _student_cms_email
AcademicSyncEnrollmentWorkflowService._student_cms_payload = _student_cms_payload
AcademicSyncEnrollmentWorkflowService._upsert_teacher_cms_metadata = _upsert_teacher_cms_metadata
AcademicSyncEnrollmentWorkflowService.resolve_class_openedx_users = resolve_class_openedx_users
AcademicSyncEnrollmentWorkflowService._upsert_enrollment_snapshot = _upsert_enrollment_snapshot
AcademicSyncEnrollmentWorkflowService.sync_class_course_enrollment = sync_class_course_enrollment
AcademicSyncEnrollmentWorkflowService.sync_class_learning_insight = sync_class_learning_insight
AcademicSyncEnrollmentWorkflowService._try_auto_map_course_for_class = _try_auto_map_course_for_class
AcademicSyncEnrollmentWorkflowService.sync_class_full_cms_flow = sync_class_full_cms_flow
