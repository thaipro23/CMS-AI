import json
import re
from urllib.parse import quote, urlsplit, urlunsplit

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def authenticated_redis_url(url: str, *, password: str | None = None, username: str | None = None) -> str:
    """Attach Redis credentials without requiring them to be baked into REDIS_URL."""
    raw = (url or '').strip() or 'redis://redis:6379/0'
    parts = urlsplit(raw)
    if parts.password:
        return raw
    secret = (password or '').strip()
    if not secret:
        return raw
    user = (username if username is not None else parts.username) or ''
    auth = f'{quote(user, safe="")}:{quote(secret, safe="")}' if user else f':{quote(secret, safe="")}'
    host = parts.hostname or 'redis'
    port = f':{parts.port}' if parts.port else ''
    path = parts.path or '/0'
    return urlunsplit((parts.scheme or 'redis', f'{auth}@{host}{port}', path, parts.query, parts.fragment))


class Settings(BaseSettings):
    """Central application settings.

    v15 keeps all production-sensitive switches in env vars so the same codebase
    can run in mock/demo, API-first, hybrid and local-first modes.
    """

    model_config = SettingsConfigDict(env_file='.env', extra='ignore')

    app_env: str = 'dev'
    app_name: str = 'AI Learning Server for Open edX'
    app_version: str = '25.9.16.7.2.64.16.5.7.2.18'
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
    # Explicit UAT-only escape hatch for HTTP environments. Never enable in production.
    allow_insecure_uat_http: bool = False
    auth_cookie_samesite: str = 'lax'
    auth_cookie_domain: str | None = None
    auth_session_token_ttl_seconds: int = 2 * 60 * 60
    openedx_session_bridge_max_age_seconds: int = 60
    auth_exchange_rate_limit_per_minute: int = 20
    auth_exchange_ticket_rate_limit_per_minute: int = 3
    openedx_session_bridge_secret: str | None = None
    openedx_session_bridge_audience: str = 'ai-learning-server'
    openedx_session_bridge_issuer: str = 'openedx-ai-connector'


    database_url: str = 'postgresql+psycopg://ai_user:ai_password@postgres:5432/ai_openedx'
    test_database_url: str = 'sqlite+pysqlite:///:memory:'
    redis_url: str = 'redis://redis:6379/0'
    redis_password: str | None = None
    redis_user: str | None = None

    @model_validator(mode='after')
    def _apply_redis_auth(self):
        url = authenticated_redis_url(self.redis_url, password=self.redis_password, username=self.redis_user)
        if url != self.redis_url:
            object.__setattr__(self, 'redis_url', url)
        return self

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

    # Persistent artifacts. Production FPL uses the external shared MinIO VM;
    # LOCAL_STORAGE_PATH remains available for caches, temporary work and
    # backward-compatible reads of files created before the cut-over.
    storage_provider: str = 'local'  # local | minio
    local_storage_path: str = '/app/.runtime'
    minio_endpoint: str = 'minio:9000'
    minio_access_key: str = 'minioadmin'
    minio_secret_key: str = 'minioadmin'
    minio_bucket: str = 'ai-openedx'
    minio_secure: bool = False
    minio_region: str | None = None
    minio_cert_check: bool = True
    # Production must pre-create the private bucket and keep this false. The
    # switch exists only for an isolated developer MinIO instance.
    minio_auto_create_bucket: bool = False

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
    # Optional server-to-server route to Studio/CMS that bypasses the public
    # Cloudflare/Ingress edge. Keep Host set to the public Studio hostname.
    openedx_cms_internal_base_url: str | None = None
    openedx_cms_host_header: str | None = None
    # Canonical owner of the single shared Question Bank Content Library.
    # Physical delivery Courses may belong to FPL/FPS/FBS/... independently.
    openedx_library_org: str = 'FPT'
    openedx_lms_base_url: str = 'http://local.openedx.io'
    openedx_oauth_base_url: str | None = None
    # Authoring MFE base URL for Studio library deep links shown in AI Server /export.
    # If omitted, AI Server derives it from OPENEDX_CMS_BASE_URL, e.g. studio.local.openedx.io -> apps.local.openedx.io/authoring.
    openedx_authoring_mfe_base_url: str | None = None
    # Backward-compatible alias used by older deployments. Prefer OPENEDX_AUTHORING_MFE_BASE_URL.
    openedx_mfe_base_url: str | None = None
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

    # v25.9.16 Academic AP / Student Management integration.
    # AP credentials are deployment secrets and must come from env, never from source.
    # Canonical v25.9.16.5.8 runtime gateway: AI Server talks to the
    # existing openedx_connector_plugin on the LMS Django host. The older
    # OPENEDX_STUDENT_INSIGHT_* names remain as deployment aliases only.
    openedx_connector_base_url: str | None = None
    openedx_connector_users_resolve_endpoint: str = '/api/ai-connector/v1/users/resolve'
    openedx_connector_course_search_endpoint: str = '/api/ai-connector/v1/courses/search'
    openedx_connector_class_analytics_endpoint: str = '/api/ai-connector/v1/class-analytics'
    openedx_connector_enrollment_enroll_endpoint: str = '/api/ai-connector/v1/course-enrollment/enroll'
    openedx_connector_enrollment_remove_endpoint: str = '/api/ai-connector/v1/course-enrollment/remove'
    openedx_connector_default_enrollment_mode: str = 'audit'
    openedx_connector_client_id: str = 'ai-server'
    openedx_connector_timeout_seconds: int = 30
    openedx_connector_max_batch_size: int = 100

    # Backward-compatible aliases for old env files. Do not use these for new
    # deployments; prefer OPENEDX_CONNECTOR_BASE_URL and OPENEDX_CONNECTOR_HMAC_SECRET.
    openedx_student_insight_base_url: str | None = None
    openedx_student_insight_users_resolve_endpoint: str = '/api/ai-student-insight/v1/users/resolve'
    openedx_student_insight_course_search_endpoint: str = '/api/ai-student-insight/v1/courses/search'
    openedx_student_insight_class_analytics_endpoint: str = '/api/ai-student-insight/v1/class-analytics'
    openedx_student_insight_enrollment_enroll_endpoint: str = '/api/ai-student-insight/v1/course-enrollment/enroll'
    openedx_student_insight_default_enrollment_mode: str = 'audit'
    academic_auto_enroll_after_cms_sync: bool = True
    academic_auto_create_cms_users: bool = True
    academic_auto_add_teachers_to_course: bool = True
    # Optional physical Course-org hints. Full stored course-v1 IDs remain the
    # source of truth; these settings are only used for suggestions/auto-map.
    # Example: {"poly":"FPL","ptcd":"FPS"}
    academic_openedx_org_by_branch: str = ''
    academic_default_openedx_course_org: str | None = None
    # v25.9.16.5.0 full Student Progress flow. When a class has no explicit
    # Course CMS mapping yet, the worker may safely create a subject-term mapping
    # only if the exact suggested course-v1:{ORG}+{SUBJECT}+{TERM} exists once.
    # This keeps user creation independent from course mapping, while still
    # allowing one-click production sync for already-created CMS courses.
    academic_auto_map_course_before_cms_sync: bool = True
    academic_full_sync_learning_after_enrollment: bool = True
    # Maximum roster size processed by one class-level CMS sync. Connector calls
    # are still chunked by OPENEDX_CONNECTOR_MAX_BATCH_SIZE.
    academic_class_sync_max_students: int = 5000
    academic_learning_low_progress_threshold_percent: float = 50.0
    academic_learning_low_grade_threshold_percent: float = 50.0
    # v25.9.16.7.2.64.14 UAT-only destructive cleanup for wrong RollNumber identity mapping.
    # Keep this disabled in real production. Mutation also requires the exact
    # confirmation phrase in the request body.
    academic_identity_cleanup_allow_destructive: bool = False
    academic_identity_cleanup_confirm_phrase: str = 'DELETE_WRONG_UAT_IDENTITY'
    openedx_courses_search_endpoint: str = '/api/courses/v1/courses/'
    openedx_student_insight_client_id: str = 'ai-server'
    openedx_student_insight_shared_secret: str | None = None
    openedx_student_insight_timeout_seconds: int = 30
    openedx_student_insight_max_batch_size: int = 100

    # v25.9.16.6.3 Learning Behavior Analytics / Aspects-lite.
    # AI Server reads a mounted Open edX tracking.log incrementally. It never
    # scans the full log from request handlers and every result is a soft signal,
    # not a disciplinary conclusion.
    openedx_tracking_log_path: str = '/openedx-data/lms/logs/tracking.log'
    analytics_ingest_enabled: bool = True
    analytics_ingest_scheduler_enabled: bool = True
    analytics_ingest_interval_seconds: int = 60
    analytics_max_lines_per_run: int = 50000
    analytics_recalculate_max_students_per_job: int = 500
    analytics_dashboard_max_page_size: int = 200
    analytics_video_complete_threshold: float = 0.9
    analytics_suspicious_watch_ratio: float = 0.25
    analytics_max_passive_segment_seconds: int = 600
    analytics_enable_problem_correlation: bool = True
    analytics_snapshot_stale_hours: int = 168
    # v25.9.16.7.2.4 production-test safety gates for analytics operations.
    analytics_backfill_max_jobs_per_request: int = 25
    analytics_backfill_max_active_jobs: int = 20
    analytics_recalculate_enqueue_cooldown_seconds: int = 300
    # v25.9.16.7.2.64.14 post-ingest orchestrator. Ingest may run every
    # minute, but recalculation must stay debounced and class-scoped so a
    # production term with thousands of enrollments does not rebuild all
    # analytics snapshots on every scheduler tick.
    analytics_post_ingest_recalculate_enabled: bool = True
    analytics_post_ingest_recalculate_cooldown_seconds: int = 900
    analytics_post_ingest_recalculate_max_jobs_per_run: int = 10
    analytics_ingest_enqueue_cooldown_seconds: int = 120
    analytics_export_max_rows: int = 50000
    analytics_production_min_events: int = 1
    analytics_production_min_snapshots: int = 1
    analytics_pilot_sample_limit: int = 5
    # v25.9.16.7.2.4 rollout/monitoring controls. These are env-only guards
    # to avoid creating rollout tables while still allowing safe production rollout.
    analytics_rollout_enabled: bool = True
    analytics_rollout_mode: str = 'production'  # off | pilot | production
    analytics_rollout_campuses: str = ''
    analytics_rollout_branches: str = ''
    analytics_rollout_class_ids: str = ''
    analytics_rollout_course_ids: str = ''
    analytics_rollout_allow_backfill: bool = True
    analytics_rollout_allow_export: bool = True
    analytics_monitoring_stale_ingest_seconds: int = 900
    analytics_monitoring_stuck_job_minutes: int = 60
    analytics_monitoring_snapshot_stale_hours: int = 168
    analytics_monitoring_warning_active_jobs: int = 10
    # v25.9.16.7.2.64.14 Bank Quiz Final Test Production QA.
    # These are operational targets only; they drive admin SLA badges and do
    # not block ingest/recalculate jobs. Keep them conservative for UAT.
    analytics_sla_ingest_target_seconds: int = 300
    analytics_sla_snapshot_target_seconds: int = 3600
    analytics_sla_max_queued_jobs: int = 50
    analytics_sla_max_failed_jobs_last_hour: int = 0
    analytics_sla_class_gap_limit: int = 20


    academic_ap_sync_enabled: bool = True
    academic_ap_api_base_url: str = 'https://api_v2.poly.edu.vn'
    # Subject catalog source of truth. Discovery always calls this endpoint with
    # branch=poly and the selected term_name. The requested UI branch is retained
    # as metadata only because AP's ptcd catalog has historically been noisy.
    academic_ap_get_course_endpoint: str = '/get-course'
    academic_ap_api_key: str | None = None
    academic_ap_request_timeout_seconds: int = 60
    # TLS verification mode for AP integrations other than api_v2.poly.edu.vn.
    # api_v2.poly.edu.vn is an approved host-specific exception and always uses
    # verify=False because its served certificate currently mismatches the hostname.
    # strict: verify CA chain + hostname (default for every other host).
    # chain_only: verify CA chain but skip hostname check.
    # off: disable TLS verification for the configured AP host.
    academic_ap_tls_mode: str = 'strict'
    # Prevent AP sync from bloating the DB. In production, empty AP classes
    # (no valid student username in student/students array) are ignored and do
    # not create subject/class/teacher/student rows. The /get-course catalog is
    # used for discovery; subjects are persisted only when required by the flow.
    academic_ap_skip_empty_classes: bool = True
    academic_ap_import_catalog_subjects: bool = False
    # Cache the AP /get-course discovery response into a local JSON file so one
    # sync run does not repeatedly download the same term catalog.
    academic_ap_get_course_file_cache_enabled: bool = True
    academic_ap_get_course_file_cache_dir: str = '/tmp/ai-server-ap-cache/get-course'
    academic_ap_get_course_file_cache_ttl_seconds: int = 86400
    academic_ap_get_course_file_cache_refresh: bool = False
    academic_ap_subject_codes: str = ''

    openedx_request_timeout_seconds: int = 30
    # Bounded retry is used only for idempotent connector operations.
    openedx_retry_max_attempts: int = 4
    openedx_retry_base_seconds: float = 2.0
    openedx_retry_max_seconds: float = 60.0
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
    celery_task_acks_late: bool = True
    celery_task_reject_on_worker_lost: bool = True
    celery_worker_prefetch_multiplier: int = 1
    celery_worker_max_tasks_per_child: int = 25
    celery_worker_max_memory_per_child_kb: int = 600000
    celery_result_expires_seconds: int = 86400
    celery_broker_visibility_timeout_seconds: int = 7200
    celery_default_soft_time_limit_seconds: int = 1500
    celery_default_time_limit_seconds: int = 1800
    academic_teacher_report_sync_export_max_teachers: int = 20
    academic_teacher_report_sync_export_max_students: int = 1000
    academic_teacher_report_file_retention_hours: int = 48

    # Batch 35 — Udemy production hardening. These limits are deployment knobs,
    # not user input, and are validated for hardened environments below.
    academic_udemy_import_max_files: int = 50
    academic_udemy_import_max_file_bytes: int = 20 * 1024 * 1024
    academic_udemy_import_max_total_bytes: int = 200 * 1024 * 1024
    academic_udemy_import_max_rows: int = 300_000
    academic_udemy_xlsx_max_entries: int = 10_000
    academic_udemy_xlsx_max_uncompressed_bytes: int = 400 * 1024 * 1024
    academic_udemy_xlsx_max_compression_ratio: int = 200
    academic_udemy_upload_rate_limit_per_minute: int = 6
    academic_udemy_file_retention_hours: int = 72
    academic_udemy_export_file_retention_hours: int = 48
    academic_udemy_sync_export_max_rows: int = 5_000
    academic_udemy_worker_max_retries: int = 3
    academic_udemy_cleanup_interval_seconds: int = 6 * 60 * 60
    # Material upload extraction is heavy and must run as a background job by
    # default. Keep the inline switch only as an emergency fallback for local
    # debugging; production should leave it false and watch the operation job.
    bank_material_extract_inline_enabled: bool = False

    # Avoid repeatedly refreshing the same AP term/block master data while a
    # sync run loops over many /get-data-cms subject responses. If AP returns a
    # different term/block signature we still update immediately; otherwise this
    # TTL controls the next idempotent verification window.
    academic_ap_term_block_refresh_ttl_seconds: int = 3600

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
    # v25.9.15.6.38.5.3: Word files created from scans often contain one image per page.
    # When FILE_OCR_ENABLED=true, OCR those embedded images before accepting/rejecting the upload.
    docx_ocr_images_enabled: bool = True
    docx_ocr_max_images: int = 0  # 0 = use FILE_OCR_MAX_PAGES
    material_upload_preflight_enabled: bool = True

    # v25.9.16.3.6 Bank material cleanup policy. Unused/draft/failed
    # materials are hard-deleted immediately. Audit-sensitive deleted materials
    # remain lightweight tombstones for this retention window before admin purge.
    bank_material_deleted_retention_days: int = 30
    bank_material_cleanup_default_limit: int = 500
    bank_material_hard_delete_unused_enabled: bool = True
    bank_material_purge_deleted_files_enabled: bool = True


