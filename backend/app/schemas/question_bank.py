from datetime import datetime
from typing import Generic, Literal, TypeVar
from pydantic import BaseModel, Field

T = TypeVar('T')


class PaginatedOut(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int
    total_pages: int
    has_next: bool = False


class CursorPaginatedOut(BaseModel, Generic[T]):
    items: list[T]
    limit: int
    has_next: bool = False
    next_cursor: dict | None = None
    total: int | None = None



class DepartmentCreate(BaseModel):
    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=255)
    description: str = ''


class DepartmentUpdate(BaseModel):
    code: str | None = Field(default=None, min_length=1, max_length=64)
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None


class SubjectUpdate(BaseModel):
    code: str | None = Field(default=None, min_length=1, max_length=64)
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None


class SubjectOfferingUpdate(BaseModel):
    code: str | None = Field(default=None, min_length=1, max_length=128)
    name: str | None = Field(default=None, max_length=255)
    term: str | None = None
    version_code: str | None = Field(default=None, max_length=64)
    description: str | None = None


class ChapterUpdate(BaseModel):
    # UI can send either full title (Bài 1.1) or a renamed title.
    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    sort_order: int | None = Field(default=None, ge=1)


class EntityDeleteOut(BaseModel):
    ok: bool
    deleted: bool
    entity_type: str
    entity_id: str
    message: str


class DepartmentOut(DepartmentCreate):
    id: str
    status: str
    created_at: datetime
    updated_at: datetime
    class Config:
        from_attributes = True


class SubjectCreate(BaseModel):
    department_id: str
    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=255)
    description: str = ''


class SubjectOut(SubjectCreate):
    id: str
    status: str
    created_at: datetime
    updated_at: datetime
    class Config:
        from_attributes = True


class SubjectOfferingCreate(BaseModel):
    subject_id: str
    # code may be omitted; backend will generate DOM123_SP25 / DOM123_SU26 / DOM123_FA27.
    code: str = Field(default='', max_length=128)
    name: str = Field(default='', max_length=255)
    # Term/version layer. Examples: SP25 = Spring 2025, SU26 = Summer 2026, FA27 = Fall 2027.
    term: str | None = None
    season: str | None = None
    year: int | str | None = None
    version_code: str = Field(default='', max_length=64)
    based_on_offering_id: str | None = None
    clone_from_offering_id: str | None = None
    # Deprecated compatibility fields. If clone_from_offering_id is provided,
    # backend always performs an exact working-copy clone. Release is not cloned.
    clone_chapters: bool = True
    clone_materials: bool = True
    clone_questions: bool = True
    description: str = ''


class SubjectOfferingOut(BaseModel):
    id: str
    department_id: str | None = None
    subject_id: str
    code: str
    name: str
    term: str | None = None
    version_code: str
    based_on_offering_id: str | None = None
    status: str
    metadata_json: dict | None = None
    created_by: str | None = None
    approved_by: str | None = None
    published_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    class Config:
        from_attributes = True


class ChapterCreate(BaseModel):
    subject_id: str
    subject_offering_id: str | None = None
    # Internal ordering number. UI does not ask teachers to enter this.
    chapter_no: int | None = Field(default=None, ge=1)
    title: str = Field(min_length=1, max_length=255)
    description: str = ''
    sort_order: int | None = Field(default=None, ge=1)


class ChapterOut(ChapterCreate):
    id: str
    status: str
    created_at: datetime
    updated_at: datetime
    class Config:
        from_attributes = True


class BankVersionCreate(BaseModel):
    subject_id: str
    chapter_id: str
    subject_offering_id: str | None = None
    version_code: str = Field(default='v1.0', max_length=64)
    title: str = ''
    change_note: str = ''
    based_on_version_id: str | None = None


class BankVersionOut(BankVersionCreate):
    id: str
    version_no: int
    status: str
    created_by: str | None = None
    approved_by: str | None = None
    published_at: datetime | None = None
    metadata_json: dict | None = None
    created_at: datetime
    updated_at: datetime
    class Config:
        from_attributes = True


class MaterialVersionCreate(BaseModel):
    subject_id: str
    chapter_id: str
    bank_version_id: str
    title: str = ''
    file_name: str = ''
    file_type: str = 'unknown'
    storage_path: str = ''
    content_hash: str | None = None
    version_no: int = Field(default=1, ge=1)
    change_type: str = 'initial'


