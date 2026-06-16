"""v25.9.15.6.38.8 product ux/ui redesign foundation marker

Revision ID: 0032_v25_9_15_6_38_8
Revises: 0031_v25_9_15_6_38_6
Create Date: 2026-06-16
"""
from alembic import op
import sqlalchemy as sa

revision: str = '0032_v25_9_15_6_38_8'
down_revision: str | None = '0031_v25_9_15_6_38_6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Frontend-only UX/UI redesign marker. No schema change.
    pass


def downgrade() -> None:
    pass
