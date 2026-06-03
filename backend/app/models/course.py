import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, Integer, Text, ForeignKey, UniqueConstraint, JSON, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.session import Base


class CourseSyncState(Base):
    __tablename__ = 'ai_course_sync_state'

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    course_id: Mapped[str] = mapped_column(String(255), index=True)
    block_id: Mapped[str] = mapped_column(String(512), index=True)
    parent_block_id: Mapped[str | None] = mapped_column(String(512), nullable=True)
    block_type: Mapped[str] = mapped_column(String(50))
    display_name: Mapped[str] = mapped_column(String(512), default='')
    content_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    sync_status: Mapped[str] = mapped_column(String(50), default='pending')
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint('course_id', 'block_id', name='uq_course_block'),
        Index('ix_ai_course_sync_course_parent_type', 'course_id', 'parent_block_id', 'block_type'),
        Index('ix_ai_course_sync_course_status_synced', 'course_id', 'sync_status', 'last_synced_at'),
    )


class ContentChunk(Base):
    __tablename__ = 'ai_content_chunks'

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    course_id: Mapped[str] = mapped_column(String(255), index=True)
    block_id: Mapped[str] = mapped_column(String(512), index=True)
    topic_id: Mapped[str | None] = mapped_column(String, ForeignKey('ai_topics.id'), nullable=True)
    content: Mapped[str] = mapped_column(Text)
    token_count: Mapped[int] = mapped_column(Integer, default=0)
    source_type: Mapped[str] = mapped_column(String(50), default='unknown')
    page_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    timestamp_start: Mapped[str | None] = mapped_column(String(50), nullable=True)
    timestamp_end: Mapped[str | None] = mapped_column(String(50), nullable=True)
    source_ref: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index('ix_ai_content_chunks_course_block_created', 'course_id', 'block_id', 'created_at'),
        Index('ix_ai_content_chunks_course_source_created', 'course_id', 'source_type', 'created_at'),
        Index('ix_ai_content_chunks_course_topic', 'course_id', 'topic_id'),
    )


class Topic(Base):
    __tablename__ = 'ai_topics'

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    course_id: Mapped[str] = mapped_column(String(255), index=True)
    lesson_id: Mapped[str | None] = mapped_column(String(512), nullable=True)
    title: Mapped[str] = mapped_column(String(512))
    summary: Mapped[str] = mapped_column(Text, default='')
    importance_score: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    __table_args__ = (Index('ix_ai_topics_course_importance', 'course_id', 'importance_score'),)


class CourseLibrary(Base):
    """One AI/Open edX Problem Bank library per Chapter/Module.

    v24: Course has many libraries by Chapter/Module, not one global library and not one library per Unit.
    """

    __tablename__ = 'ai_course_libraries'

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    course_id: Mapped[str] = mapped_column(String(255), index=True)
    chapter_node_id: Mapped[str] = mapped_column(String(512), index=True)
    chapter_title: Mapped[str] = mapped_column(String(512), default='')
    difficulty: Mapped[str] = mapped_column(String(50), default='easy', index=True)
    library_key: Mapped[str] = mapped_column(String(512), index=True)
    display_name: Mapped[str] = mapped_column(String(512), default='')
    openedx_library_id: Mapped[str | None] = mapped_column(String(512), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(50), default='local_ready')
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint('course_id', 'chapter_node_id', 'difficulty', name='uq_course_chapter_difficulty_library'),
        Index('ix_ai_course_libraries_course_difficulty_status', 'course_id', 'difficulty', 'status'),
    )