class MaterialVersionOut(MaterialVersionCreate):
    id: str
    uploaded_by: str | None = None
    status: str
    created_at: datetime
    class Config:
        from_attributes = True


class BankReleaseCreate(BaseModel):
    bank_version_id: str
    release_code: str | None = None
    title: str = ''
    include_approved_questions: bool = True
    force: bool = False  # chỉ dùng khi admin cố tình bỏ qua cảnh báo chốt release


class BankReleasePublishRequest(BaseModel):
    openedx_course_id_for_org: str | None = None
    force_reimport: bool = False


class BankReleasePublishOut(BaseModel):
    ok: bool
    release_id: str
    release_code: str
    status: str
    openedx_library_key: str | None = None
    question_count: int
    imported_now_count: int
    skipped_existing_count: int
    verified_existing_count: int = 0
    verification_warnings: list[dict] = Field(default_factory=list)
    library_result: dict | None = None
    imported: list[dict] = Field(default_factory=list)
    errors: list[dict] = Field(default_factory=list)


class MappingCheckOut(BaseModel):
    code: str
    status: str
    message: str
    blocking: bool = False
    detail: dict = Field(default_factory=dict)


class MappingValidationOut(BaseModel):
    ok: bool
    risk_level: str
    checks: list[MappingCheckOut]
    can_create_mapping: bool
    message: str


class CourseMappingValidateRequest(BaseModel):
    openedx_course_id: str = Field(min_length=1, max_length=255)
    subject_id: str
    subject_offering_id: str | None = None
    department_id: str | None = None
    term: str | None = None
    openedx_course_title: str | None = None


class CourseChapterMappingValidateRequest(BaseModel):
    course_mapping_id: str
    subject_chapter_id: str
    bank_release_id: str
    openedx_parent_node_id: str = Field(min_length=1, max_length=512)
    openedx_node_title: str | None = None


class BankReleaseOut(BaseModel):
    id: str
    bank_version_id: str
    subject_id: str
    chapter_id: str
    release_code: str
    title: str
    status: str
    approved_question_count: int
    easy_count: int
    medium_count: int
    hard_count: int
    family_count: int
    openedx_library_key: str | None = None
    openedx_library_version: int | None = None
    publish_batch_id: str | None = None
    published_at: datetime | None = None
    published_by: str | None = None
    metadata_json: dict | None = None
    created_at: datetime
    updated_at: datetime
    class Config:
        from_attributes = True


class BankReleasePreviewQuestionOut(BaseModel):
    release_question_id: str
    question_id: str
    question_text: str
    option_a: str | None = None
    option_b: str | None = None
    option_c: str | None = None
    option_d: str | None = None
    correct_answer: str
    difficulty: str
    concept_title: str | None = None
    question_family_id: str | None = None
    included_at: datetime | None = None


class BankReleasePreviewOut(BaseModel):
    release: BankReleaseOut
    frozen_snapshot: bool = True
    total_questions: int
    counts: dict = Field(default_factory=dict)
    questions: list[BankReleasePreviewQuestionOut] = Field(default_factory=list)


class CourseMappingCreate(BaseModel):
    openedx_course_id: str = Field(min_length=1, max_length=255)
    subject_id: str
    subject_offering_id: str | None = None
    department_id: str | None = None
    term: str | None = None
    openedx_course_title: str | None = None
    allow_warnings: bool = False


class CourseMappingOut(BaseModel):
    id: str
    openedx_course_id: str
    department_id: str | None = None
    subject_id: str
    term: str | None = None
    status: str
    validation_status: str = 'not_validated'
    validation_json: dict | None = None
    validated_at: datetime | None = None
    created_by: str | None = None
    created_at: datetime
    updated_at: datetime
    class Config:
        from_attributes = True


class CourseChapterMappingCreate(BaseModel):
    course_mapping_id: str
    subject_chapter_id: str
    bank_release_id: str | None = None
    openedx_parent_node_id: str | None = None
    openedx_node_title: str | None = None
    enabled: bool = True
    allow_warnings: bool = False


class CourseChapterMappingOut(BaseModel):
    id: str
    course_mapping_id: str
    subject_chapter_id: str
    bank_release_id: str | None = None
    openedx_parent_node_id: str | None = None
    enabled: bool
    validation_status: str = 'not_validated'
    validation_json: dict | None = None
    validated_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    class Config:
        from_attributes = True


