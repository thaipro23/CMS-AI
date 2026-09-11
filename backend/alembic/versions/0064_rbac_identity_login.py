"""Add Dash user profiles and last-login tracking.

Revision ID: 0064_rbac_identity_login
Revises: 0063_subject_platform_other
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = '0064_rbac_identity_login'
down_revision = '0063_subject_platform_other'
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if 'ai_user_profiles' not in inspector.get_table_names():
        op.create_table(
            'ai_user_profiles',
            sa.Column('user_id', sa.String(length=255), nullable=False),
            sa.Column('username', sa.String(length=255), nullable=True),
            sa.Column('email', sa.String(length=255), nullable=True),
            sa.Column('display_name', sa.String(length=255), nullable=True),
            sa.Column('last_login_at', sa.DateTime(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.Column('updated_at', sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint('user_id'),
        )
    existing = {index['name'] for index in inspect(bind).get_indexes('ai_user_profiles')}
    for name, columns in {
        'ix_ai_user_profiles_username': ['username'],
        'ix_ai_user_profiles_email': ['email'],
        'ix_ai_user_profiles_last_login': ['last_login_at'],
    }.items():
        if name not in existing:
            op.create_index(name, 'ai_user_profiles', columns)


def downgrade() -> None:
    bind = op.get_bind()
    if 'ai_user_profiles' not in inspect(bind).get_table_names():
        return
    for name in ('ix_ai_user_profiles_last_login', 'ix_ai_user_profiles_email', 'ix_ai_user_profiles_username'):
        try:
            op.drop_index(name, table_name='ai_user_profiles')
        except Exception:
            pass
    op.drop_table('ai_user_profiles')
