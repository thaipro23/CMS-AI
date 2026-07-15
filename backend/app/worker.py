import asyncio
import json
from datetime import datetime
from collections import defaultdict
from celery import Celery
from sqlalchemy import text
from app.core.config import settings
from app.db.session import SessionLocal
from app.core.json_safe import json_safe_value
from app.core.rbac import UserContext
from app.models.job import GenerationJob
from app.models.generation_batch import GenerationBatch
from app.models.course import ContentChunk
from app.services.model_gateway import ModelGateway, ModelResponseParseError
from app.services.question_service import QuestionService
from app.services.cost_control import CostControlService
from app.services.runtime_settings import apply_runtime_settings
from app.algorithms.node_coverage import create_batches
from app.services.generation_cache import GenerationCacheService, build_generation_cache_key, build_prompt_cache_key, sha256_text
from app.services.token_calibration import OutputTokenCalibrationService
from app.services.audit_log import AuditErrorType, log_audit

apply_runtime_settings()
celery_app = Celery('ai_openedx_worker', broker=settings.redis_url, backend=settings.redis_url)
celery_app.conf.update(
    broker_connection_retry_on_startup=True,
    broker_transport_options={
        'visibility_timeout': int(settings.celery_broker_visibility_timeout_seconds),
        'socket_timeout': 10,
        'socket_connect_timeout': 10,
        'retry_on_timeout': True,
    },
    result_expires=int(settings.celery_result_expires_seconds),
    result_backend_transport_options={'retry_policy': {'timeout': 5.0}},
    task_serializer='json',
    result_serializer='json',
    accept_content=['json'],
    timezone='UTC',
    enable_utc=True,
    task_track_started=True,
    task_acks_late=bool(settings.celery_task_acks_late),
    task_reject_on_worker_lost=bool(settings.celery_task_reject_on_worker_lost),
    worker_cancel_long_running_tasks_on_connection_loss=True,
    worker_prefetch_multiplier=int(settings.celery_worker_prefetch_multiplier),
    worker_max_tasks_per_child=int(settings.celery_worker_max_tasks_per_child),
    worker_max_memory_per_child=int(settings.celery_worker_max_memory_per_child_kb),
    task_default_queue='interactive',
    task_create_missing_queues=True,
    task_routes={
        'generate_questions_task': {'queue': 'generation'},
        'bank_material_extract_task': {'queue': 'generation'},
        'bank_generate_questions_task': {'queue': 'generation'},
        'bank_question_import_task': {'queue': 'generation'},
        'bank_material_cleanup_task': {'queue': 'generation'},
        'bank_release_publish_task': {'queue': 'sync'},
        'bank_quiz_create_task': {'queue': 'sync'},
        'academic_ap_sync_task': {'queue': 'sync'},
        'academic_class_sync_task': {'queue': 'sync'},
        'academic_subject_auto_map_all_sync_task': {'queue': 'sync'},
        'academic_teacher_report_job_task': {'queue': 'exports'},
        'analytics_ingest_task': {'queue': 'analytics'},
        'analytics_class_recalculate_task': {'queue': 'analytics'},
    },
    task_annotations={
        'generate_questions_task': {'soft_time_limit': 3300, 'time_limit': 3600},
        'bank_material_extract_task': {'soft_time_limit': 3300, 'time_limit': 3600},
        'bank_generate_questions_task': {'soft_time_limit': 3300, 'time_limit': 3600},
        'bank_question_import_task': {'soft_time_limit': 1800, 'time_limit': 2100},
        'bank_material_cleanup_task': {'soft_time_limit': 900, 'time_limit': 1200},
        'bank_release_publish_task': {'soft_time_limit': 1500, 'time_limit': 1800},
        'bank_quiz_create_task': {'soft_time_limit': 1500, 'time_limit': 1800},
        'academic_ap_sync_task': {'soft_time_limit': 3300, 'time_limit': 3600},
        'academic_class_sync_task': {'soft_time_limit': 1500, 'time_limit': 1800},
        'academic_subject_auto_map_all_sync_task': {'soft_time_limit': 3300, 'time_limit': 3600},
        'academic_teacher_report_job_task': {'soft_time_limit': 1800, 'time_limit': 2100},
        'analytics_ingest_task': {'soft_time_limit': 540, 'time_limit': 600},
        'analytics_class_recalculate_task': {'soft_time_limit': 1500, 'time_limit': 1800},
    },
)
if getattr(settings, 'analytics_ingest_scheduler_enabled', False):
    celery_app.conf.beat_schedule = {
        **getattr(celery_app.conf, 'beat_schedule', {}),
        'analytics-ingest-openedx-tracking-log': {
            'task': 'analytics_ingest_task',
            'schedule': max(60, int(getattr(settings, 'analytics_ingest_interval_seconds', 60) or 60)),
            'args': (None, None),
        },
    }


@celery_app.task(name='generate_questions_task')
def generate_questions_task(job_id: str, content_override: str | None = None, work_items: list[dict] | None = None):
    return asyncio.run(_generate_questions(job_id, content_override, work_items or []))


def _append_usage(
    *,
    usage: dict,
    scope_title: str | None,
    question_count: int,
    difficulty: str | None,
    raw_usage_parts: list[dict],
    usage_sources: list[str],
    totals: dict[str, int],
    raw_output_text: str | None = None,
    parse_error: str | None = None,
) -> tuple[str, str]:
    totals['input'] += int(usage.get('input_tokens') or 0)
    totals['cached'] += int(usage.get('cached_input_tokens') or 0)
    totals['output'] += int(usage.get('output_tokens') or 0)
    if usage.get('token_source'):
        usage_sources.append(str(usage.get('token_source')))
    raw_usage_parts.append({
        'scope_title': scope_title,
        'difficulty': difficulty,
        'question_count': question_count,
        'token_source': usage.get('token_source'),
        'usage': usage,
        'response_id': usage.get('response_id'),
        'parse_error': parse_error,
        'raw_output_text_preview': (raw_output_text or usage.get('raw_output_text') or '')[:4000],
    })
    return str(usage.get('provider') or 'openai'), str(usage.get('model') or settings.openai_model)


async def _finalize_job_usage(
    db,
    job: GenerationJob,
    *,
    status: str,
    error_message: str | None,
    totals: dict[str, int],
    raw_usage_parts: list[dict],
    usage_sources: list[str],
    provider_used: str,
    model_used: str,
    questions_created: int,
    parse_error: str | None = None,
):
    db.rollback()
    actual_cost = 0.0
    token_source = '+'.join(sorted(set(usage_sources))) if usage_sources else None
    raw_usage_json = json.dumps(raw_usage_parts, ensure_ascii=False) if raw_usage_parts else None
    if totals['input'] or totals['output']:
        actual_cost, _pricing = await CostControlService(db).calculate_cost_usd(
            model_name=model_used,
            input_tokens=totals['input'],
            cached_input_tokens=totals['cached'],
            output_tokens=totals['output'],
            apply_safety_factor=False,
        )
        CostControlService(db).log_usage(
            job_id=job.id,
            course_id=job.course_id,
            user_id=job.requested_by,
            feature='generate_questions',
            model_provider=provider_used,
            model_name=model_used,
            input_tokens=totals['input'],
            cached_input_tokens=totals['cached'],
            output_tokens=totals['output'],
            cost_usd=actual_cost,
            token_source=token_source,
            raw_usage_json=raw_usage_json,
        )

    # Learn output tokens/question from real model calls. Do not learn from cache hits.
    calibrator = OutputTokenCalibrationService(db)
    for part in raw_usage_parts:
        usage = part.get('usage') or {}
        output_tokens = int((usage or {}).get('output_tokens') or 0)
        question_count = int(part.get('question_count') or 0)
        token_source_part = str(part.get('token_source') or '')
        if output_tokens > 0 and question_count > 0 and token_source_part != 'output_cache_hit':
            calibrator.update_from_observation(
                model_name=model_used,
                course_id=job.course_id,
                difficulty=part.get('difficulty'),
                question_count=question_count,
                output_tokens=output_tokens,
            )

    estimated_raw = float(job.estimated_raw_cost_usd or 0)
    accuracy = 0.0
    if actual_cost > 0 and estimated_raw > 0:
        accuracy = max(0.0, 100.0 - abs(actual_cost - estimated_raw) / actual_cost * 100.0)
    elif actual_cost == 0 and estimated_raw == 0:
        accuracy = 100.0

    actual_output_per_question = round((totals['output'] / questions_created), 2) if questions_created else 0.0
    estimated_output = int(job.estimated_output_tokens or 0)
    output_delta = int(totals['output'] - estimated_output)
    output_accuracy = 0.0
    if totals['output'] > 0 and estimated_output > 0:
        output_accuracy = max(0.0, 100.0 - abs(totals['output'] - estimated_output) / totals['output'] * 100.0)
    elif totals['output'] == 0 and estimated_output == 0:
        output_accuracy = 100.0

    job.status = status
    job.actual_input_tokens = totals['input']
    job.actual_cached_input_tokens = totals['cached']
    job.actual_uncached_input_tokens = max(totals['input'] - totals['cached'], 0)
    job.actual_output_tokens = totals['output']
    job.actual_output_tokens_per_question = actual_output_per_question
    job.output_delta_tokens = output_delta
    job.output_accuracy_percent = round(output_accuracy, 2)
    job.actual_cost_usd = actual_cost
    job.actual_cost_vnd = actual_cost * settings.usd_to_vnd
    job.usage_token_source = token_source
    job.estimate_accuracy_percent = round(accuracy, 2)
    job.completed_question_count = questions_created
    job.openai_response_ids = ','.join([str(p.get('response_id')) for p in raw_usage_parts if p.get('response_id')])[:4000]
    job.raw_model_output_text = '\n\n--- response ---\n\n'.join([str(p.get('raw_output_text_preview') or '') for p in raw_usage_parts if p.get('raw_output_text_preview')])[:12000] or None
    job.raw_model_usage_json = raw_usage_json
    job.model_parse_error = parse_error
    job.error_message = error_message
    job.updated_at = datetime.utcnow()
    db.add(job)
    db.commit()
    log_audit(
        db,
        action='generation.job.finish',
        status='success' if status == 'completed' else 'failed',
        error_type=None if status == 'completed' else (AuditErrorType.EXTERNAL_SERVICE_ERROR if parse_error else AuditErrorType.SYSTEM_ERROR),
        message=error_message or f'Hoàn tất job tạo câu hỏi với trạng thái {status}',
        course_id=job.course_id,
        target_type='generation_job',
        target_id=job.id,
        metadata={
            'requested_by': job.requested_by,
            'job_status': status,
            'question_count': job.question_count,
            'completed_question_count': questions_created,
            'actual_input_tokens': job.actual_input_tokens,
            'actual_cached_input_tokens': job.actual_cached_input_tokens,
            'actual_output_tokens': job.actual_output_tokens,
            'actual_cost_usd': job.actual_cost_usd,
            'token_source': token_source,
            'parse_error': parse_error,
        },
    )


