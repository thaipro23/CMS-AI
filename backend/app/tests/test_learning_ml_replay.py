"""Exercise the offline evaluator with exports, never a production connection."""
import copy
import importlib.util
from pathlib import Path


def evaluator():
    path=Path(__file__).resolve().parents[3]/'scripts/evaluate-learning-ml.py'
    assert path.exists(), 'Missing offline ML evaluator'
    spec=importlib.util.spec_from_file_location('learning_ml_replay',path)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def audit():
    return {'class': {'id':'class'}, 'course_id':'course', 'generated_at_utc':'2026-10-09T08:00:00Z',
        'roster':[{'id':'s1','username':'u1','student_code':'S1'}], 'tables': {
            'academic_student_learning_snapshots': {'rows':[{'grade_percent':80, 'raw_json':{'official': True}}]},
            'analytics_quiz_attempts': {'rows':[{'id':'a','username':'u1','course_id':'course','unit_usage_key':'quiz',
                'started_at':'2026-10-09T07:40:00Z','ended_at':'2026-10-09T08:00:00Z',
                'unit_reset_nonce':'quiz-session:1','evidence_json':{'start_observed':True,
                'session_event_provenance':'server_quiz_session_v1','server_submission_times':[]}}]},
            'analytics_quiz_item_submissions': {'rows':[{'attempt_id':'a','username':'u1','course_id':'course',
                'submitted_at':'2026-10-09T07:45:00Z','problem_usage_key':'p','input_slot':'_1_1','question_hash':'a'*64}]}}}


def test_legacy_metadata_is_not_invented_and_official_grades_stay_identical():
    data=audit(); original=copy.deepcopy(data)
    report=evaluator().evaluate_audits([data])
    assert data==original
    assert report['eligibility_counts']['quiz']==0
    assert report['scored_groups']==0
    assert report['official_hash_before_after']['before']==report['official_hash_before_after']['after']
    assert report['skipped_by_reason']['quiz']['MISSING_CONTENT_VERSION']==1
    assert 'u1' not in str(report) and 'grade_percent' not in str(report)


def test_missing_raw_context_and_video_duration_never_become_normal():
    report=evaluator().evaluate_audits([audit()])
    assert report['eligibility_counts']['video']==0
    assert report['skipped_by_reason']['video']['MISSING_SESSION_MAPPING']==1
    assert report['accuracy']['status']=='UNMEASURED_NO_LABELS'
    assert report['rule_ml_disagreement']['compared']==0


def test_inconsistent_course_scope_is_excluded():
    data=audit(); data['tables']['analytics_quiz_attempts']['rows'][0]['course_id']='other'
    report=evaluator().evaluate_audits([data])
    assert report['eligibility_counts']['quiz']==0
    assert report['source_quality']['out_of_scope_rows']>=1


def test_duplicate_exports_do_not_increase_students_or_references():
    data=audit(); report=evaluator().evaluate_audits([data,copy.deepcopy(data)])
    assert report['roster_students']==1
    assert report['duplicate_student_checks']['duplicate_exports']==1


def test_truncated_feature_source_is_not_silently_scored():
    data=audit();data['tables']['analytics_quiz_item_submissions']['truncated']=True
    report=evaluator().evaluate_audits([data])
    assert report['skipped_by_reason']['quiz']['TRUNCATED_SOURCE']==1


def test_cli_refuses_to_overwrite_its_input_export(tmp_path):
    import json
    import subprocess
    import sys
    source=tmp_path/'learning.json'; source.write_text(json.dumps(audit()))
    before=source.read_bytes()
    result=subprocess.run([sys.executable,str(Path(__file__).resolve().parents[3]/'scripts/evaluate-learning-ml.py'),
        '--audit',str(source),'--output',str(source)],capture_output=True)
    assert result.returncode != 0
    assert source.read_bytes()==before
