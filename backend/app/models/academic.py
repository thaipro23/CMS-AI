from __future__ import annotations

import uuid
from datetime import datetime
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


def _uuid() -> str:
    return str(uuid.uuid4())




class AcademicCampus(Base):
    __tablename__ = 'academic_campuses'

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    campus_code: Mapped[str] = mapped_column(String(64), index=True)
    campus_name: Mapped[str] = mapped_column(String(255), default='')
    branch: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, index=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint('campus_code', 'branch', name='uq_academic_campuses_code_branch'),
        Index('ix_academic_campuses_branch_active_order', 'branch', 'active', 'sort_order'),
    )


class AcademicTerm(Base):
    __tablename__ = 'academic_terms'

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    ap_term_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    term_code: Mapped[str] = mapped_column(String(128), index=True)
    term_name: Mapped[str] = mapped_column(String(255), index=True)
    branch: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    start_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    end_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint('term_code', 'branch', name='uq_academic_terms_code_branch'),
        Index('ix_academic_terms_branch_active', 'branch', 'active'),
    )


class AcademicBlock(Base):
    __tablename__ = 'academic_blocks'

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    term_id: Mapped[str] = mapped_column(String, ForeignKey('academic_terms.id'), index=True)
    ap_block_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    block_code: Mapped[str] = mapped_column(String(128), index=True)
    block_name: Mapped[str] = mapped_column(String(255))
    start_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    end_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint('term_id', 'block_code', name='uq_academic_blocks_term_code'),
        Index('ix_academic_blocks_term_active_order', 'term_id', 'active', 'sort_order'),
    )


class AcademicSubject(Base):
    __tablename__ = 'academic_subjects'

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    ap_subject_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    subject_code: Mapped[str] = mapped_column(String(64), index=True)
    subject_name: Mapped[str] = mapped_column(String(255))
    subject_name_en: Mapped[str | None] = mapped_column(String(255), nullable=True)
    skill_code: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    branch: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint('subject_code', 'branch', name='uq_academic_subjects_code_branch'),
        Index('ix_academic_subjects_branch_active_code', 'branch', 'active', 'subject_code'),
    )


class AcademicTeacher(Base):
    __tablename__ = 'academic_teachers'

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    teacher_code: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    username: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    full_name: Mapped[str] = mapped_column(String(255), default='')
    campus: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    branch: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index('ix_academic_teachers_active_username', 'active', 'username'),
    )


class AcademicStudent(Base):
    __tablename__ = 'academic_students'

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    student_code: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    username: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    full_name: Mapped[str] = mapped_column(String(255), default='')
    phone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    campus: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    branch: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index('ix_academic_students_code_username', 'student_code', 'username'),
        Index('ix_academic_students_active_username', 'active', 'username'),
    )


class OpenEdXUserMapping(Base):
    __tablename__ = 'openedx_user_mappings'

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    student_id: Mapped[str] = mapped_column(String, ForeignKey('academic_students.id'), unique=True, index=True)
    ap_student_code: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    ap_username: Mapped[str] = mapped_column(String(255), index=True)
    ap_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    openedx_user_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    openedx_username: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    openedx_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    openedx_is_active: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    match_method: Mapped[str] = mapped_column(String(50), default='not_checked', index=True)
    match_status: Mapped[str] = mapped_column(String(50), default='not_checked', index=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    note: Mapped[str] = mapped_column(Text, default='')
    raw_json: Mapped[dict | None] = mapped_column(JSON, nullable=True, default=dict)
    last_resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index('ix_openedx_user_mappings_ap_username_status', 'ap_username', 'match_status'),
        Index('ix_openedx_user_mappings_student_status', 'student_id', 'match_status'),
    )


class AcademicClass(Base):
    __tablename__ = 'academic_classes'

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    ap_class_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    term_id: Mapped[str] = mapped_column(String, ForeignKey('academic_terms.id'), index=True)
    block_id: Mapped[str | None] = mapped_column(String, ForeignKey('academic_blocks.id'), nullable=True, index=True)
    subject_id: Mapped[str] = mapped_column(String, ForeignKey('academic_subjects.id'), index=True)
    class_code: Mapped[str] = mapped_column(String(128), index=True)
    class_name: Mapped[str] = mapped_column(String(255), default='')
    campus: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    branch: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    start_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    end_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        # A class code/name is only unique inside its full AP operating scope.
        # Different campus/branch/term/subject/block rows are distinct classes even
        # when AP shows the same visible class name.
        Index(
            'uq_academic_classes_active_scope_code',
            'term_id', 'block_id', 'subject_id', 'class_code', 'campus', 'branch',
            unique=True,
            postgresql_where=text('active IS TRUE'),
        ),
        Index('ix_academic_classes_teacher_lookup', 'term_id', 'block_id', 'subject_id', 'active'),
        Index('ix_academic_classes_campus_branch', 'campus', 'branch'),
    )


