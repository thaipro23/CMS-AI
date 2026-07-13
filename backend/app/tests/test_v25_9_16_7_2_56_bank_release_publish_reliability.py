from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
VERSION = '25.9.16.7.2.64.13'


def text(path: str) -> str:
    return (ROOT / path).read_text()


def test_version_synced_to_56():
    assert f"app_version: str = '{VERSION}'" in text('backend/app/core/config.py')
    assert f'"version": "{VERSION}"' in text('frontend/package.json')
    assert f'NEXT_PUBLIC_APP_VERSION: ${{APP_VERSION:-{VERSION}}}' in text('docker-compose.prod.yml')
    assert VERSION in text('frontend/Dockerfile')
    assert VERSION in text('frontend/package-lock.json')


def test_bank_release_publish_audit_backend_contract_is_read_only():
    service = text('backend/app/services/question_bank_service.py') + text('backend/app/services/question_bank/release_publish.py')
    route = text('backend/app/api/routes/question_bank_v2.py')
    assert 'def release_publish_audit(self, *, release_id: str) -> dict:' in service
    assert "'read_only': True" in service
    assert "'mutation_performed': False" in service
    assert "'raw_tracking_log_scanned': False" in service
    assert "@router.get('/releases/{release_id}/publish-audit')" in route
    assert 'do not write audit rows' in route


def test_bank_release_publish_audit_covers_publish_and_rollback_risks():
    service = text('backend/app/services/question_bank_service.py') + text('backend/app/services/question_bank/release_publish.py')
    required_codes = [
        'release_components_complete',
        'duplicate_library_problem_ids',
        'question_library_mismatch',
        'course_quiz_instances_present',
        'rollback_manual_required',
        'failed_quiz_instances',
    ]
    for code in required_codes:
        assert code in service
    assert 'PUBLISHED_VERIFIED' in service
    assert 'READY_TO_PUBLISH' in service
    assert 'READY_WITH_WARNINGS' in service
    assert 'BLOCKED' in service


def test_chapter_workspace_surfaces_release_audit_panel():
    page = text('frontend/app/bank/_components/pages/ChapterWorkspacePage.tsx')
    api = text('frontend/lib/api.ts')
    types = text('frontend/types/index.ts')
    assert 'getBankReleasePublishAudit' in api
    assert 'BankReleasePublishAudit' in types
    assert 'QA publish/rollback' in page
    assert 'Độ tin cậy bộ đề' in page
    assert 'Kiểm tra bộ đề' in page
    assert 'bank-release-audit-panel' in page


def test_release_audit_export_script_exists_and_is_safe():
    script = text('scripts/bank-release-publish-audit-report.sh')
    assert '/question-bank-v2/releases/$RELEASE_ID/publish-audit' in script
    assert 'BANK_RELEASE_PUBLISH_AUDIT_SUMMARY.md' in script
    assert 'curl -fsS' in script
    banned = ['rm' + ' -rf', 'docker compose down' + ' -v', 'DROP' + ' TABLE', 'DELETE' + ' FROM']
    for item in banned:
        assert item not in script
