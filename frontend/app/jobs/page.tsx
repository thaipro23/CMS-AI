'use client'

import { userFacingError } from '../../lib/userFacingError'

import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  getAcademicApSyncJobs,
  getAcademicBulkOperationJobs,
  getAcademicTrainingTeacherReportJobs,
  getAnalyticsOpsStatus,
  getBankOperationJobs,
  getCourseQuizInstances,
  getJobs,
  getRecentAcademicClassSyncJobs,
  getUserIdentityLabels,
  retryAcademicBulkOperationJob,
  retryAcademicTrainingTeacherReportJob,
  retryBankOperationJob,
} from '../../lib/api'
import { useAppContext } from '../../context/AppContext'
import { ActionMessage, ActionMessageData, toUserError } from '../../components/ui/ActionMessage'
import { AcademicBulkOperationJob, AcademicClassSyncJob, AcademicSyncRun, AcademicTeacherReportJob, AnalyticsOpsStatus, BankOperationJob, CourseQuizInstance, Job, JsonObject } from '../../types'
import { StatusBadge } from '../../components/ui/StatusBadge'
import { PageRoot } from '../../components/layout/PageHeader'
import { EnterpriseScreenHeader } from '../../components/layout/EnterpriseDesignContract'
import { EnterpriseDataTable, EnterpriseTableColumn } from '../../components/table/EnterpriseDataTable'
import { useOpsTableState } from '../../hooks/useOpsTableState'
import { formatVNDateTime } from '../../lib/time'
import { CompactFilterBar, InfoPairGrid, OperationsKpiStrip, SideDrawer } from '../../components/operations/OperationsWorkspace'

function dateText(v?: string | null) { return formatVNDateTime(v) }
function shortId(v?: string | null) { return v ? v.slice(0, 8) : '—' }
function statusText(v: string) { return ({ queued: 'Đang chờ', running: 'Đang chạy', completed: 'Hoàn tất', failed: 'Thất bại', canceled: 'Đã hủy' } as Record<string,string>)[v] || v }
function jobLabel(v: string) { return ({ material_extract: 'Tách tài liệu', bank_generate: 'Tạo câu hỏi', question_import: 'Import câu hỏi', legacy_quiz_import: 'Import Quiz CMS cũ', release_publish: 'Đưa bộ đề lên CMS', quiz_create: 'Tạo Quiz' } as Record<string,string>)[v] || v }
function academicJobLabel(v: string) { return ({ cms_sync_check: 'Kiểm tra CMS', cms_enrollment_sync: 'Ghi danh CMS', learning_sync: 'Cập nhật điểm', full_cms_sync: 'Đồng bộ full CMS', learning_analytics_recalculate: 'Tính lại học online' } as Record<string,string>)[v] || v }
function reportJobLabel(v: string) { return ({ rebuild_cache: 'Tính lại báo cáo GV', export_excel: 'Xuất Excel GV' } as Record<string,string>)[v] || v }
function bulkJobLabel(v: string) { return ({ subject_auto_map_all_sync: 'Tự động ghép Course CMS + đồng bộ CMS', learning_refresh_filter: 'Cập nhật điểm CMS theo bộ lọc', subject_catalog_refresh: 'Lấy danh sách môn từ AP', progress_reminder_email: 'Gửi mail nhắc chậm tiến độ' } as Record<string,string>)[v] || v }
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
  group: 'bank' | 'generation' | 'class_sync' | 'ap_sync' | 'teacher_report' | 'analytics' | 'bulk_sync'
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
  parentJobId?: string | null
  canRetry?: boolean
}

type JobsStatusFilter = 'active' | 'queued' | 'running' | 'completed' | 'failed' | 'all'

function jsonObject(value: unknown): JsonObject {
  return typeof value === 'object' && value !== null && !Array.isArray(value) ? value as JsonObject : {}
}

function jsonText(value: unknown): string {
  return typeof value === 'string' ? value : ''
}

