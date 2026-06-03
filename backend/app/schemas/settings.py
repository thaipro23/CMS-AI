from pydantic import BaseModel, Field


class ModelSettingsUpdate(BaseModel):
    model_provider: str = Field(default='openai', description='openai | local | auto')
    openai_model: str = 'gpt-5-mini'
    openai_api_mode: str = Field(default='responses', description='responses | chat_legacy')
    mock_llm: bool = True
    openai_api_key: str | None = Field(default=None, description='Environment-only secret; PATCH rejects non-empty values')


class OpenEdXSettingsUpdate(BaseModel):
    use_mock_openedx: bool = True
    openedx_base_url: str = 'http://studio.local.openedx.io'
    openedx_cms_base_url: str | None = None
    openedx_lms_base_url: str = 'http://local.openedx.io'
    openedx_oauth_base_url: str | None = None
    openedx_client_id: str | None = None
    openedx_client_secret: str | None = Field(default=None, description='Environment-only secret; PATCH rejects non-empty values')
    openedx_access_token: str | None = Field(default=None, description='Environment-only secret; PATCH rejects non-empty values')
    openedx_oauth_token_url: str = '/oauth2/access_token/'
    openedx_course_blocks_path: str = '/api/courses/v2/blocks/'
    openedx_publish_endpoint: str = '/api/ai-connector/v1/courses/{course_id}/problems'
    openedx_library_endpoint: str = '/api/ai-connector/v1/courses/{course_id}/libraries'
    openedx_library_import_endpoint: str = '/api/ai-connector/v1/libraries/{library_key}/problems'


class SsoSettingsUpdate(BaseModel):
    auth_mode: str = Field(default='demo', description='demo | jwt | openedx_sso')
    allow_demo_role_header: bool = True
    jwt_secret: str | None = Field(default=None, description='Environment-only secret; PATCH rejects non-empty values')


class WorkerSettingsUpdate(BaseModel):
    openai_parallel_enabled: bool = True
    openai_max_parallel_calls: int = Field(default=3, ge=1, le=8)
    openai_retry_max_attempts: int = Field(default=3, ge=1, le=8)
    openai_retry_base_seconds: float = Field(default=2.0, ge=0.1, le=60)
    openai_prompt_cache_warmup_enabled: bool = True
    generation_tail_batch_wait_enabled: bool = True


class CostSettingsUpdate(BaseModel):
    cost_input_price_per_1m: float = Field(default=0.25, ge=0)
    cost_cached_input_price_per_1m: float = Field(default=0.025, ge=0)
    cost_output_price_per_1m: float = Field(default=2.00, ge=0)
    cost_safety_factor: float = Field(default=1.5, ge=1)
    usd_to_vnd: float = Field(default=26342.0, gt=0)


class RuntimeSettingsUpdate(BaseModel):
    model: ModelSettingsUpdate
    openedx: OpenEdXSettingsUpdate
    sso: SsoSettingsUpdate
    cost: CostSettingsUpdate | None = None
    worker: WorkerSettingsUpdate | None = None
