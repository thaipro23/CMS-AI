"""Allow an explicit Other learning platform.

Revision ID: 0063_subject_platform_other
Revises: 0062_v25_9_16_7_2_64_40
"""
from alembic import op

revision = '0063_subject_platform_other'
down_revision = '0062_v25_9_16_7_2_64_40'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('academic_subject_deliveries') as batch:
        batch.drop_constraint('ck_academic_subject_delivery_platform', type_='check')
        batch.create_check_constraint('ck_academic_subject_delivery_platform', "learning_platform IS NULL OR learning_platform IN ('cms', 'udemy', 'other')")


def downgrade():
    # Do not silently turn an explicit Other assignment into an unassigned one.
    with op.batch_alter_table('academic_subject_deliveries') as batch:
        batch.drop_constraint('ck_academic_subject_delivery_platform', type_='check')
        batch.create_check_constraint('ck_academic_subject_delivery_platform', "learning_platform IS NULL OR learning_platform IN ('cms', 'udemy')")
