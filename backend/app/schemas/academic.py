from __future__ import annotations

from datetime import date, datetime
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
    learning_platform: str = 'cms'
    subject_delivery_id: str | None = None
    udemy_progress_student_count: int = 0
    udemy_progress_late_count: int = 0
    udemy_progress_average_percent: float | None = None
    udemy_progress_last_imported_at: datetime | None = None
    start_date: datetime | None = None
    end_date: datetime | None = None
    exam_cutoff_date: datetime | None = None
    exam_cutoff_source: str | None = None
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
    learning_platform: str = 'cms'
    subject_delivery_ids: list[str] = Field(default_factory=list)
    class_count: int = 0
    campus_count: int = 0
    teacher_count: int = 0
    student_count: int = 0
    cms_synced_count: int = 0
    cms_unsynced_count: int = 0
    course_mapping_status: str = 'not_found'
    course_mapping_label: str = ''
    openedx_course_id: str | None = None
    openedx_org: str | None = None
    openedx_course_ids: list[str] = Field(default_factory=list)
    openedx_orgs: list[str] = Field(default_factory=list)
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
    udemy_progress_student_count: int = 0
    udemy_progress_late_count: int = 0
    udemy_progress_unmatched_count: int = 0
    udemy_progress_average_percent: float | None = None
    udemy_progress_last_imported_at: datetime | None = None


class AcademicSubjectDeliveryBlockOut(BaseModel):
    id: str
    block_id: str
    block_name: str
    learning_platform: str | None = None
    class_count: int = 0
    campus_count: int = 0
    has_udemy_plan: bool = False
    udemy_plan_version: int | None = None
    udemy_milestone_count: int = 0
    udemy_progress_student_count: int = 0
    udemy_progress_late_count: int = 0
    udemy_progress_unmatched_count: int = 0
    last_udemy_import_at: datetime | None = None


class AcademicSubjectDeliveryOut(BaseModel):
    id: str
    subject_id: str
    ap_subject_id: str | None = None
    subject_code: str
    subject_name: str
    subject_name_en: str | None = None
    skill_code: str | None = None
    term_id: str
    term_name: str
    block_id: str
    block_name: str
    branch: str
    learning_platform: str | None = None
    active: bool = True
    configuration_source: str = 'manual'
    configured_by: str | None = None
    configured_at: datetime | None = None
    catalog_refreshed_at: datetime | None = None
    class_count: int = 0
    campus_count: int = 0
    has_udemy_plan: bool = False
    udemy_plan_id: str | None = None
    udemy_plan_version: int | None = None
    udemy_item_count: int | None = None
    udemy_milestone_count: int = 0
    udemy_plan_updated_at: datetime | None = None
    last_udemy_import_at: datetime | None = None
    udemy_progress_student_count: int = 0
    udemy_progress_late_count: int = 0
    udemy_progress_unmatched_count: int = 0
    metadata_json: dict[str, Any] | None = None
    delivery_ids: list[str] = Field(default_factory=list)
    block_count: int = 1
    block_names: list[str] = Field(default_factory=list)
    platform_consistent: bool = True
    platform_values: list[str | None] = Field(default_factory=list)
    management_scope: str = 'delivery'
    block_deliveries: list[AcademicSubjectDeliveryBlockOut] = Field(default_factory=list)
    created_at: datetime | None = None
    updated_at: datetime | None = None


class AcademicSubjectDeliverySummaryOut(BaseModel):
    total: int = 0
    cms_count: int = 0
    udemy_count: int = 0
    unassigned_count: int = 0
    mixed_count: int = 0
    class_count: int = 0
    scope_label: str = 'Toàn bộ bộ lọc'


class AcademicSubjectDeliveryListOut(BaseModel):
    items: list[AcademicSubjectDeliveryOut] = Field(default_factory=list)
    total: int = 0
    page: int = 1
    page_size: int = 50
    total_pages: int = 0
    has_next: bool = False
    summary: AcademicSubjectDeliverySummaryOut = Field(default_factory=AcademicSubjectDeliverySummaryOut)


class AcademicSubjectCatalogRefreshIn(BaseModel):
    term_id: str = Field(..., min_length=1)
    block_id: str | None = None
    branch: str = Field('poly', min_length=1, max_length=64)

    @field_validator('branch')
    @classmethod
    def _normalize_branch(cls, value: str) -> str:
        normalized = str(value or 'poly').strip().lower()
        if normalized not in {'poly', 'ptcd'}:
            raise ValueError('Hệ chỉ nhận poly hoặc ptcd')
        return normalized


