import json
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[3]
VERSION = '25.9.16.7.2.64.16.5.7.2.1'


def test_version_is_synchronized_in_active_runtime_files():
    targets = [
        ROOT / 'backend/app/core/config.py',
        ROOT / 'frontend/package.json',
        ROOT / 'frontend/package-lock.json',
        ROOT / 'e2e/package.json',
        ROOT / 'e2e/package-lock.json',
        ROOT / 'frontend/Dockerfile',
        ROOT / 'docker-compose.prod.yml',
        ROOT / '.env.production.example',
        ROOT / '.env.uat-http.example',
        ROOT / '.github/workflows/ci.yml',
    ]
    assert all(VERSION in path.read_text(encoding='utf-8') for path in targets)


def test_all_npm_resolved_urls_use_public_registry():
    for rel in ('frontend/package-lock.json', 'e2e/package-lock.json'):
        data = json.loads((ROOT / rel).read_text(encoding='utf-8'))
        urls = [
            package['resolved']
            for package in (data.get('packages') or {}).values()
            if isinstance(package, dict) and isinstance(package.get('resolved'), str)
        ]
        assert urls, rel
        assert all(urlparse(url).hostname == 'registry.npmjs.org' for url in urls), rel


def test_no_openai_internal_registry_marker_remains():
    markers = ('applied-caas-gateway', 'internal.api.openai.org', '/artifactory/api/npm/')
    for rel in ('frontend/package-lock.json', 'e2e/package-lock.json'):
        source = (ROOT / rel).read_text(encoding='utf-8').lower()
        assert all(marker not in source for marker in markers)


def test_npmrc_and_docker_force_public_registry():
    for rel in ('frontend/.npmrc', 'e2e/.npmrc'):
        source = (ROOT / rel).read_text(encoding='utf-8')
        assert 'registry=https://registry.npmjs.org/' in source
        assert 'replace-registry-host=always' in source
    dockerfile = (ROOT / 'frontend/Dockerfile').read_text(encoding='utf-8')
    assert 'NPM_CONFIG_REGISTRY=https://registry.npmjs.org/' in dockerfile
    assert '--registry="${NPM_CONFIG_REGISTRY}"' in dockerfile


def test_ci_fails_fast_before_npm_install():
    workflow = (ROOT / '.github/workflows/ci.yml').read_text(encoding='utf-8')
    assert 'npm-lockfile-registry:' in workflow
    assert 'NPM_CONFIG_REGISTRY: https://registry.npmjs.org/' in workflow
    assert './scripts/npm-public-registry-lockfile-report.sh' in workflow
    assert 'needs: npm-lockfile-registry' in workflow


def test_handoff_document_exists():
    assert (ROOT / 'AI_SERVER_PROJECT_HANDOFF_V25_9_16_7_2_64_16_5_7_2_1.md').exists()
