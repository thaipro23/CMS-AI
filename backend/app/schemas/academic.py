from __future__ import annotations

from datetime import datetime
from typing import Any
from pydantic import BaseModel, Field, field_validator

from app.core.timezone import to_vn_naive_datetime


def _coerce_vn_datetime(value: Any) -> datetime | None:
    if value is None or value == '':
        return None
    parsed = to_vn_naive_datetime(value)
    return parsed or value


class AcademicTermOut(BaseModel):
    id: str
    ap_term_id: str | None = None
    term_code: str
    term_name: str
    branch: str | None = None
    start_date: datetime | None = None
    end_date: datetime | None = None
    active: bool
    metadata_json: dict[str, Any] | None = None

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
    metadata_json: dict[str, Any] | None = None

    model_config = {'from_attributes': True}




class AcademicBlockUpsertIn(BaseModel):
    id: str | None = None
    block_code: str = Field(..., min_length=1, max_length=128, description='Mã block, ví dụ Block 1 hoặc block1-Summer 2026')
    block_name: str = Field(..., min_length=1, max_length=255, description='Tên block hiển thị')
    start_date: datetime | None = None
    end_date: datetime | None = None
    sort_order: int = Field(0, ge=0, le=100)
    active: bool = True
    metadata_json: dict[str, Any] | None = None

    @field_validator('start_date', 'end_date', mode='before')
    @classmethod
    def _normalize_block_dates(cls, value: Any) -> Any:
        return _coerce_vn_datetime(value)


class AcademicTermUpsertIn(BaseModel):
    id: str | None = None
    ap_term_id: str | None = Field(None, max_length=64)
    term_code: str = Field(..., min_length=1, max_length=128, description='Mã học kỳ AP, ví dụ Summer 2026')
    term_name: str = Field(..., min_length=1, max_length=255, description='Tên học kỳ hiển thị')
    branch: str = Field('poly', max_length=64)
    start_date: datetime | None = None
    end_date: datetime | None = None
    active: bool = True
    metadata_json: dict[str, Any] | None = None
    blocks: list[AcademicBlockUpsertIn] = Field(default_factory=list, max_length=8)

    @field_validator('start_date', 'end_date', mode='before')
    @classmethod
    def _normalize_term_dates(cls, value: Any) -> Any:
        return _coerce_vn_datetime(value)


class AcademicTermWithBlocksOut(AcademicTermOut):
    blocks: list[AcademicBlockOut] = Field(default_factory=list)


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


class AcademicSubjectManagementOut(AcademicSubjectOut):
    class_count: int = 0
    campus_count: int = 0
    teacher_count: int = 0
    student_count: int = 0
    cms_synced_count: int = 0
    cms_unsynced_count: int = 0
    course_mapping_status: str = 'not_found'
    course_mapping_label: str = ''
    openedx_course_id: str | None = None
    openedx_course_title: str | None = None
    openedx_mapping_id: str | None = None
    suggested_openedx_course_id: str | None = None
    learning_enrolled_count: int = 0
    learning_active_count: int = 0
    learning_synced_count: int = 0
    learning_not_enrolled_count: int = 0
    learning_avg_progress_percent: float | None = None
    learning_avg_grade_percent: float | None = None
    learning_last_synced_at: datetime | None = None
    learning_component_summaries: list[dict[str, Any]] = Field(default_factory=list)
    learning_alerts: list[str] = Field(default_factory=list)



class AcademicSubjectManagementSummaryOut(BaseModel):
    subject_count: int = 0
    class_count: int = 0
    student_count: int = 0
    teacher_count: int = 0
    cms_synced_count: int = 0
    cms_unsynced_count: int = 0
    course_mapped_count: int = 0
    course_missing_count: int = 0
    learning_enrolled_count: int = 0
    learning_active_count: int = 0
    learning_synced_count: int = 0
    alert_subject_count: int = 0
    scope_label: str = 'Toàn bộ bộ lọc'


