'use client'

import { useEffect, useState } from 'react'
import { getJobs } from '../../lib/api'
import { useAppContext } from '../../context/AppContext'
import { ActionMessage, ActionMessageData, toUserError } from '../../components/ui/ActionMessage'
import { Job } from '../../types'
import { StatusBadge } from '../../components/ui/StatusBadge'

function money(v: number) {
  return `$${(v || 0).toFixed(6)}`
}

function tokens(v: number) {
  return (v || 0).toLocaleString('vi-VN')
}

export default function JobsPage() {
  const { courseId, authHeaders, can } = useAppContext()
  const [jobs, setJobs] = useState<Job[]>([])
  const [message, setMessage] = useState<ActionMessageData | null>(null)

  async function load() {
    try {
      setMessage(null)
      setJobs(await getJobs(courseId, authHeaders()))
    } catch (error) {
      setMessage(toUserError(error))
    }
  }

  useEffect(() => { load() }, [courseId])

  if (!can('view_jobs')) return <div className="card empty-state">Vai trò hiện tại không có quyền xem job.</div>

  return <div className="page-stack">
    <section className="card page-intro">
      <div>
        <h2>Theo dõi job</h2>
        <p className="helper">Theo dõi ước tính trước khi chạy, usage thật sau khi model trả về và độ lệch giữa ước tính với thực tế.</p>
      </div>
      <button className="btn secondary" onClick={load}>Tải lại job</button>
    </section>
    <ActionMessage message={message} onClose={() => setMessage(null)} />
    <section className="card">
      <div className="table-wrap"><table className="table"><thead><tr><th>ID</th><th>Trạng thái</th><th>Số câu</th><th>Ước tính</th><th>Thực tế</th><th>Đối soát</th><th>Lỗi</th></tr></thead><tbody>
        {jobs.length ? jobs.map((job) => <tr key={job.id}>
          <td><code>{job.id.slice(0, 8)}</code><br /><span className="helper">{job.course_id}</span></td>
          <td><StatusBadge status={job.status} /></td>
          <td>{job.completed_question_count ?? 0}/{job.question_count}</td>
          <td>
            Gốc {money(job.estimated_raw_cost_usd)}<br />
            An toàn {money(job.estimated_cost_usd)}<br />
            Input {tokens(job.estimated_input_tokens)} · Output {tokens(job.estimated_output_tokens)}<br />
            <span className="helper">Output/câu dự kiến: {tokens(job.estimated_output_tokens_per_question || 0)}</span><br />
            <span className="helper">{job.estimate_token_source || '—'}</span>
          </td>
          <td>
            {money(job.actual_cost_usd)}<br />
            {tokens(job.actual_cost_vnd)} VND<br />
            Input {tokens(job.actual_input_tokens)} · Đã cache {tokens(job.actual_cached_input_tokens)} · Output {tokens(job.actual_output_tokens)}<br />
            <span className="helper">Output/câu thật: {tokens(job.actual_output_tokens_per_question || 0)}</span><br />
            <span className="helper">{job.usage_token_source || '—'}</span>
          </td>
          <td>
            Độ chính xác chi phí {job.estimate_accuracy_percent || 0}%<br />
            Độ chính xác output {job.output_accuracy_percent || 0}%<br />
            Chênh lệch output {tokens(job.output_delta_tokens || 0)} tokens<br />
            Chênh lệch {money(job.cost_delta_usd)}<br />
            <span className="helper">Actual không nhân safety factor</span>
          </td>
          <td>{job.model_parse_error || job.error_message || '-'}{job.openai_response_ids ? <><br /><span className="helper">{job.openai_response_ids}</span></> : null}</td>
        </tr>) : <tr><td colSpan={7}><div className="empty-state">Chưa có job generate.</div></td></tr>}
      </tbody></table></div>
    </section>
  </div>
}
