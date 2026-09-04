import pytest

from app.services.academic_service import AcademicService


def _payload(*, runtime: str, contract: str) -> dict:
    return {
        'ok': True,
        'connector_version': runtime,
        'connector_contract_version': contract,
        'progress_contract': {
            'denominator': 'reachable_sequential_subsections',
            'numerator': 'studentmodule_sequential_position_rows',
            'ignored_studentmodule_types': ['itembank', 'problem', 'video'],
        },
    }


def _service() -> AcademicService:
    return AcademicService.__new__(AcademicService)


def test_connector_accepts_newer_compatible_contract_version():
    service = _service()
    service._validate_connector_learning_contract(
        _payload(runtime='25.9.16.5.99', contract='learning-sync/v25.9.16.5.99'),
        course_id='course-v1:FPL+MEC229+SU26',
    )


def test_connector_rejects_contract_older_than_minimum():
    service = _service()
    with pytest.raises(RuntimeError, match='contract quá cũ'):
        service._validate_connector_learning_contract(
            _payload(runtime='25.9.16.5.99', contract='learning-sync/v25.9.16.5.97'),
            course_id='course-v1:FPL+MEC229+SU26',
        )


def test_connector_still_rejects_unsafe_progress_semantics():
    service = _service()
    payload = _payload(runtime='25.9.16.5.99', contract='learning-sync/v25.9.16.5.99')
    payload['progress_contract']['denominator'] = 'legacy_block_count'
    with pytest.raises(RuntimeError, match='progress_contract không an toàn'):
        service._validate_connector_learning_contract(payload, course_id='course-v1:FPL+MEC229+SU26')
