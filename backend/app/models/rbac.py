from __future__ import annotations

import uuid
from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.db.session import Base


class RBACRole(Base):
    __tablename__ = 'ai_rbac_roles'

    code: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, default='')
    rank: Mapped[int] = mapped_column(Integer, default=0, index=True)
    status: Mapped[str] = mapped_column(String(50), default='active', index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class RBACPermission(Base):
    __tablename__ = 'ai_rbac_permissions'

    code: Mapped[str] = mapped_column(String(128), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, default='')
    group_code: Mapped[str] = mapped_column(String(64), default='general', index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class RBACRolePermission(Base):
    __tablename__ = 'ai_rbac_role_permissions'

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    role_code: Mapped[str] = mapped_column(String(64), ForeignKey('ai_rbac_roles.code'), index=True)
    permission_code: Mapped[str] = mapped_column(String(128), ForeignKey('ai_rbac_permissions.code'), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint('role_code', 'permission_code', name='uq_ai_rbac_role_permission'),
        Index('ix_ai_rbac_role_permissions_role_perm', 'role_code', 'permission_code'),
    )


class UserRoleAssignment(Base):
    __tablename__ = 'ai_user_role_assignments'

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(255), index=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    role_code: Mapped[str] = mapped_column(String(64), ForeignKey('ai_rbac_roles.code'), index=True)
    scope_type: Mapped[str] = mapped_column(String(32), index=True)  # SYSTEM | DEPARTMENT | SUBJECT | SUBJECT_VERSION | CHAPTER | COURSE
    scope_id: Mapped[str] = mapped_column(String(255), default='*', index=True)
    granted_by: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    grant_reason: Mapped[str] = mapped_column(Text, default='')
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True, default=dict)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    revoked_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    revoke_reason: Mapped[str] = mapped_column(Text, default='')
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint('user_id', 'role_code', 'scope_type', 'scope_id', 'revoked_at', name='uq_ai_user_role_assignment_activeish'),
        Index('ix_ai_user_role_assignments_user_active', 'user_id', 'revoked_at'),
        Index('ix_ai_user_role_assignments_scope_active', 'scope_type', 'scope_id', 'revoked_at'),
        Index('ix_ai_user_role_assignments_role_scope', 'role_code', 'scope_type', 'scope_id'),
    )
