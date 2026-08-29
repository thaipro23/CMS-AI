from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.core.rbac import UserContext, ensure_course_access, require_permission, restrict_query_to_courses
from app.models.job import GenerationJob
from app.models.generation_batch import GenerationBatch

router = APIRouter()


@router.get('')
def list_jobs(course_id: str | None = None, db: Session = Depends(get_db), user: UserContext = Depends(require_permission('view_jobs'))):
    ensure_course_access(user, course_id)
    query = restrict_query_to_courses(db.query(GenerationJob), GenerationJob, user)
    if course_id:
        query = query.filter(GenerationJob.course_id == course_id)
    jobs = query.order_by(GenerationJob.created_at.desc()).limit(100).all()
    job_ids = [j.id for j in jobs]
    batch_summaries = {job_id: {'total': 0, 'queued': 0, 'running': 0, 'completed': 0, 'partial': 0, 'failed': 0, 'tail': 0} for job_id in job_ids}
    if job_ids:
        batch_counts = (
            db.query(GenerationBatch.job_id, GenerationBatch.status, GenerationBatch.phase, func.count(GenerationBatch.id))
            .filter(GenerationBatch.job_id.in_(job_ids))
            .group_by(GenerationBatch.job_id, GenerationBatch.status, GenerationBatch.phase)
            .all()
        )
        for job_id, status, phase, count in batch_counts:
            summary = batch_summaries.setdefault(job_id, {'total': 0, 'queued': 0, 'running': 0, 'completed': 0, 'partial': 0, 'failed': 0, 'tail': 0})
            count = int(count or 0)
            summary['total'] += count
            if status == 'queued':
                summary['queued'] += count
            if status == 'running':
                summary['running'] += count
            if status in {'completed', 'cache_hit'}:
                summary['completed'] += count
            if status == 'partial_completed':
                summary['partial'] += count
            if status in {'failed', 'parse_failed'}:
                summary['failed'] += count
            if phase == 'tail':
                summary['tail'] += count
    rows = []
    for j in jobs:
        estimated_raw = j.estimated_raw_cost_usd or 0
        actual = j.actual_cost_usd or 0
        cost_delta = actual - estimated_raw
        input_accuracy = 0.0
        if (j.actual_input_tokens or 0) > 0 and (j.estimated_input_tokens or 0) > 0:
            input_accuracy = max(0.0, 100.0 - abs((j.actual_input_tokens or 0) - (j.estimated_input_tokens or 0)) / max((j.actual_input_tokens or 0), 1) * 100.0)
        elif (j.actual_input_tokens or 0) == 0 and (j.estimated_input_tokens or 0) == 0:
            input_accuracy = 100.0
        actual_output_per_question = j.actual_output_tokens_per_question or (round((j.actual_output_tokens or 0) / max((j.completed_question_count or 0), 1), 2) if (j.completed_question_count or 0) else 0)
        estimated_output_per_question = j.estimated_output_tokens_per_question or (round((j.estimated_output_tokens or 0) / max((j.question_count or 0), 1), 2) if (j.question_count or 0) else 0)
        batch_summary = batch_summaries.get(j.id, {'total': 0, 'queued': 0, 'running': 0, 'completed': 0, 'partial': 0, 'failed': 0, 'tail': 0})
        rows.append({
            'id': j.id,
            'course_id': j.course_id,
            'question_count': j.question_count,
            'status': j.status,
            'estimated_input_tokens': j.estimated_input_tokens or 0,
            'estimated_cached_input_tokens': j.estimated_cached_input_tokens or 0,
            'estimated_uncached_input_tokens': j.estimated_uncached_input_tokens or 0,
            'estimated_output_tokens': j.estimated_output_tokens or 0,
            'estimated_raw_cost_usd': round(estimated_raw, 6),
            'estimated_cost_usd': round(j.estimated_cost_usd or 0, 6),
            'estimated_cost_vnd': round(j.estimated_cost_vnd or 0, 0),
            'estimate_token_source': j.estimate_token_source,
            'estimated_output_tokens_per_question': round(estimated_output_per_question or 0, 2),
            'output_calibration': j.output_calibration_json,
            'actual_input_tokens': j.actual_input_tokens or 0,
            'actual_cached_input_tokens': j.actual_cached_input_tokens or 0,
            'actual_uncached_input_tokens': j.actual_uncached_input_tokens or 0,
            'actual_output_tokens': j.actual_output_tokens or 0,
            'actual_cost_usd': round(actual, 6),
            'actual_cost_vnd': round(j.actual_cost_vnd or 0, 0),
            'usage_token_source': j.usage_token_source,
            'estimate_accuracy_percent': round(j.estimate_accuracy_percent or 0, 2),
            'input_accuracy_percent': round(input_accuracy, 2),
            'output_accuracy_percent': round(j.output_accuracy_percent or 0, 2),
            'actual_output_tokens_per_question': round(actual_output_per_question or 0, 2),
            'output_delta_tokens': j.output_delta_tokens or ((j.actual_output_tokens or 0) - (j.estimated_output_tokens or 0)),
            'cost_delta_usd': round(cost_delta, 6),
            'completed_question_count': j.completed_question_count or 0,
            'openai_response_ids': j.openai_response_ids,
            'model_parse_error': j.model_parse_error,
            'error_message': j.error_message,
            'created_at': j.created_at,
            'batch_summary': batch_summary,
        })
    return rows



@router.get('/{job_id}/batches')
def list_job_batches(job_id: str, db: Session = Depends(get_db), user: UserContext = Depends(require_permission('view_jobs'))):
    job = db.get(GenerationJob, job_id)
    if not job:
        return []
    ensure_course_access(user, job.course_id)
    rows = db.query(GenerationBatch).filter(GenerationBatch.job_id == job_id).order_by(GenerationBatch.batch_index.asc(), GenerationBatch.created_at.asc()).all()
    return [{
        'id': b.id,
        'job_id': b.job_id,
        'batch_index': b.batch_index,
        'phase': b.phase,
        'difficulty': b.difficulty,
        'difficulty_counts': b.difficulty_counts_json,
        'requested_questions': b.requested_questions,
        'completed_questions': b.completed_questions,
        'status': b.status,
        'actual_input_tokens': b.actual_input_tokens,
        'actual_cached_input_tokens': b.actual_cached_input_tokens,
        'actual_output_tokens': b.actual_output_tokens,
        'actual_cost_usd': round(b.actual_cost_usd or 0, 6),
        'token_source': b.token_source,
        'openai_response_id': b.openai_response_id,
        'prompt_cache_key': b.prompt_cache_key,
        'error_message': b.error_message,
        'started_at': b.started_at,
        'finished_at': b.finished_at,
    } for b in rows]