class QuizBlueprintCreate(BaseModel):
    subject_id: str
    chapter_id: str
    subject_offering_id: str | None = None
    title: str = Field(min_length=1, max_length=255)
    total_questions: int = Field(default=15, ge=1, le=200)
    difficulty_easy: int = Field(default=50, ge=0, le=100)
    difficulty_medium: int = Field(default=30, ge=0, le=100)
    difficulty_hard: int = Field(default=20, ge=0, le=100)
    max_families_per_bank: int = Field(default=2, ge=1, le=5)
    pick_count_per_slot: int = Field(default=1, ge=1, le=5)


class QuizBlueprintOut(QuizBlueprintCreate):
    id: str
    status: str
    created_at: datetime
    updated_at: datetime
    class Config:
        from_attributes = True


class BankSummaryOut(BaseModel):
    departments: int
    subjects: int
    subject_offerings: int = 0
    chapters: int
    bank_versions: int
    releases: int
    published_releases: int
    course_mappings: int = 0
    quiz_blueprints: int = 0
    material_versions: int = 0
    material_chunks: int = 0
    bank_questions: int = 0
    bank_diffs: int = 0
    carry_over_questions: int = 0
    retired_questions: int = 0


class MaterialChunkOut(BaseModel):
    id: str
    material_version_id: str
    bank_version_id: str
    subject_id: str
    chapter_id: str
    chunk_index: int
    content: str
    token_count: int
    source_type: str
    page_number: int | None = None
    source_ref: str
    content_hash: str | None = None
    created_at: datetime
    class Config:
        from_attributes = True




class MaterialDeleteOut(BaseModel):
    ok: bool
    material_version_id: str
    bank_version_id: str
    deletion_mode: str = 'soft'  # hard | soft
    chunks_deleted: int = 0
    detached_question_count: int = 0
    concepts_detached_count: int = 0
    jobs_detached_count: int = 0
    file_deleted: bool = False
    file_delete_skipped: bool = False
    auto_retire_result: dict | None = None
    message: str

class MaterialUploadOut(BaseModel):
    ok: bool
    reused_existing: bool = False
    material_version: MaterialVersionOut
    chunks_created: int
    tokens_indexed: int
    source_types: list[str] = Field(default_factory=list)
    diff_required: bool = False
    diff_base_bank_version_id: str | None = None
    document_change_state: str | None = None
    auto_retire_result: dict | None = None
    message: str


class BankGenerateRequest(BaseModel):
    question_count: int = Field(default=10, ge=1, le=100)
    target_question_count: int | None = Field(default=100, ge=1, le=100)
    difficulty_easy: int = Field(default=50, ge=0, le=100)
    difficulty_medium: int = Field(default=30, ge=0, le=100)
    difficulty_hard: int = Field(default=20, ge=0, le=100)
    material_version_ids: list[str] | None = None
    provider: str = 'openai'
    approve_after_generate: bool = False


class BankGeneratePreviewOut(BaseModel):
    ok: bool
    bank_version_id: str
    chapter_id: str
    question_count: int
    difficulty_counts: dict
    material_balancing: list[dict] = Field(default_factory=list)
    current_question_count: int
    chapter_question_limit: int
    remaining_quota: int
    estimated_input_tokens: int
    estimated_cached_input_tokens: int = 0
    estimated_output_tokens: int
    estimated_raw_cost_usd: float = 0
    estimated_cost_usd: float
    estimated_cost_vnd: float
    model_name: str
    pricing: dict | None = None
    token_source: str = 'local_bank_generation_estimate'
    message: str


class BankGenerateOut(BaseModel):
    ok: bool
    bank_version_id: str
    requested_questions: int
    created_questions: int
    pending_review_count: int
    approved_count: int
    draft_error_count: int
    input_chunks: int
    input_tokens: int
    difficulty_counts: dict
    material_balancing: list[dict] = Field(default_factory=list)
    questions: list[str] = Field(default_factory=list)
    usage: list[dict] = Field(default_factory=list)
    errors: list[dict] = Field(default_factory=list)
    message: str


