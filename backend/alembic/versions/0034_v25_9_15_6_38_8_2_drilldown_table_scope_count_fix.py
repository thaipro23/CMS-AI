"""v25.9.15.6.38.8.2 drilldown table scope count fix marker

Revision ID: 0034_v25_9_15_6_38_8_2
Revises: 0033_v25_9_15_6_38_8_1
Create Date: 2026-06-16
"""
from alembic import op
import sqlalchemy as sa

revision: str = '0034_v25_9_15_6_38_8_2'
down_revision: str | None = '0033_v25_9_15_6_38_8_1'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Frontend/API behavior marker. No schema change.
    pass


def downgrade() -> None:
    pass