def _difficulty_label(item: dict) -> str | None:
    counts = item.get('difficulty_counts') or {}
    if counts and len(counts) > 1:
        return 'mixed'
    return item.get('target_difficulty')


def _prepare_item(job: GenerationJob, item: dict, fallback_content: str, model_used: str, batch_index: int, phase_override: str | None = None) -> dict:
    count = int(item.get('question_count') or 0)
    item_content = str(item.get('content') or fallback_content or '')
    scope_title = item.get('scope_title') or job.topic
    target_difficulty = item.get('target_difficulty')
    difficulty_counts = {str(k).lower(): int(v) for k, v in (item.get('difficulty_counts') or {}).items() if int(v or 0) > 0}
    if not difficulty_counts and target_difficulty and target_difficulty not in {'mixed', 'mixed_tail'}:
        difficulty_counts = {str(target_difficulty).lower(): count}
    prompt_cache_key = item.get('prompt_cache_key') or build_prompt_cache_key(
        course_id=job.course_id,
        scope_title=scope_title,
        content=item_content,
        chunk_ids=item.get('chunk_ids') or [],
        node_id=item.get('node_id'),
    )
    difficulty_for_key = item.get('target_difficulty') or 'mixed'
    if difficulty_counts and len(difficulty_counts) > 1:
        difficulty_for_key = 'mixed_' + '_'.join(f'{k}{v}' for k, v in sorted(difficulty_counts.items()))
    generation_cache_key = item.get('generation_cache_key') or build_generation_cache_key(
        prompt_cache_key=prompt_cache_key,
        difficulty=difficulty_for_key,
        question_count=count,
        model_name=model_used,
    )
    chunk_hash = item.get('chunk_hash') or sha256_text('\n'.join(sorted(item.get('chunk_ids') or [])) + '|' + item_content, 32)
    prepared = dict(item)
    prepared.update({
        'batch_index': batch_index,
        'phase': phase_override or item.get('phase') or ('tail' if item.get('tail_wait_for_primary') else 'primary'),
        'content': item_content,
        'scope_title': scope_title,
        'question_count': count,
        'target_difficulty': target_difficulty,
        'difficulty_counts': difficulty_counts,
        'prompt_cache_key': prompt_cache_key,
        'generation_cache_key': generation_cache_key,
        'chunk_hash': chunk_hash,
    })
    return prepared


def _upsert_batch_record(db, job: GenerationJob, item: dict, *, status: str = 'queued', error: str | None = None) -> GenerationBatch:
    batch = db.query(GenerationBatch).filter(
        GenerationBatch.job_id == job.id,
        GenerationBatch.batch_index == int(item.get('batch_index') or 0),
        GenerationBatch.phase == str(item.get('phase') or 'primary'),
    ).first()
    now = datetime.utcnow()
    if not batch:
        batch = GenerationBatch(
            job_id=job.id,
            course_id=job.course_id,
            batch_index=int(item.get('batch_index') or 0),
            phase=str(item.get('phase') or 'primary'),
            difficulty=_difficulty_label(item),
            difficulty_counts_json=json.dumps(item.get('difficulty_counts') or {}, ensure_ascii=False),
            requested_questions=int(item.get('question_count') or 0),
            status=status,
            prompt_cache_key=item.get('prompt_cache_key'),
            generation_cache_key=item.get('generation_cache_key'),
            created_at=now,
            updated_at=now,
        )
    batch.status = status
    batch.updated_at = now
    if status == 'running' and not batch.started_at:
        batch.started_at = now
    if status in {'completed', 'partial_completed', 'failed', 'parse_failed', 'cache_hit'}:
        batch.finished_at = now
    if error:
        batch.error_message = error
    db.add(batch)
    db.commit()
    db.refresh(batch)
    if status == 'running':
        log_audit(
            db,
            action='generation.batch.start',
            status='running',
            message='Bắt đầu gọi GPT cho batch',
            course_id=job.course_id,
            target_type='generation_batch',
            target_id=batch.id,
            metadata={
                'job_id': job.id,
                'requested_by': job.requested_by,
                'batch_index': batch.batch_index,
                'phase': batch.phase,
                'difficulty': batch.difficulty,
                'requested_questions': batch.requested_questions,
                'prompt_cache_key': batch.prompt_cache_key,
            },
        )
    return batch


def _finish_batch_record(db, job: GenerationJob, item: dict, *, status: str, completed: int, usage: dict | None = None, error: str | None = None):
    batch = _upsert_batch_record(db, job, item, status=status, error=error)
    usage = usage or {}
    batch.completed_questions = int(completed or 0)
    batch.actual_input_tokens = int(usage.get('input_tokens') or 0)
    batch.actual_cached_input_tokens = int(usage.get('cached_input_tokens') or 0)
    batch.actual_output_tokens = int(usage.get('output_tokens') or 0)
    batch.token_source = usage.get('token_source')
    batch.openai_response_id = usage.get('response_id')
    batch.finished_at = datetime.utcnow()
    db.add(batch)
    db.commit()
    audit_status = 'success' if status in {'completed', 'partial_completed', 'cache_hit'} else 'failed'
    error_type = None
    if audit_status == 'failed':
        error_type = AuditErrorType.EXTERNAL_SERVICE_ERROR if status in {'failed', 'parse_failed'} else AuditErrorType.SYSTEM_ERROR
    log_audit(
        db,
        action='generation.batch.finish',
        status=audit_status,
        error_type=error_type,
        message=error or f'Kết thúc batch với trạng thái {status}',
        course_id=job.course_id,
        target_type='generation_batch',
        target_id=batch.id,
        metadata={
            'job_id': job.id,
            'requested_by': job.requested_by,
            'batch_index': batch.batch_index,
            'phase': batch.phase,
            'difficulty': batch.difficulty,
            'requested_questions': batch.requested_questions,
            'completed_questions': batch.completed_questions,
            'actual_input_tokens': batch.actual_input_tokens,
            'actual_cached_input_tokens': batch.actual_cached_input_tokens,
            'actual_output_tokens': batch.actual_output_tokens,
            'token_source': batch.token_source,
            'openai_response_id': batch.openai_response_id,
        },
    )


def _missing_by_difficulty(item: dict, created_count: int) -> dict[str, int]:
    requested = int(item.get('question_count') or 0)
    missing = max(requested - int(created_count or 0), 0)
    if missing <= 0:
        return {}
    counts = item.get('difficulty_counts') or {}
    if len(counts) == 1:
        diff = next(iter(counts.keys()))
        return {diff: missing}
    # If a mixed tail creates too few questions, allocate missing to the largest requested group.
    if counts:
        diff = max(counts.items(), key=lambda kv: int(kv[1] or 0))[0]
        return {diff: missing}
    diff = item.get('target_difficulty') or 'mixed'
    return {str(diff): missing}


async def _call_gateway_with_retry(gateway: ModelGateway, item: dict, job: GenerationJob) -> dict:
    attempts = max(1, int(settings.openai_retry_max_attempts or 1))
    base_seconds = max(0.5, float(settings.openai_retry_base_seconds or 1.0))
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            questions, usage = await gateway.generate_questions(
                content=item['content'],
                question_count=int(item['question_count']),
                scope_title=item.get('scope_title'),
                target_difficulty=item.get('target_difficulty'),
                difficulty_counts=item.get('difficulty_counts'),
                provider=job.provider,
                prompt_cache_key=item.get('prompt_cache_key'),
            )
            return {'ok': True, 'item': item, 'questions': questions, 'usage': usage}
        except ModelResponseParseError as exc:
            # This request may already be billed; do not retry blindly because a
            # retry would spend again. Let recovery/cache handle it.
            return {'ok': False, 'parse_error': True, 'item': item, 'exception': exc}
        except Exception as exc:  # provider/network/rate-limit errors before usable response
            last_error = exc
            text = str(exc).lower()
            retryable = any(key in text for key in ['429', 'rate limit', 'temporarily', 'timeout', 'connection', '503', '502'])
            if not retryable or attempt >= attempts:
                return {'ok': False, 'parse_error': False, 'item': item, 'exception': exc}
            await asyncio.sleep(base_seconds * (2 ** (attempt - 1)))
    return {'ok': False, 'parse_error': False, 'item': item, 'exception': last_error or RuntimeError('unknown model error')}


