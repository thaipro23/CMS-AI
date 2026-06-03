import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, Text, JSON
from sqlalchemy.orm import Mapped, mapped_column
from app.db.session import Base


class AuditLog(Base):
    __tablename__ = 'ai_audit_logs'

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    course_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    actor_id: Mapped[str] = mapped_column(String(255), default='system', index=True)
    actor_role: Mapped[str | None] = mapped_column(String(50), nullable=True)
    action: Mapped[str] = mapped_column(String(120), index=True)
    target_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    target_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(50), default='success', index=True)
    error_type: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    message: Mapped[str] = mapped_column(Text, default='')
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
