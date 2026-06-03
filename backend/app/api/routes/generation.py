from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.core.rbac import UserContext, ensure_course_access, require_permission
from app.schemas.generation import GenerateQuestionsRequest, GenerateQuestionsResponse
from app.services.cost_control import CostControlService
from app.models.job import GenerationJob
from app.services.generation_planner import build_generation_plan
from app.worker import generate_questions_task
from app.services.audit_log import log_audit

router = APIRouter()


@router.post('/generate', response_model=GenerateQuestionsResponse)
async def generate_questions(payload: GenerateQuestionsRequest, db: Session = Depends(get_db), user: UserContext = Depends(require_permission('generate_questions')), idempotency_key: str | None = Header(default=None, alias='Idempotency-Key')):
    ensure_course_access(user, payload.course_id)
    payload.requested_by = user.user_id
    idempotency_key = (idempotency_key or '').strip() or None
    if idempotency_key:
        existing = db.query(GenerationJob).filter(
            GenerationJob.course_id == payload.course_id,
            GenerationJob.requested_by == user.user_id,
            GenerationJob.idempotency_key == idempotency_key,
        ).first()
        if existing:
            return GenerateQuestionsResponse(
                job_id=existing.id,
                status=existing.status,
                estimated_cost_usd=round(existing.estimated_cost_usd or 0, 6),
                estimated_cost_vnd=round(existing.estimated_cost_vnd or 0, 0),
                message='Idempotency-Key đã tồn tại; trả lại generation job cũ để tránh tạo trùng và gọi GPT lại.',
                planned_batches=0,
                node_allocations=[],
                difficulty_allocations=[],
                topic_allocations=[],
            )
    plan = build_generation_plan(db, payload)
    if not plan.content.strip():
        log_audit(db, action='generation.request', status='failed', error_type='user', message='Không có nội dung để tạo câu hỏi. Cần sync course hoặc chọn chunk.', user=user, course_id=payload.course_id, target_type='generation_request', metadata={'question_count': payload.question_count})
        raise HTTPException(status_code=400, detail='Không có nội dung để tạo câu hỏi. Hãy đồng bộ học liệu hoặc chọn chunk trước.')

    cost_svc = CostControlService(db)
    est = await cost_svc.estimate_generation_plan_cost(
        course_id=payload.course_id,
        content=plan.content,
        work_items=plan.work_items,
    )
    try:
        # Hard stop uses estimate WITH safety factor to avoid accidental budget
        # overrun. Actual cost logged by worker does not use safety factor.
        cost_svc.hard_stop_or_raise(payload.course_id, payload.question_count, est.cost_usd)
    except ValueError as exc:
        log_audit(db, action='generation.hard_stop', status='failed', error_type='user', message=str(exc), user=user, course_id=payload.course_id, target_type='generation_request', metadata={'question_count': payload.question_count, 'estimated_cost_usd': est.cost_usd})
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    scope_title = plan.node_allocations[0]['title'] if plan.node_allocations else None
    job = GenerationJob(
        course_id=payload.course_id,
        lesson_id=payload.lesson_id,
        topic=scope_title,  # DB column kept for compatibility; value now means node/scope title.
        requested_by=user.user_id,
        question_count=payload.question_count,
        batch_size=min(payload.batch_size, 12),
        provider=payload.provider,
        model_name=est.pricing.model if est.pricing else 'gpt-5-mini',
        estimated_input_tokens=est.input_tokens,
        estimated_cached_input_tokens=est.cached_input_tokens,
        estimated_uncached_input_tokens=est.uncached_input_tokens,
        estimated_output_tokens=est.output_tokens,
        estimated_raw_cost_usd=est.raw_cost_usd,
        estimated_cost_usd=est.cost_usd,
        estimated_cost_vnd=est.cost_vnd,
        estimate_token_source=est.token_source,
        estimated_output_tokens_per_question=est.estimated_output_tokens_per_question,
        output_calibration_json=__import__('json').dumps(est.output_calibration or {}, ensure_ascii=False),
        idempotency_key=idempotency_key,
    )
    db.add(job)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        if idempotency_key:
            existing = db.query(GenerationJob).filter(GenerationJob.course_id == payload.course_id, GenerationJob.requested_by == user.user_id, GenerationJob.idempotency_key == idempotency_key).first()
            if existing:
                return GenerateQuestionsResponse(job_id=existing.id, status=existing.status, estimated_cost_usd=round(existing.estimated_cost_usd or 0, 6), estimated_cost_vnd=round(existing.estimated_cost_vnd or 0, 0), message='Idempotency-Key đã tồn tại; trả lại generation job cũ.', planned_batches=0, node_allocations=[], difficulty_allocations=[], topic_allocations=[])
        raise
    db.refresh(job)

    generate_questions_task.delay(job.id, plan.content, plan.work_items)
    log_audit(db, action='generation.enqueue', status='success', message='Đã đưa yêu cầu tạo câu hỏi vào hàng đợi', user=user, course_id=payload.course_id, target_type='generation_job', target_id=job.id, metadata={'question_count': payload.question_count, 'estimated_cost_usd': est.cost_usd, 'work_items': len(plan.work_items)})
    return GenerateQuestionsResponse(
        job_id=job.id,
        status=job.status,
        estimated_cost_usd=round(est.cost_usd, 6),
        estimated_cost_vnd=round(est.cost_vnd, 0),
        message='Đã đưa yêu cầu tạo câu hỏi vào hàng đợi. Estimate dùng /v1/responses/input_tokens; hard stop dùng safety_factor, actual cost không nhân safety_factor. Difficulty dùng Largest Remainder Method và bank tách theo Chapter + Difficulty.',
        planned_batches=len(plan.work_items),
        node_allocations=plan.node_allocations,
        difficulty_allocations=plan.difficulty_allocations,
        topic_allocations=[],
    )
