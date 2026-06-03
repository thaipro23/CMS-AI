import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, Text, Integer, JSON, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.db.session import Base


class GenerationCache(Base):
    """Internal output/recovery cache for model generations.

    This is NOT OpenAI prompt caching. It is an AI Server DB cache used to avoid
    paying again when the same generation payload is retried, and to preserve raw
    output when parsing fails after OpenAI has already billed the request.
    """

    __tablename__ = 'ai_generation_cache'
    __table_args__ = (
        UniqueConstraint('cache_key', name='uq_generation_cache_key'),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    cache_key: Mapped[str] = mapped_column(String(512), index=True)
    prompt_cache_key: Mapped[str | None] = mapped_column(String(512), nullable=True, index=True)
    course_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    source_node_id: Mapped[str | None] = mapped_column(String(512), nullable=True, index=True)
    chunk_hash: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    difficulty: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    question_count: Mapped[int] = mapped_column(Integer, default=0)
    prompt_version: Mapped[str] = mapped_column(String(100), default='v25_3_learning_check_json_schema_1')
    model_name: Mapped[str] = mapped_column(String(100), default='gpt-5-mini')
    raw_output_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    parsed_questions_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    question_hashes: Mapped[list | None] = mapped_column(JSON, nullable=True)
    response_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    parse_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cached_input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    hit_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
