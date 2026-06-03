from datetime import datetime
from pydantic import BaseModel, Field


class SyncCourseRequest(BaseModel):
    course_id: str
    force: bool = False


class SyncCourseResponse(BaseModel):
    course_id: str
    blocks_seen: int
    changed_blocks: int
    status: str


class CourseOptionResponse(BaseModel):
    course_id: str
    title: str = ''
    node_count: int = 0
    chunk_count: int = 0
    token_count: int = 0
    last_synced_at: datetime | None = None



class CourseCleanResyncResponse(BaseModel):
    course_id: str
    deleted_chunks: int
    deleted_nodes: int
    deleted_topics: int = 0
    blocks_seen: int
    changed_blocks: int
    status: str
    message: str = ''


class ContentChunkResponse(BaseModel):
    id: str
    course_id: str
    block_id: str
    topic_id: str | None = None  # kept for backward DB compatibility; UI no longer uses topic filter
    content: str
    token_count: int
    source_type: str
    page_number: int | None = None
    timestamp_start: str | None = None
    timestamp_end: str | None = None
    source_ref: str | None = None
    created_at: datetime

    class Config:
        from_attributes = True




class CourseFileUploadResponse(BaseModel):
    course_id: str
    node_id: str
    parent_node_id: str | None = None
    filename: str
    source_type: str
    chunks_created: int
    tokens_indexed: int
    status: str
    message: str = ''


class CourseNodeDeleteResponse(BaseModel):
    course_id: str
    node_id: str
    deleted_nodes: int
    deleted_chunks: int
    status: str
    message: str = ''


class TopicResponse(BaseModel):
    """Deprecated compatibility response.

    v20 no longer uses topic extraction in the UI/generation flow. It uses course
    nodes directly. This schema stays only so older clients do not break.
    """
    id: str
    course_id: str
    lesson_id: str | None = None
    title: str
    summary: str
    importance_score: int
    chunk_count: int = 0
    token_count: int = 0

    class Config:
        from_attributes = True


class CourseTreeNodeResponse(BaseModel):
    node_id: str
    parent_id: str | None = None
    block_type: str
    title: str
    path: str = ''
    chunk_count: int = 0
    token_count: int = 0
    children: list['CourseTreeNodeResponse'] = Field(default_factory=list)


class CourseNodeOptionResponse(BaseModel):
    node_id: str
    parent_id: str | None = None
    block_type: str
    title: str
    path: str
    depth: int = 0
    chunk_count: int = 0
    token_count: int = 0


CourseTreeNodeResponse.model_rebuild()
