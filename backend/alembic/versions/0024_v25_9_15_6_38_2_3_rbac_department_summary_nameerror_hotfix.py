"""v25.9.15.6.38.2.3 RBAC department summary NameError hotfix

Revision ID: 0024_v25_9_15_6_38_2_3
Revises: 0023_v25_9_15_6_38_2_1
Create Date: 2026-06-15
"""

from collections.abc import Sequence

revision: str = "0024_v25_9_15_6_38_2_3"
down_revision: str | None = "0023_v25_9_15_6_38_2_1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
