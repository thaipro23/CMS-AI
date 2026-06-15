"""v25.9.15.6.38.2 RBAC scope enforcement audit marker

Revision ID: 0022_v25_9_15_6_38_2
Revises: 0021_v25_9_15_6_38_1
Create Date: 2026-06-15
"""
from typing import Sequence, Union

revision: str = '0022_v25_9_15_6_38_2'
down_revision: Union[str, None] = '0021_v25_9_15_6_38_1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # No schema change. This marker records the RBAC scope enforcement audit:
    # non-system users only see parent nodes and child nodes within their exact
    # business scope, while Open edX remains a separate technical permission layer.
    pass


def downgrade() -> None:
    pass
