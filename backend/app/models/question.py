import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, Text, Integer, ForeignKey, Boolean, Float, JSON, Index
from sqlalchemy.orm import Mapped, mapped_column
from app.db.session import Base


class Question(Base):
    __tablename__ = 'ai_questions'

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    course_id: Mapped[str] = mapped_column(String(255), index=True)
    # v25.9.15 Question Bank-first architecture. These fields let one
    # approved question live in a versioned subject/chapter bank and later be
    # mapped into many Open edX courses. They are nullable for backward
    # compatibility with course-first generated questions.
    source_course_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    department_id: Mapped[str | None] = mapped_column(String, ForeignKey('ai_departments.id'), nullable=True, index=True)
    subject_id: Mapped[str | None] = mapped_column(String, ForeignKey('ai_subjects.id'), nullable=True, index=True)
    subject_chapter_id: Mapped[str | None] = mapped_column(String, ForeignKey('ai_subject_chapters.id'), nullable=True, index=True)
    bank_version_id: Mapped[str | None] = mapped_column(String, ForeignKey('ai_question_bank_versions.id'), nullable=True, index=True)
    bank_release_id: Mapped[str | None] = mapped_column(String, ForeignKey('ai_question_bank_releases.id'), nullable=True, index=True)
    material_version_id: Mapped[str | None] = mapped_column(String, ForeignKey('ai_learning_material_versions.id'), nullable=True, index=True)
    concept_version_id: Mapped[str | None] = mapped_column(String, ForeignKey('ai_concept_versions.id'), nullable=True, index=True)
    lesson_id: Mapped[str | None] = mapped_column(String(512), nullable=True)
    lesson_title: Mapped[str | None] = mapped_column(String(512), nullable=True)
    block_id: Mapped[str | None] = mapped_column(String(512), nullable=True, index=True)
    topic_id: Mapped[str | None] = mapped_column(String, ForeignKey('ai_topics.id'), nullable=True)
    topic: Mapped[str] = mapped_column(String(512), default='')
    concept_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    concept_title: Mapped[str | None] = mapped_column(String(512), nullable=True)
    concept_key: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    question_family_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    variant_no: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_evidence: Mapped[str] = mapped_column(Text, default='')
    difficulty: Mapped[str] = mapped_column(String(50), default='easy')
    cognitive_level: Mapped[str] = mapped_column(String(100), default='remember')
    learning_objective: Mapped[str] = mapped_column(Text, default='')
    question_type: Mapped[str] = mapped_column(String(50), default='single_choice')
    question_text: Mapped[str] = mapped_column(Text)
    # v25.3 deterministic duplicate fingerprint. Prevents exact duplicate
    # questions from being inserted when a retry/cache hit returns the same item.
    question_hash: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    option_a: Mapped[str] = mapped_column(Text)
    option_b: Mapped[str] = mapped_column(Text)
    option_c: Mapped[str] = mapped_column(Text)
    option_d: Mapped[str] = mapped_column(Text)
    correct_answer: Mapped[str] = mapped_column(String(1))
    explanation: Mapped[str] = mapped_column(Text, default='')
    source_ref: Mapped[str] = mapped_column(String(1024), default='')
    source_type: Mapped[str] = mapped_column(String(100), default='course_component')
    source_page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_timestamp_start: Mapped[str | None] = mapped_column(String(50), nullable=True)
    source_timestamp_end: Mapped[str | None] = mapped_column(String(50), nullable=True)
    source_chunk_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    # v24: original Open edX node/component. Unit Problem Bank filters/randomizes by this field.
    source_node_id: Mapped[str | None] = mapped_column(String(512), nullable=True, index=True)
    source_node_title: Mapped[str | None] = mapped_column(String(512), nullable=True)
    chapter_node_id: Mapped[str | None] = mapped_column(String(512), nullable=True, index=True)
    chapter_title: Mapped[str | None] = mapped_column(String(512), nullable=True)
    target_library_id: Mapped[str | None] = mapped_column(String, ForeignKey('ai_course_libraries.id'), nullable=True, index=True)
    target_library_key: Mapped[str | None] = mapped_column(String(512), nullable=True, index=True)
    source_excerpt: Mapped[str] = mapped_column(Text, default='')
    tags: Mapped[list | None] = mapped_column(JSON, nullable=True, default=list)
    ai_rationale: Mapped[str] = mapped_column(Text, default='')
    quality_score: Mapped[float] = mapped_column(Float, default=0.0)
    quality_flags: Mapped[list | None] = mapped_column(JSON, nullable=True, default=list)
    # v25.5 explicit draft error reason for UI Repair Center.
    draft_error_reason: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    draft_error_detail: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    repair_attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    is_duplicate: Mapped[bool] = mapped_column(Boolean, default=False)
    duplicate_of_question_id: Mapped[str | None] = mapped_column(String, nullable=True)
    duplicate_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    generation_job_id: Mapped[str | None] = mapped_column(String, ForeignKey('ai_generation_jobs.id'), nullable=True, index=True)
    model_provider: Mapped[str] = mapped_column(String(100), default='openai')
    model_name: Mapped[str] = mapped_column(String(100), default='gpt-5-mini')
    status: Mapped[str] = mapped_column(String(50), default='draft', index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    reviewed_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    openedx_block_id: Mapped[str | None] = mapped_column(String(512), nullable=True, index=True)
    openedx_library_problem_id: Mapped[str | None] = mapped_column(String(512), nullable=True, index=True)
    imported_library_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    publish_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    # v25.7 publish verification / dry-run state.
    publish_status: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    publish_verification_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    published_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # v25.9.13.42: split teacher review status from Open edX lifecycle state.
    # Keep legacy status/publish_status for backwards-compatible API/UI, but write
    # explicit fields so dashboards and rollback flows no longer infer semantics
    # from one overloaded string.
    openedx_publish_status: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    openedx_verification_status: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    openedx_delete_status: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    openedx_manual_action_required: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index('ix_ai_questions_course_status_created', 'course_id', 'status', 'created_at'),
        Index('ix_ai_questions_course_source_status_created', 'course_id', 'source_node_id', 'status', 'created_at'),
        Index('ix_ai_questions_course_publish_created', 'course_id', 'publish_status', 'created_at'),
        Index('ix_ai_questions_course_openedx_lifecycle', 'course_id', 'openedx_publish_status', 'openedx_verification_status', 'openedx_delete_status'),
        Index('ix_ai_questions_course_concept_status', 'course_id', 'concept_id', 'status'),
        Index('ix_ai_questions_course_family_status', 'course_id', 'question_family_id', 'status'),
        Index('ix_ai_questions_course_chapter_family_difficulty', 'course_id', 'chapter_node_id', 'question_family_id', 'difficulty'),
        Index('ix_ai_questions_bank_version_status', 'bank_version_id', 'status'),
        Index('ix_ai_questions_subject_chapter_status', 'subject_id', 'subject_chapter_id', 'status'),
        Index('ix_ai_questions_bank_release_status', 'bank_release_id', 'status'),
    )


