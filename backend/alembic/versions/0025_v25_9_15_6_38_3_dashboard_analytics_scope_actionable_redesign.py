"""v25.9.15.6.38.3 dashboard analytics scope actionable redesign

Revision ID: 0025_v25_9_15_6_38_3
Revises: 0024_v25_9_15_6_38_2_3
Create Date: 2026-06-15
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = '0025_v25_9_15_6_38_3'
down_revision: Union[str, None] = '0024_v25_9_15_6_38_2_3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Frontend/API redesign only. No schema change required.
    pass


def downgrade() -> None:
    pass
