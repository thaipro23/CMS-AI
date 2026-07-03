from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
VERSION = '25.9.16.7.2.38'


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding='utf-8')


def test_v35_version_is_synchronized_across_runtime_fallbacks_and_examples():
    assert f"app_version: str = '{VERSION}'" in read('backend/app/core/config.py')
    assert f'"version": "{VERSION}"' in read('frontend/package.json')
    assert f'NEXT_PUBLIC_APP_VERSION: ${{APP_VERSION:-{VERSION}}}' in read('docker-compose.prod.yml')
    assert f"process.env.NEXT_PUBLIC_APP_VERSION || '{VERSION}'" in read('frontend/components/layout/AppShell.tsx')
    assert f'APP_VERSION={VERSION}' in read('.env.example')
    assert f'APP_VERSION={VERSION}' in read('.env.production.example')
    assert f'# AI Server Open edX — v{VERSION}' in read('README.md')
    assert f'# v{VERSION} — Bank Compact Table UX + Sidebar Taxonomy' in read('RUN_CURRENT.md')


def test_post_ingest_recalculate_settings_and_env_are_exposed():
    config = read('backend/app/core/config.py')
    env = read('.env.production.example')
    assert 'analytics_post_ingest_recalculate_enabled: bool = True' in config
    assert 'analytics_post_ingest_recalculate_cooldown_seconds: int = 900' in config
    assert 'analytics_post_ingest_recalculate_max_jobs_per_run: int = 10' in config
    assert 'ANALYTICS_POST_INGEST_RECALCULATE_ENABLED=true' in env
    assert 'ANALYTICS_POST_INGEST_RECALCULATE_COOLDOWN_SECONDS=900' in env
    assert 'ANALYTICS_POST_INGEST_RECALCULATE_MAX_JOBS_PER_RUN=10' in env


def test_run_ingest_collects_impacted_courses_and_triggers_orchestrator_after_commit():
    service = read('backend/app/services/learning_analytics/analytics_core_service.py')
    run_ingest = service.split('def run_ingest', 1)[1].split('def rebuild_session_structure_from_blocks', 1)[0]
    assert 'impacted_course_usernames: dict[str, set[str]] = defaultdict(set)' in run_ingest
    assert "impacted_course_usernames[str(parsed.course_id or '').strip()].add" in run_ingest
    assert "'impacted_course_count': len(impacted_course_usernames)" in run_ingest
    assert "'impacted_user_count': sum(len(users) for users in impacted_course_usernames.values())" in run_ingest
    assert 'self.db.commit()\n            post_ingest_recalculate' in run_ingest
    assert 'self.enqueue_post_ingest_recalculate_jobs(' in run_ingest
    assert "'post_ingest_recalculate': post_ingest_recalculate" in run_ingest


def test_orchestrator_is_class_scoped_debounced_and_capped_not_per_student():
    service = read('backend/app/services/learning_analytics/analytics_core_service.py')
    orchestrator = service.split('def enqueue_post_ingest_recalculate_jobs', 1)[1].split('def run_ingest', 1)[0]
    assert 'AcademicClassCourseMapping.openedx_course_id' in service
    assert 'AcademicCourseMapping.openedx_course_id' in service
    assert "job_type='learning_analytics_recalculate'" in orchestrator
    assert "requested_by='system:analytics-ingest'" in orchestrator
    assert "AnalyticsClassSyncJob" not in orchestrator  # guard against accidental new model name
    assert "AcademicClassSyncJob.job_type == 'learning_analytics_recalculate'" in orchestrator
    assert "AcademicClassSyncJob.status.in_(['queued', 'running'])" in orchestrator
    assert "skipped['CLASS_JOB_ALREADY_ACTIVE']" in orchestrator
    assert "skipped['CLASS_COOLDOWN_ACTIVE']" in orchestrator
    assert "skipped['RUN_JOB_CAP_REACHED']" in orchestrator
    assert 'analytics_class_recalculate_task.delay(job.id)' in orchestrator
    assert "'username': None" in orchestrator
    assert "'impacted_usernames_sample': impacted_users[:20]" in orchestrator


def test_changelog_documents_v35_before_v34_and_no_new_migration():
    changelog = read('CHANGELOG.md')
    assert changelog.startswith('## v25.9.16.7.2.38 — Bank Compact Table UX + Sidebar Taxonomy')
    assert changelog.index('## v25.9.16.7.2.38 — Bank Compact Table UX + Sidebar Taxonomy') < changelog.index('## v25.9.16.7.2.34 — Production Polish Version Sync + Analytics Roster QA')
    assert '- No migration.' in changelog.split('## v25.9.16.7.2.34', 1)[0]
