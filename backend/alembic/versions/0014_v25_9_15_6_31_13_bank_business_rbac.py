"""v25.9.15.6.31.13 bank business RBAC roles

Revision ID: 0014_v25_9_15_6_31_13
Revises: 0013_v25_9_15_3_2
Create Date: 2026-06-12
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = '0014_v25_9_15_6_31_13'
down_revision = '0013_v25_9_15_3_2'
branch_labels = None
depends_on = None

ROLES = [
    ('SYSTEM_ADMIN', 'Quản trị web', 'Full quyền AI Server và toàn bộ scope.', 100),
    ('DEPARTMENT_HEAD', 'Trưởng bộ môn', 'Full quyền nghiệp vụ trong bộ môn được giao.', 70),
    ('SUBJECT_OWNER', 'Chủ môn', 'Full quyền nghiệp vụ trong môn được giao.', 50),
    ('QUESTION_REVIEWER', 'Người duyệt câu hỏi', 'Duyệt/sửa câu hỏi trong môn/chapter được giao.', 20),
]

PERMISSIONS = [
    ('user.manage_all', 'Quản lý toàn bộ người dùng', 'user'),
    ('department.manage_all', 'Quản lý toàn bộ bộ môn', 'department'),
    ('department.assign_head', 'Gán Trưởng bộ môn', 'department'),
    ('subject.create', 'Tạo môn trong scope được giao', 'subject'),
    ('subject.update', 'Cập nhật môn trong scope được giao', 'subject'),
    ('subject.assign_owner', 'Gán Chủ môn', 'subject'),
    ('reviewer.assign', 'Gán Người duyệt câu hỏi', 'review'),
    ('course.sync', 'Đồng bộ course/học liệu', 'course'),
    ('document.manage', 'Quản lý tài liệu/chunk', 'document'),
    ('question.generate', 'Tạo câu hỏi', 'question'),
    ('question.edit', 'Sửa câu hỏi', 'question'),
    ('question.approve', 'Duyệt câu hỏi', 'question'),
    ('question.reject', 'Từ chối câu hỏi', 'question'),
    ('bank.release.create', 'Chốt/tạo Bank Release', 'release'),
    ('bank.release.publish', 'Publish Bank Release sang Open edX', 'release'),
    ('quiz.preview', 'Preview Quiz Open edX', 'quiz'),
    ('quiz.create_openedx', 'Tạo Quiz Open edX', 'quiz'),
    ('quota.manage', 'Quản lý quota trong scope', 'quota'),
    ('audit.view', 'Xem audit trong scope', 'audit'),
    ('bank.view', 'Xem ngân hàng đề trong scope', 'bank'),
]

ROLE_PERMISSIONS = {
    'SYSTEM_ADMIN': [code for code, _, _ in PERMISSIONS],
    'DEPARTMENT_HEAD': [
        'bank.view', 'subject.create', 'subject.update', 'subject.assign_owner', 'reviewer.assign',
        'course.sync', 'document.manage', 'question.generate', 'question.edit', 'question.approve',
        'question.reject', 'bank.release.create', 'bank.release.publish', 'quiz.preview',
        'quiz.create_openedx', 'quota.manage', 'audit.view',
    ],
    'SUBJECT_OWNER': [
        'bank.view', 'subject.update', 'reviewer.assign', 'course.sync', 'document.manage',
        'question.generate', 'question.edit', 'question.approve', 'question.reject',
        'bank.release.create', 'bank.release.publish', 'quiz.preview', 'quiz.create_openedx', 'audit.view',
    ],
    'QUESTION_REVIEWER': ['bank.view', 'question.edit', 'question.approve', 'question.reject', 'audit.view'],
}


def _table_exists(bind, table_name: str) -> bool:
    return sa.inspect(bind).has_table(table_name)


def _index_exists(bind, table_name: str, index_name: str) -> bool:
    return _table_exists(bind, table_name) and any(item.get('name') == index_name for item in sa.inspect(bind).get_indexes(table_name))


def upgrade() -> None:
    bind = op.get_bind()

    if not _table_exists(bind, 'ai_rbac_roles'):
        op.create_table(
            'ai_rbac_roles',
            sa.Column('code', sa.String(length=64), primary_key=True),
            sa.Column('name', sa.String(length=255), nullable=False),
            sa.Column('description', sa.Text(), nullable=False, server_default=''),
            sa.Column('rank', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('status', sa.String(length=50), nullable=False, server_default='active'),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        )
        op.create_index('ix_ai_rbac_roles_rank', 'ai_rbac_roles', ['rank'])
        op.create_index('ix_ai_rbac_roles_status', 'ai_rbac_roles', ['status'])

    if not _table_exists(bind, 'ai_rbac_permissions'):
        op.create_table(
            'ai_rbac_permissions',
            sa.Column('code', sa.String(length=128), primary_key=True),
            sa.Column('name', sa.String(length=255), nullable=False),
            sa.Column('description', sa.Text(), nullable=False, server_default=''),
            sa.Column('group_code', sa.String(length=64), nullable=False, server_default='general'),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        )
        op.create_index('ix_ai_rbac_permissions_group_code', 'ai_rbac_permissions', ['group_code'])

    if not _table_exists(bind, 'ai_rbac_role_permissions'):
        op.create_table(
            'ai_rbac_role_permissions',
            sa.Column('id', sa.String(), primary_key=True),
            sa.Column('role_code', sa.String(length=64), sa.ForeignKey('ai_rbac_roles.code'), nullable=False),
            sa.Column('permission_code', sa.String(length=128), sa.ForeignKey('ai_rbac_permissions.code'), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint('role_code', 'permission_code', name='uq_ai_rbac_role_permission'),
        )
        op.create_index('ix_ai_rbac_role_permissions_role_code', 'ai_rbac_role_permissions', ['role_code'])
        op.create_index('ix_ai_rbac_role_permissions_permission_code', 'ai_rbac_role_permissions', ['permission_code'])
        op.create_index('ix_ai_rbac_role_permissions_role_perm', 'ai_rbac_role_permissions', ['role_code', 'permission_code'])

    if not _table_exists(bind, 'ai_user_role_assignments'):
        op.create_table(
            'ai_user_role_assignments',
            sa.Column('id', sa.String(), primary_key=True),
            sa.Column('user_id', sa.String(length=255), nullable=False),
            sa.Column('email', sa.String(length=255), nullable=True),
            sa.Column('role_code', sa.String(length=64), sa.ForeignKey('ai_rbac_roles.code'), nullable=False),
            sa.Column('scope_type', sa.String(length=32), nullable=False),
            sa.Column('scope_id', sa.String(length=255), nullable=False, server_default='*'),
            sa.Column('granted_by', sa.String(length=255), nullable=True),
            sa.Column('grant_reason', sa.Text(), nullable=False, server_default=''),
            sa.Column('metadata_json', sa.JSON(), nullable=True),
            sa.Column('revoked_at', sa.DateTime(), nullable=True),
            sa.Column('revoked_by', sa.String(length=255), nullable=True),
            sa.Column('revoke_reason', sa.Text(), nullable=False, server_default=''),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        )
        op.create_index('ix_ai_user_role_assignments_user_id', 'ai_user_role_assignments', ['user_id'])
        op.create_index('ix_ai_user_role_assignments_email', 'ai_user_role_assignments', ['email'])
        op.create_index('ix_ai_user_role_assignments_role_code', 'ai_user_role_assignments', ['role_code'])
        op.create_index('ix_ai_user_role_assignments_scope_type', 'ai_user_role_assignments', ['scope_type'])
        op.create_index('ix_ai_user_role_assignments_scope_id', 'ai_user_role_assignments', ['scope_id'])
        op.create_index('ix_ai_user_role_assignments_granted_by', 'ai_user_role_assignments', ['granted_by'])
        op.create_index('ix_ai_user_role_assignments_revoked_at', 'ai_user_role_assignments', ['revoked_at'])
        op.create_index('ix_ai_user_role_assignments_user_active', 'ai_user_role_assignments', ['user_id', 'revoked_at'])
        op.create_index('ix_ai_user_role_assignments_scope_active', 'ai_user_role_assignments', ['scope_type', 'scope_id', 'revoked_at'])
        op.create_index('ix_ai_user_role_assignments_role_scope', 'ai_user_role_assignments', ['role_code', 'scope_type', 'scope_id'])
        if bind.dialect.name == 'postgresql':
            op.create_index(
                'uq_ai_user_role_assignments_active',
                'ai_user_role_assignments',
                ['user_id', 'role_code', 'scope_type', 'scope_id'],
                unique=True,
                postgresql_where=sa.text('revoked_at IS NULL'),
            )

    # idempotent seed; use ON CONFLICT on PostgreSQL and regular inserts otherwise.
    if bind.dialect.name == 'postgresql':
        for code, name, description, rank in ROLES:
            bind.execute(sa.text("""
                INSERT INTO ai_rbac_roles (code, name, description, rank, status, created_at, updated_at)
                VALUES (:code, :name, :description, :rank, 'active', now(), now())
                ON CONFLICT (code) DO UPDATE SET name = EXCLUDED.name, description = EXCLUDED.description, rank = EXCLUDED.rank, updated_at = now()
            """), {'code': code, 'name': name, 'description': description, 'rank': rank})
        for code, name, group_code in PERMISSIONS:
            bind.execute(sa.text("""
                INSERT INTO ai_rbac_permissions (code, name, description, group_code, created_at)
                VALUES (:code, :name, '', :group_code, now())
                ON CONFLICT (code) DO UPDATE SET name = EXCLUDED.name, group_code = EXCLUDED.group_code
            """), {'code': code, 'name': name, 'group_code': group_code})
        import uuid
        for role_code, permissions in ROLE_PERMISSIONS.items():
            for permission_code in permissions:
                bind.execute(sa.text("""
                    INSERT INTO ai_rbac_role_permissions (id, role_code, permission_code, created_at)
                    VALUES (:id, :role_code, :permission_code, now())
                    ON CONFLICT (role_code, permission_code) DO NOTHING
                """), {'id': str(uuid.uuid4()), 'role_code': role_code, 'permission_code': permission_code})
    else:
        roles_table = sa.table('ai_rbac_roles', sa.column('code'), sa.column('name'), sa.column('description'), sa.column('rank'), sa.column('status'))
        perms_table = sa.table('ai_rbac_permissions', sa.column('code'), sa.column('name'), sa.column('description'), sa.column('group_code'))
        role_perms_table = sa.table('ai_rbac_role_permissions', sa.column('id'), sa.column('role_code'), sa.column('permission_code'))
        existing_roles = {row[0] for row in bind.execute(sa.text('SELECT code FROM ai_rbac_roles'))}
        op.bulk_insert(roles_table, [{'code': c, 'name': n, 'description': d, 'rank': r, 'status': 'active'} for c, n, d, r in ROLES if c not in existing_roles])
        existing_perms = {row[0] for row in bind.execute(sa.text('SELECT code FROM ai_rbac_permissions'))}
        op.bulk_insert(perms_table, [{'code': c, 'name': n, 'description': '', 'group_code': g} for c, n, g in PERMISSIONS if c not in existing_perms])
        import uuid
        existing_pairs = {(row[0], row[1]) for row in bind.execute(sa.text('SELECT role_code, permission_code FROM ai_rbac_role_permissions'))}
        op.bulk_insert(role_perms_table, [
            {'id': str(uuid.uuid4()), 'role_code': r, 'permission_code': p}
            for r, perms in ROLE_PERMISSIONS.items() for p in perms if (r, p) not in existing_pairs
        ])


def downgrade() -> None:
    bind = op.get_bind()
    if _table_exists(bind, 'ai_user_role_assignments'):
        if bind.dialect.name == 'postgresql' and _index_exists(bind, 'ai_user_role_assignments', 'uq_ai_user_role_assignments_active'):
            op.drop_index('uq_ai_user_role_assignments_active', table_name='ai_user_role_assignments')
        op.drop_table('ai_user_role_assignments')
    if _table_exists(bind, 'ai_rbac_role_permissions'):
        op.drop_table('ai_rbac_role_permissions')
    if _table_exists(bind, 'ai_rbac_permissions'):
        op.drop_table('ai_rbac_permissions')
    if _table_exists(bind, 'ai_rbac_roles'):
        op.drop_table('ai_rbac_roles')
