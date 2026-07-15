#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="${ROOT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
OUT_DIR="${1:-${OUT_DIR:-$ROOT_DIR/.runtime/performance-worker-reliability}}"
mkdir -p "$OUT_DIR"

python - "$ROOT_DIR" "$OUT_DIR" <<'PY'
from __future__ import annotations
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
out = Path(sys.argv[2])
worker = (root / 'backend/app/worker.py').read_text(encoding='utf-8')
config = (root / 'backend/app/core/config.py').read_text(encoding='utf-8')
academic = (root / 'backend/app/api/routes/academic.py').read_text(encoding='utf-8')
compose = (root / 'docker-compose.prod.yml').read_text(encoding='utf-8')
api = (root / 'frontend/lib/api.ts').read_text(encoding='utf-8')
teacher = (root / 'frontend/app/teacher-management/page.tsx').read_text(encoding='utf-8')
users = (root / 'frontend/app/users/page.tsx').read_text(encoding='utf-8')
bank_route = (root / 'backend/app/api/routes/question_bank_v2.py').read_text(encoding='utf-8')
analytics = (root / 'backend/app/services/learning_analytics/analytics_core_service.py').read_text(encoding='utf-8')
analytics_route = (root / 'backend/app/api/routes/learning_analytics.py').read_text(encoding='utf-8')

def check(code: str, ok: bool, message: str, severity: str = 'BLOCKER'):
    return {'code': code, 'ok': bool(ok), 'severity': 'INFO' if ok else severity, 'message': message}

checks = [
    check('CELERY_LATE_ACK', 'task_acks_late=bool(settings.celery_task_acks_late)' in worker and 'CELERY_TASK_ACKS_LATE=true' in (root / '.env.production.example').read_text(encoding='utf-8'), 'Celery late acknowledgement is configured.'),
    check('CELERY_WORKER_LOST_REQUEUE', 'task_reject_on_worker_lost=bool(settings.celery_task_reject_on_worker_lost)' in worker and 'CELERY_TASK_REJECT_ON_WORKER_LOST=true' in (root / '.env.production.example').read_text(encoding='utf-8'), 'Lost worker tasks are rejected for broker redelivery.'),
    check('CELERY_PREFETCH_ONE', 'worker_prefetch_multiplier=int(settings.celery_worker_prefetch_multiplier)' in worker and 'CELERY_WORKER_PREFETCH_MULTIPLIER=1' in (root / '.env.production.example').read_text(encoding='utf-8'), 'Worker prefetch is bounded to one by default.'),
    check('CELERY_TASK_ROUTES', all(token in worker for token in ["'queue': 'generation'", "'queue': 'sync'", "'queue': 'exports'", "'queue': 'analytics'"]), 'Heavy, sync, export and analytics tasks have explicit routes.'),
    check('CELERY_SPLIT_WORKERS', all(token in compose for token in ['worker-heavy:', 'worker-analytics:', '--queues=interactive,sync', '--queues=generation,exports', '--queues=analytics']), 'Compose runs isolated worker pools.'),
    check('CELERY_TIME_LIMITS', 'task_annotations={' in worker and 'soft_time_limit' in worker and 'time_limit' in worker, 'Task groups have soft/hard time limits.'),
    check('CELERY_PROCESS_RECYCLE', '--max-tasks-per-child=${CELERY_WORKER_MAX_TASKS_PER_CHILD:-25}' in compose and '--max-memory-per-child=${CELERY_WORKER_MAX_MEMORY_PER_CHILD_KB:-600000}' in compose, 'Worker children recycle by task count and memory.'),
    check('TEACHER_EXPORT_ASYNC_UI', 'Xuất trực tiếp' not in teacher and 'waitForAcademicTrainingTeacherReportJob' in teacher, 'Teacher export UI uses a durable background job.'),
    check('TEACHER_EXPORT_SYNC_GUARD', 'TEACHER_EXPORT_REQUIRES_BACKGROUND_JOB' in academic and 'academic_teacher_report_sync_export_max_teachers' in config, 'Synchronous teacher export has a hard size guard.'),
    check('TEACHER_EXPORT_DIRECT_FILE', '_write_training_teacher_report_xlsx(report, path)' in worker and 'path.write_bytes(content)' not in worker, 'Export worker writes workbook directly to shared storage.'),
    check('TEACHER_EXPORT_PUBLIC_ERROR', 'ACADEMIC_TEACHER_REPORT_FAILED' in worker and "job.error_message = str(exc)" not in worker[worker.index("def academic_teacher_report_job_task"):worker.index("@celery_app.task(name='analytics_ingest_task')")], 'Teacher export persists a stable public error while retaining exception details only in server audit/log.'),
    check('TEACHER_EXPORT_DEDUPE', "'request_key': request_key" in academic and 'active_request.get(\'request_key\') == request_key' in academic, 'Equivalent active exports are deduplicated.'),
    check('API_TIMEOUT_CANCEL', 'export type ApiFetchInit' in api and 'timeoutMs?: number' in api and 'signal: controller.signal' in api, 'API client has timeout and cancellation.'),
    check('API_RETRY_BACKOFF', 'RETRYABLE_STATUS_CODES' in api and 'retryAfterMs' in api and '2 ** attempt' in api, 'Safe requests use bounded retry/backoff.'),
    check('JOB_POLL_BACKOFF', 'maxIntervalMs' in api and 'backoffMultiplier' in api and 'sleepWithSignal' in api, 'Job polling uses abortable exponential backoff.'),
    check('ANALYTICS_CLASS_SCOPED_EVENTS', 'AnalyticsTrackingEvent.username.in_(target_usernames)' in analytics and 'class_id=class_id' in analytics_route, 'Class analytics recalculation filters tracking events to the AP class roster.'),
    check('SERVER_SIDE_SCOPE_SEARCH', 'searchSubjectChapters' in users and 'getSubjectChapters(headers)' not in users and "q: str | None = Query(None, max_length=120)" in bank_route, 'RBAC catalog uses bounded server-side search instead of eager full hierarchy loading.'),
]
blockers = [item for item in checks if not item['ok'] and item['severity'] == 'BLOCKER']
warnings = [item for item in checks if not item['ok'] and item['severity'] == 'WARNING']
payload = {
    'version': '25.9.16.7.2.64.16.5.6',
    'report_type': 'performance_worker_reliability',
    'status': 'READY' if not blockers and not warnings else ('BLOCKED' if blockers else 'READY_WITH_WARNINGS'),
    'checks': checks,
    'passed': sum(1 for item in checks if item['ok']),
    'blocker_count': len(blockers),
    'warning_count': len(warnings),
}
(out / 'performance-worker-reliability.json').write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(payload, ensure_ascii=False, indent=2))
raise SystemExit(1 if blockers else 0)
PY