def _split_cache_warmup_items(items: list[dict]) -> tuple[list[dict], list[dict]]:
    """Pick one cheap warm-up request per prompt_cache_key.

    OpenAI prompt caching works best when a stable prefix has already been seen
    before the next requests with the same prefix start. Running all difficulty
    calls at exactly the same time can be faster, but it may miss cache hits.
    This warm-up stage sends one request for each content prefix first, then
    parallelizes the remaining EASY/MEDIUM/HARD batches.
    """
    if not settings.openai_prompt_cache_warmup_enabled or len(items) <= 1:
        return [], items

    groups: dict[str, list[dict]] = defaultdict(list)
    for item in items:
        groups[str(item.get('prompt_cache_key') or 'no-cache-key')].append(item)

    warmups: list[dict] = []
    warmup_ids: set[int] = set()
    for group_items in groups.values():
        if len(group_items) <= 1:
            continue
        # Choose the smallest request in this prefix group. It warms the same
        # stable content prefix, finishes faster, and lets later/larger batches
        # benefit from cached input.
        chosen = sorted(
            group_items,
            key=lambda item: (int(item.get('question_count') or 0), int(item.get('batch_index') or 0)),
        )[0]
        warmups.append(chosen)
        warmup_ids.add(id(chosen))

    remaining = [item for item in items if id(item) not in warmup_ids]
    return warmups, remaining


async def _run_api_items_parallel(items: list[dict], job: GenerationJob, gateway: ModelGateway):
    max_parallel = 1
    if settings.openai_parallel_enabled:
        max_parallel = max(1, min(int(settings.openai_max_parallel_calls or 1), 8))

    async def run_many(items_to_run: list[dict]):
        if not items_to_run:
            return
        semaphore = asyncio.Semaphore(max_parallel)

        async def guarded(item: dict):
            async with semaphore:
                return await _call_gateway_with_retry(gateway, item, job)

        tasks = [asyncio.create_task(guarded(item)) for item in items_to_run]
        for task in asyncio.as_completed(tasks):
            yield await task

    warmup_items, remaining_items = _split_cache_warmup_items(items)

    # Stage 1: one warm-up request per prompt_cache_key. Different cache keys
    # may run in parallel; same key intentionally waits so following batches can
    # reuse cached input.
    async for result in run_many(warmup_items):
        yield result

    # Stage 2: normal controlled parallelism for all remaining batches.
    async for result in run_many(remaining_items):
        yield result


def _merge_counts(left: dict[str, int], right: dict[str, int]) -> dict[str, int]:
    merged = defaultdict(int)
    for source in (left or {}, right or {}):
        for key, value in source.items():
            if int(value or 0) > 0:
                merged[str(key).lower()] += int(value)
    return dict(merged)


def _build_tail_items(job: GenerationJob, base_tail_items: list[dict], missing_counts: dict[str, int], content: str, model_used: str, start_batch_index: int) -> list[dict]:
    """Build delayed tail batches while preserving one prompt per difficulty.

    Do not merge EASY/MEDIUM/HARD tails into one mixed prompt. The project
    intentionally uses three difficulty prompts so each tail item must keep its
    own target_difficulty. Example:

        planned EASY tail 1 + missing EASY 1     -> EASY tail 2
        planned MEDIUM tail 3 + missing MEDIUM 12 -> MEDIUM tail 15

    This still saves input cost because the EASY/MEDIUM/HARD prompts share the
    same large stable prefix and prompt_cache_key.
    """
    counts_by_diff: dict[str, int] = {}
    base_by_diff: dict[str, dict] = {}
    fallback_base = base_tail_items[0] if base_tail_items else {}

    for item in base_tail_items:
        item_counts = item.get('difficulty_counts') or {}
        if not item_counts and item.get('target_difficulty'):
            item_counts = {str(item.get('target_difficulty')).lower(): int(item.get('question_count') or 0)}
        for diff, value in item_counts.items():
            diff_key = str(diff).lower()
            if diff_key not in {'easy', 'medium', 'hard'}:
                continue
            count = int(value or 0)
            if count <= 0:
                continue
            counts_by_diff[diff_key] = counts_by_diff.get(diff_key, 0) + count
            base_by_diff.setdefault(diff_key, item)

    for diff, value in (missing_counts or {}).items():
        diff_key = str(diff).lower()
        if diff_key not in {'easy', 'medium', 'hard'}:
            continue
        count = int(value or 0)
        if count > 0:
            counts_by_diff[diff_key] = counts_by_diff.get(diff_key, 0) + count

    tail_items: list[dict] = []
    offset = 0
    for diff in ['easy', 'medium', 'hard']:
        count = int(counts_by_diff.get(diff) or 0)
        if count <= 0:
            continue
        base = base_by_diff.get(diff) or fallback_base
        raw = dict(base)
        raw.update({
            'phase': 'tail',
            'tail_wait_for_primary': True,
            'target_difficulty': diff,
            'difficulty_counts': {diff: count},
            'question_count': count,
            'scope_title': base.get('scope_title') or job.topic,
            'content': base.get('content') or content,
            'generation_cache_key': None,
        })
        tail_items.append(_prepare_item(job, raw, content, model_used, start_batch_index + offset, phase_override='tail'))
        offset += 1
    return tail_items


