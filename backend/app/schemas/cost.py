from pydantic import BaseModel, Field, model_validator


class DifficultyPercentages(BaseModel):
    easy: float = Field(default=50, ge=0, le=100)
    medium: float = Field(default=30, ge=0, le=100)
    hard: float = Field(default=20, ge=0, le=100)

    @model_validator(mode='after')
    def at_least_one_positive(self):
        if (self.easy + self.medium + self.hard) <= 0:
            raise ValueError('At least one difficulty percentage must be greater than 0')
        return self

    def as_dict(self) -> dict[str, float]:
        return {'easy': self.easy, 'medium': self.medium, 'hard': self.hard}


class CostEstimateRequest(BaseModel):
    course_id: str
    question_count: int = Field(ge=1, le=10000)
    # v24.3 preferred path: send the same node/chunk/manual content selection as
    # Generate so backend can build the real Responses API payload and call
    # /v1/responses/input_tokens before queueing.
    content: str | None = None
    chunk_ids: list[str] | None = None
    node_ids: list[str] | None = None
    # v25.2 default: 12 keeps JSON shorter than one huge 50-question call, but
    # avoids the old 20 => 6+6+6+2 token waste.
    batch_size: int = Field(default=12, ge=1, le=50)
    use_node_coverage: bool = True
    difficulty_percentages: DifficultyPercentages = Field(default_factory=DifficultyPercentages)
    refresh_pricing: bool = False
    # Legacy/fallback fields kept for old frontend calls.
    content_tokens: int = Field(default=30000, ge=0)
    prompt_tokens: int = Field(default=2500, ge=0)
    schema_tokens: int = Field(default=1200, ge=0)
    metadata_tokens: int = Field(default=600, ge=0)
    avg_output_tokens_per_question: int = Field(default=320, ge=50)


class CostEstimateResponse(BaseModel):
    estimated_input_tokens: int
    estimated_cached_input_tokens: int = 0
    estimated_uncached_input_tokens: int = 0
    estimated_output_tokens: int
    estimated_raw_cost_usd: float = 0
    estimated_cost_usd: float
    estimated_cost_vnd: float
    safety_factor: float
    model_name: str
    pricing: dict | None = None
    token_source: str = 'local_estimate'
    quota_ok: bool
    quota_message: str
    difficulty_allocations: list[dict] = []
    estimated_output_tokens_per_question: float = 0
    output_calibration: dict | None = None


class PricingResponse(BaseModel):
    model: str
    input_price_per_1m: float
    cached_input_price_per_1m: float
    output_price_per_1m: float
    currency: str
    unit: str
    service_tier: str
    context: str
    source: str
    fetched_at: float | None = None
    fetched_at_iso: str | None = None
    note: str | None = None


class CoursePolicyResponse(BaseModel):
    course_id: str
    monthly_budget_usd: float
    max_questions_per_course: int
    max_questions_per_job: int
    max_retry: int
    generated_questions: int = 0
    remaining_questions: int = 0


class CoursePolicyUpdate(BaseModel):
    course_id: str
    monthly_budget_usd: float = Field(default=10, ge=0)
    max_questions_per_course: int = Field(default=200, ge=1, le=100000)
    max_questions_per_job: int = Field(default=50, ge=1, le=10000)
    max_retry: int = Field(default=2, ge=0, le=20)
