"""v25.9.16.2 Academic AP to Open edX course mapping

Revision ID: 0029_v25_9_16_2_academic_course_mapping
Revises: 0028_v25_9_16_1_ap_username_mapping
Create Date: 2026-06-17
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = '0029_v25_9_16_2_academic_course_mapping'
down_revision = '0028_v25_9_16_1_ap_username_mapping'
branch_labels = None
depends_on = None


def _add_column_if_missing(table: str, column: sa.Column) -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing = {item['name'] for item in inspector.get_columns(table)}
    if column.name not in existing:
        op.add_column(table, column)


def _drop_column_if_exists(table: str, column_name: str) -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing = {item['name'] for item in inspector.get_columns(table)}
    if column_name in existing:
        op.drop_column(table, column_name)


def _create_index_if_missing(name: str, table: str, columns: list[str]) -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing = {item['name'] for item in inspector.get_indexes(table)}
    if name not in existing:
        op.create_index(name, table, columns)


def _drop_index_if_exists(name: str, table: str) -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing = {item['name'] for item in inspector.get_indexes(table)}
    if name in existing:
        op.drop_index(name, table_name=table)


def upgrade() -> None:
    _add_column_if_missing('academic_course_mappings', sa.Column('openedx_course_title', sa.String(length=255), nullable=True))
    _add_column_if_missing('academic_course_mappings', sa.Column('validation_status', sa.String(length=50), nullable=False, server_default='not_validated'))
    _add_column_if_missing('academic_course_mappings', sa.Column('validation_json', sa.JSON(), nullable=True))
    _add_column_if_missing('academic_course_mappings', sa.Column('validated_at', sa.DateTime(), nullable=True))
    _add_column_if_missing('academic_course_mappings', sa.Column('created_by', sa.String(length=255), nullable=True))
    _add_column_if_missing('academic_course_mappings', sa.Column('updated_by', sa.String(length=255), nullable=True))
    _add_column_if_missing('academic_course_mappings', sa.Column('note', sa.Text(), nullable=False, server_default=''))

    _add_column_if_missing('academic_class_course_mappings', sa.Column('openedx_course_title', sa.String(length=255), nullable=True))
    _add_column_if_missing('academic_class_course_mappings', sa.Column('mapping_source', sa.String(length=50), nullable=False, server_default='class_override'))
    _add_column_if_missing('academic_class_course_mappings', sa.Column('validation_status', sa.String(length=50), nullable=False, server_default='not_validated'))
    _add_column_if_missing('academic_class_course_mappings', sa.Column('validation_json', sa.JSON(), nullable=True))
    _add_column_if_missing('academic_class_course_mappings', sa.Column('validated_at', sa.DateTime(), nullable=True))
    _add_column_if_missing('academic_class_course_mappings', sa.Column('created_by', sa.String(length=255), nullable=True))
    _add_column_if_missing('academic_class_course_mappings', sa.Column('updated_by', sa.String(length=255), nullable=True))
    _add_column_if_missing('academic_class_course_mappings', sa.Column('note', sa.Text(), nullable=False, server_default=''))

    _create_index_if_missing('ix_academic_course_mappings_course_active', 'academic_course_mappings', ['openedx_course_id', 'active'])
    _create_index_if_missing('ix_academic_course_mappings_validation_status', 'academic_course_mappings', ['validation_status'])
    _create_index_if_missing('ix_academic_course_mappings_created_by', 'academic_course_mappings', ['created_by'])
    _create_index_if_missing('ix_academic_class_course_mappings_course_active', 'academic_class_course_mappings', ['openedx_course_id', 'active'])
    _create_index_if_missing('ix_academic_class_course_mappings_cohort_active', 'academic_class_course_mappings', ['openedx_cohort_name', 'active'])
    _create_index_if_missing('ix_academic_class_course_mappings_validation_status', 'academic_class_course_mappings', ['validation_status'])
    _create_index_if_missing('ix_academic_class_course_mappings_mapping_source', 'academic_class_course_mappings', ['mapping_source'])


def downgrade() -> None:
    _drop_index_if_exists('ix_academic_class_course_mappings_mapping_source', 'academic_class_course_mappings')
    _drop_index_if_exists('ix_academic_class_course_mappings_validation_status', 'academic_class_course_mappings')
    _drop_index_if_exists('ix_academic_class_course_mappings_cohort_active', 'academic_class_course_mappings')
    _drop_index_if_exists('ix_academic_class_course_mappings_course_active', 'academic_class_course_mappings')
    _drop_index_if_exists('ix_academic_course_mappings_created_by', 'academic_course_mappings')
    _drop_index_if_exists('ix_academic_course_mappings_validation_status', 'academic_course_mappings')
    _drop_index_if_exists('ix_academic_course_mappings_course_active', 'academic_course_mappings')

    for column in ['note', 'updated_by', 'created_by', 'validated_at', 'validation_json', 'validation_status', 'mapping_source', 'openedx_course_title']:
        _drop_column_if_exists('academic_class_course_mappings', column)
    for column in ['note', 'updated_by', 'created_by', 'validated_at', 'validation_json', 'validation_status', 'openedx_course_title']:
        _drop_column_if_exists('academic_course_mappings', column)