class AcademicSubjectCatalogRefreshOut(BaseModel):
    ok: bool
    message: str
    job_id: str
    status: str
    term_id: str
    block_id: str | None = None
    branch: str


class AcademicSubjectPlatformUpdateIn(BaseModel):
    learning_platform: str | None = None

    @field_validator('learning_platform')
    @classmethod
    def _validate_platform(cls, value: str | None) -> str | None:
        if value is None or not str(value).strip():
            return None
        normalized = str(value).strip().lower()
        if normalized not in {'cms', 'udemy'}:
            raise ValueError('Nền tảng chỉ nhận cms, udemy hoặc null')
        return normalized


class AcademicSubjectPlatformBulkIn(AcademicSubjectPlatformUpdateIn):
    delivery_ids: list[str] = Field(default_factory=list, min_length=1, max_length=2000)


class AcademicSubjectPlatformMutationOut(BaseModel):
    ok: bool
    message: str
    updated: int = 0
    items: list[AcademicSubjectDeliveryOut] = Field(default_factory=list)



class UdemyPlanMilestoneIn(BaseModel):
    week_number: int = Field(..., ge=1, le=52)
    deadline_date: date
    required_progress_percent: float = Field(..., ge=0, le=100)


class UdemyPlanMilestoneOut(UdemyPlanMilestoneIn):
    id: str | None = None
    metadata_json: dict[str, Any] | None = None


class UdemySubjectPlanOut(BaseModel):
    id: str
    subject_delivery_id: str
    version: int
    item_count: int
    active: bool
    source: str
    source_file_name: str | None = None
    source_file_hash: str | None = None
    imported_by: str | None = None
    imported_at: datetime | None = None
    note: str | None = None
    metadata_json: dict[str, Any] | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    milestones: list[UdemyPlanMilestoneOut] = Field(default_factory=list)


class UdemyPlanDeliveryOut(BaseModel):
    id: str
    subject_id: str
    subject_code: str
    subject_name: str
    term_id: str
    term_name: str
    block_id: str
    block_name: str
    branch: str
    learning_platform: str | None = None


class UdemyPlanDetailOut(BaseModel):
    delivery: UdemyPlanDeliveryOut
    active_plan: UdemySubjectPlanOut | None = None


class UdemyPlanVersionCreateIn(BaseModel):
    item_count: int = Field(..., ge=1, le=100000)
    milestones: list[UdemyPlanMilestoneIn] = Field(default_factory=list, min_length=1, max_length=52)
    note: str | None = Field(None, max_length=2000)


class UdemyPlanImportPreviewIssueOut(BaseModel):
    row: int | None = None
    subject_code: str | None = None
    code: str
    message: str


class UdemyPlanImportPreviewRowOut(BaseModel):
    row_no: int
    delivery_id: str | None = None
    term_name: str
    block_name: str
    branch: str
    subject_code: str
    subject_name: str | None = None
    item_count: int
    current_version: int | None = None
    next_version: int
    action: str
    milestones: list[UdemyPlanMilestoneIn] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class UdemyPlanImportPreviewOut(BaseModel):
    ok: bool = True
    preview_token: str
    filename: str
    file_sha256: str
    branch: str
    total_rows: int
    valid_count: int
    error_count: int
    warning_count: int
    can_commit: bool
    rows: list[UdemyPlanImportPreviewRowOut] = Field(default_factory=list)
    errors: list[UdemyPlanImportPreviewIssueOut] = Field(default_factory=list)
    warnings: list[UdemyPlanImportPreviewIssueOut] = Field(default_factory=list)
    message: str


class UdemyPlanImportCommitIn(BaseModel):
    preview_token: str = Field(..., min_length=32, max_length=32)


class UdemyPlanMutationOut(BaseModel):
    ok: bool
    message: str
    created_count: int = 0
    plans: list[UdemySubjectPlanOut] = Field(default_factory=list)


