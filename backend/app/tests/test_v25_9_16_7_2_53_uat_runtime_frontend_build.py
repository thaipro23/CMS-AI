from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[3]
VERSION = '25.9.16.7.2.64.12'


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding='utf-8')


def test_v53_frontend_build_metadata_is_not_stale() -> None:
    package = json.loads(_read('frontend/package.json'))
    lock = json.loads(_read('frontend/package-lock.json'))
    dockerfile = _read('frontend/Dockerfile')

    assert package['version'] == VERSION
    assert lock['version'] == VERSION
    assert lock['packages']['']['version'] == VERSION
    assert f'ARG NEXT_PUBLIC_APP_VERSION={VERSION}' in dockerfile
    assert 'ARG NEXT_PUBLIC_APP_VERSION=25.9.16.7.2.31' not in dockerfile
    assert '25.9.16.7.2.18' not in _read('frontend/package-lock.json')[:300]


def test_v53_frontend_build_verify_script_is_real_gate() -> None:
    script = _read('scripts/frontend-build-verify.sh')
    assert f'EXPECTED_VERSION="${{EXPECTED_VERSION:-{VERSION}}}"' in script
    assert 'frontend-version-metadata.json' in script
    assert 'package-lock.json' in script
    assert 'npm ci --include=dev --no-audit --no-fund' in script
    assert 'npm run typecheck' in script
    assert 'npm run build' in script
    assert '.next/standalone/server.js' in script
    assert 'FRONTEND_BUILD_SUMMARY.md' in script


def test_v53_runtime_verify_is_read_only_and_covers_uat_endpoints() -> None:
    script = _read('scripts/uat-runtime-verify.sh')
    assert f'EXPECTED_VERSION="${{EXPECTED_VERSION:-{VERSION}}}"' in script
    assert '/health/build' in script
    assert '/health/readiness' in script
    assert '/analytics/ops/sla' in script
    assert '/analytics/ops/pilot-acceptance' in script
    assert '/analytics/ops/evidence-pack' in script
    assert '/rbac/scope-audit' in script
    assert '/analytics/classes/$CLASS_ID/doctor' in script
    assert 'RUNTIME_VERIFY_SUMMARY.md' in script
    forbidden = ['curl -X POST', 'curl -X DELETE', 'recalculate', 'uat-cleanup']
    for term in forbidden:
        assert term not in script


def test_v53_build_gate_delegates_frontend_build_verifier() -> None:
    script = _read('scripts/uat-build-gate.sh')
    assert f'EXPECTED_VERSION="${{EXPECTED_VERSION:-{VERSION}}}"' in script
    assert 'RUN_FRONTEND_INSTALL="${RUN_FRONTEND_INSTALL:-0}"' in script
    assert 'frontend/Dockerfile' in script
    assert 'frontend/package-lock.json' in script
    assert './scripts/frontend-build-verify.sh' in script
    assert 'RUN_FRONTEND_BUILD=1' in script
    assert 'RUN_NPM_CI="$RUN_FRONTEND_INSTALL"' in script


def test_v53_claude_review_pack_includes_runtime_build_evidence() -> None:
    script = _read('scripts/claude-code-review-pack.sh')
    assert f'EXPECTED_VERSION="${{EXPECTED_VERSION:-{VERSION}}}"' in script
    assert 'scripts/frontend-build-verify.sh' in script
    assert 'scripts/uat-runtime-verify.sh' in script
    assert 'frontend_package_lock_present' in script
    assert 'This version adds UAT runtime verification and frontend build verification gates' in script or 'performance/load readiness gate' in script


def test_v53_docs_and_changelog_are_current() -> None:
    assert _read('CHANGELOG.md').startswith(f'## v{VERSION} — Performance Load Hardening')
    assert f'v{VERSION} — Performance Load Hardening' in _read('README.md')
    assert 'ai_server_openedx_v25_9_16_7_2_64_12' in _read('RUN_CURRENT.md')
    assert 'Performance Load Hardening' in _read('docs/RELEASE_v25.9.16.7.2.64.12_PERFORMANCE_LOAD_HARDENING.md')
    assert 'Claude Code Review Handoff — v25.9.16.7.2.64.12' in _read('docs/CLAUDE_CODE_REVIEW_HANDOFF_V25_9_16_7_2_57.md')