async def _generate_questions(job_id: str, content_override: str | None = None, work_items: list[dict] | None = None):
    apply_runtime_settings()
    db = SessionLocal()
    job = None
    totals = {'input': 0, 'cached': 0, 'output': 0}
    raw_usage_parts: list[dict] = []
    usage_sources: list[str] = []
    provider_used = 'openai'
    model_used = settings.openai_model
    all_created = []
    parse_error: str | None = None
    error_messages: list[str] = []
    try:
        # Acquire a row lock before moving the job to running. This makes
        # duplicate Celery deliveries safe: a second worker will wait, then see
        # running/completed and exit without creating duplicate questions.
        job = db.query(GenerationJob).filter(GenerationJob.id == job_id).with_for_update().first()
        if not job:
            return {'error': 'job not found'}
        if job.status in {'running', 'completed', 'partial_completed', 'partial_failed', 'failed', 'model_parse_failed'}:
            return {'job_id': job.id, 'status': job.status, 'idempotent_skip': True}
        provider_used = job.provider
        model_used = job.model_name or settings.openai_model
        job.status = 'running'
        job.updated_at = datetime.utcnow()
        db.commit()

        content = content_override
        if not content:
            chunks = db.query(ContentChunk).filter(ContentChunk.course_id == job.course_id).limit(12).all()
            content = '\n\n'.join(f"Source: {c.source_ref}\nType: {c.source_type}\nChunkId: {c.id}\nBlockId: {c.block_id}\n{c.content}" for c in chunks) or 'REST API dùng HTTP methods GET, POST, PUT, DELETE.'

        batches = create_batches(job.question_count, min(job.batch_size or settings.generation_batch_size, 6))
        if not work_items:
            work_items = [{'scope_title': job.topic, 'question_count': batch, 'content': content, 'phase': 'primary'} for batch in batches if batch > 0]

        prepared_items = [_prepare_item(job, item, content, model_used, idx + 1) for idx, item in enumerate(work_items)]
        primary_items = [item for item in prepared_items if not item.get('tail_wait_for_primary') and item.get('phase') != 'tail']
        base_tail_items = [item for item in prepared_items if item.get('tail_wait_for_primary') or item.get('phase') == 'tail']

        cache_service = GenerationCacheService(db)
        gateway = ModelGateway()
        missing_counts: dict[str, int] = {}

        async def process_items(items: list[dict], *, phase_name: str):
            nonlocal provider_used, model_used, parse_error, missing_counts
            api_items: list[dict] = []
            for item in items:
                if int(item.get('question_count') or 0) <= 0:
                    continue
                _upsert_batch_record(db, job, item, status='queued')
                cached_questions = cache_service.get_cached_questions(item['generation_cache_key'], int(item['question_count']))
                if cached_questions is not None:
                    usage = {
                        'input_tokens': 0,
                        'cached_input_tokens': 0,
                        'output_tokens': 0,
                        'provider': 'output_cache',
                        'model': model_used,
                        'token_source': 'output_cache_hit',
                        'raw_usage': {'cache_key': item['generation_cache_key'], 'prompt_cache_key': item['prompt_cache_key']},
                        'response_id': None,
                        'raw_output_text': '',
                        'prompt_cache_key': item['prompt_cache_key'],
                    }
                    provider_used, model_used = _append_usage(
                        usage=usage,
                        scope_title=item.get('scope_title'),
                        question_count=int(item['question_count']),
                        difficulty=_difficulty_label(item),
                        raw_usage_parts=raw_usage_parts,
                        usage_sources=usage_sources,
                        totals=totals,
                    )
                    created = QuestionService(db).create_from_ai_items(
                        course_id=job.course_id,
                        lesson_id=job.lesson_id,
                        items=cached_questions,
                        provider=provider_used,
                        model_name=model_used,
                        job_id=job.id,
                    )
                    all_created.extend(created)
                    _finish_batch_record(db, job, item, status='cache_hit', completed=len(created), usage=usage)
                    missing_counts = _merge_counts(missing_counts, _missing_by_difficulty(item, len(created)))
                else:
                    _upsert_batch_record(db, job, item, status='running')
                    api_items.append(item)

            async for result in _run_api_items_parallel(api_items, job, gateway):
                item = result['item']
                count = int(item.get('question_count') or 0)
                if result.get('ok'):
                    questions = result['questions']
                    usage = result['usage']
                    provider_used, model_used = _append_usage(
                        usage=usage,
                        scope_title=item.get('scope_title'),
                        question_count=count,
                        difficulty=_difficulty_label(item),
                        raw_usage_parts=raw_usage_parts,
                        usage_sources=usage_sources,
                        totals=totals,
                    )
                    cache_service.save_success(
                        cache_key=item['generation_cache_key'],
                        prompt_cache_key=item['prompt_cache_key'],
                        course_id=job.course_id,
                        source_node_id=item.get('node_id'),
                        chunk_hash=item.get('chunk_hash'),
                        difficulty=_difficulty_label(item),
                        question_count=count,
                        model_name=model_used,
                        raw_output_text=usage.get('raw_output_text'),
                        parsed_questions=questions,
                        response_id=usage.get('response_id'),
                        input_tokens=int(usage.get('input_tokens') or 0),
                        cached_input_tokens=int(usage.get('cached_input_tokens') or 0),
                        output_tokens=int(usage.get('output_tokens') or 0),
                    )
                    created = QuestionService(db).create_from_ai_items(
                        course_id=job.course_id,
                        lesson_id=job.lesson_id,
                        items=questions,
                        provider=provider_used,
                        model_name=model_used,
                        job_id=job.id,
                    )
                    all_created.extend(created)
                    status = 'completed' if len(created) >= count else 'partial_completed'
                    _finish_batch_record(db, job, item, status=status, completed=len(created), usage=usage)
                    missing_counts = _merge_counts(missing_counts, _missing_by_difficulty(item, len(created)))
                elif result.get('parse_error'):
                    exc = result['exception']
                    provider_used, model_used = _append_usage(
                        usage=exc.usage,
                        scope_title=item.get('scope_title'),
                        question_count=count,
                        difficulty=_difficulty_label(item),
                        raw_usage_parts=raw_usage_parts,
                        usage_sources=usage_sources,
                        totals=totals,
                        raw_output_text=exc.raw_output_text,
                        parse_error=str(exc),
                    )
                    cache_service.save_parse_failure(
                        cache_key=item['generation_cache_key'],
                        prompt_cache_key=item['prompt_cache_key'],
                        course_id=job.course_id,
                        source_node_id=item.get('node_id'),
                        chunk_hash=item.get('chunk_hash'),
                        difficulty=_difficulty_label(item),
                        question_count=count,
                        model_name=model_used,
                        raw_output_text=exc.raw_output_text,
                        response_id=exc.response_id,
                        input_tokens=int(exc.usage.get('input_tokens') or 0),
                        cached_input_tokens=int(exc.usage.get('cached_input_tokens') or 0),
                        output_tokens=int(exc.usage.get('output_tokens') or 0),
                        parse_error=str(exc),
                    )
                    parse_error = str(exc)
                    error_messages.append(f'{phase_name} batch {item.get("batch_index")}: {exc}')
                    _finish_batch_record(db, job, item, status='parse_failed', completed=0, usage=exc.usage, error=str(exc))
                    missing_counts = _merge_counts(missing_counts, _missing_by_difficulty(item, 0))
                else:
                    exc = result.get('exception') or RuntimeError('model call failed')
                    error_messages.append(f'{phase_name} batch {item.get("batch_index")}: {exc}')
                    _finish_batch_record(db, job, item, status='failed', completed=0, error=str(exc))
                    missing_counts = _merge_counts(missing_counts, _missing_by_difficulty(item, 0))

        # v25.9.8.1: run primary batches with controlled concurrency first.
        # The scheduler warms one prompt_cache_key before parallelizing the rest
        # so later difficulty prompts can reuse cached input. Delayed tail runs
        # after primary and preserves one prompt per difficulty: EASY tail,
        # MEDIUM tail, HARD tail.
        await process_items(primary_items, phase_name='primary')

        tail_items = _build_tail_items(job, base_tail_items, missing_counts, content or '', model_used, len(prepared_items) + 1)
        if tail_items and settings.generation_tail_batch_wait_enabled:
            # Prevent recursive missing from creating another paid tail loop.
            missing_counts = {}
            await process_items(tail_items, phase_name='tail')
        elif base_tail_items:
            await process_items(base_tail_items, phase_name='tail')

        final_status = 'completed' if len(all_created) >= int(job.question_count or 0) and not error_messages else ('partial_completed' if all_created else 'failed')
        if parse_error and all_created:
            final_status = 'partial_failed'
        elif parse_error and not all_created:
            final_status = 'model_parse_failed'
        err = None if final_status == 'completed' else (f'Created {len(all_created)}/{job.question_count} questions. ' + '; '.join(error_messages[:3])).strip()
        await _finalize_job_usage(
            db,
            job,
            status=final_status,
            error_message=err,
            totals=totals,
            raw_usage_parts=raw_usage_parts,
            usage_sources=usage_sources,
            provider_used=provider_used,
            model_used=model_used,
            questions_created=len(all_created),
            parse_error=parse_error,
        )
        return {'job_id': job.id, 'questions_created': len(all_created), 'status': final_status}
    except Exception as exc:
        if job:
            status = 'partial_failed' if (all_created or totals['input'] or totals['output']) else 'failed'
            await _finalize_job_usage(
                db,
                job,
                status=status,
                error_message=str(exc),
                totals=totals,
                raw_usage_parts=raw_usage_parts,
                usage_sources=usage_sources,
                provider_used=provider_used,
                model_used=model_used,
                questions_created=len(all_created),
                parse_error=parse_error,
            )
        return {'error': str(exc)}
    finally:
        db.close()


@celery_app.task(name='bank_material_extract_task')
def bank_material_extract_task(job_id: str):
    from pathlib import Path
    from app.services.bank_operation_jobs import BankOperationJobService
    from app.services.question_bank_service import VersionedQuestionBankService
    from app.services.audit_log import AuditErrorType, log_audit

    db = SessionLocal()
    ops = BankOperationJobService(db)
    job = ops.get_job(job_id)
    if not job:
        db.close()
        return {'ok': False, 'error': 'job_not_found'}
    try:
        request = job.request_json or {}
        ops.start(job, label='Đang đọc file và tách nội dung', total=5)
        pending_file = Path(str(request.get('pending_file_path') or ''))
        if not pending_file.exists() or not pending_file.is_file():
            raise ValueError(
                'Không tìm thấy file tạm của job upload. ' 
                'Nguyên nhân thường gặp: backend và worker không dùng chung LOCAL_STORAGE_PATH. ' 
                'Hãy cấu hình LOCAL_STORAGE_PATH=/app/.runtime cho cả backend và worker, deploy lại, rồi upload lại tài liệu.'
            )
        raw = pending_file.read_bytes()
        ops.progress(job, current=2, label='Đang chạy extractor/chunker')
        result = VersionedQuestionBankService(db).upload_material_bytes(
            bank_version_id=str(job.bank_version_id or request.get('bank_version_id')),
            filename=str(request.get('filename') or pending_file.name),
            raw=raw,
            content_type=str(request.get('content_type') or ''),
            title=str(request.get('title') or request.get('filename') or pending_file.name),
            change_type=str(request.get('change_type') or 'initial'),
            actor=job.requested_by,
            replace_existing=bool(request.get('replace_existing')),
        )
        ops.progress(job, current=4, label='Đang cập nhật dashboard/search index')
        material = result.get('material_version')
        result_json = {
            'ok': bool(result.get('ok')),
            'bank_version_id': job.bank_version_id,
            'material_version_id': getattr(material, 'id', None),
            'chunks_created': result.get('chunks_created'),
            'tokens_indexed': result.get('tokens_indexed'),
            'diff_required': result.get('diff_required'),
            'diff_base_bank_version_id': result.get('diff_base_bank_version_id'),
            'document_change_state': result.get('document_change_state'),
            'message': result.get('message'),
            'user_message': result.get('message') or f'Đã tách tài liệu thành công: tạo {result.get("chunks_created") or 0} đoạn nội dung.',
        }
        try:
            pending_file.unlink(missing_ok=True)
        except Exception:
            pass
        log_audit(db, action='question_bank.material.upload.async', status='success', message='Tách tài liệu bất đồng bộ thành công', user=None, target_type='bank_operation_job', target_id=job.id, metadata=result_json)
        return ops.complete(job, result=result_json, label='Đã tách và gắn tài liệu').result_json
    except Exception as exc:
        try:
            log_audit(db, action='question_bank.material.upload.async', status='failed', error_type=AuditErrorType.VALIDATION_ERROR, message=str(exc), user=None, target_type='bank_operation_job', target_id=job.id)
        except Exception:
            pass
        friendly = str(exc)
        return ops.fail(job, error=exc, result={
            'error': friendly,
            'user_message': friendly,
            'suggestion': 'Kiểm tra lại định dạng file, bật OCR nếu là scan/ảnh, hoặc upload bản DOCX/PDF có text rồi thử lại.',
        }).result_json
    finally:
        db.close()