class UdemyProgressImportBatchOut(BaseModel):
    id: str
    parent_job_id: str | None = None
    subject_delivery_id: str
    subject_code: str | None = None
    subject_name: str | None = None
    duplicate_of_batch_id: str | None = None
    file_name: str
    file_hash: str
    file_size_bytes: int = 0
    parser_format: str | None = None
    status: str
    force_reimport: bool = False
    total_rows: int = 0
    processed_rows: int = 0
    matched_rows: int = 0
    outside_roster_rows: int = 0
    unmatched_rows: int = 0
    ambiguous_rows: int = 0
    failed_rows: int = 0
    requested_by: str | None = None
    result_json: dict[str, Any] | None = None
    error_message: str | None = None
    error_report_available: bool = False
    started_at: datetime | None = None
    finished_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class UdemyProgressImportRejectedFileOut(BaseModel):
    file_name: str
    source_archive: str | None = None
    reason_code: str
    message: str
    detected_subject_code: str | None = None
    detected_term_code: str | None = None


class UdemyProgressImportJobOut(BaseModel):
    ok: bool
    message: str
    job_id: str
    status: str
    queued_count: int = 0
    duplicate_count: int = 0
    rejected_count: int = 0
    rejected_files: list[UdemyProgressImportRejectedFileOut] = Field(default_factory=list)
    batches: list[UdemyProgressImportBatchOut] = Field(default_factory=list)


class UdemyProgressSummaryOut(BaseModel):
    subject_delivery_id: str
    total_students: int = 0
    matched_students: int = 0
    outside_roster_students: int = 0
    ambiguous_students: int = 0
    unmatched_students: int = 0
    late_students: int = 0
    on_track_students: int = 0
    no_plan_students: int = 0
    average_progress_percent: float | None = None
    required_progress_percent: float | None = None
    current_plan_week: int | None = None
    current_deadline_date: date | None = None
    last_imported_at: datetime | None = None
    class_count: int = 0
    scope_label: str = 'Toàn bộ môn'


class UdemyProgressClassOptionOut(BaseModel):
    id: str
    class_code: str
    class_name: str | None = None
    campus: str | None = None


class UdemyProgressStudentOut(BaseModel):
    id: str
    student_id: str | None = None
    student_code: str | None = None
    student_username: str | None = None
    display_name: str
    email: str
    class_id: str | None = None
    class_code: str | None = None
    class_name: str | None = None
    campus: str | None = None
    teacher_names: list[str] = Field(default_factory=list)
    progress_percent: float = 0
    required_progress_percent: float | None = None
    variance_percent: float | None = None
    is_late: bool | None = None
    status: str
    status_label: str
    match_status: str
    current_plan_week: int | None = None
    current_deadline_date: date | None = None
    last_import_batch_id: str
    source_format: str
    last_imported_at: datetime
    diagnostic: str | None = None


class UdemyProgressStudentListOut(BaseModel):
    items: list[UdemyProgressStudentOut] = Field(default_factory=list)
    total: int = 0
    page: int = 1
    page_size: int = 50
    total_pages: int = 0
    has_next: bool = False


class UdemyProgressDashboardOut(BaseModel):
    delivery: UdemyPlanDeliveryOut
    summary: UdemyProgressSummaryOut
    active_plan: dict[str, Any] | None = None
    classes: list[UdemyProgressClassOptionOut] = Field(default_factory=list)
    recent_imports: list[UdemyProgressImportBatchOut] = Field(default_factory=list)


class AcademicSubjectManagementSummaryOut(BaseModel):
    learning_platform: str = 'cms'
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
    udemy_progress_student_count: int = 0
    udemy_progress_late_count: int = 0
    udemy_progress_unmatched_count: int = 0
    udemy_progress_average_percent: float | None = None
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
    learning_platform: str = 'cms'
    subject_delivery_id: str | None = None
    udemy_progress_student_count: int = 0
    udemy_progress_late_count: int = 0
    udemy_progress_average_percent: float | None = None
    udemy_progress_last_imported_at: datetime | None = None
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
    learning_platform: str | None = None
    subject_delivery_id: str | None = None
    udemy_progress_student_count: int = 0
    udemy_progress_late_count: int = 0
    udemy_progress_average_percent: float | None = None
    udemy_progress_last_imported_at: datetime | None = None



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
    summary: dict[str, Any] | None = None


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


class AcademicCampusUpdateIn(BaseModel):
    campus_code: str | None = Field(None, min_length=1, max_length=64)
    campus_name: str | None = Field(None, max_length=255)
    branch: str | None = Field(None, max_length=64)
    active: bool | None = None
    sort_order: int | None = None


