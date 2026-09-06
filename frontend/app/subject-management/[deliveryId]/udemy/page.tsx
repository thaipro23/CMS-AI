'use client'

import Link from 'next/link'
import { useParams } from 'next/navigation'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { PageRoot } from '../../../../components/layout/PageHeader'
import { EnterpriseScreenHeader } from '../../../../components/layout/EnterpriseDesignContract'
import { CompactFilterBar, OperationsKpiStrip, WorkspaceSection, WorkspaceTabs } from '../../../../components/operations/OperationsWorkspace'
import { EnterpriseDataTable, type EnterpriseTableColumn } from '../../../../components/table/EnterpriseDataTable'
import { InlineNotice, noticeError, noticeInfo, noticeSuccess, noticeWarning } from '../../../../components/ui/InlineNotice'
import { PersistentJobNotice } from '../../../../components/ui/PersistentJobNotice'
import { StatusBadge } from '../../../../components/ui/StatusBadge'
import { UdemyProgressImportDialog } from '../../../../components/subject-management/UdemyProgressImportDialog'
import { useAppContext } from '../../../../context/AppContext'
import {
  createUdemyProgressExportJob,
  downloadUdemyProgressExportJob,
  getAcademicBulkOperationJob,
  getUdemyProgressDashboard,
  getUdemyProgressStudents,
} from '../../../../lib/api'
import type {
  AcademicBulkOperationJob,
  AcademicSubjectDelivery,
  UdemyProgressDashboard,
  UdemyProgressImportBatch,
  UdemyProgressStudent,
  UdemyProgressStudentList,
} from '../../../../types'

type TabKey = 'overview' | 'students' | 'alerts' | 'history' | 'plan'
type StatusFilter = 'all' | 'on_track' | 'late' | 'no_plan' | 'unmatched' | 'ambiguous' | 'outside_roster'

const EMPTY_LIST: UdemyProgressStudentList = { items: [], total: 0, page: 1, page_size: 50, total_pages: 0, has_next: false }
const ACTIVE_JOB_STATUSES = ['queued', 'running']

function formatDate(value?: string | null) {
  if (!value) return 'Chưa có'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : new Intl.DateTimeFormat('vi-VN', { dateStyle: 'short' }).format(date)
}
function formatDateTime(value?: string | null) {
  if (!value) return 'Chưa có'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : new Intl.DateTimeFormat('vi-VN', { dateStyle: 'short', timeStyle: 'short' }).format(date)
}
function percent(value?: number | null) { return value == null ? '—' : `${Number(value).toLocaleString('vi-VN', { maximumFractionDigits: 2 })}%` }
function statusBadge(row: UdemyProgressStudent) {
  if (row.status === 'on_track') return <StatusBadge status="success" label="Đạt tiến độ" />
  if (row.status === 'late') return <StatusBadge status="failed" label="Chậm tiến độ" />
  if (row.status === 'no_plan') return <StatusBadge status="warning" label="Chưa có mốc đến hạn" />
  if (row.status === 'outside_roster') return <StatusBadge status="warning" label="Ngoài danh sách lớp AP" />
  if (row.status === 'ambiguous') return <StatusBadge status="warning" label="Cần đối chiếu" />
  return <StatusBadge status="failed" label="Chưa khớp AP" />
}
function saveBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  URL.revokeObjectURL(url)
}
function readStoredJobId(key: string) {
  try { return window.localStorage.getItem(key) || '' } catch { return '' }
}
function storeJobId(key: string, jobId: string) {
  try { window.localStorage.setItem(key, jobId) } catch { /* Browser storage can be disabled. */ }
}
function clearStoredJobId(key: string) {
  try { window.localStorage.removeItem(key) } catch { /* Browser storage can be disabled. */ }
}
function jobMatchesDelivery(job: AcademicBulkOperationJob, jobType: string, deliveryId: string) {
  return job.job_type === jobType && String(job.request_json?.delivery_id || '') === deliveryId
}

