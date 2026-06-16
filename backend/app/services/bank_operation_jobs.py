from __future__ import annotations

import json
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.question_bank import BankOperationJob


TERMINAL_STATUSES = {'completed', 'failed', 'canceled'}


def operation_pending_dir() -> Path:
    root = Path(settings.local_storage_path or '/app/.runtime')
    path = root / 'question-bank' / '_pending-operation-files'
    path.mkdir(parents=True, exist_ok=True)
    return path


def serialize_job(job: BankOperationJob) -> dict[str, Any]:
    return {
        'id': job.id,
        'operation_type': job.operation_type,
        'status': job.status,
        'target_type': job.target_type,
        'target_id': job.target_id,
        'bank_version_id': job.bank_version_id,
        'release_id': job.release_id,
        'material_version_id': job.material_version_id,
        'course_quiz_instance_id': job.course_quiz_instance_id,
        'requested_by': job.requested_by,
        'course_id': job.course_id,
        'progress_current': int(job.progress_current or 0),
        'progress_total': int(job.progress_total or 1),
        'progress_percent': round((int(job.progress_current or 0) / max(int(job.progress_total or 1), 1)) * 100, 2),
        'progress_label': job.progress_label,
        'request': job.request_json or {},
        'result': job.result_json or {},
        'error_message': job.error_message,
        'created_at': job.created_at,
        'started_at': job.started_at,
        'finished_at': job.finished_at,
        'updated_at': job.updated_at,
    }


class BankOperationJobService:
    def __init__(self, db: Session):
        self.db = db

    def create_job(
        self,
        *,
        operation_type: str,
        target_type: str,
        target_id: str | None = None,
        requested_by: str | None = None,
        bank_version_id: str | None = None,
        release_id: str | None = None,
        course_id: str | None = None,
        request_json: dict | None = None,
        progress_total: int = 1,
        progress_label: str = 'Đang chờ xử lý',
        commit: bool = True,
    ) -> BankOperationJob:
        job = BankOperationJob(
            operation_type=operation_type,
            status='queued',
            target_type=target_type,
            target_id=target_id,
            requested_by=requested_by,
            bank_version_id=bank_version_id,
            release_id=release_id,
            course_id=course_id,
            progress_current=0,
            progress_total=max(1, int(progress_total or 1)),
            progress_label=progress_label,
            request_json=request_json or {},
            result_json={},
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        self.db.add(job)
        if commit:
            self.db.commit()
            self.db.refresh(job)
        return job

    def get_job(self, job_id: str) -> BankOperationJob | None:
        return self.db.get(BankOperationJob, job_id)

    def start(self, job: BankOperationJob, *, label: str = 'Đang xử lý', total: int | None = None) -> BankOperationJob:
        job.status = 'running'
        job.started_at = job.started_at or datetime.utcnow()
        job.updated_at = datetime.utcnow()
        job.progress_current = max(1, int(job.progress_current or 0))
        if total is not None:
            job.progress_total = max(1, int(total or 1))
        job.progress_label = label
        self.db.commit()
        self.db.refresh(job)
        return job

    def progress(self, job: BankOperationJob, *, current: int | None = None, total: int | None = None, label: str | None = None, commit: bool = True) -> BankOperationJob:
        if current is not None:
            job.progress_current = max(0, int(current))
        if total is not None:
            job.progress_total = max(1, int(total))
        if label:
            job.progress_label = label
        job.updated_at = datetime.utcnow()
        if commit:
            self.db.commit()
            self.db.refresh(job)
        return job

    def complete(self, job: BankOperationJob, *, result: dict | None = None, label: str = 'Hoàn thành') -> BankOperationJob:
        job.status = 'completed'
        job.progress_current = max(int(job.progress_total or 1), int(job.progress_current or 0))
        job.progress_label = label
        job.result_json = result or {}
        # hydrate common foreign keys for easy filtering after the worker returns.
        if result:
            job.material_version_id = result.get('material_version_id') or result.get('material_version', {}).get('id') or job.material_version_id
            job.course_quiz_instance_id = result.get('course_quiz_instance_id') or job.course_quiz_instance_id
            job.course_id = result.get('openedx_course_id') or result.get('course_id') or job.course_id
        job.error_message = None
        job.finished_at = datetime.utcnow()
        job.updated_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(job)
        return job

    def fail(self, job: BankOperationJob, *, error: Exception | str, result: dict | None = None) -> BankOperationJob:
        message = str(error)
        job.status = 'failed'
        job.error_message = message[:4000]
        job.progress_label = 'Thất bại'
        job.result_json = result or {'error': message, 'traceback_tail': traceback.format_exc(limit=8)}
        job.finished_at = datetime.utcnow()
        job.updated_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(job)
        return job

    def cancel(self, job: BankOperationJob, *, reason: str = 'Đã hủy') -> BankOperationJob:
        if job.status in TERMINAL_STATUSES:
            return job
        job.status = 'canceled'
        job.error_message = reason
        job.progress_label = reason
        job.finished_at = datetime.utcnow()
        job.updated_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(job)
        return job
