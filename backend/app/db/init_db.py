from app.core.config import settings
from app.db.session import Base, engine, SessionLocal
from app.models import course, question, cost, job, generation_cache, token_calibration, generation_batch, audit, publish, concept, question_bank, rbac  # noqa: F401 - import models for metadata


def init_db() -> None:
    """Create tables only in demo/dev mode.

    Production should set AUTO_CREATE_TABLES=false and run Alembic migrations:
    alembic upgrade head
    """
    if settings.auto_create_tables:
        Base.metadata.create_all(bind=engine)
        _ensure_v24_columns()
        _ensure_rbac_catalog()



def _ensure_v24_columns() -> None:
    """Dev/demo safety net for existing Postgres volumes before v24. Production uses Alembic."""
    with engine.begin() as conn:
        conn.exec_driver_sql("""
        CREATE TABLE IF NOT EXISTS ai_course_libraries (
            id VARCHAR PRIMARY KEY,
            course_id VARCHAR(255),
            chapter_node_id VARCHAR(512),
            chapter_title VARCHAR(512),
            difficulty VARCHAR(50) DEFAULT 'easy',
            library_key VARCHAR(512),
            display_name VARCHAR(512),
            openedx_library_id VARCHAR(512),
            status VARCHAR(50),
            metadata_json JSON,
            created_at TIMESTAMP,
            updated_at TIMESTAMP,
            CONSTRAINT uq_course_chapter_difficulty_library UNIQUE (course_id, chapter_node_id, difficulty)
        )
        """)



        conn.exec_driver_sql("""
        CREATE TABLE IF NOT EXISTS ai_concepts (
            id VARCHAR PRIMARY KEY,
            course_id VARCHAR(255),
            chapter_node_id VARCHAR(512),
            source_node_id VARCHAR(512),
            source_node_title VARCHAR(512),
            concept_key VARCHAR(255),
            title VARCHAR(512) DEFAULT '',
            summary TEXT DEFAULT '',
            learning_objective TEXT DEFAULT '',
            difficulty_hint VARCHAR(50) DEFAULT 'easy',
            importance_score FLOAT DEFAULT 0.5,
            source_chunk_ids JSON,
            source_evidence TEXT DEFAULT '',
            token_count INTEGER DEFAULT 0,
            status VARCHAR(50) DEFAULT 'active',
            metadata_json JSON,
            created_at TIMESTAMP,
            updated_at TIMESTAMP,
            CONSTRAINT uq_ai_concepts_course_node_key UNIQUE (course_id, source_node_id, concept_key)
        )
        """)
        conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_ai_concepts_course_node_status ON ai_concepts(course_id, source_node_id, status)")
        conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_ai_concepts_course_chapter_difficulty ON ai_concepts(course_id, chapter_node_id, difficulty_hint)")

        conn.exec_driver_sql("""
        CREATE TABLE IF NOT EXISTS ai_publish_batches (
            id VARCHAR PRIMARY KEY,
            course_id VARCHAR(255),
            actor_id VARCHAR(255) DEFAULT 'teacher',
            mode VARCHAR(50) DEFAULT 'publish_new',
            status VARCHAR(50) DEFAULT 'running',
            total_questions INTEGER DEFAULT 0,
            published_count INTEGER DEFAULT 0,
            failed_count INTEGER DEFAULT 0,
            warning_count INTEGER DEFAULT 0,
            summary_json JSON,
            errors_json JSON,
            created_at TIMESTAMP,
            completed_at TIMESTAMP
        )
        """)
        conn.exec_driver_sql("""
        CREATE TABLE IF NOT EXISTS ai_publish_batch_items (
            id VARCHAR PRIMARY KEY,
            batch_id VARCHAR,
            question_id VARCHAR,
            course_id VARCHAR(255),
            library_key VARCHAR(512),
            difficulty VARCHAR(50),
            openedx_usage_key VARCHAR(512),
            status VARCHAR(50) DEFAULT 'pending',
            message TEXT DEFAULT '',
            result_json JSON,
            created_at TIMESTAMP
        )
        """)

        conn.exec_driver_sql("""
        CREATE TABLE IF NOT EXISTS ai_token_calibration (
            id VARCHAR PRIMARY KEY,
            model_name VARCHAR(100) DEFAULT 'gpt-5-mini',
            course_id VARCHAR(255) DEFAULT 'global',
            difficulty VARCHAR(50) DEFAULT 'mixed',
            question_type VARCHAR(50) DEFAULT 'single_choice',
            prompt_version VARCHAR(100) DEFAULT 'v25_3_learning_check_json_schema_1',
            avg_output_tokens_per_question FLOAT DEFAULT 750,
            min_output_tokens_per_question FLOAT DEFAULT 0,
            max_output_tokens_per_question FLOAT DEFAULT 0,
            sample_count INTEGER DEFAULT 0,
            last_actual_output_tokens INTEGER DEFAULT 0,
            last_question_count INTEGER DEFAULT 0,
            last_observed_tokens_per_question FLOAT DEFAULT 0,
            created_at TIMESTAMP,
            updated_at TIMESTAMP,
            CONSTRAINT uq_token_calibration_scope UNIQUE (model_name, course_id, difficulty, question_type, prompt_version)
        )
        """)

        conn.exec_driver_sql("""
        CREATE TABLE IF NOT EXISTS ai_generation_cache (
            id VARCHAR PRIMARY KEY,
            cache_key VARCHAR(512),
            prompt_cache_key VARCHAR(512),
            course_id VARCHAR(255),
            source_node_id VARCHAR(512),
            chunk_hash VARCHAR(128),
            difficulty VARCHAR(50),
            question_count INTEGER DEFAULT 0,
            prompt_version VARCHAR(100) DEFAULT 'v25_3_learning_check_json_schema_1',
            model_name VARCHAR(100) DEFAULT 'gpt-5-mini',
            raw_output_text TEXT,
            parsed_questions_json JSON,
            question_hashes JSON,
            response_id VARCHAR(255),
            parse_error TEXT,
            input_tokens INTEGER DEFAULT 0,
            cached_input_tokens INTEGER DEFAULT 0,
            output_tokens INTEGER DEFAULT 0,
            hit_count INTEGER DEFAULT 0,
            created_at TIMESTAMP,
            updated_at TIMESTAMP,
            CONSTRAINT uq_generation_cache_key UNIQUE (cache_key)
        )
        """)




        conn.exec_driver_sql("""
        CREATE TABLE IF NOT EXISTS ai_audit_logs (
            id VARCHAR PRIMARY KEY,
            course_id VARCHAR(255),
            actor_id VARCHAR(255) DEFAULT 'system',
            actor_role VARCHAR(50),
            action VARCHAR(120),
            target_type VARCHAR(80),
            target_id VARCHAR(255),
            status VARCHAR(50) DEFAULT 'success',
            error_type VARCHAR(50),
            message TEXT,
            metadata_json JSON,
            request_id VARCHAR(255),
            created_at TIMESTAMP
        )
        """)
        conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_ai_audit_logs_course ON ai_audit_logs(course_id)")
        conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_ai_audit_logs_actor ON ai_audit_logs(actor_id)")
        conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_ai_audit_logs_status ON ai_audit_logs(status)")
        conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_ai_audit_logs_error_type ON ai_audit_logs(error_type)")

        conn.exec_driver_sql("""
        CREATE TABLE IF NOT EXISTS ai_generation_batches (
            id VARCHAR PRIMARY KEY,
            job_id VARCHAR,
            course_id VARCHAR(255),
            batch_index INTEGER DEFAULT 0,
            phase VARCHAR(50) DEFAULT 'primary',
            difficulty VARCHAR(50),
            difficulty_counts_json TEXT,
            requested_questions INTEGER DEFAULT 0,
            completed_questions INTEGER DEFAULT 0,
            status VARCHAR(50) DEFAULT 'queued',
            estimated_input_tokens INTEGER DEFAULT 0,
            estimated_output_tokens INTEGER DEFAULT 0,
            actual_input_tokens INTEGER DEFAULT 0,
            actual_cached_input_tokens INTEGER DEFAULT 0,
            actual_output_tokens INTEGER DEFAULT 0,
            actual_cost_usd FLOAT DEFAULT 0,
            token_source VARCHAR(255),
            openai_response_id VARCHAR(255),
            prompt_cache_key VARCHAR(512),
            generation_cache_key VARCHAR(512),
            error_message TEXT,
            started_at TIMESTAMP,
            finished_at TIMESTAMP,
            created_at TIMESTAMP,
            updated_at TIMESTAMP
        )
        """)

        for ddl in [
            "ALTER TABLE ai_course_libraries ADD COLUMN IF NOT EXISTS difficulty VARCHAR(50) DEFAULT 'easy'",
            "ALTER TABLE ai_course_libraries DROP CONSTRAINT IF EXISTS uq_course_chapter_library",
            """DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uq_course_chapter_difficulty_library') THEN ALTER TABLE ai_course_libraries ADD CONSTRAINT uq_course_chapter_difficulty_library UNIQUE (course_id, chapter_node_id, difficulty); END IF; END $$""",
            "ALTER TABLE ai_questions ADD COLUMN IF NOT EXISTS question_hash VARCHAR(128)",
            "ALTER TABLE ai_questions ADD COLUMN IF NOT EXISTS draft_error_reason VARCHAR(100)",
            "ALTER TABLE ai_questions ADD COLUMN IF NOT EXISTS draft_error_detail JSON",
            "ALTER TABLE ai_questions ADD COLUMN IF NOT EXISTS repair_attempt_count INTEGER DEFAULT 0",
            "ALTER TABLE ai_questions ADD COLUMN IF NOT EXISTS duplicate_score FLOAT",
            "ALTER TABLE ai_questions ADD COLUMN IF NOT EXISTS publish_status VARCHAR(50)",
            "ALTER TABLE ai_questions ADD COLUMN IF NOT EXISTS concept_id VARCHAR",
            "ALTER TABLE ai_questions ADD COLUMN IF NOT EXISTS concept_title VARCHAR(512)",
            "ALTER TABLE ai_questions ADD COLUMN IF NOT EXISTS concept_key VARCHAR(255)",
            "ALTER TABLE ai_questions ADD COLUMN IF NOT EXISTS question_family_id VARCHAR(255)",
            "ALTER TABLE ai_questions ADD COLUMN IF NOT EXISTS variant_no INTEGER",
            "ALTER TABLE ai_questions ADD COLUMN IF NOT EXISTS source_evidence TEXT DEFAULT ''",
            "CREATE INDEX IF NOT EXISTS ix_ai_questions_course_family_status ON ai_questions(course_id, question_family_id, status)",
            "CREATE INDEX IF NOT EXISTS ix_ai_questions_course_chapter_family_difficulty ON ai_questions(course_id, chapter_node_id, question_family_id, difficulty)",
            "ALTER TABLE ai_questions ADD COLUMN IF NOT EXISTS publish_verification_json JSON",
            "ALTER TABLE ai_questions ADD COLUMN IF NOT EXISTS published_by VARCHAR(255)",
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_ai_questions_course_hash ON ai_questions(course_id, question_hash) WHERE question_hash IS NOT NULL",
            "ALTER TABLE ai_questions ADD COLUMN IF NOT EXISTS source_node_id VARCHAR(512)",
            "ALTER TABLE ai_questions ADD COLUMN IF NOT EXISTS source_node_title VARCHAR(512)",
            "ALTER TABLE ai_questions ADD COLUMN IF NOT EXISTS chapter_node_id VARCHAR(512)",
            "ALTER TABLE ai_questions ADD COLUMN IF NOT EXISTS chapter_title VARCHAR(512)",
            "ALTER TABLE ai_questions ADD COLUMN IF NOT EXISTS target_library_id VARCHAR",
            "ALTER TABLE ai_questions ADD COLUMN IF NOT EXISTS target_library_key VARCHAR(512)",
            "ALTER TABLE ai_questions ADD COLUMN IF NOT EXISTS openedx_library_problem_id VARCHAR(512)",
            "ALTER TABLE ai_questions ADD COLUMN IF NOT EXISTS imported_library_at TIMESTAMP",
            # v24.9 job estimate/actual usage reconciliation columns
            "ALTER TABLE ai_generation_jobs ADD COLUMN IF NOT EXISTS estimated_input_tokens INTEGER DEFAULT 0",
            "ALTER TABLE ai_generation_jobs ADD COLUMN IF NOT EXISTS estimated_cached_input_tokens INTEGER DEFAULT 0",
            "ALTER TABLE ai_generation_jobs ADD COLUMN IF NOT EXISTS estimated_uncached_input_tokens INTEGER DEFAULT 0",
            "ALTER TABLE ai_generation_jobs ADD COLUMN IF NOT EXISTS estimated_output_tokens INTEGER DEFAULT 0",
            "ALTER TABLE ai_generation_jobs ADD COLUMN IF NOT EXISTS estimated_raw_cost_usd FLOAT DEFAULT 0",
            "ALTER TABLE ai_generation_jobs ADD COLUMN IF NOT EXISTS estimated_cost_usd FLOAT DEFAULT 0",
            "ALTER TABLE ai_generation_jobs ADD COLUMN IF NOT EXISTS estimated_cost_vnd FLOAT DEFAULT 0",
            "ALTER TABLE ai_generation_jobs ADD COLUMN IF NOT EXISTS estimate_token_source VARCHAR(255)",
            "ALTER TABLE ai_generation_jobs ADD COLUMN IF NOT EXISTS actual_input_tokens INTEGER DEFAULT 0",
            "ALTER TABLE ai_generation_jobs ADD COLUMN IF NOT EXISTS actual_cached_input_tokens INTEGER DEFAULT 0",
            "ALTER TABLE ai_generation_jobs ADD COLUMN IF NOT EXISTS actual_uncached_input_tokens INTEGER DEFAULT 0",
            "ALTER TABLE ai_generation_jobs ADD COLUMN IF NOT EXISTS actual_output_tokens INTEGER DEFAULT 0",
            "ALTER TABLE ai_generation_jobs ADD COLUMN IF NOT EXISTS actual_cost_usd FLOAT DEFAULT 0",
            "ALTER TABLE ai_generation_jobs ADD COLUMN IF NOT EXISTS actual_cost_vnd FLOAT DEFAULT 0",
            "ALTER TABLE ai_generation_jobs ADD COLUMN IF NOT EXISTS usage_token_source VARCHAR(255)",
            "ALTER TABLE ai_generation_jobs ADD COLUMN IF NOT EXISTS estimate_accuracy_percent FLOAT DEFAULT 0",
            # v25.0 response recovery / partial success columns
            "ALTER TABLE ai_generation_jobs ADD COLUMN IF NOT EXISTS completed_question_count INTEGER DEFAULT 0",
            "ALTER TABLE ai_generation_jobs ADD COLUMN IF NOT EXISTS openai_response_ids TEXT",
            "ALTER TABLE ai_generation_jobs ADD COLUMN IF NOT EXISTS raw_model_output_text TEXT",
            "ALTER TABLE ai_generation_jobs ADD COLUMN IF NOT EXISTS raw_model_usage_json TEXT",
            "ALTER TABLE ai_generation_jobs ADD COLUMN IF NOT EXISTS model_parse_error TEXT",
            # v25.9.7 estimate calibration diagnostics
            "ALTER TABLE ai_generation_jobs ADD COLUMN IF NOT EXISTS estimated_output_tokens_per_question FLOAT DEFAULT 0",
            "ALTER TABLE ai_generation_jobs ADD COLUMN IF NOT EXISTS actual_output_tokens_per_question FLOAT DEFAULT 0",
            "ALTER TABLE ai_generation_jobs ADD COLUMN IF NOT EXISTS output_accuracy_percent FLOAT DEFAULT 0",
            "ALTER TABLE ai_generation_jobs ADD COLUMN IF NOT EXISTS output_delta_tokens INTEGER DEFAULT 0",
            "ALTER TABLE ai_generation_jobs ADD COLUMN IF NOT EXISTS output_calibration_json TEXT",
            # v25.9.13.3 usage-log compatibility for existing dev volumes.
            # SQLAlchemy create_all does not ALTER old tables, so older Postgres
            # volumes can miss columns that newer routes select.
            "ALTER TABLE ai_usage_log ADD COLUMN IF NOT EXISTS cached_input_tokens INTEGER DEFAULT 0",
            "ALTER TABLE ai_usage_log ADD COLUMN IF NOT EXISTS uncached_input_tokens INTEGER DEFAULT 0",
            "ALTER TABLE ai_usage_log ADD COLUMN IF NOT EXISTS cost_vnd FLOAT DEFAULT 0",
            "ALTER TABLE ai_usage_log ADD COLUMN IF NOT EXISTS token_source VARCHAR(255)",
            "ALTER TABLE ai_usage_log ADD COLUMN IF NOT EXISTS raw_usage_json TEXT",
            "ALTER TABLE ai_usage_log ADD COLUMN IF NOT EXISTS raw_error TEXT",
            "CREATE INDEX IF NOT EXISTS ix_ai_questions_draft_error_reason ON ai_questions(draft_error_reason)",
            "CREATE INDEX IF NOT EXISTS ix_ai_questions_publish_status ON ai_questions(publish_status)",
            "CREATE INDEX IF NOT EXISTS ix_generation_cache_prompt_cache_key ON ai_generation_cache(prompt_cache_key)",
            "CREATE INDEX IF NOT EXISTS ix_generation_cache_course_diff ON ai_generation_cache(course_id, difficulty)",
            "CREATE INDEX IF NOT EXISTS ix_token_calibration_lookup ON ai_token_calibration(model_name, course_id, difficulty)",
            "CREATE INDEX IF NOT EXISTS ix_generation_batches_job ON ai_generation_batches(job_id)",
            "CREATE INDEX IF NOT EXISTS ix_generation_batches_status ON ai_generation_batches(status)",
            "CREATE INDEX IF NOT EXISTS ix_publish_batches_course ON ai_publish_batches(course_id)",
            "CREATE INDEX IF NOT EXISTS ix_publish_batches_created ON ai_publish_batches(created_at)",
            "CREATE INDEX IF NOT EXISTS ix_publish_batch_items_batch ON ai_publish_batch_items(batch_id)",
            "CREATE INDEX IF NOT EXISTS ix_publish_batch_items_question ON ai_publish_batch_items(question_id)",
            # v25.9.13.42 production scale/idempotency/lifecycle compatibility.
            "ALTER TABLE ai_questions ADD COLUMN IF NOT EXISTS openedx_publish_status VARCHAR(50)",
            "ALTER TABLE ai_questions ADD COLUMN IF NOT EXISTS openedx_verification_status VARCHAR(50)",
            "ALTER TABLE ai_questions ADD COLUMN IF NOT EXISTS openedx_delete_status VARCHAR(50)",
            "ALTER TABLE ai_questions ADD COLUMN IF NOT EXISTS openedx_manual_action_required BOOLEAN DEFAULT FALSE",
            "ALTER TABLE ai_generation_jobs ADD COLUMN IF NOT EXISTS idempotency_key VARCHAR(255)",
            "ALTER TABLE ai_publish_batches ADD COLUMN IF NOT EXISTS idempotency_key VARCHAR(255)",
            "ALTER TABLE ai_publish_batches ADD COLUMN IF NOT EXISTS rollback_idempotency_key VARCHAR(255)",
            "CREATE INDEX IF NOT EXISTS ix_ai_questions_course_status_created ON ai_questions(course_id, status, created_at)",
            "CREATE INDEX IF NOT EXISTS ix_ai_questions_course_source_status_created ON ai_questions(course_id, source_node_id, status, created_at)",
            "CREATE INDEX IF NOT EXISTS ix_ai_questions_course_publish_created ON ai_questions(course_id, publish_status, created_at)",
            "CREATE INDEX IF NOT EXISTS ix_ai_questions_course_openedx_lifecycle ON ai_questions(course_id, openedx_publish_status, openedx_verification_status, openedx_delete_status)",
            "CREATE INDEX IF NOT EXISTS ix_ai_generation_jobs_course_status_created ON ai_generation_jobs(course_id, status, created_at)",
            "CREATE INDEX IF NOT EXISTS ix_ai_generation_jobs_course_requested_created ON ai_generation_jobs(course_id, requested_by, created_at)",
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_ai_generation_jobs_idempotency ON ai_generation_jobs(course_id, requested_by, idempotency_key) WHERE idempotency_key IS NOT NULL",
            "CREATE INDEX IF NOT EXISTS ix_ai_content_chunks_course_block_created ON ai_content_chunks(course_id, block_id, created_at)",
            "CREATE INDEX IF NOT EXISTS ix_ai_content_chunks_course_source_created ON ai_content_chunks(course_id, source_type, created_at)",
            "CREATE INDEX IF NOT EXISTS ix_ai_content_chunks_course_topic ON ai_content_chunks(course_id, topic_id)",
            "CREATE INDEX IF NOT EXISTS ix_ai_course_sync_course_parent_type ON ai_course_sync_state(course_id, parent_block_id, block_type)",
            "CREATE INDEX IF NOT EXISTS ix_ai_course_sync_course_status_synced ON ai_course_sync_state(course_id, sync_status, last_synced_at)",
            "CREATE INDEX IF NOT EXISTS ix_ai_usage_log_course_feature_created ON ai_usage_log(course_id, feature, created_at)",
            "CREATE INDEX IF NOT EXISTS ix_ai_usage_log_course_model_created ON ai_usage_log(course_id, model_provider, model_name, created_at)",
            "CREATE INDEX IF NOT EXISTS ix_ai_publish_batches_course_status_created ON ai_publish_batches(course_id, status, created_at)",
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_ai_publish_batches_idempotency ON ai_publish_batches(course_id, actor_id, mode, idempotency_key) WHERE idempotency_key IS NOT NULL",
            "CREATE INDEX IF NOT EXISTS ix_ai_publish_items_course_status_created ON ai_publish_batch_items(course_id, status, created_at)",
            "CREATE INDEX IF NOT EXISTS ix_ai_publish_items_question_status ON ai_publish_batch_items(question_id, status)",
        ]:
            conn.exec_driver_sql(ddl)

        # v25.9.10: normalize old lowercase audit error_type values for dev volumes.
        conn.exec_driver_sql("""
        UPDATE ai_audit_logs
        SET error_type = CASE
            WHEN error_type IN ('user', 'USER', 'user_error') THEN 'USER_ERROR'
            WHEN error_type IN ('system', 'SYSTEM', 'system_error') THEN 'SYSTEM_ERROR'
            WHEN error_type IN ('external', 'EXTERNAL', 'external_error', 'external_service_error') THEN 'EXTERNAL_SERVICE_ERROR'
            WHEN error_type IN ('validation', 'validation_error') THEN 'VALIDATION_ERROR'
            WHEN error_type IN ('auth', 'auth_error') THEN 'AUTH_ERROR'
            ELSE error_type
        END
        WHERE error_type IS NOT NULL
        """)


def _ensure_rbac_catalog() -> None:
    """Dev/demo safety net. Production uses Alembic seed in revision 0014."""
    from app.services.business_rbac import BusinessRBACService

    db = SessionLocal()
    try:
        BusinessRBACService(db).ensure_default_catalog()
    finally:
        db.close()
