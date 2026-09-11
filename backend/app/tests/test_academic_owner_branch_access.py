from types import SimpleNamespace
import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.core.rbac import UserContext
from app.models.academic import AcademicClass, AcademicSubject, AcademicTeacher, AcademicTeacherAssignment
from app.services.academic.access import AcademicAccessWorkflowService
from app.services.academic_service import AcademicService

@pytest.fixture
def scope():
    engine = create_engine("sqlite://")
    for model in (AcademicSubject, AcademicClass, AcademicTeacher, AcademicTeacherAssignment):
        model.__table__.create(engine)
    with Session(engine) as db:
        db.add_all([AcademicSubject(id=b, subject_code="MATH", subject_name="Math", branch=b) for b in ("poly", "ptcd")])
        for branch, campus in [("poly", "hn"), ("ptcd", "hn"), ("ptcd", "tk")]:
            db.add(AcademicClass(id=branch+campus, term_id="term", subject_id=branch, class_code=branch+campus, branch=branch, campus=campus))
        db.commit()
        rbac = SimpleNamespace(is_system_admin=lambda u: False, accessible_campus_codes=lambda u: {"hn", "tk"}, accessible_campus_branch_pairs=lambda u: {("poly", "hn"), ("ptcd", "tk")})
        access = AcademicAccessWorkflowService(db, rbac)
        user = UserContext(user_id="owner", role="viewer", permissions=set())
        yield db, access, user
    engine.dispose()

def test_same_campus_code_does_not_cross_owner_branch(scope):
    db, access, user = scope
    access.assert_can_access_class(user, "polyhn")
    access.assert_can_access_class(user, "ptcdtk")
    with pytest.raises(HTTPException) as caught:
        access.assert_can_access_class(user, "ptcdhn")
    assert caught.value.status_code == 403

def test_class_list_scope_preserves_branch_campus_pairs(scope):
    db, access, user = scope
    service = AcademicService(db)
    query = service._apply_academic_access_filter(db.query(AcademicClass), user, access.access_decision(user))
    assert {row.id for row in query.all()} == {"polyhn", "ptcdtk"}

def test_subject_parent_requires_class_in_exact_owned_pair(scope):
    db, access, user = scope
    db.query(AcademicClass).filter(AcademicClass.id == "ptcdtk").delete()
    db.commit()
    with pytest.raises(HTTPException):
        access.assert_can_access_subject(user, "ptcd")
