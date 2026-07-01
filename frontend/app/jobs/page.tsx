'use client'

import { useEffect, useMemo, useState } from 'react'
import {
  getAcademicApSyncJobs,
  getAcademicTrainingTeacherReportJobs,
  getAnalyticsOpsStatus,
  getBankOperationJobs,
  getCourseQuizInstances,
  getRecentAcademicClassSyncJobs,
  retryBankOperationJob,
} from '../../lib/api'
import { useAppContext } from '../../context/AppContext'
import { ActionMessage, ActionMessageData, toUserError } from '../../components/ui/ActionMessage'
import { AcademicClassSyncJob, AcademicSyncRun, AcademicTeacherReportJob, BankOperationJob, CourseQuizInstance } from '../../types'
import { StatusBadge } from '../../components/ui/StatusBadge'
import { formatVNDateTime } from '../../lib/time'

function dateText(v?: string | null) { return formatVNDateTime(v) }
function shortId(v?: string | null) { return v ? v.slice(0, 8) : '—' }
function statusText(v: string) { return ({ queued: 'Đang chờ', running: 'Đang chạy', completed: 'Hoàn tất', failed: 'Thất bại', canceled: 'Đã hủy' } as Record<string,string>)[v] || v }
function jobLabel(v: string) { return ({ material_extract: 'Tách tài liệu', bank_generate: 'Tạo câu hỏi', release_publish: 'Đưa bộ đề lên CMS', quiz_create: 'Tạo Quiz' } as Record<string,string>)[v] || v }
function academicJobLabel(v: string) { return ({ cms_sync_check: 'Kiểm tra CMS', cms_enrollment_sync: 'Enroll CMS', learning_sync: 'Cập nhật điểm', full_cms_sync: 'Đồng bộ full CMS', learning_analytics_recalculate: 'Tính lại học online' } as Record<string,string>)[v] || v }
function reportJobLabel(v: string) { return ({ rebuild_cache: 'Tính lại báo cáo GV', export_excel: 'Xuất Excel GV' } as Record<string,string>)[v] || v }
function safeNumber(v: unknown) { const n = Number(v); return Number.isFinite(n) ? n : 0 }
function progressPercent(current?: number, total?: number, explicit?: number) {
  if (typeof explicit === 'number' && Number.isFinite(explicit)) return Math.max(0, Math.min(100, explicit))
  const c = safeNumber(current); const t = safeNumber(total)
  return t > 0 ? Math.max(0, Math.min(100, Math.round((c / t) * 100))) : 0
}
function includesNeedle(values: Array<unknown>, needle: string) {
  if (!needle) return true
  return values.filter(Boolean).some((value) => String(value).toLowerCase().includes(needle))
}

function Popup({ open, title, children, onClose }: { open: boolean; title: string; children: React.ReactNode; onClose: () => void }) {
  useEffect(() => {
    if (!open) return undefined
    const onKey = (event: KeyboardEvent) => { if (event.key === 'Escape') onClose() }
    document.addEventListener('keydown', onKey)
    return () => { document.removeEventListener('keydown', onKey) }
  }, [open, onClose])
  if (!open) return null
  return <div className="modal-backdrop bank-popup-backdrop" onMouseDown={onClose}>
    <section className="modal-card bank-modal bank-modal-wide" role="dialog" aria-modal="true" onMouseDown={(event) => event.stopPropagation()}>
      <div className="section-head bank-modal-head"><div><h2>{title}</h2></div><button className="btn small secondary" onClick={onClose}>Đóng</button></div>
      <div className="bank-modal-body">{children}</div>
    </section>
  </div>
}

type OperationRow = {
  id: string
  group: 'bank' | 'class_sync' | 'ap_sync' | 'teacher_report' | 'analytics'
  label: string
  status: string
  progressCurrent: number
  progressTotal: number
  progressPercent: number
  scope: string
  scopeDetail?: string | null
  requestedBy?: string | null
  createdAt?: string | null
  message?: string | null
  error?: string | null
  rawType?: string | null
  canRetry?: boolean
}

