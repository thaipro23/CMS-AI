from __future__ import annotations

import uuid
from datetime import datetime
from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


def _uuid() -> str:
    return str(uuid.uuid4())


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
        UniqueConstraint('term_id', 'block_id', 'subject_id', 'class_code', name='uq_academic_classes_term_block_subject_code'),
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
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint('term_id', 'block_id', 'subject_id', 'campus', 'branch', name='uq_academic_course_mapping_scope'),
        Index('ix_academic_course_mappings_subject_term', 'subject_id', 'term_id', 'block_id'),
    )


class AcademicClassCourseMapping(Base):
    __tablename__ = 'academic_class_course_mappings'

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    class_id: Mapped[str] = mapped_column(String, ForeignKey('academic_classes.id'), unique=True, index=True)
    openedx_course_id: Mapped[str] = mapped_column(String(255), index=True)
    openedx_cohort_name: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


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
