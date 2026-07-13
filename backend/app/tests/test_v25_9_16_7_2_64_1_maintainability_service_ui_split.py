from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
VERSION = '25.9.16.7.2.64.13'


def text(path: str) -> str:
    return (ROOT / path).read_text(encoding='utf-8')


def test_v64_1_version_and_docs():
    assert f"app_version: str = '{VERSION}'" in text('backend/app/core/config.py')
    assert f'"version": "{VERSION}"' in text('frontend/package.json')
    assert f'NEXT_PUBLIC_APP_VERSION: ${{APP_VERSION:-{VERSION}}}' in text('docker-compose.prod.yml')
    assert 'Question Bank Quiz Creation/Auto-map Workflow Split' in text('README.md')
    assert 'RUN_V25_9_16_7_2_64_13.md' in text('README.md')
    assert text('CHANGELOG.md').startswith('## v25.9.16.7.2.64.13 — Academic AP Sync + External Assignment Workflow Split')
    assert (ROOT / 'docs/RELEASE_v25.9.16.7.2.64.13_QUESTION_BANK_QUIZ_CREATION_AUTOMAP_WORKFLOW_SPLIT.md').exists()
    assert (ROOT / 'docs/CLAUDE_CODE_REVIEW_HANDOFF_V25_9_16_7_2_64_13.md').exists()


def test_academic_service_helpers_are_split_but_reexported():
    service = text('backend/app/services/academic_service.py')
    helpers = text('backend/app/services/academic/helpers.py')
    assert 'from app.services.academic.helpers import' in service
    for name in ['_actor_names', '_page', '_boolish', '_derive_mapping_status', 'AccessDecision']:
        assert name in service
        assert name in helpers
    assert 'class AcademicService' in service
    assert 'def _actor_names' not in service
    assert 'def _actor_names' in helpers


def test_question_bank_helpers_are_split_but_reexported():
    service = text('backend/app/services/question_bank_service.py')
    helpers = text('backend/app/services/question_bank/helpers.py')
    assert 'from app.services.question_bank.helpers import' in service
    for name in ['slugify', 'normalize_academic_term_code', 'BANK_UPLOAD_MAX_BYTES', '_ui_notice', 'stable_concept_identity']:
        assert name in service
        assert name in helpers
    assert 'class VersionedQuestionBankService' in service
    assert 'def slugify' not in service
    assert 'def slugify' in helpers


def test_learning_analytics_presentation_helpers_are_split():
    service = text('backend/app/services/learning_analytics/analytics_core_service.py')
    presentation = text('backend/app/services/learning_analytics/presentation.py')
    assert 'from app.services.learning_analytics.presentation import' in service
    assert '_safe_label = staticmethod(_presentation_safe_label)' in service
    assert '_sla_status = staticmethod(_presentation_sla_status)' in service
    assert 'def safe_label' in presentation
    assert 'def sla_status' in presentation
    assert 'def _safe_label' not in service
    assert 'Không cần xử lý' in presentation


def test_global_css_is_split_for_ops_readiness():
    globals_css = text('frontend/app/globals.css')
    ops_css = text('frontend/styles/ops-readiness.css')
    assert "@import '../styles/ops-readiness.css';" in globals_css.splitlines()[0]
    assert '.ops-readiness-page' not in globals_css
    assert '.ops-readiness-page' in ops_css
    assert '.ops-gate-panel' in ops_css
    assert len(globals_css.splitlines()) < 9000


def test_maintainability_contract_tracks_split_modules():
    service = text('backend/app/services/maintainability_contract.py')
    for needle in [
        'backend/app/services/academic/helpers.py',
        'backend/app/services/question_bank/helpers.py',
        'backend/app/services/learning_analytics/presentation.py',
        'frontend/styles/ops-readiness.css',
    ]:
        assert needle in service
    assert 'service_split_modules' in service


def test_v64_1_no_new_alembic_revision():
    assert (ROOT / 'backend/alembic/versions/0052_v25_9_16_7_2_27_learning_behavior_logic_calibration.py').exists()
    assert not list((ROOT / 'backend/alembic/versions').glob('0053*.py'))