export default function JobsPage() {
  const { authHeaders, can } = useAppContext()
  const [operationJobs, setOperationJobs] = useState<BankOperationJob[]>([])
  const [classSyncJobs, setClassSyncJobs] = useState<AcademicClassSyncJob[]>([])
  const [teacherReportJobs, setTeacherReportJobs] = useState<AcademicTeacherReportJob[]>([])
  const [quizInstances, setQuizInstances] = useState<CourseQuizInstance[]>([])
  const [academicRuns, setAcademicRuns] = useState<AcademicSyncRun[]>([])
  const [analyticsOps, setAnalyticsOps] = useState<Record<string, any> | null>(null)
  const [status, setStatus] = useState('active')
  const [operationGroup, setOperationGroup] = useState('all')
  const [q, setQ] = useState('')
  const [loading, setLoading] = useState(false)
  const [message, setMessage] = useState<ActionMessageData | null>(null)
  const [quizOpen, setQuizOpen] = useState(false)

  async function load() {
    setLoading(true)
    try {
      setMessage(null)
      const headers = authHeaders()
      const statusParam = status === 'all' ? 'all' : status
      const [opJobs, nextQuizInstances, nextAcademicRuns, nextClassSyncJobs, nextTeacherReportJobs, nextAnalyticsOps] = await Promise.all([
        getBankOperationJobs(headers, { status: statusParam, page: 1, pageSize: 80 }).catch(() => ({ items: [] } as any)),
        getCourseQuizInstances(headers, { limit: 100 }).catch(() => [] as CourseQuizInstance[]),
        getAcademicApSyncJobs(headers, { status: statusParam as any, limit: 50 }).catch(() => [] as AcademicSyncRun[]),
        getRecentAcademicClassSyncJobs(headers, { status: statusParam, limit: 80 }).catch(() => [] as AcademicClassSyncJob[]),
        getAcademicTrainingTeacherReportJobs(headers, { status: statusParam, limit: 50 }).catch(() => [] as AcademicTeacherReportJob[]),
        getAnalyticsOpsStatus(headers).catch(() => null),
      ])
      setOperationJobs(opJobs.items || [])
      setQuizInstances(nextQuizInstances)
      setAcademicRuns(nextAcademicRuns || [])
      setClassSyncJobs(nextClassSyncJobs || [])
      setTeacherReportJobs(nextTeacherReportJobs || [])
      setAnalyticsOps(nextAnalyticsOps)
    } catch (error) {
      setMessage(toUserError(error))
    } finally {
      setLoading(false)
    }
  }

  async function retryJob(jobId: string) {
    setLoading(true)
    try {
      const nextJob = await retryBankOperationJob(authHeaders(), jobId)
      setOperationJobs((items) => items.map((item) => item.id === nextJob.id ? nextJob : item))
      setMessage({ type: 'success', title: 'Đã chạy lại', body: `Việc ${shortId(jobId)} đã được đưa vào hàng đợi.` })
      await load()
    } catch (error) {
      setMessage(toUserError(error))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [status]) // eslint-disable-line react-hooks/exhaustive-deps

  const rows = useMemo<OperationRow[]>(() => {
    const bankRows = operationJobs.map((job): OperationRow => ({
      id: job.id,
      group: 'bank',
      label: jobLabel(job.operation_type),
      status: job.status,
      progressCurrent: safeNumber(job.progress_current),
      progressTotal: safeNumber(job.progress_total),
      progressPercent: progressPercent(job.progress_current, job.progress_total, job.progress_percent),
      scope: job.target_type || 'Bank',
      scopeDetail: job.target_id || job.bank_version_id || job.release_id || null,
      requestedBy: job.requested_by || 'Hệ thống',
      createdAt: job.created_at,
      message: job.progress_label,
      error: job.error_message,
      rawType: job.operation_type,
      canRetry: ['queued', 'failed', 'canceled'].includes(job.status),
    }))
    const classRows = classSyncJobs.map((job): OperationRow => ({
      id: job.id,
      group: job.job_type === 'learning_analytics_recalculate' ? 'analytics' : 'class_sync',
      label: academicJobLabel(job.job_type),
      status: job.status,
      progressCurrent: safeNumber(job.progress_current),
      progressTotal: safeNumber(job.progress_total),
      progressPercent: progressPercent(job.progress_current, job.progress_total),
      scope: 'Lớp',
      scopeDetail: job.class_id,
      requestedBy: job.requested_by || 'Hệ thống',
      createdAt: job.created_at,
      message: job.progress_label,
      error: job.error_message,
      rawType: job.job_type,
      canRetry: false,
    }))
    const apRows = academicRuns.map((run): OperationRow => {
      const counters = (run.counters_json || {}) as Record<string, any>
      const progress = (counters.progress || {}) as Record<string, any>
      return {
        id: run.id,
        group: 'ap_sync',
        label: 'Đồng bộ AP',
        status: run.status,
        progressCurrent: safeNumber(progress.current),
        progressTotal: safeNumber(progress.total),
        progressPercent: progressPercent(safeNumber(progress.current), safeNumber(progress.total)),
        scope: run.term_name || 'AP',
        scopeDetail: [run.branch || null, run.campus || null].filter(Boolean).join(' · ') || null,
        requestedBy: run.requested_by || 'Hệ thống',
        createdAt: run.created_at || run.started_at,
        message: String(progress.label || ''),
        error: run.error_message,
        rawType: run.mode,
        canRetry: false,
      }
    })
    const reportRows = teacherReportJobs.map((job): OperationRow => ({
      id: job.id,
      group: 'teacher_report',
      label: reportJobLabel(job.job_type),
      status: job.status,
      progressCurrent: safeNumber(job.progress_current),
      progressTotal: safeNumber(job.progress_total),
      progressPercent: progressPercent(job.progress_current, job.progress_total),
      scope: job.term_id || 'Báo cáo giáo viên',
      scopeDetail: [job.branch || null, job.campus || null].filter(Boolean).join(' · ') || null,
      requestedBy: job.requested_by || 'Hệ thống',
      createdAt: job.created_at,
      message: job.progress_label || job.file_name || null,
      error: job.error_message,
      rawType: job.job_type,
      canRetry: false,
    }))
    const analyticsRows: OperationRow[] = []
    if (analyticsOps) {
      const ingest = (analyticsOps.ingest || {}) as Record<string, any>
      analyticsRows.push({
        id: 'analytics-ingest',
        group: 'analytics',
        label: 'Ingest học online',
        status: ingest.last_status === 'running' ? 'running' : (ingest.last_status === 'failed' ? 'failed' : 'completed'),
        progressCurrent: safeNumber(ingest.total_events_inserted),
        progressTotal: Math.max(1, safeNumber(ingest.total_lines_read) || 1),
        progressPercent: ingest.last_status === 'running' ? 50 : 100,
        scope: 'Tracking log',
        scopeDetail: ingest.file_exists ? 'Đã mount log' : 'Chưa thấy file log',
        requestedBy: 'Hệ thống',
        createdAt: ingest.last_run_at,
        message: `Events ${safeNumber(ingest.total_events_inserted)} · lỗi parse ${safeNumber(ingest.total_parse_errors)}`,
        error: ingest.last_error || null,
        rawType: 'analytics_ingest',
        canRetry: false,
      })
    }
    return [...analyticsRows, ...classRows, ...apRows, ...reportRows, ...bankRows]
      .sort((a, b) => String(b.createdAt || '').localeCompare(String(a.createdAt || '')))
  }, [operationJobs, classSyncJobs, academicRuns, teacherReportJobs, analyticsOps])

  const filteredRows = useMemo(() => {
    const needle = q.trim().toLowerCase()
    return rows.filter((row) => {
      if (operationGroup !== 'all' && row.group !== operationGroup) return false
      return includesNeedle([row.id, row.label, row.status, row.scope, row.scopeDetail, row.requestedBy, row.message, row.error, row.rawType], needle)
    })
  }, [rows, q, operationGroup])

  const failed = rows.filter((j) => j.status === 'failed').length
  const running = rows.filter((j) => ['queued', 'running'].includes(j.status)).length
  const completed = rows.filter((j) => j.status === 'completed').length

  if (!can('view_jobs')) return <div className="card empty-state">Vai trò hiện tại không có quyền xem tiến trình xử lý.</div>
  return <div className="page-stack ops-console jobs-console">
    <section className="ops-hero card">
      <div><span className="eyebrow">Tiến trình</span><h1>Việc đang xử lý</h1><p>Theo dõi đồng bộ lớp, đồng bộ AP, báo cáo giáo viên, tạo câu hỏi và publish Quiz.</p></div>
      <div className="button-row no-margin"><button className="btn secondary" onClick={() => setQuizOpen(true)}>Quiz gần đây</button><button className="btn" onClick={load} disabled={loading}>{loading ? 'Đang tải...' : 'Làm mới'}</button></div>
    </section>
    <ActionMessage message={message} onClose={() => setMessage(null)} />
    <section className="ops-kpi-grid"><div><span>Đang chạy</span><b>{running}</b></div><div><span>Hoàn tất</span><b>{completed}</b></div><div><span>Thất bại</span><b>{failed}</b></div><div><span>Quiz đã tạo</span><b>{quizInstances.length}</b></div></section>
    <section className="card ops-filter-card"><div className="grid grid-3"><label>Tìm việc<input className="input" value={q} onChange={(e) => setQ(e.target.value)} placeholder="mã việc, loại việc, lớp, người tạo..." /></label><label>Trạng thái<select className="input" value={status} onChange={(e) => setStatus(e.target.value)}><option value="active">Đang chạy</option><option value="all">Tất cả</option><option value="queued">Đang chờ</option><option value="running">Đang chạy</option><option value="completed">Hoàn tất</option><option value="failed">Thất bại</option></select></label><label>Nhóm việc<select className="input" value={operationGroup} onChange={(e) => setOperationGroup(e.target.value)}><option value="all">Tất cả</option><option value="class_sync">Đồng bộ lớp/CMS</option><option value="ap_sync">Đồng bộ AP</option><option value="teacher_report">Báo cáo giáo viên</option><option value="analytics">Học online</option><option value="bank">Bank / Quiz</option></select></label></div></section>
    <section className="card"><div className="section-head"><div><h2>Danh sách việc</h2></div></div>
      <div className="responsive-table-wrap"><table className="ops-data-table"><thead><tr><th>STT</th><th>Việc</th><th>Trạng thái</th><th>Tiến độ</th><th>Phạm vi</th><th>Người tạo</th><th>Thời điểm</th><th>Nội dung</th><th>Thao tác</th></tr></thead><tbody>{filteredRows.length ? filteredRows.map((job, index) => <tr key={`${job.group}-${job.id}`} className={`row-${job.status}`}><td className="stt-cell">{index + 1}</td><td><b>{job.label}</b><small>ID {shortId(job.id)}</small></td><td><StatusBadge status={job.status} /><small>{statusText(job.status)}</small></td><td><div className="job-progress table-progress"><i style={{ width: `${job.progressPercent}%` }} /></div><small>{Math.round(job.progressPercent)}% · {job.progressCurrent}/{job.progressTotal || 100}</small></td><td><span>{job.scope}</span><small>{job.scopeDetail || '—'}</small></td><td>{job.requestedBy || 'Hệ thống'}</td><td><small>{dateText(job.createdAt)}</small></td><td><span className={job.status === 'failed' ? 'table-error-text' : ''}>{job.error || job.message || 'Đang chờ xử lý'}</span></td><td>{job.canRetry ? <button className="btn small secondary" type="button" onClick={() => retryJob(job.id)} disabled={loading}>Chạy lại</button> : <span className="muted">—</span>}</td></tr>) : <tr><td colSpan={9}><div className="empty-state">Không có việc phù hợp.</div></td></tr>}</tbody></table></div>
    </section>

    <Popup open={quizOpen} title="Quiz gần đây" onClose={() => setQuizOpen(false)}>
      <div className="responsive-table-wrap"><table className="ops-data-table"><thead><tr><th>STT</th><th>Khóa học</th><th>Quiz</th><th>Trạng thái</th><th>Bài kiểm tra</th><th>Ngày tạo</th></tr></thead><tbody>{quizInstances.slice(0, 50).map((item, index) => <tr key={item.id}><td className="stt-cell">{index + 1}</td><td><b>{item.openedx_course_id}</b><small>{item.bank_release_id}</small></td><td>{item.metadata_json?.quiz_title || 'Quiz trên CMS'}</td><td><StatusBadge status={item.status} /></td><td><code>{item.openedx_unit_node_id || '—'}</code></td><td><small>{dateText(item.created_at)}</small></td></tr>)}{!quizInstances.length ? <tr><td colSpan={6}><div className="empty-state">Chưa có Quiz trên CMS.</div></td></tr> : null}</tbody></table></div>
    </Popup>
  </div>
}
