'use client'

import { useEffect, useState } from 'react'
import { getAuditLogs, getCourseQuizInstances, getJobs } from '../../lib/api'
import { useAppContext } from '../../context/AppContext'
import { ActionMessage, ActionMessageData, toUserError } from '../../components/ui/ActionMessage'
import { AuditLogRow, CourseQuizInstance, Job } from '../../types'
import { StatusBadge } from '../../components/ui/StatusBadge'

function money(v: number) { return `$${(v || 0).toFixed(6)}` }
function tokens(v: number) { return (v || 0).toLocaleString('vi-VN') }
function isOpsAudit(row: AuditLogRow) {
  const action = String(row.action || '')
  return action.startsWith('question_bank.') || action.includes('publish') || action.includes('quiz') || action.includes('generation')
}

export default function JobsPage() {
  const { authHeaders, can } = useAppContext()
  const [jobs, setJobs] = useState<Job[]>([])
  const [quizInstances, setQuizInstances] = useState<CourseQuizInstance[]>([])
  const [auditRows, setAuditRows] = useState<AuditLogRow[]>([])
  const [message, setMessage] = useState<ActionMessageData | null>(null)

  async function load() {
    try {
      setMessage(null)
      const headers = authHeaders()
      const [nextJobs, nextQuizInstances, nextAudit] = await Promise.all([
        getJobs('', headers),
        getCourseQuizInstances(headers, { limit: 100 }),
        getAuditLogs('', { page: 1, pageSize: 80 }, headers),
      ])
      setJobs(nextJobs)
      setQuizInstances(nextQuizInstances)
      setAuditRows((nextAudit.items || []).filter(isOpsAudit).slice(0, 30))
    } catch (error) {
      setMessage(toUserError(error))
    }
  }

  useEffect(() => { load() }, [])

  if (!can('view_jobs')) return <div className="card empty-state">Vai trò hiện tại không có quyền xem job.</div>

  return <div className="page-stack">
    <section className="card page-intro">
      <div>
        <div className="eyebrow">Vận hành</div>
        <h2>Tiến trình job</h2>
        <p className="helper">Theo dõi global theo luồng ngân hàng đề: generate câu hỏi, publish release, tạo Quiz Open edX và rollback. Không còn lọc cứng theo course hiện tại.</p>
      </div>
      <button className="btn secondary" onClick={load}>Tải lại</button>
    </section>
    <ActionMessage message={message} onClose={() => setMessage(null)} />

    <section className="card">
      <div className="section-head"><div><h2>Quiz Open edX gần đây</h2><p className="helper">CourseQuizInstance từ luồng /bank/quiz.</p></div></div>
      <div className="table-wrap"><table className="table"><thead><tr><th>Course</th><th>Trạng thái</th><th>Unit Open edX</th><th>Timer</th><th>Thời gian</th></tr></thead><tbody>{quizInstances.length ? quizInstances.map((item) => <tr key={item.id}><td><b>{item.openedx_course_id}</b><br /><span className="helper">{item.metadata_json?.quiz_title || item.bank_release_id}</span></td><td><StatusBadge status={item.status} /></td><td><code>{item.openedx_unit_node_id || '—'}</code></td><td>{item.metadata_json?.timer_config?.custom_timer_enabled ? `${item.metadata_json.timer_config.time_limit_minutes || Math.round((item.metadata_json.timer_config.duration_seconds || 0) / 60)} phút` : 'Không bật'}</td><td>{item.created_at ? new Date(item.created_at).toLocaleString('vi-VN') : '—'}</td></tr>) : <tr><td colSpan={5}><div className="empty-state">Chưa có Quiz Open edX.</div></td></tr>}</tbody></table></div>
    </section>

    <section className="card">
      <div className="section-head"><div><h2>Job generate câu hỏi</h2><p className="helper">GenerationJob từ các lần tạo câu hỏi theo Bài/Chapter.</p></div></div>
      <div className="table-wrap"><table className="table"><thead><tr><th>ID</th><th>Trạng thái</th><th>Số câu</th><th>Ước tính</th><th>Thực tế</th><th>Đối soát</th><th>Lỗi</th></tr></thead><tbody>
        {jobs.length ? jobs.map((job) => <tr key={job.id}>
          <td><code>{job.id.slice(0, 8)}</code><br /><span className="helper">{job.course_id}</span></td>
          <td><StatusBadge status={job.status} /></td>
          <td>{job.completed_question_count ?? 0}/{job.question_count}</td>
          <td>Gốc {money(job.estimated_raw_cost_usd)}<br />An toàn {money(job.estimated_cost_usd)}<br />Input {tokens(job.estimated_input_tokens)} · Output {tokens(job.estimated_output_tokens)}<br /><span className="helper">Output/câu dự kiến: {tokens(job.estimated_output_tokens_per_question || 0)}</span></td>
          <td>{money(job.actual_cost_usd)}<br />{tokens(job.actual_cost_vnd)} VND<br />Input {tokens(job.actual_input_tokens)} · Cache {tokens(job.actual_cached_input_tokens)} · Output {tokens(job.actual_output_tokens)}</td>
          <td>Chi phí {job.estimate_accuracy_percent || 0}%<br />Output {job.output_accuracy_percent || 0}%<br />Lệch {tokens(job.output_delta_tokens || 0)} tokens</td>
          <td>{job.model_parse_error || job.error_message || '-'}</td>
        </tr>) : <tr><td colSpan={7}><div className="empty-state">Chưa có job generate.</div></td></tr>}
      </tbody></table></div>
    </section>

    <section className="card">
      <div className="section-head"><div><h2>Publish / Quiz / Rollback gần đây</h2><p className="helper">Lấy từ audit log để không bỏ sót thao tác không có GenerationJob.</p></div></div>
      <div className="table-wrap"><table className="table"><thead><tr><th>Thời điểm</th><th>Người</th><th>Hành động</th><th>Kết quả</th><th>Nội dung</th></tr></thead><tbody>{auditRows.length ? auditRows.map((r) => <tr key={r.id}><td>{r.created_at ? new Date(r.created_at).toLocaleString('vi-VN') : '—'}</td><td>{r.actor_id}<br /><span className="helper">{r.actor_role || '—'}</span></td><td>{r.action}</td><td><StatusBadge status={r.status} /></td><td>{r.message || '—'}</td></tr>) : <tr><td colSpan={5}><div className="empty-state">Chưa có thao tác vận hành.</div></td></tr>}</tbody></table></div>
    </section>
  </div>
}
