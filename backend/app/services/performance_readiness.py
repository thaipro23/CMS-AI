from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func, text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.academic import AcademicBulkOperationJob, AcademicClassSyncJob, AcademicTeacherReportJob
from app.models.job import GenerationJob
from app.models.question_bank import BankOperationJob


class PerformanceReadinessService:
    """Read-only performance/load readiness report for UAT and production pilot.

    The report is intentionally conservative and safe for request handlers: it
    does not scan raw tracking.log, does not execute heavy query plans, does not
    enqueue jobs, and does not mutate data. Table size data uses PostgreSQL
    statistics when available and degrades gracefully outside PostgreSQL.
    """

    CRITICAL_INDEXES: dict[str, list[str]] = {
        'academic_classes': [
            'ix_academic_classes_scope_lookup',
            'ix_academic_classes_teacher_lookup',
            'ix_academic_classes_campus_branch',
        ],
        'academic_class_students': ['ix_academic_class_students_class_student'],
        'academic_class_sync_jobs': [
            'ix_academic_class_sync_jobs_class_status_created',
            'ix_academic_class_sync_jobs_type_status_created',
        ],
        'academic_bulk_operation_jobs': [
            'ix_academic_bulk_operation_scope_status',
            'ix_academic_bulk_operation_type_created',
        ],
        'academic_teacher_report_jobs': ['ix_academic_teacher_report_jobs_scope_status'],
        'analytics_tracking_events': [
            'ix_analytics_events_course_user_time',
            'ix_analytics_events_course_video_time',
            'ix_analytics_events_type_time',
        ],
        'analytics_student_video_progress': ['ix_analytics_video_progress_course_user_session'],
        'analytics_student_session_progress': ['ix_analytics_session_progress_course_user_week'],
        'analytics_learning_behavior_snapshots': [
            'ix_analytics_behavior_class_classification',
            'ix_analytics_behavior_course_classification',
        ],
        'ai_questions': [
            'ix_ai_questions_bank_status_created_id',
            'ix_ai_questions_chapter_status_created',
            'ix_ai_questions_bank_difficulty_status_retired',
        ],
        'ai_bank_operation_jobs': [
            'ix_ai_bank_operation_jobs_status_created',
            'ix_ai_bank_operation_jobs_target_status_created',
        ],
        'ai_course_quiz_instances': [
            'ix_ai_course_quiz_instances_release_status_created',
            'ix_ai_course_quiz_instances_course_status_created',
        ],
    }

    WATCH_TABLES = sorted(CRITICAL_INDEXES.keys())

    def __init__(self, db: Session):
        self.db = db

    def performance_readiness_report(self) -> dict[str, Any]:
        checks: list[dict[str, Any]] = []
        checks.extend(self._configuration_checks())
        checks.extend(self._index_contract_checks())
        checks.extend(self._queue_pressure_checks())
        table_estimates = self._table_estimates()
        checks.extend(self._table_growth_checks(table_estimates))

        blockers = [c for c in checks if c.get('severity') == 'BLOCKER']
        warnings = [c for c in checks if c.get('severity') == 'WARNING']
        if blockers:
            status = 'BLOCKED'
            summary = 'Cần xử lý hiệu năng trước khi mở rộng UAT/pilot.'
        elif warnings:
            status = 'READY_WITH_WARNINGS'
            summary = 'Có thể UAT có kiểm soát, cần theo dõi cảnh báo hiệu năng.'
        else:
            status = 'READY'
            summary = 'Hiệu năng nền tảng đủ điều kiện cho UAT/pilot có kiểm soát.'

        sections = self._sections_from_checks(checks)
        next_actions = self._next_actions(checks)
        return {
            'version': settings.app_version,
            'report_type': 'performance_load_readiness',
            'generated_at': datetime.utcnow().isoformat(),
            'status': status,
            'summary_label': summary,
            'blocker_count': len(blockers),
            'warning_count': len(warnings),
            'checks': checks,
            'sections': sections,
            'table_estimates': table_estimates,
            'queue_pressure': self._queue_pressure_payload(),
            'limits': self._limits_payload(),
            'next_actions': next_actions,
            'safe_policy': 'read_only_no_query_plan_execution_no_mutation',
            'read_only_guarantees': [
                'Không scan raw tracking.log trong request',
                'Không chạy heavy query plans hoặc query nặng để đo hiệu năng',
                'Không enqueue job, không recalculate, không mutate dữ liệu',
                'Chỉ dùng metadata config, index contract, job counters và pg_stat estimates nếu có',
            ],
            'disclaimer': 'Báo cáo này là preflight performance gate. Nếu bảng lớn nhanh hoặc query thực tế chậm, cần chạy thêm pg_stat_statements/plan review trên UAT bằng DBA.',
        }

    def _configuration_checks(self) -> list[dict[str, Any]]:
        checks: list[dict[str, Any]] = []
        def add(code: str, ok: bool, severity: str, actual: Any, target: str, action: str):
            checks.append({
                'category': 'configuration',
                'code': code,
                'severity': 'INFO' if ok else severity,
                'ok': ok,
                'actual': actual,
                'target': target,
                'message': f'{code} = {actual}; mục tiêu {target}.',
                'action': '' if ok else action,
            })
        add('DB_POOL_SIZE', int(settings.db_pool_size) >= 10, 'WARNING', settings.db_pool_size, '>= 10', 'Tăng DB_POOL_SIZE nếu UAT có nhiều request song song.')
        add('DB_MAX_OVERFLOW', int(settings.db_max_overflow) >= 10, 'WARNING', settings.db_max_overflow, '>= 10', 'Tăng DB_MAX_OVERFLOW hoặc giảm concurrency nếu thấy timeout pool.')
        add('DB_STATEMENT_TIMEOUT_MS', 0 < int(settings.db_statement_timeout_ms) <= 10000, 'WARNING', settings.db_statement_timeout_ms, '1..10000', 'Đặt DB_STATEMENT_TIMEOUT_MS để tránh query runaway.')
        add('ANALYTICS_DASHBOARD_MAX_PAGE_SIZE', int(settings.analytics_dashboard_max_page_size) <= 500, 'BLOCKER', settings.analytics_dashboard_max_page_size, '<= 500', 'Giảm ANALYTICS_DASHBOARD_MAX_PAGE_SIZE để tránh trả response quá lớn.')
        add('BANK_SEARCH_MAX_RESULTS', int(settings.bank_search_max_results) <= 100, 'WARNING', settings.bank_search_max_results, '<= 100', 'Giảm BANK_SEARCH_MAX_RESULTS nếu Bank Search chậm khi dữ liệu lớn.')
        add('OPENEDX_CONNECTOR_MAX_BATCH_SIZE', int(settings.openedx_connector_max_batch_size) <= 200, 'WARNING', settings.openedx_connector_max_batch_size, '<= 200', 'Giữ batch connector nhỏ để tránh timeout CMS/Open edX.')
        add('ANALYTICS_POST_INGEST_MAX_JOBS_PER_RUN', int(settings.analytics_post_ingest_recalculate_max_jobs_per_run) <= 20, 'BLOCKER', settings.analytics_post_ingest_recalculate_max_jobs_per_run, '<= 20', 'Giảm số job tạo sau mỗi ingest để tránh worker/DB bị dồn.')
        add('ANALYTICS_BACKFILL_MAX_ACTIVE_JOBS', int(settings.analytics_backfill_max_active_jobs) <= 50, 'WARNING', settings.analytics_backfill_max_active_jobs, '<= 50', 'Giảm active backfill jobs nếu DB/worker có độ trễ cao.')
        add('CELERY_WORKER_PREFETCH_MULTIPLIER', int(settings.celery_worker_prefetch_multiplier) == 1, 'WARNING', settings.celery_worker_prefetch_multiplier, '= 1', 'Đặt prefetch=1 để job dài không chiếm trước nhiều task.')
        add('CELERY_TASK_ACKS_LATE', bool(settings.celery_task_acks_late), 'BLOCKER', settings.celery_task_acks_late, '= true', 'Bật late acknowledgement để task được phục hồi khi worker mất.')
        add('CELERY_REJECT_ON_WORKER_LOST', bool(settings.celery_task_reject_on_worker_lost), 'BLOCKER', settings.celery_task_reject_on_worker_lost, '= true', 'Bật reject_on_worker_lost để broker phát lại task khi process chết.')
        add('CELERY_VISIBILITY_TIMEOUT', int(settings.celery_broker_visibility_timeout_seconds) > int(settings.celery_default_time_limit_seconds), 'BLOCKER', settings.celery_broker_visibility_timeout_seconds, f'> {settings.celery_default_time_limit_seconds}', 'Đặt visibility timeout lớn hơn hard time limit của task.')
        add('CELERY_MAX_TASKS_PER_CHILD', int(settings.celery_worker_max_tasks_per_child) <= 100, 'WARNING', settings.celery_worker_max_tasks_per_child, '1..100', 'Giới hạn task/process để thu hồi memory sau OCR/Excel/AI workload.')
        add('TEACHER_SYNC_EXPORT_LIMIT', int(settings.academic_teacher_report_sync_export_max_teachers) <= 50, 'WARNING', settings.academic_teacher_report_sync_export_max_teachers, '<= 50', 'Giữ export đồng bộ nhỏ; dataset lớn phải qua Celery export job.')
        return checks

    def _index_contract_checks(self) -> list[dict[str, Any]]:
        checks: list[dict[str, Any]] = []
        available = self._available_model_indexes()
        for table, required in self.CRITICAL_INDEXES.items():
            current = available.get(table, set())
            missing = [name for name in required if name not in current]
            checks.append({
                'category': 'index_contract',
                'code': f'INDEX_CONTRACT_{table.upper()}',
                'severity': 'BLOCKER' if missing else 'INFO',
                'ok': not missing,
                'table': table,
                'required_indexes': required,
                'missing_indexes': missing,
                'message': 'Thiếu index quan trọng cho query production.' if missing else 'Index contract trong model đã đủ cho query trọng điểm.',
                'action': 'Thêm migration index có down_revision đúng rồi chạy Alembic trên UAT.' if missing else '',
            })
        return checks

    def _available_model_indexes(self) -> dict[str, set[str]]:
        from app.db.session import Base
        result: dict[str, set[str]] = {}
        for table in Base.metadata.tables.values():
            result[table.name] = {idx.name for idx in table.indexes if idx.name}
        return result

    def _queue_pressure_checks(self) -> list[dict[str, Any]]:
        payload = self._queue_pressure_payload()
        active_total = int(payload.get('active_total') or 0)
        failed_recent = int(payload.get('failed_last_hour_total') or 0)
        checks = []
        checks.append({
            'category': 'queue_pressure',
            'code': 'ACTIVE_JOB_PRESSURE',
            'severity': 'WARNING' if active_total > int(settings.analytics_sla_max_queued_jobs) else 'INFO',
            'ok': active_total <= int(settings.analytics_sla_max_queued_jobs),
            'actual': active_total,
            'target': f"<= {settings.analytics_sla_max_queued_jobs}",
            'message': f'Có {active_total} job active/queued theo các bảng vận hành chính.',
            'action': 'Giảm batch/backfill, kiểm tra worker Celery và DB nếu hàng đợi tăng.' if active_total > int(settings.analytics_sla_max_queued_jobs) else '',
        })
        checks.append({
            'category': 'queue_pressure',
            'code': 'FAILED_JOB_LAST_HOUR',
            'severity': 'WARNING' if failed_recent > int(settings.analytics_sla_max_failed_jobs_last_hour) else 'INFO',
            'ok': failed_recent <= int(settings.analytics_sla_max_failed_jobs_last_hour),
            'actual': failed_recent,
            'target': f"<= {settings.analytics_sla_max_failed_jobs_last_hour}",
            'message': f'Có {failed_recent} job lỗi trong 1 giờ gần nhất.',
            'action': 'Mở /jobs hoặc audit để xem lỗi worker/connector gần nhất.' if failed_recent > int(settings.analytics_sla_max_failed_jobs_last_hour) else '',
        })
        return checks

    def _queue_pressure_payload(self) -> dict[str, Any]:
        since = datetime.utcnow() - timedelta(hours=1)
        models = [
            ('class_sync', AcademicClassSyncJob),
            ('bulk_operation', AcademicBulkOperationJob),
            ('teacher_report', AcademicTeacherReportJob),
            ('bank_operation', BankOperationJob),
            ('generation', GenerationJob),
        ]
        active_statuses = {'queued', 'running', 'pending', 'in_progress', 'processing'}
        failed_statuses = {'failed', 'error'}
        by_table: dict[str, Any] = {}
        active_total = 0
        failed_last_hour_total = 0
        for key, model in models:
            status_col = getattr(model, 'status', None)
            created_col = getattr(model, 'created_at', None)
            updated_col = getattr(model, 'updated_at', created_col)
            if status_col is None:
                continue
            counts = Counter()
            try:
                rows = self.db.query(status_col, func.count(model.id)).group_by(status_col).all()
                for status, count in rows:
                    normalized = str(status or '').lower()
                    counts[normalized] += int(count or 0)
                active = sum(count for status, count in counts.items() if status in active_statuses)
                failed_recent = 0
                if updated_col is not None:
                    failed_recent = int(
                        self.db.query(func.count(model.id))
                        .filter(func.lower(status_col).in_(list(failed_statuses)))
                        .filter(updated_col >= since)
                        .scalar()
                        or 0
                    )
                active_total += active
                failed_last_hour_total += failed_recent
                by_table[key] = {'status_counts': dict(counts), 'active': active, 'failed_last_hour': failed_recent}
            except Exception as exc:  # pragma: no cover - defensive runtime guard
                by_table[key] = {'error': exc.__class__.__name__}
        return {'active_total': active_total, 'failed_last_hour_total': failed_last_hour_total, 'by_table': by_table}

    def _table_estimates(self) -> dict[str, Any]:
        try:
            names = ', '.join(f"'{name}'" for name in self.WATCH_TABLES)
            sql = text(f"""
                SELECT relname, n_live_tup
                FROM pg_stat_user_tables
                WHERE relname IN ({names})
                ORDER BY relname
            """)
            rows = self.db.execute(sql).mappings().all()
            return {
                'source': 'pg_stat_user_tables',
                'items': [{'table': row['relname'], 'estimated_rows': int(row['n_live_tup'] or 0)} for row in rows],
            }
        except Exception as exc:  # pragma: no cover - non-postgres/test runtimes
            return {'source': 'unavailable', 'items': [], 'error_type': exc.__class__.__name__}

    def _table_growth_checks(self, estimates: dict[str, Any]) -> list[dict[str, Any]]:
        items = estimates.get('items') or []
        checks: list[dict[str, Any]] = []
        if not items:
            return [{
                'category': 'table_growth',
                'code': 'TABLE_ESTIMATES_UNAVAILABLE',
                'severity': 'WARNING',
                'ok': False,
                'message': 'Chưa đọc được pg_stat_user_tables để ước lượng kích thước bảng.',
                'action': 'Chạy báo cáo này trên PostgreSQL UAT/prod để có số row estimate.',
            }]
        thresholds = {
            'analytics_tracking_events': 5_000_000,
            'analytics_student_video_progress': 1_000_000,
            'analytics_student_session_progress': 1_000_000,
            'analytics_learning_behavior_snapshots': 500_000,
            'ai_questions': 1_500_000,
        }
        for item in items:
            table = item.get('table')
            rows = int(item.get('estimated_rows') or 0)
            threshold = thresholds.get(str(table), 250_000)
            over = rows > threshold
            checks.append({
                'category': 'table_growth',
                'code': f'TABLE_SIZE_{str(table).upper()}',
                'severity': 'WARNING' if over else 'INFO',
                'ok': not over,
                'table': table,
                'estimated_rows': rows,
                'target': f'<= {threshold}',
                'message': f'{table} ước lượng {rows} rows.',
                'action': 'Rà pagination/server-side filter và pg_stat_statements cho bảng này trước pilot rộng.' if over else '',
            })
        return checks

    def _limits_payload(self) -> dict[str, Any]:
        return {
            'db_pool_size': settings.db_pool_size,
            'db_max_overflow': settings.db_max_overflow,
            'db_statement_timeout_ms': settings.db_statement_timeout_ms,
            'analytics_dashboard_max_page_size': settings.analytics_dashboard_max_page_size,
            'analytics_post_ingest_recalculate_max_jobs_per_run': settings.analytics_post_ingest_recalculate_max_jobs_per_run,
            'analytics_backfill_max_active_jobs': settings.analytics_backfill_max_active_jobs,
            'bank_search_max_results': settings.bank_search_max_results,
            'openedx_connector_max_batch_size': settings.openedx_connector_max_batch_size,
            'celery_worker_prefetch_multiplier': settings.celery_worker_prefetch_multiplier,
            'celery_worker_max_tasks_per_child': settings.celery_worker_max_tasks_per_child,
            'celery_worker_max_memory_per_child_kb': settings.celery_worker_max_memory_per_child_kb,
            'celery_broker_visibility_timeout_seconds': settings.celery_broker_visibility_timeout_seconds,
            'celery_default_time_limit_seconds': settings.celery_default_time_limit_seconds,
            'academic_teacher_report_sync_export_max_teachers': settings.academic_teacher_report_sync_export_max_teachers,
            'academic_teacher_report_sync_export_max_students': settings.academic_teacher_report_sync_export_max_students,
        }

    def _sections_from_checks(self, checks: list[dict[str, Any]]) -> list[dict[str, Any]]:
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for check in checks:
            grouped[str(check.get('category') or 'other')].append(check)
        sections = []
        for category, rows in sorted(grouped.items()):
            blockers = sum(1 for row in rows if row.get('severity') == 'BLOCKER')
            warnings = sum(1 for row in rows if row.get('severity') == 'WARNING')
            status = 'BLOCKED' if blockers else ('WARNING' if warnings else 'OK')
            sections.append({
                'key': category,
                'title': self._category_title(category),
                'status': status,
                'blocker_count': blockers,
                'warning_count': warnings,
                'check_count': len(rows),
            })
        return sections

    def _category_title(self, category: str) -> str:
        return {
            'configuration': 'Giới hạn cấu hình',
            'index_contract': 'Index cho query trọng điểm',
            'queue_pressure': 'Áp lực hàng đợi worker',
            'table_growth': 'Tăng trưởng bảng dữ liệu',
        }.get(category, category)

    def _next_actions(self, checks: list[dict[str, Any]]) -> list[str]:
        actions = []
        for check in checks:
            action = str(check.get('action') or '').strip()
            if action and action not in actions:
                actions.append(action)
        if not actions:
            actions.append('Tiếp tục chạy UAT build gate và runtime verify sau mỗi lần deploy.')
            actions.append('Theo dõi /api/health/performance-readiness khi tăng số lớp/môn pilot.')
        return actions[:8]
