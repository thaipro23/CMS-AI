'use client'

import { formatVNDateTime } from '../../lib/time'
import { useDebouncedValue } from '../../lib/useDebouncedValue'
import { ChangeEvent, useEffect, useMemo, useState } from 'react'
import {
  createRoleAssignment,
  getAcademicCampuses,
  downloadRBACImportTemplate,
  searchDepartments,
  getRBACRoles,
  getRoleAssignments,
  searchSubjectChapters,
  searchSubjectOfferings,
  searchSubjects,
  importRoleAssignmentsFromExcel,
  revokeRoleAssignment,
} from '../../lib/api'
import { useAppContext } from '../../context/AppContext'
import { ActionMessage, ActionMessageData, toUserError } from '../../components/ui/ActionMessage'
import { PageHeader, PageRoot } from '../../components/layout/PageHeader'
import { EnterpriseDataTable, type EnterpriseTableColumn } from '../../components/table/EnterpriseDataTable'
import { CompactFilterBar, OperationsKpiStrip, SideDrawer, WorkspaceSection } from '../../components/operations/OperationsWorkspace'
import { StatusBadge } from '../../components/ui/StatusBadge'
import {
  BusinessRoleCode,
  BusinessScopeType,
  Department,
  RBACRole,
  RoleAssignment,
  RoleAssignmentImportResponse,
  Subject,
  SubjectChapter,
  SubjectOffering,
  AcademicCampus,
} from '../../types'


type UserAccessRow = {
  userId: string
  email?: string | null
  assignments: RoleAssignment[]
  activeAssignments: RoleAssignment[]
  roleCodes: string[]
  scopes: string[]
}
const roleLabels: Record<string, string> = {
  SYSTEM_ADMIN: 'Quản trị web',
  DEPARTMENT_HEAD: 'Trưởng bộ môn',
  SUBJECT_OWNER: 'Chủ môn',
  QUESTION_REVIEWER: 'Người duyệt câu hỏi',
  CAMPUS_OWNER: 'Chủ cơ sở',
  CAMPUS_MANAGER: 'Chủ cơ sở (legacy)',
  TEACHER_ASSIGNED: 'Giáo viên được phân công AP',
}

const roleSubtitles: Record<string, string> = {
  SYSTEM_ADMIN: 'Toàn hệ thống. Chỉ dành cho admin kỹ thuật/ban quản trị.',
  DEPARTMENT_HEAD: 'Quản lý các môn, phiên bản, bài và người duyệt trong một bộ môn.',
  SUBJECT_OWNER: 'Quản lý một môn hoặc một phiên bản/kỳ cụ thể.',
  QUESTION_REVIEWER: 'Chỉ xem, sửa, duyệt hoặc từ chối câu hỏi trong phạm vi được giao.',
  CAMPUS_OWNER: 'Vận hành sinh viên/lớp/analytics trong cơ sở được phân công.',
  CAMPUS_MANAGER: 'Legacy alias của Chủ cơ sở; dùng CAMPUS_OWNER cho gán mới.',
  TEACHER_ASSIGNED: 'Giáo viên chỉ xem lớp được AP phân công; scope CLASS/CAMPUS chỉ là ràng buộc phụ.',
}

const allowedScopesByRole: Record<string, BusinessScopeType[]> = {
  SYSTEM_ADMIN: ['SYSTEM'],
  DEPARTMENT_HEAD: ['DEPARTMENT'],
  SUBJECT_OWNER: ['SUBJECT', 'SUBJECT_VERSION'],
  QUESTION_REVIEWER: ['SUBJECT', 'SUBJECT_VERSION', 'CHAPTER'],
  CAMPUS_OWNER: ['CAMPUS', 'SYSTEM'],
  CAMPUS_MANAGER: ['CAMPUS', 'SYSTEM'],
  TEACHER_ASSIGNED: ['CLASS', 'CAMPUS', 'SYSTEM'],
}