class AcademicSubjectManagementListOut(BaseModel):
    items: list[AcademicSubjectManagementOut]
    total: int
    page: int = 1
    page_size: int = 50
    total_pages: int = 1
    has_next: bool = False
    summary: AcademicSubjectManagementSummaryOut = Field(default_factory=AcademicSubjectManagementSummaryOut)


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
    cms_synced_count: int = 0
    cms_unsynced_count: int = 0
    openedx_course_id: str | None = None
    openedx_cohort_name: str | None = None
    openedx_mapping_source: str | None = None
    openedx_mapping_validation_status: str | None = None
    learning_enrolled_count: int = 0
    learning_active_count: int = 0
    learning_synced_count: int = 0
    learning_not_enrolled_count: int = 0
    learning_avg_progress_percent: float | None = None
    learning_avg_grade_percent: float | None = None
    learning_last_synced_at: datetime | None = None
    learning_component_summaries: list[dict[str, Any]] = Field(default_factory=list)
    learning_alerts: list[str] = Field(default_factory=list)



class AcademicStudentOut(BaseModel):
    id: str
    student_code: str | None = None
    username: str
    email: str | None = None
    full_name: str
    phone: str | None = None
    total_relearn: int = 0
    campus: str | None = None
    branch: str | None = None
    active: bool

    model_config = {'from_attributes': True}


class AcademicTrainingPolicyOut(BaseModel):
    policy_version: str | None = None
    quiz_rule: str | None = None
    final_test_rule: str | None = None
    quiz_total: int = 0
    quiz_passed_count: int = 0
    quiz_failed_count: int = 0
    quiz_late_count: int = 0
    quiz_not_attempted_count: int = 0
    quiz_early_count: int = 0
    quiz_missing_deadline_count: int = 0
    all_quizzes_eligible: bool = False
    assignment_expected: bool = False
    assignment_status: str = 'not_required'
    assignment_score_10: float | None = None
    assignment_note: str = ''
    exam_eligible: bool = False
    exam_status: str = 'insufficient_data'
    exam_status_label: str = 'Chưa đủ dữ liệu'
    exam_reasons: list[str] = Field(default_factory=list)
    exam_notes: list[str] = Field(default_factory=list)
    quiz_results: list[dict[str, Any]] = Field(default_factory=list)
    deadline_mode: str = 'auto'
    deadline_mode_note: str | None = None

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
    learning_snapshot_id: str | None = None
    learning_enrollment_status: str | None = None
    learning_enrollment_mode: str | None = None
    learning_progress_percent: float | None = None
    learning_grade_percent: float | None = None
    learning_passed: bool | None = None
    learning_completed_blocks: int | None = None
    learning_total_blocks: int | None = None
    learning_last_activity_at: datetime | None = None
    learning_last_synced_at: datetime | None = None
    learning_enrollment_synced_at: datetime | None = None
    learning_progress_source: str | None = None
    learning_status: str = 'not_synced'
    learning_sync_note: str | None = None
    learning_diagnostics: dict[str, Any] | None = None
    learning_component_scores: list[dict[str, Any]] = Field(default_factory=list)
    training_policy: AcademicTrainingPolicyOut | None = None
    exam_eligible: bool | None = None
    exam_status: str | None = None
    exam_status_label: str | None = None
    exam_reasons: list[str] = Field(default_factory=list)
    assignment_defense_status: str | None = None
    assignment_score_10: float | None = None


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
    skipped_empty_classes: int = 0
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




class AcademicCampusOut(BaseModel):
    id: str
    campus_code: str
    campus_name: str = ''
    branch: str | None = None
    active: bool = True
    sort_order: int = 0
    metadata_json: dict[str, Any] | None = None

    model_config = {'from_attributes': True}


class AcademicCampusUpsertIn(BaseModel):
    campus_code: str = Field(..., min_length=1, max_length=64, description='Mã cơ sở AP, ví dụ pt/hn/hcm')
    campus_name: str = Field('', max_length=255, description='Tên cơ sở để hiển thị dropdown')
    branch: str = Field('poly', max_length=64)
    active: bool = True
    sort_order: int = 0


