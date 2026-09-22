from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, update
from sqlalchemy.orm import Session

from app.models.academic import AcademicClassSyncJob


def claim_class_sync_job(
    db: Session,
    job_id: str,
    *,
    now: datetime | None = None,
) -> AcademicClassSyncJob | None:
    """Atomically claim one queued class-sync job for execution."""
    claimed_at = now or datetime.utcnow()
    statement = (
        update(AcademicClassSyncJob)
        .where(
            AcademicClassSyncJob.id == job_id,
            AcademicClassSyncJob.status == 'queued',
        )
        .values(
            status='running',
            started_at=func.coalesce(
                AcademicClassSyncJob.started_at,
                claimed_at,
            ),
            updated_at=claimed_at,
        )
        .returning(AcademicClassSyncJob.id)
    )
    claimed_id = db.execute(statement).scalar_one_or_none()
    if claimed_id is None:
        db.rollback()
        return None
    db.commit()
    return db.get(AcademicClassSyncJob, claimed_id)
