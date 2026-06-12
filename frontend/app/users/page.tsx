'use client'

import { useEffect, useState } from 'react'
import { getUserAnalytics } from '../../lib/api'
import { useAppContext } from '../../context/AppContext'
import { ActionMessage, ActionMessageData, toUserError } from '../../components/ui/ActionMessage'
import { UserAnalyticsResponse } from '../../types'

export default function UsersPage() {
  const { authHeaders, can, accessToken } = useAppContext()
  const [data, setData] = useState<UserAnalyticsResponse | null>(null)
  const [search, setSearch] = useState('')
  const [sortBy, setSortBy] = useState('cost_usd')
  const [sortDir, setSortDir] = useState('desc')
  const [message, setMessage] = useState<ActionMessageData | null>(null)

  async function load() {
    if (!can('view_user_analytics')) {
      setData(null)
      setMessage({
        type: 'warning',
        title: 'Không đủ quyền',
        body: accessToken.trim()
          ? 'Token hiện tại không có quyền view_user_analytics.'
          : 'Chỉ admin/manager có quyền xem thống kê theo từng người dùng.',
      })
      return
    }
    try {
      const nextData = await getUserAnalytics('', { search, sortBy, sortDir }, authHeaders()) as UserAnalyticsResponse
      setData(nextData)
      setMessage(null)
    } catch (e) {
      setMessage(toUserError(e, 'Không tải được thống kê người dùng. Kiểm tra quyền admin, migration DB và backend logs.'))
    }
  }

  useEffect(() => { load() }, [])

  return <div className="page-stack">
    <section className="hero-card">
      <div>
        <div className="eyebrow">Thống kê người dùng</div>
        <h2>Thống kê theo từng người dùng</h2>
        <p>Theo dõi giáo viên làm việc trong luồng ngân hàng đề: tạo câu hỏi, duyệt, publish, tạo Quiz, rollback, lỗi và chi phí.</p>
      </div>
    </section>

    <section className="card">
      <div className="grid grid-3">
        <div><label>Tìm người dùng</label><input className="input" value={search} onChange={(e) => setSearch(e.target.value)} placeholder="teacher, reviewer..." /></div>
        <div><label>Sắp xếp theo</label><select className="input" value={sortBy} onChange={(e) => setSortBy(e.target.value)}><option value="cost_usd">cost_usd</option><option value="generate_jobs">generate_jobs</option><option value="questions_requested">questions_requested</option><option value="approved">Đã duyệt</option><option value="rejected">Đã từ chối</option><option value="published">published</option><option value="edits">edits</option><option value="input_tokens">input_tokens</option><option value="cached_input_tokens">cached_input_tokens</option><option value="output_tokens">output_tokens</option><option value="estimate_accuracy_percent">estimate_accuracy_percent</option><option value="actual_cost_usd">actual_cost_usd</option><option value="last_activity">last_activity</option><option value="audit_actions">Thao tác</option><option value="audit_failed">Lỗi thao tác</option><option value="quiz_creates">Tạo Quiz</option><option value="release_publishes">Publish release</option><option value="rollbacks">Rollback</option></select></div>
        <div><label>Chiều sắp xếp</label><select className="input" value={sortDir} onChange={(e) => setSortDir(e.target.value)}><option value="desc">desc</option><option value="asc">asc</option></select></div>
      </div>
      <div className="button-row"><button className="btn" onClick={load}>Áp dụng</button></div>
    </section>

    <ActionMessage message={message} onClose={() => setMessage(null)} />

    <section className="card">
      <div className="section-head"><div><h2>Danh sách người dùng</h2><p className="helper">Tổng người dùng: {data?.total_users || 0}</p></div></div>
      <div className="table-wrap">
        <table className="table user-table">
          <thead><tr><th>Người dùng</th><th>Thao tác</th><th>Jobs</th><th>Câu hỏi</th><th>Review</th><th>Quiz/Release</th><th>Tokens</th><th>Chi phí</th><th>Hoạt động cuối</th></tr></thead>
          <tbody>{(data?.users || []).map((u) => <tr key={u.user_id}>
            <td><b>{u.user_id}</b><br /><span className="helper">{u.last_action || '—'}</span></td>
            <td>Tổng {u.audit_actions || 0}<br />Lỗi {u.audit_failed || 0}<br />Bank {u.bank_entity_changes || 0}</td>
            <td>{u.generate_jobs}</td>
            <td>{u.questions_requested}</td>
            <td>Approve {u.approved}<br />Reject {u.rejected}<br />Publish {u.published}<br />Sửa {u.edits}</td>
            <td>Quiz {u.quiz_creates || 0}<br />Release {u.release_publishes || 0}<br />Rollback {u.rollbacks || 0}</td>
            <td>In {u.input_tokens.toLocaleString('vi-VN')}<br />Đã cache {u.cached_input_tokens.toLocaleString('vi-VN')}<br />Output {u.output_tokens.toLocaleString('vi-VN')}</td>
            <td>Est {'$'}{u.estimated_cost_usd.toLocaleString('vi-VN')}<br />Actual {'$'}{u.actual_cost_usd.toLocaleString('vi-VN')}<br />{u.cost_vnd.toLocaleString('vi-VN')} VND<br />Acc {u.estimate_accuracy_percent}%</td>
            <td>{u.last_activity || '—'}</td>
          </tr>)}</tbody>
        </table>
        {!(data?.users || []).length && <div className="empty-state">Chưa có usage/review log theo user.</div>}
      </div>
    </section>
  </div>
}
