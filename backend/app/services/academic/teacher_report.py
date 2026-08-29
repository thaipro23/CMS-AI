from __future__ import annotations

import math
from datetime import datetime
from typing import Any

from fastapi import HTTPException
from sqlalchemy import and_, func, or_

from app.core.rbac import UserContext

from app.models.academic import (
    AcademicBlock,
    AcademicClass,
    AcademicClassCourseMapping,
    AcademicClassStudent,
    AcademicStudent,
    AcademicStudentLearningSnapshot,
    AcademicSubject,
    AcademicSubjectDelivery,
    AcademicTeacher,
    AcademicTeacherAssignment,
    AcademicTeacherReportSummary,
    AcademicTerm,
    OpenEdXUserMapping,
    UdemyStudentProgress,
)
from app.services.academic.helpers import AccessDecision, _json_safe_value as json_safe_value, _page
from app.services.training_policy_service import TrainingPolicyService
from app.services.academic.udemy_progress import UdemyProgressService


class AcademicTeacherReportWorkflowService:
    """Teacher management report/cache workflow split out of AcademicService.

    This module owns the read-heavy teacher-management report paths while
    delegating low-level academic helpers to the parent service. It preserves
    the existing response shape and cache semantics.
    """

    def __init__(self, db, parent):
        self.db = db
        self.parent = parent
        self.rbac = getattr(parent, 'rbac', None)

    def __getattr__(self, name: str):
        return getattr(self.parent, name)

    @staticmethod
    def _teacher_report_scope_key(term_id: str | None, branch: str | None, campus: str | None) -> str:
        clean_term = str(term_id or '').strip()
        clean_branch = str(branch or '').strip().lower() or '__all__'
        clean_campus = str(campus or '').strip().lower() or '__all__'
        return f"term:{clean_term}|branch:{clean_branch}|campus:{clean_campus}"

    @staticmethod
    def _teacher_report_search_match(item: dict[str, Any], search: str | None) -> bool:
        needle = str(search or '').strip().lower()
        if not needle:
            return True
        haystack_values: list[Any] = [
            item.get('teacher_username'), item.get('teacher_name'), item.get('teacher_email'),
            item.get('campus'), item.get('branch'), ','.join(item.get('subject_codes') or []),
        ]
        for cls in item.get('classes') or []:
            haystack_values.extend([cls.get('class_code'), cls.get('class_name'), cls.get('subject_code'), cls.get('subject_name'), cls.get('openedx_course_id')])
        return needle in ' '.join(str(value or '').lower() for value in haystack_values)

    def _teacher_report_item_matches_filter(self, item: dict[str, Any], status_filter: str | None) -> bool:
        status_filter = self._normalize_learning_list_filter(status_filter)
        if status_filter == 'all':
            return True
        status_counts = item.get('status_counts') or {}
        if status_filter == 'no_course_map':
            return int(item.get('classes_without_course_count') or 0) > 0
        if status_filter == 'cms_not_synced':
            return int(status_counts.get('cms_not_synced', 0) or 0) > 0 or int(item.get('cms_unsynced_count') or 0) > 0
        if status_filter == 'not_fully_enrolled':
            return int(status_counts.get('not_enrolled', 0) or 0) > 0 or int(item.get('learning_enrolled_count') or 0) < int(item.get('student_count') or 0)
        if status_filter == 'no_learning_data':
            return int(item.get('learning_synced_count') or 0) == 0 and int(item.get('student_count') or 0) > 0
        if status_filter == 'udemy_late':
            return int(item.get('udemy_progress_late_count') or 0) > 0
        if status_filter in {'no_activity', 'low_progress', 'low_grade', 'sync_error', 'deadline_late', 'exam_not_eligible', 'exam_insufficient_data'}:
            return int(status_counts.get(status_filter, 0) or 0) > 0
        if status_filter == 'has_alert':
            return bool(item.get('learning_alerts')) or int(item.get('risk_student_count') or 0) > 0
        return True


    @staticmethod
    def _normalize_report_platform(value: str | None) -> str | None:
        normalized = str(value or '').strip().lower()
        return normalized if normalized in {'cms', 'udemy'} else None

    def _project_teacher_report_platform(self, item: dict[str, Any], learning_platform: str | None) -> dict[str, Any] | None:
        platform = self._normalize_report_platform(learning_platform)
        if not platform:
            return dict(item or {})
        payload = dict(item or {})
        classes = [dict(cls) for cls in (payload.get('classes') or []) if str(cls.get('learning_platform') or 'cms').lower() == platform]
        if payload.get('classes') is not None:
            if not classes:
                return None
            payload['classes'] = classes
            payload['class_count'] = len(classes)
            payload['subject_codes'] = sorted({str(cls.get('subject_code') or '') for cls in classes if cls.get('subject_code')})
            payload['subject_count'] = len(payload['subject_codes'])
            payload['student_count'] = sum(int(cls.get('student_count') or 0) for cls in classes)
            payload['unique_student_count'] = payload['student_count']
            payload['relearn_student_count'] = sum(int(cls.get('relearn_student_count') or 0) for cls in classes)
            payload['total_relearn_count'] = sum(int(cls.get('total_relearn_count') or 0) for cls in classes)
            status_counts: dict[str, int] = {}
            alerts: list[str] = []
            for cls in classes:
                for key, value in (cls.get('status_counts') or {}).items():
                    status_counts[str(key)] = status_counts.get(str(key), 0) + int(value or 0)
                for alert in cls.get('learning_alerts') or []:
                    if alert not in alerts:
                        alerts.append(alert)
            payload['status_counts'] = status_counts
            payload['learning_alerts'] = alerts
            payload['risk_student_count'] = min(payload['student_count'], sum(int(cls.get('risk_student_count') or 0) for cls in classes))
            if platform == 'cms':
                payload['cms_class_count'] = len(classes)
                payload['udemy_class_count'] = 0
                payload['cms_student_count'] = payload['student_count']
                payload['udemy_student_count'] = 0
                payload['cms_synced_count'] = sum(int(cls.get('cms_synced_count') or 0) for cls in classes)
                payload['cms_unsynced_count'] = sum(int(cls.get('cms_unsynced_count') or 0) for cls in classes)
                payload['learning_enrolled_count'] = sum(int(cls.get('learning_enrolled_count') or 0) for cls in classes)
                payload['learning_active_count'] = sum(int(cls.get('learning_active_count') or 0) for cls in classes)
                payload['learning_synced_count'] = sum(int(cls.get('learning_synced_count') or 0) for cls in classes)
                payload['classes_without_course_count'] = sum(1 for cls in classes if not cls.get('openedx_course_id'))
                payload['udemy_progress_student_count'] = 0
                payload['udemy_progress_late_count'] = 0
                payload['udemy_progress_average_percent'] = None
                payload['udemy_progress_last_imported_at'] = None
            else:
                payload['cms_class_count'] = 0
                payload['udemy_class_count'] = len(classes)
                payload['cms_student_count'] = 0
                payload['udemy_student_count'] = payload['student_count']
                imported = sum(int(cls.get('udemy_progress_student_count') or 0) for cls in classes)
                payload['udemy_progress_student_count'] = imported
                payload['udemy_progress_late_count'] = sum(int(cls.get('udemy_progress_late_count') or 0) for cls in classes)
                weighted = sum(float(cls.get('udemy_progress_average_percent') or 0) * int(cls.get('udemy_progress_student_count') or 0) for cls in classes)
                payload['udemy_progress_average_percent'] = round(weighted / imported, 2) if imported else None
                imported_dates = [cls.get('udemy_progress_last_imported_at') for cls in classes if cls.get('udemy_progress_last_imported_at')]
                payload['udemy_progress_last_imported_at'] = max(imported_dates) if imported_dates else None
                payload['cms_synced_count'] = 0
                payload['cms_unsynced_count'] = 0
                payload['learning_enrolled_count'] = 0
                payload['learning_active_count'] = 0
                payload['learning_synced_count'] = 0
                payload['classes_without_course_count'] = 0
        else:
            count_key = 'udemy_class_count' if platform == 'udemy' else 'cms_class_count'
            if int(payload.get(count_key) or 0) <= 0:
                return None
            payload['class_count'] = int(payload.get(count_key) or 0)
            payload['student_count'] = int(payload.get('udemy_student_count' if platform == 'udemy' else 'cms_student_count') or 0)
            payload['unique_student_count'] = payload['student_count']
            if platform == 'udemy':
                payload['cms_class_count'] = 0
                payload['cms_student_count'] = 0
                payload['cms_synced_count'] = 0
                payload['cms_unsynced_count'] = 0
                payload['learning_enrolled_count'] = 0
                payload['learning_active_count'] = 0
                payload['learning_synced_count'] = 0
                payload['classes_without_course_count'] = 0
            else:
                payload['udemy_class_count'] = 0
                payload['udemy_student_count'] = 0
                payload['udemy_progress_student_count'] = 0
                payload['udemy_progress_late_count'] = 0
                payload['udemy_progress_average_percent'] = None
        payload['learning_platform'] = platform
        return payload

    @staticmethod
    def _teacher_report_item_allowed_for_decision(item: dict[str, Any], decision: AccessDecision) -> bool:
        if decision.unrestricted:
            return True
        teacher_id = str(item.get('teacher_id') or '').strip()
        if decision.teacher_ids and teacher_id in set(decision.teacher_ids):
            return True
        campuses = {str(code or '').strip().lower() for code in (decision.campus_codes or set()) if str(code or '').strip()}
        if campuses:
            item_campuses = {str(item.get('campus') or '').strip().lower()}
            for cls in item.get('classes') or []:
                item_campuses.add(str(cls.get('campus') or '').strip().lower())
            if item_campuses.intersection(campuses):
                return True
        subject_codes = {str(code or '').strip().lower() for code in (decision.subject_codes or set()) if str(code or '').strip()}
        if subject_codes:
            item_subjects = {str(code or '').strip().lower() for code in (item.get('subject_codes') or [])}
            for cls in item.get('classes') or []:
                item_subjects.add(str(cls.get('subject_code') or '').strip().lower())
            if item_subjects.intersection(subject_codes):
                return True
        return False

    @staticmethod
    def _teacher_report_public_item(item: dict[str, Any], *, include_classes: bool) -> dict[str, Any]:
        """Return a UI-safe teacher row.

        The teacher-management list page does not render per-class payloads.
        Keeping thousands of nested classes in every response made the API
        return hundreds of thousands of JSON lines for large all-campus scopes.
        Class details are returned only when the caller explicitly requests
        include_classes=true, e.g. the teacher drill-down page.
        """
        payload = dict(item or {})
        if not include_classes:
            payload.pop('classes', None)
        return payload

    def _teacher_report_summary_from_items(self, items: list[dict[str, Any]]) -> dict[str, Any]:
        total_students = sum(int(item.get('student_count') or 0) for item in items)
        udemy_progress_students = sum(int(item.get('udemy_progress_student_count') or 0) for item in items)
        udemy_weighted_progress = sum(
            float(item.get('udemy_progress_average_percent') or 0) * int(item.get('udemy_progress_student_count') or 0)
            for item in items
        )
        return {
            'teacher_count': len(items),
            'class_count': sum(int(item.get('class_count') or 0) for item in items),
            'subject_count': len({code for item in items for code in (item.get('subject_codes') or [])}),
            'student_count': total_students,
            'unique_student_count': sum(int(item.get('unique_student_count') or 0) for item in items),
            'relearn_student_count': sum(int(item.get('relearn_student_count') or 0) for item in items),
            'total_relearn_count': sum(int(item.get('total_relearn_count') or 0) for item in items),
            'cms_class_count': sum(int(item.get('cms_class_count') or 0) for item in items),
            'udemy_class_count': sum(int(item.get('udemy_class_count') or 0) for item in items),
            'cms_student_count': sum(int(item.get('cms_student_count') or 0) for item in items),
            'udemy_student_count': sum(int(item.get('udemy_student_count') or 0) for item in items),
            'cms_synced_count': min(sum(int(item.get('cms_synced_count') or 0) for item in items), sum(int(item.get('cms_student_count') or 0) for item in items)),
            'udemy_progress_student_count': udemy_progress_students,
            'udemy_progress_late_count': sum(int(item.get('udemy_progress_late_count') or 0) for item in items),
            'udemy_progress_average_percent': round(udemy_weighted_progress / udemy_progress_students, 2) if udemy_progress_students else None,
            'learning_enrolled_count': min(sum(int(item.get('learning_enrolled_count') or 0) for item in items), total_students),
            'learning_active_count': min(sum(int(item.get('learning_active_count') or 0) for item in items), total_students),
            'risk_student_count': min(sum(int(item.get('risk_student_count') or 0) for item in items), total_students),
            'classes_without_course_count': sum(int(item.get('classes_without_course_count') or 0) for item in items),
            'deadline_late_student_count': sum(int(item.get('deadline_late_student_count') or 0) for item in items),
            'deadline_late_quiz_count': sum(int(item.get('deadline_late_quiz_count') or 0) for item in items),
            'exam_eligible_student_count': sum(int(item.get('exam_eligible_student_count') or 0) for item in items),
            'exam_not_eligible_student_count': sum(int(item.get('exam_not_eligible_student_count') or 0) for item in items),
            'exam_insufficient_data_student_count': sum(int(item.get('exam_insufficient_data_student_count') or 0) for item in items),
            'quiz_failed_count': sum(int(item.get('quiz_failed_count') or 0) for item in items),
            'assignment_not_graded_count': sum(int(item.get('assignment_not_graded_count') or 0) for item in items),
        }


    def _teacher_udemy_context(self, classes: list[AcademicClass]) -> dict[str, dict[str, Any]]:
        """Resolve the learning platform and live Udemy metrics for many classes.

        The report must not treat Udemy classes as "missing Course CMS" or count
        every Udemy learner as CMS-unsynced. Metrics are recalculated against the
        current due Udemy milestone, while the progress value itself remains the
        latest imported snapshot.
        """
        valid_classes = [item for item in classes if item and item.id and item.subject_id and item.term_id]
        if not valid_classes:
            return {}
        subject_ids = {item.subject_id for item in valid_classes}
        term_ids = {item.term_id for item in valid_classes}
        deliveries = self.db.query(AcademicSubjectDelivery).filter(
            AcademicSubjectDelivery.subject_id.in_(subject_ids),
            AcademicSubjectDelivery.term_id.in_(term_ids),
            AcademicSubjectDelivery.active.is_(True),
        ).all()

        def delivery_key(subject_id: str, term_id: str, block_id: str | None, branch: str | None) -> tuple[str, str, str | None, str]:
            return (str(subject_id), str(term_id), str(block_id) if block_id is not None else None, str(branch or 'poly').strip().lower())

        delivery_by_key = {
            delivery_key(item.subject_id, item.term_id, item.block_id, item.branch): item
            for item in deliveries
        }
        result: dict[str, dict[str, Any]] = {}
        udemy_class_ids: set[str] = set()
        udemy_delivery_ids: set[str] = set()
        for cls in valid_classes:
            delivery = delivery_by_key.get(delivery_key(cls.subject_id, cls.term_id, cls.block_id, cls.branch))
            platform = str(delivery.learning_platform or '').strip().lower() if delivery else None
            result[str(cls.id)] = {
                'learning_platform': platform,
                'subject_delivery_id': delivery.id if delivery else None,
                'progress_student_count': 0,
                'late_student_count': 0,
                'progress_sum': 0.0,
                'progress_count': 0,
                'average_progress_percent': None,
                'last_imported_at': None,
                'required_progress_percent': None,
                'current_plan_week': None,
                'current_deadline_date': None,
                'late_student_ids': set(),
            }
            if delivery and platform == 'udemy':
                udemy_class_ids.add(str(cls.id))
                udemy_delivery_ids.add(str(delivery.id))
        if not udemy_class_ids:
            return result

        milestone_by_delivery: dict[str, dict[str, Any] | None] = {}
        progress_service = UdemyProgressService(self.db)
        for delivery_id in udemy_delivery_ids:
            _plan, milestone = progress_service._current_dashboard_milestone(delivery_id)
            milestone_by_delivery[delivery_id] = milestone

        snapshots = self.db.query(UdemyStudentProgress).filter(
            UdemyStudentProgress.class_id.in_(sorted(udemy_class_ids)),
            UdemyStudentProgress.subject_delivery_id.in_(sorted(udemy_delivery_ids)),
        ).all()
        for snapshot in snapshots:
            class_id = str(snapshot.class_id or '')
            context = result.get(class_id)
            if not context or context.get('learning_platform') != 'udemy':
                continue
            delivery_id = str(context.get('subject_delivery_id') or '')
            milestone = milestone_by_delivery.get(delivery_id)
            required = float(milestone['required_progress_percent']) if milestone else None
            progress = float(snapshot.progress_percent or 0)
            context['progress_student_count'] += 1
            context['progress_sum'] += progress
            context['progress_count'] += 1
            context['required_progress_percent'] = required
            context['current_plan_week'] = milestone.get('week_number') if milestone else None
            context['current_deadline_date'] = milestone.get('deadline_date') if milestone else None
            if snapshot.last_imported_at and (
                context['last_imported_at'] is None or snapshot.last_imported_at > context['last_imported_at']
            ):
                context['last_imported_at'] = snapshot.last_imported_at
            if snapshot.match_status == 'matched_roster' and required is not None and progress < required:
                context['late_student_count'] += 1
                if snapshot.student_id:
                    context['late_student_ids'].add(str(snapshot.student_id))
        for context in result.values():
            count = int(context.get('progress_count') or 0)
            if count:
                context['average_progress_percent'] = round(float(context.get('progress_sum') or 0) / count, 2)
        return result

    def _training_teacher_report_lite_fast(
        self,
        user: UserContext,
        *,
        term_id: str,
        branch: str | None,
        campus: str | None,
        search: str | None,
        learning_status: str | None,
        learning_platform: str | None,
        teacher_id: str | None,
        page: int,
        page_size: int,
        decision: AccessDecision,
    ) -> dict[str, Any] | None:
        """Fast exact-lite report for the teacher-management list.

        This path is used when the UI only needs the teacher overview rows. It
        intentionally avoids hydrating nested classes, every student policy, and
        exam-deadline evaluation for the full term. Those deep fields are still
        available from the teacher drill-down/export paths.
        """
        status_filter = self._normalize_learning_list_filter(learning_status)
        if teacher_id or status_filter in {'deadline_late', 'exam_not_eligible', 'exam_insufficient_data'}:
            return None

        query = self.db.query(
            AcademicTeacher,
            AcademicClass,
            AcademicSubject,
        ).join(
            AcademicTeacherAssignment,
            AcademicTeacherAssignment.teacher_id == AcademicTeacher.id,
        ).join(
            AcademicClass,
            AcademicClass.id == AcademicTeacherAssignment.class_id,
        ).join(
            AcademicSubject,
            AcademicSubject.id == AcademicClass.subject_id,
        ).outerjoin(
            AcademicSubjectDelivery,
            and_(
                AcademicSubjectDelivery.subject_id == AcademicClass.subject_id,
                AcademicSubjectDelivery.term_id == AcademicClass.term_id,
                AcademicSubjectDelivery.block_id == AcademicClass.block_id,
                func.lower(func.coalesce(AcademicSubjectDelivery.branch, 'poly')) == func.lower(func.coalesce(AcademicClass.branch, 'poly')),
                AcademicSubjectDelivery.active.is_(True),
            ),
        ).filter(
            AcademicTeacher.active.is_(True),
            AcademicClass.active.is_(True),
            AcademicSubject.active.is_(True),
        )
        query = self._apply_academic_access_filter(query, user, decision)
        query = query.filter(AcademicClass.term_id == term_id)
        platform = self._normalize_report_platform(learning_platform)
        if platform == 'udemy':
            query = query.filter(AcademicSubjectDelivery.learning_platform == 'udemy')
        elif platform == 'cms':
            query = query.filter(AcademicSubjectDelivery.learning_platform == 'cms')
        if branch:
            query = query.filter(AcademicClass.branch == branch.strip().lower())
        if campus:
            query = query.filter(func.lower(AcademicClass.campus) == campus.strip().lower())
        if search and search.strip():
            like = f"%{search.strip()}%"
            query = query.filter(or_(
                AcademicTeacher.username.ilike(like),
                AcademicTeacher.full_name.ilike(like),
                AcademicTeacher.email.ilike(like),
                AcademicClass.class_code.ilike(like),
                AcademicSubject.subject_code.ilike(like),
                AcademicSubject.subject_name.ilike(like),
            ))

        rows = query.order_by(
            AcademicTeacher.full_name.asc().nullslast(),
            AcademicTeacher.username.asc(),
            AcademicSubject.subject_code.asc(),
            AcademicClass.class_code.asc(),
        ).all()
        if not rows:
            return {
                'items': [],
                'summary': self._teacher_report_summary_from_items([]),
                'summary_scope': 'lite_filtered',
                'total': 0,
                'page': page,
                'page_size': page_size,
                'total_pages': 0,
                'has_next': False,
                'cache': {'status': 'lite', 'scope_key': self._teacher_report_scope_key(term_id, branch, campus), 'row_count': 0},
            }

        class_by_id: dict[str, AcademicClass] = {}
        teacher_rows: list[tuple[AcademicTeacher, AcademicClass, AcademicSubject]] = []
        for teacher, cls, subject in rows:
            class_by_id[str(cls.id)] = cls
            teacher_rows.append((teacher, cls, subject))
        class_ids = list(class_by_id.keys())
        udemy_context_by_class = self._teacher_udemy_context(list(class_by_id.values()))

        student_count_by_class = {
            str(class_id): int(count or 0)
            for class_id, count in self.db.query(
                AcademicClassStudent.class_id,
                func.count(AcademicClassStudent.id),
            ).filter(AcademicClassStudent.class_id.in_(class_ids)).group_by(AcademicClassStudent.class_id).all()
        }
        sync_by_class = self._student_sync_summary_for_classes(class_ids)

        class_overrides = self.db.query(AcademicClassCourseMapping).filter(
            AcademicClassCourseMapping.class_id.in_(class_ids),
            AcademicClassCourseMapping.active.is_(True),
        ).order_by(AcademicClassCourseMapping.updated_at.desc().nullslast()).all() if class_ids else []
        override_by_class = {item.class_id: item for item in class_overrides}
        inherited_by_class = self.inherited_course_mappings_for_classes(list(class_by_id.values()))
        course_by_class: dict[str, str | None] = {}
        for class_id, cls in class_by_id.items():
            mapping = override_by_class.get(class_id) or inherited_by_class.get(class_id)
            course_by_class[class_id] = mapping.openedx_course_id if mapping else None

        learning_by_class = self._learning_summary_by_class_ids(class_ids, course_by_class)
        status_counts_by_class, _snapshot_by_class_student, _status_by_class_student = self._training_learning_status_counts_by_class(class_ids, course_by_class)

        buckets: dict[str, dict[str, Any]] = {}
        seen_teacher_classes: set[tuple[str, str]] = set()
        for teacher, cls, subject in teacher_rows:
            key = str(teacher.id)
            bucket = buckets.setdefault(key, {
                'teacher_id': str(teacher.id),
                'teacher_code': teacher.teacher_code,
                'teacher_username': teacher.username,
                'teacher_name': teacher.full_name or teacher.username,
                'teacher_email': teacher.email,
                'campus': teacher.campus,
                'branch': teacher.branch,
                'subject_ids': set(),
                'subject_codes': set(),
                'class_ids': set(),
                'student_count': 0,
                'unique_student_count': 0,
                'cms_class_count': 0,
                'udemy_class_count': 0,
                'cms_student_count': 0,
                'udemy_student_count': 0,
                'udemy_progress_student_count': 0,
                'udemy_progress_late_count': 0,
                'udemy_progress_weighted_sum': 0.0,
                'udemy_progress_weight': 0,
                'udemy_last_imported_at': None,
                'cms_synced_count': 0,
                'cms_unsynced_count': 0,
                'learning_enrolled_count': 0,
                'learning_active_count': 0,
                'learning_synced_count': 0,
                'classes_without_course_count': 0,
                'progress_values': [],
                'grade_values': [],
                'status_counts': {},
                'last_synced_at': None,
            })
            class_id = str(cls.id)
            pair = (key, class_id)
            if pair in seen_teacher_classes:
                continue
            seen_teacher_classes.add(pair)
            bucket['class_ids'].add(class_id)
            bucket['subject_ids'].add(str(subject.id))
            if subject.subject_code:
                bucket['subject_codes'].add(str(subject.subject_code))
            total_students = int(student_count_by_class.get(class_id, 0) or 0)
            bucket['student_count'] += total_students
            bucket['unique_student_count'] += total_students
            udemy_context = udemy_context_by_class.get(class_id, {})
            is_udemy = udemy_context.get('learning_platform') == 'udemy'
            if is_udemy:
                bucket['udemy_class_count'] += 1
                bucket['udemy_student_count'] += total_students
                imported = int(udemy_context.get('progress_student_count') or 0)
                late = int(udemy_context.get('late_student_count') or 0)
                bucket['udemy_progress_student_count'] += imported
                bucket['udemy_progress_late_count'] += late
                if imported and udemy_context.get('average_progress_percent') is not None:
                    bucket['udemy_progress_weighted_sum'] += float(udemy_context.get('average_progress_percent')) * imported
                    bucket['udemy_progress_weight'] += imported
                last_imported = udemy_context.get('last_imported_at')
                if last_imported and (bucket['udemy_last_imported_at'] is None or last_imported > bucket['udemy_last_imported_at']):
                    bucket['udemy_last_imported_at'] = last_imported
                if late:
                    bucket['status_counts']['udemy_late'] = int(bucket['status_counts'].get('udemy_late', 0) or 0) + late
            else:
                bucket['cms_class_count'] += 1
                bucket['cms_student_count'] += total_students
                sync_bucket = sync_by_class.get(class_id, {})
                matched = int(sync_bucket.get('matched', 0) or 0)
                bucket['cms_synced_count'] += matched
                bucket['cms_unsynced_count'] += max(0, total_students - matched)
                learning = learning_by_class.get(class_id, {})
                bucket['learning_enrolled_count'] += int(learning.get('learning_enrolled_count') or 0)
                bucket['learning_active_count'] += int(learning.get('learning_active_count') or 0)
                bucket['learning_synced_count'] += int(learning.get('learning_synced_count') or 0)
                if learning.get('learning_avg_progress_percent') is not None:
                    bucket['progress_values'].append(float(learning.get('learning_avg_progress_percent')))
                if learning.get('learning_avg_grade_percent') is not None:
                    bucket['grade_values'].append(float(learning.get('learning_avg_grade_percent')))
                last_synced_at = learning.get('learning_last_synced_at')
                if last_synced_at and (bucket['last_synced_at'] is None or last_synced_at > bucket['last_synced_at']):
                    bucket['last_synced_at'] = last_synced_at
                if not course_by_class.get(class_id):
                    bucket['classes_without_course_count'] += 1
                for status_name, count in (status_counts_by_class.get(class_id) or {}).items():
                    bucket['status_counts'][status_name] = int(bucket['status_counts'].get(status_name, 0) or 0) + int(count or 0)

        items: list[dict[str, Any]] = []
        for bucket in buckets.values():
            status_counts = dict(bucket['status_counts'])
            student_total = int(bucket['student_count'] or 0)
            avg_progress = round(sum(bucket['progress_values']) / len(bucket['progress_values']), 2) if bucket['progress_values'] else None
            avg_grade = round(sum(bucket['grade_values']) / len(bucket['grade_values']), 2) if bucket['grade_values'] else None
            risk_student_count = self._bounded_risk_count_from_status_counts(status_counts, student_total)
            learning_alerts: list[str] = []
            if int(bucket.get('classes_without_course_count') or 0):
                learning_alerts.append(f"{int(bucket.get('classes_without_course_count') or 0)} lớp chưa ghép Course CMS")
            if int(status_counts.get('cms_not_synced', 0) or 0):
                learning_alerts.append(f"{int(status_counts.get('cms_not_synced', 0) or 0)} SV chưa đồng bộ CMS")
            if int(status_counts.get('not_enrolled', 0) or 0):
                learning_alerts.append(f"{int(status_counts.get('not_enrolled', 0) or 0)} SV chưa ghi danh CMS")
            if int(status_counts.get('no_activity', 0) or 0):
                learning_alerts.append(f"{int(status_counts.get('no_activity', 0) or 0)} SV chưa học")
            if int(status_counts.get('low_progress', 0) or 0):
                learning_alerts.append(f"{int(status_counts.get('low_progress', 0) or 0)} SV tiến độ thấp")
            if int(status_counts.get('low_grade', 0) or 0):
                learning_alerts.append(f"{int(status_counts.get('low_grade', 0) or 0)} SV điểm thấp")
            if int(bucket.get('udemy_progress_late_count') or 0):
                learning_alerts.append(f"{int(bucket.get('udemy_progress_late_count') or 0)} SV Udemy chậm tiến độ")
            udemy_avg = round(bucket['udemy_progress_weighted_sum'] / bucket['udemy_progress_weight'], 2) if bucket['udemy_progress_weight'] else None
            items.append({
                'teacher_id': bucket['teacher_id'],
                'teacher_code': bucket['teacher_code'],
                'teacher_username': bucket['teacher_username'],
                'teacher_name': bucket['teacher_name'],
                'teacher_email': bucket['teacher_email'],
                'campus': bucket['campus'],
                'branch': bucket['branch'],
                'subject_count': len(bucket['subject_ids']),
                'subject_codes': sorted(bucket['subject_codes']),
                'class_count': len(bucket['class_ids']),
                'student_count': student_total,
                'unique_student_count': int(bucket['unique_student_count'] or 0),
                'cms_class_count': int(bucket['cms_class_count'] or 0),
                'udemy_class_count': int(bucket['udemy_class_count'] or 0),
                'cms_student_count': int(bucket['cms_student_count'] or 0),
                'udemy_student_count': int(bucket['udemy_student_count'] or 0),
                'udemy_progress_student_count': int(bucket['udemy_progress_student_count'] or 0),
                'udemy_progress_late_count': int(bucket['udemy_progress_late_count'] or 0),
                'udemy_progress_average_percent': udemy_avg,
                'udemy_progress_last_imported_at': bucket['udemy_last_imported_at'],
                'relearn_student_count': 0,
                'total_relearn_count': 0,
                'cms_synced_count': int(bucket['cms_synced_count'] or 0),
                'cms_unsynced_count': int(bucket['cms_unsynced_count'] or 0),
                'learning_enrolled_count': int(bucket['learning_enrolled_count'] or 0),
                'learning_active_count': int(bucket['learning_active_count'] or 0),
                'learning_synced_count': int(bucket['learning_synced_count'] or 0),
                'classes_without_course_count': int(bucket['classes_without_course_count'] or 0),
                'deadline_late_student_count': 0,
                'deadline_late_quiz_count': 0,
                'deadline_due_quiz_count': 0,
                'exam_eligible_student_count': 0,
                'exam_not_eligible_student_count': 0,
                'exam_insufficient_data_student_count': 0,
                'quiz_failed_count': 0,
                'quiz_late_count': 0,
                'quiz_not_attempted_count': 0,
                'quiz_missing_deadline_count': 0,
                'assignment_not_graded_count': 0,
                'learning_avg_progress_percent': avg_progress,
                'learning_avg_grade_percent': avg_grade,
                'learning_avg_grade_10': self._percent_to_grade10(avg_grade),
                'risk_student_count': risk_student_count,
                'status_counts': status_counts,
                'learning_alerts': learning_alerts,
                'last_synced_at': bucket['last_synced_at'],
            })
        filtered_items = [item for item in items if self._teacher_report_item_matches_filter(item, status_filter)]
        filtered_items.sort(key=lambda item: (str(item.get('teacher_name') or ''), str(item.get('teacher_username') or '')))
        total = len(filtered_items)
        total_pages = math.ceil(total / page_size) if total else 0
        page_items = filtered_items[(page - 1) * page_size: page * page_size]
        return {
            'items': page_items,
            'summary': self._teacher_report_summary_from_items(filtered_items),
            'summary_scope': 'lite_filtered',
            'total': total,
            'page': page,
            'page_size': page_size,
            'total_pages': total_pages,
            'has_next': page < total_pages,
            'cache': {
                'status': 'lite',
                'scope_key': self._teacher_report_scope_key(term_id, branch, campus),
                'row_count': len(rows),
                'note': 'Danh sách nhanh: không hydrate lớp/sinh viên chi tiết. Mở Xem lớp để tải chi tiết giáo viên.',
            },
        }

    def _training_teacher_report_from_cache(
        self,
        *,
        term_id: str,
        branch: str | None,
        campus: str | None,
        search: str | None,
        learning_status: str | None,
        learning_platform: str | None,
        teacher_id: str | None,
        decision: AccessDecision,
        page: int,
        page_size: int,
        include_classes: bool = False,
    ) -> dict[str, Any] | None:
        scope_key = self._teacher_report_scope_key(term_id, branch, campus)
        rows = self.db.query(AcademicTeacherReportSummary).filter(AcademicTeacherReportSummary.scope_key == scope_key).all()
        if not rows:
            return None
        items: list[dict[str, Any]] = []
        for row in rows:
            payload = dict(row.report_json or {})
            if not payload:
                continue
            payload.setdefault('teacher_id', row.teacher_id)
            payload.setdefault('teacher_username', row.teacher_username)
            payload.setdefault('teacher_name', row.teacher_name)
            payload['cache_built_at'] = row.built_at
            payload = self._project_teacher_report_platform(payload, learning_platform)
            if payload is None:
                continue
            if not self._teacher_report_item_allowed_for_decision(payload, decision):
                continue
            if teacher_id and str(payload.get('teacher_id')) != str(teacher_id):
                continue
            if not self._teacher_report_search_match(payload, search):
                continue
            if not self._teacher_report_item_matches_filter(payload, learning_status):
                continue
            items.append(payload)
        items.sort(key=lambda item: (str(item.get('teacher_name') or ''), str(item.get('teacher_username') or '')))
        total = len(items)
        total_pages = math.ceil(total / page_size) if total else 0
        page_items = [self._teacher_report_public_item(item, include_classes=include_classes) for item in items[(page - 1) * page_size:page * page_size]]
        latest_built_at = max((row.built_at for row in rows if row.built_at), default=None)
        return {
            'items': page_items,
            'summary': self._teacher_report_summary_from_items(items),
            'summary_scope': 'cached_filtered',
            'total': total,
            'page': page,
            'page_size': page_size,
            'total_pages': total_pages,
            'has_next': page < total_pages,
            'cache': {
                'status': 'hit',
                'scope_key': scope_key,
                'built_at': latest_built_at,
                'row_count': len(rows),
            },
        }

    def _teacher_report_refresh_scope_classes(
        self,
        user: UserContext,
        *,
        term_id: str,
        branch: str | None,
        campus: str | None,
        class_id: str | None = None,
    ) -> list[AcademicClass]:
        decision = self.access_decision(user)
        query = self.db.query(AcademicClass, AcademicSubject).join(
            AcademicSubject, AcademicSubject.id == AcademicClass.subject_id,
        ).filter(
            AcademicClass.active.is_(True),
            AcademicSubject.active.is_(True),
            AcademicClass.term_id == term_id,
        )
        query = self._apply_academic_access_filter(query, user, decision)
        if class_id:
            query = query.filter(AcademicClass.id == str(class_id))
        if branch:
            query = query.filter(func.lower(AcademicClass.branch) == str(branch).strip().lower())
        if campus:
            query = query.filter(func.lower(AcademicClass.campus) == str(campus).strip().lower())
        rows = query.order_by(AcademicClass.campus.asc().nullslast(), AcademicClass.class_code.asc()).all()
        classes_by_id = {str(cls.id): cls for cls, _subject in rows}
        return list(classes_by_id.values())

    def _teacher_report_refresh_targets(
        self,
        classes: list[AcademicClass],
    ) -> tuple[list[AcademicClass], list[tuple[AcademicClass, str]], int]:
        udemy_context = self._teacher_udemy_context(classes)
        cms_classes = [
            cls for cls in classes
            if str((udemy_context.get(str(cls.id)) or {}).get('learning_platform') or 'cms').lower() != 'udemy'
        ]
        mapped: list[tuple[AcademicClass, str]] = []
        skipped_unmapped = 0
        for cls in cms_classes:
            mapping = self.effective_course_mapping_for_class(cls)
            course_id = str(getattr(mapping, 'openedx_course_id', '') or '').strip() if mapping else ''
            if course_id:
                mapped.append((cls, course_id))
            else:
                skipped_unmapped += 1
        return cms_classes, mapped, skipped_unmapped

    def _assert_teacher_report_class_refresh_is_current(
        self,
        *,
        cls: AcademicClass,
        course_id: str,
        result: dict[str, Any],
    ) -> None:
        roster_total = int(result.get('total') or 0)
        updated_total = int(result.get('updated') or 0)
        if roster_total and updated_total < roster_total:
            raise RuntimeError(
                f'Chỉ cập nhật được {updated_total}/{roster_total} sinh viên; không dùng snapshot cũ để xuất báo cáo.'
            )
        snapshots = self.db.query(AcademicStudentLearningSnapshot).filter(
            AcademicStudentLearningSnapshot.class_id == str(cls.id),
            AcademicStudentLearningSnapshot.openedx_course_id == course_id,
        ).all()
        preserved_old_grade = sum(
            1 for snapshot in snapshots
            if isinstance(snapshot.raw_json, dict) and snapshot.raw_json.get('grade_preserved') is True
        )
        if preserved_old_grade:
            raise RuntimeError(
                f'Connector không trả điểm hiện tại cho {preserved_old_grade} sinh viên; '
                'snapshot cũ đã được giữ an toàn nhưng không được phép dùng cho báo cáo mới.'
            )

    @staticmethod
    def _teacher_report_refresh_failure(cls: AcademicClass, course_id: str, exc: Exception) -> dict[str, Any]:
        return {
            'class_id': str(cls.id),
            'class_code': cls.class_code,
            'openedx_course_id': course_id,
            'error_type': exc.__class__.__name__,
        }

    def refresh_training_teacher_learning_data(
        self,
        user: UserContext,
        *,
        term_id: str,
        branch: str | None = None,
        campus: str | None = None,
        learning_platform: str | None = 'cms',
        class_id: str | None = None,
        strict: bool = True,
        progress_callback: Any | None = None,
    ) -> dict[str, Any]:
        """Pull current CMS/Open edX grades before materializing reports.

        A cache rebuild or Excel export is not allowed to claim freshness when it
        only re-reads old AcademicStudentLearningSnapshot rows. CMS report jobs
        therefore force-refresh every mapped class in scope and fail closed if a
        current grade cannot be confirmed. Udemy remains import-driven.
        """
        platform = self._normalize_report_platform(learning_platform) or 'cms'
        if platform != 'cms':
            return {
                'ok': True,
                'learning_platform': platform,
                'class_count': 0,
                'mapped_class_count': 0,
                'refreshed_class_count': 0,
                'skipped_unmapped_class_count': 0,
                'failed_class_count': 0,
                'failures': [],
                'message': 'Nguồn Udemy dùng dữ liệu import mới nhất; không gọi CMS/Open edX.',
            }

        classes = self._teacher_report_refresh_scope_classes(
            user, term_id=term_id, branch=branch, campus=campus, class_id=class_id,
        )
        cms_classes, mapped, skipped_unmapped = self._teacher_report_refresh_targets(classes)
        refreshed = 0
        failures: list[dict[str, Any]] = []
        total = len(mapped)

        for index, (cls, course_id) in enumerate(mapped, start=1):
            if callable(progress_callback):
                progress_callback(index - 1, total, f'Đang lấy điểm CMS mới nhất: {cls.class_code or cls.id}')
            try:
                refresh_result = self.sync_class_learning_insight(
                    user, str(cls.id), force=True, limit=20000,
                )
                self._assert_teacher_report_class_refresh_is_current(
                    cls=cls, course_id=course_id, result=refresh_result,
                )
                refreshed += 1
            except Exception as exc:
                failures.append(self._teacher_report_refresh_failure(cls, course_id, exc))
            if callable(progress_callback):
                label = 'Đã cập nhật điểm' if not failures or failures[-1].get('class_id') != str(cls.id) else 'Lỗi cập nhật điểm'
                progress_callback(index, total, f'{label}: {cls.class_code or cls.id}')

        if class_id and strict and skipped_unmapped:
            raise RuntimeError('Lớp chưa ghép Course CMS; không thể xác nhận điểm mới nhất để xuất Excel.')

        result = {
            'ok': not failures and (not class_id or skipped_unmapped == 0),
            'learning_platform': 'cms',
            'class_count': len(cms_classes),
            'mapped_class_count': total,
            'refreshed_class_count': refreshed,
            'skipped_unmapped_class_count': skipped_unmapped,
            'failed_class_count': len(failures),
            'failures': failures[:50],
        }
        if failures and strict:
            failed_labels = ', '.join(str(item.get('class_code') or item.get('class_id')) for item in failures[:8])
            suffix = '…' if len(failures) > 8 else ''
            raise RuntimeError(
                f'Không thể xác nhận điểm CMS mới nhất cho {len(failures)} lớp ({failed_labels}{suffix}). '
                'Dừng báo cáo để không xuất dữ liệu điểm cũ.'
            )
        return result

    def rebuild_training_teacher_report_cache(
        self,
        user: UserContext,
        *,
        term_id: str,
        branch: str | None = None,
        campus: str | None = None,
        source_sync_run_id: str | None = None,
    ) -> dict[str, Any]:
        if not term_id:
            raise HTTPException(status_code=422, detail='Thiếu học kỳ để tính lại báo cáo giáo viên')
        scope_key = self._teacher_report_scope_key(term_id, branch, campus)
        report = self.training_teacher_report(
            user,
            term_id=term_id,
            branch=branch,
            campus=campus,
            learning_status='all',
            page=1,
            page_size=200,
            include_all=True,
            include_students=False,
            include_classes=True,
            use_cache=False,
        )
        now = datetime.utcnow()
        seen_teacher_ids: set[str] = set()
        for item in report.get('items') or []:
            teacher_id = str(item.get('teacher_id') or '').strip()
            if not teacher_id:
                continue
            seen_teacher_ids.add(teacher_id)
            row = self.db.query(AcademicTeacherReportSummary).filter(
                AcademicTeacherReportSummary.scope_key == scope_key,
                AcademicTeacherReportSummary.teacher_id == teacher_id,
            ).first()
            if not row:
                row = AcademicTeacherReportSummary(scope_key=scope_key, term_id=term_id, teacher_id=teacher_id)
                self.db.add(row)
            row.term_id = term_id
            row.branch = str(branch or '').strip().lower() or None
            row.campus = str(campus or '').strip().lower() or None
            row.teacher_username = str(item.get('teacher_username') or '')
            row.teacher_name = str(item.get('teacher_name') or item.get('teacher_username') or '')
            row.teacher_email = item.get('teacher_email')
            row.class_count = int(item.get('class_count') or 0)
            row.student_count = int(item.get('student_count') or 0)
            row.unique_student_count = int(item.get('unique_student_count') or 0)
            row.risk_student_count = int(item.get('risk_student_count') or 0)
            row.cms_synced_count = int(item.get('cms_synced_count') or 0)
            row.learning_enrolled_count = int(item.get('learning_enrolled_count') or 0)
            row.learning_avg_progress_percent = item.get('learning_avg_progress_percent')
            row.learning_avg_grade_10 = item.get('learning_avg_grade_10')
            row.report_json = json_safe_value(item)
            row.summary_json = json_safe_value(report.get('summary') or {})
            row.source_sync_run_id = source_sync_run_id
            row.built_by = user.user_id
            row.built_at = now
            row.updated_at = now
        if seen_teacher_ids:
            self.db.query(AcademicTeacherReportSummary).filter(
                AcademicTeacherReportSummary.scope_key == scope_key,
                ~AcademicTeacherReportSummary.teacher_id.in_(seen_teacher_ids),
            ).delete(synchronize_session=False)
        else:
            self.db.query(AcademicTeacherReportSummary).filter(AcademicTeacherReportSummary.scope_key == scope_key).delete(synchronize_session=False)
        self.db.commit()
        return {
            'ok': True,
            'scope_key': scope_key,
            'built_at': now,
            'teacher_count': len(seen_teacher_ids),
            'summary': report.get('summary') or {},
        }

    def training_teacher_report(
        self,
        user: UserContext,
        *,
        term_id: str | None = None,
        branch: str | None = None,
        campus: str | None = None,
        search: str | None = None,
        learning_status: str | None = None,
        learning_platform: str | None = None,
        teacher_id: str | None = None,
        class_id: str | None = None,
        page: int = 1,
        page_size: int = 50,
        include_all: bool = False,
        include_students: bool = False,
        include_classes: bool = False,
        use_cache: bool = True,
    ) -> dict[str, Any]:
        page, page_size = _page(page, page_size)
        decision = self.access_decision(user)
        status_filter = self._normalize_learning_list_filter(learning_status)
        if not term_id:
            return {
                'items': [],
                'summary': {
                    'teacher_count': 0,
                    'class_count': 0,
                    'subject_count': 0,
                    'student_count': 0,
                    'unique_student_count': 0,
                    'relearn_student_count': 0,
                    'total_relearn_count': 0,
                    'cms_class_count': 0,
                    'udemy_class_count': 0,
                    'cms_student_count': 0,
                    'udemy_student_count': 0,
                    'cms_synced_count': 0,
                    'udemy_progress_student_count': 0,
                    'udemy_progress_late_count': 0,
                    'udemy_progress_average_percent': None,
                    'learning_enrolled_count': 0,
                    'learning_active_count': 0,
                    'risk_student_count': 0,
                    'classes_without_course_count': 0,
                    'deadline_late_student_count': 0,
                    'deadline_late_quiz_count': 0,
                    'exam_eligible_student_count': 0,
                    'exam_not_eligible_student_count': 0,
                    'exam_insufficient_data_student_count': 0,
                    'quiz_failed_count': 0,
                    'assignment_not_graded_count': 0,
                },
                'total': 0,
                'page': page,
                'page_size': page_size,
                'total_pages': 0,
                'has_next': False,
            }
        if use_cache and term_id and not class_id and not include_all and not include_students:
            cached_report = self._training_teacher_report_from_cache(
                term_id=term_id,
                branch=branch,
                campus=campus,
                search=search,
                learning_status=status_filter,
                learning_platform=learning_platform,
                teacher_id=teacher_id,
                decision=decision,
                page=page,
                page_size=page_size,
                include_classes=include_classes or bool(teacher_id),
            )
            if cached_report is not None:
                return cached_report
        if term_id and not class_id and not include_all and not include_students and not include_classes and not teacher_id:
            lite_report = self._training_teacher_report_lite_fast(
                user,
                term_id=term_id,
                branch=branch,
                campus=campus,
                search=search,
                learning_status=status_filter,
                learning_platform=learning_platform,
                teacher_id=teacher_id,
                page=page,
                page_size=page_size,
                decision=decision,
            )
            if lite_report is not None:
                return lite_report
        query = self.db.query(
            AcademicTeacher,
            AcademicTeacherAssignment,
            AcademicClass,
            AcademicTerm,
            AcademicBlock,
            AcademicSubject,
        ).join(
            AcademicTeacherAssignment,
            AcademicTeacherAssignment.teacher_id == AcademicTeacher.id,
        ).join(
            AcademicClass,
            AcademicClass.id == AcademicTeacherAssignment.class_id,
        ).join(
            AcademicTerm,
            AcademicTerm.id == AcademicClass.term_id,
        ).outerjoin(
            AcademicBlock,
            AcademicBlock.id == AcademicClass.block_id,
        ).join(
            AcademicSubject,
            AcademicSubject.id == AcademicClass.subject_id,
        ).outerjoin(
            AcademicSubjectDelivery,
            and_(
                AcademicSubjectDelivery.subject_id == AcademicClass.subject_id,
                AcademicSubjectDelivery.term_id == AcademicClass.term_id,
                AcademicSubjectDelivery.block_id == AcademicClass.block_id,
                func.lower(func.coalesce(AcademicSubjectDelivery.branch, 'poly')) == func.lower(func.coalesce(AcademicClass.branch, 'poly')),
                AcademicSubjectDelivery.active.is_(True),
            ),
        ).filter(
            AcademicTeacher.active.is_(True),
            AcademicClass.active.is_(True),
            AcademicSubject.active.is_(True),
        )
        query = self._apply_academic_access_filter(query, user, decision)
        if term_id:
            query = query.filter(AcademicClass.term_id == term_id)
        platform = self._normalize_report_platform(learning_platform)
        if platform == 'udemy':
            query = query.filter(AcademicSubjectDelivery.learning_platform == 'udemy')
        elif platform == 'cms':
            query = query.filter(AcademicSubjectDelivery.learning_platform == 'cms')
        if branch:
            query = query.filter(AcademicClass.branch == branch.strip().lower())
        if campus:
            query = query.filter(func.lower(AcademicClass.campus) == campus.strip().lower())
        if teacher_id and str(teacher_id).strip():
            query = query.filter(AcademicTeacher.id == str(teacher_id).strip())
        if class_id and str(class_id).strip():
            query = query.filter(AcademicClass.id == str(class_id).strip())
        if search and search.strip():
            like = f"%{search.strip()}%"
            query = query.filter(or_(
                AcademicTeacher.username.ilike(like),
                AcademicTeacher.full_name.ilike(like),
                AcademicTeacher.email.ilike(like),
                AcademicClass.class_code.ilike(like),
                AcademicSubject.subject_code.ilike(like),
                AcademicSubject.subject_name.ilike(like),
            ))
        rows = query.order_by(
            AcademicTeacher.full_name.asc().nullslast(),
            AcademicTeacher.username.asc(),
            AcademicTerm.start_date.desc().nullslast(),
            AcademicSubject.subject_code.asc(),
            AcademicClass.class_code.asc(),
        ).all()

        # Performance guard: the default teacher-management overview should not
        # hydrate students/snapshots/policy for every teacher in every campus.
        # First resolve the teacher page, then compute class/student aggregates
        # only for the teachers visible on the current page. Full export and
        # status-filtered views keep the full scan because they need global rows.
        # Production rule: teacher KPI cards must be totals for the full current filter.
        # The previous fast page mode calculated summary from only visible teachers, which
        # made one-campus totals look larger than all-campus totals depending on page 1.
        fast_page_mode = False
        fast_total: int | None = None
        if fast_page_mode:
            ordered_teacher_ids: list[str] = []
            seen_teacher_ids: set[str] = set()
            for teacher, *_rest in rows:
                if teacher.id in seen_teacher_ids:
                    continue
                seen_teacher_ids.add(teacher.id)
                ordered_teacher_ids.append(teacher.id)
            fast_total = len(ordered_teacher_ids)
            selected_teacher_ids = set(ordered_teacher_ids[(page - 1) * page_size: page * page_size])
            rows = [row for row in rows if row[0].id in selected_teacher_ids]

        class_by_id: dict[str, AcademicClass] = {}
        block_by_class: dict[str, AcademicBlock | None] = {}
        class_context: dict[str, dict[str, Any]] = {}
        for teacher, assignment, cls, term, block, subject in rows:
            class_by_id[cls.id] = cls
            block_by_class[cls.id] = block
            class_context[cls.id] = {
                'term_name': term.term_name if term else None,
                'block_name': block.block_name if block else None,
                'subject_code': subject.subject_code if subject else None,
                'subject_name': subject.subject_name if subject else None,
            }
        class_ids = list(class_by_id.keys())
        udemy_context_by_class = self._teacher_udemy_context(list(class_by_id.values()))

        student_rows = self.db.query(AcademicClassStudent.class_id, AcademicClassStudent.student_id, AcademicClassStudent.metadata_json).filter(
            AcademicClassStudent.class_id.in_(class_ids)
        ).all() if class_ids else []
        student_ids_by_class: dict[str, set[str]] = {class_id: set() for class_id in class_ids}
        relearn_by_class: dict[str, dict[str, int]] = {class_id: {'student_count': 0, 'total': 0} for class_id in class_ids}
        relearn_by_class_student: dict[tuple[str, str], int] = {}
        for class_id, student_id, meta in student_rows:
            student_ids_by_class.setdefault(class_id, set()).add(student_id)
            total_relearn = self._metadata_total_relearn(meta)
            relearn_by_class_student[(class_id, student_id)] = total_relearn
            if total_relearn > 0:
                bucket = relearn_by_class.setdefault(class_id, {'student_count': 0, 'total': 0})
                bucket['student_count'] += 1
                bucket['total'] += total_relearn
        student_count_by_class = {class_id: len(ids) for class_id, ids in student_ids_by_class.items()}

        sync_by_class = self._student_sync_summary_for_classes(class_ids)
        class_overrides = self.db.query(AcademicClassCourseMapping).filter(
            AcademicClassCourseMapping.class_id.in_(class_ids),
            AcademicClassCourseMapping.active.is_(True),
        ).order_by(AcademicClassCourseMapping.updated_at.desc().nullslast()).all() if class_ids else []
        override_by_class = {item.class_id: item for item in class_overrides}
        inherited_by_class = self.inherited_course_mappings_for_classes(list(class_by_id.values()))
        course_by_class: dict[str, str | None] = {}
        mapping_source_by_class: dict[str, str | None] = {}
        for class_id, cls in class_by_id.items():
            mapping = override_by_class.get(class_id) or inherited_by_class.get(class_id)
            course_by_class[class_id] = mapping.openedx_course_id if mapping else None
            mapping_source_by_class[class_id] = 'class_override' if class_id in override_by_class else ('subject_term_mapping' if mapping else None)

        learning_by_class = self._learning_summary_by_class_ids(class_ids, course_by_class)
        status_counts_by_class, snapshot_by_class_student, status_by_class_student = self._training_learning_status_counts_by_class(class_ids, course_by_class)
        deadline_by_class, deadline_by_class_student = self._training_deadline_status_by_class(class_by_id, block_by_class, snapshot_by_class_student)

        policy_service = TrainingPolicyService(self.db)
        policy_by_class_student: dict[tuple[str, str], dict[str, Any]] = {}
        policy_summary_by_class: dict[str, dict[str, int]] = {}
        for class_id, cls in class_by_id.items():
            course_id = course_by_class.get(class_id)
            overrides = policy_service.deadline_overrides_for_class(class_id, course_id)
            assignment_scores = policy_service.assignment_scores_for_class(class_id, course_id)
            summary_bucket = {
                'exam_eligible_student_count': 0,
                'exam_not_eligible_student_count': 0,
                'exam_insufficient_data_student_count': 0,
                'quiz_failed_count': 0,
                'quiz_late_count': 0,
                'quiz_not_attempted_count': 0,
                'quiz_missing_deadline_count': 0,
                'assignment_not_graded_count': 0,
            }
            for student_id in student_ids_by_class.get(class_id, set()):
                snapshot = snapshot_by_class_student.get((class_id, student_id))
                # Do not evaluate exam eligibility for students/classes without a Course
                # CMS snapshot. They are already represented by CMS/enrollment/no-data
                # buckets. Evaluating policy here inflated "thiếu dữ liệu" to every
                # unsynced student and made /training-management very slow at 30+ campuses.
                if not course_id or snapshot is None:
                    continue
                raw_components = self._component_scores_from_snapshot(snapshot)
                if not raw_components and student_id not in assignment_scores:
                    continue
                components = self._enrich_component_scores_for_class(raw_components, cls)
                policy = policy_service.evaluate_student(
                    cls=cls,
                    student_id=student_id,
                    components=components,
                    block=block_by_class.get(class_id),
                    course_id=course_id,
                    assignment_score=assignment_scores.get(student_id),
                    overrides=overrides,
                )
                policy_by_class_student[(class_id, student_id)] = policy
                status_name = str(policy.get('exam_status') or '')
                if status_name == 'eligible':
                    summary_bucket['exam_eligible_student_count'] += 1
                elif status_name == 'not_eligible':
                    summary_bucket['exam_not_eligible_student_count'] += 1
                elif raw_components or student_id in assignment_scores:
                    summary_bucket['exam_insufficient_data_student_count'] += 1
                summary_bucket['quiz_failed_count'] += int(policy.get('quiz_failed_count') or 0)
                summary_bucket['quiz_late_count'] += int(policy.get('quiz_late_count') or 0)
                summary_bucket['quiz_not_attempted_count'] += int(policy.get('quiz_not_attempted_count') or 0)
                summary_bucket['quiz_missing_deadline_count'] += int(policy.get('quiz_missing_deadline_count') or 0)
                if policy.get('assignment_expected') and policy.get('assignment_status') != 'graded':
                    summary_bucket['assignment_not_graded_count'] += 1
            policy_summary_by_class[class_id] = summary_bucket

        teacher_buckets: dict[str, dict[str, Any]] = {}
        seen_teacher_classes: set[tuple[str, str]] = set()
        class_teacher_context: dict[str, list[dict[str, Any]]] = {}
        for teacher, assignment, cls, term, block, subject in rows:
            key = teacher.id
            bucket = teacher_buckets.setdefault(key, {
                'teacher_id': teacher.id,
                'teacher_code': teacher.teacher_code,
                'teacher_username': teacher.username,
                'teacher_name': teacher.full_name or teacher.username,
                'teacher_email': teacher.email,
                'campus': teacher.campus or cls.campus,
                'branch': teacher.branch or cls.branch,
                'subject_ids': set(),
                'subject_codes': set(),
                'class_ids': set(),
                'unique_student_ids': set(),
                'student_count': 0,
                'cms_class_count': 0,
                'udemy_class_count': 0,
                'cms_student_count': 0,
                'udemy_student_count': 0,
                'udemy_progress_student_count': 0,
                'udemy_progress_late_count': 0,
                'udemy_progress_weighted_sum': 0.0,
                'udemy_progress_weight': 0,
                'udemy_last_imported_at': None,
                'cms_synced_count': 0,
                'cms_unsynced_count': 0,
                'learning_enrolled_count': 0,
                'learning_active_count': 0,
                'learning_synced_count': 0,
                'classes_without_course_count': 0,
                'deadline_late_student_count': 0,
                'deadline_late_quiz_count': 0,
                'deadline_due_quiz_count': 0,
                'exam_eligible_student_count': 0,
                'exam_not_eligible_student_count': 0,
                'exam_insufficient_data_student_count': 0,
                'quiz_failed_count': 0,
                'quiz_late_count': 0,
                'quiz_not_attempted_count': 0,
                'quiz_missing_deadline_count': 0,
                'assignment_not_graded_count': 0,
                'relearn_student_count': 0,
                'total_relearn_count': 0,
                'progress_weighted_sum': 0.0,
                'progress_weight': 0,
                'grade_weighted_sum': 0.0,
                'grade_weight': 0,
                'status_counts': {},
                'risk_student_ids': set(),
                'class_items': [],
                'last_synced_at': None,
            })
            class_teacher_context.setdefault(cls.id, []).append({
                'teacher_id': teacher.id,
                'teacher_username': teacher.username,
                'teacher_name': teacher.full_name or teacher.username,
                'teacher_email': teacher.email,
            })
            pair = (teacher.id, cls.id)
            if pair in seen_teacher_classes:
                continue
            seen_teacher_classes.add(pair)
            bucket['class_ids'].add(cls.id)
            bucket['subject_ids'].add(subject.id)
            bucket['subject_codes'].add(subject.subject_code)
            class_student_ids = student_ids_by_class.get(cls.id, set())
            bucket['unique_student_ids'].update(class_student_ids)
            class_student_count = int(student_count_by_class.get(cls.id, 0) or 0)
            class_relearn = relearn_by_class.get(cls.id, {})
            relearn_student_count = int(class_relearn.get('student_count') or 0)
            total_relearn_count = int(class_relearn.get('total') or 0)
            bucket['student_count'] += class_student_count
            bucket['relearn_student_count'] += relearn_student_count
            bucket['total_relearn_count'] += total_relearn_count
            udemy_context = udemy_context_by_class.get(str(cls.id), {})
            is_udemy = udemy_context.get('learning_platform') == 'udemy'
            cms_synced = 0
            cms_unsynced = 0
            enrolled = 0
            active = 0
            synced = 0
            avg_progress = None
            avg_grade = None
            last_synced = None
            status_counts: dict[str, int] = {}
            class_risk_student_ids: set[str] = set()
            deadline: dict[str, Any] = {}
            deadline_late_students = 0
            deadline_late_quizzes = 0
            deadline_due_quizzes = 0
            policy_summary: dict[str, Any] = {}
            alerts: list[str] = []
            if is_udemy:
                bucket['udemy_class_count'] += 1
                bucket['udemy_student_count'] += class_student_count
                imported = int(udemy_context.get('progress_student_count') or 0)
                udemy_late = int(udemy_context.get('late_student_count') or 0)
                bucket['udemy_progress_student_count'] += imported
                bucket['udemy_progress_late_count'] += udemy_late
                if imported and udemy_context.get('average_progress_percent') is not None:
                    bucket['udemy_progress_weighted_sum'] += float(udemy_context.get('average_progress_percent')) * imported
                    bucket['udemy_progress_weight'] += imported
                last_imported = udemy_context.get('last_imported_at')
                if last_imported and (bucket['udemy_last_imported_at'] is None or last_imported > bucket['udemy_last_imported_at']):
                    bucket['udemy_last_imported_at'] = last_imported
                if udemy_late:
                    bucket['status_counts']['udemy_late'] = int(bucket['status_counts'].get('udemy_late', 0) or 0) + udemy_late
                    status_counts['udemy_late'] = udemy_late
                    class_risk_student_ids.update(udemy_context.get('late_student_ids') or set())
                    alerts.append(f'{udemy_late} SV Udemy chậm tiến độ')
                if imported < class_student_count:
                    alerts.append(f'{max(0, class_student_count - imported)} SV chưa có tiến độ Udemy')
                bucket['risk_student_ids'].update(class_risk_student_ids)
            else:
                bucket['cms_class_count'] += 1
                bucket['cms_student_count'] += class_student_count
                sync_counts = sync_by_class.get(cls.id, {})
                cms_synced = int(sync_counts.get('matched', 0) or 0)
                cms_unsynced = max(0, class_student_count - cms_synced)
                bucket['cms_synced_count'] += cms_synced
                bucket['cms_unsynced_count'] += cms_unsynced
                learning = learning_by_class.get(cls.id, {})
                enrolled = int(learning.get('learning_enrolled_count') or 0)
                active = int(learning.get('learning_active_count') or 0)
                synced = int(learning.get('learning_synced_count') or 0)
                bucket['learning_enrolled_count'] += enrolled
                bucket['learning_active_count'] += active
                bucket['learning_synced_count'] += synced
                if not course_by_class.get(cls.id):
                    bucket['classes_without_course_count'] += 1
                avg_progress = learning.get('learning_avg_progress_percent')
                avg_grade = learning.get('learning_avg_grade_percent')
                if isinstance(avg_progress, (int, float)) and synced:
                    bucket['progress_weighted_sum'] += float(avg_progress) * synced
                    bucket['progress_weight'] += synced
                if isinstance(avg_grade, (int, float)) and synced:
                    bucket['grade_weighted_sum'] += float(avg_grade) * synced
                    bucket['grade_weight'] += synced
                status_counts = status_counts_by_class.get(cls.id, {})
                for status_name, count in status_counts.items():
                    bucket['status_counts'][status_name] = int(bucket['status_counts'].get(status_name, 0) or 0) + int(count or 0)
                for student_id in class_student_ids:
                    # Use the precomputed per-student learning status, including CMS mapping,
                    # so risk counts are precise and each student is counted at most once
                    # for the teacher.
                    status_name = status_by_class_student.get((cls.id, student_id))
                    if status_name in self._risk_status_keys():
                        class_risk_student_ids.add(student_id)
                last_synced = learning.get('learning_last_synced_at')
                if last_synced and (bucket['last_synced_at'] is None or last_synced > bucket['last_synced_at']):
                    bucket['last_synced_at'] = last_synced
                deadline = deadline_by_class.get(cls.id, {})
                deadline_late_students = int(deadline.get('late_student_count') or 0)
                deadline_late_quizzes = int(deadline.get('late_quiz_count') or 0)
                deadline_due_quizzes = int(deadline.get('due_quiz_count') or 0)
                bucket['deadline_late_student_count'] += deadline_late_students
                bucket['deadline_late_quiz_count'] += deadline_late_quizzes
                bucket['deadline_due_quiz_count'] += deadline_due_quizzes
                policy_summary = policy_summary_by_class.get(cls.id, {})
                for policy_key in ('exam_eligible_student_count', 'exam_not_eligible_student_count', 'exam_insufficient_data_student_count', 'quiz_failed_count', 'quiz_late_count', 'quiz_not_attempted_count', 'quiz_missing_deadline_count', 'assignment_not_graded_count'):
                    bucket[policy_key] += int(policy_summary.get(policy_key) or 0)
                if int(policy_summary.get('exam_not_eligible_student_count') or 0):
                    bucket['status_counts']['exam_not_eligible'] = int(bucket['status_counts'].get('exam_not_eligible', 0) or 0) + int(policy_summary.get('exam_not_eligible_student_count') or 0)
                    for (policy_class_id, policy_student_id), policy in policy_by_class_student.items():
                        if policy_class_id == cls.id and str(policy.get('exam_status') or '') == 'not_eligible':
                            class_risk_student_ids.add(policy_student_id)
                if int(policy_summary.get('exam_insufficient_data_student_count') or 0):
                    bucket['status_counts']['exam_insufficient_data'] = int(bucket['status_counts'].get('exam_insufficient_data', 0) or 0) + int(policy_summary.get('exam_insufficient_data_student_count') or 0)
                if deadline_late_students:
                    bucket['status_counts']['deadline_late'] = int(bucket['status_counts'].get('deadline_late', 0) or 0) + deadline_late_students
                    for (deadline_class_id, deadline_student_id), deadline_status in deadline_by_class_student.items():
                        if deadline_class_id == cls.id and int(deadline_status.get('late_quiz_count') or 0) > 0:
                            class_risk_student_ids.add(deadline_student_id)
                bucket['risk_student_ids'].update(class_risk_student_ids)
                alerts = list(learning.get('learning_alerts') or [])
                if not course_by_class.get(cls.id) and 'Chưa map Course CMS' not in alerts:
                    alerts.append('Chưa map Course CMS')
                if deadline_late_students:
                    alerts.append(f'{deadline_late_students} SV trễ deadline quiz ({deadline_late_quizzes} lượt quiz)')
            bucket['class_items'].append({
                'class_id': cls.id,
                'class_code': cls.class_code,
                'class_name': cls.class_name,
                'term_id': cls.term_id,
                'term_name': term.term_name if term else None,
                'block_id': cls.block_id,
                'block_name': block.block_name if block else None,
                'subject_id': subject.id,
                'subject_code': subject.subject_code,
                'subject_name': subject.subject_name,
                'campus': cls.campus,
                'branch': cls.branch,
                'learning_platform': 'udemy' if is_udemy else 'cms',
                'subject_delivery_id': udemy_context.get('subject_delivery_id') if is_udemy else None,
                'student_count': class_student_count,
                'udemy_progress_student_count': int(udemy_context.get('progress_student_count') or 0) if is_udemy else 0,
                'udemy_progress_late_count': int(udemy_context.get('late_student_count') or 0) if is_udemy else 0,
                'udemy_progress_average_percent': udemy_context.get('average_progress_percent') if is_udemy else None,
                'udemy_progress_required_percent': udemy_context.get('required_progress_percent') if is_udemy else None,
                'udemy_progress_current_week': udemy_context.get('current_plan_week') if is_udemy else None,
                'udemy_progress_deadline_date': udemy_context.get('current_deadline_date') if is_udemy else None,
                'udemy_progress_last_imported_at': udemy_context.get('last_imported_at') if is_udemy else None,
                'relearn_student_count': relearn_student_count,
                'total_relearn_count': total_relearn_count,
                'cms_synced_count': cms_synced,
                'cms_unsynced_count': cms_unsynced,
                'openedx_course_id': course_by_class.get(cls.id),
                'openedx_mapping_source': mapping_source_by_class.get(cls.id),
                'learning_enrolled_count': enrolled,
                'learning_active_count': active,
                'learning_synced_count': synced,
                'learning_avg_progress_percent': avg_progress,
                'learning_avg_grade_percent': avg_grade,
                'learning_avg_grade_10': self._percent_to_grade10(avg_grade),
                'learning_last_synced_at': last_synced,
                'learning_component_summaries': learning.get('learning_component_summaries') or [],
                'status_counts': status_counts,
                'learning_alerts': alerts,
                'risk_student_count': len(class_risk_student_ids),
                'deadline_quiz_count': int(deadline.get('quiz_count') or 0),
                'deadline_due_quiz_count': deadline_due_quizzes,
                'deadline_completed_due_quiz_count': int(deadline.get('completed_due_quiz_count') or 0),
                'deadline_late_student_count': deadline_late_students,
                'deadline_late_quiz_count': deadline_late_quizzes,
                'deadline_next_quiz_label': deadline.get('next_quiz_label'),
                'deadline_next_quiz_from_date': deadline.get('next_quiz_from_date'),
                'deadline_next_quiz_due_date': deadline.get('next_quiz_due_date'),
                'deadline_schedule_note': deadline.get('schedule_note'),
                'exam_eligible_student_count': int(policy_summary.get('exam_eligible_student_count') or 0),
                'exam_not_eligible_student_count': int(policy_summary.get('exam_not_eligible_student_count') or 0),
                'exam_insufficient_data_student_count': int(policy_summary.get('exam_insufficient_data_student_count') or 0),
                'quiz_failed_count': int(policy_summary.get('quiz_failed_count') or 0),
                'quiz_late_count': int(policy_summary.get('quiz_late_count') or 0),
                'quiz_not_attempted_count': int(policy_summary.get('quiz_not_attempted_count') or 0),
                'quiz_missing_deadline_count': int(policy_summary.get('quiz_missing_deadline_count') or 0),
                'assignment_not_graded_count': int(policy_summary.get('assignment_not_graded_count') or 0),
            })

        items: list[dict[str, Any]] = []
        alert_keys = sorted(self._risk_status_keys())
        for bucket in teacher_buckets.values():
            status_counts = dict(bucket['status_counts'])
            avg_progress = round(bucket['progress_weighted_sum'] / bucket['progress_weight'], 2) if bucket['progress_weight'] else None
            avg_grade = round(bucket['grade_weighted_sum'] / bucket['grade_weight'], 2) if bucket['grade_weight'] else None
            risk_student_count = len(bucket.get('risk_student_ids') or set())
            if not risk_student_count:
                risk_student_count = self._bounded_risk_count_from_status_counts(status_counts, int(bucket.get('student_count') or 0))
            learning_alerts: list[str] = []
            if bucket['classes_without_course_count']:
                learning_alerts.append(f"{bucket['classes_without_course_count']} lớp chưa map Course CMS")
            if int(status_counts.get('cms_not_synced', 0) or 0):
                learning_alerts.append(f"{int(status_counts.get('cms_not_synced', 0) or 0)} SV chưa đồng bộ CMS")
            if int(status_counts.get('not_enrolled', 0) or 0):
                learning_alerts.append(f"{int(status_counts.get('not_enrolled', 0) or 0)} SV chưa enroll")
            if int(status_counts.get('no_activity', 0) or 0):
                learning_alerts.append(f"{int(status_counts.get('no_activity', 0) or 0)} SV chưa học")
            if int(status_counts.get('low_progress', 0) or 0):
                learning_alerts.append(f"{int(status_counts.get('low_progress', 0) or 0)} SV tiến độ thấp")
            if int(status_counts.get('low_grade', 0) or 0):
                learning_alerts.append(f"{int(status_counts.get('low_grade', 0) or 0)} SV điểm thấp")
            if int(status_counts.get('deadline_late', 0) or 0):
                learning_alerts.append(f"{int(status_counts.get('deadline_late', 0) or 0)} SV trễ deadline quiz")
            if int(status_counts.get('exam_not_eligible', 0) or 0):
                learning_alerts.append(f"{int(status_counts.get('exam_not_eligible', 0) or 0)} SV không được thi")
            if int(status_counts.get('exam_insufficient_data', 0) or 0):
                learning_alerts.append(f"{int(status_counts.get('exam_insufficient_data', 0) or 0)} SV chưa đủ dữ liệu xét thi")
            if int(bucket.get('udemy_progress_late_count') or 0):
                learning_alerts.append(f"{int(bucket.get('udemy_progress_late_count') or 0)} SV Udemy chậm tiến độ")
            udemy_avg = round(bucket['udemy_progress_weighted_sum'] / bucket['udemy_progress_weight'], 2) if bucket['udemy_progress_weight'] else None
            item = {
                'teacher_id': bucket['teacher_id'],
                'teacher_code': bucket['teacher_code'],
                'teacher_username': bucket['teacher_username'],
                'teacher_name': bucket['teacher_name'],
                'teacher_email': bucket['teacher_email'],
                'campus': bucket['campus'],
                'branch': bucket['branch'],
                'subject_count': len(bucket['subject_ids']),
                'subject_codes': sorted(bucket['subject_codes']),
                'class_count': len(bucket['class_ids']),
                'student_count': int(bucket['student_count']),
                'unique_student_count': len(bucket['unique_student_ids']),
                'cms_class_count': int(bucket['cms_class_count']),
                'udemy_class_count': int(bucket['udemy_class_count']),
                'cms_student_count': int(bucket['cms_student_count']),
                'udemy_student_count': int(bucket['udemy_student_count']),
                'udemy_progress_student_count': int(bucket['udemy_progress_student_count']),
                'udemy_progress_late_count': int(bucket['udemy_progress_late_count']),
                'udemy_progress_average_percent': udemy_avg,
                'udemy_progress_last_imported_at': bucket['udemy_last_imported_at'],
                'relearn_student_count': int(bucket['relearn_student_count']),
                'total_relearn_count': int(bucket['total_relearn_count']),
                'cms_synced_count': int(bucket['cms_synced_count']),
                'cms_unsynced_count': int(bucket['cms_unsynced_count']),
                'learning_enrolled_count': int(bucket['learning_enrolled_count']),
                'learning_active_count': int(bucket['learning_active_count']),
                'learning_synced_count': int(bucket['learning_synced_count']),
                'classes_without_course_count': int(bucket['classes_without_course_count']),
                'deadline_late_student_count': int(bucket['deadline_late_student_count']),
                'deadline_late_quiz_count': int(bucket['deadline_late_quiz_count']),
                'deadline_due_quiz_count': int(bucket['deadline_due_quiz_count']),
                'exam_eligible_student_count': int(bucket['exam_eligible_student_count']),
                'exam_not_eligible_student_count': int(bucket['exam_not_eligible_student_count']),
                'exam_insufficient_data_student_count': int(bucket['exam_insufficient_data_student_count']),
                'quiz_failed_count': int(bucket['quiz_failed_count']),
                'quiz_late_count': int(bucket['quiz_late_count']),
                'quiz_not_attempted_count': int(bucket['quiz_not_attempted_count']),
                'quiz_missing_deadline_count': int(bucket['quiz_missing_deadline_count']),
                'assignment_not_graded_count': int(bucket['assignment_not_graded_count']),
                'learning_avg_progress_percent': avg_progress,
                'learning_avg_grade_percent': avg_grade,
                'learning_avg_grade_10': self._percent_to_grade10(avg_grade),
                'risk_student_count': risk_student_count,
                'status_counts': status_counts,
                'learning_alerts': learning_alerts,
                'last_synced_at': bucket['last_synced_at'],
            }
            if include_classes or include_students or include_all:
                item['classes'] = sorted(bucket['class_items'], key=lambda item: (str(item.get('subject_code') or ''), str(item.get('class_code') or '')))

            item['learning_platform'] = platform or 'all'
            items.append(item)

        def matches_training_filter(item: dict[str, Any]) -> bool:
            if status_filter == 'all':
                return True
            status_counts = item.get('status_counts') or {}
            if status_filter == 'no_course_map':
                return int(item.get('classes_without_course_count') or 0) > 0
            if status_filter == 'cms_not_synced':
                return int(status_counts.get('cms_not_synced', 0) or 0) > 0 or int(item.get('cms_unsynced_count') or 0) > 0
            if status_filter == 'not_fully_enrolled':
                return int(status_counts.get('not_enrolled', 0) or 0) > 0 or int(item.get('learning_enrolled_count') or 0) < int(item.get('student_count') or 0)
            if status_filter == 'no_learning_data':
                return int(item.get('learning_synced_count') or 0) == 0 and int(item.get('student_count') or 0) > 0
            if status_filter == 'udemy_late':
                return int(item.get('udemy_progress_late_count') or 0) > 0
            if status_filter in {'no_activity', 'low_progress', 'low_grade', 'sync_error', 'deadline_late', 'exam_not_eligible', 'exam_insufficient_data'}:
                return int(status_counts.get(status_filter, 0) or 0) > 0
            if status_filter == 'has_alert':
                return bool(item.get('learning_alerts')) or int(item.get('risk_student_count') or 0) > 0
            return True

        filtered_items = [item for item in items if matches_training_filter(item)]
        filtered_items.sort(key=lambda item: (str(item.get('teacher_name') or ''), str(item.get('teacher_username') or '')))
        if fast_page_mode:
            total = int(fast_total or 0)
            page_items = filtered_items
            total_pages = math.ceil(total / page_size) if total else 0
        else:
            total = len(filtered_items)
            if include_all:
                page_items = filtered_items
                total_pages = 1 if total else 0
            else:
                page_items = [self._teacher_report_public_item(item, include_classes=include_classes or bool(teacher_id)) for item in filtered_items[(page - 1) * page_size: page * page_size]]
                total_pages = math.ceil(total / page_size) if total else 0
        # Summary counters intentionally remain teacher-assignment scoped for class/student
        # workload, but warning counts are bounded and non-overlapping per teacher.
        summary = {
            'teacher_count': total,
            'class_count': sum(int(item.get('class_count') or 0) for item in filtered_items),
            'subject_count': len({code for item in filtered_items for code in (item.get('subject_codes') or [])}),
            'student_count': sum(int(item.get('student_count') or 0) for item in filtered_items),
            'unique_student_count': sum(int(item.get('unique_student_count') or 0) for item in filtered_items),
            'relearn_student_count': sum(int(item.get('relearn_student_count') or 0) for item in filtered_items),
            'total_relearn_count': sum(int(item.get('total_relearn_count') or 0) for item in filtered_items),
            'cms_class_count': sum(int(item.get('cms_class_count') or 0) for item in filtered_items),
            'udemy_class_count': sum(int(item.get('udemy_class_count') or 0) for item in filtered_items),
            'cms_student_count': sum(int(item.get('cms_student_count') or 0) for item in filtered_items),
            'udemy_student_count': sum(int(item.get('udemy_student_count') or 0) for item in filtered_items),
            'cms_synced_count': min(sum(int(item.get('cms_synced_count') or 0) for item in filtered_items), sum(int(item.get('cms_student_count') or 0) for item in filtered_items)),
            'udemy_progress_student_count': sum(int(item.get('udemy_progress_student_count') or 0) for item in filtered_items),
            'udemy_progress_late_count': sum(int(item.get('udemy_progress_late_count') or 0) for item in filtered_items),
            'udemy_progress_average_percent': (
                round(
                    sum(float(item.get('udemy_progress_average_percent') or 0) * int(item.get('udemy_progress_student_count') or 0) for item in filtered_items)
                    / sum(int(item.get('udemy_progress_student_count') or 0) for item in filtered_items),
                    2,
                )
                if sum(int(item.get('udemy_progress_student_count') or 0) for item in filtered_items)
                else None
            ),
            'learning_enrolled_count': min(sum(int(item.get('learning_enrolled_count') or 0) for item in filtered_items), sum(int(item.get('student_count') or 0) for item in filtered_items)),
            'learning_active_count': min(sum(int(item.get('learning_active_count') or 0) for item in filtered_items), sum(int(item.get('student_count') or 0) for item in filtered_items)),
            'risk_student_count': min(sum(int(item.get('risk_student_count') or 0) for item in filtered_items), sum(int(item.get('student_count') or 0) for item in filtered_items)),
            'classes_without_course_count': sum(int(item.get('classes_without_course_count') or 0) for item in filtered_items),
            'deadline_late_student_count': sum(int(item.get('deadline_late_student_count') or 0) for item in filtered_items),
            'deadline_late_quiz_count': sum(int(item.get('deadline_late_quiz_count') or 0) for item in filtered_items),
            'exam_eligible_student_count': sum(int(item.get('exam_eligible_student_count') or 0) for item in filtered_items),
            'exam_not_eligible_student_count': sum(int(item.get('exam_not_eligible_student_count') or 0) for item in filtered_items),
            'exam_insufficient_data_student_count': sum(int(item.get('exam_insufficient_data_student_count') or 0) for item in filtered_items),
            'quiz_failed_count': sum(int(item.get('quiz_failed_count') or 0) for item in filtered_items),
            'assignment_not_graded_count': sum(int(item.get('assignment_not_graded_count') or 0) for item in filtered_items),
        }
        result: dict[str, Any] = {'items': page_items, 'summary': summary, 'summary_scope': 'current_page' if fast_page_mode else 'filtered', 'total': total, 'page': page, 'page_size': page_size, 'total_pages': total_pages, 'has_next': (not include_all and page < total_pages), 'cache': {'status': 'bypass' if not use_cache else 'miss', 'scope_key': self._teacher_report_scope_key(term_id, branch, campus) if term_id else None}}

        if include_students and class_ids:
            student_query = self.db.query(
                AcademicClassStudent.class_id,
                AcademicClassStudent.metadata_json,
                AcademicStudent,
                OpenEdXUserMapping,
    UdemyStudentProgress,
            ).join(
                AcademicStudent,
                AcademicStudent.id == AcademicClassStudent.student_id,
            ).outerjoin(
                OpenEdXUserMapping,
    UdemyStudentProgress,
                OpenEdXUserMapping.student_id == AcademicClassStudent.student_id,
            ).filter(AcademicClassStudent.class_id.in_(class_ids))
            watch_rows: list[dict[str, Any]] = []
            for class_id, class_student_meta, student, mapping in student_query.order_by(AcademicStudent.student_code.asc().nullslast(), AcademicStudent.username.asc()).all():
                snapshot = snapshot_by_class_student.get((class_id, student.id))
                status_name = self._learning_status_for_snapshot(snapshot, mapping)
                deadline_status = deadline_by_class_student.get((class_id, student.id), {})
                policy = policy_by_class_student.get((class_id, student.id), {})
                if not class_id and status_name in {'good', 'in_progress'} and int(deadline_status.get('late_quiz_count') or 0) <= 0 and policy.get('exam_status') != 'not_eligible':
                    continue
                for teacher_ctx in class_teacher_context.get(class_id, []):
                    context = class_context.get(class_id, {})
                    watch_rows.append({
                        **teacher_ctx,
                        'class_id': class_id,
                        'class_code': class_by_id[class_id].class_code if class_id in class_by_id else '',
                        'term_name': context.get('term_name'),
                        'block_name': context.get('block_name'),
                        'subject_code': context.get('subject_code'),
                        'subject_name': context.get('subject_name'),
                        'student_code': student.student_code,
                        'student_username': student.username,
                        'student_name': student.full_name,
                        'student_email': student.email,
                        'total_relearn': self._metadata_total_relearn(class_student_meta, student.metadata_json),
                        'openedx_username': mapping.openedx_username if mapping else None,
                        'status': status_name,
                        'status_label': self._learning_status_label(status_name),
                        'enrollment_status': snapshot.enrollment_status if snapshot else None,
                        'progress_percent': self._snapshot_progress_percent(snapshot),
                        'grade_percent': self._snapshot_grade_percent(snapshot),
                        'grade_10': self._percent_to_grade10(self._snapshot_grade_percent(snapshot)),
                        'last_activity_at': snapshot.last_activity_at if snapshot else None,
                        'last_synced_at': (snapshot.learning_synced_at or snapshot.last_synced_at) if snapshot else None,
                        'exam_status': policy.get('exam_status'),
                        'exam_status_label': policy.get('exam_status_label'),
                        'exam_reasons': policy.get('exam_reasons') or [],
                        'exam_cutoff_date': policy.get('exam_cutoff_date'),
                        'exam_cutoff_source': policy.get('exam_cutoff_source'),
                        'quiz_passed_count': policy.get('quiz_passed_count'),
                        'quiz_failed_count': policy.get('quiz_failed_count'),
                        'quiz_not_attempted_count': policy.get('quiz_not_attempted_count'),
                        'assignment_status': policy.get('assignment_status'),
                        'assignment_score_10': policy.get('assignment_score_10'),
                        'deadline_due_quiz_count': int(deadline_status.get('due_quiz_count') or 0),
                        'deadline_completed_due_quiz_count': int(deadline_status.get('completed_due_quiz_count') or 0),
                        'deadline_late_quiz_count': int(deadline_status.get('late_quiz_count') or 0),
                        'deadline_late_quizzes': deadline_status.get('late_quizzes') or [],
                        'deadline_next_quiz_label': deadline_status.get('next_quiz_label'),
                        'deadline_next_quiz_from_date': deadline_status.get('next_quiz_from_date'),
                        'deadline_next_quiz_due_date': deadline_status.get('next_quiz_due_date'),
                    })
                    if len(watch_rows) >= 20000:
                        break
                if len(watch_rows) >= 20000:
                    break
            result['student_watch_rows'] = watch_rows
        return result

