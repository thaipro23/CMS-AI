"""v25.9.15.6.38.2.1 rbac summary visibility hotfix

Revision ID: 0023_v25_9_15_6_38_2_1
Revises: 0022_v25_9_15_6_38_2
Create Date: 2026-06-15
"""
from alembic import op
import sqlalchemy as sa

revision = '0023_v25_9_15_6_38_2_1'
down_revision = '0022_v25_9_15_6_38_2'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Code-only hotfix marker. Keeps deployed revision traceable.
    pass


def downgrade() -> None:
    pass
