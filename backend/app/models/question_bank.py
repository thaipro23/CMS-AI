import uuid
from datetime import datetime
from sqlalchemy import Boolean, DateTime, ForeignKey, Float, Index, Integer, JSON, String, Text, UniqueConstraint
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


class SubjectOffering(Base):
    """A subject version layer, e.g. DOM123_SU26.

    This is the product-level version boundary requested by the user:
    Department -> Subject -> Subject Version (DOM123_SP25) -> Chapters.
    Questions/concepts/families are still data entities attached to the
    concrete bank/version, not top-level UI hierarchy.
    """
    __tablename__ = 'ai_subject_offerings'

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    department_id: Mapped[str | None] = mapped_column(String, ForeignKey('ai_departments.id'), nullable=True, index=True)
    subject_id: Mapped[str] = mapped_column(String, ForeignKey('ai_subjects.id'), index=True)
    code: Mapped[str] = mapped_column(String(128), index=True)  # DOM123_SU26 / DOM123_v2
    name: Mapped[str] = mapped_column(String(255), default='')
    term: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    version_code: Mapped[str] = mapped_column(String(64), default='v1.0')
    based_on_offering_id: Mapped[str | None] = mapped_column(String, ForeignKey('ai_subject_offerings.id'), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(50), default='draft', index=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True, default=dict)
    created_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    approved_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint('subject_id', 'code', name='uq_ai_subject_offering_subject_code'),
        Index('ix_ai_subject_offerings_subject_status', 'subject_id', 'status'),
        Index('ix_ai_subject_offerings_subject_status_created', 'subject_id', 'status', 'created_at', 'id'),
    )


class SubjectChapter(Base):
    __tablename__ = 'ai_subject_chapters'

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    subject_id: Mapped[str] = mapped_column(String, ForeignKey('ai_subjects.id'), index=True)
    subject_offering_id: Mapped[str | None] = mapped_column(String, ForeignKey('ai_subject_offerings.id'), nullable=True, index=True)
    chapter_no: Mapped[int] = mapped_column(Integer, default=1)
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text, default='')
    sort_order: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(50), default='active', index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint('subject_id', 'subject_offering_id', 'chapter_no', name='uq_ai_subject_offering_chapter_no'),
        Index('ix_ai_subject_chapters_offering_order', 'subject_offering_id', 'sort_order'),
        Index('ix_ai_subject_chapters_subject_status', 'subject_id', 'status'),
        Index('ix_ai_subject_chapters_offering_status_order', 'subject_offering_id', 'status', 'sort_order', 'id'),
    )


class QuestionBankVersion(Base):
    __tablename__ = 'ai_question_bank_versions'

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    subject_id: Mapped[str] = mapped_column(String, ForeignKey('ai_subjects.id'), index=True)
    chapter_id: Mapped[str] = mapped_column(String, ForeignKey('ai_subject_chapters.id'), index=True)
    subject_offering_id: Mapped[str | None] = mapped_column(String, ForeignKey('ai_subject_offerings.id'), nullable=True, index=True)
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
        Index('ix_ai_bank_versions_offering_status', 'subject_offering_id', 'status'),
        Index('ix_ai_bank_versions_offering_chapter_status', 'subject_offering_id', 'chapter_id', 'status'),
    )


class LearningMaterialVersion(Base):
    __tablename__ = 'ai_learning_material_versions'

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    subject_id: Mapped[str] = mapped_column(String, ForeignKey('ai_subjects.id'), index=True)
    chapter_id: Mapped[str] = mapped_column(String, ForeignKey('ai_subject_chapters.id'), index=True)
    subject_offering_id: Mapped[str | None] = mapped_column(String, ForeignKey('ai_subject_offerings.id'), nullable=True, index=True)
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
    # v25.9.16.3.6: material deletion is now policy-based. Draft/unused
    # materials are hard-deleted immediately, while audit-sensitive materials are
    # kept as lightweight tombstones with deleted_at/deleted_by so admins can
    # purge them after the retention window.
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    deleted_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index('ix_ai_material_versions_bank_hash', 'bank_version_id', 'content_hash'),
        Index('ix_ai_material_versions_status_deleted', 'status', 'deleted_at'),
    )




