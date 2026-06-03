import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, Integer, Float, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.db.session import Base


class TokenCalibration(Base):
    """Rolling output-token calibration for generation estimates.

    OpenAI can count input before a request, but output tokens can only be
    projected.  This table stores actual output tokens/question by model,
    course, difficulty and prompt version so the next estimate is based on
    real usage instead of a fixed constant like 320 tokens/question.
    """

    __tablename__ = 'ai_token_calibration'
    __table_args__ = (
        UniqueConstraint('model_name', 'course_id', 'difficulty', 'question_type', 'prompt_version', name='uq_token_calibration_scope'),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    model_name: Mapped[str] = mapped_column(String(100), default='gpt-5-mini')
    course_id: Mapped[str] = mapped_column(String(255), default='global')
    difficulty: Mapped[str] = mapped_column(String(50), default='mixed')
    question_type: Mapped[str] = mapped_column(String(50), default='single_choice')
    prompt_version: Mapped[str] = mapped_column(String(100), default='v25_3_learning_check_json_schema_1')
    avg_output_tokens_per_question: Mapped[float] = mapped_column(Float, default=750.0)
    min_output_tokens_per_question: Mapped[float] = mapped_column(Float, default=0.0)
    max_output_tokens_per_question: Mapped[float] = mapped_column(Float, default=0.0)
    sample_count: Mapped[int] = mapped_column(Integer, default=0)
    last_actual_output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    last_question_count: Mapped[int] = mapped_column(Integer, default=0)
    last_observed_tokens_per_question: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
