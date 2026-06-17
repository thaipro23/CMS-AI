"""v25.9.16.2.1 Academic core safety hotfix

Revision ID: 0030_v25_9_16_2_1_academic_core_safety_hotfix
Revises: 0029_v25_9_16_2_academic_course_mapping
Create Date: 2026-06-17
"""
from __future__ import annotations

revision = '0030_v25_9_16_2_1_academic_core_safety_hotfix'
down_revision = '0029_v25_9_16_2_academic_course_mapping'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Source/runtime safety hotfix only. Schema is unchanged.
    pass


def downgrade() -> None:
    pass
