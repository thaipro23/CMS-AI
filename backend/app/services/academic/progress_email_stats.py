from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Iterable

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.academic import (
    AcademicBulkOperationJob,
    AcademicClass,
    AcademicTeacherAssignment,
)


@dataclass
class AcademicProgressEmailStats:
    class_sent_count: dict[str, int] = field(default_factory=dict)
    class_last_sent_at: dict[str, datetime] = field(default_factory=dict)
    student_sent_count: dict[tuple[str, str], int] = field(default_factory=dict)
    student_last_sent_at: dict[tuple[str, str], datetime] = field(default_factory=dict)
    teacher_sent_count: dict[str, int] = field(default_factory=dict)


def _clean_ids(values: Iterable[str]) -> set[str]:
    return {str(value).strip() for value in values if str(value or '').strip()}


def _latest(current: datetime | None, candidate: datetime | None) -> datetime | None:
    if candidate is None:
        return current
    if current is None or candidate > current:
        return candidate
    return current


class AcademicProgressEmailStatsService:
    """Read-only aggregation over durable progress-reminder Mail Send evidence."""

    def __init__(self, db: Session):
        self.db = db

    def for_classes(
        self,
        class_ids: Iterable[str],
        *,
        term_id: str | None = None,
        branch: str | None = None,
        campus: str | None = None,
    ) -> AcademicProgressEmailStats:
        requested_class_ids = _clean_ids(class_ids)
        stats = AcademicProgressEmailStats()
        if not requested_class_ids:
            return stats

        query = self.db.query(AcademicBulkOperationJob).filter(
            AcademicBulkOperationJob.job_type == 'progress_reminder_email',
        )
        if term_id:
            query = query.filter(AcademicBulkOperationJob.term_id == str(term_id))
        if branch:
            query = query.filter(
                func.lower(AcademicBulkOperationJob.branch) == str(branch).strip().lower()
            )
        if campus:
            query = query.filter(
                func.lower(AcademicBulkOperationJob.campus) == str(campus).strip().lower()
            )

        for job in query.all():
            request = job.request_json if isinstance(job.request_json, dict) else {}
            class_id = str(request.get('class_id') or '').strip()
            if class_id not in requested_class_ids:
                continue
            result = job.result_json if isinstance(job.result_json, dict) else {}
            if result.get('mail_send_confirmed') is not True:
                continue

            try:
                sent_count = max(0, int(result.get('sent_count') or 0))
            except (TypeError, ValueError):
                sent_count = 0
            confirmed_at = job.finished_at or job.updated_at
            if sent_count:
                stats.class_sent_count[class_id] = (
                    stats.class_sent_count.get(class_id, 0) + sent_count
                )
                latest = _latest(stats.class_last_sent_at.get(class_id), confirmed_at)
                if latest is not None:
                    stats.class_last_sent_at[class_id] = latest

            deliveries = result.get('mail_send_deliveries')
            if not isinstance(deliveries, list):
                continue
            for delivery in deliveries:
                if not isinstance(delivery, dict):
                    continue
                if str(delivery.get('provider_state') or '').upper() != 'TERMINAL':
                    continue
                if str(delivery.get('status') or '').upper() != 'COMPLETED':
                    continue
                student_id = str(delivery.get('student_id') or '').strip()
                if not student_id:
                    continue
                try:
                    delivery_sent = max(0, int(delivery.get('sent_count') or 0))
                    delivery_failed = max(0, int(delivery.get('failed_count') or 0))
                except (TypeError, ValueError):
                    continue
                if delivery_sent <= 0 and delivery_failed <= 0:
                    # Each personalized provider session targets one student.
                    # Older provider responses may omit sentCount on COMPLETED.
                    delivery_sent = 1
                if delivery_sent <= 0:
                    continue
                key = (class_id, student_id)
                stats.student_sent_count[key] = (
                    stats.student_sent_count.get(key, 0) + delivery_sent
                )
                latest = _latest(stats.student_last_sent_at.get(key), confirmed_at)
                if latest is not None:
                    stats.student_last_sent_at[key] = latest
        return stats

    def for_teachers(
        self,
        teacher_ids: Iterable[str],
        *,
        term_id: str | None = None,
        branch: str | None = None,
        campus: str | None = None,
    ) -> AcademicProgressEmailStats:
        requested_teacher_ids = _clean_ids(teacher_ids)
        if not requested_teacher_ids:
            return AcademicProgressEmailStats()

        query = self.db.query(
            AcademicTeacherAssignment.teacher_id,
            AcademicTeacherAssignment.class_id,
        ).join(
            AcademicClass,
            AcademicClass.id == AcademicTeacherAssignment.class_id,
        ).filter(
            AcademicTeacherAssignment.teacher_id.in_(requested_teacher_ids),
            AcademicClass.active.is_(True),
        )
        if term_id:
            query = query.filter(AcademicClass.term_id == str(term_id))
        if branch:
            query = query.filter(
                func.lower(AcademicClass.branch) == str(branch).strip().lower()
            )
        if campus:
            query = query.filter(
                func.lower(AcademicClass.campus) == str(campus).strip().lower()
            )

        classes_by_teacher: dict[str, set[str]] = {
            teacher_id: set() for teacher_id in requested_teacher_ids
        }
        for teacher_id, class_id in query.all():
            classes_by_teacher.setdefault(str(teacher_id), set()).add(str(class_id))
        class_ids = set().union(*classes_by_teacher.values()) if classes_by_teacher else set()
        stats = self.for_classes(
            class_ids,
            term_id=term_id,
            branch=branch,
            campus=campus,
        )
        stats.teacher_sent_count = {
            teacher_id: sum(
                stats.class_sent_count.get(class_id, 0)
                for class_id in assigned_class_ids
            )
            for teacher_id, assigned_class_ids in classes_by_teacher.items()
        }
        return stats
