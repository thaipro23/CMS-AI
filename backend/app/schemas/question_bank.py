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


class ChapterCreate(BaseModel):
    subject_id: str
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
    department_id: str | None = None
    term: str | None = None


class CourseMappingOut(CourseMappingCreate):
    id: str
    status: str
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
    enabled: bool = True


class CourseChapterMappingOut(CourseChapterMappingCreate):
    id: str
    created_at: datetime
    updated_at: datetime
    class Config:
        from_attributes = True


class QuizBlueprintCreate(BaseModel):
    subject_id: str
    chapter_id: str
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
    chapters: int
    bank_versions: int
    releases: int
    published_releases: int
    course_mappings: int
    quiz_blueprints: int