class AcademicTeacherAssignment(Base):
    __tablename__ = 'academic_teacher_assignments'

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    teacher_id: Mapped[str] = mapped_column(String, ForeignKey('academic_teachers.id'), index=True)
    class_id: Mapped[str] = mapped_column(String, ForeignKey('academic_classes.id'), index=True)
    subject_id: Mapped[str] = mapped_column(String, ForeignKey('academic_subjects.id'), index=True)
    term_id: Mapped[str] = mapped_column(String, ForeignKey('academic_terms.id'), index=True)
    block_id: Mapped[str | None] = mapped_column(String, ForeignKey('academic_blocks.id'), nullable=True, index=True)
    campus: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    branch: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    source: Mapped[str] = mapped_column(String(50), default='ap')
    synced_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True, default=dict)

    __table_args__ = (
        UniqueConstraint('teacher_id', 'class_id', 'subject_id', 'term_id', 'block_id', name='uq_academic_teacher_assignment'),
        Index('ix_academic_teacher_assignments_teacher_term_block', 'teacher_id', 'term_id', 'block_id'),
        Index('ix_academic_teacher_assignments_class_teacher', 'class_id', 'teacher_id'),
    )


class AcademicClassStudent(Base):
    __tablename__ = 'academic_class_students'

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    class_id: Mapped[str] = mapped_column(String, ForeignKey('academic_classes.id'), index=True)
    student_id: Mapped[str] = mapped_column(String, ForeignKey('academic_students.id'), index=True)
    source: Mapped[str] = mapped_column(String(50), default='ap')
    synced_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True, default=dict)

    __table_args__ = (
        UniqueConstraint('class_id', 'student_id', name='uq_academic_class_student'),
        Index('ix_academic_class_students_class_student', 'class_id', 'student_id'),
    )


class AcademicCourseMapping(Base):
    __tablename__ = 'academic_course_mappings'

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    term_id: Mapped[str] = mapped_column(String, ForeignKey('academic_terms.id'), index=True)
    block_id: Mapped[str | None] = mapped_column(String, ForeignKey('academic_blocks.id'), nullable=True, index=True)
    subject_id: Mapped[str] = mapped_column(String, ForeignKey('academic_subjects.id'), index=True)
    campus: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    branch: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    openedx_course_id: Mapped[str] = mapped_column(String(255), index=True)
    openedx_course_title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    validation_status: Mapped[str] = mapped_column(String(50), default='not_validated', index=True)
    validation_json: Mapped[dict | None] = mapped_column(JSON, nullable=True, default=dict)
    validated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    updated_by: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    note: Mapped[str] = mapped_column(Text, default='')
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint('term_id', 'block_id', 'subject_id', 'campus', 'branch', name='uq_academic_course_mapping_scope'),
        Index('ix_academic_course_mappings_subject_term', 'subject_id', 'term_id', 'block_id'),
        Index('ix_academic_course_mappings_course_active', 'openedx_course_id', 'active'),
    )


class AcademicClassCourseMapping(Base):
    __tablename__ = 'academic_class_course_mappings'

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    class_id: Mapped[str] = mapped_column(String, ForeignKey('academic_classes.id'), unique=True, index=True)
    openedx_course_id: Mapped[str] = mapped_column(String(255), index=True)
    openedx_cohort_name: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    openedx_course_title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    mapping_source: Mapped[str] = mapped_column(String(50), default='class_override', index=True)
    validation_status: Mapped[str] = mapped_column(String(50), default='not_validated', index=True)
    validation_json: Mapped[dict | None] = mapped_column(JSON, nullable=True, default=dict)
    validated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    updated_by: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    note: Mapped[str] = mapped_column(Text, default='')
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index('ix_academic_class_course_mappings_course_active', 'openedx_course_id', 'active'),
        Index('ix_academic_class_course_mappings_cohort_active', 'openedx_cohort_name', 'active'),
    )




