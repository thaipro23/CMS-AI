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
import { CompactFilterBar, InfoPairGrid, OperationsKpiStrip, SideDrawer } from '../../components/operations/OperationsWorkspace'

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
  const [selectedJob, setSelectedJob] = useState<OperationRow | null>(null)

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
    { key: 'stt', header: 'STT', kind: 'index', width: 52, sticky: 'left', hideable: false, render: (_row, index) => (safePage - 1) * pageSize + index + 1 },
    { key: 'job', header: 'Việc', kind: 'identity', minWidth: 250, sticky: 'left', priority: 'required', hideable: false, render: (job) => <><b>{job.label}</b><small>{job.scope}{job.scopeDetail ? ` · ${shortId(job.scopeDetail)}` : ''}</small></> },
    { key: 'status', header: 'Trạng thái', kind: 'status', width: 116, priority: 'required', hideable: false, render: (job) => <StatusBadge status={job.status} /> },
    { key: 'progress', header: 'Tiến độ', kind: 'progress', minWidth: 165, priority: 'important', hideable: true, render: (job) => <><div className="job-progress table-progress" role="progressbar" aria-label={`Tiến độ ${job.label}`} aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(job.progressPercent)}><i style={{ width: `${job.progressPercent}%` }} /></div><small>{Math.round(job.progressPercent)}% · {job.progressCurrent}/{job.progressTotal || 100}</small></> },
    { key: 'created_at', header: 'Thời điểm', kind: 'date', width: 138, priority: 'important', hideable: true, render: (job) => <small>{dateText(job.createdAt)}</small> },
    { key: 'scope', header: 'Phạm vi chi tiết', kind: 'text', minWidth: 175, priority: 'optional', hideable: true, defaultVisible: false, render: (job) => <><span>{job.scope}</span><small>{job.scopeDetail || '—'}</small></> },
    { key: 'requested_by', header: 'Người tạo', kind: 'text', width: 120, priority: 'optional', hideable: true, defaultVisible: false, render: (job) => job.requestedBy || 'Hệ thống' },
    { key: 'message', header: 'Nội dung', kind: 'text', minWidth: 230, priority: 'optional', hideable: true, defaultVisible: false, truncateLines: 2, render: (job) => <span className={job.status === 'failed' ? 'table-error-text' : ''}>{job.error || job.message || 'Đang chờ xử lý'}</span> },
    { key: 'actions', header: 'Thao tác', kind: 'actions', width: 92, sticky: 'right', hideable: false, render: (job) => <button className="btn small secondary" type="button" onClick={() => setSelectedJob(job)}>Chi tiết</button> },
  ], [pageSize, safePage])

  const failed = rows.filter((j) => j.status === 'failed').length
  const running = rows.filter((j) => ['queued', 'running'].includes(j.status)).length
  const completed = rows.filter((j) => j.status === 'completed').length
  const resetFilters = () => update({ q: '', status: 'all', group: 'all', page: 1 }, { resetPage: false })

  const quizColumns = useMemo<EnterpriseTableColumn<CourseQuizInstance>[]>(() => [
    { key: 'stt', header: 'STT', kind: 'index', width: 52, hideable: false, render: (_item, index) => index + 1 },
    { key: 'course', header: 'Khóa học', kind: 'identity', minWidth: 260, hideable: false, render: (item) => <><b>{item.openedx_course_id}</b><small>{item.metadata_json?.quiz_title || 'Quiz trên CMS'}</small></> },
    { key: 'status', header: 'Trạng thái', kind: 'status', width: 116, hideable: false, render: (item) => <StatusBadge status={item.status} /> },
    { key: 'node', header: 'Node CMS', kind: 'text', minWidth: 160, priority: 'optional', hideable: true, render: (item) => <code>{item.openedx_unit_node_id || '—'}</code> },
    { key: 'created', header: 'Ngày tạo', kind: 'date', width: 138, priority: 'important', hideable: true, render: (item) => <small>{dateText(item.created_at)}</small> },
  ], [])

  if (!can('view_jobs')) return <div className="card empty-state">Vai trò hiện tại không có quyền xem tiến trình xử lý.</div>
  return <div className="page-stack ops-console jobs-console ux-enterprise-page">
    <PageHeader
      eyebrow="Vận hành hệ thống"
      title="Tác vụ nền"
      description="Theo dõi tiến trình Celery theo nhóm nghiệp vụ. Nhật ký thao tác được quản lý riêng tại Nhật ký hoạt động."
      secondaryActions={<button className="btn secondary" type="button" onClick={() => setQuizOpen(true)}>Quiz gần đây</button>}
      primaryAction={<button className="btn" type="button" onClick={load} disabled={loading}>{loading ? 'Đang tải...' : 'Tải lại'}</button>}
    />
    <ActionMessage message={message} onClose={() => setMessage(null)} />
    <OperationsKpiStrip items={[
      { label: 'Đang xử lý', value: running, hint: 'Đang chờ hoặc đang chạy', tone: running ? 'info' : 'neutral' },
      { label: 'Hoàn tất', value: completed, hint: 'Trong dữ liệu vừa tải', tone: 'success' },
      { label: 'Thất bại', value: failed, hint: failed ? 'Cần mở chi tiết để xử lý' : 'Không có lỗi gần đây', tone: failed ? 'danger' : 'neutral' },
      { label: 'Đồng bộ AP', value: academicRuns.length, hint: 'Lần chạy gần đây' },
    ]} />
    <CompactFilterBar actions={<button className="btn secondary" type="button" onClick={resetFilters} disabled={!q && status === 'all' && operationGroup === 'all'}>Xóa lọc</button>}>
      <label>Tìm việc<input className="input" value={q} onChange={(event) => update({ q: event.target.value })} placeholder="Mã việc, lớp, phạm vi..." /></label>
      <label>Trạng thái<select className="input" value={status} onChange={(event) => update({ status: event.target.value })}><option value="all">Tất cả</option><option value="active">Đang xử lý</option><option value="queued">Đang chờ</option><option value="running">Đang chạy</option><option value="completed">Hoàn tất</option><option value="failed">Thất bại</option></select></label>
      <label>Nhóm việc<select className="input" value={operationGroup} onChange={(event) => update({ group: event.target.value })}><option value="all">Tất cả</option><option value="class_sync">Đồng bộ lớp/CMS</option><option value="ap_sync">Đồng bộ AP</option><option value="teacher_report">Báo cáo giảng viên</option><option value="analytics">Học online</option><option value="bulk_sync">Ghép Course CMS hàng loạt</option><option value="bank">Bank / Quiz</option></select></label>
    </CompactFilterBar>
    <EnterpriseDataTable tableId="ops-jobs-v2" caption="Danh sách việc" rows={pageRows} columns={columns} rowKey={(job) => `${job.group}-${job.id}`} density={density} onDensityChange={(value) => update({ density: value }, { resetPage: false })} loading={loading} emptyTitle="Không có việc phù hợp" emptyDescription="Thử thay đổi từ khóa, trạng thái hoặc nhóm việc." page={safePage} pageSize={pageSize} total={filteredRows.length} totalPages={totalPages} onPageChange={(value) => update({ page: value }, { resetPage: false })} onPageSizeChange={(value) => update({ pageSize: value, page: 1 }, { resetPage: false })} label="việc" getRowClassName={(job) => `row-${job.status}`} />

    <SideDrawer open={Boolean(selectedJob)} title={selectedJob?.label || 'Chi tiết tác vụ'} description={selectedJob ? `ID ${selectedJob.id}` : undefined} onClose={() => setSelectedJob(null)} footer={selectedJob?.canRetry ? <button className="btn" type="button" onClick={() => { retryJob(selectedJob.id); setSelectedJob(null) }} disabled={loading}>Chạy lại tác vụ</button> : undefined}>
      {selectedJob ? <div className="page-stack compact-stack"><StatusBadge status={selectedJob.status} label={statusText(selectedJob.status)} /><InfoPairGrid items={[
        { label: 'Nhóm việc', value: selectedJob.group },
        { label: 'Loại kỹ thuật', value: selectedJob.rawType || '—' },
        { label: 'Phạm vi', value: selectedJob.scope },
        { label: 'Đối tượng', value: selectedJob.scopeDetail || '—' },
        { label: 'Người tạo', value: selectedJob.requestedBy || 'Hệ thống' },
        { label: 'Thời điểm', value: dateText(selectedJob.createdAt) },
        { label: 'Tiến độ', value: `${Math.round(selectedJob.progressPercent)}% · ${selectedJob.progressCurrent}/${selectedJob.progressTotal || 100}`, wide: true },
        { label: selectedJob.error ? 'Lỗi' : 'Nội dung', value: selectedJob.error || selectedJob.message || 'Không có mô tả.', wide: true },
      ]} /></div> : null}
    </SideDrawer>

    <SideDrawer open={quizOpen} title="Quiz gần đây" description="Các Quiz đã tạo trên Open edX CMS." onClose={() => setQuizOpen(false)}>
      <EnterpriseDataTable tableId="ops-recent-quizzes" caption="Quiz gần đây" rows={quizInstances.slice(0, 50)} columns={quizColumns} rowKey={(item) => item.id} density="compact" label="Quiz" emptyTitle="Chưa có Quiz trên CMS" />
    </SideDrawer>
  </div>
}

export default function JobsPage() {
  return <Suspense fallback={<div className="card">Đang tải danh sách việc...</div>}><JobsContent /></Suspense>
}
