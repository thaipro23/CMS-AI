"""v25.9.13.2 usage log and publish safety compatibility

Revision ID: 0004_v25_9_13_2
Revises: 0003_v25_9_9_readiness
Create Date: 2026-05-27
"""
from alembic import op

revision = '0004_v25_9_13_2'
down_revision = '0003_v25_9_9_readiness'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Existing dev/prod volumes may have ai_usage_log from older releases. Newer
    # SQLAlchemy models select these columns on /users/analytics and dashboard pages.
    for statement in [
        "ALTER TABLE ai_usage_log ADD COLUMN IF NOT EXISTS cached_input_tokens INTEGER DEFAULT 0",
        "ALTER TABLE ai_usage_log ADD COLUMN IF NOT EXISTS uncached_input_tokens INTEGER DEFAULT 0",
        "ALTER TABLE ai_usage_log ADD COLUMN IF NOT EXISTS cost_vnd DOUBLE PRECISION DEFAULT 0",
        "ALTER TABLE ai_usage_log ADD COLUMN IF NOT EXISTS token_source VARCHAR(255)",
        "ALTER TABLE ai_usage_log ADD COLUMN IF NOT EXISTS raw_usage_json TEXT",
        "ALTER TABLE ai_usage_log ADD COLUMN IF NOT EXISTS raw_error TEXT",
    ]:
        op.execute(statement)


def downgrade() -> None:
    # Keep usage history columns on downgrade.
    pass
