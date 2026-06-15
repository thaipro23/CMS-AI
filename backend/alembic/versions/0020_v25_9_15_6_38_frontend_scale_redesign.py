"""v25.9.15.6.38 frontend scale redesign marker

Revision ID: 0020_v25_9_15_6_38
Revises: 0019_v25_9_15_6_37
Create Date: 2026-06-15
"""

from typing import Sequence, Union

from alembic import op  # noqa: F401
import sqlalchemy as sa  # noqa: F401

revision: str = '0020_v25_9_15_6_38'
down_revision: Union[str, None] = '0019_v25_9_15_6_37'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Frontend-only scale refactor. No schema changes.
    pass


def downgrade() -> None:
    # No schema changes to revert.
    pass