@celery_app.task(name='bank_generate_questions_task')
def bank_generate_questions_task(job_id: str):
    from app.services.bank_operation_jobs import BankOperationJobService
    from app.services.question_bank_service import VersionedQuestionBankService
    from app.services.audit_log import AuditErrorType, log_audit

    async def _run():
        db = SessionLocal()
        ops = BankOperationJobService(db)
        job = ops.get_job(job_id)
        if not job:
            db.close()
            return {'ok': False, 'error': 'job_not_found'}
        try:
            payload = job.request_json or {}
            total_questions = int(payload.get('question_count') or 1)
            ops.start(job, label='Đang chuẩn bị prompt và gọi GPT', total=max(3, total_questions + 2))
            result = await VersionedQuestionBankService(db).generate_from_bank_version(
                bank_version_id=str(job.bank_version_id or payload.get('bank_version_id')),
                question_count=total_questions,
                target_question_count=payload.get('target_question_count'),
                difficulty_easy=int(payload.get('difficulty_easy') or 50),
                difficulty_medium=int(payload.get('difficulty_medium') or 30),
                difficulty_hard=int(payload.get('difficulty_hard') or 20),
                material_version_ids=payload.get('material_version_ids'),
                provider=str(payload.get('provider') or 'openai'),
                actor=job.requested_by,
                approve_after_generate=bool(payload.get('approve_after_generate')),
            )
            result_json = {
                'ok': bool(result.get('ok')),
                'bank_version_id': result.get('bank_version_id') or job.bank_version_id,
                'requested_questions': result.get('requested_questions'),
                'created_questions': result.get('created_questions'),
                'pending_review_count': result.get('pending_review_count'),
                'approved_count': result.get('approved_count'),
                'draft_error_count': result.get('draft_error_count'),
                'input_chunks': result.get('input_chunks'),
                'input_tokens': result.get('input_tokens'),
                'difficulty_counts': result.get('difficulty_counts'),
                'errors': result.get('errors') or [],
                'message': result.get('message'),
            }
            log_audit(db, action='question_bank.bank_version.generate.async', status='success' if result_json.get('created_questions') else 'failed', error_type=None if result_json.get('created_questions') else AuditErrorType.EXTERNAL_SERVICE_ERROR, message=result_json.get('message') or '', user=None, target_type='bank_operation_job', target_id=job.id, metadata=result_json)
            return ops.complete(job, result=result_json, label='Đã tạo câu hỏi').result_json
        except Exception as exc:
            try:
                log_audit(db, action='question_bank.bank_version.generate.async', status='failed', error_type=AuditErrorType.EXTERNAL_SERVICE_ERROR, message=str(exc), user=None, target_type='bank_operation_job', target_id=job.id)
            except Exception:
                pass
            return ops.fail(job, error=exc).result_json
        finally:
            db.close()

    return asyncio.run(_run())


@celery_app.task(name='bank_release_publish_task')
def bank_release_publish_task(job_id: str):
    from app.services.bank_operation_jobs import BankOperationJobService
    from app.services.question_bank_service import VersionedQuestionBankService
    from app.services.audit_log import AuditErrorType, log_audit

    async def _run():
        db = SessionLocal()
        ops = BankOperationJobService(db)
        job = ops.get_job(job_id)
        if not job:
            db.close()
            return {'ok': False, 'error': 'job_not_found'}
        try:
            payload = job.request_json or {}
            ops.start(job, label='Đang publish Bank Release sang Open edX Library', total=5)
            result = await VersionedQuestionBankService(db).publish_release_to_openedx(
                release_id=str(job.release_id or payload.get('release_id')),
                actor=job.requested_by,
                course_id_for_org=payload.get('openedx_course_id_for_org'),
                force_reimport=bool(payload.get('force_reimport')),
            )
            ops.progress(job, current=4, label='Đang verify kết quả publish')
            result_json = {
                'ok': bool(result.get('ok')),
                'release_id': result.get('release_id') or job.release_id,
                'release_code': result.get('release_code'),
                'status': result.get('status'),
                'openedx_library_key': result.get('openedx_library_key'),
                'question_count': result.get('question_count'),
                'imported_now_count': result.get('imported_now_count'),
                'skipped_existing_count': result.get('skipped_existing_count'),
                'errors': result.get('errors') or [],
                'message': 'Publish Bank Release sang Open edX Library thành công' if result.get('ok') else 'Publish Bank Release hoàn tất nhưng có lỗi',
            }
            log_audit(db, action='question_bank.release.publish_openedx.async', status='success', message=result_json['message'], user=None, target_type='bank_operation_job', target_id=job.id, metadata=result_json)
            return ops.complete(job, result=result_json, label='Đã publish Library').result_json
        except Exception as exc:
            try:
                log_audit(db, action='question_bank.release.publish_openedx.async', status='failed', error_type=AuditErrorType.EXTERNAL_SERVICE_ERROR, message=str(exc), user=None, target_type='bank_operation_job', target_id=job.id)
            except Exception:
                pass
            return ops.fail(job, error=exc).result_json
        finally:
            db.close()

    return asyncio.run(_run())


@celery_app.task(name='bank_quiz_create_task')
def bank_quiz_create_task(job_id: str):
    from app.services.bank_operation_jobs import BankOperationJobService
    from app.services.question_bank_service import VersionedQuestionBankService
    from app.services.audit_log import AuditErrorType, log_audit

    async def _run():
        db = SessionLocal()
        ops = BankOperationJobService(db)
        job = ops.get_job(job_id)
        if not job:
            db.close()
            return {'ok': False, 'error': 'job_not_found'}
        try:
            payload = job.request_json or {}
            ops.start(job, label='Đang tạo Quiz node và ItemBank slots trên Open edX', total=7)
            result = await VersionedQuestionBankService(db).create_quiz_from_release(
                course_chapter_mapping_id=str(payload.get('course_chapter_mapping_id')),
                quiz_title=str(payload.get('quiz_title') or ''),
                unit_title=str(payload.get('unit_title') or 'Quiz'),
                total_questions=int(payload.get('total_questions') or 15),
                difficulty_easy=int(payload.get('difficulty_easy') or 50),
                difficulty_medium=int(payload.get('difficulty_medium') or 30),
                difficulty_hard=int(payload.get('difficulty_hard') or 20),
                max_families_per_bank=int(payload.get('max_families_per_bank') or 2),
                custom_timer_enabled=bool(payload.get('custom_timer_enabled', True)),
                time_limit_minutes=int(payload.get('time_limit_minutes') or 15),
                retake_cooldown_minutes=int(payload.get('retake_cooldown_minutes') or 5),
                auto_submit_on_timeout=bool(payload.get('custom_timer_enabled', True)),
                lock_after_timeout=bool(payload.get('custom_timer_enabled', True)),
                native_timed_exam=bool(payload.get('native_timed_exam', False)),
                assessment_type=str(payload.get('assessment_type') or 'quiz'),
                actor=job.requested_by,
                expected_bank_release_id=str(job.release_id or payload.get('release_id')),
            )
            result_json = {
                'ok': bool(result.get('ok')),
                'status': result.get('status'),
                'course_quiz_instance_id': result.get('course_quiz_instance_id'),
                'openedx_course_id': result.get('openedx_course_id'),
                'openedx_quiz_node_id': result.get('openedx_quiz_node_id'),
                'openedx_unit_node_id': result.get('openedx_unit_node_id'),
                'bank_release_id': result.get('bank_release_id') or job.release_id,
                'release_code': result.get('release_code'),
                'message': result.get('message'),
            }
            log_audit(db, action='question_bank.release.quiz.create.async', status='success', message=result_json.get('message') or 'Tạo Quiz thành công', user=None, course_id=result_json.get('openedx_course_id'), target_type='bank_operation_job', target_id=job.id, metadata=result_json)
            return ops.complete(job, result=result_json, label='Đã tạo Quiz Open edX').result_json
        except Exception as exc:
            try:
                log_audit(db, action='question_bank.release.quiz.create.async', status='failed', error_type=AuditErrorType.EXTERNAL_SERVICE_ERROR, message=str(exc), user=None, target_type='bank_operation_job', target_id=job.id)
            except Exception:
                pass
            return ops.fail(job, error=exc).result_json
        finally:
            db.close()

    return asyncio.run(_run())



@celery_app.task(name='bank_question_import_task')
def bank_question_import_task(job_id: str):
    from app.services.bank_operation_jobs import BankOperationJobService
    from app.services.question_bank.import_export import import_questions
    from app.services.audit_log import AuditErrorType, log_audit

    db = SessionLocal()
    ops = BankOperationJobService(db)
    job = ops.get_job(job_id)
    if not job:
        db.close()
        return {'ok': False, 'error': 'job_not_found'}
    try:
        payload = job.request_json or {}
        total = max(2, int(payload.get('valid_count') or 1) + 1)
        ops.start(job, label='Đang import câu hỏi', total=total)
        result = import_questions(
            db,
            bank_version_id=str(job.bank_version_id or payload.get('bank_version_id') or job.target_id),
            preview_path=str(payload.get('preview_path') or ''),
            actor=job.requested_by,
        )
        ops.progress(job, current=total - 1, total=total, label='Đang cập nhật thống kê Bank')
        try:
            from app.services.bank_dashboard_stats import BankDashboardStatsService
            BankDashboardStatsService(db).refresh_for_bank_version(str(job.bank_version_id or job.target_id))
        except Exception:
            db.rollback()
        log_audit(db, action='question_bank.question.import.async', status='success', message=result.get('message') or 'Import câu hỏi hoàn tất', user=None, target_type='bank_operation_job', target_id=job.id, metadata=result)
        return ops.complete(job, result=result, label='Đã import câu hỏi').result_json
    except Exception as exc:
        try:
            log_audit(db, action='question_bank.question.import.async', status='failed', error_type=AuditErrorType.VALIDATION_ERROR, message=str(exc), user=None, target_type='bank_operation_job', target_id=job.id)
        except Exception:
            pass
        return ops.fail(job, error=exc, result={'user_message': str(exc)}).result_json
    finally:
        db.close()


@celery_app.task(name='bank_material_cleanup_task')
def bank_material_cleanup_task(retention_days: int | None = None, limit: int | None = None, dry_run: bool = False):
    """Admin/ops task for v25.9.16.3.6 material cleanup policy."""
    from app.services.question_bank_service import VersionedQuestionBankService
    db = SessionLocal()
    try:
        return VersionedQuestionBankService(db).purge_deleted_materials(
            retention_days=retention_days,
            dry_run=bool(dry_run),
            limit=limit,
        )
    finally:
        db.close()


