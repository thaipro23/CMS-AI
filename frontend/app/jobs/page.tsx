'use client'

import { Suspense, useCallback, useEffect, useMemo, useState } from 'react'
import {
  getAcademicApSyncJobs,
  getAcademicBulkOperationJobs,
  getAcademicTrainingTeacherReportJobs,
  getAnalyticsOpsStatus,
  getBankOperationJobs,
  getCourseQuizInstances,
  getRecentAcademicClassSyncJobs,
  retryBankOperationJob,
} from '../../lib/api'
import { useAppContext } from '../../context/AppContext'
import { ActionMessage, ActionMessageData, toUserError } from '../../components/ui/ActionMessage'
import { AcademicBulkOperationJob, AcademicClassSyncJob, AcademicSyncRun, AcademicTeacherReportJob, AnalyticsOpsStatus, BankOperationJob, CourseQuizInstance, JsonObject } from '../../types'
import { StatusBadge } from '../../components/ui/StatusBadge'
import { PageHeader } from '../../components/layout/PageHeader'
import { EnterpriseDataTable, EnterpriseTableColumn } from '../../components/table/EnterpriseDataTable'
import { useOpsTableState } from '../../hooks/useOpsTableState'
import { formatVNDateTime } from '../../lib/time'

function dateText(v?: string | null) { return formatVNDateTime(v) }
function shortId(v?: string | null) { return v ? v.slice(0, 8) : '—' }
function statusText(v: string) { return ({ queued: 'Đang chờ', running: 'Đang chạy', completed: 'Hoàn tất', failed: 'Thất bại', canceled: 'Đã hủy' } as Record<string,string>)[v] || v }
function jobLabel(v: string) { return ({ material_extract: 'Tách tài liệu', bank_generate: 'Tạo câu hỏi', release_publish: 'Đưa bộ đề lên CMS', quiz_create: 'Tạo Quiz' } as Record<string,string>)[v] || v }
function academicJobLabel(v: string) { return ({ cms_sync_check: 'Kiểm tra CMS', cms_enrollment_sync: 'Ghi danh CMS', learning_sync: 'Cập nhật điểm', full_cms_sync: 'Đồng bộ full CMS', learning_analytics_recalculate: 'Tính lại học online' } as Record<string,string>)[v] || v }
function reportJobLabel(v: string) { return ({ rebuild_cache: 'Tính lại báo cáo GV', export_excel: 'Xuất Excel GV' } as Record<string,string>)[v] || v }
function bulkJobLabel(v: string) { return ({ subject_auto_map_all_sync: 'Tự động ghép Course CMS + đồng bộ CMS' } as Record<string,string>)[v] || v }
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
  group: 'bank' | 'class_sync' | 'ap_sync' | 'teacher_report' | 'analytics' | 'bulk_sync'
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

type JobsStatusFilter = 'active' | 'queued' | 'running' | 'completed' | 'failed' | 'all'

function jsonObject(value: unknown): JsonObject {
  return typeof value === 'object' && value !== null && !Array.isArray(value) ? value as JsonObject : {}
}

function jsonText(value: unknown): string {
  return typeof value === 'string' ? value : ''
}

