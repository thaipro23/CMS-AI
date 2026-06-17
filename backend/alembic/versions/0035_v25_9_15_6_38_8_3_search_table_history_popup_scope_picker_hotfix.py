"""v25.9.15.6.38.8.3 search table/history popup/scope picker marker

Revision ID: 0035_v25_9_15_6_38_8_3
Revises: 0034_v25_9_15_6_38_8
Create Date: 2026-06-17
"""

from alembic import op  # noqa: F401
import sqlalchemy as sa  # noqa: F401

revision = '0035_v25_9_15_6_38_8_3'
down_revision = '0034_v25_9_15_6_38_8'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Compatibility marker. The corresponding release was frontend/service-only
    # for this deployment path and does not require schema changes.
    pass


def downgrade() -> None:
    pass
