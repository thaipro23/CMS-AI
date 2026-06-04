from datetime import datetime
from pydantic import BaseModel, Field


class ConceptOut(BaseModel):
    id: str
    course_id: str
    chapter_node_id: str | None = None
    source_node_id: str | None = None
    source_node_title: str | None = None
    concept_key: str
    title: str
    summary: str
    learning_objective: str
    difficulty_hint: str
    importance_score: float
    source_chunk_ids: list[str] | None = None
    source_evidence: str
    token_count: int = 0
    status: str
    metadata_json: dict | None = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ConceptExtractRequest(BaseModel):
    node_id: str | None = None
    force: bool = False
    max_concepts: int = Field(default=20, ge=1, le=100)


class ConceptExtractResponse(BaseModel):
    course_id: str
    node_id: str | None = None
    concept_count: int
    reused_existing: bool = False
    concepts: list[ConceptOut]


class ConceptListResponse(BaseModel):
    course_id: str
    node_id: str | None = None
    total: int
    concepts: list[ConceptOut]
