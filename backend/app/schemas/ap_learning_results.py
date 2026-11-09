"""Stable AP v1 response allowlist. No raw evidence or other learner identities."""
from typing import Literal

from pydantic import BaseModel


class APClassContext(BaseModel):
    ap_class_id: str
    ap_term_id: str
    ap_block_id: str | None
    branch: str
    campus: str
    subject_code: str
    course_id: str


class APLearningResult(BaseModel):
    student_code: str | None
    full_name: str
    status: Literal['ready', 'stale', 'missing']
    classification: str | None
    display_label: str
    confidence_score: float | None
    reason_codes: list[str]
    human_readable_summary: str
    recommended_action: str
    data_quality: str
    calculated_at: str | None
    last_activity_at: str | None
    snapshot_stale: bool


class APClassSummary(BaseModel):
    roster_count: int
    snapshot_count: int
    missing_snapshot_count: int
    stale_snapshot_count: int
    data_status: Literal['ready', 'partial', 'not_calculated']
    classification_counts: dict[str, int]


class APResultsBase(BaseModel):
    schema_version: Literal['1'] = '1'
    context: APClassContext
    disclaimer: str
    read_only: Literal[True] = True


class APClassResults(APResultsBase):
    summary: APClassSummary
    total: int
    limit: int
    offset: int
    next_offset: int | None
    items: list[APLearningResult]


class APStudentResult(APResultsBase):
    result: APLearningResult
