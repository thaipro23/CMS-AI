from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.rbac import UserContext, require_permission
from app.db.session import get_db
from app.models.academic import AcademicCampus
from app.services.business_rbac import BusinessRBACService


router = APIRouter()


@router.get('/training-scope')
def get_training_scope(
    user: UserContext = Depends(require_permission('view_training_reports')),
    db: Session = Depends(get_db),
):
    """Return the effective campus/branch scope used by Training Operations UI.

    The backend remains the source of truth.  A campus-scoped owner receives only
    the campuses granted by RBAC plus their catalog branch, allowing the frontend
    to choose PTCĐ/Poly before issuing broad training-data requests.
    """
    rbac = BusinessRBACService(db)
    campus_codes = rbac.accessible_campus_codes(user)

    if campus_codes is None:
        return {
            'unrestricted': True,
            'campus_scoped': False,
            'campus_codes': [],
            'branches': [],
            'campuses': [],
            'preferred_branch': None,
            'preferred_campus': None,
        }

    normalized_codes = sorted({rbac.normalize_campus_code(code) for code in campus_codes if rbac.normalize_campus_code(code)})
    if not normalized_codes:
        # AP-assigned teachers can have no direct CAMPUS role.  Their existing
        # class-level filtering must keep working without forcing a branch here.
        return {
            'unrestricted': False,
            'campus_scoped': False,
            'campus_codes': [],
            'branches': [],
            'campuses': [],
            'preferred_branch': None,
            'preferred_campus': None,
        }

    rows = (
        db.query(AcademicCampus)
        .filter(
            AcademicCampus.active.is_(True),
            func.lower(AcademicCampus.campus_code).in_(normalized_codes),
        )
        .order_by(AcademicCampus.sort_order.asc(), AcademicCampus.campus_code.asc())
        .all()
    )

    campuses = []
    branches: list[str] = []
    seen_campuses: set[tuple[str, str]] = set()
    for row in rows:
        campus_code = rbac.normalize_campus_code(row.campus_code)
        branch = str(row.branch or '').strip().lower()
        key = (campus_code, branch)
        if not campus_code or key in seen_campuses:
            continue
        seen_campuses.add(key)
        campuses.append({
            'campus_code': campus_code,
            'campus_name': str(row.campus_name or campus_code.upper()).strip(),
            'branch': branch,
        })
        if branch and branch not in branches:
            branches.append(branch)

    # If one explicitly assigned campus has no active catalog row, keep it in the
    # response so the UI does not silently widen scope.  Its branch is intentionally
    # left blank; backend authorization still enforces the campus assignment.
    known_codes = {item['campus_code'] for item in campuses}
    for campus_code in normalized_codes:
        if campus_code not in known_codes:
            campuses.append({'campus_code': campus_code, 'campus_name': campus_code.upper(), 'branch': ''})

    preferred_branch = branches[0] if branches else None
    preferred_campus = normalized_codes[0] if len(normalized_codes) == 1 else None
    return {
        'unrestricted': False,
        'campus_scoped': True,
        'campus_codes': normalized_codes,
        'branches': branches,
        'campuses': campuses,
        'preferred_branch': preferred_branch,
        'preferred_campus': preferred_campus,
    }