class AcademicStudentLearningSnapshot(Base):
    __tablename__ = 'academic_student_learning_snapshots'

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    class_id: Mapped[str] = mapped_column(String, ForeignKey('academic_classes.id'), index=True)
    student_id: Mapped[str] = mapped_column(String, ForeignKey('academic_students.id'), index=True)
    openedx_course_id: Mapped[str] = mapped_column(String(255), index=True)
    openedx_username: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    openedx_user_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    enrollment_status: Mapped[str] = mapped_column(String(50), default='unknown', index=True)
    enrollment_mode: Mapped[str | None] = mapped_column(String(50), nullable=True)
    progress_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    grade_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    passed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    completed_blocks: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_blocks: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_activity_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    raw_json: Mapped[dict | None] = mapped_column(JSON, nullable=True, default=dict)
    enrollment_synced_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    learning_synced_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint('class_id', 'student_id', 'openedx_course_id', name='uq_academic_learning_class_student_course'),
        Index('ix_academic_learning_class_course_sync', 'class_id', 'openedx_course_id', 'last_synced_at'),
        Index('ix_academic_learning_status_grade', 'enrollment_status', 'passed', 'grade_percent'),
    )


class AcademicQuizDeadlineOverride(Base):
    __tablename__ = 'academic_quiz_deadline_overrides'

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    class_id: Mapped[str] = mapped_column(String, ForeignKey('academic_classes.id'), index=True)
    course_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    component_key: Mapped[str | None] = mapped_column(String(512), nullable=True, index=True)
    component_label: Mapped[str] = mapped_column(String(255), default='')
    quiz_number: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    start_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    deadline_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    reason: Mapped[str] = mapped_column(Text, default='')
    created_by: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    updated_by: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True, default=dict)

    __table_args__ = (
        Index('ix_academic_quiz_deadline_class_course', 'class_id', 'course_id', 'quiz_number'),
        Index(
            'uq_academic_quiz_deadline_class_course_number_v2',
            'class_id',
            text("COALESCE(course_id, '')"),
            'quiz_number',
            unique=True,
            postgresql_where=text('quiz_number IS NOT NULL'),
        ),
    )


class AcademicAssignmentDefenseScore(Base):
    __tablename__ = 'academic_assignment_defense_scores'

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    class_id: Mapped[str] = mapped_column(String, ForeignKey('academic_classes.id'), index=True)
    student_id: Mapped[str] = mapped_column(String, ForeignKey('academic_students.id'), index=True)
    course_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    assignment_key: Mapped[str | None] = mapped_column(String(512), nullable=True, index=True)
    assignment_label: Mapped[str] = mapped_column(String(255), default='Assignment')
    score_10: Mapped[float | None] = mapped_column(Float, nullable=True)
    defense_status: Mapped[str] = mapped_column(String(50), default='not_graded', index=True)
    graded_by: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    graded_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    note: Mapped[str] = mapped_column(Text, default='')
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True, default=dict)

    __table_args__ = (
        Index('ix_academic_assignment_defense_class_student', 'class_id', 'student_id'),
        Index(
            'uq_academic_assignment_defense_class_student_key_v2',
            'class_id',
            'student_id',
            text("COALESCE(course_id, '')"),
            text("COALESCE(assignment_key, '')"),
            unique=True,
        ),
    )


class AcademicClassSyncJob(Base):
    """Async class-level CMS/Open edX sync job tracked for UI polling.

    Heavy class operations call the Open edX Connector plugin and can take
    longer than a normal HTTP request. Keep them in Celery and let the frontend
    poll this table instead of blocking a Uvicorn worker.
    """

    __tablename__ = 'academic_class_sync_jobs'

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    job_type: Mapped[str] = mapped_column(String(80), index=True)  # cms_sync_check | cms_enrollment_sync | learning_sync
    status: Mapped[str] = mapped_column(String(50), default='queued', index=True)  # queued | running | completed | failed
    class_id: Mapped[str] = mapped_column(String, ForeignKey('academic_classes.id'), index=True)
    requested_by: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    force: Mapped[bool] = mapped_column(Boolean, default=False)
    limit: Mapped[int] = mapped_column(Integer, default=500)
    mode: Mapped[str | None] = mapped_column(String(50), nullable=True)
    progress_current: Mapped[int] = mapped_column(Integer, default=0)
    progress_total: Mapped[int] = mapped_column(Integer, default=100)
    progress_label: Mapped[str] = mapped_column(String(255), default='Đang chờ xử lý')
    request_json: Mapped[dict | None] = mapped_column(JSON, nullable=True, default=dict)
    result_json: Mapped[dict | None] = mapped_column(JSON, nullable=True, default=dict)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index('ix_academic_class_sync_jobs_class_status_created', 'class_id', 'status', 'created_at'),
        Index('ix_academic_class_sync_jobs_actor_created', 'requested_by', 'created_at'),
        Index('ix_academic_class_sync_jobs_type_status_created', 'job_type', 'status', 'created_at'),
    )


