#!/usr/bin/env bash
set -Eeuo pipefail
ROOT_DIR="${ROOT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
cd "$ROOT_DIR/backend"
pytest -q \
  app/tests/test_academic_auto_map_invalid_org_repair.py \
  app/tests/test_academic_branch_course_mapping.py \
  app/tests/test_academic_daily_pipeline_ap_mapping.py \
  app/tests/test_academic_daily_pipeline_provision_score.py \
  app/tests/test_academic_daily_pipeline_recovery.py \
  app/tests/test_daily_teacher_report_pipeline_contract.py \
  app/tests/test_daily_teacher_report_watchdog.py \
  app/tests/test_learning_sync_preserves_confirmed_enrollment.py \
  app/tests/test_primary_after_enrollment_policy.py \
  app/tests/test_primary_after_enrollment_connector_client.py \
  app/tests/test_official_course_completion.py \
  app/tests/test_assignment_ui_suppression.py \
  app/tests/test_assessment_average_grade.py \
  app/tests/test_teacher_cms_list_performance.py \
  app/tests/test_teacher_management_all_cms_regression.py \
  app/tests/test_v25_9_16_7_2_64_34_udemy_dashboard_export.py \
  app/tests/test_email_privacy_contract.py \
  app/tests/test_academic_progress_email.py \
  app/tests/test_v25_9_16_7_2_64_16_5_4_production_security_closure.py \
  app/tests/test_v25_9_16_7_2_64_16_5_5_performance_worker_reliability.py \
  app/tests/test_v25_9_16_7_2_64_16_5_7_release_contract.py \
  app/tests/test_quiz_tracking_log_integrity.py \
  app/tests/test_quiz_item_materialization.py \
  app/tests/test_quiz_integrity_rules.py \
  app/tests/test_quiz_integrity_access.py \
  app/tests/test_quiz_tracking_integration.py \
  app/tests/test_quiz_worker_batching.py \
  app/tests/test_quiz_release_readiness.py
pytest -q app/tests/test_v25_9_16_7_2_64_16_5_6_release_contract.py -k 'not version_is_synchronized_across_runtime_artifacts'
pytest -q -m integration app/tests/integration
