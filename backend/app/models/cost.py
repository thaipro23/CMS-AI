import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, Float, Integer, Text, Boolean, Index
from sqlalchemy.orm import Mapped, mapped_column
from app.db.session import Base


class BudgetPolicy(Base):
    __tablename__ = 'ai_budget_policy'

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    scope: Mapped[str] = mapped_column(String(50), default='course')
    scope_id: Mapped[str] = mapped_column(String(255), default='default')
    monthly_budget_usd: Mapped[float] = mapped_column(Float, default=10.0)
    max_questions_per_course: Mapped[int] = mapped_column(Integer, default=200)
    max_questions_per_job: Mapped[int] = mapped_column(Integer, default=50)
    max_retry: Mapped[int] = mapped_column(Integer, default=2)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class UsageLog(Base):
    __tablename__ = 'ai_usage_log'

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    job_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    course_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    user_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    feature: Mapped[str] = mapped_column(String(100), default='generate_questions')
    model_provider: Mapped[str] = mapped_column(String(100), default='openai')
    model_name: Mapped[str] = mapped_column(String(100), default='gpt-5-mini')
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cached_input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    uncached_input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, default=0)
    cost_vnd: Mapped[float] = mapped_column(Float, default=0)
    status: Mapped[str] = mapped_column(String(50), default='completed')
    token_source: Mapped[str | None] = mapped_column(String(255), nullable=True)
    raw_usage_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index('ix_ai_usage_log_course_feature_created', 'course_id', 'feature', 'created_at'),
        Index('ix_ai_usage_log_course_model_created', 'course_id', 'model_provider', 'model_name', 'created_at'),
        Index('ix_ai_usage_log_course_user_created', 'course_id', 'user_id', 'created_at'),
    )


class CostAlert(Base):
    __tablename__ = 'ai_cost_alert'

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    scope: Mapped[str] = mapped_column(String(50))
    scope_id: Mapped[str] = mapped_column(String(255))
    threshold_percent: Mapped[int] = mapped_column(Integer)
    message: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
