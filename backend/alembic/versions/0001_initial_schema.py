"""initial schema from SQLAlchemy metadata

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-05-06
"""
from alembic import op
from app.db.session import Base
from app.models import (  # noqa: F401
    audit,
    cost,
    course,
    generation_batch,
    generation_cache,
    job,
    publish,
    question,
    token_calibration,
)

revision = '0001_initial_schema'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)


def downgrade() -> None:
    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind)
