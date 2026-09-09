from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding='utf-8')


def test_ptcd_subject_overview_does_not_hydrate_snapshot_raw_json():
    source = read('backend/app/services/academic_subject_overview_performance.py')
    fast = source.split('def _learning_summary_by_class_ids_fast', 1)[1].split('def _inherited_course_mappings_for_classes_fast', 1)[0]
    assert 'AcademicStudentLearningSnapshot.raw_json' not in fast
    assert 'AcademicStudentLearningSnapshot.progress_percent' in fast
    assert 'AcademicStudentLearningSnapshot.grade_percent' in fast
    assert '_OVERVIEW_MODE' in source


def test_inherited_mapping_lookup_is_bucketed_by_term_and_subject():
    source = read('backend/app/services/academic_subject_overview_performance.py')
    assert "by_scope.setdefault((str(mapping.term_id), str(mapping.subject_id)), []).append(mapping)" in source
    assert "candidates = by_scope.get((str(cls.term_id), str(cls.subject_id)), [])" in source


def test_bank_quiz_preview_prefers_saved_course_mapping_before_live_tree():
    source = read('backend/app/services/bank_quiz_saved_mapping_fastpath.py')
    assert 'EdxCourseChapterMapping.course_mapping_id == mapping.id' in source
    assert "'cache_kind': 'saved_course_mapping'" in source
    assert '_bank_quiz_force_live_tree' in source
    assert 'return await _ORIGINAL_LOAD(self, canonical)' in source


def test_runtime_installs_both_performance_hotfixes_after_existing_bank_patch():
    source = read('backend/app/main.py')
    first = source.index('apply_bank_quiz_performance_patches()')
    saved = source.index('apply_bank_quiz_saved_mapping_fastpath()')
    academic = source.index('apply_academic_subject_overview_performance_patches()')
    assert first < saved < academic
