"""v25.9.15.6.38.8.4 search index drilldown performance guard marker

Revision ID: 0036_v25_9_15_6_38_8_4
Revises: 0035_v25_9_15_6_38_8_3
Create Date: 2026-06-17
"""

from alembic import op  # noqa: F401
import sqlalchemy as sa  # noqa: F401

revision = '0036_v25_9_15_6_38_8_4'
down_revision = '0035_v25_9_15_6_38_8_3'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Compatibility marker. The corresponding release was frontend/service-only
    # for this deployment path and does not require schema changes.
    pass


def downgrade() -> None:
    pass