PRODUCTION_ENVS = {'prod', 'production'}
UAT_ENVS = {'uat', 'staging'}


def deployment_env() -> str:
    return (settings.app_env or '').lower().strip()


def is_production() -> bool:
    return deployment_env() in PRODUCTION_ENVS


def is_uat() -> bool:
    return deployment_env() in UAT_ENVS


def is_hardened_deployment() -> bool:
    return is_production() or is_uat()


def cors_origin_list() -> list[str]:
    raw = settings.cors_allowed_origins or ''
    return [item.strip().rstrip('/') for item in raw.split(',') if item.strip()]


def validate_security_settings() -> None:
    """Fail closed when production security switches are unsafe.

    This is intentionally strict. A misconfigured production container should not
    silently fall back to demo auth, mock Open edX, mock LLM, wildcard CORS, or a
    runtime-persisted secret.
    """
    if not is_hardened_deployment():
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
    if not settings.auth_cookie_secure:
        if is_production():
            errors.append('AUTH_COOKIE_SECURE=true is required in production')
        elif not settings.allow_insecure_uat_http:
            errors.append('AUTH_COOKIE_SECURE=false in UAT requires ALLOW_INSECURE_UAT_HTTP=true')
    if (settings.auth_cookie_samesite or '').lower().strip() not in {'lax', 'strict'}:
        errors.append('AUTH_COOKIE_SAMESITE must be lax or strict in production')
    if settings.auth_session_token_ttl_seconds < 900 or settings.auth_session_token_ttl_seconds > 7200:
        errors.append('AUTH_SESSION_TOKEN_TTL_SECONDS must be between 900 and 7200 seconds in production')
    if settings.openedx_session_bridge_max_age_seconds < 30 or settings.openedx_session_bridge_max_age_seconds > 60:
        errors.append('OPENEDX_SESSION_BRIDGE_MAX_AGE_SECONDS must be between 30 and 60 seconds in production')
    if settings.auth_exchange_rate_limit_per_minute < 1:
        errors.append('AUTH_EXCHANGE_RATE_LIMIT_PER_MINUTE must be at least 1 in production')
    if settings.auth_exchange_ticket_rate_limit_per_minute < 1:
        errors.append('AUTH_EXCHANGE_TICKET_RATE_LIMIT_PER_MINUTE must be at least 1 in production')
    if not (settings.redis_url or '').strip() or 'CHANGE_ME' in settings.redis_url:
        errors.append('REDIS_URL is required for one-time SSO tickets and session revocation in production')
    if not urlsplit(settings.redis_url).password or (settings.redis_password or '').startswith('CHANGE_ME'):
        errors.append('REDIS_PASSWORD is required in production (or embed the password in REDIS_URL)')
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
    library_org = str(settings.openedx_library_org or '').strip().upper()
    if not re.fullmatch(r'[A-Z0-9._-]{1,30}', library_org):
        errors.append('OPENEDX_LIBRARY_ORG must be 1-30 characters: A-Z, 0-9, dot, underscore or hyphen')
    if not (1 <= int(settings.openedx_retry_max_attempts) <= 8):
        errors.append('OPENEDX_RETRY_MAX_ATTEMPTS must be between 1 and 8')
    if float(settings.openedx_retry_base_seconds) <= 0:
        errors.append('OPENEDX_RETRY_BASE_SECONDS must be > 0')
    if float(settings.openedx_retry_max_seconds) < float(settings.openedx_retry_base_seconds):
        errors.append('OPENEDX_RETRY_MAX_SECONDS must be >= OPENEDX_RETRY_BASE_SECONDS')
    internal_cms = str(settings.openedx_cms_internal_base_url or '').strip()
    if internal_cms:
        parsed_internal = urlsplit(internal_cms)
        if parsed_internal.scheme not in {'http', 'https'} or not parsed_internal.hostname:
            errors.append('OPENEDX_CMS_INTERNAL_BASE_URL must be an absolute http(s) URL when configured')
    cms_host_header = str(settings.openedx_cms_host_header or '').strip()
    if cms_host_header and ('://' in cms_host_header or '/' in cms_host_header or any(ch.isspace() for ch in cms_host_header)):
        errors.append('OPENEDX_CMS_HOST_HEADER must contain only a host name, not a URL/path')
    default_course_org = str(settings.academic_default_openedx_course_org or '').strip().upper()
    if default_course_org and not re.fullmatch(r'[A-Z0-9._-]{1,30}', default_course_org):
        errors.append('ACADEMIC_DEFAULT_OPENEDX_COURSE_ORG contains an invalid Open edX org')
    branch_org_raw = str(settings.academic_openedx_org_by_branch or '').strip()
    if branch_org_raw:
        try:
            branch_org_map = json.loads(branch_org_raw)
        except Exception:
            branch_org_map = None
        if not isinstance(branch_org_map, dict):
            errors.append('ACADEMIC_OPENEDX_ORG_BY_BRANCH must be a JSON object when configured')
        else:
            for branch_key, org_value in branch_org_map.items():
                branch_name = str(branch_key or '').strip()
                org_name = str(org_value or '').strip().upper()
                if not branch_name or not re.fullmatch(r'[A-Z0-9._-]{1,30}', org_name):
                    errors.append('ACADEMIC_OPENEDX_ORG_BY_BRANCH contains an invalid branch/org mapping')
                    break

    if not settings.openedx_connector_hmac_secret or settings.openedx_connector_hmac_secret.startswith('CHANGE_ME') or len(settings.openedx_connector_hmac_secret) < 32:
        errors.append('OPENEDX_CONNECTOR_HMAC_SECRET with a real value of at least 32 characters is required in production')
    if settings.auth_mode.lower().strip() == 'openedx_sso':
        bridge_secret = settings.openedx_session_bridge_secret or settings.openedx_connector_hmac_secret
        if not bridge_secret or str(bridge_secret).startswith('CHANGE_ME') or len(str(bridge_secret)) < 32:
            errors.append('OPENEDX_SESSION_BRIDGE_SECRET or OPENEDX_CONNECTOR_HMAC_SECRET is required for AUTH_MODE=openedx_sso')

    if settings.celery_worker_prefetch_multiplier < 1 or settings.celery_worker_prefetch_multiplier > 4:
        errors.append('CELERY_WORKER_PREFETCH_MULTIPLIER must be between 1 and 4 in production')
    if settings.celery_worker_max_tasks_per_child < 1:
        errors.append('CELERY_WORKER_MAX_TASKS_PER_CHILD must be at least 1 in production')
    if settings.celery_default_soft_time_limit_seconds < 60:
        errors.append('CELERY_DEFAULT_SOFT_TIME_LIMIT_SECONDS must be at least 60 seconds')
    if settings.celery_default_time_limit_seconds <= settings.celery_default_soft_time_limit_seconds:
        errors.append('CELERY_DEFAULT_TIME_LIMIT_SECONDS must be greater than soft time limit')
    if settings.celery_broker_visibility_timeout_seconds <= settings.celery_default_time_limit_seconds:
        errors.append('CELERY_BROKER_VISIBILITY_TIMEOUT_SECONDS must be greater than task hard time limit')
    if settings.academic_class_sync_max_students < 1000 or settings.academic_class_sync_max_students > 20000:
        errors.append('ACADEMIC_CLASS_SYNC_MAX_STUDENTS must be between 1000 and 20000')
    if settings.academic_teacher_report_sync_export_max_teachers < 1:
        errors.append('ACADEMIC_TEACHER_REPORT_SYNC_EXPORT_MAX_TEACHERS must be at least 1')
    if settings.academic_teacher_report_sync_export_max_students < 1:
        errors.append('ACADEMIC_TEACHER_REPORT_SYNC_EXPORT_MAX_STUDENTS must be at least 1')
    if settings.academic_udemy_import_max_files < 1 or settings.academic_udemy_import_max_files > 100:
        errors.append('ACADEMIC_UDEMY_IMPORT_MAX_FILES must be between 1 and 100')
    if settings.academic_udemy_import_max_file_bytes < 1024 * 1024 or settings.academic_udemy_import_max_file_bytes > 100 * 1024 * 1024:
        errors.append('ACADEMIC_UDEMY_IMPORT_MAX_FILE_BYTES must be between 1 MB and 100 MB')
    if settings.academic_udemy_import_max_total_bytes < settings.academic_udemy_import_max_file_bytes:
        errors.append('ACADEMIC_UDEMY_IMPORT_MAX_TOTAL_BYTES must be >= max file bytes')
    if settings.academic_udemy_import_max_rows < 1_000 or settings.academic_udemy_import_max_rows > 1_000_000:
        errors.append('ACADEMIC_UDEMY_IMPORT_MAX_ROWS must be between 1000 and 1000000')
    if settings.academic_udemy_xlsx_max_entries < 100 or settings.academic_udemy_xlsx_max_entries > 50_000:
        errors.append('ACADEMIC_UDEMY_XLSX_MAX_ENTRIES must be between 100 and 50000')
    if settings.academic_udemy_xlsx_max_uncompressed_bytes < settings.academic_udemy_import_max_file_bytes:
        errors.append('ACADEMIC_UDEMY_XLSX_MAX_UNCOMPRESSED_BYTES must be >= max file bytes')
    if settings.academic_udemy_xlsx_max_compression_ratio < 10 or settings.academic_udemy_xlsx_max_compression_ratio > 1000:
        errors.append('ACADEMIC_UDEMY_XLSX_MAX_COMPRESSION_RATIO must be between 10 and 1000')
    if settings.academic_udemy_upload_rate_limit_per_minute < 1:
        errors.append('ACADEMIC_UDEMY_UPLOAD_RATE_LIMIT_PER_MINUTE must be at least 1')
    if settings.academic_udemy_file_retention_hours < 1 or settings.academic_udemy_export_file_retention_hours < 1:
        errors.append('Udemy artifact retention must be at least 1 hour')
    if settings.academic_udemy_sync_export_max_rows < 100 or settings.academic_udemy_sync_export_max_rows > 50_000:
        errors.append('ACADEMIC_UDEMY_SYNC_EXPORT_MAX_ROWS must be between 100 and 50000')
    if settings.academic_udemy_worker_max_retries < 0 or settings.academic_udemy_worker_max_retries > 10:
        errors.append('ACADEMIC_UDEMY_WORKER_MAX_RETRIES must be between 0 and 10')
    if settings.academic_udemy_cleanup_interval_seconds < 3600:
        errors.append('ACADEMIC_UDEMY_CLEANUP_INTERVAL_SECONDS must be at least 3600')

    if settings.academic_ap_sync_enabled:
        if not settings.academic_ap_api_base_url or 'CHANGE_ME' in settings.academic_ap_api_base_url:
            errors.append('ACADEMIC_AP_API_BASE_URL is required when ACADEMIC_AP_SYNC_ENABLED=true')
        if not settings.academic_ap_api_key or settings.academic_ap_api_key.startswith('CHANGE_ME') or len(settings.academic_ap_api_key) < 12:
            errors.append('ACADEMIC_AP_API_KEY is required when ACADEMIC_AP_SYNC_ENABLED=true')
        if settings.academic_ap_request_timeout_seconds < 5:
            errors.append('ACADEMIC_AP_REQUEST_TIMEOUT_SECONDS must be at least 5 seconds')
    if errors:
        raise RuntimeError('Unsafe production configuration: ' + '; '.join(errors))


settings = Settings()
