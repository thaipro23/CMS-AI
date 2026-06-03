from datetime import datetime
from pydantic import BaseModel
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.core.rbac import UserContext, ensure_course_access, require_permission
from app.db.session import get_db
from app.services.library_service import ChapterLibraryService

router = APIRouter()

class CourseLibraryOut(BaseModel):
    id: str
    course_id: str
    chapter_node_id: str
    chapter_title: str
    difficulty: str
    library_key: str
    display_name: str
    openedx_library_id: str | None = None
    status: str
    created_at: datetime
    updated_at: datetime
    class Config:
        from_attributes = True

@router.get('', response_model=list[CourseLibraryOut])
def list_libraries(course_id: str | None = None, db: Session = Depends(get_db), user: UserContext = Depends(require_permission('view_questions'))):
    ensure_course_access(user, course_id)
    return ChapterLibraryService(db).list_libraries(course_id)
