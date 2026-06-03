import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, Integer, Float, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.db.session import Base


class GenerationBatch(Base):
    """One planned model call within a generation job.

    v25.9.8 adds controlled parallel GPT calls. A job can have many primary
    batches plus one delayed tail/recovery batch. Tracking at this level makes
    progress, retry, actual usage and partial failures explainable.
    """

    __tablename__ = 'ai_generation_batches'

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    job_id: Mapped[str] = mapped_column(String, index=True)
    course_id: Mapped[str] = mapped_column(String(255), index=True)
    batch_index: Mapped[int] = mapped_column(Integer, default=0)
    phase: Mapped[str] = mapped_column(String(50), default='primary')  # primary | tail | recovery | cache
    difficulty: Mapped[str | None] = mapped_column(String(50), nullable=True)
    difficulty_counts_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    requested_questions: Mapped[int] = mapped_column(Integer, default=0)
    completed_questions: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(50), default='queued')  # queued | running | completed | partial_completed | failed | parse_failed | cache_hit
    estimated_input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    estimated_output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    actual_input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    actual_cached_input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    actual_output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    actual_cost_usd: Mapped[float] = mapped_column(Float, default=0)
    token_source: Mapped[str | None] = mapped_column(String(255), nullable=True)
    openai_response_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    prompt_cache_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    generation_cache_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
