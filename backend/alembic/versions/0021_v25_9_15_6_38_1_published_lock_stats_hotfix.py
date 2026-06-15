"""v25.9.15.6.38.1 published lock and stats hotfix marker

Revision ID: 0021_v25_9_15_6_38_1
Revises: 0020_v25_9_15_6_38
Create Date: 2026-06-15
"""
from typing import Sequence, Union

from alembic import op

revision: str = '0021_v25_9_15_6_38_1'
down_revision: Union[str, None] = '0020_v25_9_15_6_38'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # No schema change. This marker documents the frontend/backend hotfix that
    # locks published Bank Version UI/actions and auto-heals missing summary rows.
    pass


def downgrade() -> None:
    pass
