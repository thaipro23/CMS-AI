from __future__ import annotations

import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]
VERSION = '25.9.16.7.2.64.16.5.7.1.1'


def test_ci_has_real_database_browser_and_container_jobs() -> None:
    workflow = (ROOT / '.github/workflows/ci.yml').read_text(encoding='utf-8')
    assert 'pgvector/pgvector:pg16' in workflow
    assert 'redis:7-alpine' in workflow
    assert 'browser-e2e' in workflow
    assert 'container-hardening' in workflow
    assert 'alembic -c alembic.ini upgrade head' in workflow


def test_playwright_and_frontend_quality_commands_are_versioned() -> None:
    package = json.loads((ROOT / 'frontend/package.json').read_text(encoding='utf-8'))
    assert package['version'] == VERSION
    assert '@playwright/test' in json.loads((ROOT / 'e2e/package.json').read_text(encoding='utf-8'))['devDependencies']
    for script in ('lint', 'typecheck', 'build', 'test:e2e:ci'):
        assert script in package['scripts']
    assert (ROOT / 'e2e/playwright.config.ts').exists()
    assert (ROOT / 'e2e/tests/production-smoke.spec.ts').exists()


def test_production_images_are_non_root_and_multi_stage() -> None:
    backend = (ROOT / 'backend/Dockerfile.prod').read_text(encoding='utf-8')
    frontend = (ROOT / 'frontend/Dockerfile').read_text(encoding='utf-8')
    assert ' AS wheels' in backend
    assert 'requirements-runtime.txt' in backend
    assert 'USER ${APP_UID}:${APP_GID}' in backend
    assert 'USER ${APP_UID}:${APP_GID}' in frontend
    assert 'chmod -R a-w /app' in frontend


def test_compose_separates_migration_and_hardens_runtime() -> None:
    compose = yaml.safe_load((ROOT / 'docker-compose.prod.yml').read_text(encoding='utf-8'))
    services = compose['services']
    assert services['migrate']['restart'] == 'no'
    assert 'alembic' in ' '.join(services['migrate']['command'])
    assert 'alembic' not in ' '.join(services['backend']['command'])
    for name in ('backend', 'worker', 'worker-heavy', 'worker-analytics', 'beat', 'frontend'):
        service = services[name]
        assert service['user'] == '10001:10001'
        assert service['read_only'] is True
        assert 'ALL' in service['cap_drop']
        assert 'no-new-privileges:true' in service['security_opt']
        assert service['pids_limit'] > 0
        assert service['mem_limit']
        assert service['cpus']


def test_integration_and_hardening_gates_exist() -> None:
    assert (ROOT / 'backend/app/tests/integration/test_ci_runtime_smoke.py').exists()
    assert (ROOT / 'scripts/ci-backend-tests.sh').exists()
    assert (ROOT / 'scripts/ci-e2e-container-hardening-report.sh').exists()
    assert (ROOT / '.github/dependabot.yml').exists()