function academicJobError(error: string | null | undefined, resultValue: unknown): string | null {
  const result = jsonObject(resultValue)
  if (result.code === 'CELERY_JOB_ORPHANED') {
    return 'Worker bị gián đoạn hoặc không nhận job trong thời gian cho phép. Tác vụ đã được dừng an toàn; hãy chạy lại sau khi kiểm tra worker.'
  }
  if (result.code === 'CLASS_SYNC_TRANSIENT_RETRY') return null
  return error || null
}

function requesterContextUsername(value: unknown): string {
  const context = jsonObject(jsonObject(value).requester_context)
  return jsonText(context.username).trim()
}

function isSystemActor(value?: string | null): boolean {
  const actor = String(value || '').trim().toLowerCase()
  if (!actor) return true
  if (['system', 'scheduler', 'worker', 'unknown'].includes(actor)) return true
  return /(^|[-_.])(system|scheduler|worker)([-_.]|$)/.test(actor)
}

function requestedByLabel(
  requestedBy: string | null | undefined,
  requestValue: unknown,
  labels: Record<string, string>,
): string {
  const actor = String(requestedBy || '').trim()
  if (isSystemActor(actor)) return 'Hệ thống'
  if (labels[actor]) return labels[actor]
  const snapshotUsername = requesterContextUsername(requestValue)
  if (snapshotUsername) return snapshotUsername
  return /^\d+$/.test(actor) ? `Người dùng #${actor}` : actor
}

function operationStatusLabel(job: OperationRow) {
  if (job.status === 'queued' && /tự chạy lại/i.test(job.message || '')) return 'Chờ tự chạy lại'
  if (job.status === 'queued') return 'Chờ worker'
  if (job.status === 'running' && (job.group === 'bulk_sync' || job.rawType === 'learning_refresh_filter')) return 'Đang điều phối'
  return statusText(job.status)
}

function jobProgressText(job: OperationRow) {
  if (job.status === 'queued') return job.message || 'Chờ worker nhận tác vụ'
  if (job.group === 'generation') return `${job.progressCurrent}/${job.progressTotal || 0} câu`
  if (job.group === 'class_sync' && job.status === 'running' && job.progressCurrent <= 10) {
    return job.message || 'Worker đã nhận tác vụ'
  }
  return `${Math.round(job.progressPercent)}% · ${job.progressCurrent}/${job.progressTotal || 100}`
}