class MaterialChunk(Base):
    __tablename__ = 'ai_material_chunks'

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    material_version_id: Mapped[str] = mapped_column(String, ForeignKey('ai_learning_material_versions.id'), index=True)
    bank_version_id: Mapped[str] = mapped_column(String, ForeignKey('ai_question_bank_versions.id'), index=True)
    subject_id: Mapped[str] = mapped_column(String, ForeignKey('ai_subjects.id'), index=True)
    chapter_id: Mapped[str] = mapped_column(String, ForeignKey('ai_subject_chapters.id'), index=True)
    subject_offering_id: Mapped[str | None] = mapped_column(String, ForeignKey('ai_subject_offerings.id'), nullable=True, index=True)
    chunk_index: Mapped[int] = mapped_column(Integer, default=1)
    content: Mapped[str] = mapped_column(Text)
    token_count: Mapped[int] = mapped_column(Integer, default=0)
    source_type: Mapped[str] = mapped_column(String(100), default='file')
    page_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_ref: Mapped[str] = mapped_column(String(1024), default='')
    content_hash: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint('material_version_id', 'chunk_index', name='uq_ai_material_chunk_index'),
        Index('ix_ai_material_chunks_bank_subject_chapter', 'bank_version_id', 'subject_id', 'chapter_id'),
        Index('ix_ai_material_chunks_bank_source', 'bank_version_id', 'source_type'),
        Index('ix_ai_material_chunks_bank_chunk', 'bank_version_id', 'material_version_id', 'chunk_index'),
    )

class ConceptVersion(Base):
    __tablename__ = 'ai_concept_versions'

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    bank_version_id: Mapped[str] = mapped_column(String, ForeignKey('ai_question_bank_versions.id'), index=True)
    subject_id: Mapped[str] = mapped_column(String, ForeignKey('ai_subjects.id'), index=True)
    chapter_id: Mapped[str] = mapped_column(String, ForeignKey('ai_subject_chapters.id'), index=True)
    subject_offering_id: Mapped[str | None] = mapped_column(String, ForeignKey('ai_subject_offerings.id'), nullable=True, index=True)
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
    subject_offering_id: Mapped[str | None] = mapped_column(String, ForeignKey('ai_subject_offerings.id'), nullable=True, index=True)
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
    subject_offering_id: Mapped[str | None] = mapped_column(String, ForeignKey('ai_subject_offerings.id'), nullable=True, index=True)
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
        Index('ix_ai_releases_bank_status_created', 'bank_version_id', 'status', 'created_at'),
    )


class BankVersionDiff(Base):
    __tablename__ = 'ai_bank_version_diffs'

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    from_bank_version_id: Mapped[str] = mapped_column(String, ForeignKey('ai_question_bank_versions.id'), index=True)
    to_bank_version_id: Mapped[str] = mapped_column(String, ForeignKey('ai_question_bank_versions.id'), index=True)
    status: Mapped[str] = mapped_column(String(50), default='preview', index=True)  # preview | applied | archived
    material_similarity: Mapped[float | None] = mapped_column(Float, nullable=True)
    summary_json: Mapped[dict | None] = mapped_column(JSON, nullable=True, default=dict)
    created_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    applied_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    applied_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index('ix_ai_bank_version_diffs_pair_status', 'from_bank_version_id', 'to_bank_version_id', 'status'),
    )


