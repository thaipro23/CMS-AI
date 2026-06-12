'use client'

import { useEffect, useMemo, useState } from 'react'
import {
  createRoleAssignment,
  getDepartments,
  getEffectiveRBAC,
  getRBACRoles,
  getRoleAssignments,
  getSubjectChapters,
  getSubjectOfferings,
  getSubjects,
  getUserAnalytics,
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
  Subject,
  SubjectChapter,
  SubjectOffering,
  UserAnalyticsResponse,
} from '../../types'

const roleHelp: Record<string, string> = {
  SYSTEM_ADMIN: 'Quản trị web: full quyền toàn hệ thống.',
  DEPARTMENT_HEAD: 'Trưởng bộ môn: full quyền trong bộ môn được giao.',
  SUBJECT_OWNER: 'Chủ môn: full quyền trong môn/phiên bản môn được giao.',
  QUESTION_REVIEWER: 'Người duyệt: sửa/duyệt/từ chối câu hỏi trong scope được giao.',
}

const allowedScopesByRole: Record<string, BusinessScopeType[]> = {
  SYSTEM_ADMIN: ['SYSTEM'],
  DEPARTMENT_HEAD: ['DEPARTMENT'],
  SUBJECT_OWNER: ['SUBJECT', 'SUBJECT_VERSION'],
  QUESTION_REVIEWER: ['SUBJECT', 'SUBJECT_VERSION', 'CHAPTER'],
}