class AcademicAPSyncIn(BaseModel):
    term_name: str = Field(..., description='Ví dụ: Summer 2026')
    sync_scope: str = Field('campus', description='all = tất cả cơ sở nhưng chỉ các môn đã chọn CMS/Udemy; campus = một hoặc nhiều cơ sở với tập môn đã chọn; subject = cơ sở + danh sách môn đã chọn cụ thể')
    campus: str | None = Field(None, description='Mã cơ sở AP dạng pc/pt/hn/hcm...; giữ để tương thích bản cũ')
    campuses: list[str] = Field(default_factory=list, description='Danh sách cơ sở khi sync_scope=all/campus')
    branch: str = 'poly'
    subject_codes: list[str] = Field(default_factory=list, description='Danh sách mã môn AP. Nếu rỗng, backend tự lấy đúng các môn đã chọn CMS hoặc Udemy trong Quản lý môn học của kỳ/hệ; không đồng bộ môn Chưa chọn. Nếu truyền mã môn cụ thể, mọi mã vẫn phải thuộc tập đã chọn CMS/Udemy.')
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
    selected_subject_codes: list[str] = Field(default_factory=list, description='Mã môn đã được chọn CMS hoặc Udemy trong Quản lý môn học của kỳ/hệ.')
    selected_subject_count: int = 0
    cms_subject_count: int = 0
    udemy_subject_count: int = 0

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


class AcademicProgressEmailRecipientOut(BaseModel):
    student_id: str
    student_code: str | None = None
    full_name: str = ''
    masked_email: str | None = None
    progress_percent: float | None = None
    grade_percent: float | None = None
    overdue_quiz_count: int = 0
    overdue_quizzes: list[str] = Field(default_factory=list)
    last_synced_at: datetime | None = None
    deliverable: bool = False
    delivery_issue: str | None = None
    total_relearn: int = 0


class AcademicProgressEmailPreviewOut(BaseModel):
    class_id: str
    class_code: str | None = None
    subject_code: str | None = None
    subject_name: str | None = None
    openedx_course_id: str
    generated_at: datetime
    mail_configured: bool = False
    max_recipients: int = 1000
    roster_total: int = 0
    candidate_count: int = 0
    deliverable_count: int = 0
    missing_email_count: int = 0
    inactive_student_count: int = 0
    duplicate_email_count: int = 0
    no_learning_data_count: int = 0
    recipients: list[AcademicProgressEmailRecipientOut] = Field(default_factory=list)
    default_subject: str
    default_body_template: str
    refresh_before_send: bool = True
    policy_note: str


class AcademicProgressEmailJobIn(BaseModel):
    class_id: str | None = Field(None, max_length=255)
    student_ids: list[str] = Field(..., min_length=1, max_length=1000)
    subject: str = Field(..., min_length=1, max_length=200)
    body_template: str = Field(..., min_length=1, max_length=12000)
    request_key: str | None = Field(None, max_length=128)

    @field_validator('student_ids')
    @classmethod
    def _unique_student_ids(cls, values: list[str]) -> list[str]:
        normalized = list(dict.fromkeys(str(value or '').strip() for value in values if str(value or '').strip()))
        if not normalized:
            raise ValueError('Phải chọn ít nhất một sinh viên.')
        return normalized

    @field_validator('subject')
    @classmethod
    def _safe_subject(cls, value: str) -> str:
        normalized = ' '.join(str(value or '').replace('\r', ' ').replace('\n', ' ').split())
        if not normalized:
            raise ValueError('Tiêu đề email không được để trống.')
        return normalized

    @field_validator('body_template')
    @classmethod
    def _safe_body_template(cls, value: str) -> str:
        normalized = str(value or '').strip()
        if not normalized:
            raise ValueError('Nội dung email không được để trống.')
        return normalized


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


class AcademicIdentityReconciliationItemOut(BaseModel):
    student_id: str
    student_code: str | None = None
    full_name: str = ''
    email: str | None = None
    ap_username: str | None = None
    canonical_username: str
    openedx_username: str | None = None
    openedx_user_id: str | None = None
    openedx_is_active: bool | None = None
    match_status: str = 'not_checked'
    match_method: str = 'not_checked'
    status: str
    severity: str
    can_enroll: bool = False
    recommended_action: str
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    duplicate_rollnumber_count: int = 0
    duplicate_canonical_mapping_count: int = 0


class AcademicIdentityReconciliationOut(BaseModel):
    ok: bool = True
    class_id: str
    class_code: str | None = None
    status: str
    message: str
    policy: str = 'rollnumber_canonical_username'
    dry_run: bool = True
    mutation_performed: bool = False
    counts: dict[str, int] = Field(default_factory=dict)
    total: int = 0
    page: int = 1
    page_size: int = 200
    total_pages: int = 1
    has_next: bool = False
    items: list[AcademicIdentityReconciliationItemOut] = Field(default_factory=list)
    next_actions: list[str] = Field(default_factory=list)


