from pathlib import Path

p = Path('frontend/app/users/page.tsx')
s = p.read_text(encoding='utf-8')
old = """      const headers = authHeaders()
      const [roleRows, assignmentRows, departmentRows, campusPolyRows, campusPtcdRows] = await Promise.all([
        getRBACRoles(headers),
        getRoleAssignments(headers, { includeRevoked }),
        searchDepartments(headers),
        getAcademicCampuses(headers, { active: true, branch: 'poly' }),
        getAcademicCampuses(headers, { active: true, branch: 'ptcd' }),
      ])
"""
new = """      const headers = authHeaders()
      const canLoadBankGrantScopes = isSystemAdmin || businessPermissions.includes('subject.assign_owner') || businessPermissions.includes('reviewer.assign')
      const [roleRows, assignmentRows, departmentRows, campusPolyRows, campusPtcdRows] = await Promise.all([
        getRBACRoles(headers),
        getRoleAssignments(headers, { includeRevoked }),
        canLoadBankGrantScopes ? searchDepartments(headers) : Promise.resolve([] as Department[]),
        isSystemAdmin ? getAcademicCampuses(headers, { active: true, branch: 'poly' }) : Promise.resolve([] as AcademicCampus[]),
        isSystemAdmin ? getAcademicCampuses(headers, { active: true, branch: 'ptcd' }) : Promise.resolve([] as AcademicCampus[]),
      ])
"""
if s.count(old) != 1:
    raise SystemExit(f'users loadAll anchor mismatch: {s.count(old)}')
s = s.replace(old, new)
p.write_text(s, encoding='utf-8')
print('users RBAC scope patch applied')
