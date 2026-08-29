from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
VERSION = '25.9.16.7.2.64.13'
TITLE = 'Bank Workflow UX Completion'


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding='utf-8')


def test_v47_version_docs_and_changelog_are_current():
    assert f"app_version: str = '{VERSION}'" in read('backend/app/core/config.py')
    assert f'"version": "{VERSION}"' in read('frontend/package.json')
    assert f'NEXT_PUBLIC_APP_VERSION: ${{APP_VERSION:-{VERSION}}}' in read('docker-compose.prod.yml')
    assert f"process.env.NEXT_PUBLIC_APP_VERSION || '{VERSION}'" in read('frontend/components/layout/AppShell.tsx')
    assert f'# v{VERSION} — {TITLE}' in read('RUN_CURRENT.md')
    assert f'# v{VERSION} — {TITLE}' in read('RUN_CURRENT.md')
    assert read('CHANGELOG.md').startswith(f'## v{VERSION} — {TITLE}')


def test_v47_backend_defaults_final_test_and_reports_production_gate():
    service = read('backend/app/services/question_bank_service.py') + read('backend/app/services/question_bank/quiz_creation.py')
    assert "return 'final_test'" in service
    assert "return 'assignment'" in service
    assert 'def _quiz_production_status_for_mapping(' in service
    assert "'status_code': 'READY_TO_CREATE'" in service
    assert "'status_code': 'SKIPPED_NO_CREATE'" in service
    assert "'MISSING_' + '_AND_'.join(missing)" in service
    assert "'production_gate': production_gate" in service
    assert "'final_test_count': final_test_count" in service
    assert "'missing_section_count': missing_section_count" in service
    assert "'missing_release_count': missing_release_count" in service


def test_v47_frontend_bank_quiz_has_gate_and_explicit_columns():
    page = read('frontend/app/bank/quiz/page.tsx')
    types = read('frontend/types/index.ts')
    css = read('frontend/app/globals.css') + read('frontend/styles/ops-readiness.css')
    assert 'quiz-production-gate-strip' in page
    assert '<th>Loại</th>' in page
    assert '<th>Điều kiện</th>' in page
    assert 'actionTypeBadge(item)' in page
    assert 'missingRequirementLabel' in page
    assert 'Thiếu Section' in page
    assert 'Thiếu Release' in page
    assert 'Final test mặc định' not in page  # copy should be operational, not release-note text.
    assert 'status_code?: string | null' in types
    assert 'missing_requirements?: string[]' in types
    assert 'production_ready?: boolean' in types
    assert '.bank-quiz-page .quiz-map-table th:last-child' in css
    assert 'position: sticky' in css


def test_v47_no_migration_added():
    versions = sorted((ROOT / 'backend/alembic/versions').glob('*.py'))
    assert versions[-1].name == '0052_v25_9_16_7_2_27_learning_behavior_logic_calibration.py'
