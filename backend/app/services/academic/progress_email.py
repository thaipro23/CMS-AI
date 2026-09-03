from __future__ import annotations

import html
import re
from datetime import datetime, timedelta
from typing import Any

from fastapi import HTTPException
from sqlalchemy import and_
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.rbac import UserContext
from app.models.academic import (
    AcademicBlock,
    AcademicClass,
    AcademicClassStudent,
    AcademicStudent,
    AcademicStudentLearningSnapshot,
    AcademicSubject,
)
from app.services.academic.subject_delivery import AcademicSubjectDeliveryService
from app.services.training_policy_service import TrainingPolicyService


_EMAIL_PATTERN = re.compile(r'^[^\s@]+@[^\s@]+\.[^\s@]+$')
_ACTIVE_OVERDUE_QUIZ_STATUSES = {
    'progress_deadline_missed_not_attempted',
    'progress_deadline_missed_not_100',
}


def normalize_recipient_email(value: Any) -> str | None:
    email = str(value or '').strip().lower()
    return email if email and _EMAIL_PATTERN.fullmatch(email) else None


def mask_recipient_email(value: Any) -> str | None:
    email = normalize_recipient_email(value)
    if not email:
        return None
    local, domain = email.rsplit('@', 1)
    if len(local) <= 1:
        masked_local = f'{local[:1]}***'
    else:
        masked_local = f'{local[:1]}***{local[-1:]}'
    return f'{masked_local}@{domain}'


def plain_text_mail_template(value: str) -> str:
    """Convert teacher-authored plain text to conservative email HTML."""
    escaped = html.escape(str(value or '').strip(), quote=True)
    paragraphs = [item.strip() for item in re.split(r'\n\s*\n', escaped) if item.strip()]
    if not paragraphs:
        return ''
    rendered = ''.join(f'<p>{item.replace(chr(10), "<br>")}</p>' for item in paragraphs)
    return f'<div style="font-family:Arial,sans-serif;font-size:14px;line-height:1.6;color:#172033">{rendered}</div>'