function JobsContent() {
  const { authHeaders, can } = useAppContext()
  const [operationJobs, setOperationJobs] = useState<BankOperationJob[]>([])
  const [classSyncJobs, setClassSyncJobs] = useState<AcademicClassSyncJob[]>([])
  const [bulkOperationJobs, setBulkOperationJobs] = useState<AcademicBulkOperationJob[]>([])
  const [teacherReportJobs, setTeacherReportJobs] = useState<AcademicTeacherReportJob[]>([])
  const [quizInstances, setQuizInstances] = useState<CourseQuizInstance[]>([])
  const [academicRuns, setAcademicRuns] = useState<AcademicSyncRun[]>([])
  const [analyticsOps, setAnalyticsOps] = useState<AnalyticsOpsStatus | null>(null)
  const { state, update } = useOpsTableState({ pageSize: 20 })
  const { status, group: operationGroup, q, page, pageSize, density } = state
  const [loading, setLoading] = useState(false)
  const [message, setMessage] = useState<ActionMessageData | null>(null)
  const [quizOpen, setQuizOpen] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      setMessage(null)
      const headers = authHeaders()
      const statusParam = (status === 'all' ? 'all' : status) as JobsStatusFilter
      const [opJobs, nextQuizInstances, nextAcademicRuns, nextClassSyncJobs, nextTeacherReportJobs, nextBulkOperationJobs, nextAnalyticsOps] = await Promise.all([
        getBankOperationJobs(headers, { status: statusParam, page: 1, pageSize: 80 }).catch(() => ({ items: [] as BankOperationJob[] })),
        getCourseQuizInstances(headers, { limit: 100 }).catch(() => [] as CourseQuizInstance[]),
        getAcademicApSyncJobs(headers, { status: statusParam, limit: 50 }).catch(() => [] as AcademicSyncRun[]),
        getRecentAcademicClassSyncJobs(headers, { status: statusParam, limit: 80 }).catch(() => [] as AcademicClassSyncJob[]),
        getAcademicTrainingTeacherReportJobs(headers, { status: statusParam, limit: 50 }).catch(() => [] as AcademicTeacherReportJob[]),
        getAcademicBulkOperationJobs(headers, { status: statusParam, limit: 50 }).catch(() => [] as AcademicBulkOperationJob[]),
        getAnalyticsOpsStatus(headers).catch(() => null),
      ])
      setOperationJobs(opJobs.items || [])
      setQuizInstances(nextQuizInstances)
      setAcademicRuns(nextAcademicRuns || [])
      setClassSyncJobs(nextClassSyncJobs || [])
      setTeacherReportJobs(nextTeacherReportJobs || [])
      setBulkOperationJobs(nextBulkOperationJobs || [])
      setAnalyticsOps(nextAnalyticsOps)
    } catch (error) {
      setMessage(toUserError(error))
    } finally {
      setLoading(false)
    }
  }, [authHeaders, status])

  const retryJob = useCallback(async (jobId: string) => {
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
  }, [authHeaders, load])

  useEffect(() => { load() }, [load])

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
    const bulkRows = bulkOperationJobs.map((job): OperationRow => {
      const request = jsonObject(job.request_json)
      const result = jsonObject(job.result_json)
      const scopeText = [job.branch || request.branch || null, job.campus || request.campus || null].filter(Boolean).join(' · ') || 'Theo bộ lọc'
      const mapped = safeNumber(result.subject_mapped)
      const already = safeNumber(result.subject_already_mapped)
      const queued = safeNumber(result.jobs_queued)
      const reused = safeNumber(result.jobs_reused)
      const skipped = safeNumber(result.jobs_skipped)
      return {
        id: job.id,
        group: 'bulk_sync',
        label: bulkJobLabel(job.job_type),
        status: job.status,
        progressCurrent: safeNumber(job.progress_current),
        progressTotal: safeNumber(job.progress_total),
        progressPercent: progressPercent(job.progress_current, job.progress_total),
        scope: job.term_id || 'Tự động ghép Course CMS',
        scopeDetail: scopeText,
        requestedBy: job.requested_by || 'Hệ thống',
        createdAt: job.created_at,
        message: job.progress_label || `Map ${mapped}+${already} môn · queue ${queued} lớp · reuse ${reused} · bỏ qua ${skipped}`,
        error: job.error_message,
        rawType: job.job_type,
        canRetry: false,
      }
    })
    const apRows = academicRuns.map((run): OperationRow => {
      const counters = run.counters_json || {}
      const progress = jsonObject(counters.progress)
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
        message: jsonText(progress.label),
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
      const ingest = jsonObject(analyticsOps.ingest)
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
        createdAt: jsonText(ingest.last_run_at) || null,
        message: `Events ${safeNumber(ingest.total_events_inserted)} · lỗi parse ${safeNumber(ingest.total_parse_errors)}`,
        error: jsonText(ingest.last_error) || null,
        rawType: 'analytics_ingest',
        canRetry: false,
      })
    }
    return [...analyticsRows, ...bulkRows, ...classRows, ...apRows, ...reportRows, ...bankRows]
      .sort((a, b) => String(b.createdAt || '').localeCompare(String(a.createdAt || '')))
  }, [operationJobs, classSyncJobs, academicRuns, teacherReportJobs, bulkOperationJobs, analyticsOps])

  const filteredRows = useMemo(() => {
    const needle = q.trim().toLowerCase()
    return rows.filter((row) => {
      if (operationGroup !== 'all' && row.group !== operationGroup) return false
      if (status === 'active' && !['queued', 'running'].includes(row.status)) return false
      if (!['all', 'active'].includes(status) && row.status !== status) return false
      return includesNeedle([row.id, row.label, row.status, row.scope, row.scopeDetail, row.requestedBy, row.message, row.error, row.rawType], needle)
    })
  }, [rows, q, operationGroup, status])

  const totalPages = Math.max(1, Math.ceil(filteredRows.length / pageSize))
  const safePage = Math.min(page, totalPages)
  const pageRows = filteredRows.slice((safePage - 1) * pageSize, safePage * pageSize)

  useEffect(() => {
    if (page !== safePage) update({ page: safePage }, { resetPage: false })
  }, [page, safePage, update])

  const columns = useMemo<EnterpriseTableColumn<OperationRow>[]>(() => [
    { key: 'stt', header: 'STT', width: 72, sticky: 'left', stickyOffset: 0, hideable: false, render: (_row, index) => (safePage - 1) * pageSize + index + 1 },
    { key: 'job', header: 'Việc', minWidth: 210, sticky: 'left', stickyOffset: 72, render: (job) => <><b>{job.label}</b><small>ID {shortId(job.id)}</small></> },
    { key: 'status', header: 'Trạng thái', minWidth: 125, render: (job) => <StatusBadge status={job.status} /> },
    { key: 'progress', header: 'Tiến độ', minWidth: 180, render: (job) => <><div className="job-progress table-progress" role="progressbar" aria-label={`Tiến độ ${job.label}`} aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(job.progressPercent)}><i style={{ width: `${job.progressPercent}%` }} /></div><small>{Math.round(job.progressPercent)}% · {job.progressCurrent}/{job.progressTotal || 100}</small></> },
    { key: 'scope', header: 'Phạm vi', minWidth: 190, render: (job) => <><span>{job.scope}</span><small>{job.scopeDetail || '—'}</small></> },
    { key: 'requested_by', header: 'Người tạo', minWidth: 140, hideable: true, render: (job) => job.requestedBy || 'Hệ thống' },
    { key: 'created_at', header: 'Thời điểm', minWidth: 150, hideable: true, render: (job) => <small>{dateText(job.createdAt)}</small> },
    { key: 'message', header: 'Nội dung', minWidth: 280, render: (job) => <span className={job.status === 'failed' ? 'table-error-text' : ''}>{job.error || job.message || 'Đang chờ xử lý'}</span> },
    { key: 'actions', header: 'Thao tác', minWidth: 110, sticky: 'right', hideable: false, render: (job) => job.canRetry ? <button className="btn small secondary" type="button" onClick={() => retryJob(job.id)} disabled={loading}>Chạy lại</button> : <span className="muted">—</span> },
  ], [loading, pageSize, retryJob, safePage])

  const failed = rows.filter((j) => j.status === 'failed').length
  const running = rows.filter((j) => ['queued', 'running'].includes(j.status)).length
  const completed = rows.filter((j) => j.status === 'completed').length

  if (!can('view_jobs')) return <div className="card empty-state">Vai trò hiện tại không có quyền xem tiến trình xử lý.</div>
  return <div className="page-stack ops-console jobs-console ux-enterprise-page">
    <PageHeader
      eyebrow="Vận hành hệ thống"
      title="Tác vụ nền"
      description="Theo dõi tiến trình đồng bộ, báo cáo, analytics, tạo câu hỏi và Quiz. Nhật ký thao tác được quản lý riêng tại Nhật ký hoạt động."
      secondaryActions={<button className="btn secondary" type="button" onClick={() => setQuizOpen(true)}>Quiz gần đây</button>}
      primaryAction={<button className="btn" type="button" onClick={load} disabled={loading}>{loading ? 'Đang tải...' : 'Tải lại'}</button>}
    />
    <ActionMessage message={message} onClose={() => setMessage(null)} />
    <section className="ops-kpi-grid"><div><span>Đang chạy</span><b>{running}</b></div><div><span>Hoàn tất</span><b>{completed}</b></div><div><span>Thất bại</span><b>{failed}</b></div><div><span>AP sync gần đây</span><b>{academicRuns.length}</b></div></section>
    <section className="card ops-filter-card"><div className="grid grid-3"><label>Tìm việc<input className="input" value={q} onChange={(e) => update({ q: e.target.value })} placeholder="mã việc, loại việc, lớp, người tạo..." /></label><label>Trạng thái<select className="input" value={status} onChange={(e) => update({ status: e.target.value })}><option value="all">Tất cả</option><option value="active">Đang chạy</option><option value="queued">Đang chờ</option><option value="running">Đang chạy</option><option value="completed">Hoàn tất</option><option value="failed">Thất bại</option></select></label><label>Nhóm việc<select className="input" value={operationGroup} onChange={(e) => update({ group: e.target.value })}><option value="all">Tất cả</option><option value="class_sync">Đồng bộ lớp/CMS</option><option value="ap_sync">Đồng bộ AP</option><option value="teacher_report">Báo cáo giáo viên</option><option value="analytics">Học online</option><option value="bulk_sync">Ghép Course CMS / đồng bộ hàng loạt</option><option value="bank">Bank / Quiz</option></select></label></div></section>
    <EnterpriseDataTable tableId="ops-jobs" caption="Danh sách việc" rows={pageRows} columns={columns} rowKey={(job) => `${job.group}-${job.id}`} density={density} onDensityChange={(value) => update({ density: value }, { resetPage: false })} loading={loading} emptyTitle="Không có việc phù hợp" emptyDescription="Thử thay đổi từ khóa, trạng thái hoặc nhóm việc." page={safePage} pageSize={pageSize} total={filteredRows.length} totalPages={totalPages} onPageChange={(value) => update({ page: value }, { resetPage: false })} onPageSizeChange={(value) => update({ pageSize: value, page: 1 }, { resetPage: false })} label="việc" getRowClassName={(job) => `row-${job.status}`} />

    <Popup open={quizOpen} title="Quiz gần đây" onClose={() => setQuizOpen(false)}>
      <div className="responsive-table-wrap"><table className="ops-data-table"><thead><tr><th>STT</th><th>Khóa học</th><th>Quiz</th><th>Trạng thái</th><th>Bài kiểm tra</th><th>Ngày tạo</th></tr></thead><tbody>{quizInstances.slice(0, 50).map((item, index) => <tr key={item.id}><td className="stt-cell">{index + 1}</td><td><b>{item.openedx_course_id}</b><small>{item.bank_release_id}</small></td><td>{item.metadata_json?.quiz_title || 'Quiz trên CMS'}</td><td><StatusBadge status={item.status} /></td><td><code>{item.openedx_unit_node_id || '—'}</code></td><td><small>{dateText(item.created_at)}</small></td></tr>)}{!quizInstances.length ? <tr><td colSpan={6}><div className="empty-state">Chưa có Quiz trên CMS.</div></td></tr> : null}</tbody></table></div>
    </Popup>
  </div>
}

export default function JobsPage() {
  return <Suspense fallback={<div className="card">Đang tải danh sách việc...</div>}><JobsContent /></Suspense>
}
