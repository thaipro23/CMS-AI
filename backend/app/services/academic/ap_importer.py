from __future__ import annotations

from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.academic import (
    AcademicClass,
    AcademicClassStudent,
    AcademicStudent,
    AcademicSubject,
    AcademicTeacher,
    AcademicTeacherAssignment,
    AcademicTerm,
)
from app.services.ap_academic_sync import (
    AcademicImportService as _BaseAcademicImportService,
    SyncCounters,
    _clean,
    _lower,
    _now,
    _text_key,
)


_SUCCESS_STATUS_VALUES = {None, True, 1, '1', 'success', 'SUCCESS', 'ok', 'OK'}
_SUCCESS_CODE_VALUES = {None, 200, '200'}


class AcademicImportService(_BaseAcademicImportService):
    """Compatibility/reconciliation layer for AP ``/get-data-cms`` payloads.

    AP currently has two valid response envelopes in production history::

        {"status": "success", "data": {...}}
        {"status": 1, "code": 200, "message": "success", "data": {...}}

    The HTTP client already unwraps ``data`` before the normal API sync path, but
    the manual ``/sync/from-json`` path can receive the raw envelope.  Normalizing
    here keeps both paths equivalent and prevents a raw successful response from
    silently importing zero rows.

    The base importer is intentionally upsert-oriented.  After each successful
    import we also reconcile AP-owned teacher/student links for the classes that
    AP explicitly returned so a teacher change or roster shrink does not leave
    stale associations behind.  Manual/non-AP links are never deleted.
    """

    def __init__(self, db: Session):
        super().__init__(db)

    @staticmethod
    def _normalize_payload(payload: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise ValueError('AP payload phải là object JSON.')

        data = payload.get('data')
        is_envelope = isinstance(data, dict) and any(key in data for key in ('term', 'class', 'classes'))
        if is_envelope:
            status_value = payload.get('status')
            code_value = payload.get('code')
            if status_value not in _SUCCESS_STATUS_VALUES or code_value not in _SUCCESS_CODE_VALUES:
                message = _clean(payload.get('message') or payload.get('error') or status_value or code_value)
                raise ValueError(f'AP get-data-cms trả trạng thái lỗi: {message or "unknown"}')
            root = dict(data)
        else:
            root = dict(payload)

        # Keep a small forward-compatible alias without changing the canonical AP
        # contract. The current API still uses singular ``class``.
        if 'class' not in root and isinstance(root.get('classes'), list):
            root['class'] = root['classes']
        return root

    @staticmethod
    def _raw_students(raw_class: dict[str, Any]) -> tuple[bool, list[Any] | None]:
        if 'student' in raw_class:
            value = raw_class.get('student')
            return True, value if isinstance(value, list) else None
        if 'students' in raw_class:
            value = raw_class.get('students')
            return True, value if isinstance(value, list) else None
        return False, None

    def _existing_class_for_ap_row(
        self,
        raw_class: dict[str, Any],
        *,
        campus: str | None,
        branch: str,
    ) -> AcademicClass | None:
        ap_class_id = _clean(raw_class.get('id') or raw_class.get('class_id'))
        if not ap_class_id:
            # Destructive reconciliation requires a stable AP identity. The normal
            # importer still supports natural-key rows, but we deliberately do not
            # delete associations from an ambiguous row that has no AP class id.
            return None
        return (
            self.db.query(AcademicClass)
            .filter(
                AcademicClass.ap_class_id == ap_class_id,
                AcademicClass.campus == (_lower(campus) or None),
                AcademicClass.branch == (_lower(branch) or 'poly'),
            )
            .order_by(AcademicClass.active.desc(), AcademicClass.updated_at.desc().nullslast())
            .first()
        )

    def _delete_ap_class_links(self, cls: AcademicClass) -> None:
        for assignment in (
            self.db.query(AcademicTeacherAssignment)
            .filter(
                AcademicTeacherAssignment.class_id == cls.id,
                AcademicTeacherAssignment.source == 'ap',
            )
            .all()
        ):
            self.db.delete(assignment)
        for link in (
            self.db.query(AcademicClassStudent)
            .filter(
                AcademicClassStudent.class_id == cls.id,
                AcademicClassStudent.source == 'ap',
            )
            .all()
        ):
            self.db.delete(link)

    def _mark_ap_class_inactive(self, cls: AcademicClass, *, reason: str) -> None:
        if cls.active:
            cls.active = False
        meta = dict(cls.metadata_json or {})
        meta.update({
            'source': meta.get('source') or 'ap',
            'last_sync_source': 'ap',
            'inactive_reason': reason,
            'inactive_at': _now().isoformat(),
        })
        cls.metadata_json = meta
        cls.updated_at = _now()
        self.db.add(cls)

    def _reconcile_returned_class(
        self,
        raw_class: dict[str, Any],
        *,
        campus: str | None,
        branch: str,
    ) -> None:
        cls = self._existing_class_for_ap_row(raw_class, campus=campus, branch=branch)
        if not cls:
            return

        has_student_field, raw_students = self._raw_students(raw_class)

        # An explicit empty roster is authoritative. It is different from a
        # missing/malformed student field: the latter must never wipe existing
        # data because it may indicate a temporary upstream schema/problem.
        if has_student_field and raw_students == []:
            self._delete_ap_class_links(cls)
            self._mark_ap_class_inactive(cls, reason='ap_explicit_empty_roster')
            return

        if 'teacher' in raw_class:
            teacher_username = _lower(raw_class.get('teacher'))
            expected_teacher_id: str | None = None
            if teacher_username:
                teacher = (
                    self.db.query(AcademicTeacher)
                    .filter(func.lower(AcademicTeacher.username) == teacher_username)
                    .first()
                )
                if teacher:
                    expected_teacher_id = teacher.id
            # Empty teacher is an explicit "no AP teacher" signal. If a non-empty
            # teacher could not be resolved, do not delete anything.
            if not teacher_username or expected_teacher_id:
                for assignment in (
                    self.db.query(AcademicTeacherAssignment)
                    .filter(
                        AcademicTeacherAssignment.class_id == cls.id,
                        AcademicTeacherAssignment.source == 'ap',
                    )
                    .all()
                ):
                    if expected_teacher_id is None or assignment.teacher_id != expected_teacher_id:
                        self.db.delete(assignment)

        if not has_student_field or raw_students is None:
            return
        if not raw_students:
            return

        valid_usernames = {
            _lower(item.get('username') or item.get('user_name') or item.get('login'))
            for item in raw_students
            if isinstance(item, dict) and _lower(item.get('username') or item.get('user_name') or item.get('login'))
        }
        if not valid_usernames:
            # Non-empty but unusable rows are malformed, not an authoritative empty
            # roster. Preserve current links and let the base importer diagnostics
            # expose the bad rows instead of deleting production data.
            return

        students = (
            self.db.query(AcademicStudent)
            .filter(func.lower(AcademicStudent.username).in_(sorted(valid_usernames)))
            .all()
        )
        expected_student_ids = {student.id for student in students}
        if len(expected_student_ids) != len(valid_usernames):
            # At least one valid-looking AP student failed to persist/resolve. Avoid
            # destructive roster reconciliation in a partial-import situation.
            return

        for link in (
            self.db.query(AcademicClassStudent)
            .filter(
                AcademicClassStudent.class_id == cls.id,
                AcademicClassStudent.source == 'ap',
            )
            .all()
        ):
            if link.student_id not in expected_student_ids:
                self.db.delete(link)

    def _resolve_term(self, root: dict[str, Any], *, branch: str) -> AcademicTerm | None:
        term_payload = root.get('term') if isinstance(root.get('term'), dict) else {}
        ap_term_id = _clean(term_payload.get('id') or term_payload.get('term_id') or term_payload.get('pterm_id'))
        normalized_branch = _lower(branch) or 'poly'
        if ap_term_id:
            term = self.db.query(AcademicTerm).filter(
                AcademicTerm.ap_term_id == ap_term_id,
                AcademicTerm.branch == normalized_branch,
            ).first()
            if term:
                return term
        term_name = _clean(term_payload.get('term_name') or term_payload.get('pterm_name') or term_payload.get('name'))
        if not term_name:
            return None
        for term in self.db.query(AcademicTerm).filter(AcademicTerm.branch == normalized_branch).all():
            if _text_key(term.term_name) == _text_key(term_name) or _text_key(term.term_code) == _text_key(term_name):
                return term
        return None

    def _reconcile_omitted_classes(
        self,
        root: dict[str, Any],
        *,
        campus: str | None,
        branch: str,
    ) -> None:
        """Deactivate AP classes omitted from a non-empty subject-scoped response.

        /get-data-cms is requested once per campus+term+subject. When at least one
        class is returned, the subject can be proven from the payload and omission
        is authoritative for that scope. If AP returns zero classes, the response
        itself carries no subject_code, so this method intentionally does nothing
        rather than guessing the caller's subject and deactivating the wrong rows.
        """
        raw_classes = root.get('class') if isinstance(root.get('class'), list) else []
        object_rows = [item for item in raw_classes if isinstance(item, dict)]
        if not object_rows:
            return

        subject_codes = {
            _clean(item.get('psubject_code') or item.get('subject_code')).upper()
            for item in object_rows
            if _clean(item.get('psubject_code') or item.get('subject_code'))
        }
        if len(subject_codes) != 1:
            return
        subject_code = next(iter(subject_codes))
        normalized_branch = _lower(branch) or 'poly'
        subject = self.db.query(AcademicSubject).filter(
            AcademicSubject.subject_code == subject_code,
            AcademicSubject.branch == normalized_branch,
        ).first()
        term = self._resolve_term(root, branch=normalized_branch)
        if not subject or not term:
            return

        incoming_ap_ids = {
            _clean(item.get('id') or item.get('class_id'))
            for item in object_rows
            if _clean(item.get('id') or item.get('class_id'))
        }
        if not incoming_ap_ids:
            return

        existing = self.db.query(AcademicClass).filter(
            AcademicClass.term_id == term.id,
            AcademicClass.subject_id == subject.id,
            AcademicClass.campus == (_lower(campus) or None),
            AcademicClass.branch == normalized_branch,
            AcademicClass.active.is_(True),
        ).all()
        for cls in existing:
            meta = cls.metadata_json if isinstance(cls.metadata_json, dict) else {}
            is_ap_owned = bool(cls.ap_class_id) or meta.get('source') == 'ap'
            if not is_ap_owned or not cls.ap_class_id:
                continue
            if str(cls.ap_class_id) in incoming_ap_ids:
                continue
            self._delete_ap_class_links(cls)
            self._mark_ap_class_inactive(cls, reason='ap_omitted_from_subject_response')

    def import_payload(
        self,
        payload: dict[str, Any],
        *,
        run=None,
        campus: str | None = None,
        branch: str = 'poly',
    ) -> SyncCounters:
        root = self._normalize_payload(payload)
        counters = super().import_payload(root, run=run, campus=campus, branch=branch)

        raw_classes = root.get('class') if isinstance(root.get('class'), list) else []
        for raw_class in raw_classes:
            if isinstance(raw_class, dict):
                self._reconcile_returned_class(raw_class, campus=campus, branch=branch)
        self._reconcile_omitted_classes(root, campus=campus, branch=branch)

        # The base importer commits its upserts. Reconciliation is intentionally a
        # second transaction: if AP data was malformed, conservative guards above
        # avoid destructive changes; if reconciliation itself fails, the workflow
        # reports the error rather than silently leaving stale relationships.
        self.db.commit()
        return counters
