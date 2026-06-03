import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, Integer, Float, Text, Index
from sqlalchemy.orm import Mapped, mapped_column
from app.db.session import Base


class GenerationJob(Base):
    __tablename__ = 'ai_generation_jobs'

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    course_id: Mapped[str] = mapped_column(String(255), index=True)
    lesson_id: Mapped[str | None] = mapped_column(String(512), nullable=True)
    topic: Mapped[str | None] = mapped_column(String(512), nullable=True)
    requested_by: Mapped[str] = mapped_column(String(255), default='teacher')
    question_count: Mapped[int] = mapped_column(Integer, default=10)
    batch_size: Mapped[int] = mapped_column(Integer, default=10)
    provider: Mapped[str] = mapped_column(String(50), default='openai')
    model_name: Mapped[str] = mapped_column(String(100), default='gpt-5-mini')
    status: Mapped[str] = mapped_column(String(50), default='pending')
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    # Estimate snapshot (before enqueue). estimated_cost_usd includes safety_factor for hard stop.
    estimated_input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    estimated_cached_input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    estimated_uncached_input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    estimated_output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    estimated_raw_cost_usd: Mapped[float] = mapped_column(Float, default=0)
    estimated_cost_usd: Mapped[float] = mapped_column(Float, default=0)
    estimated_cost_vnd: Mapped[float] = mapped_column(Float, default=0)
    estimate_token_source: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # v25.9.7: output-token calibration diagnostics. This makes clear whether
    # output estimate was learned from actual usage or a safe default.
    estimated_output_tokens_per_question: Mapped[float] = mapped_column(Float, default=0)
    output_calibration_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Actual usage snapshot (after model response). actual_cost_usd never uses safety_factor.
    actual_input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    actual_cached_input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    actual_uncached_input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    actual_output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    actual_output_tokens_per_question: Mapped[float] = mapped_column(Float, default=0)
    output_accuracy_percent: Mapped[float] = mapped_column(Float, default=0)
    output_delta_tokens: Mapped[int] = mapped_column(Integer, default=0)
    actual_cost_usd: Mapped[float] = mapped_column(Float, default=0)
    actual_cost_vnd: Mapped[float] = mapped_column(Float, default=0)
    usage_token_source: Mapped[str | None] = mapped_column(String(255), nullable=True)
    estimate_accuracy_percent: Mapped[float] = mapped_column(Float, default=0)
    completed_question_count: Mapped[int] = mapped_column(Integer, default=0)
    openai_response_ids: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_model_output_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_model_usage_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    model_parse_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index('ix_ai_generation_jobs_course_status_created', 'course_id', 'status', 'created_at'),
        Index('ix_ai_generation_jobs_course_requested_created', 'course_id', 'requested_by', 'created_at'),
        Index('uq_ai_generation_jobs_idempotency', 'course_id', 'requested_by', 'idempotency_key', unique=True),
    )
