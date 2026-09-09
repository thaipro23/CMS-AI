"""Add term-first indexes for training operations.

Revision ID: 0062_v25_9_16_7_2_64_40
Revises: 0061_v25_9_16_7_2_64_39
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = '0062_v25_9_16_7_2_64_40'
down_revision = '0061_v25_9_16_7_2_64_39'
branch_labels = None
depends_on = None


CLASS_INDEX = 'ix_academic_classes_training_scope'
DELIVERY_INDEX = 'ix_academic_subject_delivery_training_scope'


def _index_names(table_name: str) -> set[str]:
    bind = op.get_bind()
    inspector = inspect(bind)
    if table_name not in inspector.get_table_names():
        return set()
    return {str(item.get('name')) for item in inspector.get_indexes(table_name) if item.get('name')}


def _create_indexes(*, concurrent: bool) -> None:
    # The UI scope is semester -> system/branch -> campus. Existing training
    # queries intentionally normalize branch/campus with lower(), therefore the
    # index uses the same expressions so PostgreSQL can use all leading keys.
    if CLASS_INDEX not in _index_names('academic_classes'):
        op.create_index(
            CLASS_INDEX,
            'academic_classes',
            [
                'term_id',
                sa.text('lower(branch)'),
                sa.text('lower(campus)'),
                'subject_id',
                'class_code',
            ],
            unique=False,
            postgresql_where=sa.text('active IS TRUE'),
            postgresql_concurrently=concurrent,
        )

    # Subject delivery joins normalize nullable branch as
    # lower(coalesce(branch, 'poly')); match that expression exactly. Deliveries
    # do not carry campus, so the next selective key is learning_platform.
    if DELIVERY_INDEX not in _index_names('academic_subject_deliveries'):
        op.create_index(
            DELIVERY_INDEX,
            'academic_subject_deliveries',
            [
                'term_id',
                sa.text("lower(coalesce(branch, 'poly'))"),
                'learning_platform',
                'subject_id',
                'block_id',
            ],
            unique=False,
            postgresql_where=sa.text('active IS TRUE'),
            postgresql_concurrently=concurrent,
        )


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == 'postgresql':
        # CREATE INDEX CONCURRENTLY avoids a long write lock on AP/student sync
        # while production is online. Alembic requires an autocommit block for it.
        with op.get_context().autocommit_block():
            _create_indexes(concurrent=True)
    else:
        _create_indexes(concurrent=False)


def _drop_indexes(*, concurrent: bool) -> None:
    if DELIVERY_INDEX in _index_names('academic_subject_deliveries'):
        op.drop_index(
            DELIVERY_INDEX,
            table_name='academic_subject_deliveries',
            postgresql_concurrently=concurrent,
        )
    if CLASS_INDEX in _index_names('academic_classes'):
        op.drop_index(
            CLASS_INDEX,
            table_name='academic_classes',
            postgresql_concurrently=concurrent,
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == 'postgresql':
        with op.get_context().autocommit_block():
            _drop_indexes(concurrent=True)
    else:
        _drop_indexes(concurrent=False)
