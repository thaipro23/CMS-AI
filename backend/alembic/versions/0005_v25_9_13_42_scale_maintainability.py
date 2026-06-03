"""v25.9.13.42 scale, idempotency and Open edX lifecycle fields

Revision ID: 0005_v25_9_13_42
Revises: 0004_v25_9_13_2
Create Date: 2026-06-02
"""
from alembic import op

revision = '0005_v25_9_13_42'
down_revision = '0004_v25_9_13_2'
branch_labels = None
depends_on = None


def upgrade() -> None:

    # v25.9.13.47: Some historical production/dev databases reached this
    # migration without the publish history tables because they were originally
    # created by dev create_all() and later switched to Alembic. Create them
    # idempotently before adding idempotency/lifecycle columns or indexes.
    op.execute("""
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
    op.execute("""
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
    # Explicit Open edX lifecycle fields. Legacy ai_questions.status remains the
    # teacher review/business status for backwards-compatible UI/API filters.
    for statement in [
        "ALTER TABLE ai_questions ADD COLUMN IF NOT EXISTS openedx_publish_status VARCHAR(50)",
        "ALTER TABLE ai_questions ADD COLUMN IF NOT EXISTS openedx_verification_status VARCHAR(50)",
        "ALTER TABLE ai_questions ADD COLUMN IF NOT EXISTS openedx_delete_status VARCHAR(50)",
        "ALTER TABLE ai_questions ADD COLUMN IF NOT EXISTS openedx_manual_action_required BOOLEAN DEFAULT FALSE",
        "UPDATE ai_questions SET openedx_publish_status = COALESCE(openedx_publish_status, publish_status) WHERE publish_status IS NOT NULL",
        "UPDATE ai_questions SET openedx_verification_status = COALESCE(openedx_verification_status, CASE WHEN publish_status IN ('verified','published','success','published_with_tag_warning','published_ok_stale_verify') THEN 'verified' WHEN publish_status IN ('published_with_pending_changes','imported_needs_manual_publish','imported_needs_manual_verify') THEN 'pending' WHEN publish_status = 'failed' THEN 'failed' ELSE NULL END)",
        "UPDATE ai_questions SET openedx_manual_action_required = TRUE WHERE publish_status IN ('published_with_pending_changes','imported_needs_manual_publish','imported_needs_manual_verify','rollback_openedx_delete_unverified')",
        "ALTER TABLE ai_generation_jobs ADD COLUMN IF NOT EXISTS idempotency_key VARCHAR(255)",
        "ALTER TABLE ai_publish_batches ADD COLUMN IF NOT EXISTS idempotency_key VARCHAR(255)",
        "ALTER TABLE ai_publish_batches ADD COLUMN IF NOT EXISTS rollback_idempotency_key VARCHAR(255)",
    ]:
        op.execute(statement)

    # Composite indexes for common production filters and analytics queries.
    index_statements = [
        "CREATE INDEX IF NOT EXISTS ix_ai_questions_course_status_created ON ai_questions(course_id, status, created_at)",
        "CREATE INDEX IF NOT EXISTS ix_ai_questions_course_source_status_created ON ai_questions(course_id, source_node_id, status, created_at)",
        "CREATE INDEX IF NOT EXISTS ix_ai_questions_course_publish_created ON ai_questions(course_id, publish_status, created_at)",
        "CREATE INDEX IF NOT EXISTS ix_ai_questions_course_openedx_lifecycle ON ai_questions(course_id, openedx_publish_status, openedx_verification_status, openedx_delete_status)",
        "CREATE INDEX IF NOT EXISTS ix_ai_questions_course_quality ON ai_questions(course_id, quality_score)",
        "CREATE INDEX IF NOT EXISTS ix_ai_generation_jobs_course_status_created ON ai_generation_jobs(course_id, status, created_at)",
        "CREATE INDEX IF NOT EXISTS ix_ai_generation_jobs_course_requested_created ON ai_generation_jobs(course_id, requested_by, created_at)",
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_ai_generation_jobs_idempotency ON ai_generation_jobs(course_id, requested_by, idempotency_key) WHERE idempotency_key IS NOT NULL",
        "CREATE INDEX IF NOT EXISTS ix_ai_content_chunks_course_block_created ON ai_content_chunks(course_id, block_id, created_at)",
        "CREATE INDEX IF NOT EXISTS ix_ai_content_chunks_course_source_created ON ai_content_chunks(course_id, source_type, created_at)",
        "CREATE INDEX IF NOT EXISTS ix_ai_content_chunks_course_topic ON ai_content_chunks(course_id, topic_id)",
        "CREATE INDEX IF NOT EXISTS ix_ai_course_sync_course_parent_type ON ai_course_sync_state(course_id, parent_block_id, block_type)",
        "CREATE INDEX IF NOT EXISTS ix_ai_course_sync_course_status_synced ON ai_course_sync_state(course_id, sync_status, last_synced_at)",
        "CREATE INDEX IF NOT EXISTS ix_ai_topics_course_importance ON ai_topics(course_id, importance_score)",
        "CREATE INDEX IF NOT EXISTS ix_ai_course_libraries_course_difficulty_status ON ai_course_libraries(course_id, difficulty, status)",
        "CREATE INDEX IF NOT EXISTS ix_ai_usage_log_course_feature_created ON ai_usage_log(course_id, feature, created_at)",
        "CREATE INDEX IF NOT EXISTS ix_ai_usage_log_course_model_created ON ai_usage_log(course_id, model_provider, model_name, created_at)",
        "CREATE INDEX IF NOT EXISTS ix_ai_usage_log_course_user_created ON ai_usage_log(course_id, user_id, created_at)",
        "CREATE INDEX IF NOT EXISTS ix_ai_publish_batches_course_status_created ON ai_publish_batches(course_id, status, created_at)",
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_ai_publish_batches_idempotency ON ai_publish_batches(course_id, actor_id, mode, idempotency_key) WHERE idempotency_key IS NOT NULL",
        "CREATE INDEX IF NOT EXISTS ix_ai_publish_items_course_status_created ON ai_publish_batch_items(course_id, status, created_at)",
        "CREATE INDEX IF NOT EXISTS ix_ai_publish_items_question_status ON ai_publish_batch_items(question_id, status)",
    ]
    for statement in index_statements:
        op.execute(statement)


def downgrade() -> None:
    # Keep columns and indexes on downgrade to avoid losing production audit/state.
    pass
