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


class GenerateQuestionsRequest(BaseModel):
    course_id: str
    lesson_id: str | None = None
    # v20: generation is scoped by Open edX nodes, not inferred topics.
    node_ids: list[str] | None = None
    question_count: int = Field(ge=1, le=10000, default=20)
    # v25.2: cost-aware difficulty grouping. 20 questions defaults to
    # 10 EASY + 6 MEDIUM + 4 HARD = 3 model calls, not 6+6+6+2.
    batch_size: int = Field(ge=1, le=50, default=12)
    content: str | None = None
    chunk_ids: list[str] | None = None
    requested_by: str = 'teacher'
    provider: str = 'openai'
    use_node_coverage: bool = True
    difficulty_percentages: DifficultyPercentages = Field(default_factory=DifficultyPercentages)
    # Deprecated compatibility fields. They are ignored in v20+.
    topic: str | None = None
    use_topic_coverage: bool | None = None


class GenerateQuestionsResponse(BaseModel):
    job_id: str
    status: str
    estimated_cost_usd: float
    estimated_cost_vnd: float
    message: str
    planned_batches: int = 1
    node_allocations: list[dict] = []
    difficulty_allocations: list[dict] = []
    topic_allocations: list[dict] = []  # deprecated compatibility alias