class BankVersionDiffItem(Base):
    __tablename__ = 'ai_bank_version_diff_items'

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    diff_id: Mapped[str] = mapped_column(String, ForeignKey('ai_bank_version_diffs.id'), index=True)
    item_type: Mapped[str] = mapped_column(String(50), index=True)  # material | concept | question
    source_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    target_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    change_type: Mapped[str] = mapped_column(String(50), index=True)  # unchanged | changed | new | removed | carry_over_candidate | retire_candidate | already_exists
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    reason: Mapped[str] = mapped_column(Text, default='')
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index('ix_ai_bank_diff_items_diff_type_change', 'diff_id', 'item_type', 'change_type'),
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
        Index('ix_ai_release_questions_release_difficulty', 'bank_release_id', 'difficulty'),
    )


class EdxCourseMapping(Base):
    __tablename__ = 'ai_edx_course_mappings'

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    openedx_course_id: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    department_id: Mapped[str | None] = mapped_column(String, ForeignKey('ai_departments.id'), nullable=True, index=True)
    subject_id: Mapped[str] = mapped_column(String, ForeignKey('ai_subjects.id'), index=True)
    subject_offering_id: Mapped[str | None] = mapped_column(String, ForeignKey('ai_subject_offerings.id'), nullable=True, index=True)
    term: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(50), default='active', index=True)
    validation_status: Mapped[str] = mapped_column(String(50), default='not_validated', index=True)
    validation_json: Mapped[dict | None] = mapped_column(JSON, nullable=True, default=dict)
    validated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
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
    validation_status: Mapped[str] = mapped_column(String(50), default='not_validated', index=True)
    validation_json: Mapped[dict | None] = mapped_column(JSON, nullable=True, default=dict)
    validated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
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
    subject_offering_id: Mapped[str | None] = mapped_column(String, ForeignKey('ai_subject_offerings.id'), nullable=True, index=True)
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
    subject_offering_id: Mapped[str | None] = mapped_column(String, ForeignKey('ai_subject_offerings.id'), nullable=True, index=True)
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
        Index('ix_ai_course_quiz_instances_release_status_created', 'bank_release_id', 'status', 'created_at'),
        Index('ix_ai_course_quiz_instances_course_status_created', 'openedx_course_id', 'status', 'created_at'),
    )

class BankChapterStats(Base):
    """Pre-aggregated Bank Dashboard statistics per chapter.

    v25.9.15.6.34 keeps dashboards off the 1.5M-row ai_questions table.
    Request-time dashboard code reads this 15k-row table and small hierarchy
    tables only; rebuild/refresh jobs are the only code paths allowed to
    aggregate ai_questions directly.
    """
    __tablename__ = 'ai_bank_chapter_stats'

    chapter_id: Mapped[str] = mapped_column(String, ForeignKey('ai_subject_chapters.id'), primary_key=True)
    subject_id: Mapped[str] = mapped_column(String, ForeignKey('ai_subjects.id'), nullable=False, index=True)
    subject_offering_id: Mapped[str | None] = mapped_column(String, ForeignKey('ai_subject_offerings.id'), nullable=True, index=True)
    latest_bank_version_id: Mapped[str | None] = mapped_column(String, ForeignKey('ai_question_bank_versions.id'), nullable=True, index=True)
    total_questions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    approved_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    pending_review_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    draft_error_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rejected_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    retired_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    duplicate_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    easy_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    medium_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    hard_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    family_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    material_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    release_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    published_release_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    ready_to_release: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    unresolved_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow, index=True)

    __table_args__ = (
        Index('ix_ai_bank_chapter_stats_subject_unresolved', 'subject_id', 'unresolved_count'),
        Index('ix_ai_bank_chapter_stats_offering_ready', 'subject_offering_id', 'ready_to_release'),
        Index('ix_ai_bank_chapter_stats_updated', 'updated_at'),
    )