@celery_app.task(name='academic_ap_sync_task')
def academic_ap_sync_task(run_id: str):
    """Run AP get-data-cms sync outside request/response and persist progress in AcademicSyncRun."""
    from app.models.academic import AcademicSyncRun
    from app.services.ap_academic_sync import AcademicImportService, SyncCounters
    from app.services.audit_log import AuditErrorType, log_audit

    db = SessionLocal()
    try:
        run = db.get(AcademicSyncRun, run_id)
        if not run:
            return {'ok': False, 'error': 'sync_run_not_found'}
        if run.status not in {'queued', 'running'}:
            return {'ok': run.status == 'completed', 'status': run.status, 'sync_run_id': run.id}

        data = run.counters_json if isinstance(run.counters_json, dict) else {}
        request = data.get('request') if isinstance(data.get('request'), dict) else {}
        service = AcademicImportService(db)
        service.update_run_progress(run, current=0, total=1, label='Hệ thống đang chuẩn bị job đồng bộ AP', counters=SyncCounters())
        result_run, counters = service.sync_from_ap(
            requested_by=run.requested_by,
            term_name=str(request.get('term_name') or run.term_name or ''),
            campus=request.get('campus'),
            branch=str(request.get('branch') or run.branch or 'poly'),
            subject_codes=list(request.get('subject_codes') or []),
            max_subjects=int(request.get('max_subjects') or 0),
            dry_run=bool(request.get('dry_run')),
            sync_scope=str(request.get('sync_scope') or 'all'),
            campuses=list(request.get('campuses') or []),
            run=run,
        )
        status = 'success' if result_run.status == 'completed' else 'failed'
        try:
            log_audit(
                db,
                action='academic.ap.sync_api.async',
                status=status,
                error_type=None if status == 'success' else AuditErrorType.EXTERNAL_SERVICE_ERROR,
                message='Đồng bộ dữ liệu AP qua job hoàn tất' if status == 'success' else result_run.error_message,
                user=None,
                target_type='academic_sync_run',
                target_id=result_run.id,
                metadata=json_safe_value({'request': request, 'counters': counters.as_dict()}),
            )
        except Exception:
            pass
        return {'ok': result_run.status == 'completed', 'sync_run_id': result_run.id, 'status': result_run.status, 'counters': counters.as_dict()}
    except Exception as exc:
        db.rollback()
        run = db.get(AcademicSyncRun, run_id)
        if run:
            run.status = 'failed'
            run.error_message = str(exc)[:4000] or 'Không thể hoàn tất đồng bộ AP.'
            data = run.counters_json if isinstance(run.counters_json, dict) else {}
            data['progress'] = {'current': 0, 'total': 1, 'label': 'Đồng bộ AP thất bại', 'updated_at': datetime.utcnow().isoformat()}
            run.counters_json = json_safe_value(data)
            run.finished_at = datetime.utcnow()
            db.add(run)
            db.commit()
        return {'ok': False, 'error': 'academic_ap_sync_failed', 'message': str(exc)}
    finally:
        db.close()



def _worker_user_from_request_json(request_json: dict | None, *, fallback_user_id: str | None, source: str, job_id: str):
    """Rebuild a safe user context for worker-side RBAC checks.

    Tokens/cookies are intentionally not stored. Business RBAC is read from DB
    using user_id/username; legacy permissions are only the ones captured at
    enqueue time, never broader than the requester.
    """

    data = (request_json or {}).get('requester_context') if isinstance(request_json, dict) else None
    data = data if isinstance(data, dict) else {}
    permissions = data.get('permissions') if isinstance(data.get('permissions'), list) else []
    course_ids = data.get('course_ids') if isinstance(data.get('course_ids'), list) else None
    return UserContext(
        user_id=str(data.get('user_id') or fallback_user_id or 'academic-worker'),
        username=str(data.get('username') or data.get('user_id') or fallback_user_id or 'academic-worker'),
        email=data.get('email'),
        role=str(data.get('role') or 'viewer'),
        permissions={str(item) for item in permissions},
        course_ids=[str(item) for item in course_ids] if course_ids is not None else None,
        raw_claims={'source': source, 'job_id': job_id, 'worker_scope_recheck': True},
    )


def _advisory_xact_lock_for_key(db, key: str) -> None:
    try:
        bind = db.get_bind()
        if bind and bind.dialect.name == 'postgresql':
            db.execute(text('SELECT pg_advisory_xact_lock(hashtext(:key))'), {'key': key})
    except Exception:
        pass

@celery_app.task(name='academic_class_sync_task')
def academic_class_sync_task(job_id: str):
    """Run class-level CMS/Open edX sync outside request/response."""
    from app.models.academic import AcademicClassSyncJob
    from app.services.academic_service import AcademicService
    from app.services.audit_log import AuditErrorType, log_audit

    db = SessionLocal()
    try:
        job = db.get(AcademicClassSyncJob, job_id)
        if not job:
            return {'ok': False, 'error': 'job_not_found'}
        if job.status not in {'queued', 'running'}:
            return job.result_json or {'ok': job.status == 'completed', 'status': job.status}

        now = datetime.utcnow()
        job.status = 'running'
        job.started_at = job.started_at or now
        job.updated_at = now
        job.progress_current = max(job.progress_current or 0, 10)
        labels = {
            'cms_sync_check': 'Đang kiểm tra CMS',
            'cms_enrollment_sync': 'Đang enroll CMS',
            'learning_sync': 'Đang cập nhật điểm',
            'full_cms_sync': 'Đang đồng bộ CMS',
        }
        job.progress_label = labels.get(job.job_type, 'Đang đồng bộ học vụ')
        db.commit()

        request_json = job.request_json if isinstance(job.request_json, dict) else {}
        approved_class_id = str(request_json.get('approved_class_id') or '')
        if approved_class_id and approved_class_id != str(job.class_id):
            raise PermissionError('Job đồng bộ lớp vượt ngoài phạm vi đã được duyệt khi enqueue.')

        worker_user = _worker_user_from_request_json(
            request_json,
            fallback_user_id=job.requested_by,
            source='celery_academic_class_sync_job',
            job_id=job.id,
        )
        service = AcademicService(db)
        # Re-check RBAC inside worker. For normal jobs this catches stale or
        # tampered job rows; for bulk child jobs the approved_class_id above
        # additionally freezes the scope authorized at parent enqueue time.
        service.assert_can_access_class(worker_user, job.class_id)
        force = bool(job.force)
        limit = max(1, min(500, int(job.limit or 500)))

        if job.job_type == 'cms_sync_check':
            result = service.resolve_class_openedx_users(worker_user, job.class_id, force=force, limit=limit)
            action = 'academic.cms_sync_check.class.async'
            label = 'Hoàn tất kiểm tra CMS'
        elif job.job_type == 'cms_enrollment_sync':
            result = service.sync_class_course_enrollment(worker_user, job.class_id, force=force, limit=limit, mode=job.mode)
            action = 'academic.cms_enrollment_sync.class.async'
            label = 'Hoàn tất enroll CMS'
        elif job.job_type == 'learning_sync':
            result = service.sync_class_learning_insight(worker_user, job.class_id, force=force, limit=limit)
            action = 'academic.learning_sync.class.async'
            label = 'Hoàn tất cập nhật điểm'
        elif job.job_type == 'full_cms_sync':
            result = service.sync_class_full_cms_flow(
                worker_user,
                job.class_id,
                force=force,
                limit=limit,
                mode=job.mode,
                auto_map_course=bool(request_json.get('auto_map_course', True)),
                sync_learning=bool(request_json.get('sync_learning', True)),
            )
            action = 'academic.full_cms_sync.class.async'
            label = 'Hoàn tất đồng bộ CMS'
        else:
            raise ValueError(f'Unsupported academic class sync job_type: {job.job_type}')

        safe_result = json_safe_value(result)
        job.status = 'completed'
        job.progress_current = 100
        job.progress_total = 100
        job.progress_label = label
        job.result_json = safe_result
        job.error_message = None
        job.finished_at = datetime.utcnow()
        job.updated_at = datetime.utcnow()
        db.add(job)
        db.commit()
        try:
            log_audit(
                db,
                action=action,
                status='success',
                message=label,
                user=None,
                target_type='academic_class_sync_job',
                target_id=job.id,
                metadata=json_safe_value({'class_id': job.class_id, 'counts': safe_result.get('counts', {}) if isinstance(safe_result, dict) else {}, 'updated': safe_result.get('updated', 0) if isinstance(safe_result, dict) else 0}),
            )
        except Exception:
            pass
        return safe_result
    except Exception as exc:
        db.rollback()
        job = db.get(AcademicClassSyncJob, job_id)
        if job:
            job.status = 'failed'
            job.progress_current = job.progress_current or 0
            job.progress_total = 100
            job.progress_label = 'Đồng bộ thất bại'
            job.error_message = str(exc)[:4000] or 'Không thể hoàn tất đồng bộ lớp.'
            job.result_json = json_safe_value({'ok': False, 'message': job.error_message})
            job.finished_at = datetime.utcnow()
            job.updated_at = datetime.utcnow()
            db.add(job)
            db.commit()
            try:
                log_audit(db, action='academic.class_sync.async', status='failed', error_type=AuditErrorType.EXTERNAL_SERVICE_ERROR, message=str(exc), user=None, target_type='academic_class_sync_job', target_id=job.id, metadata=json_safe_value({'class_id': job.class_id, 'job_type': job.job_type}))
            except Exception:
                pass
        return json_safe_value({'ok': False, 'error': 'academic_class_sync_failed', 'message': str(exc)})
    finally:
        db.close()


