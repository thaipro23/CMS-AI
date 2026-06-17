"""v25.9.15.6.38.6-38.8 frontend ops/product UI marker

Revision ID: 0034_v25_9_15_6_38_8
Revises: 0033_v25_9_15_6_38_5_2
Create Date: 2026-06-17
"""

from alembic import op  # noqa: F401
import sqlalchemy as sa  # noqa: F401

revision = '0034_v25_9_15_6_38_8'
down_revision = '0033_v25_9_15_6_38_5_2'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Compatibility marker. The corresponding release was frontend/service-only
    # for this deployment path and does not require schema changes.
    pass


def downgrade() -> None:
    pass