class BankQuestionListItemOut(BaseModel):
    id: str
    bank_version_id: str | None = None
    subject_id: str | None = None
    subject_chapter_id: str | None = None
    difficulty: str
    status: str
    question_text_preview: str
    option_a_preview: str | None = None
    option_b_preview: str | None = None
    option_c_preview: str | None = None
    option_d_preview: str | None = None
    correct_answer: str
    concept_title: str | None = None
    question_family_id: str | None = None
    variant_no: int | None = None
    quality_score: float
    draft_error_reason: str | None = None
    is_duplicate: bool | None = None
    is_retired: bool | None = None
    previous_question_id: str | None = None
    lineage_root_question_id: str | None = None
    question_revision_no: int | None = None
    is_carry_over: bool | None = None
    created_at: datetime


class BankVersionQuestionOut(BaseModel):
    id: str
    bank_version_id: str | None = None
    subject_id: str | None = None
    subject_chapter_id: str | None = None
    material_version_id: str | None = None
    concept_version_id: str | None = None
    concept_title: str | None = None
    question_family_id: str | None = None
    variant_no: int | None = None
    difficulty: str
    cognitive_level: str | None = None
    learning_objective: str | None = None
    question_type: str | None = None
    question_text: str
    option_a: str | None = None
    option_b: str | None = None
    option_c: str | None = None
    option_d: str | None = None
    correct_answer: str
    explanation: str | None = None
    source_ref: str | None = None
    source_type: str | None = None
    source_excerpt: str | None = None
    source_evidence: str | None = None
    status: str
    reviewed_by: str | None = None
    reviewed_at: datetime | None = None
    quality_score: float
    quality_flags: list[str] | None = None
    draft_error_reason: str | None = None
    draft_error_detail: dict | None = None
    is_duplicate: bool | None = None
    duplicate_score: float | None = None
    duplicate_of_question_id: str | None = None
    previous_question_id: str | None = None
    lineage_root_question_id: str | None = None
    question_revision_no: int | None = None
    is_carry_over: bool | None = None
    is_retired: bool | None = None
    retired_reason: str | None = None
    retired_at: datetime | None = None
    created_at: datetime
    class Config:
        from_attributes = True


class BankQuestionDetailOut(BankVersionQuestionOut):
    pass


class BankVersionDiffPreviewRequest(BaseModel):
    base_bank_version_id: str | None = None
    persist: bool = False  # compatibility only; preview endpoints never persist


class BankVersionDiffCreateRequest(BaseModel):
    base_bank_version_id: str | None = None


class BankVersionDiffSummaryOut(BaseModel):
    from_bank_version_id: str
    to_bank_version_id: str
    from_version_code: str | None = None
    to_version_code: str | None = None
    material_similarity: float | None = None
    source_material_count: int = 0
    target_material_count: int = 0
    exact_shared_material_count: int = 0
    unchanged_concept_count: int = 0
    changed_concept_count: int = 0
    new_concept_count: int = 0
    removed_concept_count: int = 0
    source_approved_question_count: int = 0
    carry_over_candidate_count: int = 0
    retire_candidate_count: int = 0
    review_candidate_count: int = 0
    already_exists_count: int = 0
    recommendation: str | None = None
    changed_concepts: list[str] = Field(default_factory=list)
    new_concepts: list[str] = Field(default_factory=list)
    removed_concepts: list[str] = Field(default_factory=list)


class BankVersionDiffPreviewOut(BaseModel):
    ok: bool
    diff_id: str | None = None
    summary: BankVersionDiffSummaryOut
    material_similarity: float | None = None
    carry_over_candidates: list[str] = Field(default_factory=list)
    retire_candidates: list[str] = Field(default_factory=list)
    review_candidates: list[str] = Field(default_factory=list)
    already_exists: list[str] = Field(default_factory=list)
    message: str


class BankCarryOverRequest(BaseModel):
    base_bank_version_id: str
    question_ids: list[str] | None = None
    require_review: bool = False  # deprecated; carry-over accepted by policy
    diff_id: str | None = None


class BankCarryOverOut(BaseModel):
    ok: bool
    created_count: int
    skipped_count: int
    created_question_ids: list[str] = Field(default_factory=list)
    skipped: list[dict] = Field(default_factory=list)
    message: str


class BankRetireQuestionsRequest(BaseModel):
    question_ids: list[str]
    reason: str = 'retired_by_version_diff'


