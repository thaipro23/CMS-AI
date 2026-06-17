from __future__ import annotations

from datetime import datetime
from typing import Any
from pydantic import BaseModel, Field


class AcademicTermOut(BaseModel):
    id: str
    ap_term_id: str | None = None
    term_code: str
    term_name: str
    branch: str | None = None
    start_date: datetime | None = None
    end_date: datetime | None = None
    active: bool

    model_config = {'from_attributes': True}


class AcademicBlockOut(BaseModel):
    id: str
    term_id: str
    ap_block_id: str | None = None
    block_code: str
    block_name: str
    start_date: datetime | None = None
    end_date: datetime | None = None
    sort_order: int
    active: bool

    model_config = {'from_attributes': True}


class AcademicSubjectOut(BaseModel):
    id: str
    ap_subject_id: str | None = None
    subject_code: str
    subject_name: str
    subject_name_en: str | None = None
    skill_code: str | None = None
    branch: str | None = None
    active: bool

    model_config = {'from_attributes': True}


class AcademicClassOut(BaseModel):
    id: str
    ap_class_id: str | None = None
    term_id: str
    term_name: str | None = None
    block_id: str | None = None
    block_name: str | None = None
    subject_id: str
    subject_code: str | None = None
    subject_name: str | None = None
    class_code: str
    class_name: str
    campus: str | None = None
    branch: str | None = None
    start_date: datetime | None = None
    end_date: datetime | None = None
    active: bool
    teacher_username: str | None = None
    teacher_name: str | None = None
    student_count: int = 0
    openedx_course_id: str | None = None
    openedx_cohort_name: str | None = None


class AcademicStudentOut(BaseModel):
    id: str
    student_code: str | None = None
    username: str
    email: str | None = None
    full_name: str
    phone: str | None = None
    campus: str | None = None
    branch: str | None = None
    active: bool

    model_config = {'from_attributes': True}


class AcademicClassStudentOut(AcademicStudentOut):
    class_id: str
    synced_at: datetime | None = None


class AcademicClassListOut(BaseModel):
    items: list[AcademicClassOut]
    total: int
    page: int = 1
    page_size: int = 50
    total_pages: int = 1
    has_next: bool = False


class AcademicStudentListOut(BaseModel):
    items: list[AcademicClassStudentOut]
    total: int
    page: int = 1
    page_size: int = 50
    total_pages: int = 1
    has_next: bool = False


class AcademicSyncCounters(BaseModel):
    terms: int = 0
    blocks: int = 0
    subjects: int = 0
    classes: int = 0
    teachers: int = 0
    students: int = 0
    teacher_assignments: int = 0
    class_students: int = 0
    errors: int = 0


class AcademicSyncRunOut(BaseModel):
    id: str
    source: str
    mode: str
    status: str
    requested_by: str | None = None
    term_name: str | None = None
    campus: str | None = None
    branch: str | None = None
    counters_json: dict[str, Any] | None = None
    error_message: str = ''
    started_at: datetime
    finished_at: datetime | None = None
    created_at: datetime

    model_config = {'from_attributes': True}


class AcademicImportFromJsonIn(BaseModel):
    payload: dict[str, Any] = Field(..., description='AP get-data-cms payload: {term: {...}, class: [...]}')
    campus: str | None = None
    branch: str = 'poly'
    source: str = 'ap_json'


class AcademicImportResultOut(BaseModel):
    ok: bool
    message: str
    sync_run: AcademicSyncRunOut
    counters: AcademicSyncCounters


class AcademicAPSyncIn(BaseModel):
    term_name: str = Field(..., description='Ví dụ: Spring 2026')
    campus: str = Field(..., description='Mã cơ sở AP dạng pc/pt/hn/hcm...')
    branch: str = 'poly'
    subject_codes: list[str] = Field(default_factory=list, description='Rỗng = lấy danh sách môn từ AP trước rồi sync toàn bộ, có thể rất lâu')
    max_subjects: int = Field(50, ge=1, le=500)
    dry_run: bool = False


class AcademicHealthOut(BaseModel):
    ok: bool
    terms: int
    classes: int
    students: int
    assignments: int
    last_sync: AcademicSyncRunOut | None = None
