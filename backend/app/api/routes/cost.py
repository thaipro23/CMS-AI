from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.core.rbac import UserContext, ensure_course_access, require_permission
from app.schemas.cost import CostEstimateRequest, CostEstimateResponse, PricingResponse, CoursePolicyResponse, CoursePolicyUpdate
from app.schemas.generation import GenerateQuestionsRequest
from app.services.cost_control import CostControlService
from app.services.generation_planner import build_generation_plan
from app.services.pricing_service import OpenAIPricingService
from app.core.config import settings
from app.models.cost import BudgetPolicy
from app.models.question import Question
from app.services.audit_log import log_audit

router = APIRouter()


BANK_CHAPTER_POLICY_ID = '__bank_chapter_default__'

def _policy_scope(course_id: str) -> tuple[str, str]:
    # Bank-first UI stores the default quota for every Bài/Chapter here.
    if course_id in {BANK_CHAPTER_POLICY_ID, 'chapter', 'chapter_default'}:
        return 'chapter', 'default'
    return 'course', course_id


def _policy_course_id(scope: str, scope_id: str) -> str:
    return BANK_CHAPTER_POLICY_ID if scope == 'chapter' and scope_id == 'default' else scope_id


@router.post('/estimate', response_model=CostEstimateResponse)
async def estimate_cost(payload: CostEstimateRequest, db: Session = Depends(get_db), user: UserContext = Depends(require_permission('estimate_cost'))):
    ensure_course_access(user, payload.course_id)
    svc = CostControlService(db)

    # Preferred v24.3 path: estimate the exact Responses payload tokens for the
    # selected chunks/nodes/manual content before queueing the job.
    if payload.content or payload.chunk_ids or payload.node_ids:
        plan_payload = GenerateQuestionsRequest(
            course_id=payload.course_id,
            node_ids=payload.node_ids,
            question_count=payload.question_count,
            batch_size=payload.batch_size,
            content=payload.content,
            chunk_ids=payload.chunk_ids,
            requested_by='estimate',
            provider='openai',
            use_node_coverage=payload.use_node_coverage,
            difficulty_percentages=payload.difficulty_percentages.model_dump(),
        )
        plan = build_generation_plan(db, plan_payload)
        est = await svc.estimate_generation_plan_cost(
            course_id=payload.course_id,
            content=plan.content,
            work_items=plan.work_items,
            avg_output_tokens_per_question=payload.avg_output_tokens_per_question,
            refresh_pricing=payload.refresh_pricing,
        )
    else:
        # Compatibility fallback for older UI that only sends content_tokens.
        est = svc.estimate_generation_cost(
            course_id=payload.course_id,
            question_count=payload.question_count,
            content_tokens=payload.content_tokens,
            prompt_tokens=payload.prompt_tokens,
            schema_tokens=payload.schema_tokens,
            metadata_tokens=payload.metadata_tokens,
            avg_output_tokens_per_question=payload.avg_output_tokens_per_question,
        )

    log_audit(db, action='cost.estimate', status='success' if est.quota_ok else 'failed', error_type=None if est.quota_ok else 'user', message=est.quota_message, user=user, course_id=payload.course_id, target_type='cost_estimate', metadata={'question_count': payload.question_count, 'estimated_cost_usd': round(est.cost_usd, 6), 'token_source': est.token_source})

    return CostEstimateResponse(
        estimated_input_tokens=est.input_tokens,
        estimated_cached_input_tokens=est.cached_input_tokens,
        estimated_uncached_input_tokens=est.uncached_input_tokens,
        estimated_output_tokens=est.output_tokens,
        estimated_raw_cost_usd=round(est.raw_cost_usd, 6),
        estimated_cost_usd=round(est.cost_usd, 6),
        estimated_cost_vnd=round(est.cost_vnd, 0),
        safety_factor=settings.cost_safety_factor,
        model_name=settings.openai_model,
        pricing=est.pricing.as_dict() if est.pricing else None,
        token_source=est.token_source,
        quota_ok=est.quota_ok,
        quota_message=est.quota_message,
        difficulty_allocations=plan.difficulty_allocations if (payload.content or payload.chunk_ids or payload.node_ids) else [],
        estimated_output_tokens_per_question=est.estimated_output_tokens_per_question,
        output_calibration=est.output_calibration,
    )


@router.get('/policy', response_model=CoursePolicyResponse)
async def get_course_policy(course_id: str = Query(...), db: Session = Depends(get_db), user: UserContext = Depends(require_permission('estimate_cost'))):
    scope, scope_id = _policy_scope(course_id)
    if scope == 'course':
        ensure_course_access(user, course_id)
    policy = db.query(BudgetPolicy).filter(BudgetPolicy.scope == scope, BudgetPolicy.scope_id == scope_id).one_or_none()
    if policy is None:
        policy = BudgetPolicy(scope=scope, scope_id=scope_id, monthly_budget_usd=10.0, max_questions_per_course=100, max_questions_per_job=50, max_retry=2)
        db.add(policy)
        db.commit()
        db.refresh(policy)
    generated = db.query(Question).filter(Question.course_id == course_id).count() if scope == 'course' else 0
    return CoursePolicyResponse(
        course_id=_policy_course_id(scope, scope_id),
        monthly_budget_usd=policy.monthly_budget_usd,
        max_questions_per_course=policy.max_questions_per_course,
        max_questions_per_job=policy.max_questions_per_job,
        max_retry=policy.max_retry,
        generated_questions=generated,
        remaining_questions=max(0, policy.max_questions_per_course - generated),
    )


@router.patch('/policy', response_model=CoursePolicyResponse)
async def update_course_policy(payload: CoursePolicyUpdate, db: Session = Depends(get_db), user: UserContext = Depends(require_permission('manage_settings'))):
    scope, scope_id = _policy_scope(payload.course_id)
    if scope == 'course':
        ensure_course_access(user, payload.course_id)
    policy = db.query(BudgetPolicy).filter(BudgetPolicy.scope == scope, BudgetPolicy.scope_id == scope_id).one_or_none()
    if policy is None:
        policy = BudgetPolicy(scope=scope, scope_id=scope_id)
        db.add(policy)
    policy.monthly_budget_usd = payload.monthly_budget_usd
    policy.max_questions_per_course = payload.max_questions_per_course
    policy.max_questions_per_job = payload.max_questions_per_job
    policy.max_retry = payload.max_retry
    db.commit()
    log_audit(db, action='chapter_policy.update' if scope == 'chapter' else 'course_policy.update', status='success', message='Admin updated bank chapter generation limits' if scope == 'chapter' else 'Admin updated course generation limits', user=user, course_id=None if scope == 'chapter' else payload.course_id, target_type='chapter_policy' if scope == 'chapter' else 'course_policy', metadata={**payload.model_dump(), 'scope': scope, 'scope_id': scope_id})
    return await get_course_policy(_policy_course_id(scope, scope_id), db, user)


@router.get('/pricing/realtime', response_model=PricingResponse, dependencies=[Depends(require_permission('manage_settings'))])
async def realtime_pricing(
    model: str | None = Query(default=None, description='Default is current OPENAI_MODEL'),
    refresh: bool = Query(default=False, description='Fetch OpenAI pricing page instead of using cache'),
):
    pricing = await OpenAIPricingService().get_pricing(model or settings.openai_model, refresh=refresh)
    return pricing.as_dict()
