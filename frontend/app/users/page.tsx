'use client'

import { ChangeEvent, useEffect, useMemo, useState } from 'react'
import {
  createRoleAssignment,
  downloadRBACImportTemplate,
  getDepartments,
  getEffectiveRBAC,
  getRBACRoles,
  getRoleAssignments,
  getSubjectChapters,
  getSubjectOfferings,
  getSubjects,
  importRoleAssignmentsFromExcel,
  revokeRoleAssignment,
} from '../../lib/api'
import { useAppContext } from '../../context/AppContext'
import { ActionMessage, ActionMessageData, toUserError } from '../../components/ui/ActionMessage'
import {
  BusinessRoleCode,
  BusinessScopeType,
  Department,
  EffectiveRBAC,
  RBACRole,
  RoleAssignment,
  RoleAssignmentImportResponse,
  Subject,
  SubjectChapter,
  SubjectOffering,
} from '../../types'

const roleLabels: Record<string, string> = {
  SYSTEM_ADMIN: 'Quản trị web',
  DEPARTMENT_HEAD: 'Trưởng bộ môn',
  SUBJECT_OWNER: 'Chủ môn',
  QUESTION_REVIEWER: 'Người duyệt câu hỏi',
}

const roleSubtitles: Record<string, string> = {
  SYSTEM_ADMIN: 'Toàn hệ thống. Chỉ dành cho admin kỹ thuật/ban quản trị.',
  DEPARTMENT_HEAD: 'Quản lý các môn, version, bài và reviewer trong một bộ môn.',
  SUBJECT_OWNER: 'Quản lý một môn hoặc một version/kỳ cụ thể.',
  QUESTION_REVIEWER: 'Chỉ xem, sửa, duyệt hoặc từ chối câu hỏi trong scope được giao.',
}

const roleTone: Record<string, string> = {
  SYSTEM_ADMIN: 'danger',
  DEPARTMENT_HEAD: 'blue',
  SUBJECT_OWNER: 'violet',
  QUESTION_REVIEWER: 'green',
}

const allowedScopesByRole: Record<string, BusinessScopeType[]> = {
  SYSTEM_ADMIN: ['SYSTEM'],
  DEPARTMENT_HEAD: ['DEPARTMENT'],
  SUBJECT_OWNER: ['SUBJECT', 'SUBJECT_VERSION'],
  QUESTION_REVIEWER: ['SUBJECT', 'SUBJECT_VERSION', 'CHAPTER'],
}

const scopeLabel: Record<string, string> = {
  SYSTEM: 'Toàn hệ thống',
  DEPARTMENT: 'Bộ môn',
  SUBJECT: 'Môn học',
  SUBJECT_VERSION: 'Version/kỳ môn',
  CHAPTER: 'Bài / chapter',
  COURSE: 'Course Open edX',
}

function formatDate(value?: string | null) {
  if (!value) return '—'
  try { return new Date(value).toLocaleString('vi-VN') } catch { return value }
}

function resultClass(status: string) {
  if (status === 'created' || status === 'success' || status === 'valid') return 'approved'
  if (status === 'skipped') return 'pending'
  if (status === 'failed' || status === 'error') return 'rejected'
  return 'warning'
}

function Popup({ open, title, children, onClose }: { open: boolean; title: string; children: React.ReactNode; onClose: () => void }) {
  useEffect(() => {
    if (!open) return undefined
    const prev = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    const onKey = (event: KeyboardEvent) => { if (event.key === 'Escape') onClose() }
    document.addEventListener('keydown', onKey)
    return () => { document.body.style.overflow = prev; document.removeEventListener('keydown', onKey) }
  }, [open, onClose])
  if (!open) return null
  return <div className="modal-backdrop bank-popup-backdrop" onMouseDown={onClose}>
    <section className="modal-card bank-modal bank-modal-wide" role="dialog" aria-modal="true" onMouseDown={(event) => event.stopPropagation()}>
      <div className="section-head bank-modal-head"><div><h2>{title}</h2></div><button className="btn small secondary" onClick={onClose}>Đóng</button></div>
      <div className="bank-modal-body">{children}</div>
    </section>
  </div>
}