class QuestionSearchDocument(Base):
    """Lightweight search document for Bank Question search.

    v25.9.15.6.35 keeps quick/global search off the heavy ai_questions table.
    The document stores normalized, accent-stripped text built by the app; API
    search reads this compact table and only opens full Question rows when a
    user navigates to a question/chapter.
    """
    __tablename__ = 'ai_question_search_documents'

    question_id: Mapped[str] = mapped_column(String, ForeignKey('ai_questions.id'), primary_key=True)
    bank_version_id: Mapped[str | None] = mapped_column(String, ForeignKey('ai_question_bank_versions.id'), nullable=True, index=True)
    subject_id: Mapped[str | None] = mapped_column(String, ForeignKey('ai_subjects.id'), nullable=True, index=True)
    subject_offering_id: Mapped[str | None] = mapped_column(String, ForeignKey('ai_subject_offerings.id'), nullable=True, index=True)
    chapter_id: Mapped[str | None] = mapped_column(String, ForeignKey('ai_subject_chapters.id'), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(50), default='draft', index=True)
    difficulty: Mapped[str] = mapped_column(String(50), default='easy', index=True)
    question_text_preview: Mapped[str] = mapped_column(String(500), default='')
    concept_title: Mapped[str | None] = mapped_column(String(512), nullable=True)
    question_family_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    search_text: Mapped[str] = mapped_column(Text, default='')
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow, index=True)

    __table_args__ = (
        Index('ix_ai_question_search_bank_status', 'bank_version_id', 'status'),
        Index('ix_ai_question_search_subject_chapter_status', 'subject_id', 'chapter_id', 'status'),
        Index('ix_ai_question_search_chapter_difficulty', 'chapter_id', 'difficulty'),
        Index('ix_ai_question_search_updated', 'updated_at'),
    )


class BankOperationJob(Base):
    """Long-running Bank Manager operation tracked outside request/response.

    v25.9.15.6.37 keeps heavy work out of Uvicorn workers: material extraction,
    GPT generation, Open edX publish, and Quiz creation run in Celery while this
    table stores progress/result/error for the UI and admins.
    """

    __tablename__ = 'ai_bank_operation_jobs'

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    operation_type: Mapped[str] = mapped_column(String(80), index=True)  # material_extract | bank_generate | release_publish | quiz_create
    status: Mapped[str] = mapped_column(String(50), default='queued', index=True)  # queued | running | completed | failed | canceled
    target_type: Mapped[str] = mapped_column(String(80), default='', index=True)
    target_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    bank_version_id: Mapped[str | None] = mapped_column(String, ForeignKey('ai_question_bank_versions.id'), nullable=True, index=True)
    release_id: Mapped[str | None] = mapped_column(String, ForeignKey('ai_question_bank_releases.id'), nullable=True, index=True)
    material_version_id: Mapped[str | None] = mapped_column(String, ForeignKey('ai_learning_material_versions.id'), nullable=True, index=True)
    course_quiz_instance_id: Mapped[str | None] = mapped_column(String, ForeignKey('ai_course_quiz_instances.id'), nullable=True, index=True)
    requested_by: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    course_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    progress_current: Mapped[int] = mapped_column(Integer, default=0)
    progress_total: Mapped[int] = mapped_column(Integer, default=1)
    progress_label: Mapped[str] = mapped_column(String(255), default='Đang chờ xử lý')
    request_json: Mapped[dict | None] = mapped_column(JSON, nullable=True, default=dict)
    result_json: Mapped[dict | None] = mapped_column(JSON, nullable=True, default=dict)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index('ix_ai_bank_operation_jobs_status_created', 'status', 'created_at'),
        Index('ix_ai_bank_operation_jobs_target_status_created', 'target_type', 'target_id', 'status', 'created_at'),
        Index('ix_ai_bank_operation_jobs_actor_created', 'requested_by', 'created_at'),
        Index('ix_ai_bank_operation_jobs_bank_status_created', 'bank_version_id', 'status', 'created_at'),
        Index('ix_ai_bank_operation_jobs_release_status_created', 'release_id', 'status', 'created_at'),
    )