class BankRetireQuestionsOut(BaseModel):
    ok: bool
    retired_count: int = 0
    retired_question_ids: list[str] = Field(default_factory=list)
    source_question_ids: list[str] = Field(default_factory=list)
    excluded_count: int = 0
    excluded_question_ids: list[str] = Field(default_factory=list)
    skipped: list[dict] = Field(default_factory=list)
    message: str


class BankQuestionReviewRequest(BaseModel):
    action: str = Field(default='approve', pattern='^(approve|reject|back_to_review)$')
    note: str = ''


class BankQuestionUpdateRequest(BaseModel):
    difficulty: str | None = Field(default=None, pattern='^(easy|medium|hard)$')
    cognitive_level: str | None = None
    learning_objective: str | None = None
    question_text: str | None = None
    option_a: str | None = None
    option_b: str | None = None
    option_c: str | None = None
    option_d: str | None = None
    correct_answer: str | None = Field(default=None, pattern='^[ABCD]$')
    explanation: str | None = None
    concept_title: str | None = None
    question_family_id: str | None = None
    source_ref: str | None = None
    source_type: str | None = None
    source_excerpt: str | None = None
    source_evidence: str | None = None
    target_status: str | None = Field(default=None, pattern='^(pending_review|approved|rejected)$')
    note: str = 'Giáo viên sửa câu hỏi trong ngân hàng đề'


class BankQuestionReviewOut(BaseModel):
    ok: bool
    question: BankVersionQuestionOut
    old_status: str
    new_status: str
    message: str


class BankQuestionBulkReviewRequest(BaseModel):
    action: str = Field(default='approve', pattern='^(approve|reject|back_to_review)$')
    question_ids: list[str] = Field(default_factory=list)
    approve_all_pending: bool = False
    apply_to_filtered: bool = False
    status_filter: str | None = None
    difficulty: str | None = None
    search: str | None = None
    note: str = ''


class BankQuestionBulkReviewOut(BaseModel):
    ok: bool
    changed_count: int
    skipped_count: int
    changed_question_ids: list[str] = Field(default_factory=list)
    skipped: list[dict] = Field(default_factory=list)
    message: str




class BankQuestionImportConfirmRequest(BaseModel):
    preview_token: str = Field(min_length=16, max_length=128)


class BankQuestionImportPreviewOut(BaseModel):
    ok: bool
    preview_token: str
    total_rows: int
    valid_count: int
    error_count: int
    preview_rows: list[dict] = Field(default_factory=list)
    errors: list[dict] = Field(default_factory=list)
    can_commit: bool
    message: str


class BankDocumentDiffResolveRequest(BaseModel):
    note: str = ''


class BankDocumentDiffResolveOut(BaseModel):
    ok: bool
    bank_version_id: str
    diff_required: bool
    document_change_state: str
    message: str


class BankReleaseReadinessOut(BaseModel):
    ok: bool
    bank_version_id: str
    can_create_release: bool
    status: str
    checks: list[dict] = Field(default_factory=list)
    stats: dict = Field(default_factory=dict)
    recommended_actions: list[str] = Field(default_factory=list)
    message: str


class BankReleaseQuizPreviewRequest(BaseModel):
    total_questions: int = Field(default=15, ge=1, le=200)
    difficulty_easy: int = Field(default=50, ge=0, le=100)
    difficulty_medium: int = Field(default=30, ge=0, le=100)
    difficulty_hard: int = Field(default=20, ge=0, le=100)
    max_families_per_bank: int = Field(default=2, ge=1, le=10)


class BankReleaseQuizCreateRequest(BankReleaseQuizPreviewRequest):
    course_chapter_mapping_id: str
    quiz_title: str = Field(default='', max_length=255)
    unit_title: str = Field(default='Quiz', max_length=255)
    assessment_type: Literal['quiz', 'final_test'] = 'quiz'
    custom_timer_enabled: bool = True
    time_limit_minutes: int = Field(default=15, ge=1, le=300)
    retake_cooldown_minutes: int = Field(default=5, ge=0, le=10080)
    auto_submit_on_timeout: bool = True
    lock_after_timeout: bool = True
    native_timed_exam: bool = False


class BackendUiStatusMixin(BaseModel):
    ui_status: Literal['success', 'error', 'warning', 'info'] = 'info'
    ui_title: str | None = None
    ui_message: str | None = None


