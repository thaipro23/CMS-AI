"""v25.9.16.2.1 Academic core safety hotfix

Revision ID: 0030_v25_9_16_2_1_safety
Revises: 0029_v25_9_16_2_course_map
Create Date: 2026-06-17
"""
from __future__ import annotations

revision = '0030_v25_9_16_2_1_safety'
down_revision = '0029_v25_9_16_2_course_map'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Source/runtime safety hotfix only. Schema is unchanged.
    pass


def downgrade() -> None:
    pass
