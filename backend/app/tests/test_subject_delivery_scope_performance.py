from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def test_subject_delivery_aggregates_are_scoped_before_grouping():
    source = (ROOT / 'backend/app/services/academic/subject_delivery.py').read_text(encoding='utf-8')

    assert 'class_counts_query = (' in source
    assert 'class_counts_query = class_counts_query.filter(AcademicClass.term_id == term_id)' in source
    assert 'class_counts_query = class_counts_query.filter(class_branch_key == branch_value)' in source

    assert 'active_plan_query = (' in source
    assert 'active_plan_query = active_plan_query.filter(AcademicSubjectDelivery.term_id == term_id)' in source
    assert 'active_plan_query = active_plan_query.filter(func.lower(AcademicSubjectDelivery.branch) == branch_value)' in source

    assert 'progress_stats_query = (' in source
    assert 'progress_stats_query = progress_stats_query.filter(AcademicSubjectDelivery.term_id == term_id)' in source
    assert 'progress_stats_query = progress_stats_query.filter(func.lower(AcademicSubjectDelivery.branch) == branch_value)' in source

    assert '.join(active_plan, active_plan.c.plan_id == UdemySubjectPlanMilestone.plan_id)' in source
