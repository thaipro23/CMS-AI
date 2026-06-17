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
    openedx_mapping_source: str | None = None
    openedx_mapping_validation_status: str | None = None


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
    mapping_id: str | None = None
    openedx_user_id: str | None = None
    openedx_username: str | None = None
    openedx_email: str | None = None
    openedx_is_active: bool | None = None
    match_status: str = 'not_checked'
    match_method: str = 'not_checked'
    mapping_confidence: float = 0.0
    mapping_note: str = ''
    last_resolved_at: datetime | None = None


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

class AcademicResolveClassUsersIn(BaseModel):
    force: bool = False
    limit: int = Field(1000, ge=1, le=5000)


class AcademicMappingSummaryOut(BaseModel):
    class_id: str
    total: int
    counts: dict[str, int]


class AcademicMappingResolveOut(BaseModel):
    ok: bool
    class_id: str
    total: int
    updated: int
    counts: dict[str, int]
    message: str


class AcademicManualMappingRecordIn(BaseModel):
    ap_username: str | None = None
    student_code: str | None = None
    openedx_user_id: str | int | None = None
    openedx_username: str | None = None
    openedx_email: str | None = None
    is_active: bool = True
    note: str | None = None


class AcademicManualMappingImportIn(BaseModel):
    records: list[AcademicManualMappingRecordIn] = Field(default_factory=list, max_length=10000)


class AcademicManualMappingImportOut(BaseModel):
    ok: bool
    total: int
    counters: dict[str, int]
    errors: list[dict[str, Any]] = Field(default_factory=list)


class AcademicCourseMappingOut(BaseModel):
    id: str
    term_id: str
    term_name: str | None = None
    block_id: str | None = None
    block_name: str | None = None
    subject_id: str
    subject_code: str | None = None
    subject_name: str | None = None
    campus: str | None = None
    branch: str | None = None
    openedx_course_id: str
    openedx_course_title: str | None = None
    validation_status: str = 'not_validated'
    validation_json: dict[str, Any] | None = None
    validated_at: datetime | None = None
    note: str = ''
    active: bool = True
    created_by: str | None = None
    updated_by: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {'from_attributes': True}


class AcademicClassCourseMappingOut(BaseModel):
    id: str
    class_id: str
    class_code: str | None = None
    term_id: str | None = None
    term_name: str | None = None
    block_id: str | None = None
    block_name: str | None = None
    subject_id: str | None = None
    subject_code: str | None = None
    openedx_course_id: str
    openedx_cohort_name: str | None = None
    openedx_course_title: str | None = None
    mapping_source: str = 'class_override'
    validation_status: str = 'not_validated'
    validation_json: dict[str, Any] | None = None
    validated_at: datetime | None = None
    note: str = ''
    active: bool = True
    created_by: str | None = None
    updated_by: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {'from_attributes': True}


class AcademicCourseMappingListOut(BaseModel):
    items: list[AcademicCourseMappingOut]
    total: int
    page: int = 1
    page_size: int = 50
    total_pages: int = 1
    has_next: bool = False


class AcademicClassCourseMappingListOut(BaseModel):
    items: list[AcademicClassCourseMappingOut]
    total: int
    page: int = 1
    page_size: int = 50
    total_pages: int = 1
    has_next: bool = False


class AcademicCourseMappingValidateIn(BaseModel):
    term_id: str
    subject_id: str
    openedx_course_id: str
    block_id: str | None = None
    campus: str | None = None
    branch: str | None = None
    openedx_course_title: str | None = None


class AcademicCourseMappingCreateIn(AcademicCourseMappingValidateIn):
    allow_warnings: bool = False
    note: str | None = None


class AcademicClassCourseMappingValidateIn(BaseModel):
    openedx_course_id: str
    openedx_cohort_name: str | None = None
    openedx_course_title: str | None = None


class AcademicClassCourseMappingCreateIn(AcademicClassCourseMappingValidateIn):
    allow_warnings: bool = False
    note: str | None = None


class AcademicCourseMappingValidationOut(BaseModel):
    ok: bool
    can_save: bool
    risk_level: str
    message: str
    checks: list[dict[str, Any]] = Field(default_factory=list)
    suggested_openedx_course_id: str | None = None
    parsed_course: dict[str, Any] | None = None


class AcademicClassCourseMappingProposalOut(BaseModel):
    class_id: str
    class_code: str
    suggested_openedx_course_id: str
    suggested_cohort_name: str
    inherited_course_mapping: AcademicCourseMappingOut | None = None
    effective_openedx_course_id: str | None = None
    effective_openedx_cohort_name: str | None = None
    effective_mapping_source: str
    checks: list[dict[str, Any]] = Field(default_factory=list)
