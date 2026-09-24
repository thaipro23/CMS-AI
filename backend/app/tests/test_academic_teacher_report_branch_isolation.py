from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.rbac import UserContext
from app.models.academic import (
    AcademicClass,
    AcademicSubject,
    AcademicTeacher,
    AcademicTeacherAssignment,
    AcademicTerm,
)
from app.services.academic.report_snapshot import (
    ReportSnapshotError,
    validate_campus_report,
    validate_report_branch,
)
from app.services.academic.teacher_report import TeacherReportBranchScopeError
from app.services.academic_service import AcademicService


def _report_payload(*, branch: str, teacher_branch: str | None) -> dict:
    return {
        "items": [{
            "teacher_id": "teacher-1",
            "teacher_name": "Teacher One",
            "campus": "hn",
            "branch": teacher_branch,
            "classes": [{
                "class_id": "class-1",
                "class_code": "DOM1021.01",
                "campus": "hn",
                "branch": branch,
            }],
        }],
        "student_watch_rows": [{
            "teacher_id": "teacher-1",
            "class_id": "class-1",
            "student_id": "student-1",
        }],
        "summary": {"teacher_count": 1, "class_count": 1, "student_count": 1},
    }


@pytest.mark.parametrize(
    ("scheduled_branch", "foreign_branch"),
    [("poly", "ptcd"), ("ptcd", "poly")],
)
def test_snapshot_rejects_explicit_opposite_teacher_branch(
    scheduled_branch: str,
    foreign_branch: str,
):
    report = _report_payload(branch=scheduled_branch, teacher_branch=foreign_branch)

    with pytest.raises(ReportSnapshotError, match="teacher branch"):
        validate_campus_report(report, campus="hn", branch=scheduled_branch)


@pytest.mark.parametrize("branch", ["poly", "ptcd"])
def test_null_teacher_branch_inherits_class_branch(branch: str):
    report = _report_payload(branch=branch, teacher_branch=None)

    counts = validate_campus_report(report, campus="hn", branch=branch)

    assert counts["teacher_count"] == 1
    assert validate_report_branch(report, branch=branch) == {
        "teacher_count": 1,
        "class_count": 1,
    }


def _scheduler_user() -> UserContext:
    return UserContext(
        user_id="academic-score-scheduler",
        username="academic-score-scheduler",
        email=None,
        role="admin",
        permissions=set(),
        course_ids=None,
        raw_claims={"ai_system_admin": True},
    )


def test_scheduled_query_detects_cross_branch_assignment_instead_of_hiding_it():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    for model in [
        AcademicTerm,
        AcademicSubject,
        AcademicClass,
        AcademicTeacher,
        AcademicTeacherAssignment,
    ]:
        model.__table__.create(engine)
    with Session(engine) as db:
        db.add_all([
            AcademicTerm(
                id="term-ptcd",
                term_code="FA26",
                term_name="Fall 2026",
                branch="ptcd",
                active=True,
            ),
            AcademicSubject(
                id="subject-1",
                subject_code="DOM1021",
                subject_name="DOM",
                branch="ptcd",
                active=True,
            ),
            AcademicClass(
                id="class-ptcd",
                term_id="term-ptcd",
                subject_id="subject-1",
                class_code="DOM1021.01",
                class_name="DOM1021.01",
                campus="hn",
                branch="ptcd",
                active=True,
            ),
            AcademicTeacher(
                id="teacher-poly",
                username="teacher.poly",
                full_name="Poly Teacher",
                campus="hn",
                branch="poly",
                active=True,
            ),
            AcademicTeacherAssignment(
                id="assignment-1",
                teacher_id="teacher-poly",
                class_id="class-ptcd",
                subject_id="subject-1",
                term_id="term-ptcd",
                campus="hn",
                branch="ptcd",
                source="ap",
            ),
        ])
        db.commit()

        with pytest.raises(TeacherReportBranchScopeError, match="teacher branch"):
            AcademicService(db).training_teacher_report(
                _scheduler_user(),
                term_id="term-ptcd",
                branch="ptcd",
                campus="hn",
                include_all=True,
                include_students=True,
                use_cache=False,
                allowed_class_ids={"class-ptcd"},
                enforce_branch_integrity=True,
            )
    engine.dispose()
