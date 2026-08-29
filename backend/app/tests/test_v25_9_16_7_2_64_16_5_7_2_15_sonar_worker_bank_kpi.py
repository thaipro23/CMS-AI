from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
VERSION = '25.9.16.7.2.64.16.5.7.2.18'


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding='utf-8')


def test_supplied_sonar_critical_source_contracts() -> None:
    route = read('backend/app/api/routes/question_bank_v2.py')
    review = read('backend/app/services/question_bank/generation_review.py')
    dashboard = read('backend/app/services/bank_dashboard_stats.py')
    assert route.count("'question_bank.version.question.bulk_review'") == 1
    assert "_BULK_REVIEW_AUDIT_ACTION = 'question_bank.version.question.bulk_review'" in route
    assert 'datetime.utcnow' not in review
    assert 'def _dashboard_next_action(' in dashboard
    assert 'def build_dashboard_next_actions(' in dashboard


def test_business_rbac_campus_normalizer_is_static() -> None:
    tree = ast.parse(read('backend/app/services/business_rbac.py'))
    classes = [node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == 'BusinessRBACService']
    assert classes
    methods = [node for node in classes[0].body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == 'normalize_campus_code']
    assert methods
    decorators = {ast.unparse(item) for item in methods[0].decorator_list}
    assert 'staticmethod' in decorators


def test_question_bank_facade_signatures_match_current_workflow_contracts() -> None:
    source = read('backend/app/services/question_bank_service.py')
    assert 'def _format_offering_candidate(self, item: dict) -> dict:' in source
    assert 'def _cleanup_stale_release_keys_for_chapter(self, *, chapter: SubjectChapter, reason: str) -> int:' in source
    assert 'def preview_quiz_from_release(' in source and 'bank_release_id: str' in source
    assert 'def _build_release_quiz_plan(' in source and 'release: QuestionBankRelease' in source
    assert 'def cancel_failed_release(self, *, release_id: str, actor: str | None = None) -> dict:' in source


def test_release_publish_is_worker_only_idempotent_and_reports_progress() -> None:
    route = read('backend/app/api/routes/question_bank_v2.py')
    worker = read('backend/app/worker.py')
    publish = read('backend/app/services/question_bank/release_publish.py')
    section = route[route.index('def _enqueue_release_publish_job'):route.index("@router.post('/releases/{release_id}/quiz/preview'")]
    assert '.publish_release_to_openedx(' not in section
    assert '_enqueue_bank_job_or_fail(db, job, bank_release_publish_task' in section
    assert "operation_type == 'release_publish'" in section or "BankOperationJob.operation_type == 'release_publish'" in section
    assert 'with_for_update()' in section
    assert 'skipped_duplicate_delivery' in worker
    assert 'progress_callback=report_progress' in worker
    for marker in ('report_progress(10,', 'report_progress(20,', 'report_progress(90,', 'report_progress(97,'):
        assert marker in publish
    published_assignment = publish.rfind("release.status = 'published'")
    completeness_check = publish.find('report_progress(90,')
    assert completeness_check >= 0 < published_assignment


def test_chapter_ui_enqueues_publish_shows_real_progress_and_restores_after_reload() -> None:
    page = read('frontend/app/bank/_components/pages/ChapterWorkspacePage.tsx')
    api = read('frontend/lib/api.ts')
    css = read('frontend/app/globals.css')
    assert 'enqueueBankReleasePublish' in page
    assert "'release_publish'" in page
    assert "operationType: 'release_publish'" in page
    assert "targetType: 'bank_release'" in page
    assert 'progressPercent' in page and 'progressLabel' in page
    assert 'aria-valuenow=' in page
    assert 'is-determinate' in page and 'is-determinate' in css
    assert 'export async function enqueueBankReleasePublish' in api
    publish_api = api[api.index('export async function enqueueBankReleasePublish'):api.index('export async function getCourseMappings')]
    assert 'enqueueAndWait' not in publish_api


def test_bank_dashboard_counts_generated_questions_and_does_not_fabricate_cache_usage() -> None:
    analytics = read('backend/app/services/bank_cost_analytics.py')
    generation = read('backend/app/services/question_bank/generation_review.py')
    page = read('frontend/app/bank/_components/pages/BankDashboardPage.tsx')
    gateway = read('backend/app/services/model_gateway.py')
    assert "Question.source_type == 'bank_material'" not in analytics
    assert 'Question.model_provider.isnot(None)' in analytics
    assert "notin_(['', 'manual'])" in analytics
    assert 'Chỉ hiển thị chi phí thực tế đã ghi nhận' not in page
    cache_line = next(line for line in generation.splitlines() if "prompt_cache_key='qbank:'" in line)
    assert 'difficulty' not in cache_line
    assert 'active_material_id' in cache_line and 'material_content' in cache_line and 'settings.openai_model' in cache_line
    assert 'cached_tokens' in gateway
    assert 'cached_input_tokens' in gateway


def test_current_version_contract_files_are_15() -> None:
    assert read('VERSION').strip() == VERSION
    for rel in (
        'backend/app/core/config.py', 'frontend/package.json', 'frontend/package-lock.json',
        'frontend/Dockerfile', 'docker-compose.prod.yml', 'deploy/k8s/base/kustomization.yaml',
        'deploy/k8s/jobs/kustomization.yaml', 'deploy/k8s/jobs/migrate.yaml',
        'scripts/build-k8s-images.sh', '.env.example', '.env.production.example',
        'Jenkinsfile', 'README.md', 'RUN_CURRENT.md',
    ):
        assert VERSION in read(rel), rel
