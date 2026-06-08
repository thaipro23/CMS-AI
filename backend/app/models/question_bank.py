import uuid
from datetime import datetime
from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.db.session import Base


class Department(Base):
    __tablename__ = 'ai_departments'

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text, default='')
    status: Mapped[str] = mapped_column(String(50), default='active', index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Subject(Base):
    __tablename__ = 'ai_subjects'

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    department_id: Mapped[str] = mapped_column(String, ForeignKey('ai_departments.id'), index=True)
    code: Mapped[str] = mapped_column(String(64), index=True)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text, default='')
    status: Mapped[str] = mapped_column(String(50), default='active', index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint('department_id', 'code', name='uq_ai_subject_department_code'),
        Index('ix_ai_subjects_department_status', 'department_id', 'status'),
    )


class SubjectChapter(Base):
    __tablename__ = 'ai_subject_chapters'

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    subject_id: Mapped[str] = mapped_column(String, ForeignKey('ai_subjects.id'), index=True)
    chapter_no: Mapped[int] = mapped_column(Integer, default=1)
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text, default='')
    sort_order: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(50), default='active', index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint('subject_id', 'chapter_no', name='uq_ai_subject_chapter_no'),
        Index('ix_ai_subject_chapters_subject_status', 'subject_id', 'status'),
    )


class QuestionBankVersion(Base):
    __tablename__ = 'ai_question_bank_versions'

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    subject_id: Mapped[str] = mapped_column(String, ForeignKey('ai_subjects.id'), index=True)
    chapter_id: Mapped[str] = mapped_column(String, ForeignKey('ai_subject_chapters.id'), index=True)
    version_no: Mapped[int] = mapped_column(Integer, default=1)
    version_code: Mapped[str] = mapped_column(String(64), default='v1.0')
    title: Mapped[str] = mapped_column(String(255), default='')
    change_note: Mapped[str] = mapped_column(Text, default='')
    status: Mapped[str] = mapped_column(String(50), default='draft', index=True)  # draft | reviewing | approved | published | archived
    based_on_version_id: Mapped[str | None] = mapped_column(String, ForeignKey('ai_question_bank_versions.id'), nullable=True, index=True)
    created_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    approved_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint('subject_id', 'chapter_id', 'version_code', name='uq_ai_bank_version_code'),
        Index('ix_ai_bank_versions_chapter_status', 'chapter_id', 'status'),
    )


class LearningMaterialVersion(Base):
    __tablename__ = 'ai_learning_material_versions'

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    subject_id: Mapped[str] = mapped_column(String, ForeignKey('ai_subjects.id'), index=True)
    chapter_id: Mapped[str] = mapped_column(String, ForeignKey('ai_subject_chapters.id'), index=True)
    bank_version_id: Mapped[str] = mapped_column(String, ForeignKey('ai_question_bank_versions.id'), index=True)
    title: Mapped[str] = mapped_column(String(255), default='')
    file_name: Mapped[str] = mapped_column(String(512), default='')
    file_type: Mapped[str] = mapped_column(String(100), default='unknown')
    storage_path: Mapped[str] = mapped_column(String(1024), default='')
    content_hash: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    version_no: Mapped[int] = mapped_column(Integer, default=1)
    change_type: Mapped[str] = mapped_column(String(50), default='initial')
    uploaded_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(50), default='active', index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index('ix_ai_material_versions_bank_hash', 'bank_version_id', 'content_hash'),
    )


class ConceptVersion(Base):
    __tablename__ = 'ai_concept_versions'

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    bank_version_id: Mapped[str] = mapped_column(String, ForeignKey('ai_question_bank_versions.id'), index=True)
    subject_id: Mapped[str] = mapped_column(String, ForeignKey('ai_subjects.id'), index=True)
    chapter_id: Mapped[str] = mapped_column(String, ForeignKey('ai_subject_chapters.id'), index=True)
    material_version_id: Mapped[str | None] = mapped_column(String, ForeignKey('ai_learning_material_versions.id'), nullable=True, index=True)
    concept_key: Mapped[str] = mapped_column(String(255), index=True)
    concept_title: Mapped[str] = mapped_column(String(512))
    description: Mapped[str] = mapped_column(Text, default='')
    learning_objective: Mapped[str] = mapped_column(Text, default='')
    source_evidence: Mapped[str] = mapped_column(Text, default='')
    source_chunk_hash: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(50), default='active', index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint('bank_version_id', 'concept_key', name='uq_ai_concept_version_key'),
        Index('ix_ai_concept_versions_bank_status', 'bank_version_id', 'status'),
    )


class BankQuestionFamily(Base):
    __tablename__ = 'ai_bank_question_families'

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    bank_version_id: Mapped[str] = mapped_column(String, ForeignKey('ai_question_bank_versions.id'), index=True)
    subject_id: Mapped[str] = mapped_column(String, ForeignKey('ai_subjects.id'), index=True)
    chapter_id: Mapped[str] = mapped_column(String, ForeignKey('ai_subject_chapters.id'), index=True)
    concept_version_id: Mapped[str | None] = mapped_column(String, ForeignKey('ai_concept_versions.id'), nullable=True, index=True)
    difficulty: Mapped[str] = mapped_column(String(50), default='easy', index=True)
    family_key: Mapped[str] = mapped_column(String(255), index=True)
    family_title: Mapped[str] = mapped_column(String(512), default='')
    family_fingerprint: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(50), default='active', index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint('bank_version_id', 'difficulty', 'family_key', name='uq_ai_bank_family_key'),
        Index('ix_ai_bank_families_bank_difficulty_status', 'bank_version_id', 'difficulty', 'status'),
    )


