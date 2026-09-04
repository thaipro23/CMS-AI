from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.models.rbac import RBACPermission, RBACRole, RBACRolePermission, UserRoleAssignment
from app.models.question_bank import Department, Subject, SubjectChapter, SubjectOffering, QuestionBankRelease, QuestionBankVersion
from app.core.config import settings

SYSTEM_ADMIN = 'SYSTEM_ADMIN'
DEPARTMENT_HEAD = 'DEPARTMENT_HEAD'
SUBJECT_OWNER = 'SUBJECT_OWNER'
QUESTION_REVIEWER = 'QUESTION_REVIEWER'
CAMPUS_MANAGER = 'CAMPUS_MANAGER'  # legacy alias kept for existing assignments
CAMPUS_OWNER = 'CAMPUS_OWNER'
TEACHER_ASSIGNED = 'TEACHER_ASSIGNED'

ROLE_RANK = {
    SYSTEM_ADMIN: 100,
    DEPARTMENT_HEAD: 70,
    SUBJECT_OWNER: 50,
    QUESTION_REVIEWER: 20,
    CAMPUS_MANAGER: 60,
    CAMPUS_OWNER: 60,
    TEACHER_ASSIGNED: 10,
}

ROLE_LABELS = {
    SYSTEM_ADMIN: 'Quản trị web',
    DEPARTMENT_HEAD: 'Trưởng bộ môn',
    SUBJECT_OWNER: 'Chủ môn',
    QUESTION_REVIEWER: 'Người duyệt câu hỏi',
    CAMPUS_MANAGER: 'Chủ cơ sở (legacy)',
    CAMPUS_OWNER: 'Chủ cơ sở',
    TEACHER_ASSIGNED: 'Giáo viên được phân công AP',
}

ROLE_PERMISSIONS: dict[str, set[str]] = {
    SYSTEM_ADMIN: {
        'user.manage_all', 'department.manage_all', 'department.update', 'department.assign_head', 'subject.create', 'subject.update',
        'subject.assign_owner', 'reviewer.assign', 'course.sync', 'document.manage', 'question.generate',
        'question.edit', 'question.approve', 'question.reject', 'bank.release.create', 'bank.release.publish',
        'quiz.preview', 'quiz.create_openedx', 'quota.manage', 'audit.view', 'bank.view',
        'academic.view', 'academic.manage_campus', 'view_training_reports',
        'jobs.view', 'ops.readiness.view', 'rbac.view',
    },
    # QUIZ_BANK domain: question bank / quiz roles only. They do not grant
    # Student Ops visibility unless the user is separately assigned there.
    DEPARTMENT_HEAD: {
        'bank.view', 'department.update', 'subject.create', 'subject.update', 'subject.assign_owner', 'reviewer.assign', 'course.sync',
        'document.manage', 'question.generate', 'question.edit', 'question.approve', 'question.reject',
        'bank.release.create', 'bank.release.publish', 'quiz.preview', 'quiz.create_openedx', 'quota.manage', 'audit.view',
        'jobs.view', 'rbac.view',
    },
    SUBJECT_OWNER: {
        'bank.view', 'subject.update', 'reviewer.assign', 'course.sync', 'document.manage', 'question.generate',
        'question.edit', 'question.approve', 'question.reject', 'bank.release.create', 'bank.release.publish',
        'quiz.preview', 'quiz.create_openedx', 'audit.view', 'jobs.view', 'rbac.view',
    },
    QUESTION_REVIEWER: {'bank.view', 'question.edit', 'question.approve', 'question.reject', 'audit.view', 'jobs.view'},
    # STUDENT_OPS domain: campus/class/student operations only. These roles do
    # not grant Question Bank/Quiz permissions.
    CAMPUS_OWNER: {'academic.view', 'academic.manage_campus', 'view_training_reports', 'jobs.view'},
    CAMPUS_MANAGER: {'academic.view', 'academic.manage_campus', 'view_training_reports', 'jobs.view'},
    TEACHER_ASSIGNED: {'academic.view', 'view_training_reports'},
}


CAMPUS_OWNER_ALL_CAMPUS_PERMISSIONS: set[str] = {
    'department.manage_all', 'subject.create', 'subject.update', 'course.sync',
    'rbac.view',
}


def _is_all_campus_assignment(assignment: Any) -> bool:
    role_code = str(getattr(assignment, 'role_code', '') or '').upper()
    scope_type = str(getattr(assignment, 'scope_type', '') or '').upper()
    scope_id = str(getattr(assignment, 'scope_id', '') or '').strip()
    return role_code in {CAMPUS_OWNER, CAMPUS_MANAGER} and (
        scope_type == 'SYSTEM' or (scope_type == 'CAMPUS' and scope_id == '*')
    )

LEGACY_PERMISSION_BRIDGE: dict[str, set[str]] = {
    'view_dashboard': {'bank.view', 'audit.view', 'academic.view', 'view_training_reports'},
    'view_questions': {'bank.view', 'question.edit', 'question.approve', 'question.reject'},
    'sync_course': {'course.sync'},
    'estimate_cost': {'question.generate', 'document.manage', 'bank.view'},
    'generate_questions': {'question.generate'},
    'edit_questions': {'subject.update', 'document.manage', 'question.edit'},
    'delete_questions': {'question.edit'},
    'review_questions': {'question.approve', 'question.reject'},
    'publish_questions': {'bank.release.create', 'bank.release.publish', 'quiz.preview', 'quiz.create_openedx'},
    'export_questions': {'bank.release.create', 'bank.release.publish'},
    'publish_to_openedx': {'bank.release.publish', 'quiz.create_openedx'},
    'manage_budget': {'quota.manage'},
    'manage_settings': {'user.manage_all', 'department.manage_all', 'department.assign_head'},
    'manage_department': {'department.manage_all', 'department.update'},
    'view_user_analytics': {'user.manage_all'},
    'view_training_reports': {'academic.view', 'view_training_reports'},
    'manage_training_deadlines': {'academic.manage_campus'},
    'view_jobs': {'jobs.view'},
    'view_ops_readiness': {'ops.readiness.view'},
    'view_rbac': {'rbac.view', 'user.manage_all', 'subject.assign_owner', 'reviewer.assign'},
}


ROLE_TO_LEGACY = {
    # v25.9.16.7.2.64.13: do not elevate business roles into legacy teacher/admin.
    # Frontend and backend must use business_permissions for access. Legacy role
    # only remains for SYSTEM_ADMIN so old admin-only UI keeps working for real
    # Open edX superusers / explicit system admins.
    SYSTEM_ADMIN: 'admin',
    DEPARTMENT_HEAD: 'viewer',
    SUBJECT_OWNER: 'viewer',
    QUESTION_REVIEWER: 'viewer',
    CAMPUS_OWNER: 'viewer',
    CAMPUS_MANAGER: 'viewer',
    TEACHER_ASSIGNED: 'viewer',
}
LEGACY_RANK = {'viewer': 0, 'reviewer': 20, 'teacher': 50, 'admin': 100}


