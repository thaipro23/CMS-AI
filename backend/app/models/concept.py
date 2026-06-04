import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, Integer, Float, Text, JSON, UniqueConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column
from app.db.session import Base


class Concept(Base):
    """A teachable knowledge point extracted from synced course content.

    v25.9.14.0: Concepts are the pedagogy layer between raw chunks and
    generated question variants.  A concept should represent one distinct
    learning issue/objective, not one random sentence.
    """

    __tablename__ = 'ai_concepts'

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    course_id: Mapped[str] = mapped_column(String(255), index=True)
    chapter_node_id: Mapped[str | None] = mapped_column(String(512), nullable=True, index=True)
    source_node_id: Mapped[str | None] = mapped_column(String(512), nullable=True, index=True)
    source_node_title: Mapped[str | None] = mapped_column(String(512), nullable=True)
    concept_key: Mapped[str] = mapped_column(String(255), index=True)
    title: Mapped[str] = mapped_column(String(512), default='')
    summary: Mapped[str] = mapped_column(Text, default='')
    learning_objective: Mapped[str] = mapped_column(Text, default='')
    difficulty_hint: Mapped[str] = mapped_column(String(50), default='easy', index=True)
    importance_score: Mapped[float] = mapped_column(Float, default=0.5)
    source_chunk_ids: Mapped[list | None] = mapped_column(JSON, nullable=True, default=list)
    source_evidence: Mapped[str] = mapped_column(Text, default='')
    token_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(50), default='active', index=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint('course_id', 'source_node_id', 'concept_key', name='uq_ai_concepts_course_node_key'),
        Index('ix_ai_concepts_course_node_status', 'course_id', 'source_node_id', 'status'),
        Index('ix_ai_concepts_course_chapter_difficulty', 'course_id', 'chapter_node_id', 'difficulty_hint'),
    )
