"""v25.9.15.6.38.2.2 rbac summary nameerror hotfix

Revision ID: 0024_v25_9_15_6_38_2_2
Revises: 0023_v25_9_15_6_38_2_1
Create Date: 2026-06-15
"""
from alembic import op
import sqlalchemy as sa

revision = '0024_v25_9_15_6_38_2_2'
down_revision = '0023_v25_9_15_6_38_2_1'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Code-only hotfix marker. Fixes Bank dashboard summary NameError.
    pass


def downgrade() -> None:
    pass
