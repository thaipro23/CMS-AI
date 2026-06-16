'use client'

import { useEffect, useMemo, useState } from 'react'
import { getAuditLogs, getBankOperationJobs, getCourseQuizInstances, getJobs } from '../../lib/api'
import { useAppContext } from '../../context/AppContext'
import { ActionMessage, ActionMessageData, toUserError } from '../../components/ui/ActionMessage'
import { AuditLogRow, BankOperationJob, CourseQuizInstance, Job } from '../../types'
import { StatusBadge } from '../../components/ui/StatusBadge'

function money(v?: number | null) { return `$${Number(v || 0).toFixed(6)}` }
function tokens(v?: number | null) { return Number(v || 0).toLocaleString('vi-VN') }
function dateText(v?: string | null) { try { return v ? new Date(v).toLocaleString('vi-VN') : '—' } catch { return v || '—' } }
function jobLabel(v: string) { return ({ material_extract: 'Tách tài liệu', bank_generate: 'Tạo câu hỏi', release_publish: 'Publish release', quiz_create: 'Tạo Quiz' } as Record<string,string>)[v] || v }
function isOpsAudit(row: AuditLogRow) { const a = String(row.action || ''); return a.startsWith('question_bank.') || a.includes('publish') || a.includes('quiz') || a.includes('generation') }