class AcademicIdentityCleanupIn(BaseModel):
    dry_run: bool = True
    confirm_phrase: str | None = None
    statuses: list[str] = Field(
        default_factory=lambda: ['LEGACY_AP_USERNAME', 'CMS_USERNAME_MISMATCH', 'DUPLICATE_CMS_MAPPING', 'CANONICAL_INACTIVE'],
        max_length=12,
    )
    student_ids: list[str] = Field(default_factory=list, max_length=1000)
    delete_wrong_learning_snapshots: bool = True


class AcademicIdentityCleanupOut(BaseModel):
    ok: bool = True
    class_id: str
    class_code: str | None = None
    dry_run: bool = True
    mutation_performed: bool = False
    destructive_allowed: bool = False
    confirm_phrase_required: str = 'DELETE_WRONG_UAT_IDENTITY'
    policy: str = 'uat_rollnumber_identity_cleanup'
    counts: dict[str, int] = Field(default_factory=dict)
    deleted_mapping_ids: list[str] = Field(default_factory=list)
    deleted_snapshot_ids: list[str] = Field(default_factory=list)
    skipped: list[dict[str, Any]] = Field(default_factory=list)
    items: list[AcademicIdentityReconciliationItemOut] = Field(default_factory=list)
    message: str = ''
    next_actions: list[str] = Field(default_factory=list)


class AcademicIdentityMigrationItemOut(AcademicIdentityReconciliationItemOut):
    class_id: str
    class_code: str | None = None
    class_name: str | None = None
    term_id: str | None = None
    term_name: str | None = None
    subject_id: str | None = None
    subject_code: str | None = None
    subject_name: str | None = None
    campus: str | None = None
    branch: str | None = None


class AcademicIdentityMigrationOut(BaseModel):
    ok: bool = True
    status: str
    message: str
    policy: str = 'rollnumber_identity_migration_assistant'
    dry_run: bool = True
    mutation_performed: bool = False
    scope: dict[str, Any] = Field(default_factory=dict)
    counts: dict[str, int] = Field(default_factory=dict)
    severity_counts: dict[str, int] = Field(default_factory=dict)
    total: int = 0
    scanned: int = 0
    page: int = 1
    page_size: int = 200
    total_pages: int = 1
    has_next: bool = False
    items: list[AcademicIdentityMigrationItemOut] = Field(default_factory=list)
    next_actions: list[str] = Field(default_factory=list)
    export_hints: dict[str, Any] = Field(default_factory=dict)


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
    previous_course_cleanup: dict[str, Any] | None = None
    next_effective_openedx_course_id: str | None = None
    learning_snapshots_cleared: bool | None = None
    cache_invalidated: dict[str, Any] | None = None

    model_config = {'from_attributes': True}


class AcademicCourseMappingListOut(BaseModel):
    items: list[AcademicCourseMappingOut]
    total: int
    page: int = 1
    page_size: int = 50
    total_pages: int = 1
    has_next: bool = False




class AcademicSubjectAutoMapAllSyncIn(BaseModel):
    term_id: str
    branch: str | None = None
    campus: str | None = None
    search: str | None = None
    learning_status: str | None = None
    force: bool = True
    limit: int = Field(500, ge=1, le=500)
    mode: str | None = Field(None, max_length=50, description='Enrollment mode CMS/Open edX, mặc định audit')
    sync_learning: bool = True
    max_classes: int = Field(3000, ge=1, le=5000)


class AcademicSubjectAutoMapAllSyncOut(BaseModel):
    ok: bool
    message: str
    job_id: str | None = None
    status: str | None = None
    term_id: str
    branch: str | None = None
    campus: str | None = None
    subject_total: int = 0
    subject_mapped: int = 0
    subject_already_mapped: int = 0
    subject_failed: int = 0
    class_total: int = 0
    jobs_queued: int = 0
    jobs_reused: int = 0
    jobs_skipped: int = 0
    capped: bool = False
    subject_results: list[dict[str, Any]] = Field(default_factory=list)
    job_ids: list[str] = Field(default_factory=list)


class AcademicBulkOperationJobOut(BaseModel):
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
    error_message: str | None = None
    created_at: datetime | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {'from_attributes': True}


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
    cleanup_previous_course: bool = False
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