class AcademicTeacherReportSummary(Base):
    """Materialized teacher-management row for large term/campus scopes.

    One row is one teacher under a requested report scope. Keep the rendered
    report payload JSON so the list page can read fast without rehydrating
    class/student/grade policy rows on every request.
    """

    __tablename__ = 'academic_teacher_report_summaries'

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    term_id: Mapped[str] = mapped_column(String, ForeignKey('academic_terms.id'), index=True)
    branch: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    campus: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    scope_key: Mapped[str] = mapped_column(String(255), index=True)
    teacher_id: Mapped[str] = mapped_column(String, ForeignKey('academic_teachers.id'), index=True)
    teacher_username: Mapped[str] = mapped_column(String(255), index=True)
    teacher_name: Mapped[str] = mapped_column(String(255), default='', index=True)
    teacher_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    class_count: Mapped[int] = mapped_column(Integer, default=0, index=True)
    student_count: Mapped[int] = mapped_column(Integer, default=0)
    unique_student_count: Mapped[int] = mapped_column(Integer, default=0)
    risk_student_count: Mapped[int] = mapped_column(Integer, default=0, index=True)
    cms_synced_count: Mapped[int] = mapped_column(Integer, default=0)
    learning_enrolled_count: Mapped[int] = mapped_column(Integer, default=0)
    learning_avg_progress_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    learning_avg_grade_10: Mapped[float | None] = mapped_column(Float, nullable=True)
    report_json: Mapped[dict | None] = mapped_column(JSON, nullable=True, default=dict)
    summary_json: Mapped[dict | None] = mapped_column(JSON, nullable=True, default=dict)
    source_sync_run_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    built_by: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    built_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint('scope_key', 'teacher_id', name='uq_academic_teacher_report_scope_teacher'),
        Index('ix_academic_teacher_report_scope_built', 'scope_key', 'built_at'),
        Index('ix_academic_teacher_report_scope_risk', 'scope_key', 'risk_student_count'),
    )


class AcademicTeacherReportJob(Base):
    __tablename__ = 'academic_teacher_report_jobs'

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    job_type: Mapped[str] = mapped_column(String(80), index=True)  # rebuild_cache | export_excel
    status: Mapped[str] = mapped_column(String(50), default='queued', index=True)
    term_id: Mapped[str | None] = mapped_column(String, ForeignKey('academic_terms.id'), nullable=True, index=True)
    branch: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    campus: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    requested_by: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    progress_current: Mapped[int] = mapped_column(Integer, default=0)
    progress_total: Mapped[int] = mapped_column(Integer, default=100)
    progress_label: Mapped[str] = mapped_column(String(255), default='Đang chờ xử lý')
    request_json: Mapped[dict | None] = mapped_column(JSON, nullable=True, default=dict)
    result_json: Mapped[dict | None] = mapped_column(JSON, nullable=True, default=dict)
    file_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    file_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index('ix_academic_teacher_report_jobs_scope_status', 'term_id', 'branch', 'campus', 'status'),
        Index('ix_academic_teacher_report_jobs_actor_created', 'requested_by', 'created_at'),
    )


class AcademicSyncRun(Base):
    __tablename__ = 'academic_sync_runs'

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    source: Mapped[str] = mapped_column(String(50), default='ap', index=True)
    mode: Mapped[str] = mapped_column(String(50), default='manual', index=True)
    status: Mapped[str] = mapped_column(String(50), default='running', index=True)
    requested_by: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    term_name: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    campus: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    branch: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    counters_json: Mapped[dict | None] = mapped_column(JSON, nullable=True, default=dict)
    error_message: Mapped[str] = mapped_column(Text, default='')
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index('ix_academic_sync_runs_status_created', 'status', 'created_at'),
    )


class AcademicSyncError(Base):
    __tablename__ = 'academic_sync_errors'

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    sync_run_id: Mapped[str | None] = mapped_column(String, ForeignKey('academic_sync_runs.id'), nullable=True, index=True)
    source: Mapped[str] = mapped_column(String(50), default='ap', index=True)
    entity_type: Mapped[str] = mapped_column(String(80), index=True)
    entity_key: Mapped[str] = mapped_column(String(255), default='', index=True)
    message: Mapped[str] = mapped_column(Text, default='')
    payload_json: Mapped[dict | None] = mapped_column(JSON, nullable=True, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