class AcademicAPSyncIn(BaseModel):
    term_name: str = Field(..., description='Ví dụ: Summer 2026')
    sync_scope: str = Field('campus', description='all = tất cả cơ sở/tất cả môn; campus = một hoặc nhiều cơ sở; subject = cơ sở + danh sách môn')
    campus: str | None = Field(None, description='Mã cơ sở AP dạng pc/pt/hn/hcm...; giữ để tương thích bản cũ')
    campuses: list[str] = Field(default_factory=list, description='Danh sách cơ sở khi sync_scope=all/campus')
    branch: str = 'poly'
    subject_codes: list[str] = Field(default_factory=list, description='Danh sách mã môn AP psubject_code. Rỗng ở sync_scope=all/campus = backend lấy danh sách môn triển khai từ AP /api/cms/get-subject-cms theo term_name; env ACADEMIC_AP_SUBJECT_CODES chỉ là fallback')
    max_subjects: int = Field(0, ge=0, le=5000, description='0 = không giới hạn; >0 = giới hạn số môn mỗi cơ sở để chia batch an toàn')
    dry_run: bool = False




class AcademicAPOptionOut(BaseModel):
    value: str
    label: str
    description: str | None = None
    meta: dict[str, Any] = Field(default_factory=dict)


class AcademicAPSyncOptionsOut(BaseModel):
    branches: list[AcademicAPOptionOut] = Field(default_factory=list)
    campuses: list[AcademicAPOptionOut] = Field(default_factory=list)
    terms: list[AcademicAPOptionOut] = Field(default_factory=list)
    subjects: list[AcademicAPOptionOut] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

class AcademicHealthOut(BaseModel):
    ok: bool
    terms: int
    classes: int
    students: int
    assignments: int
    last_sync: AcademicSyncRunOut | None = None

class AcademicResolveClassUsersIn(BaseModel):
    force: bool = False
    limit: int = Field(500, ge=1, le=500)


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
    enrollment: dict[str, Any] | None = None
    teachers: dict[str, Any] | None = None



class AcademicEnrollmentSyncIn(BaseModel):
    force: bool = False
    limit: int = Field(500, ge=1, le=500)
    mode: str | None = Field(None, max_length=50, description='Enrollment mode CMS/Open edX, mặc định audit')


class AcademicEnrollmentSyncOut(BaseModel):
    ok: bool
    class_id: str
    openedx_course_id: str | None = None
    total: int
    updated: int
    counts: dict[str, int] = Field(default_factory=dict)
    message: str
    learning_summary: dict[str, Any] | None = None
    teachers: dict[str, Any] | None = None


class AcademicLearningSyncIn(BaseModel):
    force: bool = False
    limit: int = Field(500, ge=1, le=500)


class AcademicFullCmsSyncIn(BaseModel):
    force: bool = False
    limit: int = Field(500, ge=1, le=500)
    mode: str | None = Field(None, max_length=50, description='Enrollment mode CMS/Open edX, mặc định audit')
    auto_map_course: bool = True
    sync_learning: bool = True


class AcademicLearningSummaryOut(BaseModel):
    class_id: str
    openedx_course_id: str | None = None
    total: int
    counts: dict[str, int] = Field(default_factory=dict)
    active_count: int = 0
    avg_progress_percent: float | None = None
    avg_grade_percent: float | None = None
    last_synced_at: datetime | None = None
    component_summaries: list[dict[str, Any]] = Field(default_factory=list)
    status_counts: dict[str, int] = Field(default_factory=dict)
    alert_counts: dict[str, int] = Field(default_factory=dict)
    diagnostic_counts: dict[str, int] = Field(default_factory=dict)
    source_counts: dict[str, int] = Field(default_factory=dict)
    diagnostic_note: str | None = None


