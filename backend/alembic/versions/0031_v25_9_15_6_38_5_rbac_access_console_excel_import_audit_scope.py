"""v25.9.15.6.38.5 RBAC access console/excel import/audit scope marker

Revision ID: 0031_v25_9_15_6_38_5
Revises: 0026_v25_9_15_6_38_4
Create Date: 2026-06-17
"""

from alembic import op  # noqa: F401
import sqlalchemy as sa  # noqa: F401

revision = '0031_v25_9_15_6_38_5'
down_revision = '0026_v25_9_15_6_38_4'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Compatibility marker. The corresponding release was frontend/service-only
    # for this deployment path and does not require schema changes.
    pass


def downgrade() -> None:
    pass