export default function UdemyProgressPage() {
  const params = useParams<{ deliveryId: string }>()
  const deliveryId = String(params?.deliveryId || '')
  const { authHeaders, can } = useAppContext()
  const headers = useMemo(() => authHeaders(), [authHeaders])
  const exportStorageKey = useMemo(() => `ai-server:udemy-export-job:${deliveryId}`, [deliveryId])
  const importStorageKey = useMemo(() => `ai-server:udemy-import-job:${deliveryId}`, [deliveryId])
  const handledImportJobs = useRef(new Set<string>())
  const canManage = can('academic.catalog.manage')

  const [dashboard, setDashboard] = useState<UdemyProgressDashboard | null>(null)
  const [rows, setRows] = useState<UdemyProgressStudentList>(EMPTY_LIST)
  const [tab, setTab] = useState<TabKey>('overview')
  const [q, setQ] = useState('')
  const [appliedQ, setAppliedQ] = useState('')
  const [classId, setClassId] = useState('')
  const [status, setStatus] = useState<StatusFilter>('all')
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(50)
  const [sortBy, setSortBy] = useState('student')
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('asc')
  const [loading, setLoading] = useState(true)
  const [exporting, setExporting] = useState(false)
  const [exportJob, setExportJob] = useState<AcademicBulkOperationJob | null>(null)
  const [importJob, setImportJob] = useState<AcademicBulkOperationJob | null>(null)
  const [downloadedExportJobId, setDownloadedExportJobId] = useState('')
  const [exportDownloadFailed, setExportDownloadFailed] = useState(false)
  const [exportPollWarning, setExportPollWarning] = useState('')
  const [importPollWarning, setImportPollWarning] = useState('')
  const [exportRecoveryJobId, setExportRecoveryJobId] = useState('')
  const [importRecoveryJobId, setImportRecoveryJobId] = useState('')
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [importOpen, setImportOpen] = useState(false)

  const loadDashboard = useCallback(async () => {
    if (!deliveryId) return
    try {
      const data = await getUdemyProgressDashboard(headers, deliveryId)
      setDashboard(data)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Không tải được tổng quan Udemy.')
    }
  }, [deliveryId, headers])

  const effectiveStatus = tab === 'alerts'
    ? (status === 'all' || status === 'on_track' ? 'alerts' : status)
    : status

  const loadRows = useCallback(async () => {
    if (!deliveryId || !['students', 'alerts'].includes(tab)) return
    setLoading(true)
    setError('')
    try {
      setRows(await getUdemyProgressStudents(headers, deliveryId, {
        q: appliedQ,
        classId,
        status: effectiveStatus,
        page,
        pageSize,
        sortBy,
        sortDir,
      }))
    } catch (err) {
      setRows(EMPTY_LIST)
      setError(err instanceof Error ? err.message : 'Không tải được danh sách tiến độ Udemy.')
    } finally { setLoading(false) }
  }, [appliedQ, classId, deliveryId, effectiveStatus, headers, page, pageSize, sortBy, sortDir, tab])

  const reloadAll = useCallback(async () => {
    await loadDashboard()
    if (['students', 'alerts'].includes(tab)) await loadRows()
  }, [loadDashboard, loadRows, tab])

  useEffect(() => { void loadDashboard() }, [loadDashboard])
  useEffect(() => { void loadRows() }, [loadRows])

  const changeTab = (key: string) => {
    const next = key as TabKey
    setTab(next)
    setPage(1)
    if (next === 'alerts' && status === 'on_track') setStatus('all')
  }

  const deliveryForImport = useMemo<AcademicSubjectDelivery | null>(() => dashboard ? {
    id: dashboard.delivery.id,
    subject_id: dashboard.delivery.subject_id,
    subject_code: dashboard.delivery.subject_code,
    subject_name: dashboard.delivery.subject_name,
    term_id: dashboard.delivery.term_id,
    term_name: dashboard.delivery.term_name,
    block_id: dashboard.delivery.block_id,
    block_name: dashboard.delivery.block_name,
    branch: dashboard.delivery.branch,
    learning_platform: 'udemy',
    active: true,
    configuration_source: 'manual',
    class_count: dashboard.summary.class_count,
    campus_count: 0,
    has_udemy_plan: Boolean(dashboard.active_plan),
  } : null, [dashboard])

  useEffect(() => {
    if (!deliveryId || exportJob) return
    const storedJobId = readStoredJobId(exportStorageKey)
    if (!storedJobId) return
    setExportRecoveryJobId(storedJobId)
    getAcademicBulkOperationJob(headers, storedJobId)
      .then((job) => {
        if (!jobMatchesDelivery(job, 'udemy_progress_export', deliveryId) || ![...ACTIVE_JOB_STATUSES, 'completed'].includes(job.status)) {
          clearStoredJobId(exportStorageKey)
          setExportRecoveryJobId('')
          if (job.status === 'failed') setError(job.error_message || 'Job export Udemy trước đó đã thất bại.')
          return
        }
        setExportRecoveryJobId('')
        setExportJob(job)
        setExporting(ACTIVE_JOB_STATUSES.includes(job.status))
        setMessage(job.status === 'completed' ? 'Job export Udemy đã hoàn tất; đang chuẩn bị tải file.' : (job.progress_label || 'Đang tiếp tục job export Udemy sau khi tải lại trang.'))
      })
      .catch(() => setExportPollWarning('Chưa thể khôi phục trạng thái export. Hệ thống sẽ không tạo thêm job cho đến khi bạn thử lại.'))
  }, [deliveryId, exportJob, exportStorageKey, headers])

  useEffect(() => {
    if (!deliveryId || importJob) return
    const storedJobId = readStoredJobId(importStorageKey)
    if (!storedJobId) return
    setImportRecoveryJobId(storedJobId)
    getAcademicBulkOperationJob(headers, storedJobId)
      .then((job) => {
        if (!jobMatchesDelivery(job, 'udemy_progress_import', deliveryId) || ![...ACTIVE_JOB_STATUSES, 'completed'].includes(job.status)) {
          clearStoredJobId(importStorageKey)
          setImportRecoveryJobId('')
          if (job.status === 'failed') setError(job.error_message || 'Job import Udemy trước đó đã thất bại.')
          return
        }
        setImportRecoveryJobId('')
        setImportJob(job)
        setMessage(job.status === 'completed' ? 'Import Udemy đã hoàn tất; đang cập nhật dashboard.' : (job.progress_label || 'Đang tiếp tục theo dõi import Udemy sau khi tải lại trang.'))
      })
      .catch(() => setImportPollWarning('Chưa thể khôi phục trạng thái import. Job vẫn chạy nền; hãy dùng nút “Thử đọc lại trạng thái”.'))
  }, [deliveryId, headers, importJob, importStorageKey])

  useEffect(() => {
    if (!exportJob?.id || !ACTIVE_JOB_STATUSES.includes(exportJob.status)) return
    const timer = window.setInterval(async () => {
      try {
        const next = await getAcademicBulkOperationJob(headers, exportJob.id)
        setExportJob(next)
        setExportPollWarning('')
        setExporting(ACTIVE_JOB_STATUSES.includes(next.status))
        if (next.status === 'failed') {
          clearStoredJobId(exportStorageKey)
          setError(next.error_message || 'Job export Udemy thất bại.')
        }
      } catch (err) {
        setExportPollWarning(err instanceof Error ? err.message : 'Tạm thời chưa đọc được trạng thái export. Job vẫn tiếp tục chạy nền.')
      }
    }, 1800)
    return () => window.clearInterval(timer)
  }, [exportJob?.id, exportJob?.status, exportStorageKey, headers])

  useEffect(() => {
    if (!importJob?.id || !ACTIVE_JOB_STATUSES.includes(importJob.status)) return
    const timer = window.setInterval(async () => {
      try {
        const next = await getAcademicBulkOperationJob(headers, importJob.id)
        setImportJob(next)
        setImportPollWarning('')
      } catch (err) {
        setImportPollWarning(err instanceof Error ? err.message : 'Tạm thời chưa đọc được trạng thái import. Job vẫn tiếp tục chạy nền.')
      }
    }, 1800)
    return () => window.clearInterval(timer)
  }, [headers, importJob?.id, importJob?.status])

  useEffect(() => {
    if (!importJob?.id || !['completed', 'failed'].includes(importJob.status) || handledImportJobs.current.has(importJob.id)) return
    handledImportJobs.current.add(importJob.id)
    clearStoredJobId(importStorageKey)
    if (importJob.status === 'failed') {
      setError(importJob.error_message || 'Import tiến độ Udemy thất bại.')
      setImportJob(null)
      return
    }
    setMessage(importJob.progress_label || 'Import tiến độ Udemy đã hoàn tất.')
    void Promise.all([loadDashboard(), ['students', 'alerts'].includes(tab) ? loadRows() : Promise.resolve()])
      .finally(() => setImportJob(null))
  }, [importJob, importStorageKey, loadDashboard, loadRows, tab])

  const downloadExportFile = useCallback(async (job: AcademicBulkOperationJob) => {
    try {
      const blob = await downloadUdemyProgressExportJob(headers, job.id)
      saveBlob(blob, String(job.result_json?.file_name || `udemy-progress-${dashboard?.delivery.subject_code || 'report'}.xlsx`))
      clearStoredJobId(exportStorageKey)
      setMessage('Đã tải báo cáo theo đúng bộ lọc và phạm vi quyền hiện tại.')
      setExportDownloadFailed(false)
      setExporting(false)
      setExportJob(null)
    } catch (err) {
      setExportDownloadFailed(true)
      setExporting(false)
      setError(err instanceof Error ? err.message : 'Không tải được file export Udemy đã hoàn tất.')
    }
  }, [dashboard?.delivery.subject_code, exportStorageKey, headers])

  useEffect(() => {
    if (!exportJob?.id || exportJob.status !== 'completed' || downloadedExportJobId === exportJob.id || exportDownloadFailed) return
    setDownloadedExportJobId(exportJob.id)
    void downloadExportFile(exportJob)
  }, [downloadExportFile, downloadedExportJobId, exportDownloadFailed, exportJob])

  const columns: EnterpriseTableColumn<UdemyProgressStudent>[] = [
    { key: 'stt', header: 'STT', kind: 'index', width: 54, render: (_row, index) => (page - 1) * pageSize + index + 1 },
    { key: 'student', header: 'Sinh viên', kind: 'identity', minWidth: 260, sticky: 'left', render: (row) => <div className="udemy-student-identity"><b>{row.student_code || row.student_username || 'Chưa khớp AP'}</b><span>{row.display_name}</span><small>{row.email}</small></div> },
    { key: 'class', header: 'Lớp', kind: 'identity', minWidth: 150, sortable: true, render: (row) => <div><b>{row.class_code || '—'}</b>{row.campus ? <small>{String(row.campus).toUpperCase()}</small> : null}</div> },
    { key: 'teacher', header: 'Giảng viên', kind: 'text', minWidth: 190, render: (row) => row.teacher_names.length ? row.teacher_names.join(', ') : '—' },
    { key: 'progress', header: 'Tiến độ', kind: 'progress', minWidth: 180, sortable: true, render: (row) => <div className="udemy-progress-meter" role="progressbar" aria-label={`Tiến độ của ${row.display_name}`} aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(Math.max(0, Math.min(100, row.progress_percent)))}><div aria-hidden="true"><span style={{ width: `${Math.max(0, Math.min(100, row.progress_percent))}%` }} /></div><b>{percent(row.progress_percent)}</b></div> },
    { key: 'required', header: 'Mốc yêu cầu', kind: 'number', minWidth: 135, sortable: true, render: (row) => <div><b>{percent(row.required_progress_percent)}</b>{row.current_plan_week ? <small>Tuần {row.current_plan_week}</small> : null}</div> },
    { key: 'variance', header: 'Chênh lệch', kind: 'number', width: 112, render: (row) => row.variance_percent == null ? '—' : <span className={row.variance_percent < 0 ? 'udemy-negative' : 'udemy-positive'}>{row.variance_percent > 0 ? '+' : ''}{percent(row.variance_percent)}</span> },
    { key: 'deadline', header: 'Deadline', kind: 'date', minWidth: 130, render: (row) => formatDate(row.current_deadline_date) },
    { key: 'status', header: 'Trạng thái', kind: 'status', minWidth: 150, sortable: true, render: statusBadge },
    { key: 'match', header: 'Đối chiếu AP', kind: 'status', minWidth: 160, render: (row) => row.match_status === 'matched_roster' ? <StatusBadge status="success" label="Khớp danh sách AP" /> : <StatusBadge status="warning" label={row.status_label} /> },
    { key: 'updated', header: 'Cập nhật', kind: 'date', minWidth: 145, sortable: true, render: (row) => <div>{formatDateTime(row.last_imported_at)}<small>{row.source_format}</small></div> },
    { key: 'note', header: 'Ghi chú', kind: 'text', minWidth: 260, render: (row) => row.diagnostic || '—' },
  ]

  const historyColumns: EnterpriseTableColumn<UdemyProgressImportBatch>[] = [
    { key: 'stt', header: 'STT', kind: 'index', width: 54, render: (_row, index) => index + 1 },
    { key: 'created', header: 'Thời điểm', kind: 'date', minWidth: 145, render: (row) => formatDateTime(row.created_at) },
    { key: 'file', header: 'File', kind: 'identity', minWidth: 260, render: (row) => <div><b>{row.file_name}</b><small>{row.subject_code || dashboard?.delivery.subject_code}</small></div> },
    { key: 'status', header: 'Trạng thái', kind: 'status', minWidth: 130, render: (row) => <StatusBadge status={row.status} /> },
    { key: 'format', header: 'Định dạng', kind: 'text', minWidth: 145, render: (row) => row.parser_format || '—' },
    { key: 'processed', header: 'Bản ghi SV', kind: 'number', width: 105, render: (row) => row.processed_rows },
    { key: 'matched', header: 'Khớp roster', kind: 'number', width: 110, render: (row) => row.matched_rows },
    { key: 'issues', header: 'Cần đối chiếu', kind: 'number', width: 120, render: (row) => row.outside_roster_rows + row.unmatched_rows + row.ambiguous_rows + row.failed_rows },
    { key: 'actor', header: 'Người thực hiện', kind: 'identity', minWidth: 170, render: (row) => row.requested_by || 'Hệ thống' },
  ]

  const exportData = async () => {
    if (exportJob?.status === 'completed' && exportDownloadFailed) {
      setDownloadedExportJobId(exportJob.id)
      setExportDownloadFailed(false)
      await downloadExportFile(exportJob)
      return
    }
    setExporting(true)
    setError('')
    setMessage('')
    setDownloadedExportJobId('')
    setExportDownloadFailed(false)
    try {
      const job = await createUdemyProgressExportJob(headers, deliveryId, { q: appliedQ, classId, status: effectiveStatus })
      storeJobId(exportStorageKey, job.id)
      setExportJob(job)
      setMessage(job.progress_label || 'Đã xếp hàng export Udemy. Bạn có thể F5, job vẫn tiếp tục chạy.')
    } catch (err) {
      setExporting(false)
      setError(err instanceof Error ? err.message : 'Không tạo được job export Udemy.')
    }
  }

  const resumeJob = async (jobId: string, kind: 'import' | 'export') => {
    try {
      const job = await getAcademicBulkOperationJob(headers, jobId)
      const expectedType = kind === 'import' ? 'udemy_progress_import' : 'udemy_progress_export'
      if (!jobMatchesDelivery(job, expectedType, deliveryId)) throw new Error('Job không thuộc môn Udemy đang mở hoặc không còn trong phạm vi quyền hiện tại.')
      if (kind === 'import') {
        setImportRecoveryJobId('')
        setImportJob(job)
        setImportPollWarning('')
      } else {
        setExportRecoveryJobId('')
        setExportJob(job)
        setExportPollWarning('')
        setExporting(ACTIVE_JOB_STATUSES.includes(job.status))
        if (job.status === 'failed') setError(job.error_message || 'Job export Udemy thất bại.')
      }
    } catch (err) {
      const text = err instanceof Error ? err.message : `Không đọc được trạng thái ${kind}.`
      if (kind === 'import') setImportPollWarning(text)
      else setExportPollWarning(text)
    }
  }

  const summary = dashboard?.summary
  const alertCount = summary ? summary.late_students + summary.unmatched_students + summary.ambiguous_students + summary.outside_roster_students + summary.no_plan_students : 0
  const matchedRate = summary?.total_students ? Math.round((summary.matched_students / summary.total_students) * 100) : 0
  const exportButtonLabel = exportJob?.status === 'completed' && exportDownloadFailed
    ? 'Tải lại file'
    : exporting
      ? `Đang xuất ${Math.round(((exportJob?.progress_current || 0) / Math.max(1, exportJob?.progress_total || 100)) * 100)}%`
      : 'Xuất Excel'

  return <PageRoot className="page-stack enterprise-standard-page training-operations-page udemy-progress-page">
    <EnterpriseScreenHeader
      eyebrow="Quản lý môn học · Udemy"
      title={dashboard ? `${dashboard.delivery.subject_code} · Tiến độ Udemy` : 'Tiến độ Udemy'}
      description={dashboard ? `${dashboard.delivery.subject_name} · ${dashboard.delivery.term_name} · ${dashboard.delivery.block_name} · phạm vi: ${summary?.scope_label}` : 'Theo dõi tiến độ, cảnh báo và lịch sử import Udemy.'}
      icon="analytics"
      tone="green"
      breadcrumbs={[{ label: 'Quản lý môn học', href: '/subject-management' }, { label: dashboard?.delivery.subject_code || 'Udemy' }]}
      secondaryActions={<div className="subject-header-actions"><Link className="btn secondary" href="/subject-management">Quay lại</Link>{dashboard && canManage ? <Link className="btn secondary" href={`/subject-management/${encodeURIComponent(deliveryId)}/udemy-plan`}>Kế hoạch Udemy</Link> : null}<button className="btn secondary" type="button" disabled={exporting || Boolean(exportRecoveryJobId) || !dashboard} onClick={exportData}>{exportRecoveryJobId ? 'Đang khôi phục export…' : exportButtonLabel}</button></div>}
      primaryAction={canManage ? <button className="btn" type="button" disabled={!dashboard || Boolean(importRecoveryJobId) || Boolean(importJob && ACTIVE_JOB_STATUSES.includes(importJob.status))} onClick={() => setImportOpen(true)}>{importRecoveryJobId ? 'Đang khôi phục import…' : 'Import điểm Udemy'}</button> : undefined}
    />

    <InlineNotice notice={message ? noticeSuccess(message) : null} />
    <InlineNotice notice={error ? { ...noticeError(error), onRetry: exportJob?.status === 'completed' && exportDownloadFailed ? () => void exportData() : undefined, retryLabel: 'Tải lại file' } : null} />
    <InlineNotice notice={exportPollWarning ? { ...noticeWarning(exportPollWarning, 'Chưa đọc được trạng thái export'), onRetry: (exportJob?.id || exportRecoveryJobId) ? () => void resumeJob(exportJob?.id || exportRecoveryJobId, 'export') : undefined, retryLabel: 'Thử đọc lại trạng thái' } : null} />
    <InlineNotice notice={importPollWarning ? { ...noticeWarning(importPollWarning, 'Chưa đọc được trạng thái import'), onRetry: (importJob?.id || importRecoveryJobId) ? () => void resumeJob(importJob?.id || importRecoveryJobId, 'import') : undefined, retryLabel: 'Thử đọc lại trạng thái' } : null} />
    {exportJob && [...ACTIVE_JOB_STATUSES, 'completed'].includes(exportJob.status) ? <PersistentJobNotice job={exportJob} title="Xuất báo cáo Udemy" description={exportJob.status === 'completed' ? (exportDownloadFailed ? 'Báo cáo đã sẵn sàng nhưng lần tải gần nhất thất bại.' : 'Báo cáo đã hoàn tất; hệ thống đang tải file.') : undefined} action={exportJob.status === 'completed' && exportDownloadFailed ? <button className="btn secondary small" type="button" onClick={() => void exportData()}>Tải lại file</button> : undefined} /> : null}
    {importJob && ACTIVE_JOB_STATUSES.includes(importJob.status) ? <PersistentJobNotice job={importJob} title="Import tiến độ Udemy" description="Job tiếp tục chạy kể cả khi F5 hoặc chuyển trang. Dashboard sẽ tự cập nhật khi hoàn tất." /> : null}

    <OperationsKpiStrip items={[
      { label: 'Tổng sinh viên', value: summary?.total_students ?? '—', hint: `${summary?.class_count || 0} lớp trong phạm vi`, icon: 'users' },
      { label: 'Đạt tiến độ', value: summary?.on_track_students ?? '—', hint: `Mốc hiện tại ${percent(summary?.required_progress_percent)}`, tone: 'success', icon: 'check' },
      { label: 'Chậm tiến độ', value: summary?.late_students ?? '—', hint: summary?.current_deadline_date ? `Deadline ${formatDate(summary.current_deadline_date)}` : 'Chưa có deadline', tone: 'danger', icon: 'alert' },
      { label: 'Cần đối chiếu', value: summary ? summary.unmatched_students + summary.ambiguous_students + summary.outside_roster_students : '—', hint: 'Email hoặc roster AP chưa rõ', tone: 'warning', icon: 'alert' },
      { label: 'Tiến độ trung bình', value: percent(summary?.average_progress_percent), hint: `Cập nhật ${formatDateTime(summary?.last_imported_at)}`, tone: 'info', icon: 'analytics' },
    ]} />

    <WorkspaceTabs idPrefix="udemy-progress" active={tab} onChange={changeTab} tabs={[
      { key: 'overview', label: 'Tổng quan', icon: 'dashboard' },
      { key: 'students', label: 'Tiến độ sinh viên', count: summary?.total_students, icon: 'users' },
      { key: 'alerts', label: 'Cảnh báo', count: alertCount, icon: 'alert' },
      { key: 'history', label: 'Lịch sử import', count: dashboard?.recent_imports.length, icon: 'clock' },
      { key: 'plan', label: 'Kế hoạch', icon: 'calendar' },
    ]} />

    {tab === 'overview' ? <div id="udemy-progress-panel-overview" role="tabpanel" aria-labelledby="udemy-progress-tab-overview" tabIndex={0}>
      <WorkspaceSection title="Tổng quan vận hành Udemy" description="Tóm tắt phạm vi, chất lượng đối chiếu và mốc kế hoạch hiện tại." icon="dashboard" tone="green" actions={<button className="btn small secondary" type="button" onClick={() => void loadDashboard()}>Làm mới</button>}>
        <div className="udemy-overview-grid">
          <article className="udemy-overview-card"><span>Độ phủ roster AP</span><b>{matchedRate}%</b><small>{summary?.matched_students || 0}/{summary?.total_students || 0} sinh viên khớp roster</small></article>
          <article className="udemy-overview-card"><span>Cần ưu tiên xử lý</span><b>{alertCount}</b><small>{summary?.late_students || 0} chậm · {summary?.no_plan_students || 0} chưa có mốc</small></article>
          <article className="udemy-overview-card"><span>Kế hoạch đang dùng</span><b>{dashboard?.active_plan ? `v${dashboard.active_plan.version}` : 'Chưa có'}</b><small>{summary?.current_plan_week ? `Tuần ${summary.current_plan_week} · yêu cầu ${percent(summary.required_progress_percent)}` : 'Chưa đến mốc đánh giá'}</small></article>
          <article className="udemy-overview-card"><span>Dữ liệu gần nhất</span><b>{formatDate(summary?.last_imported_at)}</b><small>{dashboard?.recent_imports[0]?.file_name || 'Chưa có file import'}</small></article>
        </div>
        <div className="udemy-overview-actions"><button className="btn secondary" type="button" onClick={() => changeTab('students')}>Xem tiến độ sinh viên</button><button className="btn secondary" type="button" onClick={() => changeTab('alerts')}>Xử lý cảnh báo</button>{canManage ? <Link className="btn secondary" href={`/subject-management/${encodeURIComponent(deliveryId)}/udemy-plan`}>Quản lý kế hoạch</Link> : null}</div>
      </WorkspaceSection>
      {!dashboard?.active_plan ? <InlineNotice notice={noticeWarning('Chưa có kế hoạch active nên hệ thống chưa thể xác định chính xác đạt hoặc chậm tiến độ.', 'Chưa có kế hoạch Udemy')} /> : null}
      {!summary?.last_imported_at ? <InlineNotice notice={noticeInfo('Hãy import file tiến độ đầu tiên để dashboard bắt đầu hiển thị số liệu.', 'Chưa có dữ liệu tiến độ')} /> : null}
    </div> : null}

    {(tab === 'students' || tab === 'alerts') ? <div id={`udemy-progress-panel-${tab}`} role="tabpanel" aria-labelledby={`udemy-progress-tab-${tab}`} tabIndex={0}>
      <CompactFilterBar actions={<div className="subject-filter-actions"><button className="btn secondary" type="button" onClick={() => { setAppliedQ(q.trim()); setPage(1) }}>Áp dụng</button><button className="btn secondary" type="button" onClick={() => { setQ(''); setAppliedQ(''); setClassId(''); setStatus('all'); setPage(1) }}>Xóa lọc</button></div>}>
        <label>Tìm kiếm<input className="input" value={q} onChange={(event) => setQ(event.target.value)} onKeyDown={(event) => { if (event.key === 'Enter') { setAppliedQ(q.trim()); setPage(1) } }} placeholder="Mã SV, họ tên, email, lớp..." /></label>
        <label>Lớp<select className="input" value={classId} onChange={(event) => { setClassId(event.target.value); setPage(1) }}><option value="">Tất cả lớp</option>{dashboard?.classes.map((item) => <option key={item.id} value={item.id}>{item.class_code}{item.campus ? ` · ${String(item.campus).toUpperCase()}` : ''}</option>)}</select></label>
        <label>Trạng thái<select className="input" value={status} onChange={(event) => { setStatus(event.target.value as StatusFilter); setPage(1) }}><option value="all">{tab === 'alerts' ? 'Tất cả cảnh báo' : 'Tất cả'}</option>{tab !== 'alerts' ? <option value="on_track">Đạt tiến độ</option> : null}<option value="late">Chậm tiến độ</option><option value="no_plan">Chưa có mốc đến hạn</option><option value="outside_roster">Ngoài danh sách lớp AP</option><option value="ambiguous">Cần đối chiếu</option><option value="unmatched">Chưa khớp AP</option></select></label>
      </CompactFilterBar>
      <WorkspaceSection title={tab === 'alerts' ? 'Sinh viên cần xử lý' : 'Tiến độ sinh viên Udemy'} description={tab === 'alerts' ? 'Chỉ hiển thị trường hợp chậm tiến độ, chưa có mốc hoặc chưa khớp AP.' : 'Dữ liệu hiện tại lấy từ lần import mới nhất; lịch sử file vẫn được giữ.'} actions={<button className="btn small secondary" type="button" onClick={() => void reloadAll()} disabled={loading}>Làm mới</button>}>
        <EnterpriseDataTable
          tableId={`udemy-progress-${tab}-batch35-1`}
          caption={tab === 'alerts' ? 'Danh sách cảnh báo tiến độ Udemy' : 'Danh sách tiến độ sinh viên Udemy'}
          rows={rows.items}
          columns={columns}
          rowKey={(row) => row.id}
          loading={loading}
          error={error || undefined}
          onRetry={loadRows}
          emptyTitle={tab === 'alerts' ? 'Không có cảnh báo theo bộ lọc' : 'Chưa có dữ liệu tiến độ'}
          emptyDescription="Import file Udemy hoặc thay đổi bộ lọc để xem dữ liệu."
          page={rows.page}
          pageSize={rows.page_size}
          total={rows.total}
          totalPages={rows.total_pages}
          onPageChange={setPage}
          onPageSizeChange={(value) => { setPageSize(value); setPage(1) }}
          sortKey={sortBy}
          sortDirection={sortDir}
          onSortChange={(key, direction) => { setSortBy(key); setSortDir(direction); setPage(1) }}
          label="sinh viên"
          stickyHorizontalScroll
        />
      </WorkspaceSection>
    </div> : null}

    {tab === 'history' ? <div id="udemy-progress-panel-history" role="tabpanel" aria-labelledby="udemy-progress-tab-history" tabIndex={0}>
      <WorkspaceSection title="Lịch sử import gần nhất" description={dashboard?.recent_imports.length ? 'Hiển thị 10 file gần nhất trong phạm vi quyền hiện tại.' : 'Chưa có lịch sử import trong phạm vi được phép xem.'} icon="clock" tone="slate">
        <EnterpriseDataTable
          tableId="udemy-import-history-batch35-1"
          caption="Lịch sử import tiến độ Udemy"
          rows={dashboard?.recent_imports || []}
          columns={historyColumns}
          rowKey={(row) => row.id}
          emptyTitle="Chưa có lịch sử import"
          emptyDescription="Lịch sử sẽ xuất hiện sau khi có file tiến độ được xử lý."
          label="lần import"
          stickyHorizontalScroll
        />
      </WorkspaceSection>
    </div> : null}

    {tab === 'plan' ? <div id="udemy-progress-panel-plan" role="tabpanel" aria-labelledby="udemy-progress-tab-plan" tabIndex={0}>
      <WorkspaceSection title="Kế hoạch Udemy đang áp dụng" description="Mốc kế hoạch được dùng để xác định đạt hoặc chậm tiến độ." icon="calendar" tone="green">
        <div className="udemy-plan-summary-card"><div><span>Phiên bản</span><b>{dashboard?.active_plan ? `v${dashboard.active_plan.version}` : 'Chưa có'}</b></div><div><span>Số item</span><b>{dashboard?.active_plan?.item_count ?? '—'}</b></div><div><span>Mốc hiện tại</span><b>{summary?.current_plan_week ? `Tuần ${summary.current_plan_week} · ${percent(summary.required_progress_percent)}` : 'Chưa đến mốc'}</b></div><div><span>Deadline</span><b>{formatDate(summary?.current_deadline_date)}</b></div></div>
        <div className="workspace-section-actions udemy-plan-actions">{canManage ? <Link className="btn" href={`/subject-management/${encodeURIComponent(deliveryId)}/udemy-plan`}>{dashboard?.active_plan ? 'Xem và tạo phiên bản mới' : 'Tạo kế hoạch Udemy'}</Link> : <span className="muted">Bạn đang xem kế hoạch ở chế độ chỉ đọc.</span>}</div>
      </WorkspaceSection>
    </div> : null}

    <UdemyProgressImportDialog
      open={importOpen}
      branch={(dashboard?.delivery.branch || 'poly') as 'poly' | 'ptcd'}
      termId={dashboard?.delivery.term_id || ''}
      blockId={dashboard?.delivery.block_id || ''}
      delivery={deliveryForImport}
      headers={headers}
      onClose={() => setImportOpen(false)}
      onQueued={async (response) => {
        setMessage(response.message)
        setError('')
        storeJobId(importStorageKey, response.job_id)
        setImportRecoveryJobId(response.job_id)
        try {
          setImportJob(await getAcademicBulkOperationJob(headers, response.job_id))
          setImportRecoveryJobId('')
        } catch {
          setImportPollWarning('Job đã được xếp hàng nhưng chưa đọc được trạng thái ban đầu. Hãy thử đọc lại trạng thái.')
        }
      }}
    />
  </PageRoot>
}