const scopeLabel: Record<string, string> = {
  SYSTEM: 'Toàn hệ thống',
  DEPARTMENT: 'Bộ môn',
  SUBJECT: 'Môn học',
  SUBJECT_VERSION: 'Version/kỳ môn',
  CHAPTER: 'Bài / chapter',
  COURSE: 'Course Open edX',
  CAMPUS: 'Cơ sở',
}

function formatDate(value?: string | null) {
  if (!value) return '—'
  try { return formatVNDateTime(value) } catch { return value }
}

function resultClass(status: string) {
  if (status === 'created' || status === 'success' || status === 'valid') return 'approved'
  if (status === 'skipped') return 'pending'
  if (status === 'failed' || status === 'error') return 'rejected'
  return 'warning'
}

export default function UsersPage() {
  const { authHeaders, isSystemAdmin, businessPermissions, canScope } = useAppContext()
  const [message, setMessage] = useState<ActionMessageData | null>(null)
  const [loading, setLoading] = useState(false)
  const [roles, setRoles] = useState<RBACRole[]>([])
  const [assignments, setAssignments] = useState<RoleAssignment[]>([])
  const [departments, setDepartments] = useState<Department[]>([])
  const [subjects, setSubjects] = useState<Subject[]>([])
  const [offerings, setOfferings] = useState<SubjectOffering[]>([])
  const [chapters, setChapters] = useState<SubjectChapter[]>([])
  const [campuses, setCampuses] = useState<AcademicCampus[]>([])
  const [filterText, setFilterText] = useState('')
  const [includeRevoked, setIncludeRevoked] = useState(false)
  const [importFile, setImportFile] = useState<File | null>(null)
  const [dryRun, setDryRun] = useState(true)
  const [importResult, setImportResult] = useState<RoleAssignmentImportResponse | null>(null)
  const [scopeSearch, setScopeSearch] = useState('')
  const debouncedScopeSearch = useDebouncedValue(scopeSearch, 300)
  const [scopeOptionsLoading, setScopeOptionsLoading] = useState(false)
  const [importOpen, setImportOpen] = useState(false)
  const [scopeDropdownOpen, setScopeDropdownOpen] = useState(false)
  const [selectedUserId, setSelectedUserId] = useState<string | null>(null)
  const [form, setForm] = useState({
    user_id: '',
    email: '',
    role_code: 'DEPARTMENT_HEAD' as BusinessRoleCode,
    scope_type: 'DEPARTMENT' as BusinessScopeType,
    scope_id: '',
    grant_reason: '',
    sync_openedx: false,
  })

  const fallbackRoles = useMemo(() => [
    { code: 'SYSTEM_ADMIN', name: 'Quản trị web', description: roleSubtitles.SYSTEM_ADMIN, rank: 100, status: 'active' },
    { code: 'DEPARTMENT_HEAD', name: 'Trưởng bộ môn', description: roleSubtitles.DEPARTMENT_HEAD, rank: 70, status: 'active' },
    { code: 'SUBJECT_OWNER', name: 'Chủ môn', description: roleSubtitles.SUBJECT_OWNER, rank: 50, status: 'active' },
    { code: 'QUESTION_REVIEWER', name: 'Người duyệt câu hỏi', description: roleSubtitles.QUESTION_REVIEWER, rank: 30, status: 'active' },
    { code: 'CAMPUS_OWNER', name: 'Chủ cơ sở', description: roleSubtitles.CAMPUS_OWNER, rank: 60, status: 'active' },
    { code: 'CAMPUS_MANAGER', name: 'Chủ cơ sở (legacy)', description: roleSubtitles.CAMPUS_MANAGER, rank: 60, status: 'active' },
    { code: 'TEACHER_ASSIGNED', name: 'Giáo viên được phân công AP', description: roleSubtitles.TEACHER_ASSIGNED, rank: 10, status: 'active' },
  ] as RBACRole[], [])
  const allRoles = roles.length ? roles : fallbackRoles
  const grantableRoleCodes = useMemo(() => {
    if (isSystemAdmin) return new Set(allRoles.map((role) => role.code))
    const result = new Set<string>()
    if (businessPermissions.includes('subject.assign_owner')) result.add('SUBJECT_OWNER')
    if (businessPermissions.includes('reviewer.assign')) result.add('QUESTION_REVIEWER')
    return result
  }, [allRoles, businessPermissions, isSystemAdmin])
  const visibleRoles = allRoles.filter((role) => grantableRoleCodes.has(role.code))
  const availableScopes = allowedScopesByRole[form.role_code] || ['SYSTEM']
  const scopeOptions = useMemo(() => {
    const needle = scopeSearch.trim().toLowerCase()
    const requiredPermission = form.role_code === 'SUBJECT_OWNER' ? 'subject.assign_owner' : form.role_code === 'QUESTION_REVIEWER' ? 'reviewer.assign' : 'user.manage_all'
    const filter = <T extends { id: string; label: string; path: string; target: Parameters<typeof canScope>[1] }>(rows: T[]) => rows
      .filter((row) => canScope(requiredPermission, row.target))
      .filter((row) => needle ? [row.id, row.label, row.path].some((value) => String(value || '').toLowerCase().includes(needle)) : true)
      .map(({ target: _target, ...row }) => row)
    if (form.scope_type === 'SYSTEM') return isSystemAdmin ? [{ id: '*', label: 'Toàn hệ thống', path: 'SYSTEM' }] : []
    if (form.scope_type === 'DEPARTMENT') return filter(departments.map((d) => ({ id: d.id, label: `${d.code} · ${d.name}`, path: `Bộ môn / ${d.code}`, target: { scopeType: 'DEPARTMENT' as const, scopeId: d.id, departmentId: d.id } })))
    if (form.scope_type === 'SUBJECT') return filter(subjects.map((subject) => ({ id: subject.id, label: `${subject.code} · ${subject.name}`, path: `Môn / ${subject.code}`, target: { scopeType: 'SUBJECT' as const, scopeId: subject.id, subjectId: subject.id, departmentId: subject.department_id } })))
    if (form.scope_type === 'SUBJECT_VERSION') return filter(offerings.map((offering) => ({ id: offering.id, label: `${offering.code} · ${offering.name || offering.version_code}`, path: `Version / ${offering.code}`, target: { scopeType: 'SUBJECT_VERSION' as const, scopeId: offering.id, subjectOfferingId: offering.id, subjectId: offering.subject_id, departmentId: offering.department_id || undefined } })))
    if (form.scope_type === 'CHAPTER') return filter(chapters.map((chapter) => ({ id: chapter.id, label: chapter.title, path: `Bài / ${chapter.title}`, target: { scopeType: 'CHAPTER' as const, scopeId: chapter.id, chapterId: chapter.id, subjectOfferingId: chapter.subject_offering_id || undefined, subjectId: chapter.subject_id } })))
    if (form.scope_type === 'CAMPUS') return isSystemAdmin ? [{ id: '*', label: 'Tất cả cơ sở', path: 'Cơ sở / Tất cả' }, ...campuses.map((campus) => ({ id: campus.campus_code, label: `${campus.campus_code.toUpperCase()} · ${campus.campus_name}`, path: `Cơ sở / ${campus.campus_code.toUpperCase()}` }))] : []
    return []
  }, [campuses, canScope, chapters, departments, form.role_code, form.scope_type, isSystemAdmin, offerings, scopeSearch, subjects])

  const selectedScopeOption = useMemo(() => scopeOptions.find((item) => item.id === form.scope_id), [form.scope_id, scopeOptions])

  function chooseScopeOption(id: string) {
    setForm({ ...form, scope_id: id })
    setScopeDropdownOpen(false)
  }

  const filteredAssignments = useMemo(() => {
    const needle = filterText.trim().toLowerCase()
    if (!needle) return assignments
    return assignments.filter((a) => [a.user_id, a.email, a.role_code, a.role_name, a.scope_label, a.scope_type, a.scope_id, a.grant_reason]
      .filter(Boolean)
      .some((item) => String(item).toLowerCase().includes(needle)))
  }, [assignments, filterText])

  const userRows = useMemo<UserAccessRow[]>(() => {
    const grouped = new Map<string, RoleAssignment[]>()
    for (const assignment of filteredAssignments) {
      const rows = grouped.get(assignment.user_id) || []
      rows.push(assignment)
      grouped.set(assignment.user_id, rows)
    }
    return Array.from(grouped.entries()).map(([userId, rows]) => {
      const activeRows = rows.filter((row) => !row.revoked_at)
      return {
        userId,
        email: rows.find((row) => row.email)?.email || null,
        assignments: rows,
        activeAssignments: activeRows,
        roleCodes: Array.from(new Set(activeRows.map((row) => String(row.role_code)))),
        scopes: Array.from(new Set(activeRows.map((row) => row.scope_label || `${row.scope_type}:${row.scope_id}`))),
      }
    }).sort((a, b) => a.userId.localeCompare(b.userId, 'vi'))
  }, [filteredAssignments])

  const assignmentStats = useMemo(() => {
    const active = assignments.filter((a) => !a.revoked_at)
    return {
      total: active.length,
      heads: active.filter((a) => a.role_code === 'DEPARTMENT_HEAD').length,
      owners: active.filter((a) => a.role_code === 'SUBJECT_OWNER').length,
      reviewers: active.filter((a) => a.role_code === 'QUESTION_REVIEWER').length,
      campusManagers: active.filter((a) => a.role_code === 'CAMPUS_MANAGER' || a.role_code === 'CAMPUS_OWNER').length,
    }
  }, [assignments])

  useEffect(() => {
    if (!visibleRoles.length) return
    if (!visibleRoles.some((role) => role.code === form.role_code)) syncScopeForRole(visibleRoles[0].code as BusinessRoleCode)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [visibleRoles.map((role) => role.code).join('|')])

  function syncScopeForRole(nextRole: BusinessRoleCode) {
    const scopes = allowedScopesByRole[nextRole] || ['SYSTEM']
    setForm((prev) => ({ ...prev, role_code: nextRole, scope_type: scopes[0], scope_id: scopes[0] === 'SYSTEM' ? '*' : '' }))
  }

  async function loadAll() {
    setLoading(true)
    try {
      const headers = authHeaders()
      const [roleRows, assignmentRows, departmentRows, campusPolyRows, campusPtcdRows] = await Promise.all([
        getRBACRoles(headers),
        getRoleAssignments(headers, { includeRevoked }),
        searchDepartments(headers),
        getAcademicCampuses(headers, { active: true, branch: 'poly' }),
        getAcademicCampuses(headers, { active: true, branch: 'ptcd' }),
      ])
      setRoles(roleRows)
      setAssignments(assignmentRows.items)
      setDepartments(departmentRows)
      const campusMap = new Map<string, AcademicCampus>()
      ;[...campusPolyRows, ...campusPtcdRows].forEach((campus) => {
        const key = campus.campus_code.toLowerCase()
        if (!campusMap.has(key)) campusMap.set(key, campus)
      })
      setCampuses(Array.from(campusMap.values()).sort((a, b) => a.campus_code.localeCompare(b.campus_code)))
      setMessage(null)
    } catch (e) {
      setMessage(toUserError(e, 'Không tải được trang phân quyền. Kiểm tra token, RBAC scope và backend logs.'))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (!scopeDropdownOpen) return
    if (!['DEPARTMENT', 'SUBJECT', 'SUBJECT_VERSION', 'CHAPTER'].includes(form.scope_type)) return
    const controller = new AbortController()
    const headers = authHeaders()
    setScopeOptionsLoading(true)
    const run = async () => {
      if (form.scope_type === 'DEPARTMENT') {
        setDepartments(await searchDepartments(headers, debouncedScopeSearch, controller.signal))
      } else if (form.scope_type === 'SUBJECT') {
        setSubjects(await searchSubjects(headers, { query: debouncedScopeSearch, signal: controller.signal }))
      } else if (form.scope_type === 'SUBJECT_VERSION') {
        setOfferings(await searchSubjectOfferings(headers, { query: debouncedScopeSearch, signal: controller.signal }))
      } else if (form.scope_type === 'CHAPTER') {
        setChapters(await searchSubjectChapters(headers, { query: debouncedScopeSearch, signal: controller.signal }))
      }
    }
    run().catch((error) => {
      if (!controller.signal.aborted) setMessage(toUserError(error, 'Không tải được danh mục phạm vi.'))
    }).finally(() => {
      if (!controller.signal.aborted) setScopeOptionsLoading(false)
    })
    return () => controller.abort()
  }, [authHeaders, debouncedScopeSearch, form.scope_type, scopeDropdownOpen])

  async function submitAssignment() {
    try {
      if (!form.user_id.trim()) throw new Error('Cần nhập user_id/username/email Open edX.')
      if (form.scope_type !== 'SYSTEM' && !form.scope_id.trim()) throw new Error('Cần chọn scope để gán quyền.')
      await createRoleAssignment({
        user_id: form.user_id.trim(),
        email: form.email.trim() || null,
        role_code: form.role_code,
        scope_type: form.scope_type,
        scope_id: form.scope_type === 'SYSTEM' ? '*' : form.scope_id,
        grant_reason: form.grant_reason.trim() || 'Gán từ màn phân quyền',
        sync_openedx: form.sync_openedx,
      }, authHeaders(true))
      setMessage({ type: 'success', title: 'Đã gán quyền', body: 'Người dùng cần đăng nhập lại AI/CMS để nhận quyền mới.' })
      setForm((prev) => ({ ...prev, user_id: '', email: '', grant_reason: '' }))
      await loadAll()
    } catch (e) {
      setMessage(toUserError(e, 'Không gán được quyền. Kiểm tra đúng vai trò, phạm vi và quyền người đang thao tác.'))
    }
  }

  async function revokeAssignment(id: string) {
    try {
      await revokeRoleAssignment(id, authHeaders(true), 'Thu hồi từ màn phân quyền')
      setMessage({ type: 'success', title: 'Đã thu hồi quyền', body: 'Assignment đã được revoke, không xóa cứng để giữ audit.' })
      await loadAll()
    } catch (e) {
      setMessage(toUserError(e, 'Không thu hồi được quyền.'))
    }
  }

  async function downloadTemplate() {
    try {
      const blob = await downloadRBACImportTemplate(authHeaders())
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = 'ai-question-bank-rbac-import-template.xlsx'
      a.click()
      URL.revokeObjectURL(url)
    } catch (e) {
      setMessage(toUserError(e, 'Không tải được file Excel mẫu.'))
    }
  }

  async function submitImport() {
    try {
      if (!importFile) throw new Error('Cần chọn file Excel .xlsx')
      const result = await importRoleAssignmentsFromExcel(authHeaders(true), importFile, dryRun)
      setImportResult(result)
      setMessage({
        type: result.failed_count ? 'warning' : 'success',
        title: dryRun ? 'Đã kiểm tra file Excel' : 'Đã import phân quyền',
        body: `Hợp lệ ${result.valid_rows}/${result.total_rows}. Tạo ${result.created_count}, bỏ qua ${result.skipped_count}, lỗi ${result.failed_count}.`,
      })
      if (!dryRun) await loadAll()
    } catch (e) {
      setMessage(toUserError(e, 'Không import được file Excel. Kiểm tra đúng template và dữ liệu scope_id.'))
    }
  }

  function onFileChange(event: ChangeEvent<HTMLInputElement>) {
    setImportFile(event.target.files?.[0] || null)
    setImportResult(null)
  }

  useEffect(() => { loadAll() }, [includeRevoked]) // eslint-disable-line react-hooks/exhaustive-deps

  const userColumns: EnterpriseTableColumn<UserAccessRow>[] = [
    { key: 'user', header: 'Người dùng', kind: 'identity', minWidth: 220, priority: 'required', hideable: false, render: (item) => <div className="rbac-user-summary"><b>{item.userId}</b><small>{item.email || 'Chưa có email'}</small></div> },
    { key: 'roles', header: 'Vai trò hiệu lực', kind: 'text', minWidth: 250, priority: 'required', hideable: false, render: (item) => <div className="rbac-role-stack">{item.roleCodes.length ? item.roleCodes.map((code) => <span key={code} className={`rbac-role-chip ${code === 'SYSTEM_ADMIN' ? 'system' : ''}`}>{roleLabels[code] || code}</span>) : <span className="muted">Không có quyền hiệu lực</span>}</div> },
    { key: 'scope', header: 'Phạm vi', kind: 'identity', minWidth: 240, priority: 'important', hideable: true, render: (item) => <div className="rbac-scope-list">{item.scopes.slice(0, 2).map((scope) => <span key={scope}>{scope}</span>)}{item.scopes.length > 2 ? <small>+{item.scopes.length - 2} phạm vi khác</small> : null}</div> },
    { key: 'count', header: 'Số quyền', kind: 'number', width: 82, priority: 'important', hideable: true, render: (item) => item.activeAssignments.length },
    { key: 'actions', header: 'Thao tác', kind: 'actions', width: 92, sticky: 'right', hideable: false, render: (item) => <button className="btn small secondary" type="button" onClick={() => setSelectedUserId(item.userId)}>Chi tiết</button> },
  ]


  const selectedRole = allRoles.find((role) => role.code === form.role_code)

  return <PageRoot className="page-stack access-console access-console-v2">
    <PageHeader
      eyebrow="Quản trị"
      title="Người dùng & phân quyền"
      secondaryActions={<>
        {isSystemAdmin && <button className="btn secondary" type="button" onClick={downloadTemplate}>Tải template</button>}
        {isSystemAdmin && <button className="btn secondary" type="button" onClick={() => setImportOpen(true)}>Import Excel</button>}
        <button className="btn secondary" type="button" onClick={loadAll} disabled={loading}>{loading ? 'Đang tải...' : 'Làm mới'}</button>
      </>}
    />

    <ActionMessage message={message} onClose={() => setMessage(null)} />

    <OperationsKpiStrip items={[
      { label: 'Người dùng có quyền', value: userRows.length, hint: 'Theo phạm vi bạn quản lý' },
      { label: 'Quyền hiệu lực', value: assignmentStats.total, hint: isSystemAdmin ? 'Toàn hệ thống' : 'Trong scope hiện tại', tone: 'info' },
      { label: 'Trưởng/Chủ môn', value: assignmentStats.heads + assignmentStats.owners, hint: `${assignmentStats.heads} trưởng bộ môn · ${assignmentStats.owners} chủ môn` },
      { label: 'Người duyệt', value: assignmentStats.reviewers, hint: 'Quyền review câu hỏi' },
      { label: 'Chủ cơ sở', value: assignmentStats.campusManagers, hint: 'Phạm vi vận hành đào tạo' },
    ]} />

    <CompactFilterBar actions={<label className="check-row"><input type="checkbox" checked={includeRevoked} onChange={(event) => setIncludeRevoked(event.target.checked)} /> Hiện quyền đã thu hồi</label>}>
      <label>Tìm người dùng, vai trò hoặc phạm vi<input className="input" value={filterText} onChange={(event) => setFilterText(event.target.value)} placeholder="username, email, COM1071, cơ sở..." /></label>
    </CompactFilterBar>

    <section className="rbac-user-workspace">
      <WorkspaceSection title="Người dùng đã được cấp quyền" description="Mỗi người dùng là một dòng. Mở Chi tiết để xem quyền trực tiếp, phạm vi, nguồn cấp và thu hồi.">
        <EnterpriseDataTable tableId="rbac-users" caption="Người dùng & quyền" rows={userRows} columns={userColumns} rowKey={(item) => item.userId} density="compact" loading={loading} label="người dùng" emptyTitle="Chưa có người dùng phù hợp" emptyDescription="Thay đổi từ khóa hoặc gán quyền mới ở panel bên phải." />
      </WorkspaceSection>
      <aside className="card rbac-grant-panel" aria-label="Gán quyền mới">
        <div className="section-head compact-section-head"><div><span className="eyebrow">Gán quyền</span><h2>Quyền mới</h2><p className="helper">Chọn người dùng, vai trò và đúng phạm vi cần giao.</p></div></div>
        {!visibleRoles.length ? <div className="alert warning">Bạn không có quyền gán thêm vai trò trong phạm vi hiện tại.</div> : <>
          <label>Vai trò<select className="input" value={form.role_code} onChange={(event) => syncScopeForRole(event.target.value as BusinessRoleCode)}>{visibleRoles.map((role) => <option key={role.code} value={role.code}>{roleLabels[role.code] || role.name}</option>)}</select></label>
          <div className="permission-role-description"><b>{roleLabels[form.role_code]}</b><span>{selectedRole?.description || roleSubtitles[form.role_code]}</span></div>
          <label>Tài khoản Open edX<input className="input" value={form.user_id} onChange={(event) => setForm({ ...form, user_id: event.target.value })} placeholder="vd: owner_web107" /></label>
          <label>Email <span className="optional-label">(không bắt buộc)</span><input className="input" value={form.email} onChange={(event) => setForm({ ...form, email: event.target.value })} placeholder="user@fpt.edu.vn" /></label>
          <label>Loại phạm vi<select className="input" value={form.scope_type} onChange={(event) => { setScopeSearch(''); setForm({ ...form, scope_type: event.target.value as BusinessScopeType, scope_id: event.target.value === 'SYSTEM' ? '*' : '' }) }}>{availableScopes.map((scope) => <option key={scope} value={scope}>{scopeLabel[scope]}</option>)}</select></label>
          <div className="searchable-scope-field"><label>Phạm vi cụ thể</label><div className={`searchable-select ${scopeDropdownOpen ? 'open' : ''} ${form.scope_type === 'SYSTEM' ? 'disabled' : ''}`}>
            <button className="input searchable-select-trigger" type="button" disabled={form.scope_type === 'SYSTEM'} onClick={() => setScopeDropdownOpen((value) => !value)}><span>{form.scope_type === 'SYSTEM' ? 'Toàn hệ thống' : selectedScopeOption?.label || 'Chọn phạm vi'}</span><b>⌄</b></button>
            {scopeDropdownOpen && form.scope_type !== 'SYSTEM' ? <div className="searchable-select-menu"><input className="input scope-search-input" value={scopeSearch} onChange={(event) => setScopeSearch(event.target.value)} placeholder="Gõ mã hoặc tên phạm vi..." autoFocus /><div className="searchable-select-list">{scopeOptions.map((item) => <button type="button" className={`searchable-select-option ${form.scope_id === item.id ? 'selected' : ''}`} key={item.id} onClick={() => chooseScopeOption(item.id)}><b>{item.label}</b><small>{item.path}</small></button>)}{!scopeOptions.length ? <div className="empty-state small-empty">Không tìm thấy phạm vi phù hợp.</div> : null}</div></div> : null}
          </div></div>
          <label>Lý do cấp quyền<input className="input" value={form.grant_reason} onChange={(event) => setForm({ ...form, grant_reason: event.target.value })} placeholder="Ví dụ: Phụ trách COM1071 Summer 2026" /></label>
          {form.scope_id ? <div className="permission-effect-preview"><span>Quyền sẽ có hiệu lực</span><b>{roleLabels[form.role_code]} · {scopeLabel[form.scope_type]}</b><small>{scopeOptions.find((item) => item.id === form.scope_id)?.path || form.scope_id}</small></div> : null}
          <label className="check-row"><input type="checkbox" checked={form.sync_openedx} onChange={(event) => setForm({ ...form, sync_openedx: event.target.checked })} /> Ghi nhận yêu cầu đồng bộ Open edX</label>
          <button className="btn full-width" type="button" onClick={submitAssignment} disabled={!form.user_id.trim() || !form.scope_id}>Gán quyền</button>
        </>}
      </aside>
    </section>

    <SideDrawer open={Boolean(selectedUserId)} title={selectedUserId || 'Chi tiết người dùng'} description="Quyền trực tiếp đang được lưu; quyền kế thừa được backend áp dụng theo cây scope." onClose={() => setSelectedUserId(null)}>
      <div className="rbac-user-detail-list">{assignments.filter((item) => item.user_id === selectedUserId).map((item) => <article className="rbac-user-detail-item" key={item.id}><header><div><b>{roleLabels[item.role_code] || item.role_name || item.role_code}</b><small>{item.scope_label || `${item.scope_type}:${item.scope_id}`}</small></div><StatusBadge status={item.revoked_at ? 'revoked' : 'active'} label={item.revoked_at ? 'Đã thu hồi' : 'Đang hiệu lực'} /></header><p>{item.grant_reason || 'Không ghi lý do cấp quyền.'}</p><small>{item.granted_by ? `Cấp bởi ${item.granted_by}` : 'Không rõ người cấp'} · {formatDate(item.created_at)}</small>{!item.revoked_at ? <button className="btn small secondary danger-text" type="button" onClick={() => revokeAssignment(item.id)}>Thu hồi quyền</button> : null}</article>)}{!assignments.some((item) => item.user_id === selectedUserId) ? <div className="empty-state">Không có assignment.</div> : null}</div>
    </SideDrawer>

    {isSystemAdmin && <SideDrawer open={importOpen} title="Import phân quyền bằng Excel" description="Dùng template chuẩn, chạy kiểm tra trước khi ghi assignment." onClose={() => setImportOpen(false)} width="medium">
      <div className="import-steps"><div><b>1</b><span>Tải file mẫu</span></div><div><b>2</b><span>Điền người dùng và phạm vi</span></div><div><b>3</b><span>Kiểm tra thử</span></div><div><b>4</b><span>Import chính thức</span></div></div>
      <div className="button-row"><button className="btn secondary" onClick={downloadTemplate}>Tải Excel mẫu</button></div>
      <label>Chọn file Excel</label><input className="input" type="file" accept=".xlsx,.xlsm" onChange={onFileChange} />
      <label className="check-row"><input type="checkbox" checked={dryRun} onChange={(event) => setDryRun(event.target.checked)} /> Kiểm tra trước, chưa ghi dữ liệu</label>
      <div className="button-row"><button className="btn" onClick={submitImport}>{dryRun ? 'Kiểm tra file' : 'Import phân quyền'}</button></div>
      {importResult && <div className="import-result"><div className="summary-grid"><div><span>Tổng dòng</span><b>{importResult.total_rows}</b></div><div><span>Hợp lệ</span><b>{importResult.valid_rows}</b></div><div><span>Đã tạo</span><b>{importResult.created_count}</b></div><div><span>Lỗi</span><b>{importResult.failed_count}</b></div></div><div className="import-row-list">{importResult.rows.slice(0, 30).map((row) => <div key={row.row_index} className="stat-row"><span>Dòng {row.row_index} · {row.user_id} · {row.role_code}</span><b className={`status ${resultClass(row.status)}`}>{row.status}</b><small>{row.message}</small></div>)}</div></div>}
    </SideDrawer>}
  </PageRoot>
}
