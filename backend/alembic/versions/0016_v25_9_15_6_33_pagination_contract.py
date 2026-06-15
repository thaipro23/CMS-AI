"""v25.9.15.6.33 pagination contract

Revision ID: 0016_v25_9_15_6_33
Revises: 0015_v25_9_15_6_32
Create Date: 2026-06-12

This release changes API contracts and frontend compatibility wrappers only.
No schema change is required; the no-op revision marks the deployed version
in Alembic history so operators can verify rollout order.
"""

from alembic import op  # noqa: F401
import sqlalchemy as sa  # noqa: F401


revision = '0016_v25_9_15_6_33'
down_revision = '0015_v25_9_15_6_32'
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