export default function JobsPage() {
  const { authHeaders, can } = useAppContext()
  const [legacyJobs, setLegacyJobs] = useState<Job[]>([])
  const [operationJobs, setOperationJobs] = useState<BankOperationJob[]>([])
  const [quizInstances, setQuizInstances] = useState<CourseQuizInstance[]>([])
  const [auditRows, setAuditRows] = useState<AuditLogRow[]>([])
  const [status, setStatus] = useState('all')
  const [operationType, setOperationType] = useState('all')
  const [q, setQ] = useState('')
  const [loading, setLoading] = useState(false)
  const [message, setMessage] = useState<ActionMessageData | null>(null)

  async function load() {
    setLoading(true)
    try {
      setMessage(null)
      const headers = authHeaders()
      const [nextJobs, opJobs, nextQuizInstances, nextAudit] = await Promise.all([
        getJobs('', headers),
        getBankOperationJobs(headers, { status, operationType, page: 1, pageSize: 50 }),
        getCourseQuizInstances(headers, { limit: 100 }),
        getAuditLogs('', { page: 1, pageSize: 80 }, headers),
      ])
      setLegacyJobs(nextJobs)
      setOperationJobs(opJobs.items || [])
      setQuizInstances(nextQuizInstances)
      setAuditRows((nextAudit.items || []).filter(isOpsAudit).slice(0, 30))
    } catch (error) { setMessage(toUserError(error)) } finally { setLoading(false) }
  }
  useEffect(() => { load() }, [status, operationType]) // eslint-disable-line react-hooks/exhaustive-deps

  const filteredOps = useMemo(() => {
    const needle = q.trim().toLowerCase()
    if (!needle) return operationJobs
    return operationJobs.filter((job) => [job.id, job.operation_type, job.status, job.progress_label, job.error_message, job.target_type, job.target_id].filter(Boolean).some((v) => String(v).toLowerCase().includes(needle)))
  }, [operationJobs, q])
  const failed = operationJobs.filter((j) => j.status === 'failed').length
  const running = operationJobs.filter((j) => ['queued', 'running'].includes(j.status)).length
  const completed = operationJobs.filter((j) => j.status === 'completed').length

  if (!can('view_jobs')) return <div className="card empty-state">Vai trò hiện tại không có quyền xem tiến trình.</div>
  return <div className="page-stack ops-console jobs-console">
    <section className="ops-hero card"><div><span className="eyebrow">Operations cockpit</span><h1>Tiến trình xử lý</h1><p>Giám sát upload tài liệu, OCR, generate, publish release, tạo Quiz và rollback. Lỗi được tách rõ để người vận hành biết cần làm gì tiếp theo.</p></div><button className="btn secondary" onClick={load} disabled={loading}>{loading ? 'Đang tải...' : 'Làm mới'}</button></section>
    <ActionMessage message={message} onClose={() => setMessage(null)} />
    <section className="ops-kpi-grid"><div><span>Đang chạy</span><b>{running}</b></div><div><span>Hoàn tất</span><b>{completed}</b></div><div><span>Thất bại</span><b>{failed}</b></div><div><span>Quiz đã tạo</span><b>{quizInstances.length}</b></div></section>
    <section className="card ops-filter-card"><div className="grid grid-3"><label>Tìm job<input className="input" value={q} onChange={(e) => setQ(e.target.value)} placeholder="id, lỗi, loại job..." /></label><label>Trạng thái<select className="input" value={status} onChange={(e) => setStatus(e.target.value)}><option value="all">Tất cả</option><option value="queued">Đang chờ</option><option value="running">Đang chạy</option><option value="completed">Hoàn tất</option><option value="failed">Thất bại</option><option value="canceled">Đã hủy</option></select></label><label>Loại job<select className="input" value={operationType} onChange={(e) => setOperationType(e.target.value)}><option value="all">Tất cả</option><option value="material_extract">Tách tài liệu</option><option value="bank_generate">Tạo câu hỏi</option><option value="release_publish">Publish release</option><option value="quiz_create">Tạo Quiz</option></select></label></div></section>
    <section className="card"><div className="section-head"><div><h2>Operation jobs</h2><p className="helper">Luồng async mới của Bank-first. Người không đủ quyền chỉ thấy job trong phạm vi được phép.</p></div></div><div className="job-board">{filteredOps.length ? filteredOps.map((job) => <article className={`job-card ${job.status}`} key={job.id}><div className="job-card-head"><b>{jobLabel(job.operation_type)}</b><StatusBadge status={job.status} /></div><p>{job.error_message || job.progress_label || 'Đang chờ xử lý...'}</p><div className="job-progress"><i style={{ width: `${Math.max(0, Math.min(100, Number(job.progress_percent || 0)))}%` }} /></div><div className="job-meta"><span>ID {job.id.slice(0, 8)}</span><span>{job.target_type} {job.target_id || ''}</span><span>{dateText(job.created_at)}</span></div></article>) : <div className="empty-state">Không có job phù hợp.</div>}</div></section>
    <section className="ops-two-col"><section className="card"><div className="section-head"><div><h2>Generation jobs cũ</h2><p className="helper">Chi phí và token từ luồng tạo câu hỏi course-first/legacy.</p></div></div><div className="compact-list">{legacyJobs.slice(0, 10).map((job) => <div className="ops-list-row" key={job.id}><div><b>{job.id.slice(0, 8)}</b><small>{job.course_id}</small></div><StatusBadge status={job.status} /><span>{job.completed_question_count ?? 0}/{job.question_count}</span><span>{money(job.actual_cost_usd || job.estimated_cost_usd)}</span><small>{job.model_parse_error || job.error_message || `${tokens(job.actual_output_tokens)} output tokens`}</small></div>)}{!legacyJobs.length ? <div className="empty-state">Chưa có generation job.</div> : null}</div></section><section className="card"><div className="section-head"><div><h2>Quiz gần đây</h2><p className="helper">CourseQuizInstance được tạo từ Bank Release.</p></div></div><div className="compact-list">{quizInstances.slice(0, 10).map((item) => <div className="ops-list-row" key={item.id}><div><b>{item.openedx_course_id}</b><small>{item.metadata_json?.quiz_title || item.bank_release_id}</small></div><StatusBadge status={item.status} /><code>{item.openedx_unit_node_id || '—'}</code><small>{dateText(item.created_at)}</small></div>)}{!quizInstances.length ? <div className="empty-state">Chưa có Quiz Open edX.</div> : null}</div></section></section>
    <section className="card"><div className="section-head"><div><h2>Hoạt động vận hành gần đây</h2><p className="helper">Audit đã lọc theo quyền backend.</p></div></div><div className="activity-list">{auditRows.map((r) => <div className="activity-item" key={r.id}><div><b>{r.action}</b><p>{r.message || '—'}</p><small>{r.actor_id} · {dateText(r.created_at)}</small></div><StatusBadge status={r.status} /></div>)}{!auditRows.length ? <div className="empty-state">Chưa có thao tác vận hành.</div> : null}</div></section>
  </div>
}
