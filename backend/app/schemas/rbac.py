from __future__ import annotations

from datetime import datetime
from pydantic import BaseModel, Field, field_validator

VALID_ROLE_CODES = {'SYSTEM_ADMIN', 'DEPARTMENT_HEAD', 'SUBJECT_OWNER', 'QUESTION_REVIEWER', 'CAMPUS_MANAGER'}
VALID_SCOPE_TYPES = {'SYSTEM', 'DEPARTMENT', 'SUBJECT', 'SUBJECT_VERSION', 'CHAPTER', 'COURSE', 'CAMPUS'}


class RBACRoleOut(BaseModel):
    code: str
    name: str
    description: str = ''
    rank: int
    status: str

    class Config:
        from_attributes = True


class RBACPermissionOut(BaseModel):
    code: str
    name: str
    group_code: str = 'general'

    class Config:
        from_attributes = True


class RoleAssignmentCreate(BaseModel):
    user_id: str = Field(min_length=1, max_length=255)
    email: str | None = Field(default=None, max_length=255)
    role_code: str
    scope_type: str
    scope_id: str = Field(default='*', max_length=255)
    grant_reason: str = ''
    sync_openedx: bool = False

    @field_validator('role_code')
    @classmethod
    def validate_role_code(cls, value: str) -> str:
        value = value.strip().upper()
        if value not in VALID_ROLE_CODES:
            raise ValueError(f'role_code không hợp lệ: {value}')
        return value

    @field_validator('scope_type')
    @classmethod
    def validate_scope_type(cls, value: str) -> str:
        value = value.strip().upper()
        if value not in VALID_SCOPE_TYPES:
            raise ValueError(f'scope_type không hợp lệ: {value}')
        return value

    @field_validator('scope_id')
    @classmethod
    def normalize_scope_id(cls, value: str) -> str:
        return (value or '*').strip() or '*'


class RoleAssignmentRevoke(BaseModel):
    revoke_reason: str = ''


class RoleAssignmentOut(BaseModel):
    id: str
    user_id: str
    email: str | None = None
    role_code: str
    role_name: str | None = None
    scope_type: str
    scope_id: str
    scope_label: str | None = None
    granted_by: str | None = None
    grant_reason: str = ''
    metadata_json: dict | None = None
    revoked_at: datetime | None = None
    revoked_by: str | None = None
    revoke_reason: str = ''
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class RoleAssignmentListOut(BaseModel):
    items: list[RoleAssignmentOut]
    total: int


class EffectiveRBACOut(BaseModel):
    user_id: str
    legacy_role: str
    effective_legacy_role: str
    permissions: list[str]
    assignments: list[RoleAssignmentOut]


class RBACBootstrapOut(BaseModel):
    ok: bool
    created: bool
    message: str
    assignment: RoleAssignmentOut | None = None


class RoleAssignmentImportRowOut(BaseModel):
    row_index: int
    status: str
    message: str
    user_id: str = ''
    email: str | None = None
    role_code: str = ''
    scope_type: str = ''
    scope_id: str = ''
    scope_label: str | None = None
    assignment: RoleAssignmentOut | None = None


class RoleAssignmentImportOut(BaseModel):
    ok: bool
    dry_run: bool
    total_rows: int
    valid_rows: int
    created_count: int
    skipped_count: int
    failed_count: int
    rows: list[RoleAssignmentImportRowOut]