class AcademicLearningSyncOut(AcademicLearningSummaryOut):
    ok: bool
    updated: int
    message: str
    connector_counts: dict[str, int] = Field(default_factory=dict)
    connector_diagnostics: dict[str, Any] | None = None


class AcademicFullCmsSyncOut(BaseModel):
    ok: bool
    class_id: str
    openedx_course_id: str | None = None
    status: str = 'completed'
    message: str
    mapping: dict[str, Any] | None = None
    cms_users: dict[str, Any] | None = None
    enrollment: dict[str, Any] | None = None
    learning: dict[str, Any] | None = None
    counts: dict[str, int] = Field(default_factory=dict)
    learning_summary: dict[str, Any] | None = None


class AcademicClassSyncJobOut(BaseModel):
    id: str
    job_type: str
    status: str
    class_id: str
    requested_by: str | None = None
    force: bool = False
    limit: int = 500
    mode: str | None = None
    progress_current: int = 0
    progress_total: int = 100
    progress_label: str = 'Đang chờ xử lý'
    request_json: dict[str, Any] | None = None
    result_json: dict[str, Any] | None = None
    error_message: str | None = None
    created_at: datetime | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {'from_attributes': True}


class AcademicTeacherReportJobOut(BaseModel):
    id: str
    job_type: str
    status: str
    term_id: str | None = None
    branch: str | None = None
    campus: str | None = None
    requested_by: str | None = None
    progress_current: int = 0
    progress_total: int = 100
    progress_label: str = 'Đang chờ xử lý'
    request_json: dict[str, Any] | None = None
    result_json: dict[str, Any] | None = None
    file_path: str | None = None
    file_name: str | None = None
    error_message: str | None = None
    created_at: datetime | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {'from_attributes': True}


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


class AcademicSubjectCourseAutoMapOut(BaseModel):
    ok: bool
    status: str
    message: str
    suggested_openedx_course_id: str | None = None
    candidate_count: int | None = None
    candidate_source: str | None = None
    candidates: list[dict[str, Any]] = Field(default_factory=list)
    mapping: AcademicCourseMappingOut | None = None


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


class AcademicQuizDeadlineOverrideIn(BaseModel):
    id: str | None = None
    course_id: str | None = None
    component_key: str | None = None
    component_label: str = 'Quiz'
    quiz_number: int | None = Field(None, ge=1, le=200)
    start_date: datetime | None = None
    deadline_date: datetime | None = None
    reason: str | None = None


class AcademicQuizDeadlineOverrideBulkIn(BaseModel):
    items: list[AcademicQuizDeadlineOverrideIn] = Field(default_factory=list, max_length=300)


class AcademicQuizDeadlineOverrideOut(BaseModel):
    id: str
    class_id: str
    course_id: str | None = None
    component_key: str | None = None
    component_label: str = ''
    quiz_number: int | None = None
    start_date: datetime | None = None
    deadline_date: datetime | None = None
    reason: str = ''
    created_by: str | None = None
    updated_by: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {'from_attributes': True}


class AcademicAssignmentDefenseScoreIn(BaseModel):
    student_id: str
    course_id: str | None = None
    assignment_key: str | None = None
    assignment_label: str = 'Assignment'
    score_10: float | None = Field(None, ge=0, le=10)
    defense_status: str = Field('not_graded', max_length=50)
    note: str | None = None


class AcademicAssignmentDefenseScoreBulkIn(BaseModel):
    items: list[AcademicAssignmentDefenseScoreIn] = Field(default_factory=list, max_length=2000)


class AcademicAssignmentDefenseScoreOut(BaseModel):
    id: str
    class_id: str
    student_id: str
    student_code: str | None = None
    student_username: str | None = None
    student_name: str | None = None
    course_id: str | None = None
    assignment_key: str | None = None
    assignment_label: str = 'Assignment'
    score_10: float | None = None
    defense_status: str = 'not_graded'
    graded_by: str | None = None
    graded_at: datetime | None = None
    note: str = ''
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {'from_attributes': True}