function JobsContent() {
  const { authHeaders, can } = useAppContext()
  const [operationJobs, setOperationJobs] = useState<BankOperationJob[]>([])
  const [generationJobs, setGenerationJobs] = useState<Job[]>([])
  const [classSyncJobs, setClassSyncJobs] = useState<AcademicClassSyncJob[]>([])
  const [bulkOperationJobs, setBulkOperationJobs] = useState<AcademicBulkOperationJob[]>([])
  const [teacherReportJobs, setTeacherReportJobs] = useState<AcademicTeacherReportJob[]>([])
  const [quizInstances, setQuizInstances] = useState<CourseQuizInstance[]>([])
  const [academicRuns, setAcademicRuns] = useState<AcademicSyncRun[]>([])
  const [analyticsOps, setAnalyticsOps] = useState<AnalyticsOpsStatus | null>(null)
  const [creatorLabels, setCreatorLabels] = useState<Record<string, string>>({})
  const { state, update } = useOpsTableState({ pageSize: 20 })
  const { status, group: operationGroup, q, page, pageSize, density } = state
  const [loading, setLoading] = useState(false)
  const [quizLoading, setQuizLoading] = useState(false)
  const [message, setMessage] = useState<ActionMessageData | null>(null)
  const [quizOpen, setQuizOpen] = useState(false)
  const [selectedJob, setSelectedJob] = useState<OperationRow | null>(null)
  const loadGeneration = useRef(0)

  const load = useCallback(async () => {
    const generation = ++loadGeneration.current
    setLoading(true)
    try {
      setMessage(null)
      const headers = authHeaders()
      const statusParam = (status === 'all' ? 'all' : status) as JobsStatusFilter
      const canViewGenerationJobs = can('view_questions')
      // The operational tables are the first paint. Keep every source independent:
      // one failed endpoint must not hide successful jobs from the other sources.
      const [opJobsResult, generationJobsResult, academicRunsResult, classSyncJobsResult, teacherReportJobsResult, bulkOperationJobsResult] = await Promise.allSettled([
        getBankOperationJobs(headers, { status: statusParam, page: 1, pageSize: 80 }),
        canViewGenerationJobs ? getJobs(null, headers) : Promise.resolve([] as Job[]),
        getAcademicApSyncJobs(headers, { status: statusParam, limit: 50 }),
        getRecentAcademicClassSyncJobs(headers, { status: statusParam, limit: 100 }),
        getAcademicTrainingTeacherReportJobs(headers, { status: statusParam, limit: 50 }),
        getAcademicBulkOperationJobs(headers, { status: statusParam, limit: 50 }),
      ])
      if (generation !== loadGeneration.current) return

      const opJobs = opJobsResult.status === 'fulfilled' ? opJobsResult.value : { items: [] as BankOperationJob[] }
      const nextGenerationJobs = generationJobsResult.status === 'fulfilled' ? generationJobsResult.value : [] as Job[]
      const nextAcademicRuns = academicRunsResult.status === 'fulfilled' ? academicRunsResult.value : [] as AcademicSyncRun[]
      const nextClassSyncJobs = classSyncJobsResult.status === 'fulfilled' ? classSyncJobsResult.value : [] as AcademicClassSyncJob[]
      const nextTeacherReportJobs = teacherReportJobsResult.status === 'fulfilled' ? teacherReportJobsResult.value : [] as AcademicTeacherReportJob[]
      const nextBulkOperationJobs = bulkOperationJobsResult.status === 'fulfilled' ? bulkOperationJobsResult.value : [] as AcademicBulkOperationJob[]
      const primaryFailure = [opJobsResult, generationJobsResult, academicRunsResult, classSyncJobsResult, teacherReportJobsResult, bulkOperationJobsResult]
        .find((result): result is PromiseRejectedResult => result.status === 'rejected')

      setOperationJobs(opJobs.items || [])
      setGenerationJobs(nextGenerationJobs || [])
      setAcademicRuns(nextAcademicRuns || [])
      setClassSyncJobs(nextClassSyncJobs || [])
      setTeacherReportJobs(nextTeacherReportJobs || [])
      setBulkOperationJobs(nextBulkOperationJobs || [])
      if (primaryFailure) setMessage(toUserError(primaryFailure.reason))
      setLoading(false)

      const creatorIds = Array.from(new Set([
        ...(opJobs.items || []).map((job) => job.requested_by),
        ...(nextGenerationJobs || []).map((job) => job.requested_by),
        ...(nextAcademicRuns || []).map((job) => job.requested_by),
        ...(nextClassSyncJobs || []).map((job) => job.requested_by),
        ...(nextTeacherReportJobs || []).map((job) => job.requested_by),
        ...(nextBulkOperationJobs || []).map((job) => job.requested_by),
      ].map((value) => String(value || '').trim()).filter((value) => value && !isSystemActor(value))))
      getUserIdentityLabels(headers, creatorIds).then((labels) => {
        if (generation !== loadGeneration.current) return
        setCreatorLabels(Object.fromEntries(
          Object.entries(labels).map(([userId, item]) => [userId, item.username]),
        ))
      }).catch(() => {
        if (generation === loadGeneration.current) setCreatorLabels({})
      })

      // Supplemental data is allowed to arrive independently after the first
      // table render. A refresh started later owns the state and stale results
      // are discarded. Keep Quiz explicitly loading so an empty state is not
      // shown while the request is still in flight.
      setQuizLoading(true)
      getCourseQuizInstances(headers, { limit: 100 }).then((items) => {
        if (generation === loadGeneration.current) setQuizInstances(items || [])
      }).catch(() => {}).finally(() => {
        if (generation === loadGeneration.current) setQuizLoading(false)
      })
      getAnalyticsOpsStatus(headers).then((value) => {
        if (generation === loadGeneration.current) setAnalyticsOps(value)
      }).catch(() => {})
    } catch (error) {
      if (generation === loadGeneration.current) {
        setMessage(toUserError(error))
        setLoading(false)
        setQuizLoading(false)
      }
    }
  }, [authHeaders, can, status])

  const retryJob = useCallback(async (job: OperationRow) => {
    setLoading(true)
    try {
      if (job.group === 'bulk_sync') {
        const nextJob = await retryAcademicBulkOperationJob(authHeaders(), job.id)
        setBulkOperationJobs((items) => items.map((item) => item.id === nextJob.id ? nextJob : item))
      } else if (job.group === 'teacher_report') {
        const nextJob = await retryAcademicTrainingTeacherReportJob(authHeaders(), job.id)
        setTeacherReportJobs((items) => items.map((item) => item.id === nextJob.id ? nextJob : item))
      } else {
        const nextJob = await retryBankOperationJob(authHeaders(), job.id)
        setOperationJobs((items) => items.map((item) => item.id === nextJob.id ? nextJob : item))
      }
      setMessage({ type: 'success', title: 'Đã chạy lại', body: `Việc ${shortId(job.id)} đã được đưa vào hàng đợi.` })
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
      requestedBy: requestedByLabel(job.requested_by, job.request, creatorLabels),
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
      requestedBy: requestedByLabel(job.requested_by, job.request_json, creatorLabels),
      createdAt: job.created_at,
      message: job.progress_label,
      error: academicJobError(job.error_message, job.result_json),
      rawType: job.job_type,
      parentJobId: job.parent_job_id,
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
      const children = classSyncJobs.filter((child) => child.parent_job_id === job.id)
      const childRunning = children.filter((child) => child.status === 'running').length
      const childQueued = children.filter((child) => child.status === 'queued').length
      const childCompleted = children.filter((child) => child.status === 'completed').length
      const childFailed = children.filter((child) => child.status === 'failed').length
      const childSummary = children.length
        ? `${childRunning} đang chạy · ${childQueued} chờ worker · ${childCompleted} hoàn tất${childFailed ? ` · ${childFailed} lỗi` : ''}`
        : ''
      return {
        id: job.id,
        group: job.job_type === 'learning_refresh_filter' ? 'class_sync' : 'bulk_sync',
        label: bulkJobLabel(job.job_type),
        status: job.status,
        progressCurrent: safeNumber(job.progress_current),
        progressTotal: safeNumber(job.progress_total),
        progressPercent: progressPercent(job.progress_current, job.progress_total),
        scope: job.term_id || 'Tự động ghép Course CMS',
        scopeDetail: scopeText,
        requestedBy: requestedByLabel(job.requested_by, job.request_json, creatorLabels),
        createdAt: job.created_at,
        message: childSummary || job.progress_label || `Map ${mapped}+${already} môn · queue ${queued} lớp · reuse ${reused} · bỏ qua ${skipped}`,
        error: academicJobError(job.error_message, job.result_json),
        rawType: job.job_type,
        canRetry: job.job_type === 'subject_auto_map_all_sync' && job.status === 'failed',
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
        requestedBy: requestedByLabel(run.requested_by, run.counters_json, creatorLabels),
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
      requestedBy: requestedByLabel(job.requested_by, job.request_json, creatorLabels),
      createdAt: job.created_at,
      message: job.progress_label || job.file_name || null,
      error: academicJobError(job.error_message, job.result_json),
      rawType: job.job_type,
      canRetry: job.status === 'failed',
    }))
    const generationRows = generationJobs.map((job): OperationRow => {
      const total = Math.max(0, safeNumber(job.question_count))
      const completed = Math.max(0, safeNumber(job.completed_question_count))
      const batches = job.batch_summary || {}
      const batchText = [
        safeNumber(batches.running) ? `${safeNumber(batches.running)} batch chạy` : '',
        safeNumber(batches.queued) ? `${safeNumber(batches.queued)} batch chờ` : '',
        safeNumber(batches.failed) ? `${safeNumber(batches.failed)} batch lỗi` : '',
      ].filter(Boolean).join(' · ')
      return {
        id: job.id,
        group: 'generation',
        label: 'Gen câu hỏi',
        status: job.status,
        progressCurrent: completed,
        progressTotal: total,
        progressPercent: progressPercent(completed, total),
        scope: job.course_id || 'Ngân hàng câu hỏi',
        scopeDetail: total ? `${total} câu yêu cầu` : null,
        requestedBy: requestedByLabel(job.requested_by, null, creatorLabels),
        createdAt: job.created_at,
        message: batchText || (total ? `Đã tạo ${completed}/${total} câu` : 'Đang chuẩn bị kế hoạch sinh câu hỏi'),
        error: job.error_message || job.model_parse_error || null,
        rawType: 'question_generation',
        canRetry: false,
      }
    })

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
    const loadedParentIds = new Set(bulkOperationJobs.map((job) => job.id))
    const topLevelClassRows = classRows.filter((row) => !row.parentJobId || !loadedParentIds.has(row.parentJobId))
    return [...analyticsRows, ...bulkRows, ...topLevelClassRows, ...apRows, ...reportRows, ...generationRows, ...bankRows]
      .sort((a, b) => String(b.createdAt || '').localeCompare(String(a.createdAt || '')))
  }, [operationJobs, generationJobs, classSyncJobs, academicRuns, teacherReportJobs, bulkOperationJobs, analyticsOps, creatorLabels])

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
    { key: 'status', header: 'Trạng thái', kind: 'status', width: 132, priority: 'required', hideable: false, render: (job) => <StatusBadge status={job.status} label={operationStatusLabel(job)} /> },
    { key: 'progress', header: 'Tiến độ / công đoạn', kind: 'progress', minWidth: 220, priority: 'important', hideable: true, render: (job) => <><div className="job-progress table-progress" role="progressbar" aria-label={`Tiến độ ${job.label}`} aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(job.progressPercent)}><i style={{ width: `${job.progressPercent}%` }} /></div><small>{jobProgressText(job)}</small></> },
    { key: 'created_at', header: 'Thời điểm', kind: 'date', width: 138, priority: 'important', hideable: true, render: (job) => <small>{dateText(job.createdAt)}</small> },
    { key: 'scope', header: 'Phạm vi chi tiết', kind: 'text', minWidth: 175, priority: 'optional', hideable: true, defaultVisible: false, render: (job) => <><span>{job.scope}</span><small>{job.scopeDetail || '—'}</small></> },
    { key: 'requested_by', header: 'Người tạo', kind: 'text', width: 120, priority: 'optional', hideable: true, defaultVisible: false, render: (job) => job.requestedBy || 'Hệ thống' },
    { key: 'message', header: 'Nội dung', kind: 'text', minWidth: 230, priority: 'optional', hideable: true, defaultVisible: false, truncateLines: 2, render: (job) => <span className={job.status === 'failed' ? 'table-error-text' : ''}>{job.error ? userFacingError(job.error) : job.message || 'Đang chờ xử lý'}</span> },
    { key: 'actions', header: 'Thao tác', kind: 'actions', width: 92, sticky: 'right', hideable: false, render: (job) => <button className="btn small secondary" type="button" onClick={() => setSelectedJob(job)}>Chi tiết</button> },
  ], [pageSize, safePage])

  const failed = rows.filter((j) => j.status === 'failed').length
  const running = rows.filter((j) => j.status === 'running').length
  const queued = rows.filter((j) => j.status === 'queued').length
  const completed = rows.filter((j) => j.status === 'completed').length
  const generationActive = rows.filter((j) => j.group === 'generation' && ['queued', 'running'].includes(j.status)).length
  const syncRunning = classSyncJobs.filter((job) => job.status === 'running').length
  const resetFilters = () => update({ q: '', status: 'all', group: 'all', page: 1 }, { resetPage: false })

  const quizColumns = useMemo<EnterpriseTableColumn<CourseQuizInstance>[]>(() => [
    { key: 'stt', header: 'STT', kind: 'index', width: 52, hideable: false, render: (_item, index) => index + 1 },
    { key: 'course', header: 'Khóa học', kind: 'identity', minWidth: 260, hideable: false, render: (item) => <><b>{item.openedx_course_id}</b><small>{item.metadata_json?.quiz_title || 'Quiz trên CMS'}</small></> },
    { key: 'status', header: 'Trạng thái', kind: 'status', width: 116, hideable: false, render: (item) => <StatusBadge status={item.status} /> },
    { key: 'node', header: 'Node CMS', kind: 'text', minWidth: 160, priority: 'optional', hideable: true, render: (item) => <code>{item.openedx_unit_node_id || '—'}</code> },
    { key: 'created', header: 'Ngày tạo', kind: 'date', width: 138, priority: 'important', hideable: true, render: (item) => <small>{dateText(item.created_at)}</small> },
  ], [])

  if (!can('view_jobs')) return <PageRoot className="page-stack enterprise-standard-page ops-console jobs-console"><EnterpriseScreenHeader eyebrow="Vận hành hệ thống" title="Tác vụ nền" description="Theo dõi đồng bộ dữ liệu, tạo câu hỏi, xuất báo cáo và xuất bản bộ đề." icon="jobs" tone="blue" breadcrumbs={[{ label: 'Vận hành hệ thống' }, { label: 'Tác vụ nền' }]} /><section className="card empty-state">Vai trò hiện tại không có quyền xem tiến trình xử lý.</section></PageRoot>
  return <PageRoot className="page-stack enterprise-standard-page ops-console jobs-console ux-enterprise-page">
    <EnterpriseScreenHeader
      eyebrow="Vận hành hệ thống"
      title="Tác vụ nền"
      description="Theo dõi đồng bộ dữ liệu, tạo câu hỏi, xuất báo cáo và xuất bản bộ đề."
      icon="jobs"
      tone="blue"
      breadcrumbs={[{ label: 'Vận hành hệ thống' }, { label: 'Tác vụ nền' }]}
      secondaryActions={<button className="btn secondary" type="button" onClick={() => setQuizOpen(true)}>Quiz gần đây</button>}
      primaryAction={<button className="btn" type="button" onClick={load} disabled={loading}>{loading ? 'Đang tải...' : 'Tải lại'}</button>}
    />
    <ActionMessage message={message} onClose={() => setMessage(null)} />
    <OperationsKpiStrip items={[
      { label: 'Đang chạy', value: running, hint: `${Math.min(syncRunning, 10)}/10 slot đồng bộ lớp đang dùng`, tone: running ? 'info' : 'neutral' },
      { label: 'Đang chờ', value: queued, hint: queued ? 'Chờ worker hoặc chờ tự chạy lại' : 'Không có hàng đợi', tone: queued ? 'info' : 'neutral' },
      { label: 'Gen câu hỏi', value: generationActive, hint: 'Job sinh câu hỏi đang hoạt động', tone: generationActive ? 'info' : 'neutral' },
      { label: 'Hoàn tất', value: completed, hint: 'Trong dữ liệu vừa tải', tone: 'success' },
      { label: 'Thất bại', value: failed, hint: failed ? 'Cần mở chi tiết để xử lý' : 'Không có lỗi gần đây', tone: failed ? 'danger' : 'neutral' },
    ]} />
    <CompactFilterBar actions={<button className="btn secondary" type="button" onClick={resetFilters} disabled={!q && status === 'all' && operationGroup === 'all'}>Xóa lọc</button>}>
      <label>Tìm việc<input className="input" value={q} onChange={(event) => update({ q: event.target.value })} placeholder="Mã việc, lớp, phạm vi..." /></label>
      <label>Trạng thái<select className="input" value={status} onChange={(event) => update({ status: event.target.value })}><option value="all">Tất cả</option><option value="active">Đang xử lý</option><option value="queued">Đang chờ</option><option value="running">Đang chạy</option><option value="completed">Hoàn tất</option><option value="failed">Thất bại</option></select></label>
      <label>Nhóm việc<select className="input" value={operationGroup} onChange={(event) => update({ group: event.target.value })}><option value="all">Tất cả</option><option value="class_sync">Đồng bộ lớp/CMS</option><option value="generation">Gen câu hỏi</option><option value="ap_sync">Đồng bộ AP</option><option value="teacher_report">Báo cáo giảng viên</option><option value="analytics">Học online</option><option value="bulk_sync">Ghép Course CMS hàng loạt</option><option value="bank">Bank / Quiz</option></select></label>
    </CompactFilterBar>
    <EnterpriseDataTable tableId="ops-jobs-v2" caption="Danh sách việc" rows={pageRows} columns={columns} rowKey={(job) => `${job.group}-${job.id}`} density={density} onDensityChange={(value) => update({ density: value }, { resetPage: false })} loading={loading} emptyTitle="Không có việc phù hợp" emptyDescription="Thử thay đổi từ khóa, trạng thái hoặc nhóm việc." page={safePage} pageSize={pageSize} total={filteredRows.length} totalPages={totalPages} onPageChange={(value) => update({ page: value }, { resetPage: false })} onPageSizeChange={(value) => update({ pageSize: value, page: 1 }, { resetPage: false })} label="việc" getRowClassName={(job) => `row-${job.status}`} />

    <SideDrawer open={Boolean(selectedJob)} title={selectedJob?.label || 'Chi tiết tác vụ'} description={selectedJob ? `ID ${selectedJob.id}` : undefined} onClose={() => setSelectedJob(null)} footer={selectedJob?.canRetry ? <button className="btn" type="button" onClick={() => { void retryJob(selectedJob); setSelectedJob(null) }} disabled={loading}>Chạy lại tác vụ</button> : undefined}>
      {selectedJob ? <div className="page-stack compact-stack"><StatusBadge status={selectedJob.status} label={statusText(selectedJob.status)} /><InfoPairGrid items={[
        { label: 'Nhóm việc', value: selectedJob.group },
        { label: 'Loại kỹ thuật', value: selectedJob.rawType || '—' },
        { label: 'Phạm vi', value: selectedJob.scope },
        { label: 'Đối tượng', value: selectedJob.scopeDetail || '—' },
        { label: 'Người tạo', value: selectedJob.requestedBy || 'Hệ thống' },
        { label: 'Thời điểm', value: dateText(selectedJob.createdAt) },
        { label: 'Tiến độ', value: jobProgressText(selectedJob), wide: true },
        { label: selectedJob.error ? 'Lỗi' : 'Nội dung', value: selectedJob.error || selectedJob.message || 'Không có mô tả.', wide: true },
      ]} />
      {classSyncJobs.some((child) => child.parent_job_id === selectedJob.id) ? <section className="page-stack compact-stack">
        <b>Các lớp trong tác vụ này</b>
        {classSyncJobs.filter((child) => child.parent_job_id === selectedJob.id).slice(0, 20).map((child) => <div className="stat-row" key={child.id}>
          <span>{shortId(child.class_id)} · {academicJobLabel(child.job_type)}</span>
          <StatusBadge status={child.status} label={child.status === 'queued' ? (/tự chạy lại/i.test(child.progress_label || '') ? 'Chờ tự chạy lại' : 'Chờ worker') : statusText(child.status)} />
          <small>{child.progress_label || (child.status === 'queued' ? 'Chờ worker' : 'Đang xử lý')}</small>
        </div>)}
      </section> : null}
      </div> : null}
    </SideDrawer>

    <SideDrawer open={quizOpen} title="Quiz gần đây" description="Các Quiz đã tạo trên Open edX CMS." onClose={() => setQuizOpen(false)}>
      <EnterpriseDataTable tableId="ops-recent-quizzes" caption="Quiz gần đây" rows={quizInstances.slice(0, 50)} columns={quizColumns} rowKey={(item) => item.id} density="compact" loading={quizLoading} label="Quiz" emptyTitle="Chưa có Quiz trên CMS" />
    </SideDrawer>
  </PageRoot>
}

export default function JobsPage() {
  return <Suspense fallback={<div className="card">Đang tải danh sách việc...</div>}><JobsContent /></Suspense>
}