export default function UsersPage() {
  const { authHeaders } = useAppContext()
  const [message, setMessage] = useState<ActionMessageData | null>(null)
  const [loading, setLoading] = useState(false)
  const [effective, setEffective] = useState<EffectiveRBAC | null>(null)
  const [roles, setRoles] = useState<RBACRole[]>([])
  const [assignments, setAssignments] = useState<RoleAssignment[]>([])
  const [departments, setDepartments] = useState<Department[]>([])
  const [subjects, setSubjects] = useState<Subject[]>([])
  const [offerings, setOfferings] = useState<SubjectOffering[]>([])
  const [chapters, setChapters] = useState<SubjectChapter[]>([])
  const [filterText, setFilterText] = useState('')
  const [includeRevoked, setIncludeRevoked] = useState(false)
  const [importFile, setImportFile] = useState<File | null>(null)
  const [dryRun, setDryRun] = useState(true)
  const [importResult, setImportResult] = useState<RoleAssignmentImportResponse | null>(null)
  const [scopeSearch, setScopeSearch] = useState('')
  const [importOpen, setImportOpen] = useState(false)
  const [assignmentsOpen, setAssignmentsOpen] = useState(false)
  const [scopeDropdownOpen, setScopeDropdownOpen] = useState(false)
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
  ] as RBACRole[], [])
  const visibleRoles = roles.length ? roles : fallbackRoles
  const availableScopes = allowedScopesByRole[form.role_code] || ['SYSTEM']
  const scopeOptions = useMemo(() => {
    const needle = scopeSearch.trim().toLowerCase()
    const filter = <T extends { id: string; label: string; path: string }>(rows: T[]) => needle ? rows.filter((row) => [row.id, row.label, row.path].some((value) => String(value || '').toLowerCase().includes(needle))) : rows
    if (form.scope_type === 'SYSTEM') return [{ id: '*', label: 'Toàn hệ thống', path: 'SYSTEM' }]
    if (form.scope_type === 'DEPARTMENT') return filter(departments.map((d) => ({ id: d.id, label: `${d.code} · ${d.name}`, path: `Bộ môn / ${d.code}` })))
    if (form.scope_type === 'SUBJECT') return filter(subjects.map((s) => ({ id: s.id, label: `${s.code} · ${s.name}`, path: `Môn / ${s.code}` })))
    if (form.scope_type === 'SUBJECT_VERSION') return filter(offerings.map((o) => ({ id: o.id, label: `${o.code} · ${o.name || o.version_code}`, path: `Version / ${o.code}` })))
    if (form.scope_type === 'CHAPTER') return filter(chapters.map((c) => ({ id: c.id, label: c.title, path: `Bài / ${c.title}` })))
    return []
  }, [chapters, departments, form.scope_type, offerings, scopeSearch, subjects])

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

  const assignmentStats = useMemo(() => {
    const active = assignments.filter((a) => !a.revoked_at)
    return {
      total: active.length,
      heads: active.filter((a) => a.role_code === 'DEPARTMENT_HEAD').length,
      owners: active.filter((a) => a.role_code === 'SUBJECT_OWNER').length,
      reviewers: active.filter((a) => a.role_code === 'QUESTION_REVIEWER').length,
    }
  }, [assignments])

  function syncScopeForRole(nextRole: BusinessRoleCode) {
    const scopes = allowedScopesByRole[nextRole] || ['SYSTEM']
    setForm((prev) => ({ ...prev, role_code: nextRole, scope_type: scopes[0], scope_id: scopes[0] === 'SYSTEM' ? '*' : '' }))
  }

  async function loadAll() {
    setLoading(true)
    try {
      const headers = authHeaders()
      const [me, roleRows, assignmentRows, departmentRows] = await Promise.all([
        getEffectiveRBAC(headers),
        getRBACRoles(headers),
        getRoleAssignments(headers, { includeRevoked }),
        getDepartments(headers),
      ])
      setEffective(me)
      setRoles(roleRows)
      setAssignments(assignmentRows.items)
      setDepartments(departmentRows)
      const [subjectRows, offeringRows, chapterRows] = await Promise.all([
        getSubjects(headers),
        getSubjectOfferings(headers),
        getSubjectChapters(headers),
      ])
      setSubjects(subjectRows)
      setOfferings(offeringRows)
      setChapters(chapterRows)
      setMessage(null)
    } catch (e) {
      setMessage(toUserError(e, 'Không tải được trang phân quyền. Kiểm tra token, RBAC scope và backend logs.'))
    } finally {
      setLoading(false)
    }
  }

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
      setMessage(toUserError(e, 'Không gán được quyền. Kiểm tra đúng role, scope và quyền người đang thao tác.'))
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

  return <div className="page-stack access-console">
    <section className="access-hero">
      <div className="access-hero-grid">
        <div>
          <div className="eyebrow">AI Question Bank · RBAC</div>
          <h2>Quản lý quyền truy cập</h2>
          <p>Gán quyền theo đúng nhánh công việc. Giao diện chỉ hiển thị scope bạn được phép quản lý.</p>
        </div>
        <div className="access-session-card">
          <span>Phiên hiện tại</span>
          <b>{effective?.effective_legacy_role || effective?.legacy_role || '—'}</b>
          <small>{effective?.assignments?.length || 0} quyền đang hiệu lực</small>
          <button className="btn secondary" onClick={loadAll} disabled={loading}>{loading ? 'Đang tải...' : 'Làm mới'}</button>
        </div>
      </div>
    </section>

    <ActionMessage message={message} onClose={() => setMessage(null)} />

    <section className="access-kpi-grid">
      <div className="access-kpi"><span>Quyền đang hiệu lực</span><b>{assignmentStats.total}</b><small>Trong phạm vi bạn quản lý</small></div>
      <div className="access-kpi"><span>Trưởng bộ môn</span><b>{assignmentStats.heads}</b><small>DEPARTMENT_HEAD</small></div>
      <div className="access-kpi"><span>Chủ môn</span><b>{assignmentStats.owners}</b><small>SUBJECT_OWNER</small></div>
      <div className="access-kpi"><span>Người duyệt</span><b>{assignmentStats.reviewers}</b><small>QUESTION_REVIEWER</small></div>
    </section>

    <section className="access-main-grid">
      <div className="card access-card-large">
        <div className="section-head">
          <div><h2>Gán quyền nhanh</h2><p className="helper">Chọn vai trò, rồi chọn đúng phạm vi cần giao.</p></div>
        </div>
        <div className="role-picker-grid">
          {visibleRoles.map((role) => <button type="button" key={role.code} className={`role-choice ${form.role_code === role.code ? 'selected' : ''} tone-${roleTone[role.code] || 'blue'}`} onClick={() => syncScopeForRole(role.code as BusinessRoleCode)}>
            <span>{roleLabels[role.code] || role.name}</span>
            <b>{role.code}</b>
            <small>{roleSubtitles[role.code] || role.description}</small>
          </button>)}
        </div>
        <div className="grid grid-2">
          <div><label>User ID / username Open edX</label><input className="input" value={form.user_id} onChange={(e) => setForm({ ...form, user_id: e.target.value })} placeholder="vd: owner_web107" /></div>
          <div><label>Email</label><input className="input" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} placeholder="user@fpt.edu.vn" /></div>
        </div>
        <div className="grid grid-3">
          <div><label>Loại phạm vi</label><select className="input" value={form.scope_type} onChange={(e) => { setScopeSearch(''); setForm({ ...form, scope_type: e.target.value as BusinessScopeType, scope_id: e.target.value === 'SYSTEM' ? '*' : '' }) }}>
            {availableScopes.map((scope) => <option key={scope} value={scope}>{scopeLabel[scope]} · {scope}</option>)}
          </select></div>
          <div className="searchable-scope-field"><label>Phạm vi cụ thể</label><div className={`searchable-select ${scopeDropdownOpen ? 'open' : ''} ${form.scope_type === 'SYSTEM' ? 'disabled' : ''}`}>
            <button className="input searchable-select-trigger" type="button" disabled={form.scope_type === 'SYSTEM'} onClick={() => setScopeDropdownOpen((value) => !value)}>
              <span>{form.scope_type === 'SYSTEM' ? 'Toàn hệ thống' : selectedScopeOption?.label || 'Chọn phạm vi'}</span>
              <b>⌄</b>
            </button>
            {scopeDropdownOpen && form.scope_type !== 'SYSTEM' ? <div className="searchable-select-menu">
              <input className="input scope-search-input" value={scopeSearch} onChange={(e) => setScopeSearch(e.target.value)} placeholder="Gõ mã môn, tên bộ môn, bài..." autoFocus />
              <div className="searchable-select-list">
                {scopeOptions.map((item) => <button type="button" className={`searchable-select-option ${form.scope_id === item.id ? 'selected' : ''}`} key={item.id} onClick={() => chooseScopeOption(item.id)}>
                  <b>{item.label}</b><small>{item.path}</small>
                </button>)}
                {!scopeOptions.length ? <div className="empty-state small-empty">Không tìm thấy phạm vi phù hợp.</div> : null}
              </div>
            </div> : null}
          </div><small className="helper">Mở dropdown rồi gõ để tìm nhanh trong phạm vi bạn được phép quản lý.</small></div>
          <div><label>Lý do cấp quyền</label><input className="input" value={form.grant_reason} onChange={(e) => setForm({ ...form, grant_reason: e.target.value })} placeholder="Phụ trách WEB107 SU26" /></div>
        </div>
        {form.scope_id && <div className="scope-preview"><span>Quyền sẽ được cấp</span><b>{roleLabels[form.role_code]} · {scopeLabel[form.scope_type]}</b><small>{scopeOptions.find((s) => s.id === form.scope_id)?.path || form.scope_id}</small></div>}
        <label className="check-row"><input type="checkbox" checked={form.sync_openedx} onChange={(e) => setForm({ ...form, sync_openedx: e.target.checked })} /> Ghi nhận yêu cầu sync Open edX trong metadata</label>
        <div className="button-row"><button className="btn" onClick={submitAssignment}>Gán quyền</button><button className="btn secondary" onClick={() => setForm({ user_id: '', email: '', role_code: 'DEPARTMENT_HEAD', scope_type: 'DEPARTMENT', scope_id: '', grant_reason: '', sync_openedx: false })}>Xóa form</button></div>
      </div>

      <div className="card access-side-actions">
        <div className="section-head"><div><h2>Công cụ</h2><p className="helper">Mở khi cần, tránh trang chính quá nhiều thông tin.</p></div></div>
        <button className="btn secondary full-width" type="button" onClick={() => setImportOpen(true)}>Import bằng Excel</button>
        <button className="btn secondary full-width" type="button" onClick={() => setAssignmentsOpen(true)}>Danh sách quyền đang có ({assignmentStats.total})</button>
        <button className="btn secondary full-width" type="button" onClick={downloadTemplate}>Tải Excel mẫu</button>
      </div>
    </section>

    <Popup open={importOpen} title="Import phân quyền bằng Excel" onClose={() => setImportOpen(false)}>
      <div className="import-steps"><div><b>1</b><span>Tải file mẫu</span></div><div><b>2</b><span>Điền user, role, scope</span></div><div><b>3</b><span>Dry-run kiểm tra</span></div><div><b>4</b><span>Import thật</span></div></div>
      <div className="button-row"><button className="btn secondary" onClick={downloadTemplate}>Tải Excel mẫu</button></div>
      <label>Chọn file Excel</label><input className="input" type="file" accept=".xlsx,.xlsm" onChange={onFileChange} />
      <label className="check-row"><input type="checkbox" checked={dryRun} onChange={(e) => setDryRun(e.target.checked)} /> Dry-run trước, chưa ghi DB</label>
      <div className="button-row"><button className="btn" onClick={submitImport}>{dryRun ? 'Kiểm tra file' : 'Import phân quyền'}</button></div>
      {importResult && <div className="import-result"><div className="summary-grid"><div><span>Tổng dòng</span><b>{importResult.total_rows}</b></div><div><span>Hợp lệ</span><b>{importResult.valid_rows}</b></div><div><span>Đã tạo</span><b>{importResult.created_count}</b></div><div><span>Lỗi</span><b>{importResult.failed_count}</b></div></div><div className="import-row-list">{importResult.rows.slice(0, 30).map((row) => <div key={row.row_index} className="stat-row"><span>Dòng {row.row_index} · {row.user_id} · {row.role_code}</span><b className={`status ${resultClass(row.status)}`}>{row.status}</b><small>{row.message}</small></div>)}</div></div>}
    </Popup>

    <Popup open={assignmentsOpen} title="Danh sách quyền đang có" onClose={() => setAssignmentsOpen(false)}>
      <div className="section-head compact-section-head"><div><p className="helper">Chỉ hiển thị các quyền bạn được phép nhìn thấy hoặc quản lý.</p></div><label className="check-row"><input type="checkbox" checked={includeRevoked} onChange={(e) => setIncludeRevoked(e.target.checked)} /> Cả quyền đã thu hồi</label></div>
      <div className="grid grid-3"><div><label>Tìm trong danh sách</label><input className="input" value={filterText} onChange={(e) => setFilterText(e.target.value)} placeholder="user, role, scope..." /></div></div>
      <div className="assignment-board modal-assignment-board">
        {filteredAssignments.map((a) => <article className={`assignment-card ${a.revoked_at ? 'is-revoked' : ''}`} key={a.id}>
          <div className="assignment-top"><span className={`role-dot tone-${roleTone[a.role_code] || 'blue'}`}>{roleLabels[a.role_code] || a.role_code}</span><span className="pill">{a.scope_type}</span></div>
          <h3>{a.user_id}</h3>
          <p>{a.email || 'Chưa có email'} · {a.scope_label || a.scope_id}</p>
          <code>{a.scope_type}:{a.scope_id}</code>
          <div className="assignment-meta"><span>Cấp bởi {a.granted_by || '—'}</span><span>{formatDate(a.created_at)}</span></div>
          {a.grant_reason && <small>{a.grant_reason}</small>}
          {a.revoked_at ? <b className="status rejected">Đã thu hồi</b> : <button className="btn small danger" onClick={() => revokeAssignment(a.id)}>Thu hồi</button>}
        </article>)}
        {!filteredAssignments.length && <div className="empty-state">Chưa có quyền nào trong phạm vi bạn được xem.</div>}
      </div>
    </Popup>
  </div>
}
