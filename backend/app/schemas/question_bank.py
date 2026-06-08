from datetime import datetime
from pydantic import BaseModel, Field


class DepartmentCreate(BaseModel):
    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=255)
    description: str = ''


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
    chapter_no: int = Field(default=1, ge=1)
    title: str = Field(min_length=1, max_length=255)
    description: str = ''
    sort_order: int = Field(default=1, ge=1)


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


class MaterialUploadOut(BaseModel):
    ok: bool
    reused_existing: bool = False
    material_version: MaterialVersionOut
    chunks_created: int
    tokens_indexed: int
    source_types: list[str] = Field(default_factory=list)
    message: str


class BankGenerateRequest(BaseModel):
    question_count: int = Field(default=10, ge=1, le=200)
    difficulty_easy: int = Field(default=50, ge=0, le=100)
    difficulty_medium: int = Field(default=30, ge=0, le=100)
    difficulty_hard: int = Field(default=20, ge=0, le=100)
    material_version_ids: list[str] | None = None
    provider: str = 'openai'
    approve_after_generate: bool = False


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
    questions: list[str] = Field(default_factory=list)
    usage: list[dict] = Field(default_factory=list)
    errors: list[dict] = Field(default_factory=list)
    message: str


class BankVersionQuestionOut(BaseModel):
    id: str
    bank_version_id: str | None = None
    subject_id: str | None = None
    subject_chapter_id: str | None = None
    material_version_id: str | None = None
    concept_version_id: str | None = None
    question_family_id: str | None = None
    variant_no: int | None = None
    difficulty: str
    question_text: str
    correct_answer: str
    status: str
    quality_score: float
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


class BankVersionDiffPreviewRequest(BaseModel):
    base_bank_version_id: str | None = None
    persist: bool = True


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