class AcademicProgressEmailService:
    """Resolve overdue Quiz-checkpoint recipients without exposing raw emails."""

    def __init__(self, db: Session):
        self.db = db

    @staticmethod
    def mail_configured() -> bool:
        return bool(
            settings.mailsend_enabled
            and str(settings.mailsend_proxy_base_url or '').strip()
            and str(settings.mailsend_proxy_api_key or '').strip()
        )

    def _context(self, user: UserContext, class_id: str) -> tuple[Any, AcademicClass, AcademicSubject | None, AcademicBlock | None, str]:
        # Local import avoids a module cycle: AcademicService composes the
        # workflow modules under app.services.academic.
        from app.services.academic_service import AcademicService

        academic = AcademicService(self.db)
        academic.assert_can_access_class(user, class_id)
        cls = self.db.get(AcademicClass, class_id)
        if not cls:
            raise HTTPException(status_code=404, detail='Không tìm thấy lớp.')
        AcademicSubjectDeliveryService(self.db).assert_cms_workflow_allowed_for_class(
            class_id,
            job_type='gửi mail nhắc tiến độ CMS',
        )
        mapping = academic.effective_course_mapping_for_class(cls)
        if not mapping or not mapping.openedx_course_id:
            raise HTTPException(
                status_code=409,
                detail='Lớp chưa ghép Course CMS nên chưa thể xác định người chậm tiến độ.',
            )
        subject = self.db.get(AcademicSubject, cls.subject_id) if cls.subject_id else None
        block = self.db.get(AcademicBlock, cls.block_id) if cls.block_id else None
        return academic, cls, subject, block, str(mapping.openedx_course_id)

    @staticmethod
    def _default_subject(cls: AcademicClass, subject: AcademicSubject | None) -> str:
        subject_code = str(subject.subject_code if subject else '').strip()
        class_code = str(cls.class_code or '').strip()
        scope = ' · '.join(item for item in (subject_code, class_code) if item)
        return f'[AI Server] Nhắc tiến độ học tập{f" - {scope}" if scope else ""}'

    @staticmethod
    def _default_body(cls: AcademicClass, subject: AcademicSubject | None) -> str:
        class_code = str(cls.class_code or 'lớp đang học').strip()
        subject_label = ' - '.join(
            item for item in (
                str(subject.subject_code or '').strip() if subject else '',
                str(subject.subject_name or '').strip() if subject else '',
            ) if item
        ) or 'môn học trên CMS'
        return (
            'Xin chào {{maHs}},\n\n'
            f'AI Server ghi nhận bạn đang chậm một hoặc nhiều mốc Quiz của {subject_label}, lớp {class_code}. '
            'Vui lòng vào CMS để kiểm tra và hoàn thành các nội dung còn thiếu.\n\n'
            'Deadline Quiz chỉ là mốc nhắc tiến độ học tập, không phải kết luận cấm thi. '
            'Điều kiện dự thi chỉ được đánh giá sau ngày học cuối chính thức của lớp/block.\n\n'
            'Nếu bạn vừa hoàn thành, dữ liệu sẽ được cập nhật ở lần đồng bộ tiếp theo.\n\n'
            'Trân trọng,\nGiảng viên phụ trách'
        )

    def _evaluate(
        self,
        user: UserContext,
        class_id: str,
        *,
        selected_student_ids: set[str] | None = None,
        minimum_synced_at: datetime | None = None,
    ) -> dict[str, Any]:
        academic, cls, subject, block, course_id = self._context(user, class_id)
        rows = (
            self.db.query(AcademicStudent, AcademicClassStudent, AcademicStudentLearningSnapshot)
            .join(AcademicClassStudent, AcademicClassStudent.student_id == AcademicStudent.id)
            .outerjoin(
                AcademicStudentLearningSnapshot,
                and_(
                    AcademicStudentLearningSnapshot.class_id == class_id,
                    AcademicStudentLearningSnapshot.student_id == AcademicStudent.id,
                    AcademicStudentLearningSnapshot.openedx_course_id == course_id,
                ),
            )
            .filter(AcademicClassStudent.class_id == class_id)
            .order_by(AcademicStudent.student_code.asc().nullslast(), AcademicStudent.username.asc())
            .all()
        )
        all_components: list[dict[str, Any]] = []
        for _student, _membership, snapshot in rows:
            all_components.extend(academic._component_scores_from_snapshot(snapshot))
        quiz_schedule = academic._quiz_schedule_map_for_class(cls, all_components)
        policy_service = TrainingPolicyService(self.db)
        deadline_overrides = policy_service.deadline_overrides_for_class(class_id, course_id)
        assignment_scores = policy_service.assignment_scores_for_class(class_id, course_id)
        candidates: list[dict[str, Any]] = []
        no_learning_data_count = 0

        for student, membership, snapshot in rows:
            components = academic._enrich_component_scores_for_class(
                academic._component_scores_from_snapshot(snapshot),
                cls,
                quiz_schedule,
            )
            if not snapshot or not components:
                no_learning_data_count += 1
                continue
            policy = policy_service.evaluate_student(
                cls=cls,
                student_id=student.id,
                components=components,
                block=block,
                course_id=course_id,
                assignment_score=assignment_scores.get(student.id),
                overrides=deadline_overrides,
            )
            overdue_items = [
                item for item in (policy.get('quiz_results') or [])
                if isinstance(item, dict)
                and str(item.get('status') or '').strip() in _ACTIVE_OVERDUE_QUIZ_STATUSES
            ]
            # A learner who eventually reached 100% may still carry a historical
            # "completed late" marker, but is intentionally not reminded again.
            if not overdue_items:
                continue
            raw_email = normalize_recipient_email(student.email)
            last_synced_at = snapshot.learning_synced_at or snapshot.last_synced_at
            is_fresh = True
            if minimum_synced_at is not None:
                tolerance = minimum_synced_at - timedelta(seconds=2)
                is_fresh = bool(last_synced_at and last_synced_at >= tolerance)
            delivery_issue = None
            if not student.active:
                delivery_issue = 'inactive_student'
            elif raw_email is None:
                delivery_issue = 'missing_email'
            elif not is_fresh:
                delivery_issue = 'stale_after_refresh'
            candidates.append({
                'student_id': str(student.id),
                'student_code': student.student_code,
                'full_name': student.full_name,
                'masked_email': mask_recipient_email(raw_email),
                'private_email': raw_email,
                'progress_percent': academic._snapshot_progress_percent(snapshot),
                'grade_percent': academic._snapshot_grade_percent(snapshot),
                'overdue_quiz_count': len(overdue_items),
                'overdue_quizzes': [str(item.get('label') or f"Quiz {item.get('quiz_number')}") for item in overdue_items[:30]],
                'last_synced_at': last_synced_at,
                'deliverable': delivery_issue is None,
                'delivery_issue': delivery_issue,
                'total_relearn': academic._metadata_total_relearn(membership.metadata_json, student.metadata_json),
            })

        # De-duplicate by normalized recipient address. This prevents two stale AP
        # roster rows from producing two messages to the same learner mailbox.
        seen_emails: set[str] = set()
        for item in candidates:
            email = item.get('private_email')
            if not item.get('deliverable') or not email:
                continue
            if email in seen_emails:
                item['deliverable'] = False
                item['delivery_issue'] = 'duplicate_email'
            else:
                seen_emails.add(email)

        selected = set(selected_student_ids or set())
        selected_candidates = [item for item in candidates if not selected or item['student_id'] in selected]
        deliverable = [item for item in selected_candidates if item.get('deliverable')]
        issues: dict[str, int] = {}
        for item in selected_candidates:
            issue = str(item.get('delivery_issue') or '')
            if issue:
                issues[issue] = issues.get(issue, 0) + 1

        return {
            'class': cls,
            'subject': subject,
            'course_id': course_id,
            'roster_total': len(rows),
            'candidates': candidates,
            'selected_candidates': selected_candidates,
            'deliverable': deliverable,
            'issue_counts': issues,
            'no_learning_data_count': no_learning_data_count,
            'default_subject': self._default_subject(cls, subject),
            'default_body_template': self._default_body(cls, subject),
        }

    def preview(self, user: UserContext, class_id: str) -> dict[str, Any]:
        result = self._evaluate(user, class_id)
        cls: AcademicClass = result['class']
        subject: AcademicSubject | None = result['subject']
        public_items = [
            {key: value for key, value in item.items() if key != 'private_email'}
            for item in result['candidates']
        ]
        return {
            'class_id': str(cls.id),
            'class_code': cls.class_code,
            'subject_code': subject.subject_code if subject else None,
            'subject_name': subject.subject_name if subject else None,
            'openedx_course_id': result['course_id'],
            'generated_at': datetime.utcnow(),
            'mail_configured': self.mail_configured(),
            'max_recipients': max(1, min(1000, int(settings.mailsend_max_recipients or 1000))),
            'roster_total': result['roster_total'],
            'candidate_count': len(result['candidates']),
            'deliverable_count': len(result['deliverable']),
            'missing_email_count': int(result['issue_counts'].get('missing_email', 0)),
            'inactive_student_count': int(result['issue_counts'].get('inactive_student', 0)),
            'duplicate_email_count': int(result['issue_counts'].get('duplicate_email', 0)),
            'no_learning_data_count': result['no_learning_data_count'],
            'recipients': public_items,
            'default_subject': result['default_subject'],
            'default_body_template': result['default_body_template'],
            'refresh_before_send': True,
            'policy_note': (
                'Chỉ chọn sinh viên còn Quiz đã quá mốc tiến độ và chưa đạt 100%. '
                'Job gửi sẽ đồng bộ CMS lần cuối và tự loại người vừa bắt kịp.'
            ),
        }

    def resolve_selected_after_refresh(
        self,
        user: UserContext,
        class_id: str,
        *,
        selected_student_ids: set[str],
        minimum_synced_at: datetime,
    ) -> dict[str, Any]:
        result = self._evaluate(
            user,
            class_id,
            selected_student_ids=selected_student_ids,
            minimum_synced_at=minimum_synced_at,
        )
        current_candidate_ids = {item['student_id'] for item in result['selected_candidates']}
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