class QuestionReviewLog(Base):
    __tablename__ = 'ai_question_review_logs'

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    question_id: Mapped[str] = mapped_column(String, ForeignKey('ai_questions.id'), index=True)
    old_status: Mapped[str] = mapped_column(String(50))
    new_status: Mapped[str] = mapped_column(String(50))
    actor: Mapped[str] = mapped_column(String(255), default='system')
    note: Mapped[str] = mapped_column(Text, default='')
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class QuestionVersion(Base):
    __tablename__ = 'ai_question_versions'

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    question_id: Mapped[str] = mapped_column(String, ForeignKey('ai_questions.id'), index=True)
    version: Mapped[int] = mapped_column(Integer)
    actor: Mapped[str] = mapped_column(String(255), default='teacher')
    note: Mapped[str] = mapped_column(Text, default='')
    snapshot: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class QuestionEmbedding(Base):
    __tablename__ = 'ai_question_embeddings'

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    question_id: Mapped[str] = mapped_column(String, ForeignKey('ai_questions.id'), index=True, unique=True)
    course_id: Mapped[str] = mapped_column(String(255), index=True)
    topic_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    question_text: Mapped[str] = mapped_column(Text)
    # v25.3 deterministic duplicate fingerprint. Prevents exact duplicate
    # questions from being inserted when a retry/cache hit returns the same item.
    question_hash: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    embedding_vector: Mapped[list | None] = mapped_column(JSON, nullable=True, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index('ix_ai_question_embeddings_course_topic_created', 'course_id', 'topic_id', 'created_at'),
        Index('ix_ai_question_embeddings_course_hash', 'course_id', 'question_hash'),
    )
