from fastapi import APIRouter, Depends
from sqlalchemy import case, func, literal_column, or_
from sqlalchemy.orm import Session
from app.core.rbac import UserContext, ensure_course_access, require_permission, restrict_query_to_courses
from app.db.session import get_db
from app.models.cost import BudgetPolicy, UsageLog
from app.models.course import ContentChunk, CourseSyncState
from app.models.job import GenerationJob
from app.models.question import Question, QuestionReviewLog
from app.services.cost_control import USD_TO_VND

router = APIRouter()


def _count_map(query, key_column, count_column) -> dict[str, int]:
    rows = query.with_entities(key_column, func.count(count_column)).group_by(key_column).all()
    return {str(key or 'unknown'): int(count or 0) for key, count in rows}


def _sum(value) -> float:
    return float(value or 0)


@router.get('/overview')
def overview(course_id: str | None = None, db: Session = Depends(get_db), user: UserContext = Depends(require_permission('view_dashboard'))):
    ensure_course_access(user, course_id)
    q_query = restrict_query_to_courses(db.query(Question), Question, user)
    j_query = restrict_query_to_courses(db.query(GenerationJob), GenerationJob, user)
    u_query = restrict_query_to_courses(db.query(UsageLog), UsageLog, user)
    chunk_query = restrict_query_to_courses(db.query(ContentChunk), ContentChunk, user)
    sync_query = restrict_query_to_courses(db.query(CourseSyncState), CourseSyncState, user)
    review_query = db.query(QuestionReviewLog)
    if course_id:
        q_query = q_query.filter(Question.course_id == course_id)
        j_query = j_query.filter(GenerationJob.course_id == course_id)
        u_query = u_query.filter(UsageLog.course_id == course_id)
        chunk_query = chunk_query.filter(ContentChunk.course_id == course_id)
        sync_query = sync_query.filter(CourseSyncState.course_id == course_id)
        review_query = review_query.join(Question, QuestionReviewLog.question_id == Question.id).filter(Question.course_id == course_id)

    # Production scale: keep dashboard aggregation in SQL. The previous version
    # loaded all questions/jobs/usage/chunks into Python, which becomes slow and
    # memory-heavy on large courses.
    by_status = _count_map(q_query, Question.status, Question.id)
    by_difficulty = _count_map(q_query, Question.difficulty, Question.id)
    by_cognitive_level = _count_map(q_query, Question.cognitive_level, Question.id)
    # PostgreSQL requires the SELECT and GROUP BY expressions to be identical.
    # Building func.coalesce(..., 'unknown') twice makes SQLAlchemy generate two
    # different bind parameters, which PostgreSQL treats as different
    # expressions and raises GroupingError. Use a literal SQL constant and reuse
    # the same expression object.
    unknown_topic = literal_column("'unknown'")
    topic_scope = func.coalesce(Question.topic, unknown_topic).label('scope')
    topic_count = func.count(Question.id).label('count')
    top_scope_rows = (
        q_query.with_entities(topic_scope, topic_count)
        .group_by(topic_scope)
        .order_by(topic_count.desc())
        .limit(10)
        .all()
    )
    top_scopes = [{'scope': str(scope or 'unknown'), 'count': int(count or 0)} for scope, count in top_scope_rows]
    job_by_status = _count_map(j_query, GenerationJob.status, GenerationJob.id)

    q_total, duplicate_count, quality_average = q_query.with_entities(
        func.count(Question.id),
        func.coalesce(func.sum(case((Question.is_duplicate == True, 1), else_=0)), 0),
        func.coalesce(func.avg(Question.quality_score), 0),
    ).one()
    q_total = int(q_total or 0)
    duplicate_count = int(duplicate_count or 0)
    quality_average = float(quality_average or 0)

    job_totals = j_query.with_entities(
        func.count(GenerationJob.id),
        func.coalesce(func.sum(GenerationJob.estimated_cost_usd), 0),
        func.coalesce(func.sum(GenerationJob.estimated_raw_cost_usd), 0),
        func.coalesce(func.sum(GenerationJob.actual_cost_usd), 0),
        func.coalesce(func.sum(GenerationJob.estimated_input_tokens), 0),
        func.coalesce(func.sum(GenerationJob.estimated_output_tokens), 0),
        func.coalesce(func.sum(GenerationJob.actual_input_tokens), 0),
        func.coalesce(func.sum(GenerationJob.actual_cached_input_tokens), 0),
        func.coalesce(func.sum(GenerationJob.actual_output_tokens), 0),
        func.coalesce(func.sum(GenerationJob.completed_question_count), 0),
        func.coalesce(func.sum(GenerationJob.question_count), 0),
        func.coalesce(func.sum(GenerationJob.retry_count), 0),
    ).one()
    (
        total_jobs,
        total_estimated_cost_usd,
        total_estimated_raw_cost_usd,
        total_actual_job_cost_usd,
        total_estimated_input_tokens,
        total_estimated_output_tokens,
        total_actual_input_tokens,
        total_actual_cached_input_tokens,
        total_actual_output_tokens,
        total_completed_questions,
        total_requested_questions,
        retry_total,
    ) = job_totals

    reconciled_query = j_query.filter(
        GenerationJob.status == 'completed',
        or_(GenerationJob.actual_input_tokens > 0, GenerationJob.actual_output_tokens > 0, GenerationJob.actual_cost_usd > 0),
    )
    avg_estimate_accuracy, avg_output_accuracy = reconciled_query.with_entities(
        func.coalesce(func.avg(GenerationJob.estimate_accuracy_percent), 0),
        func.coalesce(func.avg(GenerationJob.output_accuracy_percent), 0),
    ).one()

    cost_rows = u_query.with_entities(
        UsageLog.feature,
        func.coalesce(func.sum(UsageLog.cost_usd), 0),
    ).group_by(UsageLog.feature).all()
    cost_by_feature = {str(feature or 'unknown'): float(cost or 0) for feature, cost in cost_rows}
    model_rows = u_query.with_entities(
        UsageLog.model_provider,
        UsageLog.model_name,
        func.coalesce(func.sum(UsageLog.cost_usd), 0),
    ).group_by(UsageLog.model_provider, UsageLog.model_name).all()
    cost_by_model = {f'{provider or "unknown"}/{model or "unknown"}': float(cost or 0) for provider, model, cost in model_rows}
    usage_totals = u_query.with_entities(
        func.coalesce(func.sum(UsageLog.cost_usd), 0),
        func.coalesce(func.sum(UsageLog.input_tokens), 0),
        func.coalesce(func.sum(UsageLog.cached_input_tokens), 0),
        func.coalesce(func.sum(UsageLog.output_tokens), 0),
    ).one()
    total_cost_usd, usage_input_tokens, usage_cached_input_tokens, usage_output_tokens = usage_totals

    approved = int(by_status.get('approved', 0)) + int(by_status.get('published', 0))
    reviewed = approved + int(by_status.get('rejected', 0))
    approve_rate = round(approved / reviewed * 100, 2) if reviewed else 0
    failed_jobs = int(job_by_status.get('failed', 0))

    policy = None
    if course_id:
        policy = db.query(BudgetPolicy).filter(BudgetPolicy.scope == 'course', BudgetPolicy.scope_id == course_id, BudgetPolicy.is_active == True).first()
    monthly_budget = policy.monthly_budget_usd if policy else 10.0
    max_questions = policy.max_questions_per_course if policy else 200
    budget_used_percent = round((_sum(total_cost_usd) / monthly_budget) * 100, 2) if monthly_budget else 0
    quota_used_percent = round((q_total / max_questions) * 100, 2) if max_questions else 0

    sync_nodes = sync_query.count()
    content_hash_rows = sync_query.filter(CourseSyncState.content_hash != None).count()
    chunk_count, tokens_indexed = chunk_query.with_entities(
        func.count(ContentChunk.id),
        func.coalesce(func.sum(ContentChunk.token_count), 0),
    ).one()
    chunk_source_rows = chunk_query.with_entities(ContentChunk.source_type, func.count(ContentChunk.id)).group_by(ContentChunk.source_type).all()

    return {
        'course_id': course_id,
        'questions': {
            'total': q_total,
            'by_status': by_status,
            'by_difficulty': by_difficulty,
            'by_cognitive_level': by_cognitive_level,
            'top_scopes': top_scopes,
            'approve_rate_percent': approve_rate,
            'duplicate_count': duplicate_count,
            'quality_average': round(quality_average, 2),
            'openedx': {
                'verified': int(q_query.filter(Question.openedx_verification_status == 'verified').count()),
                'pending': int(q_query.filter(Question.openedx_verification_status == 'pending').count()),
                'manual_action_required': int(q_query.filter(Question.openedx_manual_action_required == True).count()),
                'delete_failed_or_manual': int(q_query.filter(Question.openedx_delete_status.in_(['manual_delete_required', 'failed'])).count()),
            },
        },
        'jobs': {
            'total': int(total_jobs or 0),
            'by_status': job_by_status,
            'retry_total': int(retry_total or 0),
            'failed_jobs': failed_jobs,
            'estimated_cost_usd': round(_sum(total_estimated_cost_usd), 6),
            'estimated_raw_cost_usd': round(_sum(total_estimated_raw_cost_usd), 6),
            'actual_job_cost_usd': round(_sum(total_actual_job_cost_usd), 6),
            'estimate_accuracy_percent': round(float(avg_estimate_accuracy or 0), 2),
            'output_accuracy_percent': round(float(avg_output_accuracy or 0), 2),
            'estimated_output_tokens_per_question': round(int(total_estimated_output_tokens or 0) / int(total_requested_questions or 1), 2) if int(total_requested_questions or 0) else 0,
            'actual_output_tokens_per_question': round(int(total_actual_output_tokens or 0) / int(total_completed_questions or 1), 2) if int(total_completed_questions or 0) else 0,
            'output_delta_tokens': int(total_actual_output_tokens or 0) - int(total_estimated_output_tokens or 0),
            'cost_delta_usd': round(_sum(total_actual_job_cost_usd) - _sum(total_estimated_raw_cost_usd), 6),
            'estimated_input_tokens': int(total_estimated_input_tokens or 0),
            'estimated_output_tokens': int(total_estimated_output_tokens or 0),
            'actual_input_tokens': int(total_actual_input_tokens or 0),
            'actual_cached_input_tokens': int(total_actual_cached_input_tokens or 0),
            'actual_output_tokens': int(total_actual_output_tokens or 0),
        },
        'cost': {
            'total_usage_cost_usd': round(_sum(total_cost_usd), 6),
            'total_usage_cost_vnd': round(_sum(total_cost_usd) * USD_TO_VND, 0),
            'monthly_budget_usd': monthly_budget,
            'budget_used_percent': budget_used_percent,
            'by_feature': {k: round(v, 6) for k, v in cost_by_feature.items()},
            'by_model': {k: round(v, 6) for k, v in cost_by_model.items()},
            'actual_input_tokens': int(usage_input_tokens or 0),
            'actual_cached_input_tokens': int(usage_cached_input_tokens or 0),
            'actual_uncached_input_tokens': max(int(usage_input_tokens or 0) - int(usage_cached_input_tokens or 0), 0),
            'actual_output_tokens': int(usage_output_tokens or 0),
        },
        'course_sync': {
            'nodes': sync_nodes,
            'chunks': int(chunk_count or 0),
            'content_hash_rows': content_hash_rows,
            'tokens_indexed': int(tokens_indexed or 0),
            'by_source_type': {str(source or 'unknown'): int(count or 0) for source, count in chunk_source_rows},
        },
        'governance': {
            'quota_max_questions_per_course': max_questions,
            'quota_used_percent': quota_used_percent,
            'hard_stop_enabled': True,
            'review_log_count': review_query.count(),
        },
    }
