from pathlib import Path


def test_docker_compose_has_celery_beat_and_tracking_mount():
    compose = Path('docker-compose.prod.yml').read_text()
    assert 'container_name: ai-beat' in compose
    assert 'celery -A app.worker.celery_app beat' in compose
    assert '/openedx-data/lms/logs:ro' in compose
    assert 'OPENEDX_TRACKING_LOG_HOST_DIR' in compose


def test_scheduler_default_enabled_for_full_test_rollout():
    config = Path('backend/app/core/config.py').read_text()
    assert 'analytics_ingest_scheduler_enabled: bool = True' in config
    env = Path('.env.production.example').read_text()
    assert 'ANALYTICS_INGEST_SCHEDULER_ENABLED=true' in env
    assert 'OPENEDX_TRACKING_LOG_HOST_DIR=/home/thaitx3/.local/share/tutor/data/lms/logs' in env


def test_frontend_operational_tables_have_stt_and_no_duplicate_analytics_section():
    analytics = Path('frontend/app/analytics/learning/page.tsx').read_text()
    assert '<th>STT</th>' in analytics
    assert analytics.count('Dấu hiệu bất thường cần kiểm tra') >= 1
    assert '    <section className="card academic-unified-card">\n    <section className="card academic-unified-card">' not in analytics
    class_page = Path('frontend/app/student-management/classes/[classId]/page.tsx').read_text()
    assert '<th className="stt-col">STT</th>' in class_page
    assert 'td className="stt-cell">{(page - 1) * PAGE_SIZE + index + 1}</td>' in class_page
