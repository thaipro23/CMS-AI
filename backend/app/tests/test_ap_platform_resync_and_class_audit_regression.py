from __future__ import annotations

import ast
import os
from pathlib import Path

os.environ.setdefault('DATABASE_URL', 'sqlite+pysqlite:///:memory:')

ROOT = Path(__file__).resolve().parents[3]


def text(path: str) -> str:
    return (ROOT / path).read_text(encoding='utf-8')


def function_source(path: str, function_name: str) -> str:
    source = text(path)
    tree = ast.parse(source)
    lines = source.splitlines()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == function_name:
            return '\n'.join(lines[node.lineno - 1: node.end_lineno])
    raise AssertionError(f'missing function {function_name} in {path}')


def test_bulk_and_scheduled_class_sync_success_audits_are_suppressed_but_manual_is_kept():
    source = function_source('backend/app/worker.py', '_should_log_academic_class_sync_success')
    namespace: dict[str, object] = {}
    exec(source, namespace)
    policy = namespace['_should_log_academic_class_sync_success']

    assert policy({}) is True
    assert policy({'approved_class_id': 'class-1'}) is True
    assert policy({'scheduled': True, 'approved_class_id': 'class-1'}) is False
    assert policy({'parent_job_id': 'bulk-parent', 'approved_class_id': 'class-1'}) is False
    assert policy({'parent_job_type': 'subject_auto_map_all_sync', 'approved_class_id': 'class-1'}) is False
    assert sum(bool(policy({'parent_job_id': 'bulk-parent', 'approved_class_id': f'class-{i}'})) for i in range(100)) == 0

    task = function_source('backend/app/worker.py', 'academic_class_sync_task')
    assert task.count('if _should_log_academic_class_sync_success(request_json):') >= 2
    assert "action='academic.class_sync.async'" in task
    assert "status='failed'" in task


def test_scheduled_score_parent_writes_one_summary_audit_instead_of_child_success_spam():
    source = function_source('backend/app/worker.py', 'academic_sync_all_student_scores_task')
    assert "action='academic.sync_all_student_scores'" in source
    assert "status='success'" in source
    assert "status='failed'" in source
    assert "metadata=json_safe_value(result)" in source


def test_ap_worker_uses_reconciliation_importer_and_clears_platform_resync_only_after_clean_success():
    source = function_source('backend/app/worker.py', 'academic_ap_sync_task')
    assert 'from app.services.academic.ap_importer import AcademicImportService' in source
    assert 'from app.services.ap_academic_sync import SyncCounters' in source
    assert 'AcademicSubjectDeliveryService(db).mark_ap_reconciled' in source
    assert "result_run.status == 'completed'" in source
    assert "not bool(request.get('dry_run'))" in source
    assert 'int(counters.errors or 0) == 0' in source


def test_udemy_to_cms_platform_change_sets_durable_ap_reconcile_marker_in_single_and_bulk_paths():
    single = function_source('backend/app/services/academic/subject_delivery.py', 'set_platform')
    bulk = function_source('backend/app/services/academic/subject_delivery.py', 'bulk_set_platform')
    marker = function_source('backend/app/services/academic/subject_delivery.py', '_mark_ap_reconcile_required')
    clear = function_source('backend/app/services/academic/subject_delivery.py', 'mark_ap_reconciled')

    assert '_mark_ap_reconcile_required' in single
    assert '_mark_ap_reconcile_required' in bulk
    assert "previous_platform == 'udemy'" in marker
    assert "next_platform == 'cms'" in marker
    assert "metadata['ap_reconcile_required'] = True" in marker
    assert "metadata['ap_reconcile_reason'] = 'learning_platform_changed_udemy_to_cms'" in marker
    assert "metadata['ap_reconcile_required'] = False" in clear
    assert "AcademicSubjectDelivery.learning_platform == 'cms'" in clear
