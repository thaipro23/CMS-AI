'use client'

import { useEffect, useMemo, useState } from 'react'
import { getAuditLogs, getBankOperationJobs, getCourseQuizInstances } from '../../lib/api'
import { useAppContext } from '../../context/AppContext'
import { ActionMessage, ActionMessageData, toUserError } from '../../components/ui/ActionMessage'
import { AuditLogRow, BankOperationJob, CourseQuizInstance } from '../../types'
import { StatusBadge } from '../../components/ui/StatusBadge'

function dateText(v?: string | null) { try { return v ? new Date(v).toLocaleString('vi-VN') : '—' } catch { return v || '—' } }
function jobLabel(v: string) { return ({ material_extract: 'Tách tài liệu', bank_generate: 'Tạo câu hỏi', release_publish: 'Publish release', quiz_create: 'Tạo Quiz' } as Record<string,string>)[v] || v }
function statusText(v: string) { return ({ queued: 'Đang chờ', running: 'Đang chạy', completed: 'Hoàn tất', failed: 'Thất bại', canceled: 'Đã hủy' } as Record<string,string>)[v] || v }
function isOpsAudit(row: AuditLogRow) { const a = String(row.action || ''); return a.startsWith('question_bank.') || a.includes('publish') || a.includes('quiz') || a.includes('generation') }
function shortId(v?: string | null) { return v ? v.slice(0, 8) : '—' }

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

