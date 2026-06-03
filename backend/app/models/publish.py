import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, Integer, Text, JSON, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column
from app.db.session import Base


class PublishBatch(Base):
    __tablename__ = 'ai_publish_batches'

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    course_id: Mapped[str] = mapped_column(String(255), index=True)
    actor_id: Mapped[str] = mapped_column(String(255), default='teacher', index=True)
    mode: Mapped[str] = mapped_column(String(50), default='publish_new')
    status: Mapped[str] = mapped_column(String(50), default='running', index=True)
    total_questions: Mapped[int] = mapped_column(Integer, default=0)
    published_count: Mapped[int] = mapped_column(Integer, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, default=0)
    warning_count: Mapped[int] = mapped_column(Integer, default=0)
    summary_json: Mapped[dict | None] = mapped_column(JSON, nullable=True, default=dict)
    errors_json: Mapped[list | None] = mapped_column(JSON, nullable=True, default=list)
    idempotency_key: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    rollback_idempotency_key: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    __table_args__ = (
        Index('ix_ai_publish_batches_course_status_created', 'course_id', 'status', 'created_at'),
        Index('ix_ai_publish_batches_idempotency_lookup', 'course_id', 'actor_id', 'mode', 'idempotency_key'),
    )


class PublishBatchItem(Base):
    __tablename__ = 'ai_publish_batch_items'

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    batch_id: Mapped[str] = mapped_column(String, ForeignKey('ai_publish_batches.id'), index=True)
    question_id: Mapped[str] = mapped_column(String, ForeignKey('ai_questions.id'), index=True)
    course_id: Mapped[str] = mapped_column(String(255), index=True)
    library_key: Mapped[str | None] = mapped_column(String(512), nullable=True, index=True)
    difficulty: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    openedx_usage_key: Mapped[str | None] = mapped_column(String(512), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(50), default='pending', index=True)
    message: Mapped[str] = mapped_column(Text, default='')
    result_json: Mapped[dict | None] = mapped_column(JSON, nullable=True, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)

    __table_args__ = (
        Index('ix_ai_publish_items_course_status_created', 'course_id', 'status', 'created_at'),
        Index('ix_ai_publish_items_question_status', 'question_id', 'status'),
    )
