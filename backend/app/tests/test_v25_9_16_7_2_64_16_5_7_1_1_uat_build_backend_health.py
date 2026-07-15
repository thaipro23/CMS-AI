from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import yaml

from app.services import runtime_settings

ROOT = Path(__file__).resolve().parents[3]
VERSION = '25.9.16.7.2.64.16.5.7.1.1'


def test_hardened_runtime_file_cannot_override_environment_owned_fields(monkeypatch, tmp_path):
    runtime_file = tmp_path / 'runtime-settings.json'
    runtime_file.write_text(json.dumps({
        'auth_mode': 'demo',
        'allow_demo_role_header': True,
        'use_mock_openedx': True,
        'mock_llm': True,
        'openai_model': 'gpt-5-mini-safe-runtime',
    }), encoding='utf-8')
    fake = SimpleNamespace(
        auth_mode='openedx_sso',
        allow_demo_role_header=False,
        use_mock_openedx=False,
        mock_llm=False,
        openai_model='gpt-5-mini',
    )
    monkeypatch.setattr(runtime_settings, 'RUNTIME_CONFIG_PATH', runtime_file)
    monkeypatch.setattr(runtime_settings, 'settings', fake)
    monkeypatch.setattr(runtime_settings, 'is_hardened_deployment', lambda: True)

    runtime_settings.apply_runtime_settings()

    assert fake.auth_mode == 'openedx_sso'
    assert fake.allow_demo_role_header is False
    assert fake.use_mock_openedx is False
    assert fake.mock_llm is False
    assert fake.openai_model == 'gpt-5-mini-safe-runtime'


def test_invalid_optional_runtime_value_does_not_create_restart_loop(monkeypatch, tmp_path):
    runtime_file = tmp_path / 'runtime-settings.json'
    runtime_file.write_text('{"openai_max_parallel_calls": "not-a-number"}', encoding='utf-8')
    fake = SimpleNamespace(openai_max_parallel_calls=3)
    monkeypatch.setattr(runtime_settings, 'RUNTIME_CONFIG_PATH', runtime_file)
    monkeypatch.setattr(runtime_settings, 'settings', fake)
    monkeypatch.setattr(runtime_settings, 'is_hardened_deployment', lambda: True)

    runtime_settings.apply_runtime_settings()

    assert fake.openai_max_parallel_calls == 3


def test_frontend_docker_install_is_pinned_cached_and_retried():
    source = (ROOT / 'frontend' / 'Dockerfile').read_text(encoding='utf-8')
    package = json.loads((ROOT / 'frontend' / 'package.json').read_text(encoding='utf-8'))
    assert 'ARG NPM_VERSION=10.9.2' in source
    assert '--mount=type=cache,id=ai-server-frontend-npm' in source
    assert 'while ! npm ci' in source
    assert 'install_attempt' in source
    assert package['packageManager'] == 'npm@10.9.2'


def test_backend_healthcheck_uses_direct_http_and_long_warmup():
    compose = yaml.safe_load((ROOT / 'docker-compose.prod.yml').read_text(encoding='utf-8'))
    health = compose['services']['backend']['healthcheck']
    assert health['test'][:3] == ['CMD', 'python', '-c']
    assert 'http.client.HTTPConnection' in health['test'][3]
    assert health['start_period'] == '90s'
    assert health['interval'] == '10s'
    command = compose['services']['backend']['command']
    assert '--capture-output' in command
    assert '--access-logfile' in command


def test_hotfix_version_and_env_build_knob_are_current():
    assert VERSION in (ROOT / 'backend' / 'app' / 'core' / 'config.py').read_text(encoding='utf-8')
    assert VERSION in (ROOT / 'frontend' / 'package.json').read_text(encoding='utf-8')
    assert 'FRONTEND_NPM_VERSION=10.9.2' in (ROOT / '.env.production.example').read_text(encoding='utf-8')