def _enqueue_academic_class_sync_child_job(
    db,
    *,
    requested_by: str | None,
    class_id: str,
    force: bool,
    limit: int,
    mode: str | None,
    auto_map_course: bool,
    sync_learning: bool,
    requester_context: dict | None = None,
    parent_job_id: str | None = None,
):
    """Create/reuse a durable per-class full CMS sync job from a parent bulk job."""
    from app.models.academic import AcademicClassSyncJob

    _advisory_xact_lock_for_key(db, f'academic-class-sync:{class_id}')

    existing = (
        db.query(AcademicClassSyncJob)
        .filter(
            AcademicClassSyncJob.class_id == class_id,
            AcademicClassSyncJob.status.in_(['queued', 'running']),
        )
        .order_by(AcademicClassSyncJob.created_at.desc())
        .first()
    )
    if existing:
        return existing, True

    clean_limit = max(1, min(500, int(limit or 500)))
    job = AcademicClassSyncJob(
        job_type='full_cms_sync',
        status='queued',
        class_id=class_id,
        requested_by=requested_by or 'academic-bulk-worker',
        force=bool(force),
        limit=clean_limit,
        mode=mode,
        progress_current=0,
        progress_total=100,
        progress_label='Đang chờ đồng bộ từ Auto map tất cả',
        request_json=json_safe_value({
            'force': bool(force),
            'limit': clean_limit,
            'mode': mode,
            'auto_map_course': auto_map_course,
            'sync_learning': sync_learning,
            'parent_job_type': 'subject_auto_map_all_sync',
            'parent_job_id': parent_job_id,
            'requester_context': requester_context or {},
            'approved_class_id': class_id,
        }),
        result_json={},
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    academic_class_sync_task.delay(job.id)
    return job, False


@celery_app.task(name='academic_subject_auto_map_all_sync_task')
def academic_subject_auto_map_all_sync_task(job_id: str):
    """Run heavy /student-management Auto map tất cả inside Celery.

    The HTTP request only creates this parent job. This worker job performs safe
    subject Course CMS auto-mapping, then enqueues child full_cms_sync jobs for
    mapped classes so every user can see progress in /jobs and F5 is safe.
    """
    from app.models.academic import AcademicBulkOperationJob
    from app.services.academic_service import AcademicService
    from app.services.audit_log import AuditErrorType, log_audit

    db = SessionLocal()
    try:
        job = db.get(AcademicBulkOperationJob, job_id)
        if not job:
            return {'ok': False, 'error': 'job_not_found'}
        if job.status not in {'queued', 'running'}:
            return job.result_json or {'ok': job.status == 'completed', 'status': job.status}

        request_json = job.request_json if isinstance(job.request_json, dict) else {}
        now = datetime.utcnow()
        job.status = 'running'
        job.started_at = job.started_at or now
        job.updated_at = now
        job.progress_current = max(job.progress_current or 0, 5)
        job.progress_total = 100
        job.progress_label = 'Đang auto map Course CMS theo bộ lọc'
        db.add(job)
        db.commit()

        worker_user = _worker_user_from_request_json(
            request_json,
            fallback_user_id=job.requested_by,
            source='celery_academic_bulk_operation_job',
            job_id=job.id,
        )
        approved_class_ids = {str(item) for item in (request_json.get('approved_class_ids') or []) if str(item)}
        if not approved_class_ids:
            raise PermissionError('Job Auto map tất cả không có phạm vi lớp đã được duyệt; dừng để tránh mở rộng quyền.')
        service = AcademicService(db)
        prepared = service.auto_map_subject_courses_for_filter(
            worker_user,
            term_id=str(request_json.get('term_id') or job.term_id or ''),
            branch=request_json.get('branch') or job.branch,
            campus=request_json.get('campus') or job.campus,
            search=request_json.get('search'),
            learning_status=request_json.get('learning_status'),
            max_classes=int(request_json.get('max_classes') or 3000),
        )

        raw_class_ids = [str(item) for item in (prepared.get('class_ids') or [])]
        class_ids = [item for item in raw_class_ids if item in approved_class_ids]
        blocked_class_ids = [item for item in raw_class_ids if item not in approved_class_ids]
        class_total = int(prepared.get('class_total') or len(class_ids) or 0)
        result_json = dict(prepared)
        result_json.update({'jobs_queued': 0, 'jobs_reused': 0, 'jobs_skipped': 0, 'job_ids': [], 'scope_blocked_class_count': len(blocked_class_ids), 'approved_class_count': len(approved_class_ids)})
        job.result_json = json_safe_value(result_json)
        job.progress_current = 40
        job.progress_total = 100
        job.progress_label = f"Đã map môn; đang đưa {len(class_ids)}/{class_total} lớp vào hàng đợi đồng bộ"
        job.updated_at = datetime.utcnow()
        db.add(job)
        db.commit()

        jobs_queued = 0
        jobs_reused = 0
        jobs_skipped = 0
        child_job_ids: list[str] = []
        total_children = max(len(class_ids), 1)
        for index, class_id in enumerate(class_ids, start=1):
            try:
                child_job, reused = _enqueue_academic_class_sync_child_job(
                    db,
                    requested_by=job.requested_by,
                    class_id=str(class_id),
                    force=bool(request_json.get('force', True)),
                    limit=int(request_json.get('limit') or 500),
                    mode=request_json.get('mode'),
                    auto_map_course=True,
                    sync_learning=bool(request_json.get('sync_learning', True)),
                    requester_context=request_json.get('requester_context') if isinstance(request_json.get('requester_context'), dict) else {},
                    parent_job_id=job.id,
                )
                child_job_ids.append(child_job.id)
                if reused:
                    jobs_reused += 1
                else:
                    jobs_queued += 1
            except Exception:
                jobs_skipped += 1
            if index == 1 or index % 20 == 0 or index == len(class_ids):
                current = 40 + int((index / total_children) * 50)
                job = db.get(AcademicBulkOperationJob, job_id)
                if job:
                    next_result = dict(job.result_json or {}) if isinstance(job.result_json, dict) else {}
                    next_result.update({
                        'jobs_queued': jobs_queued,
                        'jobs_reused': jobs_reused,
                        'jobs_skipped': jobs_skipped,
                        'job_ids': child_job_ids[:200],
                    })
                    job.result_json = json_safe_value(next_result)
                    job.progress_current = min(95, current)
                    job.progress_total = 100
                    job.progress_label = f'Đã đưa {index}/{len(class_ids)} lớp vào hàng đợi đồng bộ CMS/enroll'
                    job.updated_at = datetime.utcnow()
                    db.add(job)
                    db.commit()

        final_result = dict(prepared)
        final_result.update({
            'jobs_queued': jobs_queued,
            'jobs_reused': jobs_reused,
            'jobs_skipped': jobs_skipped,
            'job_ids': child_job_ids[:200],
            'scope_blocked_class_count': len(blocked_class_ids),
            'approved_class_count': len(approved_class_ids),
        })
        message = (
            f"Đã auto map {prepared.get('subject_mapped', 0)} môn mới; "
            f"{prepared.get('subject_already_mapped', 0)} môn đã map sẵn; "
            f"đã đưa {jobs_queued} lớp vào hàng đợi đồng bộ CMS/enroll"
        )
        if jobs_reused:
            message += f'; {jobs_reused} lớp đang có job chạy nên dùng lại'
        if prepared.get('subject_failed'):
            message += f"; {prepared.get('subject_failed')} môn chưa map được"
        if prepared.get('capped'):
            message += f"; đã giới hạn {len(class_ids)}/{prepared.get('class_total', 0)} lớp để tránh quá tải"
        final_result['message'] = message

        job = db.get(AcademicBulkOperationJob, job_id)
        if job:
            job.status = 'completed'
            job.progress_current = 100
            job.progress_total = 100
            job.progress_label = message[:255]
            job.result_json = json_safe_value(final_result)
            job.error_message = None
            job.finished_at = datetime.utcnow()
            job.updated_at = datetime.utcnow()
            db.add(job)
            db.commit()
        try:
            log_audit(
                db,
                action='academic.subject_course_mapping.auto_all_sync_job.finish',
                status='success',
                message=message,
                user=None,
                target_type='academic_bulk_operation_job',
                target_id=job_id,
                metadata=json_safe_value(final_result),
            )
        except Exception:
            pass
        return json_safe_value({'ok': True, **final_result})
    except Exception as exc:
        db.rollback()
        job = db.get(AcademicBulkOperationJob, job_id)
        if job:
            job.status = 'failed'
            job.error_message = str(exc)[:4000] or 'Không thể Auto map tất cả.'
            job.progress_label = 'Auto map tất cả thất bại'
            job.result_json = json_safe_value({'ok': False, 'message': job.error_message})
            job.finished_at = datetime.utcnow()
            job.updated_at = datetime.utcnow()
            db.add(job)
            db.commit()
            try:
                log_audit(db, action='academic.subject_course_mapping.auto_all_sync_job.failed', status='failed', error_type=AuditErrorType.SYSTEM_ERROR, message=str(exc), user=None, target_type='academic_bulk_operation_job', target_id=job_id, metadata=json_safe_value({'request_json': job.request_json}))
            except Exception:
                pass
        return json_safe_value({'ok': False, 'error': 'academic_bulk_auto_map_failed', 'message': str(exc)})
    finally:
        db.close()


@celery_app.task(name='academic_teacher_report_job_task')
def academic_teacher_report_job_task(job_id: str):
    """Run teacher-management cache rebuild/export jobs outside request/response."""
    from pathlib import Path
    from app.core.config import settings
    from app.core.json_safe import json_safe_value
    from app.models.academic import AcademicTeacherReportJob
    from app.services.academic_service import AcademicService
    from app.services.audit_log import AuditErrorType, log_audit
    from app.api.routes.academic import _write_training_teacher_report_xlsx

    db = SessionLocal()
    try:
        job = db.get(AcademicTeacherReportJob, job_id)
        if not job:
            return {'ok': False, 'error': 'job_not_found'}
        if job.status not in {'queued', 'running'}:
            return job.result_json or {'ok': job.status == 'completed', 'status': job.status}

        now = datetime.utcnow()
        job.status = 'running'
        job.started_at = job.started_at or now
        job.updated_at = now
        job.progress_current = max(job.progress_current or 0, 10)
        job.progress_label = 'Đang tính lại báo cáo giáo viên' if job.job_type == 'rebuild_cache' else 'Đang dựng file Excel báo cáo giáo viên'
        db.commit()

        request = job.request_json if isinstance(job.request_json, dict) else {}
        worker_user = _worker_user_from_request_json(
            request,
            fallback_user_id=job.requested_by,
            source='celery_teacher_report_job',
            job_id=job.id,
        )
        service = AcademicService(db)
        term_id = job.term_id or request.get('term_id')
        branch = job.branch or request.get('branch')
        campus = job.campus or request.get('campus')

        if job.job_type == 'rebuild_cache':
            result = service.rebuild_training_teacher_report_cache(worker_user, term_id=term_id, branch=branch, campus=campus)
            job.progress_label = 'Đã tính lại cache báo cáo giáo viên'
            job.file_path = None
            job.file_name = None
            action = 'academic.teacher_report.cache_rebuild.async'
        elif job.job_type == 'export_excel':
            report = service.training_teacher_report(
                worker_user,
                term_id=term_id,
                branch=branch,
                campus=campus,
                search=request.get('search'),
                learning_status=request.get('learning_status'),
                teacher_id=request.get('teacher_id'),
                page=1,
                page_size=200,
                include_all=True,
                include_students=True,
                use_cache=False,
            )
            job.progress_current = 70
            job.progress_label = 'Đang ghi file Excel báo cáo giáo viên'
            db.commit()
            root = Path(settings.local_storage_path or '/app/.runtime').expanduser().resolve()
            out_dir = root / 'teacher-reports'
            out_dir.mkdir(parents=True, exist_ok=True)
            retention_seconds = max(3600, int(settings.academic_teacher_report_file_retention_hours) * 3600)
            cutoff = datetime.utcnow().timestamp() - retention_seconds
            for old_file in out_dir.glob('teacher-management-report-*.xlsx'):
                try:
                    if old_file.is_file() and old_file.stat().st_mtime < cutoff:
                        old_file.unlink(missing_ok=True)
                except OSError:
                    pass
            safe_branch = str(branch or 'all').replace('/', '-').replace(' ', '-')
            safe_campus = str(campus or 'all').replace('/', '-').replace(' ', '-')
            filename = f'teacher-management-report-{safe_branch}-{safe_campus}-{job.id[:8]}.xlsx'
            path = out_dir / filename
            bytes_written = _write_training_teacher_report_xlsx(report, path)
            job.file_path = str(path)
            job.file_name = filename
            result = {'ok': True, 'file_name': filename, 'bytes': bytes_written, 'summary': report.get('summary') or {}}
            action = 'academic.teacher_report.export_excel.async'
        else:
            raise ValueError(f'Unsupported teacher report job_type: {job.job_type}')

        job.status = 'completed'
        job.progress_current = 100
        job.progress_total = 100
        job.result_json = json_safe_value(result)
        job.error_message = None
        job.finished_at = datetime.utcnow()
        job.updated_at = datetime.utcnow()
        db.add(job)
        db.commit()
        try:
            log_audit(db, action=action, status='success', message=job.progress_label, user=None, target_type='academic_teacher_report_job', target_id=job.id, metadata=json_safe_value({'term_id': term_id, 'branch': branch, 'campus': campus, 'result': result}))
        except Exception:
            pass
        return json_safe_value(result)
    except Exception as exc:
        db.rollback()
        job = db.get(AcademicTeacherReportJob, job_id)
        if job:
            job.status = 'failed'
            job.progress_total = 100
            job.progress_label = 'Báo cáo giáo viên thất bại'
            public_message = 'Không thể hoàn tất báo cáo giáo viên. Vui lòng thử lại hoặc kiểm tra Nhật ký hoạt động.'
            job.error_message = public_message
            job.result_json = json_safe_value({'ok': False, 'code': 'ACADEMIC_TEACHER_REPORT_FAILED', 'message': public_message})
            job.finished_at = datetime.utcnow()
            job.updated_at = datetime.utcnow()
            db.add(job)
            db.commit()
            try:
                log_audit(db, action='academic.teacher_report.async', status='failed', error_type=AuditErrorType.SYSTEM_ERROR, message=str(exc), user=None, target_type='academic_teacher_report_job', target_id=job.id, metadata=json_safe_value({'job_type': job.job_type}))
            except Exception:
                pass
        return json_safe_value({'ok': False, 'error': 'academic_teacher_report_failed', 'code': 'ACADEMIC_TEACHER_REPORT_FAILED', 'message': 'Không thể hoàn tất báo cáo giáo viên. Vui lòng thử lại hoặc kiểm tra Nhật ký hoạt động.'})
    finally:
        db.close()


@celery_app.task(name='analytics_ingest_task')
def analytics_ingest_task(file_path: str | None = None, max_lines: int | None = None):
    """Ingest Open edX tracking.log incrementally outside HTTP requests."""
    from app.services.learning_analytics.analytics_core_service import LearningAnalyticsCoreService
    from app.services.audit_log import AuditErrorType, log_audit

    db = SessionLocal()
    try:
        result = LearningAnalyticsCoreService(db).run_ingest(file_path=file_path, max_lines=max_lines)
        try:
            log_audit(
                db,
                action='analytics.ingest.async',
                status='success',
                message='Ingest tracking log học online hoàn tất',
                user=None,
                target_type='learning_analytics',
                metadata=json_safe_value({'result': result, 'signals_only_not_violation': True}),
            )
        except Exception:
            pass
        return json_safe_value(result)
    except Exception as exc:
        db.rollback()
        try:
            log_audit(
                db,
                action='analytics.ingest.async',
                status='failed',
                error_type=AuditErrorType.SYSTEM_ERROR,
                message=str(exc),
                user=None,
                target_type='learning_analytics',
                metadata=json_safe_value({'file_path': file_path}),
            )
        except Exception:
            pass
        return json_safe_value({'ok': False, 'error': 'analytics_ingest_failed', 'message': str(exc)})
    finally:
        db.close()


@celery_app.task(name='analytics_class_recalculate_task')
def analytics_class_recalculate_task(job_id: str):
    """Recalculate online-learning signals for one class using the existing job table."""
    from app.models.academic import AcademicClassSyncJob
    from app.services.learning_analytics.analytics_core_service import LearningAnalyticsCoreService
    from app.services.audit_log import AuditErrorType, log_audit

    db = SessionLocal()
    try:
        job = db.get(AcademicClassSyncJob, job_id)
        if not job:
            return {'ok': False, 'error': 'job_not_found'}
        if job.status not in {'queued', 'running'}:
            return job.result_json or {'ok': job.status == 'completed', 'status': job.status}
        if job.job_type != 'learning_analytics_recalculate':
            raise RuntimeError(f'Unsupported analytics job_type: {job.job_type}')
        request = job.request_json if isinstance(job.request_json, dict) else {}
        course_id = str(request.get('course_id') or '').strip()
        username = str(request.get('username') or '').strip() or None
        if not course_id:
            raise RuntimeError('Thiếu course_id để tính lại học online')
        now = datetime.utcnow()
        job.status = 'running'
        job.started_at = job.started_at or now
        job.updated_at = now
        job.progress_current = 10
        job.progress_total = 100
        job.progress_label = 'Đang tính lại học online'
        db.add(job)
        db.commit()

        service = LearningAnalyticsCoreService(db)
        video_result = service.recalculate_course_video_progress(course_id=course_id, username=username, class_id=job.class_id)
        job.progress_current = 45
        job.progress_label = 'Đang tổng hợp theo Bài/Deadline'
        db.add(job)
        db.commit()
        session_result = service.recalculate_student_session_progress(class_id=job.class_id, course_id=course_id, username=username)
        job.progress_current = 75
        job.progress_label = 'Đang phân loại tín hiệu học online'
        db.add(job)
        db.commit()
        behavior_result = service.recalculate_learning_behavior(class_id=job.class_id, course_id=course_id, username=username)

        result = json_safe_value({
            'ok': True,
            'class_id': job.class_id,
            'course_id': course_id,
            'username': username,
            'video': video_result,
            'session': session_result,
            'behavior': behavior_result,
            'signals_only_not_violation': True,
        })
        job.status = 'completed'
        job.progress_current = 100
        job.progress_total = 100
        job.progress_label = 'Hoàn tất học online'
        job.result_json = result
        job.error_message = None
        job.finished_at = datetime.utcnow()
        job.updated_at = datetime.utcnow()
        db.add(job)
        db.commit()
        try:
            log_audit(
                db,
                action='analytics.learning_behavior.recalculate.async',
                status='success',
                message='Hoàn tất tính lại học online theo tín hiệu mềm',
                user=None,
                course_id=course_id,
                target_type='academic_class_sync_job',
                target_id=job.id,
                metadata=json_safe_value({'class_id': job.class_id, 'username': username, 'result': behavior_result, 'signals_only_not_violation': True}),
            )
        except Exception:
            pass
        return result
    except Exception as exc:
        db.rollback()
        job = db.get(AcademicClassSyncJob, job_id)
        if job:
            job.status = 'failed'
            job.progress_label = 'Tính lại học online thất bại'
            job.error_message = str(exc)[:4000]
            job.result_json = json_safe_value({'ok': False, 'message': job.error_message})
            job.finished_at = datetime.utcnow()
            job.updated_at = datetime.utcnow()
            db.add(job)
            db.commit()
            try:
                log_audit(db, action='analytics.learning_behavior.recalculate.async', status='failed', error_type=AuditErrorType.SYSTEM_ERROR, message=str(exc), user=None, target_type='academic_class_sync_job', target_id=job.id, metadata=json_safe_value({'class_id': job.class_id, 'signals_only_not_violation': True}))
            except Exception:
                pass
        return json_safe_value({'ok': False, 'error': 'analytics_class_recalculate_failed', 'message': str(exc)})
    finally:
        db.close()
