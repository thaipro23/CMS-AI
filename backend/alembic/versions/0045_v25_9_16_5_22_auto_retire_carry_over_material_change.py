"""v25.9.16.5.22 auto retire carry-over questions after material change

Revision ID: 0045_v25_9_16_5_22_auto_retire
Revises: 0044_v25_9_16_5_21_scale
Create Date: 2026-06-24

Runtime-only hardening. The schema already has the fields needed to track cloned
questions, retired state, material chunks and operation jobs. This migration is
kept as a no-op revision so deployments can verify the code/database pair.
"""
from __future__ import annotations

revision = '0045_v25_9_16_5_22_auto_retire'
down_revision = '0044_v25_9_16_5_21_scale'
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
