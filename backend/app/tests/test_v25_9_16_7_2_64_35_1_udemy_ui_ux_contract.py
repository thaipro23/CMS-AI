from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
FRONTEND = ROOT / "frontend"


def read(relative_path: str) -> str:
    return (FRONTEND / relative_path).read_text(encoding="utf-8")


def test_udemy_primary_actions_use_shared_button_contract() -> None:
    css = read("styles/subject-management-udemy.css")
    dashboard = read("app/subject-management/[deliveryId]/udemy/page.tsx")
    subject_management = read("app/subject-management/page.tsx")
    class_detail = read("app/student-management/classes/[classId]/page.tsx")

    assert ".udemy-action" not in css
    assert "udemy-action" not in dashboard
    assert "udemy-action" not in subject_management
    assert "udemy-action" not in class_detail
    assert 'className="btn"' in dashboard
    assert "'Import điểm Udemy'" in dashboard


def test_alert_tab_cannot_keep_on_track_filter() -> None:
    dashboard = read("app/subject-management/[deliveryId]/udemy/page.tsx")

    assert "status === 'all' || status === 'on_track' ? 'alerts' : status" in dashboard
    assert "tab !== 'alerts' ? <option value=\"on_track\">Đạt tiến độ</option> : null" in dashboard
    assert "next === 'alerts' && status === 'on_track'" in dashboard


def test_udemy_jobs_are_persistent_and_recoverable() -> None:
    dashboard = read("app/subject-management/[deliveryId]/udemy/page.tsx")
    notice = read("components/ui/PersistentJobNotice.tsx")

    assert "ai-server:udemy-import-job:" in dashboard
    assert "ai-server:udemy-export-job:" in dashboard
    assert "getAcademicBulkOperationJob" in dashboard
    assert "setInterval" in dashboard
    assert "PersistentJobNotice" in dashboard
    assert "role={statusTone === 'error' ? 'alert' : 'status'}" in notice
    assert "<progress" in notice
    assert "exportRecoveryJobId" in dashboard
    assert "importRecoveryJobId" in dashboard
    queued_block = dashboard.split('onQueued={async (response) => {', 1)[1]
    assert "setImportOpen(false)" not in queued_block


def test_tabs_panels_and_progress_have_accessibility_semantics() -> None:
    dashboard = read("app/subject-management/[deliveryId]/udemy/page.tsx")
    workspace = read("components/operations/OperationsWorkspace.tsx")

    assert 'idPrefix="udemy-progress"' in dashboard
    assert 'role="tabpanel"' in dashboard
    assert "aria-labelledby=\"udemy-progress-tab-overview\"" in dashboard
    assert 'role="progressbar"' in dashboard
    assert "aria-valuenow" in dashboard
    assert "aria-controls={idPrefix ?" in workspace


def test_auxiliary_udemy_tables_use_enterprise_data_table() -> None:
    dashboard = read("app/subject-management/[deliveryId]/udemy/page.tsx")
    progress_dialog = read("components/subject-management/UdemyProgressImportDialog.tsx")
    plan_page = read("app/subject-management/[deliveryId]/udemy-plan/page.tsx")
    plan_dialog = read("components/subject-management/UdemyPlanImportDialog.tsx")

    assert 'tableId="udemy-import-history-batch35-1"' in dashboard
    assert "EnterpriseDataTable" in progress_dialog
    assert "EnterpriseDataTable" in plan_page
    assert plan_dialog.count("EnterpriseDataTable") >= 3
    assert "file tổng hợp ACMS" not in progress_dialog
    assert "file tổng hợp tiến độ 7 cột" in progress_dialog


def test_udemy_notices_use_shared_notice_components() -> None:
    dashboard = read("app/subject-management/[deliveryId]/udemy/page.tsx")
    subject_management = read("app/subject-management/page.tsx")
    class_detail = read("app/student-management/classes/[classId]/page.tsx")
    progress_dialog = read("components/subject-management/UdemyProgressImportDialog.tsx")
    plan_dialog = read("components/subject-management/UdemyPlanImportDialog.tsx")

    for source in (dashboard, subject_management, class_detail, progress_dialog, plan_dialog):
        assert "InlineNotice" in source
    assert "udemy-class-routing-notice" not in class_detail


def test_udemy_browser_contract_suite_covers_required_widths_and_job_resume() -> None:
    spec = (ROOT / "e2e/tests/udemy-ui-ux.spec.ts").read_text(encoding="utf-8")

    for width in (1440, 1366, 1024, 768, 390):
        assert f"width: {width}" in spec
    assert "jobs resume after reload" in spec
    assert "alert semantics" in spec
    assert "contrastRatio" in spec


def test_batch35_1_version_and_schema_contract() -> None:
    assert (ROOT / "RELEASE_v25.9.16.7.2.64.16.5.7.2.5_UDEMY_UI_UX_CONTRACT_BATCH35_1.md").exists()
    migrations = list((ROOT / "backend/alembic/versions").glob("0058*"))
    assert migrations == []
    assert (ROOT / "backend/alembic/versions/0057_v25_9_16_7_2_64_35_udemy_hardening_indexes.py").exists()