class BankReleaseQuizPlanOut(BackendUiStatusMixin):
    ok: bool
    planner_engine: str | None = None
    uses_llm: bool = False
    release_id: str
    release_code: str
    openedx_library_key: str | None = None
    requested_total_questions: int
    total_questions: int
    target_counts: dict = Field(default_factory=dict)
    effective_target_counts: dict = Field(default_factory=dict)
    coverage: list[dict] = Field(default_factory=list)
    slots: list[dict] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    assigned_question_count: int = 0
    assigned_component_count: int = 0
    hard_guard: dict = Field(default_factory=dict)
    message: str = ''


class BankReleaseQuizCreateOut(BackendUiStatusMixin):
    ok: bool
    status: str
    course_quiz_instance_id: str
    openedx_course_id: str
    openedx_quiz_node_id: str | None = None
    openedx_unit_node_id: str | None = None
    bank_release_id: str
    release_code: str
    plan: dict = Field(default_factory=dict)
    quiz_result: dict = Field(default_factory=dict)
    problem_bank_result: dict = Field(default_factory=dict)
    timer_config: dict = Field(default_factory=dict)
    message: str


class CourseQuizInstanceOut(BaseModel):
    id: str
    openedx_course_id: str
    subject_id: str
    chapter_id: str
    subject_offering_id: str | None = None
    bank_release_id: str
    quiz_blueprint_id: str | None = None
    openedx_quiz_node_id: str | None = None
    openedx_unit_node_id: str | None = None
    status: str
    metadata_json: dict | None = None
    created_at: datetime
    updated_at: datetime
    class Config:
        from_attributes = True


class CourseQuizRollbackRequest(BaseModel):
    mode: str = Field(default='safe')  # safe = thử xóa trên Open edX nếu connector hỗ trợ, manual = chỉ đánh dấu cần xóa tay
    note: str = ''


class CourseQuizRollbackOut(BackendUiStatusMixin):
    ok: bool
    course_quiz_instance_id: str
    status: str
    openedx_deleted: bool = False
    manual_cleanup_required: bool = False
    delete_result: dict = Field(default_factory=dict)
    message: str


class QuizChapterPlanItem(BaseModel):
    chapter_id: str = Field(min_length=1, max_length=255)
    action: Literal['quiz', 'skip', 'assignment', 'final_test'] = 'quiz'


class QuizAutoMapRequest(BaseModel):
    openedx_course_id: str = Field(min_length=1, max_length=255)
    selected_subject_offering_id: str | None = None
    total_questions: int = Field(default=15, ge=1, le=200)
    difficulty_easy: int = Field(default=50, ge=0, le=100)
    difficulty_medium: int = Field(default=30, ge=0, le=100)
    difficulty_hard: int = Field(default=20, ge=0, le=100)
    max_families_per_bank: int = Field(default=2, ge=1, le=10)
    chapter_plan: list[QuizChapterPlanItem] = Field(default_factory=list)


class QuizAutoMapOut(BackendUiStatusMixin):
    ok: bool
    openedx_course_id: str
    mode: str = 'preview'
    subject: dict | None = None
    offering: dict | None = None
    course_mapping: dict | None = None
    summary: dict = Field(default_factory=dict)
    sections: list[dict] = Field(default_factory=list)
    mappings: list[dict] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    blocking_errors: list[str] = Field(default_factory=list)
    can_apply: bool = False
    message: str


class BankOperationJobOut(BaseModel):
    id: str
    operation_type: str
    status: str
    target_type: str
    target_id: str | None = None
    bank_version_id: str | None = None
    release_id: str | None = None
    material_version_id: str | None = None
    course_quiz_instance_id: str | None = None
    requested_by: str | None = None
    course_id: str | None = None
    progress_current: int = 0
    progress_total: int = 1
    progress_percent: float = 0
    progress_label: str = ''
    request: dict = Field(default_factory=dict)
    result: dict = Field(default_factory=dict)
    celery_task_id: str | None = None
    task_name: str | None = None
    enqueued_at: datetime | str | None = None
    retry_token: str | None = None
    enqueue_history: list[dict] = Field(default_factory=list)
    error_message: str | None = None
    created_at: datetime | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    updated_at: datetime | None = None


class BankOperationJobQueuedOut(BaseModel):
    ok: bool = True
    job: BankOperationJobOut
    message: str