class QuestionBankRelease(Base):
    __tablename__ = 'ai_question_bank_releases'

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    bank_version_id: Mapped[str] = mapped_column(String, ForeignKey('ai_question_bank_versions.id'), index=True)
    subject_id: Mapped[str] = mapped_column(String, ForeignKey('ai_subjects.id'), index=True)
    chapter_id: Mapped[str] = mapped_column(String, ForeignKey('ai_subject_chapters.id'), index=True)
    release_code: Mapped[str] = mapped_column(String(128), index=True)
    title: Mapped[str] = mapped_column(String(255), default='')
    status: Mapped[str] = mapped_column(String(50), default='draft', index=True)  # draft | published | deprecated | archived
    approved_question_count: Mapped[int] = mapped_column(Integer, default=0)
    easy_count: Mapped[int] = mapped_column(Integer, default=0)
    medium_count: Mapped[int] = mapped_column(Integer, default=0)
    hard_count: Mapped[int] = mapped_column(Integer, default=0)
    family_count: Mapped[int] = mapped_column(Integer, default=0)
    openedx_library_key: Mapped[str | None] = mapped_column(String(512), nullable=True, index=True)
    openedx_library_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    publish_batch_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    published_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint('bank_version_id', 'release_code', name='uq_ai_bank_release_code'),
        UniqueConstraint('openedx_library_key', name='uq_ai_bank_release_openedx_library_key'),
        Index('ix_ai_bank_releases_chapter_status', 'chapter_id', 'status'),
    )


class BankReleaseQuestion(Base):
    __tablename__ = 'ai_bank_release_questions'

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    bank_release_id: Mapped[str] = mapped_column(String, ForeignKey('ai_question_bank_releases.id'), index=True)
    question_id: Mapped[str] = mapped_column(String, ForeignKey('ai_questions.id'), index=True)
    question_family_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    difficulty: Mapped[str] = mapped_column(String(50), default='easy', index=True)
    openedx_library_problem_id: Mapped[str | None] = mapped_column(String(512), nullable=True, index=True)
    included_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint('bank_release_id', 'question_id', name='uq_ai_release_question'),
        UniqueConstraint('bank_release_id', 'openedx_library_problem_id', name='uq_ai_release_openedx_problem'),
        Index('ix_ai_release_questions_release_family', 'bank_release_id', 'question_family_id'),
    )


class EdxCourseMapping(Base):
    __tablename__ = 'ai_edx_course_mappings'

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    openedx_course_id: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    department_id: Mapped[str | None] = mapped_column(String, ForeignKey('ai_departments.id'), nullable=True, index=True)
    subject_id: Mapped[str] = mapped_column(String, ForeignKey('ai_subjects.id'), index=True)
    term: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(50), default='active', index=True)
    created_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class EdxCourseChapterMapping(Base):
    __tablename__ = 'ai_edx_course_chapter_mappings'

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    course_mapping_id: Mapped[str] = mapped_column(String, ForeignKey('ai_edx_course_mappings.id'), index=True)
    subject_chapter_id: Mapped[str] = mapped_column(String, ForeignKey('ai_subject_chapters.id'), index=True)
    bank_release_id: Mapped[str | None] = mapped_column(String, ForeignKey('ai_question_bank_releases.id'), nullable=True, index=True)
    openedx_parent_node_id: Mapped[str | None] = mapped_column(String(512), nullable=True, index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint('course_mapping_id', 'subject_chapter_id', name='uq_ai_course_chapter_mapping'),
    )


class QuizBlueprint(Base):
    __tablename__ = 'ai_quiz_blueprints'

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    subject_id: Mapped[str] = mapped_column(String, ForeignKey('ai_subjects.id'), index=True)
    chapter_id: Mapped[str] = mapped_column(String, ForeignKey('ai_subject_chapters.id'), index=True)
    title: Mapped[str] = mapped_column(String(255))
    total_questions: Mapped[int] = mapped_column(Integer, default=15)
    difficulty_easy: Mapped[int] = mapped_column(Integer, default=50)
    difficulty_medium: Mapped[int] = mapped_column(Integer, default=30)
    difficulty_hard: Mapped[int] = mapped_column(Integer, default=20)
    max_families_per_bank: Mapped[int] = mapped_column(Integer, default=2)
    pick_count_per_slot: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(50), default='active', index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index('ix_ai_quiz_blueprints_chapter_status', 'chapter_id', 'status'),
    )


class CourseQuizInstance(Base):
    __tablename__ = 'ai_course_quiz_instances'

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    openedx_course_id: Mapped[str] = mapped_column(String(255), index=True)
    subject_id: Mapped[str] = mapped_column(String, ForeignKey('ai_subjects.id'), index=True)
    chapter_id: Mapped[str] = mapped_column(String, ForeignKey('ai_subject_chapters.id'), index=True)
    bank_release_id: Mapped[str] = mapped_column(String, ForeignKey('ai_question_bank_releases.id'), index=True)
    quiz_blueprint_id: Mapped[str | None] = mapped_column(String, ForeignKey('ai_quiz_blueprints.id'), nullable=True, index=True)
    openedx_quiz_node_id: Mapped[str | None] = mapped_column(String(512), nullable=True, index=True)
    openedx_unit_node_id: Mapped[str | None] = mapped_column(String(512), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(50), default='planned', index=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index('ix_ai_course_quiz_instances_course_chapter', 'openedx_course_id', 'chapter_id'),
    )
