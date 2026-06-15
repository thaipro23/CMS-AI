from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central application settings.

    v15 keeps all production-sensitive switches in env vars so the same codebase
    can run in mock/demo, API-first, hybrid and local-first modes.
    """

    model_config = SettingsConfigDict(env_file='.env', extra='ignore')

    app_env: str = 'dev'
    app_name: str = 'AI Learning Server for Open edX'
    app_version: str = '25.9.15.6.37-async-material-generate-publish-quiz'
    debug: bool = True
    auto_create_tables: bool = True  # dev convenience; production should use Alembic

    # Production hardening
    # Comma-separated origin whitelist. Never use '*' with credentials in production.
    cors_allowed_origins: str = 'http://localhost:3000,http://127.0.0.1:3000'
    metrics_enabled: bool = True
    metrics_token: str | None = None
    require_course_scope_in_production: bool = True
    # CMS session bridge: lets a user who is already logged into CMS/Studio
    # obtain an AI Server bearer token without re-entering credentials. The
    # bridge ticket is signed by the CMS connector plugin using the shared HMAC
    # secret and exchanged by the AI backend for a short-lived AI JWT.
    auth_cookie_secure: bool = True
    auth_cookie_samesite: str = 'lax'
    auth_cookie_domain: str | None = None
    auth_session_token_ttl_seconds: int = 8 * 60 * 60
    openedx_session_bridge_secret: str | None = None
    openedx_session_bridge_audience: str = 'ai-learning-server'
    openedx_session_bridge_issuer: str = 'openedx-ai-connector'


    database_url: str = 'postgresql+psycopg://ai_user:ai_password@postgres:5432/ai_openedx'
    test_database_url: str = 'sqlite+pysqlite:///:memory:'
    redis_url: str = 'redis://redis:6379/0'

    # v25.9.15.6.32 database scale foundation.
    # These protect the API from unbounded connection growth and runaway queries
    # when Bank Manager grows to hundreds of subjects and millions of questions.
    db_pool_size: int = 10
    db_max_overflow: int = 20
    db_pool_timeout: int = 30
    db_pool_recycle: int = 1800
    db_statement_timeout_ms: int = 5000
    # v25.9.15.6.34 dashboard summary cache. Dashboard reads ai_bank_chapter_stats
    # and small hierarchy tables only; Redis cache reduces repeated aggregates.
    bank_dashboard_cache_ttl_seconds: int = 45
    # v25.9.15.6.35 Bank Search Engine. Limit per group/result set.
    bank_search_max_results: int = 50

    # Object storage adapter. MinIO is dev/demo only unless your organization approves AGPL/commercial terms.
    storage_provider: str = 'local'  # local | s3 | azure | gcs | minio
    local_storage_path: str = '/tmp/ai-openedx-storage'
    minio_endpoint: str = 'minio:9000'
    minio_access_key: str = 'minioadmin'
    minio_secret_key: str = 'minioadmin'
    minio_bucket: str = 'ai-openedx'

    # Model gateway
    openai_api_key: str | None = None
    openai_model: str = 'gpt-5-mini'
    openai_api_mode: str = 'responses'  # responses | chat_legacy
    mock_llm: bool = True
    model_provider: str = 'openai'  # openai | local | auto
    local_openai_base_url: str = 'http://vllm:8000/v1'
    llm_timeout_seconds: int = 90
    # v25.9.8 controlled parallel GPT calls. Keep defaults conservative to avoid 429 storms.
    openai_parallel_enabled: bool = True
    openai_max_parallel_calls: int = 3
    openai_retry_max_attempts: int = 3
    openai_retry_base_seconds: float = 2.0
    openai_rate_limit_respect_headers: bool = True
    # Run one request per prompt_cache_key first, then parallelize the rest.
    # This sacrifices a little latency but maximizes cached input for later batches.
    openai_prompt_cache_warmup_enabled: bool = True
    generation_tail_batch_wait_enabled: bool = True

    # v25.9.14.5 stable family reconciliation. Planning uses concept metadata
    # already produced during extraction/generation and never sends approved
    # questions to GPT again.
    family_plan_reconcile_on_preview: bool = True
    family_plan_require_all_approved: bool = True
    family_plan_hard_duplicate_guard: bool = True

    # Cost governance
    cost_input_price_per_1m: float = 0.25
    cost_cached_input_price_per_1m: float = 0.025
    cost_output_price_per_1m: float = 2.00
    cost_safety_factor: float = 1.5
    usd_to_vnd: float = 26342.0
    default_course_question_quota: int = 200
    default_job_question_limit: int = 50
    default_retry_limit: int = 2
    global_monthly_budget_usd: float = 100.0

    # Open edX integration
    use_mock_openedx: bool = True
    # Backward-compatible alias: CMS/Studio base URL for connector endpoints.
    openedx_base_url: str = 'http://studio.local.openedx.io'
    # Split hosts because Tutor usually serves OAuth/Course Blocks from LMS, while
    # Studio content/publish connector endpoints live on CMS/Studio.
    openedx_cms_base_url: str | None = None
    openedx_lms_base_url: str = 'http://local.openedx.io'
    openedx_oauth_base_url: str | None = None
    # Authoring MFE base URL for Studio library deep links shown in AI Server /export.
    # If omitted, AI Server derives it from OPENEDX_CMS_BASE_URL, e.g. studio.local.openedx.io -> apps.local.openedx.io/authoring.
    openedx_authoring_mfe_base_url: str | None = None
    openedx_client_id: str | None = None
    openedx_client_secret: str | None = None
    openedx_access_token: str | None = None
    openedx_oauth_token_url: str = '/oauth2/access_token/'
    openedx_course_blocks_path: str = '/api/courses/v2/blocks/'
    # Studio connector endpoint runs inside CMS/Studio and can read draft content, old problems and assets.
    # Keep enabled for Tutor/local pilot; if unavailable, AI Server falls back to Course Blocks API.
    openedx_studio_content_endpoint: str = '/api/ai-connector/v1/courses/{course_id}/studio-content'
    openedx_prefer_studio_content: bool = True
    openedx_course_metadata_path: str = '/api/courses/v1/courses/{course_id}/'
    openedx_publish_endpoint: str = '/api/ai-connector/v1/courses/{course_id}/problems'  # legacy direct-to-unit endpoint
    openedx_library_endpoint: str = '/api/ai-connector/v1/courses/{course_id}/libraries'
    openedx_library_import_endpoint: str = '/api/ai-connector/v1/libraries/{library_key}/problems'
    openedx_library_verify_endpoint: str = '/api/ai-connector/v1/libraries/{library_key}/problems/verify'
    openedx_library_delete_endpoint: str = '/api/ai-connector/v1/libraries/{library_key}/problems/delete'
    # CMS Quiz Node Creator. This endpoint runs inside Studio/CMS and
    # creates real draft XBlocks. It must fail loudly if modulestore create_child
    # is unavailable; AI Server must not fake quiz creation in production.
    openedx_quiz_node_create_endpoint: str = '/api/ai-connector/v1/courses/{course_id}/quiz-nodes'
    # v25.9.14.6: create native Ulmo ItemBankBlock Problem Banks inside a Studio Unit.
    # The CMS connector creates course-local ProblemBlock children through
    # sync_library_content and returns success only after exact upstream verification.
    openedx_problem_bank_insert_endpoint: str = '/api/ai-connector/v1/courses/{course_id}/problem-banks'
    # Force-save custom timed-practice config after Quiz node creation.
    # This endpoint lives in the LMS unit-reset plugin and accepts the same HMAC headers.
    openedx_quiz_timer_config_upsert_endpoint: str = '/api/unit-reset/v1/quiz-config/upsert'
    openedx_request_timeout_seconds: int = 30
    # Server-to-server HMAC used by the AI Server when calling the CMS connector plugin.
    # The same value must be set in the CMS container as AI_CONNECTOR_HMAC_SECRET.
    openedx_connector_hmac_secret: str | None = None
    openedx_connector_hmac_skew_seconds: int = 300
    # SSRF guard for assets/transcripts downloaded during sync. Comma-separated extra hosts.
    openedx_allowed_download_hosts: str = ''
    openedx_asset_max_bytes: int = 15 * 1024 * 1024
    openedx_transcript_max_bytes: int = 2 * 1024 * 1024

    # Auth/RBAC. Demo mode uses X-User-* headers. Production should use SSO/JWT validation.
    auth_mode: str = 'demo'  # demo | jwt | openedx_sso
    jwt_secret: str = Field(default='dev_secret_change_me')
    jwt_algorithm: str = 'HS256'
    jwt_issuer: str = 'ai-learning-server'
    jwt_audience: str = 'ai-learning-server-api'
    allow_demo_role_header: bool = True
    # One-time RBAC bootstrap guard. Production bootstrap is disabled unless this token is set and supplied via X-RBAC-Bootstrap-Token.
    rbac_bootstrap_token: str | None = None

    # Worker behavior
    task_always_eager: bool = False
    generation_batch_size: int = 50
    bank_operation_job_ttl_days: int = 30

    # v25.9.15.6.37 async material/generate/publish/quiz safety limits.
    max_upload_bytes: int = 50 * 1024 * 1024
    max_pdf_pages: int = 300
    max_pptx_slides: int = 300
    max_docx_paragraphs: int = 10000
    max_docx_tables: int = 500
    max_xlsx_sheets: int = 20
    max_xlsx_rows_per_sheet: int = 5000
    max_csv_rows: int = 50000
    max_zip_uncompressed_bytes: int = 200 * 1024 * 1024
    max_zip_members: int = 5000
    max_extracted_chars: int = 2_000_000

    # Advanced file extraction. Keep OCR disabled by default because it needs
    # Tesseract/Poppler system packages and can be slow on large scanned files.
    file_ocr_enabled: bool = False
    file_ocr_language: str = 'vie+eng'
    file_ocr_max_pages: int = 20
    # Tesseract default page segmentation often reads only big headings on screenshots/PDF scans.
    # PSM 6 treats the rendered page as a uniform text block and captures smaller body text better.
    file_ocr_tesseract_config: str = '--oem 3 --psm 6'
    pptx_extract_speaker_notes: bool = True
    pptx_ocr_images_enabled: bool = False


PRODUCTION_ENVS = {'prod', 'production'}


def is_production() -> bool:
    return (settings.app_env or '').lower().strip() in PRODUCTION_ENVS


def cors_origin_list() -> list[str]:
    raw = settings.cors_allowed_origins or ''
    return [item.strip().rstrip('/') for item in raw.split(',') if item.strip()]


def validate_security_settings() -> None:
    """Fail closed when production security switches are unsafe.

    This is intentionally strict. A misconfigured production container should not
    silently fall back to demo auth, mock Open edX, mock LLM, wildcard CORS, or a
    runtime-persisted secret.
    """
    if not is_production():
        return

    errors: list[str] = []
    if settings.debug:
        errors.append('DEBUG=false is required in production')
    if settings.auto_create_tables:
        errors.append('AUTO_CREATE_TABLES=false is required in production; run Alembic migrations instead')
    if (settings.auth_mode or '').lower().strip() not in {'jwt', 'openedx_sso'}:
        errors.append('AUTH_MODE must be jwt or openedx_sso in production')
    if settings.allow_demo_role_header:
        errors.append('ALLOW_DEMO_ROLE_HEADER=false is required in production')
    if not settings.jwt_secret or settings.jwt_secret == 'dev_secret_change_me' or settings.jwt_secret.startswith('CHANGE_ME') or len(settings.jwt_secret) < 32:
        errors.append('JWT_SECRET must be a real strong secret with at least 32 characters in production')
    if not settings.jwt_issuer:
        errors.append('JWT_ISSUER is required in production')
    if not settings.jwt_audience:
        errors.append('JWT_AUDIENCE is required in production')
    if settings.use_mock_openedx:
        errors.append('USE_MOCK_OPENEDX=false is required in production')
    if settings.mock_llm:
        errors.append('MOCK_LLM=false is required in production')
    if not settings.family_plan_reconcile_on_preview:
        errors.append('FAMILY_PLAN_RECONCILE_ON_PREVIEW=true is required in production')
    if not settings.family_plan_require_all_approved:
        errors.append('FAMILY_PLAN_REQUIRE_ALL_APPROVED=true is required in production')
    if not settings.family_plan_hard_duplicate_guard:
        errors.append('FAMILY_PLAN_HARD_DUPLICATE_GUARD=true is required in production')
    origins = cors_origin_list()
    if not origins or '*' in origins:
        errors.append('CORS_ALLOWED_ORIGINS must be an explicit comma-separated whitelist in production')
    if settings.metrics_enabled and (not settings.metrics_token or settings.metrics_token.startswith('CHANGE_ME') or len(settings.metrics_token) < 32):
        errors.append('METRICS_TOKEN with a real value of at least 32 characters is required when /metrics is enabled in production')
    if settings.database_url.startswith('sqlite'):
        errors.append('DATABASE_URL must point to PostgreSQL in production')
    if 'CHANGE_ME' in settings.database_url:
        errors.append('DATABASE_URL still contains CHANGE_ME placeholder')
    if settings.db_pool_size < 1:
        errors.append('DB_POOL_SIZE must be at least 1 in production')
    if settings.db_max_overflow < 0:
        errors.append('DB_MAX_OVERFLOW must be at least 0 in production')
    if settings.db_pool_timeout < 1:
        errors.append('DB_POOL_TIMEOUT must be at least 1 second in production')
    if settings.db_statement_timeout_ms < 1000:
        errors.append('DB_STATEMENT_TIMEOUT_MS should be at least 1000ms in production')
    if not settings.openai_api_key or settings.openai_api_key.startswith('CHANGE_ME'):
        errors.append('OPENAI_API_KEY is required in production when MOCK_LLM=false')
    if not settings.openedx_client_id or settings.openedx_client_id.startswith('CHANGE_ME'):
        errors.append('OPENEDX_CLIENT_ID is required in production')
    if not settings.openedx_client_secret or settings.openedx_client_secret.startswith('CHANGE_ME'):
        errors.append('OPENEDX_CLIENT_SECRET is required in production')
    if not settings.openedx_connector_hmac_secret or settings.openedx_connector_hmac_secret.startswith('CHANGE_ME') or len(settings.openedx_connector_hmac_secret) < 32:
        errors.append('OPENEDX_CONNECTOR_HMAC_SECRET with a real value of at least 32 characters is required in production')
    if settings.auth_mode.lower().strip() == 'openedx_sso':
        bridge_secret = settings.openedx_session_bridge_secret or settings.openedx_connector_hmac_secret
        if not bridge_secret or str(bridge_secret).startswith('CHANGE_ME') or len(str(bridge_secret)) < 32:
            errors.append('OPENEDX_SESSION_BRIDGE_SECRET or OPENEDX_CONNECTOR_HMAC_SECRET is required for AUTH_MODE=openedx_sso')
    if errors:
        raise RuntimeError('Unsafe production configuration: ' + '; '.join(errors))


settings = Settings()
