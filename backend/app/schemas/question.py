from datetime import datetime
from pydantic import BaseModel, Field


class QuestionOut(BaseModel):
    id: str
    course_id: str
    lesson_id: str | None = None
    lesson_title: str | None = None
    block_id: str | None = None
    topic_id: str | None = None
    topic: str
    difficulty: str
    cognitive_level: str
    learning_objective: str
    question_type: str
    question_text: str
    option_a: str
    option_b: str
    option_c: str
    option_d: str
    correct_answer: str
    explanation: str
    source_ref: str
    source_type: str
    source_page: int | None = None
    source_timestamp_start: str | None = None
    source_timestamp_end: str | None = None
    source_chunk_id: str | None = None
    source_node_id: str | None = None
    source_node_title: str | None = None
    chapter_node_id: str | None = None
    chapter_title: str | None = None
    target_library_id: str | None = None
    target_library_key: str | None = None
    source_excerpt: str
    tags: list[str] | None = None
    ai_rationale: str
    quality_score: float
    quality_flags: list[str] | None = None
    draft_error_reason: str | None = None
    draft_error_detail: dict | None = None
    repair_attempt_count: int = 0
    is_duplicate: bool
    duplicate_of_question_id: str | None = None
    duplicate_score: float | None = None
    generation_job_id: str | None = None
    model_provider: str
    model_name: str
    status: str
    version: int
    reviewed_by: str | None = None
    reviewed_at: datetime | None = None
    published_at: datetime | None = None
    openedx_block_id: str | None = None
    openedx_library_problem_id: str | None = None
    imported_library_at: datetime | None = None
    publish_error: str | None = None
    publish_status: str | None = None
    publish_verification_json: dict | None = None
    published_by: str | None = None
    openedx_publish_status: str | None = None
    openedx_verification_status: str | None = None
    openedx_delete_status: str | None = None
    openedx_manual_action_required: bool | None = False
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ReviewQuestionRequest(BaseModel):
    actor: str = 'teacher'
    note: str = ''


class QuestionUpdateRequest(BaseModel):
    actor: str = 'teacher'
    note: str = 'Teacher edited question'
    lesson_title: str | None = None
    block_id: str | None = None
    topic: str | None = None
    difficulty: str | None = Field(default=None, pattern='^(easy|medium|hard)$')
    cognitive_level: str | None = Field(default=None, pattern='^(remember|understand|recognize_example|simple_apply)$')
    learning_objective: str | None = None
    question_text: str | None = None
    option_a: str | None = None
    option_b: str | None = None
    option_c: str | None = None
    option_d: str | None = None
    correct_answer: str | None = Field(default=None, pattern='^[ABCD]$')
    explanation: str | None = None
    source_ref: str | None = None
    source_type: str | None = None
    source_page: int | None = None
    source_timestamp_start: str | None = None
    source_timestamp_end: str | None = None
    source_chunk_id: str | None = None
    source_node_id: str | None = None
    source_node_title: str | None = None
    source_excerpt: str | None = None
    tags: list[str] | None = None


class BulkApproveRequest(BaseModel):
    actor: str = 'teacher'
    note: str = 'Bulk approve'
    question_ids: list[str] | None = None
    course_id: str | None = None
    approve_all_pending: bool = False


class DraftErrorRepairRequest(BaseModel):
    note: str = 'Repair draft error'


class KeepDraftErrorRequest(BaseModel):
    note: str = 'Keep anyway after teacher review'


class ChangeQuestionStatusRequest(BaseModel):
    actor: str = 'teacher'
    note: str = 'Manual status correction'
    target_status: str = Field(pattern='^(pending_review|approved|rejected)$')


class OpenEdxExportOut(BaseModel):
    format: str
    question_count: int
    olx: str


class QuestionBankStatsOut(BaseModel):
    total: int
    pending_review: int
    approved: int
    rejected: int
    published: int
    openedx_verified: int = 0
    openedx_pending: int = 0
    openedx_manual_delete_required: int = 0
    draft_error: int
