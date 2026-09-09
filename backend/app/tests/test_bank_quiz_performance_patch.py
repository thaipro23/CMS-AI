from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
PATCH = ROOT / 'backend/app/services/bank_quiz_performance.py'
MAIN = ROOT / 'backend/app/main.py'


def test_bank_quiz_version_readiness_is_batched():
    source = PATCH.read_text(encoding='utf-8')
    assert 'SubjectChapter.subject_offering_id.in_(offering_ids)' in source
    assert 'QuestionBankRelease.chapter_id.in_(chapter_ids)' in source
    assert 'BankReleaseQuestion.bank_release_id.in_(release_ids)' in source
    assert '.group_by(BankReleaseQuestion.bank_release_id)' in source
    assert '_bank_quiz_offering_status_cache' in source


def test_preview_uses_synced_course_tree_and_apply_forces_live_verification():
    source = PATCH.read_text(encoding='utf-8')
    assert "self.db.query(CourseSyncState)" in source
    assert "'source': 'cached'" in source
    assert "_bank_quiz_force_live_tree" in source
    assert 'return await _ORIGINAL_LOAD_COURSE_TREE(self, course_id)' in source
    assert '_ORIGINAL_APPLY_AUTO_MAP(self, *args, **kwargs)' in source


def test_runtime_installs_bank_quiz_performance_patch():
    source = MAIN.read_text(encoding='utf-8')
    assert 'from app.services.bank_quiz_performance import apply_bank_quiz_performance_patches' in source
    assert 'apply_bank_quiz_performance_patches()' in source
