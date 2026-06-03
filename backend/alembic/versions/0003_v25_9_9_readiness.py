"""v25.9.9 production readiness schema

Revision ID: 0003_v25_9_9_readiness
Revises: 0002_chapter_libraries
Create Date: 2026-05-18
"""
from alembic import op

revision = '0003_v25_9_9_readiness'
down_revision = '0002_chapter_libraries'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # PostgreSQL-oriented migration. The app still has AUTO_CREATE_TABLES for dev,
    # but production should use this migration instead of relying on runtime ALTERs.
    op.execute("ALTER TABLE ai_course_libraries ADD COLUMN IF NOT EXISTS difficulty VARCHAR(50) DEFAULT 'easy'")
    op.execute("UPDATE ai_course_libraries SET difficulty='easy' WHERE difficulty IS NULL OR difficulty='' ")
    # v24 used one library per chapter. v25.2+ needs one library per chapter + difficulty.
    # Drop the old unique constraint if it exists so EASY/MEDIUM/HARD libraries can coexist.
    op.execute("ALTER TABLE ai_course_libraries DROP CONSTRAINT IF EXISTS uq_course_chapter_library")
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_course_chapter_difficulty_library ON ai_course_libraries(course_id, chapter_node_id, difficulty)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_ai_course_libraries_difficulty ON ai_course_libraries(difficulty)")

    question_columns = [
        "ALTER TABLE ai_questions ADD COLUMN IF NOT EXISTS question_hash VARCHAR(128)",
        "ALTER TABLE ai_questions ADD COLUMN IF NOT EXISTS draft_error_reason VARCHAR(100)",
        "ALTER TABLE ai_questions ADD COLUMN IF NOT EXISTS draft_error_detail JSONB",
        "ALTER TABLE ai_questions ADD COLUMN IF NOT EXISTS repair_attempt_count INTEGER DEFAULT 0",
        "ALTER TABLE ai_questions ADD COLUMN IF NOT EXISTS is_duplicate BOOLEAN DEFAULT FALSE",
        "ALTER TABLE ai_questions ADD COLUMN IF NOT EXISTS duplicate_of_question_id VARCHAR",
        "ALTER TABLE ai_questions ADD COLUMN IF NOT EXISTS duplicate_score DOUBLE PRECISION",
        "ALTER TABLE ai_questions ADD COLUMN IF NOT EXISTS generation_job_id VARCHAR",
        "ALTER TABLE ai_questions ADD COLUMN IF NOT EXISTS openedx_library_problem_id VARCHAR(512)",
        "ALTER TABLE ai_questions ADD COLUMN IF NOT EXISTS imported_library_at TIMESTAMP",
        "ALTER TABLE ai_questions ADD COLUMN IF NOT EXISTS publish_error TEXT",
        "ALTER TABLE ai_questions ADD COLUMN IF NOT EXISTS publish_status VARCHAR(50)",
        "ALTER TABLE ai_questions ADD COLUMN IF NOT EXISTS publish_verification_json JSONB",
        "ALTER TABLE ai_questions ADD COLUMN IF NOT EXISTS published_by VARCHAR(255)",
    ]
    for statement in question_columns:
        op.execute(statement)
    op.execute("CREATE INDEX IF NOT EXISTS ix_ai_questions_question_hash ON ai_questions(question_hash)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_ai_questions_draft_error_reason ON ai_questions(draft_error_reason)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_ai_questions_generation_job_id ON ai_questions(generation_job_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_ai_questions_publish_status ON ai_questions(publish_status)")

    job_columns = [
        "ALTER TABLE ai_generation_jobs ADD COLUMN IF NOT EXISTS estimated_output_tokens_per_question DOUBLE PRECISION DEFAULT 0",
        "ALTER TABLE ai_generation_jobs ADD COLUMN IF NOT EXISTS output_calibration_json TEXT",
        "ALTER TABLE ai_generation_jobs ADD COLUMN IF NOT EXISTS actual_output_tokens_per_question DOUBLE PRECISION DEFAULT 0",
        "ALTER TABLE ai_generation_jobs ADD COLUMN IF NOT EXISTS output_accuracy_percent DOUBLE PRECISION DEFAULT 0",
        "ALTER TABLE ai_generation_jobs ADD COLUMN IF NOT EXISTS output_delta_tokens INTEGER DEFAULT 0",
        "ALTER TABLE ai_generation_jobs ADD COLUMN IF NOT EXISTS completed_question_count INTEGER DEFAULT 0",
        "ALTER TABLE ai_generation_jobs ADD COLUMN IF NOT EXISTS openai_response_ids TEXT",
        "ALTER TABLE ai_generation_jobs ADD COLUMN IF NOT EXISTS raw_model_output_text TEXT",
        "ALTER TABLE ai_generation_jobs ADD COLUMN IF NOT EXISTS raw_model_usage_json TEXT",
        "ALTER TABLE ai_generation_jobs ADD COLUMN IF NOT EXISTS model_parse_error TEXT",
    ]
    for statement in job_columns:
        op.execute(statement)

    op.execute("""
    CREATE TABLE IF NOT EXISTS ai_generation_cache (
        id VARCHAR PRIMARY KEY,
        cache_key VARCHAR(512) NOT NULL,
        prompt_cache_key VARCHAR(512),
        course_id VARCHAR(255),
        source_node_id VARCHAR(512),
        chunk_hash VARCHAR(128),
        difficulty VARCHAR(50),
        question_count INTEGER DEFAULT 0,
        prompt_version VARCHAR(100) DEFAULT 'v25_3_learning_check_json_schema_1',
        model_name VARCHAR(100) DEFAULT 'gpt-5-mini',
        raw_output_text TEXT,
        parsed_questions_json JSONB,
        question_hashes JSONB,
        response_id VARCHAR(255),
        parse_error TEXT,
        input_tokens INTEGER DEFAULT 0,
        cached_input_tokens INTEGER DEFAULT 0,
        output_tokens INTEGER DEFAULT 0,
        hit_count INTEGER DEFAULT 0,
        created_at TIMESTAMP,
        updated_at TIMESTAMP,
        CONSTRAINT uq_generation_cache_key UNIQUE(cache_key)
    )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_ai_generation_cache_prompt_cache_key ON ai_generation_cache(prompt_cache_key)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_ai_generation_cache_course_id ON ai_generation_cache(course_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_ai_generation_cache_difficulty ON ai_generation_cache(difficulty)")

    op.execute("""
    CREATE TABLE IF NOT EXISTS ai_token_calibration (
        id VARCHAR PRIMARY KEY,
        model_name VARCHAR(100) DEFAULT 'gpt-5-mini',
        course_id VARCHAR(255) DEFAULT 'global',
        difficulty VARCHAR(50) DEFAULT 'mixed',
        question_type VARCHAR(50) DEFAULT 'single_choice',
        prompt_version VARCHAR(100) DEFAULT 'v25_3_learning_check_json_schema_1',
        avg_output_tokens_per_question DOUBLE PRECISION DEFAULT 750,
        min_output_tokens_per_question DOUBLE PRECISION DEFAULT 0,
        max_output_tokens_per_question DOUBLE PRECISION DEFAULT 0,
        sample_count INTEGER DEFAULT 0,
        last_actual_output_tokens INTEGER DEFAULT 0,
        last_question_count INTEGER DEFAULT 0,
        last_observed_tokens_per_question DOUBLE PRECISION DEFAULT 0,
        created_at TIMESTAMP,
        updated_at TIMESTAMP,
        CONSTRAINT uq_token_calibration_scope UNIQUE(model_name, course_id, difficulty, question_type, prompt_version)
    )
    """)

    op.execute("""
    CREATE TABLE IF NOT EXISTS ai_generation_batches (
        id VARCHAR PRIMARY KEY,
        job_id VARCHAR NOT NULL,
        course_id VARCHAR(255) NOT NULL,
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
        actual_cost_usd DOUBLE PRECISION DEFAULT 0,
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
    op.execute("CREATE INDEX IF NOT EXISTS ix_ai_generation_batches_job_id ON ai_generation_batches(job_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_ai_generation_batches_course_id ON ai_generation_batches(course_id)")

    op.execute("""
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
        metadata_json JSONB,
        request_id VARCHAR(255),
        created_at TIMESTAMP
    )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_ai_audit_logs_course ON ai_audit_logs(course_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_ai_audit_logs_actor ON ai_audit_logs(actor_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_ai_audit_logs_status ON ai_audit_logs(status)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_ai_audit_logs_error_type ON ai_audit_logs(error_type)")
    op.execute("""
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


def downgrade() -> None:
    # Keep downgrade conservative to avoid dropping production audit/usage history.
    op.execute("DROP TABLE IF EXISTS ai_audit_logs")
    op.execute("DROP TABLE IF EXISTS ai_generation_batches")
    op.execute("DROP TABLE IF EXISTS ai_token_calibration")
    op.execute("DROP TABLE IF EXISTS ai_generation_cache")
