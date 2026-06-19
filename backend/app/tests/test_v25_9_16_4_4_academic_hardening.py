from types import SimpleNamespace

import pytest

pytest.importorskip("jose")

from app.services.academic_service import AcademicService
from app.services import runtime_settings


def test_enrollment_only_snapshot_is_not_learning_payload():
    snapshot = SimpleNamespace(
        progress_percent=None,
        grade_percent=None,
        completed_blocks=None,
        total_blocks=None,
        raw_json={"enrollment_payload": {"status": "enrolled"}},
    )

    assert AcademicService._snapshot_has_learning_payload(snapshot) is False


def test_component_snapshot_counts_as_learning_payload():
    snapshot = SimpleNamespace(
        progress_percent=None,
        grade_percent=None,
        completed_blocks=None,
        total_blocks=None,
        raw_json={"payload": {"component_scores": [{"name": "Quiz", "percent": 80}]}},
    )

    assert AcademicService._snapshot_has_learning_payload(snapshot) is True


def test_runtime_settings_blocks_security_knobs_in_production(monkeypatch):
    monkeypatch.setattr(runtime_settings, "is_production", lambda: True)

    with pytest.raises(ValueError) as exc:
        runtime_settings.update_runtime_settings({
            "sso": {"auth_mode": "demo", "allow_demo_role_header": True},
            "openedx": {"use_mock_openedx": True},
            "model": {"mock_llm": True},
        })

    assert "Production không cho phép đổi runtime security settings" in str(exc.value)