export default function UsersPage() {
  const { authHeaders, can, accessToken } = useAppContext()
  const [data, setData] = useState<UserAnalyticsResponse | null>(null)
  const [search, setSearch] = useState('')
  const [sortBy, setSortBy] = useState('cost_usd')
  const [sortDir, setSortDir] = useState('desc')
  const [message, setMessage] = useState<ActionMessageData | null>(null)

  const [effective, setEffective] = useState<EffectiveRBAC | null>(null)
  const [roles, setRoles] = useState<RBACRole[]>([])
  const [assignments, setAssignments] = useState<RoleAssignment[]>([])
  const [departments, setDepartments] = useState<Department[]>([])
  const [subjects, setSubjects] = useState<Subject[]>([])
  const [offerings, setOfferings] = useState<SubjectOffering[]>([])
  const [chapters, setChapters] = useState<SubjectChapter[]>([])
  const [rbacSearch, setRbacSearch] = useState('')
  const [form, setForm] = useState({
    user_id: '',
    email: '',
    role_code: 'DEPARTMENT_HEAD' as BusinessRoleCode,
    scope_type: 'DEPARTMENT' as BusinessScopeType,
    scope_id: '',
    grant_reason: '',
    sync_openedx: false,
  })

  const availableScopes = allowedScopesByRole[form.role_code] || ['SYSTEM']

  const scopeOptions = useMemo(() => {
    if (form.scope_type === 'SYSTEM') return [{ id: '*', label: 'Toàn hệ thống' }]
    if (form.scope_type === 'DEPARTMENT') return departments.map((d) => ({ id: d.id, label: `${d.code} · ${d.name}` }))
    if (form.scope_type === 'SUBJECT') return subjects.map((s) => ({ id: s.id, label: `${s.code} · ${s.name}` }))
    if (form.scope_type === 'SUBJECT_VERSION') return offerings.map((o) => ({ id: o.id, label: `${o.code} · ${o.name || o.version_code}` }))
    if (form.scope_type === 'CHAPTER') return chapters.map((c) => ({ id: c.id, label: c.title }))
    return []
  }, [chapters, departments, form.scope_type, offerings, subjects])

  function syncScopeForRole(nextRole: BusinessRoleCode) {
    const scopes = allowedScopesByRole[nextRole] || ['SYSTEM']
    setForm((prev) => ({ ...prev, role_code: nextRole, scope_type: scopes[0], scope_id: scopes[0] === 'SYSTEM' ? '*' : '' }))
  }

  async function loadAnalytics() {
    if (!can('view_user_analytics')) {
      setData(null)
      setMessage({
        type: 'warning',
        title: 'Không đủ quyền xem thống kê',
        body: accessToken.trim()
          ? 'Token hiện tại không có quyền view_user_analytics. Phần phân quyền nghiệp vụ vẫn sẽ tải nếu bạn có role SYSTEM_ADMIN/DEPARTMENT_HEAD/SUBJECT_OWNER phù hợp.'
          : 'Bạn cần phiên CMS/AI hợp lệ để xem thống kê người dùng.',
      })
      return
    }
    try {
      const nextData = await getUserAnalytics('', { search, sortBy, sortDir }, authHeaders()) as UserAnalyticsResponse
      setData(nextData)
    } catch (e) {
      setMessage(toUserError(e, 'Không tải được thống kê người dùng. Kiểm tra quyền admin, migration DB và backend logs.'))
    }
  }

  async function loadRBAC() {
    try {
      const headers = authHeaders()
      const [me, roleRows, assignmentRows, departmentRows] = await Promise.all([
        getEffectiveRBAC(headers),
        getRBACRoles(headers),
        getRoleAssignments(headers, rbacSearch.trim() ? { userId: rbacSearch.trim() } : {}),
        getDepartments(headers),
      ])
      setEffective(me)
      setRoles(roleRows)
      setAssignments(assignmentRows.items)
      setDepartments(departmentRows)
      const subjectRows = await getSubjects(headers)
      setSubjects(subjectRows)
      const offeringRows = await getSubjectOfferings(headers)
      setOfferings(offeringRows)
      const chapterRows = await getSubjectChapters(headers)
      setChapters(chapterRows)
      setMessage(null)
    } catch (e) {
      setMessage(toUserError(e, 'Không tải được phân quyền nghiệp vụ. Hãy chạy alembic upgrade head và đảm bảo bạn có quyền RBAC trong scope phù hợp.'))
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
        grant_reason: form.grant_reason,
        sync_openedx: form.sync_openedx,
      }, authHeaders(true))
      setMessage({ type: 'success', title: 'Đã gán quyền', body: 'Assignment đã được lưu trong AI Server RBAC. Người dùng đăng nhập lại CMS/AI để nhận effective role mới.' })
      setForm((prev) => ({ ...prev, user_id: '', email: '', grant_reason: '' }))
      await loadRBAC()
    } catch (e) {
      setMessage(toUserError(e, 'Không gán được quyền. Kiểm tra role của bạn và scope đang chọn.'))
    }
  }

  async function revokeAssignment(id: string) {
    try {
      await revokeRoleAssignment(id, authHeaders(true), 'Thu hồi từ màn Người dùng')
      setMessage({ type: 'success', title: 'Đã thu hồi quyền', body: 'Assignment đã được đánh dấu revoked, không xóa cứng để giữ audit.' })
      await loadRBAC()
    } catch (e) {
      setMessage(toUserError(e, 'Không thu hồi được quyền.'))
    }
  }

  useEffect(() => { loadAnalytics(); loadRBAC() }, [])

  return <div className="page-stack">
    <section className="hero-card">
      <div>
        <div className="eyebrow">Người dùng & phân quyền</div>
        <h2>RBAC nghiệp vụ Bank-first</h2>
        <p>Quản trị web → Trưởng bộ môn → Chủ môn → Người duyệt câu hỏi. Role nghiệp vụ nằm trong AI Server; Open edX chỉ giữ quyền kỹ thuật tối thiểu.</p>
      </div>
    </section>

    <ActionMessage message={message} onClose={() => setMessage(null)} />

    <section className="card">
      <div className="section-head">
        <div>
          <h2>Phiên hiện tại</h2>
          <p className="helper">Legacy role từ token: <b>{effective?.legacy_role || '—'}</b> · effective role sau RBAC: <b>{effective?.effective_legacy_role || '—'}</b></p>
        </div>
        <button className="btn secondary" onClick={loadRBAC}>Tải lại RBAC</button>
      </div>
      <div className="grid grid-4">
        {(roles || []).map((r) => <div className="mini-card" key={r.code}>
          <b>{r.name}</b>
          <p>{roleHelp[r.code] || r.description}</p>
          <span className="pill">{r.code}</span>
        </div>)}
      </div>
    </section>

    <section className="card">
      <div className="section-head">
        <div><h2>Gán quyền nghiệp vụ</h2><p className="helper">Admin gán Trưởng bộ môn; Trưởng bộ môn gán Chủ môn; Chủ môn gán Người duyệt.</p></div>
      </div>
      <div className="grid grid-3">
        <div><label>User ID / username Open edX</label><input className="input" value={form.user_id} onChange={(e) => setForm({ ...form, user_id: e.target.value })} placeholder="head_cntt / owner_dbi / reviewer1" /></div>
        <div><label>Email</label><input className="input" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} placeholder="user@fpt.edu.vn" /></div>
        <div><label>Role nghiệp vụ</label><select className="input" value={form.role_code} onChange={(e) => syncScopeForRole(e.target.value as BusinessRoleCode)}>
          {(roles.length ? roles : [{ code: 'SYSTEM_ADMIN', name: 'Quản trị web' }, { code: 'DEPARTMENT_HEAD', name: 'Trưởng bộ môn' }, { code: 'SUBJECT_OWNER', name: 'Chủ môn' }, { code: 'QUESTION_REVIEWER', name: 'Người duyệt câu hỏi' }] as any[]).map((r) => <option value={r.code} key={r.code}>{r.name} · {r.code}</option>)}
        </select></div>
        <div><label>Scope type</label><select className="input" value={form.scope_type} onChange={(e) => setForm({ ...form, scope_type: e.target.value as BusinessScopeType, scope_id: e.target.value === 'SYSTEM' ? '*' : '' })}>
          {availableScopes.map((scope) => <option key={scope} value={scope}>{scope}</option>)}
        </select></div>
        <div><label>Scope</label><select className="input" value={form.scope_id} onChange={(e) => setForm({ ...form, scope_id: e.target.value })} disabled={form.scope_type === 'SYSTEM'}>
          {form.scope_type === 'SYSTEM' ? <option value="*">Toàn hệ thống</option> : <option value="">-- chọn scope --</option>}
          {scopeOptions.map((item) => <option value={item.id} key={item.id}>{item.label}</option>)}
        </select></div>
        <div><label>Lý do</label><input className="input" value={form.grant_reason} onChange={(e) => setForm({ ...form, grant_reason: e.target.value })} placeholder="Phụ trách DBI102 SU26..." /></div>
      </div>
      <div className="button-row">
        <label className="inline-check"><input type="checkbox" checked={form.sync_openedx} onChange={(e) => setForm({ ...form, sync_openedx: e.target.checked })} /> Ghi nhận yêu cầu sync Open edX sau</label>
        <button className="btn" onClick={submitAssignment}>Gán quyền</button>
      </div>
    </section>

    <section className="card">
      <div className="section-head"><div><h2>Assignment đang hiệu lực</h2><p className="helper">Tổng assignment: {assignments.length}</p></div></div>
      <div className="grid grid-3">
        <div><label>Lọc theo user_id</label><input className="input" value={rbacSearch} onChange={(e) => setRbacSearch(e.target.value)} placeholder="reviewer1" /></div>
        <div className="button-row"><button className="btn secondary" onClick={loadRBAC}>Lọc</button></div>
      </div>
      <div className="table-wrap">
        <table className="table user-table">
          <thead><tr><th>User</th><th>Role</th><th>Scope</th><th>Người gán</th><th>Ngày gán</th><th></th></tr></thead>
          <tbody>{assignments.map((a) => <tr key={a.id}>
            <td><b>{a.user_id}</b><br /><span className="helper">{a.email || '—'}</span></td>
            <td><b>{a.role_name || a.role_code}</b><br /><span className="pill">{a.role_code}</span></td>
            <td>{a.scope_label || a.scope_id}<br /><span className="helper">{a.scope_type}:{a.scope_id}</span></td>
            <td>{a.granted_by || '—'}<br /><span className="helper">{a.grant_reason || '—'}</span></td>
            <td>{a.created_at}</td>
            <td><button className="btn small danger" onClick={() => revokeAssignment(a.id)}>Thu hồi</button></td>
          </tr>)}</tbody>
        </table>
        {!assignments.length && <div className="empty-state">Chưa có assignment RBAC phù hợp với scope của bạn.</div>}
      </div>
    </section>

    <section className="card">
      <div className="section-head"><div><h2>Thống kê hoạt động</h2><p className="helper">Tổng người dùng: {data?.total_users || 0}</p></div></div>
      <div className="grid grid-3">
        <div><label>Tìm người dùng</label><input className="input" value={search} onChange={(e) => setSearch(e.target.value)} placeholder="teacher, reviewer..." /></div>
        <div><label>Sắp xếp theo</label><select className="input" value={sortBy} onChange={(e) => setSortBy(e.target.value)}><option value="cost_usd">cost_usd</option><option value="generate_jobs">generate_jobs</option><option value="questions_requested">questions_requested</option><option value="approved">Đã duyệt</option><option value="rejected">Đã từ chối</option><option value="audit_actions">Thao tác</option><option value="audit_failed">Lỗi thao tác</option><option value="last_activity">last_activity</option></select></div>
        <div><label>Chiều sắp xếp</label><select className="input" value={sortDir} onChange={(e) => setSortDir(e.target.value)}><option value="desc">desc</option><option value="asc">asc</option></select></div>
      </div>
      <div className="button-row"><button className="btn secondary" onClick={loadAnalytics}>Áp dụng thống kê</button></div>
      <div className="table-wrap">
        <table className="table user-table">
          <thead><tr><th>Người dùng</th><th>Thao tác</th><th>Jobs</th><th>Câu hỏi</th><th>Review</th><th>Quiz/Release</th><th>Chi phí</th><th>Hoạt động cuối</th></tr></thead>
          <tbody>{(data?.users || []).map((u) => <tr key={u.user_id}>
            <td><b>{u.user_id}</b><br /><span className="helper">{u.last_action || '—'}</span></td>
            <td>Tổng {u.audit_actions || 0}<br />Lỗi {u.audit_failed || 0}</td>
            <td>{u.generate_jobs}</td>
            <td>{u.questions_requested}</td>
            <td>Approve {u.approved}<br />Reject {u.rejected}<br />Sửa {u.edits}</td>
            <td>Quiz {u.quiz_creates || 0}<br />Release {u.release_publishes || 0}<br />Rollback {u.rollbacks || 0}</td>
            <td>Actual {'$'}{u.actual_cost_usd.toLocaleString('vi-VN')}<br />{u.cost_vnd.toLocaleString('vi-VN')} VND</td>
            <td>{u.last_activity || '—'}</td>
          </tr>)}</tbody>
        </table>
        {!(data?.users || []).length && <div className="empty-state">Chưa có usage/review log theo user hoặc bạn chưa đủ quyền xem thống kê.</div>}
      </div>
    </section>
  </div>
}