@dataclass(frozen=True)
class EntityScope:
    scope_type: str
    scope_id: str
    department_id: str | None = None
    subject_id: str | None = None
    subject_offering_id: str | None = None
    chapter_id: str | None = None
    class_id: str | None = None
    course_id: str | None = None


@dataclass(frozen=True)
class ScopeVisibility:
    unrestricted: bool
    parent_department_ids: set[str]
    parent_subject_ids: set[str]
    parent_offering_ids: set[str]
    broad_department_ids: set[str]
    broad_subject_ids: set[str]
    broad_offering_ids: set[str]
    exact_chapter_ids: set[str]


class BusinessRBACService:
    def __init__(self, db: Session):
        self.db = db


    def ensure_default_catalog(self) -> None:
        for code, name in ROLE_LABELS.items():
            role = self.db.get(RBACRole, code)
            if not role:
                role = RBACRole(code=code, name=name, description='', rank=ROLE_RANK.get(code, 0), status='active')
                self.db.add(role)
            else:
                role.name = name
                role.rank = ROLE_RANK.get(code, role.rank)
                role.status = role.status or 'active'
        permission_names = {
            'user.manage_all': 'Quản lý toàn bộ người dùng',
            'department.manage_all': 'Quản lý toàn bộ bộ môn',
            'department.update': 'Cập nhật bộ môn trong phạm vi được giao',
            'department.assign_head': 'Gán Trưởng bộ môn',
            'subject.create': 'Tạo môn',
            'subject.update': 'Cập nhật môn',
            'subject.assign_owner': 'Gán Chủ môn',
            'reviewer.assign': 'Gán Người duyệt',
            'course.sync': 'Đồng bộ course/học liệu',
            'document.manage': 'Quản lý tài liệu',
            'question.generate': 'Tạo câu hỏi',
            'question.edit': 'Sửa câu hỏi',
            'question.approve': 'Duyệt câu hỏi',
            'question.reject': 'Từ chối câu hỏi',
            'bank.release.create': 'Tạo Bank Release',
            'bank.release.publish': 'Publish Bank Release',
            'quiz.preview': 'Preview Quiz Open edX',
            'quiz.create_openedx': 'Tạo Quiz Open edX',
            'quota.manage': 'Quản lý quota',
            'audit.view': 'Xem audit',
            'bank.view': 'Xem ngân hàng đề',
            'academic.view': 'Xem báo cáo giáo viên/lớp trong cơ sở',
            'academic.manage_campus': 'Quản lý vận hành đào tạo theo cơ sở',
            'view_training_reports': 'Xem báo cáo quản lý giáo viên',
            'jobs.view': 'Xem tác vụ trong phạm vi được phân quyền',
            'ops.readiness.view': 'Xem readiness toàn hệ thống',
            'rbac.view': 'Xem và gán quyền trong phạm vi được phép',
        }
        for code, name in permission_names.items():
            perm = self.db.get(RBACPermission, code)
            if not perm:
                self.db.add(RBACPermission(code=code, name=name, group_code=code.split('.', 1)[0]))
            else:
                perm.name = name
                perm.group_code = code.split('.', 1)[0]
        self.db.flush()
        existing = {(row.role_code, row.permission_code) for row in self.db.query(RBACRolePermission).all()}
        for role_code, permissions in ROLE_PERMISSIONS.items():
            for permission_code in permissions:
                if (role_code, permission_code) not in existing:
                    self.db.add(RBACRolePermission(id=str(uuid.uuid4()), role_code=role_code, permission_code=permission_code))
        self.db.commit()

    def active_assignments_query(self):
        return self.db.query(UserRoleAssignment).filter(UserRoleAssignment.revoked_at.is_(None))

    def active_assignments_for_identity(self, user_id: str | None, email: str | None = None, username: str | None = None) -> list[UserRoleAssignment]:
        values = {
            str(item).strip().lower()
            for item in [user_id, username, email]
            if str(item or '').strip()
        }
        filters = []
        if values:
            filters.append(func.lower(UserRoleAssignment.user_id).in_(sorted(values)))
            filters.append(func.lower(UserRoleAssignment.email).in_(sorted(values)))
        if not filters:
            return []
        return self.active_assignments_query().filter(or_(*filters)).all()

    def active_assignments_for_user(self, user_id: str | None) -> list[UserRoleAssignment]:
        return self.active_assignments_for_identity(user_id)

    def active_assignments_for_actor(self, user: Any) -> list[UserRoleAssignment]:
        raw_claims = getattr(user, 'raw_claims', None) or {}
        return self.active_assignments_for_identity(
            getattr(user, 'user_id', None),
            email=getattr(user, 'email', None) or raw_claims.get('email'),
            username=getattr(user, 'username', None) or raw_claims.get('username'),
        )

    def is_legacy_system_admin(self, user: Any) -> bool:
        if str(getattr(user, 'role', '') or '').lower() != 'admin':
            return False
        raw_claims = getattr(user, 'raw_claims', None) or {}
        # Production SSO rule: only Open edX superuser/super_admin may become AI
        # SYSTEM_ADMIN through the CMS session bridge. `is_staff` alone is never
        # enough and AI_ADMIN group bootstrap is intentionally not trusted here.
        if raw_claims.get('is_superuser') is True or raw_claims.get('is_super_admin') is True:
            return True
        # Explicit AI system-admin tokens issued by trusted server-side flows can
        # set this claim, but generic role=admin without proof is rejected.
        if raw_claims.get('ai_system_admin') is True:
            return True
        # Keep local demo/dev usable without accidentally weakening production.
        if str(settings.app_env or '').lower() not in {'prod', 'production'} and not raw_claims:
            return True
        return False

    def is_system_admin(self, user: Any) -> bool:
        if self.is_legacy_system_admin(user):
            return True
        # A SYSTEM_ADMIN assignment is a server-side RBAC decision stored in ACMS.
        # It must remain effective for identities authenticated through the Open edX
        # session bridge. We still do NOT trust a generic client role=admin claim:
        # is_legacy_system_admin() above only accepts Open edX superuser/super_admin
        # or the explicit trusted ai_system_admin claim.
        return any(a.role_code == SYSTEM_ADMIN for a in self.active_assignments_for_actor(user))

    def effective_legacy_role_for_user(self, user_id: str, base_role: str = 'viewer', email: str | None = None, username: str | None = None) -> str:
        best = base_role if base_role in LEGACY_RANK else 'viewer'
        best_rank = LEGACY_RANK.get(best, 0)
        for assignment in self.active_assignments_for_identity(user_id, email=email, username=username):
            mapped = ROLE_TO_LEGACY.get(assignment.role_code, 'viewer')
            rank = LEGACY_RANK.get(mapped, 0)
            if rank > best_rank:
                best = mapped
                best_rank = rank
        return best

    def _has_ap_teacher_assignment(self, user: Any) -> bool:
        """Return whether the authenticated identity is an active AP-assigned teacher.

        AP is the source of truth for teacher-to-class assignment. A teacher must not
        need a duplicated TEACHER_ASSIGNED row merely to make the training pages visible.
        """
        raw_claims = getattr(user, 'raw_claims', None) or {}
        values = {
            getattr(user, 'user_id', None),
            getattr(user, 'username', None),
            getattr(user, 'email', None),
            raw_claims.get('username'),
            raw_claims.get('preferred_username'),
            raw_claims.get('email'),
        }
        names = {str(value).strip().lower() for value in values if str(value or '').strip()}
        if not names:
            return False
        try:
            from app.models.academic import AcademicTeacher, AcademicTeacherAssignment
            return self.db.query(AcademicTeacherAssignment.id).join(
                AcademicTeacher, AcademicTeacher.id == AcademicTeacherAssignment.teacher_id,
            ).filter(
                AcademicTeacher.active.is_(True),
                or_(
                    func.lower(AcademicTeacher.username).in_(sorted(names)),
                    func.lower(AcademicTeacher.email).in_(sorted(names)),
                ),
            ).first() is not None
        except Exception:
            return False

    def effective_permissions_for_user(self, user: Any) -> set[str]:
        permissions: set[str] = set()
        system_admin = self.is_system_admin(user)
        if system_admin:
            permissions.update(ROLE_PERMISSIONS[SYSTEM_ADMIN])
            permissions.update(
                str(row.code).strip()
                for row in self.db.query(RBACPermission).all()
                if str(getattr(row, 'code', '') or '').strip()
            )
        for assignment in self.active_assignments_for_actor(user):
            if assignment.role_code == SYSTEM_ADMIN and not system_admin:
                continue
            permissions.update(ROLE_PERMISSIONS.get(assignment.role_code, set()))
            if _is_all_campus_assignment(assignment):
                permissions.update(CAMPUS_OWNER_ALL_CAMPUS_PERMISSIONS)
        if self._has_ap_teacher_assignment(user):
            permissions.update(ROLE_PERMISSIONS[TEACHER_ASSIGNED])
        return permissions

    def has_any_business_permission(self, user: Any, permission: str) -> bool:
        if self.is_system_admin(user):
            return True
        wanted = LEGACY_PERMISSION_BRIDGE.get(permission, {permission})
        user_permissions = self.effective_permissions_for_user(user)
        return bool(user_permissions.intersection(wanted))

    def _subject_department_id(self, subject_id: str | None) -> str | None:
        if not subject_id:
            return None
        subject = self.db.get(Subject, subject_id)
        return subject.department_id if subject else None

    def _offering_scope(self, offering_id: str | None) -> EntityScope | None:
        if not offering_id:
            return None
        offering = self.db.get(SubjectOffering, offering_id)
        if not offering:
            return None
        department_id = offering.department_id or self._subject_department_id(offering.subject_id)
        return EntityScope('SUBJECT_VERSION', offering.id, department_id=department_id, subject_id=offering.subject_id, subject_offering_id=offering.id)

    def _chapter_scope(self, chapter_id: str | None) -> EntityScope | None:
        if not chapter_id:
            return None
        chapter = self.db.get(SubjectChapter, chapter_id)
        if not chapter:
            return None
        department_id = self._subject_department_id(chapter.subject_id)
        offering_scope = self._offering_scope(chapter.subject_offering_id) if chapter.subject_offering_id else None
        if offering_scope and offering_scope.department_id:
            department_id = offering_scope.department_id
        return EntityScope('CHAPTER', chapter.id, department_id=department_id, subject_id=chapter.subject_id, subject_offering_id=chapter.subject_offering_id, chapter_id=chapter.id)

    def entity_scope(self, scope_type: str, scope_id: str | None) -> EntityScope:
        normalized = (scope_type or 'SYSTEM').strip().upper()
        scope_id = (scope_id or '*').strip() or '*'
        if normalized == 'SYSTEM':
            return EntityScope('SYSTEM', '*')
        if normalized == 'DEPARTMENT':
            return EntityScope('DEPARTMENT', scope_id, department_id=scope_id)
        if normalized == 'SUBJECT':
            return EntityScope('SUBJECT', scope_id, department_id=self._subject_department_id(scope_id), subject_id=scope_id)
        if normalized == 'SUBJECT_VERSION':
            scope = self._offering_scope(scope_id)
            if scope:
                return scope
            return EntityScope('SUBJECT_VERSION', scope_id, subject_offering_id=scope_id)
        if normalized == 'CHAPTER':
            scope = self._chapter_scope(scope_id)
            if scope:
                return scope
            return EntityScope('CHAPTER', scope_id, chapter_id=scope_id)
        if normalized == 'CAMPUS':
            return EntityScope('CAMPUS', scope_id)
        if normalized == 'CLASS':
            return EntityScope('CLASS', scope_id, class_id=scope_id)
        if normalized == 'COURSE':
            return EntityScope('COURSE', scope_id, course_id=scope_id)
        if normalized == 'BANK_VERSION':
            bank = self.db.get(QuestionBankVersion, scope_id)
            if bank:
                return EntityScope('BANK_VERSION', scope_id, department_id=self._subject_department_id(bank.subject_id), subject_id=bank.subject_id, subject_offering_id=bank.subject_offering_id, chapter_id=bank.chapter_id)
            return EntityScope('BANK_VERSION', scope_id)
        if normalized == 'RELEASE':
            release = self.db.get(QuestionBankRelease, scope_id)
            if release:
                return EntityScope('RELEASE', scope_id, department_id=self._subject_department_id(release.subject_id), subject_id=release.subject_id, subject_offering_id=release.subject_offering_id, chapter_id=release.chapter_id)
            return EntityScope('RELEASE', scope_id)
        return EntityScope(normalized, scope_id)

    def _assignment_covers(self, assignment: UserRoleAssignment, target: EntityScope) -> bool:
        assignment_scope = self.entity_scope(assignment.scope_type, assignment.scope_id)
        if assignment_scope.scope_type == 'SYSTEM' or assignment.role_code == SYSTEM_ADMIN:
            return True
        if target.scope_type == 'SYSTEM':
            return False
        if assignment_scope.scope_type == 'DEPARTMENT':
            return bool(target.department_id and target.department_id == assignment_scope.department_id)
        if assignment_scope.scope_type == 'SUBJECT':
            return bool(target.subject_id and target.subject_id == assignment_scope.subject_id)
        if assignment_scope.scope_type == 'SUBJECT_VERSION':
            return bool(target.subject_offering_id and target.subject_offering_id == assignment_scope.subject_offering_id)
        if assignment_scope.scope_type == 'CHAPTER':
            return bool(target.chapter_id and target.chapter_id == assignment_scope.chapter_id)
        if assignment_scope.scope_type == 'COURSE':
            return bool(target.course_id and target.course_id == assignment_scope.course_id)
        if assignment_scope.scope_type == 'CAMPUS':
            return target.scope_type == 'CAMPUS' and (assignment_scope.scope_id == '*' or assignment_scope.scope_id.lower() == target.scope_id.lower())
        if assignment_scope.scope_type == 'CLASS':
            return bool(target.class_id and target.class_id == assignment_scope.scope_id)
        return assignment_scope.scope_type == target.scope_type and assignment_scope.scope_id == target.scope_id

    def has_permission(self, user: Any, permission: str, target: EntityScope | None = None) -> bool:
        if self.is_system_admin(user):
            return True
        target = target or EntityScope('SYSTEM', '*')
        for assignment in self.active_assignments_for_actor(user):
            if assignment.role_code == SYSTEM_ADMIN and not self.is_system_admin(user):
                continue
            if permission not in ROLE_PERMISSIONS.get(assignment.role_code, set()):
                continue
            if self._assignment_covers(assignment, target):
                return True
        return False

    def require_permission(self, user: Any, permission: str, scope_type: str = 'SYSTEM', scope_id: str | None = '*') -> None:
        target = self.entity_scope(scope_type, scope_id)
        if not self.has_permission(user, permission, target):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f'Không đủ quyền {permission} trong scope {target.scope_type}:{target.scope_id}',
            )

    def require_system_admin(self, user: Any) -> None:
        if not self.is_system_admin(user):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='Chỉ Quản trị web mới được thao tác toàn hệ thống')

    def can_grant(self, actor: Any, role_code: str, scope_type: str, scope_id: str) -> bool:
        if self.is_system_admin(actor):
            return True
        target = self.entity_scope(scope_type, scope_id)
        if role_code == SUBJECT_OWNER:
            return self.has_permission(actor, 'subject.assign_owner', target)
        if role_code == QUESTION_REVIEWER:
            return self.has_permission(actor, 'reviewer.assign', target)
        if role_code in {CAMPUS_MANAGER, CAMPUS_OWNER, TEACHER_ASSIGNED}:
            return self.is_system_admin(actor)
        return False

    def _validate_assignment_scope(self, role_code: str, scope_type: str, scope_id: str) -> None:
        scope_type = scope_type.upper()
        if role_code == SYSTEM_ADMIN and scope_type != 'SYSTEM':
            raise HTTPException(status_code=400, detail='SYSTEM_ADMIN chỉ được gán ở scope SYSTEM')
        if role_code == DEPARTMENT_HEAD and scope_type != 'DEPARTMENT':
            raise HTTPException(status_code=400, detail='DEPARTMENT_HEAD chỉ được gán ở scope DEPARTMENT')
        if role_code == SUBJECT_OWNER and scope_type not in {'SUBJECT', 'SUBJECT_VERSION'}:
            raise HTTPException(status_code=400, detail='SUBJECT_OWNER chỉ được gán ở scope SUBJECT hoặc SUBJECT_VERSION')
        if role_code == QUESTION_REVIEWER and scope_type not in {'SUBJECT', 'SUBJECT_VERSION', 'CHAPTER'}:
            raise HTTPException(status_code=400, detail='QUESTION_REVIEWER chỉ được gán ở scope SUBJECT/SUBJECT_VERSION/CHAPTER')
        if role_code in {CAMPUS_MANAGER, CAMPUS_OWNER} and scope_type not in {'CAMPUS', 'SYSTEM'}:
            raise HTTPException(status_code=400, detail='CAMPUS_OWNER/CAMPUS_MANAGER chỉ được gán ở scope CAMPUS hoặc SYSTEM')
        if role_code == TEACHER_ASSIGNED and scope_type not in {'CLASS', 'CAMPUS', 'SYSTEM'}:
            raise HTTPException(status_code=400, detail='TEACHER_ASSIGNED chỉ được gán ở scope CLASS/CAMPUS/SYSTEM; AP assignment vẫn là nguồn lớp chính')
        if scope_type == 'SYSTEM':
            return
        if scope_type == 'CAMPUS':
            if scope_id == '*':
                return
            from app.models.academic import AcademicCampus
            exists = self.db.query(AcademicCampus.id).filter(AcademicCampus.campus_code.ilike(scope_id)).first()
            if not exists:
                raise HTTPException(status_code=404, detail='Không tìm thấy cơ sở để gán quyền')
            return
        if scope_type == 'CLASS':
            from app.models.academic import AcademicClass
            exists = self.db.get(AcademicClass, scope_id)
            if not exists:
                raise HTTPException(status_code=404, detail='Không tìm thấy lớp để gán quyền')
            return
        if scope_type == 'DEPARTMENT' and not self.db.get(Department, scope_id):
            raise HTTPException(status_code=404, detail='Không tìm thấy bộ môn để gán quyền')
        if scope_type == 'SUBJECT' and not self.db.get(Subject, scope_id):
            raise HTTPException(status_code=404, detail='Không tìm thấy môn để gán quyền')
        if scope_type == 'SUBJECT_VERSION' and not self.db.get(SubjectOffering, scope_id):
            raise HTTPException(status_code=404, detail='Không tìm thấy phiên bản môn để gán quyền')
        if scope_type == 'CHAPTER' and not self.db.get(SubjectChapter, scope_id):
            raise HTTPException(status_code=404, detail='Không tìm thấy bài/chapter để gán quyền')

    def create_assignment(self, *, actor: Any, user_id: str, email: str | None, role_code: str, scope_type: str, scope_id: str = '*', grant_reason: str = '', sync_openedx: bool = False) -> UserRoleAssignment:
        role_code = role_code.strip().upper()
        if role_code == CAMPUS_MANAGER:
            raise HTTPException(status_code=400, detail='CAMPUS_MANAGER là role legacy; dùng CAMPUS_OWNER cho gán mới')
        scope_type = scope_type.strip().upper()
        scope_id = (scope_id or '*').strip() or '*'
        self._validate_assignment_scope(role_code, scope_type, scope_id)
        if not self.can_grant(actor, role_code, scope_type, scope_id):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='Bạn không được gán role này trong scope này')
        existing = self.active_assignments_query().filter(
            UserRoleAssignment.user_id == user_id,
            UserRoleAssignment.role_code == role_code,
            UserRoleAssignment.scope_type == scope_type,
            UserRoleAssignment.scope_id == scope_id,
        ).first()
        if existing:
            if email and not existing.email:
                existing.email = email
            if grant_reason:
                existing.grant_reason = grant_reason
            existing.metadata_json = {**(existing.metadata_json or {}), 'sync_openedx_requested': bool(sync_openedx)}
            self.db.add(existing)
            self.db.commit()
            self.db.refresh(existing)
            return existing
        item = UserRoleAssignment(
            id=str(uuid.uuid4()),
            user_id=user_id,
            email=email,
            role_code=role_code,
            scope_type=scope_type,
            scope_id=scope_id,
            granted_by=getattr(actor, 'user_id', None),
            grant_reason=grant_reason or '',
            metadata_json={'sync_openedx_requested': bool(sync_openedx)},
        )
        self.db.add(item)
        self.db.commit()
        self.db.refresh(item)
        return item

    def create_assignments_batch(
        self,
        *,
        actor: Any,
        user_id: str,
        email: str | None,
        role_code: str,
        scope_type: str,
        scope_ids: list[str],
        grant_reason: str = '',
        sync_openedx: bool = False,
    ) -> tuple[list[UserRoleAssignment], int, int]:
        role_code = role_code.strip().upper()
        if role_code == CAMPUS_MANAGER:
            raise HTTPException(status_code=400, detail='CAMPUS_MANAGER là role legacy; dùng CAMPUS_OWNER cho gán mới')
        scope_type = scope_type.strip().upper()
        normalized_ids = list(dict.fromkeys(((value or '*').strip() or '*') for value in scope_ids))
        if not normalized_ids:
            raise HTTPException(status_code=400, detail='Cần chọn ít nhất một phạm vi')
        if len(normalized_ids) > 200:
            raise HTTPException(status_code=400, detail='Mỗi lần chỉ được gán tối đa 200 phạm vi')

        # Validate the whole request before adding anything so the operation is atomic.
        for scope_id in normalized_ids:
            self._validate_assignment_scope(role_code, scope_type, scope_id)
            if not self.can_grant(actor, role_code, scope_type, scope_id):
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f'Bạn không được gán role này trong scope {scope_id}')

        existing_rows = self.active_assignments_query().filter(
            UserRoleAssignment.user_id == user_id,
            UserRoleAssignment.role_code == role_code,
            UserRoleAssignment.scope_type == scope_type,
            UserRoleAssignment.scope_id.in_(normalized_ids),
        ).all()
        existing_by_scope = {item.scope_id: item for item in existing_rows}
        items: list[UserRoleAssignment] = []
        created_count = 0
        reused_count = 0
        for scope_id in normalized_ids:
            item = existing_by_scope.get(scope_id)
            if item is not None:
                if email and not item.email:
                    item.email = email
                if grant_reason:
                    item.grant_reason = grant_reason
                item.metadata_json = {**(item.metadata_json or {}), 'sync_openedx_requested': bool(sync_openedx), 'batch_grant': True}
                reused_count += 1
            else:
                item = UserRoleAssignment(
                    id=str(uuid.uuid4()),
                    user_id=user_id,
                    email=email,
                    role_code=role_code,
                    scope_type=scope_type,
                    scope_id=scope_id,
                    granted_by=getattr(actor, 'user_id', None),
                    grant_reason=grant_reason or '',
                    metadata_json={'sync_openedx_requested': bool(sync_openedx), 'batch_grant': True},
                )
                created_count += 1
            self.db.add(item)
            items.append(item)
        try:
            self.db.commit()
            for item in items:
                self.db.refresh(item)
        except Exception:
            self.db.rollback()
            raise
        return items, created_count, reused_count

    def revoke_assignment(self, assignment_id: str, actor: Any, revoke_reason: str = '') -> UserRoleAssignment:
        item = self.db.get(UserRoleAssignment, assignment_id)
        if not item or item.revoked_at is not None:
            raise HTTPException(status_code=404, detail='Không tìm thấy assignment đang hiệu lực')
        if not self.can_grant(actor, item.role_code, item.scope_type, item.scope_id):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='Bạn không được thu hồi assignment này')
        item.revoked_at = datetime.now(timezone.utc).replace(tzinfo=None)
        item.revoked_by = getattr(actor, 'user_id', None)
        item.revoke_reason = revoke_reason or ''
        self.db.add(item)
        self.db.commit()
        self.db.refresh(item)
        return item

    def bootstrap_system_admin(self, *, user_id: str, email: str | None = None, reason: str = '') -> tuple[UserRoleAssignment | None, bool]:
        existing_admins = self.active_assignments_query().filter(UserRoleAssignment.role_code == SYSTEM_ADMIN).first()
        if existing_admins:
            return None, False
        pseudo_actor = type('Actor', (), {'user_id': 'bootstrap', 'role': 'admin'})()
        item = self.create_assignment(actor=pseudo_actor, user_id=user_id, email=email, role_code=SYSTEM_ADMIN, scope_type='SYSTEM', scope_id='*', grant_reason=reason or 'Bootstrap SYSTEM_ADMIN')
        return item, True

    def list_roles(self) -> list[RBACRole]:
        return self.db.query(RBACRole).order_by(RBACRole.rank.desc(), RBACRole.code.asc()).all()

    def list_permissions(self) -> list[RBACPermission]:
        return self.db.query(RBACPermission).order_by(RBACPermission.group_code.asc(), RBACPermission.code.asc()).all()

    def list_assignments(self, *, actor: Any, user_id: str | None = None, role_code: str | None = None, scope_type: str | None = None, scope_id: str | None = None, include_revoked: bool = False) -> list[UserRoleAssignment]:
        query = self.db.query(UserRoleAssignment)
        if not include_revoked:
            query = query.filter(UserRoleAssignment.revoked_at.is_(None))
        if user_id:
            query = query.filter(UserRoleAssignment.user_id == user_id)
        if role_code:
            query = query.filter(UserRoleAssignment.role_code == role_code.upper())
        if scope_type:
            query = query.filter(UserRoleAssignment.scope_type == scope_type.upper())
        if scope_id:
            query = query.filter(UserRoleAssignment.scope_id == scope_id)
        items = query.order_by(UserRoleAssignment.created_at.desc()).all()
        if self.is_system_admin(actor):
            return items
        # Non-system actors can only see assignments they would be able to grant/revoke.
        return [item for item in items if self.can_grant(actor, item.role_code, item.scope_type, item.scope_id) or item.user_id == getattr(actor, 'user_id', None)]

    def scope_label(self, scope_type: str, scope_id: str) -> str:
        scope_type = scope_type.upper()
        if scope_type == 'SYSTEM':
            return 'Toàn hệ thống'
        if scope_type == 'DEPARTMENT':
            item = self.db.get(Department, scope_id)
            return f'{item.code} · {item.name}' if item else scope_id
        if scope_type == 'SUBJECT':
            item = self.db.get(Subject, scope_id)
            return f'{item.code} · {item.name}' if item else scope_id
        if scope_type == 'SUBJECT_VERSION':
            item = self.db.get(SubjectOffering, scope_id)
            return f'{item.code} · {item.name or item.version_code}' if item else scope_id
        if scope_type == 'CHAPTER':
            item = self.db.get(SubjectChapter, scope_id)
            return item.title if item else scope_id
        if scope_type == 'CAMPUS':
            if scope_id == '*':
                return 'Tất cả cơ sở'
            try:
                from app.models.academic import AcademicCampus
                item = self.db.query(AcademicCampus).filter(AcademicCampus.campus_code.ilike(scope_id)).first()
                return f'{str(item.campus_code).upper()} · {item.campus_name}' if item else str(scope_id).upper()
            except Exception:
                return str(scope_id).upper()
        return scope_id

    @staticmethod
    def assignment_permission_codes(item: UserRoleAssignment) -> list[str]:
        permissions = set(ROLE_PERMISSIONS.get(item.role_code, set()))
        if _is_all_campus_assignment(item):
            permissions.update(CAMPUS_OWNER_ALL_CAMPUS_PERMISSIONS)
        return sorted(permissions)

    def serialize_assignment(self, item: UserRoleAssignment) -> dict[str, Any]:
        return {
            'id': item.id,
            'user_id': item.user_id,
            'email': item.email,
            'role_code': item.role_code,
            'role_name': ROLE_LABELS.get(item.role_code, item.role_code),
            'permission_codes': self.assignment_permission_codes(item),
            'scope_type': item.scope_type,
            'scope_id': item.scope_id,
            'scope_label': self.scope_label(item.scope_type, item.scope_id),
            'granted_by': item.granted_by,
            'grant_reason': item.grant_reason or '',
            'metadata_json': item.metadata_json or {},
            'revoked_at': item.revoked_at,
            'revoked_by': item.revoked_by,
            'revoke_reason': item.revoke_reason or '',
            'created_at': item.created_at,
            'updated_at': item.updated_at,
        }

    def _scope_covers_scope(self, parent: EntityScope, child: EntityScope) -> bool:
        """Return True when parent scope covers child scope in the Bank hierarchy.

        This is used for both write permission checks and read/navigation checks.
        A child-scoped role must not become a full parent permission, but it may
        see the parent node so the UI can render the path to the assigned leaf.
        """
        if parent.scope_type == 'SYSTEM':
            return True
        if child.scope_type == 'SYSTEM':
            return False
        if parent.scope_type == child.scope_type and parent.scope_id == child.scope_id:
            return True
        if parent.scope_type == 'DEPARTMENT':
            return bool(child.department_id and child.department_id == parent.department_id)
        if parent.scope_type == 'SUBJECT':
            return bool(child.subject_id and child.subject_id == parent.subject_id)
        if parent.scope_type == 'SUBJECT_VERSION':
            return bool(child.subject_offering_id and child.subject_offering_id == parent.subject_offering_id)
        if parent.scope_type == 'CHAPTER':
            return bool(child.chapter_id and child.chapter_id == parent.chapter_id)
        if parent.scope_type == 'COURSE':
            return bool(child.course_id and child.course_id == parent.course_id)
        if parent.scope_type == 'CAMPUS':
            return child.scope_type == 'CAMPUS' and (parent.scope_id == '*' or parent.scope_id.lower() == child.scope_id.lower())
        return False

    def is_visible_scope(self, user: Any, scope_type: str, scope_id: str | None = '*') -> bool:
        """Navigation/read visibility for parent-or-child nodes.

        DEPARTMENT_HEAD/SUBJECT_OWNER/QUESTION_REVIEWER may see parent nodes and
        owned child nodes, but this does not grant mutating permissions on the
        parent. Mutations must still call require_permission(...).
        """
        if self.is_system_admin(user):
            return True
        target = self.entity_scope(scope_type, scope_id)
        for assignment in self.active_assignments_for_actor(user):
            assigned = self.entity_scope(assignment.scope_type, assignment.scope_id)
            if self._scope_covers_scope(assigned, target) or self._scope_covers_scope(target, assigned):
                return True
        return False

    def require_visible_scope(self, user: Any, scope_type: str, scope_id: str | None = '*') -> None:
        if not self.is_visible_scope(user, scope_type, scope_id):
            target = self.entity_scope(scope_type, scope_id)
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f'Bạn không được xem scope {target.scope_type}:{target.scope_id}',
            )


    def accessible_campus_codes(self, user: Any) -> set[str] | None:
        """Academic campus visibility for teacher-management.

        None means all campuses. Empty set means no campus-level grant; the
        academic service may still expose AP-assigned teacher classes.
        """
        if self.is_system_admin(user):
            return None
        codes: set[str] = set()
        for assignment in self.active_assignments_for_actor(user):
            if assignment.role_code == SYSTEM_ADMIN:
                return None
            if assignment.role_code in {CAMPUS_MANAGER, CAMPUS_OWNER} and assignment.scope_type.upper() in {'SYSTEM', 'CAMPUS'}:
                scope_id = str(assignment.scope_id or '*').strip()
                if assignment.scope_type.upper() == 'SYSTEM' or scope_id == '*':
                    return None
                codes.add(scope_id.lower())
        return codes

    def can_manage_assignment_scores_for_campus(self, user: Any, campus_code: str | None) -> bool:
        """Deprecated in v25.9.16.7.2.64.13.

        Assignment/defense score entry is owned by an external system. AI Server
        may display read-only assignment status from snapshots/imports, but must
        not grant UI/API permission to enter or edit assignment scores.
        """
        return False

    @staticmethod
    def normalize_campus_code(value: Any) -> str:
        """Normalize campus codes for security comparisons.

        Campus scope checks must not depend on display casing from AP/FEID/UI.
        Empty values are never treated as wildcard; wildcard is only literal '*'.
        """
        return str(value or '').strip().lower()

    def campus_scope_for_user(self, user: Any) -> dict[str, Any]:
        """Return a compact campus-scope object for audit/health/UI.

        Shape:
        - unrestricted=True means all campuses.
        - campus_codes is a normalized set for CAMPUS_MANAGER scoped grants.
        - enforced_by_backend is always true to make UI copy explicit.
        """
        codes = self.accessible_campus_codes(user)
        if codes is None:
            return {
                'unrestricted': True,
                'campus_codes': [],
                'label': 'Toàn bộ cơ sở',
                'enforced_by_backend': True,
            }
        clean = sorted({self.normalize_campus_code(code) for code in codes if self.normalize_campus_code(code)})
        return {
            'unrestricted': False,
            'campus_codes': clean,
            'label': ', '.join(code.upper() for code in clean) if clean else 'Không có scope cơ sở trực tiếp',
            'enforced_by_backend': True,
        }

    def can_access_campus(self, user: Any, campus_code: str | None, *, allow_empty_for_self: bool = False) -> bool:
        if self.is_system_admin(user):
            return True
        wanted = self.normalize_campus_code(campus_code)
        if not wanted:
            return bool(allow_empty_for_self)
        codes = self.accessible_campus_codes(user)
        if codes is None:
            return True
        return wanted in {self.normalize_campus_code(code) for code in codes if self.normalize_campus_code(code)}

    def require_campus_access(self, user: Any, campus_code: str | None, *, action: str = 'xem dữ liệu cơ sở') -> None:
        if self.can_access_campus(user, campus_code):
            return
        wanted = self.normalize_campus_code(campus_code) or '(trống)'
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f'Bạn không được {action} trong cơ sở {wanted.upper()}',
        )

    def ensure_requested_campus_filter_allowed(self, user: Any, campus: str | None, *, require_filter_when_scoped: bool = False, action: str = 'xem dữ liệu cơ sở') -> None:
        """Validate a request-level campus filter before running/exporting broad jobs.

        For limited CAMPUS_MANAGER scopes, all-campus jobs can leak data in async
        workers because they may materialize/export rows outside the actor scope.
        Use require_filter_when_scoped=True for report/export/cache jobs.
        """
        if self.is_system_admin(user):
            return
        campus_value = self.normalize_campus_code(campus)
        codes = self.accessible_campus_codes(user)
        if codes is None:
            return
        allowed = {self.normalize_campus_code(code) for code in codes if self.normalize_campus_code(code)}
        if campus_value:
            if campus_value not in allowed:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f'Bạn không được {action} trong cơ sở {campus_value.upper()}',
                )
            return
        if require_filter_when_scoped and allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail='Scope cơ sở giới hạn phải chọn một cơ sở cụ thể trước khi tạo job/export để tránh mở rộng dữ liệu ngoài quyền.',
            )

    def can_access_academic_scope(self, user: Any, *, campus: str | None = None, requested_by: str | None = None, request_json: dict[str, Any] | None = None) -> bool:
        """Conservative visibility check for durable async academic jobs.

        Jobs with campus=None are considered broad. Limited campus users may see
        only their own broad jobs, because the job payload was originally created
        from their authorized scope. Other broad jobs are hidden.
        """
        if self.is_system_admin(user):
            return True
        actor_ids = {str(v).strip() for v in [getattr(user, 'user_id', None), getattr(user, 'username', None), getattr(user, 'email', None)] if str(v or '').strip()}
        data = request_json or {}
        # A durable job that was created by this actor after backend scope validation
        # remains visible/downloadable to that actor even when the job stores a
        # concrete campus. This is required for AP-assigned teachers exporting their
        # own class without granting them campus-wide visibility.
        if requested_by and str(requested_by).strip() in actor_ids and isinstance(data, dict) and data.get('scope_enforced_by_backend') is True:
            return True
        if campus and self.can_access_campus(user, campus):
            return True
        if not campus and requested_by and str(requested_by).strip() in actor_ids:
            return True
        # Jobs created after v25.9.16.7.2.64.13 can persist approved campus scope in
        # request_json. Treat it as additional defense but never as an allow-all.
        approved_campuses = data.get('approved_campus_codes') if isinstance(data, dict) else None
        if isinstance(approved_campuses, list) and approved_campuses:
            codes = self.accessible_campus_codes(user)
            if codes is None:
                return True
            allowed = {self.normalize_campus_code(code) for code in codes if self.normalize_campus_code(code)}
            requested = {self.normalize_campus_code(code) for code in approved_campuses if self.normalize_campus_code(code)}
            if requested and requested.issubset(allowed):
                return True
        return False

    def require_academic_scope(self, user: Any, *, campus: str | None = None, requested_by: str | None = None, request_json: dict[str, Any] | None = None, action: str = 'xem tác vụ học vụ') -> None:
        if self.can_access_academic_scope(user, campus=campus, requested_by=requested_by, request_json=request_json):
            return
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f'Bạn không được {action} ngoài phạm vi cơ sở/lớp được phân quyền')

    def _empty_visibility(self) -> ScopeVisibility:
        return ScopeVisibility(
            unrestricted=False,
            parent_department_ids=set(),
            parent_subject_ids=set(),
            parent_offering_ids=set(),
            broad_department_ids=set(),
            broad_subject_ids=set(),
            broad_offering_ids=set(),
            exact_chapter_ids=set(),
        )

    def visibility_for_user(self, user: Any) -> ScopeVisibility:
        if self.is_system_admin(user):
            return ScopeVisibility(
                unrestricted=True,
                parent_department_ids=set(),
                parent_subject_ids=set(),
                parent_offering_ids=set(),
                broad_department_ids=set(),
                broad_subject_ids=set(),
                broad_offering_ids=set(),
                exact_chapter_ids=set(),
            )
        visibility = self._empty_visibility()
        for assignment in self.active_assignments_for_actor(user):
            scope = self.entity_scope(assignment.scope_type, assignment.scope_id)
            if assignment.role_code == SYSTEM_ADMIN or scope.scope_type == 'SYSTEM':
                return ScopeVisibility(
                    unrestricted=True,
                    parent_department_ids=set(),
                    parent_subject_ids=set(),
                    parent_offering_ids=set(),
                    broad_department_ids=set(),
                    broad_subject_ids=set(),
                    broad_offering_ids=set(),
                    exact_chapter_ids=set(),
                )
            if scope.department_id:
                visibility.parent_department_ids.add(scope.department_id)
            if scope.subject_id:
                visibility.parent_subject_ids.add(scope.subject_id)
            if scope.subject_offering_id:
                visibility.parent_offering_ids.add(scope.subject_offering_id)
            if scope.scope_type == 'DEPARTMENT' and scope.department_id:
                visibility.broad_department_ids.add(scope.department_id)
            elif scope.scope_type == 'SUBJECT' and scope.subject_id:
                visibility.broad_subject_ids.add(scope.subject_id)
            elif scope.scope_type == 'SUBJECT_VERSION' and scope.subject_offering_id:
                visibility.broad_offering_ids.add(scope.subject_offering_id)
            elif scope.scope_type == 'CHAPTER' and scope.chapter_id:
                visibility.exact_chapter_ids.add(scope.chapter_id)
        return visibility

    def _subject_ids_for_departments(self, department_ids: set[str]) -> set[str]:
        if not department_ids:
            return set()
        rows = self.db.query(Subject.id).filter(Subject.department_id.in_(department_ids)).all()
        return {row[0] for row in rows}

    def accessible_department_ids(self, user: Any) -> set[str] | None:
        visibility = self.visibility_for_user(user)
        if visibility.unrestricted:
            return None
        return set(visibility.parent_department_ids)

    def accessible_subject_ids(self, user: Any) -> set[str] | None:
        """Subjects visible in the hierarchy, including parents of child grants."""
        visibility = self.visibility_for_user(user)
        if visibility.unrestricted:
            return None
        subjects = set(visibility.parent_subject_ids)
        subjects.update(self._subject_ids_for_departments(visibility.broad_department_ids))
        return subjects

    def accessible_subject_offering_ids(self, user: Any) -> set[str] | None:
        """Subject versions visible in the hierarchy.

        Important: a CHAPTER-scoped reviewer only sees the parent version of that
        chapter, not every version of the parent subject.
        """
        visibility = self.visibility_for_user(user)
        if visibility.unrestricted:
            return None
        subject_ids = set(visibility.broad_subject_ids)
        subject_ids.update(self._subject_ids_for_departments(visibility.broad_department_ids))
        offerings = set(visibility.parent_offering_ids)
        if subject_ids:
            rows = self.db.query(SubjectOffering.id).filter(SubjectOffering.subject_id.in_(subject_ids)).all()
            offerings.update(row[0] for row in rows)
        return offerings

    def accessible_chapter_ids(self, user: Any) -> set[str] | None:
        """Chapters visible in the hierarchy.

        Department/subject/subject-version grants expand downward. Chapter grants
        stay exact so reviewers do not see sibling chapters.
        """
        visibility = self.visibility_for_user(user)
        if visibility.unrestricted:
            return None
        subject_ids = set(visibility.broad_subject_ids)
        subject_ids.update(self._subject_ids_for_departments(visibility.broad_department_ids))
        query_filters = []
        if subject_ids:
            query_filters.append(SubjectChapter.subject_id.in_(subject_ids))
        if visibility.broad_offering_ids:
            query_filters.append(SubjectChapter.subject_offering_id.in_(visibility.broad_offering_ids))
        if visibility.exact_chapter_ids:
            query_filters.append(SubjectChapter.id.in_(visibility.exact_chapter_ids))
        if not query_filters:
            return set()
        rows = self.db.query(SubjectChapter.id).filter(or_(*query_filters)).all()
        return {row[0] for row in rows}

    def _hierarchy_conditions(self, model: Any, user: Any):
        visibility = self.visibility_for_user(user)
        if visibility.unrestricted:
            return None
        conditions = []
        department_subject_ids = self._subject_ids_for_departments(visibility.broad_department_ids)
        department_col = getattr(model, 'department_id', None)
        subject_col = getattr(model, 'subject_id', None)
        offering_col = getattr(model, 'subject_offering_id', None)
        chapter_col = getattr(model, 'chapter_id', None)
        if chapter_col is None:
            chapter_col = getattr(model, 'subject_chapter_id', None)
        if department_col is not None and visibility.broad_department_ids:
            conditions.append(department_col.in_(visibility.broad_department_ids))
        if subject_col is not None:
            subject_ids = set(visibility.broad_subject_ids) | department_subject_ids
            if subject_ids:
                conditions.append(subject_col.in_(subject_ids))
        if offering_col is not None and visibility.broad_offering_ids:
            conditions.append(offering_col.in_(visibility.broad_offering_ids))
        if chapter_col is not None and visibility.exact_chapter_ids:
            conditions.append(chapter_col.in_(visibility.exact_chapter_ids))
        return conditions

    def apply_department_filter(self, query, user: Any):
        ids = self.accessible_department_ids(user)
        if ids is None:
            return query
        if not ids:
            return query.filter(False)
        return query.filter(Department.id.in_(ids))

    def apply_subject_filter(self, query, user: Any):
        visibility = self.visibility_for_user(user)
        if visibility.unrestricted:
            return query
        conditions = []
        if visibility.broad_department_ids:
            conditions.append(Subject.department_id.in_(visibility.broad_department_ids))
        if visibility.parent_subject_ids:
            conditions.append(Subject.id.in_(visibility.parent_subject_ids))
        if not conditions:
            return query.filter(False)
        return query.filter(or_(*conditions))

    def apply_subject_offering_filter(self, query, user: Any):
        visibility = self.visibility_for_user(user)
        if visibility.unrestricted:
            return query
        conditions = []
        department_subject_ids = self._subject_ids_for_departments(visibility.broad_department_ids)
        subject_ids = set(visibility.broad_subject_ids) | department_subject_ids
        if subject_ids:
            conditions.append(SubjectOffering.subject_id.in_(subject_ids))
        if visibility.parent_offering_ids:
            conditions.append(SubjectOffering.id.in_(visibility.parent_offering_ids))
        if not conditions:
            return query.filter(False)
        return query.filter(or_(*conditions))

    def apply_chapter_filter(self, query, user: Any):
        visibility = self.visibility_for_user(user)
        if visibility.unrestricted:
            return query
        conditions = []
        department_subject_ids = self._subject_ids_for_departments(visibility.broad_department_ids)
        subject_ids = set(visibility.broad_subject_ids) | department_subject_ids
        if subject_ids:
            conditions.append(SubjectChapter.subject_id.in_(subject_ids))
        if visibility.broad_offering_ids:
            conditions.append(SubjectChapter.subject_offering_id.in_(visibility.broad_offering_ids))
        if visibility.exact_chapter_ids:
            conditions.append(SubjectChapter.id.in_(visibility.exact_chapter_ids))
        if not conditions:
            return query.filter(False)
        return query.filter(or_(*conditions))

    def apply_hierarchy_filter(self, query, model: Any, user: Any):
        conditions = self._hierarchy_conditions(model, user)
        if conditions is None:
            return query
        if not conditions:
            return query.filter(False)
        return query.filter(or_(*conditions))
