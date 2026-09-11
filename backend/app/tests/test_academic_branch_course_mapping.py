"""Behavioral regressions for PTCD/FPS and POLY/FPL course boundaries."""
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.academic import (
    AcademicBlock, AcademicClass, AcademicClassCourseMapping, AcademicCourseMapping,
    AcademicSubject, AcademicSubjectDelivery, AcademicTerm,
)
from app.models.course import CourseSyncState
from app.services.academic_service import AcademicService, OpenEdXConnectorClient
from app.services.academic_subject_overview_performance import _inherited_course_mappings_for_classes_fast


@pytest.fixture
def scope(monkeypatch):
    monkeypatch.setattr(settings, 'academic_openedx_org_by_branch', '')
    monkeypatch.setattr(settings, 'academic_default_openedx_course_org', '')
    # The connector is external; exercise actual database queries and service decisions.
    monkeypatch.setattr(OpenEdXConnectorClient, 'verify_course_exists', lambda self, cid: {'available': True, 'exists': True})
    monkeypatch.setattr(OpenEdXConnectorClient, 'find_exact_course', lambda self, cid: (None, None, 0, 'test_connector'))
    monkeypatch.setattr(OpenEdXConnectorClient, 'search_courses', lambda self, **kwargs: [])
    engine = create_engine('sqlite+pysqlite:///:memory:')
    for model in (AcademicTerm, AcademicBlock, AcademicSubject, AcademicSubjectDelivery, AcademicClass,
                  AcademicCourseMapping, AcademicClassCourseMapping, CourseSyncState):
        model.__table__.create(engine)
    with Session(engine) as db:
        term = AcademicTerm(id='term', term_code='FA26', term_name='Fall 2026', branch='ptcd')
        subject = AcademicSubject(id='subject', subject_code='MAR2023', subject_name='Marketing', branch='ptcd')
        cls = AcademicClass(id='class', term_id=term.id, subject_id=subject.id, class_code='MAR2023.01', branch='ptcd')
        db.add_all([term, subject, cls])
        db.commit()
        yield AcademicService(db), term, subject, cls
    engine.dispose()


def stored_mapping(service, *, org='FPL', direct=False, branch='ptcd'):
    if direct:
        row = AcademicClassCourseMapping(class_id='class', openedx_course_id=f'course-v1:{org}+MAR2023+FA26')
    else:
        row = AcademicCourseMapping(term_id='term', subject_id='subject', branch=branch, openedx_course_id=f'course-v1:{org}+MAR2023+FA26')
    service.db.add(row)
    service.db.commit()
    return row


def cache_course(service, cid, title='Marketing'):
    service.db.add(CourseSyncState(course_id=cid, block_id=cid, block_type='course', display_name=title))
    service.db.commit()


@pytest.mark.parametrize(('branch', 'org'), [('ptcd', 'FPS'), (' PTCD ', 'FPS'), ('poly', 'FPL')])
def test_branch_suggestion_cannot_be_reversed_by_old_settings(scope, monkeypatch, branch, org):
    service, term, subject, _ = scope
    monkeypatch.setattr(settings, 'academic_openedx_org_by_branch', '{"ptcd":"FPL","poly":"FPS"}')
    assert service.suggested_course_id_for_scope(term.id, subject.id, branch=branch) == f'course-v1:{org}+MAR2023+FA26'


@pytest.mark.parametrize('cid', ['course-v1:FPL+MAR2023+FA26', 'course-v1:FPS+MAR2023+SU26', 'course-v1:FPS+OTHER+FA26'])
def test_auto_candidate_requires_org_subject_and_term(scope, cid):
    service, term, subject, _ = scope
    cache_course(service, cid, 'Marketing FA26')
    result = service._find_openedx_course_candidate_for_scope(term=term, subject=subject, suggested='course-v1:FPS+MAR2023+FA26', allow_external=False)
    assert result['candidate'] is None
    assert result['count'] == 0


def test_auto_candidate_accepts_matching_org_with_term_alias(scope):
    service, term, subject, _ = scope
    cache_course(service, 'course-v1:FPL+MAR2023+FA26')
    cache_course(service, 'course-v1:FPS+MAR2023+FA2026')
    result = service._find_openedx_course_candidate_for_scope(term=term, subject=subject, suggested='course-v1:FPS+MAR2023+FA26', allow_external=False)
    assert result['candidate'] == 'course-v1:FPS+MAR2023+FA2026'
    assert result['count'] == 1


@pytest.mark.parametrize('branch', ['ptcd', None])
def test_manual_wrong_org_is_blocking_even_without_explicit_branch(scope, branch):
    service, term, subject, _ = scope
    result = service.validate_course_mapping_payload(term_id=term.id, subject_id=subject.id, branch=branch, openedx_course_id='course-v1:FPL+MAR2023+FA26')
    assert result['can_save'] is False
    assert any(check['code'] == 'org_match' and check['blocking'] for check in result['checks'])


@pytest.mark.parametrize('direct', [False, True])
def test_existing_wrong_org_is_not_effective_or_mutated(scope, direct):
    service, _, _, cls = scope
    row = stored_mapping(service, direct=direct)
    assert service.effective_course_mapping_for_class(cls) is None
    service.db.refresh(row)
    assert row.active is True
    assert row.openedx_course_id == 'course-v1:FPL+MAR2023+FA26'


@pytest.mark.parametrize('reader', [AcademicService.inherited_course_mappings_for_classes, _inherited_course_mappings_for_classes_fast])
def test_inherited_reader_skips_invalid_specific_mapping_and_keeps_valid_global(scope, reader):
    service, _, _, cls = scope
    stored_mapping(service)
    valid = stored_mapping(service, org='FPS', branch=None)
    assert reader(service, [cls]) == {'class': valid}


def test_wrong_direct_mapping_does_not_hide_valid_inherited_course(scope):
    service, _, _, cls = scope
    stored_mapping(service, direct=True)
    valid = stored_mapping(service, org='FPS')
    assert service.effective_course_mapping_for_class(cls) is valid


def test_auto_create_never_reuses_or_overwrites_invalid_existing_mapping(scope):
    service, _, _, _ = scope
    row = stored_mapping(service)
    result = service._auto_create_subject_course_mapping_if_safe(SimpleNamespace(user_id='admin'), term_id='term', subject_id='subject', branch_value='ptcd', candidate='course-v1:FPS+MAR2023+FA26', suggested='course-v1:FPS+MAR2023+FA26')
    assert result is None
    assert service.db.query(AcademicCourseMapping).count() == 1
    assert row.openedx_course_id == 'course-v1:FPL+MAR2023+FA26'


def test_valid_stored_mapping_remains_reusable(scope):
    service, _, _, cls = scope
    row = stored_mapping(service, org='FPS')
    assert service.effective_course_mapping_for_class(cls) is row
    assert service._auto_create_subject_course_mapping_if_safe(SimpleNamespace(user_id='admin'), term_id='term', subject_id='subject', branch_value='ptcd', candidate='course-v1:FPS+MAR2023+FA26', suggested='course-v1:FPS+MAR2023+FA26') is row


def test_admin_mapping_payload_marks_legacy_wrong_org_invalid(scope):
    service, _, _, _ = scope
    row = stored_mapping(service)
    payload = service._course_mapping_item(row)
    assert payload['validation_status'] == 'invalid_org_match'
    assert payload['validation_json']['can_save'] is False
    assert row.validation_status == 'not_validated'
