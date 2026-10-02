from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from types import SimpleNamespace

from app.services.openedx_student_insight import OpenEdXConnectorClient


ROOT = Path(__file__).resolve().parents[3]


def _load_student_insight(monkeypatch):
    package_name = "test_openedx_ai_connector"
    package = types.ModuleType(package_name)
    package.__path__ = [str(ROOT / "openedx-connector-plugin" / "openedx_ai_connector")]
    monkeypatch.setitem(sys.modules, package_name, package)

    django = types.ModuleType("django")
    django_http = types.ModuleType("django.http")
    django_http.JsonResponse = type("JsonResponse", (), {})
    django_views = types.ModuleType("django.views")
    django_decorators = types.ModuleType("django.views.decorators")
    django_csrf = types.ModuleType("django.views.decorators.csrf")
    django_csrf.csrf_exempt = lambda func: func
    for name, module in {
        "django": django,
        "django.http": django_http,
        "django.views": django_views,
        "django.views.decorators": django_decorators,
        "django.views.decorators.csrf": django_csrf,
    }.items():
        monkeypatch.setitem(sys.modules, name, module)

    auth = types.ModuleType(f"{package_name}.auth")
    auth._batch_too_large_response = lambda *args, **kwargs: None
    auth._json_response = lambda *args, **kwargs: None
    auth._read_json_body = lambda *args, **kwargs: {}
    auth._require_student_insight_hmac = lambda func: func
    auth._setting_or_env = lambda *args, **kwargs: None
    monkeypatch.setitem(sys.modules, auth.__name__, auth)

    runtime = types.ModuleType(f"{package_name}.runtime")
    runtime._load_openedx_modules = lambda: {}
    monkeypatch.setitem(sys.modules, runtime.__name__, runtime)

    studio = types.ModuleType(f"{package_name}.studio")
    studio._safe_str = lambda value: "" if value is None else str(value)
    studio._block_type = lambda block: "unknown"
    studio._display_name = lambda block: "unknown"
    studio._get_item_best_effort = lambda store, key: None
    studio._children_locations = lambda block: []
    monkeypatch.setitem(sys.modules, studio.__name__, studio)

    module_name = f"{package_name}.student_insight"
    source = ROOT / "openedx-connector-plugin" / "openedx_ai_connector" / "student_insight.py"
    spec = importlib.util.spec_from_file_location(module_name, source)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, module_name, module)
    spec.loader.exec_module(module)
    return module


def test_connector_uses_openedx_course_home_summary_counts_including_locked(monkeypatch):
    module = _load_student_insight(monkeypatch)
    calls = []

    official_api = SimpleNamespace(
        get_course_blocks_completion_summary=lambda course_key, user: (
            calls.append((course_key, user.id))
            or {"complete_count": 32, "incomplete_count": 0, "locked_count": 1}
        )
    )

    def import_module(name):
        if name == "lms.djangoapps.courseware.courses":
            return official_api
        raise ImportError(name)

    monkeypatch.setattr(module.importlib, "import_module", import_module)

    result = module._completion_api_progress_snapshot(
        "course-v1:FPL+BUS1052+FA26",
        [SimpleNamespace(id=7, username="PC12804")],
    )

    assert calls == [("course-v1:FPL+BUS1052+FA26", 7)]
    assert result[7] == {
        "percent": 96.97,
        "source": "CourseHomeOfficial:get_course_blocks_completion_summary",
        "completed_blocks": 32,
        "total_blocks": 33,
        "complete_count": 32,
        "incomplete_count": 0,
        "locked_count": 1,
    }


def test_official_completion_failure_is_isolated_per_student_and_invalid_totals_fall_back(monkeypatch):
    module = _load_student_insight(monkeypatch)

    def get_summary(course_key, user):
        if user.id == 8:
            raise RuntimeError('learner-specific completion failure')
        if user.id == 9:
            return {"complete_count": 0, "incomplete_count": 0, "locked_count": 0}
        return {"complete_count": 33, "incomplete_count": 0, "locked_count": 0}

    official_api = SimpleNamespace(get_course_blocks_completion_summary=get_summary)
    monkeypatch.setattr(
        module.importlib,
        'import_module',
        lambda name: official_api if name == 'lms.djangoapps.courseware.courses' else None,
    )

    result = module._completion_api_progress_snapshot(
        'course-v1:FPL+BUS1052+FA26',
        [SimpleNamespace(id=7), SimpleNamespace(id=8), SimpleNamespace(id=9)],
    )

    assert result[7]['percent'] == 100.0
    assert 8 not in result
    assert 9 not in result


def test_official_course_home_total_is_not_overwritten_by_studentmodule_denominator(monkeypatch):
    module = _load_student_insight(monkeypatch)
    official = {
        7: {
            "percent": 96.97,
            "source": "CourseHomeOfficial:get_course_blocks_completion_summary",
            "completed_blocks": 32,
            "total_blocks": 33,
        }
    }
    monkeypatch.setattr(module, "_course_home_progress_snapshot", lambda course_key, users: official)
    monkeypatch.setattr(
        module,
        "_completion_denominator_block_snapshot",
        lambda course_key: {"eligible_total": 99, "subsection_total": 99},
    )
    monkeypatch.setattr(module, "_student_module_model", lambda: (None, None, None))

    result, fallback_total = module._completion_snapshot(
        "course-v1:FPL+BUS1052+FA26",
        [SimpleNamespace(id=7, username="PC12804")],
    )

    assert fallback_total == 99
    assert result[7]["completed_blocks"] == 32
    assert result[7]["total_blocks"] == 33
    assert result[7]["percent"] == 96.97


def test_connector_diagnostics_reports_direct_official_completion_api(monkeypatch):
    module = _load_student_insight(monkeypatch)
    for helper in (
        '_course_enrollment_model',
        '_persistent_course_grade_model',
        '_persistent_subsection_grade_model',
        '_student_module_model',
    ):
        monkeypatch.setattr(module, helper, lambda: (None, None, None))

    official_api = SimpleNamespace(get_course_blocks_completion_summary=lambda course_key, user: {})

    def import_module(name):
        if name == 'lms.djangoapps.courseware.courses':
            return official_api
        raise ImportError(name)

    monkeypatch.setattr(module.importlib, 'import_module', import_module)

    diagnostics = module._learning_connector_diagnostics()

    assert diagnostics['completion_api_functions'] == [
        'lms.djangoapps.courseware.courses.get_course_blocks_completion_summary'
    ]


def test_new_direct_official_flag_overrides_legacy_skip_only_in_new_connector(monkeypatch):
    module = _load_student_insight(monkeypatch)

    assert module._should_skip_course_home_progress({'skip_course_home_progress': True}) is True
    assert module._should_skip_course_home_progress({
        'skip_course_home_progress': True,
        'use_official_course_home_progress': True,
    }) is False
    assert module._should_skip_course_home_progress({}) is False


def test_backend_requests_official_course_home_progress(monkeypatch):
    client = OpenEdXConnectorClient.__new__(OpenEdXConnectorClient)
    client.class_analytics_endpoint = "/api/ai-connector/v1/class-analytics"
    client.timeout_seconds = 60
    monkeypatch.setattr(client, "configured", lambda: True)
    captured = {}

    def post_json(**kwargs):
        captured.update(kwargs)
        return {"ok": True, "results": []}

    monkeypatch.setattr(client, "_post_json", post_json)

    client.class_analytics_payload(
        course_id="course-v1:FPL+BUS1052+FA26",
        students=[{"username": "PC12804"}],
    )

    assert captured["body"]["skip_course_home_progress"] is True
    assert captured["body"]["use_official_course_home_progress"] is True
