from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
VERSION = '25.9.16.7.2.64.16.5.7.2.18'


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding='utf-8')


def test_version_is_synchronized_across_runtime_artifacts():
    for path in (
        'backend/app/core/config.py',
        'frontend/package.json',
        'frontend/package-lock.json',
        'frontend/Dockerfile',
        'docker-compose.prod.yml',
        '.env.example',
        '.env.production.example',
        'README.md',
        'RUN_CURRENT.md',
    ):
        assert VERSION in read(path), path


def test_release_keeps_historical_migrations_and_current_0061_head():
    versions = ROOT / 'backend/alembic/versions'
    assert (versions / '0053_v25_9_16_7_2_64_16_5_4_diff_idempotency.py').exists()
    assert (versions / '0057_v25_9_16_7_2_64_35_udemy_hardening_indexes.py').exists()
    assert (versions / '0058_v25_9_16_7_2_64_36_question_pedagogy.py').exists()
    assert (versions / '0059_v25_9_16_7_2_64_37_question_bank_legacy_hygiene.py').exists()
    assert (versions / '0060_v25_9_16_7_2_64_38_question_authoring_types_media.py').exists()
    assert (versions / '0061_v25_9_16_7_2_64_39_quiz_blueprint_type_quota.py').exists()


def test_accessible_dialog_is_the_only_active_dialog_primitive():
    dialog = read('frontend/components/ui/AccessibleDialog.tsx')
    assert 'dialogStack' in dialog
    assert 'lockBodyScroll()' in dialog
    assert "event.key === 'Escape'" in dialog
    assert "event.key !== 'Tab'" in dialog
    assert 'previousActive' in dialog
    for path in (ROOT / 'frontend').rglob('*.tsx'):
        if 'node_modules' in path.parts or '.next' in path.parts or path.name == 'AccessibleDialog.tsx':
            continue
        source = path.read_text(encoding='utf-8')
        assert 'role="dialog"' not in source, path
        assert 'aria-modal="true"' not in source, path
        assert 'modal-backdrop' not in source, path
        assert 'bank-popup-backdrop' not in source, path


def test_native_alert_and_confirm_are_removed():
    source = '\n'.join(
        path.read_text(encoding='utf-8')
        for path in (ROOT / 'frontend').rglob('*.tsx')
        if 'node_modules' not in path.parts and '.next' not in path.parts
    )
    assert 'window.alert(' not in source
    assert 'window.confirm(' not in source
    assert '\nalert(' not in source
    assert '\nconfirm(' not in source


def test_route_level_runtime_boundaries_exist():
    for path in ('loading.tsx', 'error.tsx', 'global-error.tsx', 'not-found.tsx'):
        assert (ROOT / 'frontend/app' / path).exists(), path


def test_enterprise_table_executes_declared_runtime_contracts():
    source = read('frontend/components/table/EnterpriseDataTable.tsx')
    assert 'column.defaultVisible !== false' in source
    assert 'truncate-lines-${layout.column.truncateLines}' in source
    assert 'onSortChange?:' in source
    assert 'aria-sort=' in source
    assert 'enterprise-sort-button' in source


def test_frontend_runtime_gate_is_integrated_into_review_and_uat():
    for path in ('scripts/claude-code-review-pack.sh', 'scripts/uat-build-gate.sh'):
        source = read(path)
        assert 'frontend-runtime-contracts-report.sh' in source
        assert 'FRONTEND_RUNTIME_CONTRACTS' in source