export default function JobsPage() {
  const { authHeaders, can } = useAppContext()
  const [operationJobs, setOperationJobs] = useState<BankOperationJob[]>([])
  const [quizInstances, setQuizInstances] = useState<CourseQuizInstance[]>([])
  const [auditRows, setAuditRows] = useState<AuditLogRow[]>([])
  const [status, setStatus] = useState('all')
  const [operationType, setOperationType] = useState('all')
  const [q, setQ] = useState('')
  const [loading, setLoading] = useState(false)
  const [message, setMessage] = useState<ActionMessageData | null>(null)
  const [quizOpen, setQuizOpen] = useState(false)
  const [activityOpen, setActivityOpen] = useState(false)

  async function load() {
    setLoading(true)
    try {
      setMessage(null)
      const headers = authHeaders()
      const [opJobs, nextQuizInstances, nextAudit] = await Promise.all([
        getBankOperationJobs(headers, { status, operationType, page: 1, pageSize: 80 }),
        getCourseQuizInstances(headers, { limit: 100 }),
        getAuditLogs('', { page: 1, pageSize: 80 }, headers),
      ])
      setOperationJobs(opJobs.items || [])
      setQuizInstances(nextQuizInstances)
      setAuditRows((nextAudit.items || []).filter(isOpsAudit).slice(0, 30))
    } catch (error) { setMessage(toUserError(error)) } finally { setLoading(false) }
  }
  useEffect(() => { load() }, [status, operationType]) // eslint-disable-line react-hooks/exhaustive-deps

  const filteredOps = useMemo(() => {
    const needle = q.trim().toLowerCase()
    if (!needle) return operationJobs
    return operationJobs.filter((job) => [job.id, job.operation_type, job.status, job.progress_label, job.error_message, job.target_type, job.target_id, job.requested_by].filter(Boolean).some((v) => String(v).toLowerCase().includes(needle)))
  }, [operationJobs, q])
  const failed = operationJobs.filter((j) => j.status === 'failed').length
  const running = operationJobs.filter((j) => ['queued', 'running'].includes(j.status)).length
  const completed = operationJobs.filter((j) => j.status === 'completed').length

  if (!can('view_jobs')) return <div className="card empty-state">Vai trò hiện tại không có quyền xem tiến trình.</div>
  return <div className="page-stack ops-console jobs-console">
    <section className="ops-hero card">
      <div><span className="eyebrow">Operations cockpit</span><h1>Tiến trình xử lý</h1><p>Theo dõi upload tài liệu, OCR, generate, publish release và tạo Quiz. Các job được trình bày dạng bảng để dễ biết đang chạy gì, ở đâu và lỗi gì.</p></div>
      <div className="button-row no-margin"><button className="btn secondary" onClick={() => setQuizOpen(true)}>Quiz gần đây</button><button className="btn secondary" onClick={() => setActivityOpen(true)}>Hoạt động gần đây</button><button className="btn" onClick={load} disabled={loading}>{loading ? 'Đang tải...' : 'Làm mới'}</button></div>
    </section>
    <ActionMessage message={message} onClose={() => setMessage(null)} />
    <section className="ops-kpi-grid"><div><span>Đang chạy</span><b>{running}</b></div><div><span>Hoàn tất</span><b>{completed}</b></div><div><span>Thất bại</span><b>{failed}</b></div><div><span>Quiz đã tạo</span><b>{quizInstances.length}</b></div></section>
    <section className="card ops-filter-card"><div className="grid grid-3"><label>Tìm job<input className="input" value={q} onChange={(e) => setQ(e.target.value)} placeholder="id, lỗi, loại job, người tạo..." /></label><label>Trạng thái<select className="input" value={status} onChange={(e) => setStatus(e.target.value)}><option value="all">Tất cả</option><option value="queued">Đang chờ</option><option value="running">Đang chạy</option><option value="completed">Hoàn tất</option><option value="failed">Thất bại</option><option value="canceled">Đã hủy</option></select></label><label>Loại job<select className="input" value={operationType} onChange={(e) => setOperationType(e.target.value)}><option value="all">Tất cả</option><option value="material_extract">Tách tài liệu</option><option value="bank_generate">Tạo câu hỏi</option><option value="release_publish">Publish release</option><option value="quiz_create">Tạo Quiz</option></select></label></div></section>
    <section className="card"><div className="section-head"><div><h2>Operation jobs</h2><p className="helper">Bảng job async mới của Bank-first. Người không đủ quyền chỉ thấy job trong phạm vi được phép.</p></div></div>
      <div className="responsive-table-wrap"><table className="ops-data-table"><thead><tr><th>Loại việc</th><th>Trạng thái</th><th>Tiến độ</th><th>Đối tượng</th><th>Người tạo</th><th>Thời điểm</th><th>Nội dung / lỗi</th></tr></thead><tbody>{filteredOps.length ? filteredOps.map((job) => <tr key={job.id} className={`row-${job.status}`}><td><b>{jobLabel(job.operation_type)}</b><small>ID {shortId(job.id)}</small></td><td><StatusBadge status={job.status} /><small>{statusText(job.status)}</small></td><td><div className="job-progress table-progress"><i style={{ width: `${Math.max(0, Math.min(100, Number(job.progress_percent || 0)))}%` }} /></div><small>{Math.round(Number(job.progress_percent || 0))}% · {job.progress_current || 0}/{job.progress_total || 0}</small></td><td><span>{job.target_type || '—'}</span><small>{job.target_id || job.bank_version_id || job.release_id || '—'}</small></td><td>{job.requested_by || 'system'}</td><td><small>{dateText(job.created_at)}</small></td><td><span className={job.status === 'failed' ? 'table-error-text' : ''}>{job.error_message || job.progress_label || 'Đang chờ xử lý...'}</span></td></tr>) : <tr><td colSpan={7}><div className="empty-state">Không có job phù hợp.</div></td></tr>}</tbody></table></div>
    </section>

    <Popup open={quizOpen} title="Quiz gần đây" onClose={() => setQuizOpen(false)}>
      <div className="responsive-table-wrap"><table className="ops-data-table"><thead><tr><th>Course</th><th>Quiz</th><th>Trạng thái</th><th>Unit</th><th>Ngày tạo</th></tr></thead><tbody>{quizInstances.slice(0, 50).map((item) => <tr key={item.id}><td><b>{item.openedx_course_id}</b><small>{item.bank_release_id}</small></td><td>{item.metadata_json?.quiz_title || 'Quiz Open edX'}</td><td><StatusBadge status={item.status} /></td><td><code>{item.openedx_unit_node_id || '—'}</code></td><td><small>{dateText(item.created_at)}</small></td></tr>)}{!quizInstances.length ? <tr><td colSpan={5}><div className="empty-state">Chưa có Quiz Open edX.</div></td></tr> : null}</tbody></table></div>
    </Popup>
    <Popup open={activityOpen} title="Hoạt động vận hành gần đây" onClose={() => setActivityOpen(false)}>
      <div className="responsive-table-wrap"><table className="ops-data-table"><thead><tr><th>Thời điểm</th><th>Người</th><th>Hành động</th><th>Kết quả</th><th>Nội dung</th></tr></thead><tbody>{auditRows.map((r) => <tr key={r.id}><td><small>{dateText(r.created_at)}</small></td><td>{r.actor_id || '—'}</td><td><b>{r.action}</b></td><td><StatusBadge status={r.status} /></td><td>{r.message || '—'}</td></tr>)}{!auditRows.length ? <tr><td colSpan={5}><div className="empty-state">Chưa có thao tác vận hành.</div></td></tr> : null}</tbody></table></div>
    </Popup>
  </div>
}
