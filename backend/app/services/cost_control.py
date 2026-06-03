from dataclasses import dataclass
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.core.config import settings
from app.models.cost import BudgetPolicy, UsageLog
from app.models.question import Question
from app.services.model_gateway import ModelGateway
from app.services.pricing_service import OpenAIPricingService, ModelPricing
from app.services.prompt_builder import build_question_prompt
from app.services.token_calibration import OutputTokenCalibrationService

USD_TO_VND = settings.usd_to_vnd


@dataclass
class CostEstimate:
    input_tokens: int
    cached_input_tokens: int
    output_tokens: int
    raw_cost_usd: float
    cost_usd: float
    cost_vnd: float
    quota_ok: bool
    quota_message: str
    pricing: ModelPricing | None = None
    token_source: str = 'local_estimate'
    output_calibration: dict | None = None
    estimated_output_tokens_per_question: float = 0

    @property
    def uncached_input_tokens(self) -> int:
        return max(self.input_tokens - self.cached_input_tokens, 0)


class CostControlService:
    def __init__(self, db: Session):
        self.db = db

    async def calculate_cost_usd(
        self,
        *,
        model_name: str,
        input_tokens: int,
        cached_input_tokens: int,
        output_tokens: int,
        apply_safety_factor: bool,
        refresh_pricing: bool = False,
    ) -> tuple[float, ModelPricing]:
        pricing = await OpenAIPricingService().get_pricing(model_name, refresh=refresh_pricing)
        cached = max(cached_input_tokens or 0, 0)
        total_input = max(input_tokens or 0, 0)
        uncached = max(total_input - cached, 0)
        raw_cost = (
            uncached / 1_000_000 * pricing.input_price_per_1m
            + cached / 1_000_000 * pricing.cached_input_price_per_1m
            + max(output_tokens or 0, 0) / 1_000_000 * pricing.output_price_per_1m
        )
        if apply_safety_factor:
            return raw_cost * settings.cost_safety_factor, pricing
        return raw_cost, pricing

    def estimate_generation_cost(
        self,
        course_id: str,
        question_count: int,
        content_tokens: int,
        prompt_tokens: int = 2500,
        schema_tokens: int = 1200,
        metadata_tokens: int = 600,
        avg_output_tokens_per_question: int = 320,
    ) -> CostEstimate:
        """Legacy synchronous estimate retained for old callers.

        v24.3 uses estimate_generation_plan_cost() for node/chunk generation.
        This fallback still applies safety_factor because it is an estimate.
        """
        input_tokens = content_tokens + prompt_tokens + schema_tokens + metadata_tokens
        output_tokens = question_count * avg_output_tokens_per_question
        raw_cost = (
            input_tokens / 1_000_000 * settings.cost_input_price_per_1m
            + output_tokens / 1_000_000 * settings.cost_output_price_per_1m
        )
        cost_usd = raw_cost * settings.cost_safety_factor
        cost_vnd = cost_usd * settings.usd_to_vnd
        quota_ok, quota_message = self.check_quota(course_id, question_count)
        return CostEstimate(input_tokens, 0, output_tokens, raw_cost, cost_usd, cost_vnd, quota_ok, quota_message, token_source='legacy_local_estimate', output_calibration={'source': 'legacy_request', 'tokens_per_question': avg_output_tokens_per_question}, estimated_output_tokens_per_question=avg_output_tokens_per_question)

    async def estimate_generation_plan_cost(
        self,
        *,
        course_id: str,
        content: str,
        work_items: list[dict],
        avg_output_tokens_per_question: int = 320,
        refresh_pricing: bool = False,
    ) -> CostEstimate:
        """Estimate the exact Responses input payload tokens before queuing.

        It calls /v1/responses/input_tokens once for each planned model call so
        the estimate matches the actual prompt + schema + system instruction that
        will be sent during generation. Output tokens are still projected because
        they do not exist until the model replies.
        """
        total_input = 0
        total_cached = 0
        total_output = 0
        token_source = 'responses/input_tokens'
        gateway = ModelGateway()
        output_calibrator = OutputTokenCalibrationService(self.db)
        output_breakdown: list[dict] = []
        for item in work_items:
            count = int(item.get('question_count') or 0)
            if count <= 0:
                continue
            item_content = str(item.get('content') or content or '')
            scope_title = item.get('scope_title')
            prompt = build_question_prompt(item_content, count, scope_title, item.get('target_difficulty'), difficulty_counts=item.get('difficulty_counts'))
            token_info = await gateway.count_responses_input_tokens_for_prompt(prompt)
            total_input += int(token_info.get('input_tokens') or 0)
            total_cached += int(token_info.get('cached_input_tokens') or 0)
            token_source = str(token_info.get('token_source') or token_source)

            # v25.9.7: output tokens are calibrated from actual usage.
            # /responses/input_tokens can count input, but output can only be
            # projected.  Use course/model/difficulty rolling averages instead
            # of the old fixed 320 tokens/question.  If the caller explicitly
            # supplied a high legacy value, keep the higher value as an override.
            target_difficulty = item.get('target_difficulty')
            projected = output_calibrator.estimate_output_for_item(
                model_name=settings.openai_model,
                course_id=course_id,
                difficulty=target_difficulty,
                question_count=count,
            )
            override_tokens = int(count * avg_output_tokens_per_question) if avg_output_tokens_per_question and avg_output_tokens_per_question > projected.tokens_per_question else 0
            item_output_tokens = max(projected.output_tokens, override_tokens)
            total_output += item_output_tokens
            output_breakdown.append({
                'difficulty': projected.difficulty,
                'question_count': count,
                'tokens_per_question': round(item_output_tokens / count, 2) if count else 0,
                'calibrated_tokens_per_question': round(projected.tokens_per_question, 2),
                'estimated_output_tokens': item_output_tokens,
                'source': 'request_override' if override_tokens else projected.source,
                'sample_count': projected.sample_count,
            })

        raw_cost, pricing = await self.calculate_cost_usd(
            model_name=settings.openai_model,
            input_tokens=total_input,
            cached_input_tokens=total_cached,
            output_tokens=total_output,
            apply_safety_factor=False,
            refresh_pricing=refresh_pricing,
        )
        safe_cost = raw_cost * settings.cost_safety_factor
        quota_ok, quota_message = self.check_quota(course_id, sum(max(int(item.get('question_count') or 0), 0) for item in work_items))
        return CostEstimate(
            input_tokens=total_input,
            cached_input_tokens=total_cached,
            output_tokens=total_output,
            raw_cost_usd=raw_cost,
            cost_usd=safe_cost,
            cost_vnd=safe_cost * settings.usd_to_vnd,
            quota_ok=quota_ok,
            quota_message=quota_message,
            pricing=pricing,
            token_source=token_source,
            output_calibration={
                'strategy': 'v25.9.7_rolling_output_tokens_per_question',
                'breakdown': output_breakdown,
                'note': 'Output tokens are projected from actual usage history by difficulty. Input tokens still use /v1/responses/input_tokens.',
            },
            estimated_output_tokens_per_question=round(total_output / max(sum(max(int(item.get('question_count') or 0), 0) for item in work_items), 1), 2),
        )

    def check_quota(self, course_id: str, question_count: int) -> tuple[bool, str]:
        policy = self._get_course_policy(course_id)
        if question_count > policy.max_questions_per_job:
            return False, f'Vượt giới hạn {policy.max_questions_per_job} câu/lần generate.'

        generated_count = self.db.query(func.count(Question.id)).filter(Question.course_id == course_id).scalar() or 0
        if generated_count + question_count > policy.max_questions_per_course:
            return False, f'Vượt quota course {policy.max_questions_per_course} câu. Cần admin/manager approve.'
        return True, 'OK'

    def hard_stop_or_raise(self, course_id: str, question_count: int, estimated_cost_usd_with_safety: float) -> None:
        ok, msg = self.check_quota(course_id, question_count)
        if not ok:
            raise ValueError(msg)

        policy = self._get_course_policy(course_id)
        spent = self.db.query(func.coalesce(func.sum(UsageLog.cost_usd), 0)).filter(UsageLog.course_id == course_id).scalar() or 0
        if spent + estimated_cost_usd_with_safety > policy.monthly_budget_usd:
            raise ValueError('Vượt monthly budget của course. Hard stop trước khi gọi model.')

    def log_usage(
        self,
        *,
        job_id: str | None,
        course_id: str,
        user_id: str,
        feature: str,
        model_provider: str,
        model_name: str,
        input_tokens: int,
        output_tokens: int,
        cost_usd: float,
        cached_input_tokens: int = 0,
        token_source: str | None = None,
        raw_usage_json: str | None = None,
        status: str = 'completed',
        raw_error: str | None = None,
    ) -> UsageLog:
        uncached_input_tokens = max(int(input_tokens or 0) - int(cached_input_tokens or 0), 0)
        usage = UsageLog(
            job_id=job_id,
            course_id=course_id,
            user_id=user_id,
            feature=feature,
            model_provider=model_provider,
            model_name=model_name,
            input_tokens=input_tokens,
            cached_input_tokens=cached_input_tokens,
            uncached_input_tokens=uncached_input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost_usd,
            cost_vnd=cost_usd * settings.usd_to_vnd,
            status=status,
            token_source=token_source,
            raw_usage_json=raw_usage_json,
            raw_error=raw_error,
        )
        self.db.add(usage)
        self.db.commit()
        return usage

    def _get_course_policy(self, course_id: str) -> BudgetPolicy:
        policy = self.db.query(BudgetPolicy).filter(
            BudgetPolicy.scope == 'course',
            BudgetPolicy.scope_id == course_id,
            BudgetPolicy.is_active == True,
        ).first()
        if policy:
            return policy
        default = BudgetPolicy(
            scope='course',
            scope_id=course_id,
            monthly_budget_usd=10.0,
            max_questions_per_course=settings.default_course_question_quota,
            max_questions_per_job=settings.default_job_question_limit,
            max_retry=settings.default_retry_limit,
        )
        self.db.add(default)
        self.db.commit()
        self.db.refresh(default)
        return default
