"""v25.9.16.4.4 academic security and scale hardening

Revision ID: 0042_v25_9_16_4_4_hardening
Revises: 0041_v25_9_16_3_6_cleanup
Create Date: 2026-06-19
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = '0042_v25_9_16_4_4_hardening'
down_revision = '0041_v25_9_16_3_6_cleanup'
branch_labels = None
depends_on = None


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return any(col.get('name') == column for col in inspector.get_columns(table))


def _has_index(table: str, index_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return any(idx.get('name') == index_name for idx in inspector.get_indexes(table))


def upgrade() -> None:
    bind = op.get_bind()

    # Make legacy Alembic databases safe before writing this long revision id.
    bind.exec_driver_sql(
        "ALTER TABLE IF EXISTS alembic_version ALTER COLUMN version_num TYPE VARCHAR(255)"
    )

    table = 'academic_student_learning_snapshots'
    if not _has_column(table, 'enrollment_synced_at'):
        op.add_column(table, sa.Column('enrollment_synced_at', sa.DateTime(), nullable=True))
    if not _has_column(table, 'learning_synced_at'):
        op.add_column(table, sa.Column('learning_synced_at', sa.DateTime(), nullable=True))
    if not _has_index(table, 'ix_academic_learning_enrollment_synced_at'):
        op.create_index('ix_academic_learning_enrollment_synced_at', table, ['enrollment_synced_at'])
    if not _has_index(table, 'ix_academic_learning_learning_synced_at'):
        op.create_index('ix_academic_learning_learning_synced_at', table, ['learning_synced_at'])

    # Backfill split timestamps best-effort from old last_synced_at so old dashboards remain readable.
    bind.exec_driver_sql(
        "UPDATE academic_student_learning_snapshots "
        "SET learning_synced_at = last_synced_at "
        "WHERE learning_synced_at IS NULL "
        "AND (progress_percent IS NOT NULL OR grade_percent IS NOT NULL OR total_blocks IS NOT NULL OR completed_blocks IS NOT NULL)"
    )
    bind.exec_driver_sql(
        "UPDATE academic_student_learning_snapshots "
        "SET enrollment_synced_at = last_synced_at "
        "WHERE enrollment_synced_at IS NULL AND last_synced_at IS NOT NULL"
    )

    # PostgreSQL UNIQUE treats NULL as distinct. Disable duplicate active course mappings first,
    # then enforce uniqueness on the effective scope using COALESCE.
    bind.exec_driver_sql(
        """
        UPDATE academic_course_mappings m
        SET active = FALSE, updated_at = NOW(), note = COALESCE(NULLIF(note, ''), '') ||
            CASE WHEN COALESCE(note, '') = '' THEN '' ELSE E'\n' END ||
            'Auto-disabled duplicate active mapping by v25.9.16.4.4 migration'
        WHERE active = TRUE
          AND id NOT IN (
            SELECT id FROM (
              SELECT DISTINCT ON (
                term_id,
                subject_id,
                COALESCE(block_id, ''),
                COALESCE(campus, ''),
                COALESCE(branch, '')
              ) id
              FROM academic_course_mappings
              WHERE active = TRUE
              ORDER BY
                term_id,
                subject_id,
                COALESCE(block_id, ''),
                COALESCE(campus, ''),
                COALESCE(branch, ''),
                updated_at DESC NULLS LAST,
                created_at DESC NULLS LAST,
                id DESC
            ) keepers
          )
        """
    )
    if not _has_index('academic_course_mappings', 'uq_academic_course_mapping_effective_scope_active'):
        bind.exec_driver_sql(
            """
            CREATE UNIQUE INDEX uq_academic_course_mapping_effective_scope_active
            ON academic_course_mappings (
                term_id,
                subject_id,
                COALESCE(block_id, ''),
                COALESCE(campus, ''),
                COALESCE(branch, '')
            )
            WHERE active = TRUE
            """
        )


def downgrade() -> None:
    bind = op.get_bind()
    if _has_index('academic_course_mappings', 'uq_academic_course_mapping_effective_scope_active'):
        bind.exec_driver_sql('DROP INDEX IF EXISTS uq_academic_course_mapping_effective_scope_active')
    table = 'academic_student_learning_snapshots'
    if _has_index(table, 'ix_academic_learning_learning_synced_at'):
        op.drop_index('ix_academic_learning_learning_synced_at', table_name=table)
    if _has_index(table, 'ix_academic_learning_enrollment_synced_at'):
        op.drop_index('ix_academic_learning_enrollment_synced_at', table_name=table)
    if _has_column(table, 'learning_synced_at'):
        op.drop_column(table, 'learning_synced_at')
    if _has_column(table, 'enrollment_synced_at'):
        op.drop_column(table, 'enrollment_synced_at')
