from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
VERSION = '25.9.16.7.2.64.13'
TITLE = 'Bank Release Publish Reliability + Rollback QA'


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding='utf-8')


def test_v52_version_sync_for_claude_review_build_gate() -> None:
    targets = [
        'backend/app/core/config.py',
        'frontend/package.json',
        'docker-compose.prod.yml',
        '.env.example',
        '.env.production.example',
        'frontend/components/layout/AppShell.tsx',
        'README.md',
        'RUN_CURRENT.md',
        'RUN_V25_9_16_7_2_53.md',
        'CHANGELOG.md',
    ]
    for target in targets:
        assert VERSION in _read(target), target
    assert f'# v{VERSION} — {TITLE}' in _read('RUN_CURRENT.md')
    assert _read('CHANGELOG.md').startswith(f'## v{VERSION} — {TITLE}')


def test_v52_uat_build_gate_script_is_guarded_and_actionable() -> None:
    script = _read('scripts/uat-build-gate.sh')
    assert 'set -Eeuo pipefail' in script
    assert 'EXPECTED_VERSION="${EXPECTED_VERSION:-25.9.16.7.2.64.13}"' in script
    assert 'STRICT="${STRICT:-0}"' in script
    assert 'RUN_FRONTEND_BUILD="${RUN_FRONTEND_BUILD:-0}"' in script
    assert 'build-gate-summary.json' in script
    assert 'BUILD_GATE_SUMMARY.md' in script
    assert 'python -m compileall -q backend/app' in script
    assert 'scripts/frontend-build-verify.sh' in script
    assert 'RUN_FRONTEND_INSTALL' in script
    assert 'frontend-build-instructions.txt' in script
    assert 'docker compose -f docker-compose.prod.yml --env-file .env.production config' in script
    assert 'RUN_REVIEW_PACK' in script


def test_v52_claude_review_pack_includes_build_gate_evidence() -> None:
    script = _read('scripts/claude-code-review-pack.sh')
    assert 'runtime-dependency-status.json' in script
    assert 'frontend-typecheck-required.txt' in script
    assert 'INCLUDE_BUILD_GATE' in script
    assert 'STRICT_BUILD_GATE' in script
    assert './scripts/uat-build-gate.sh' in script
    assert 'bash -n scripts/uat-build-gate.sh' in script
    assert 'EXPECTED_VERSION' in script and VERSION in script


def test_v52_handoff_docs_are_explicit_for_reviewers() -> None:
    handoff = _read('docs/CLAUDE_CODE_REVIEW_HANDOFF_V25_9_16_7_2_53.md')
    release = _read('docs/RELEASE_v25.9.16.7.2.64.13_UAT_RUNTIME_VERIFICATION_FRONTEND_BUILD_FIX.md')
    combined = handoff + release
    assert 'frontend-build-verify.sh' in combined
    assert 'uat-runtime-verify.sh' in combined
    assert 'scripts/uat-build-gate.sh' in combined
    assert 'STRICT=1' in combined
    assert 'npm run typecheck' in combined
    assert '0052_v25_9_16_7_2_27_learning_behavior_logic_calibration.py' in combined
    assert 'Không migration mới' in release


def test_v52_does_not_add_new_migration() -> None:
    migrations = sorted((ROOT / 'backend/alembic/versions').glob('*.py'))
    names = [p.name for p in migrations]
    assert '0052_v25_9_16_7_2_27_learning_behavior_logic_calibration.py' in names
    assert not any(name.startswith('0053_') or name.startswith('0054_') for name in names)
