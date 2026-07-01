'use client'

import Link from 'next/link'
import { useEffect, useMemo, useState } from 'react'
import { useAppContext } from '../../context/AppContext'
import {
  createAcademicTrainingTeacherCacheJob,
  createAcademicTrainingTeacherExportJob,
  downloadAcademicTrainingTeacherReport,
  downloadAcademicTrainingTeacherReportJob,
  getAcademicCampuses,
  getAcademicTerms,
  getAcademicTrainingTeacherReport,
  getAcademicTrainingTeacherReportJob,
} from '../../lib/api'
import { AcademicCampus, AcademicLearningComponentScore, AcademicTeacherReportJob, AcademicTerm, AcademicTrainingTeacherReport } from '../../types'
import { useDebouncedValue } from '../../lib/useDebouncedValue'

const PAGE_SIZE = 50

type TrainingSummary = {
  teacher_count: number
  class_count: number
  subject_count: number
  student_count: number
  unique_student_count: number
  relearn_student_count: number
  total_relearn_count: number
  cms_synced_count: number
  learning_enrolled_count: number
  learning_active_count: number
  risk_student_count: number
  classes_without_course_count: number
  deadline_late_student_count: number
  deadline_late_quiz_count: number
  exam_eligible_student_count: number
  exam_not_eligible_student_count: number
  exam_insufficient_data_student_count: number
  quiz_failed_count: number
  assignment_not_graded_count: number
}

const EMPTY_SUMMARY: TrainingSummary = {
  teacher_count: 0,
  class_count: 0,
  subject_count: 0,
  student_count: 0,
  unique_student_count: 0,
  relearn_student_count: 0,
  total_relearn_count: 0,
  cms_synced_count: 0,
  learning_enrolled_count: 0,
  learning_active_count: 0,
  risk_student_count: 0,
  classes_without_course_count: 0,
  deadline_late_student_count: 0,
  deadline_late_quiz_count: 0,
  exam_eligible_student_count: 0,
  exam_not_eligible_student_count: 0,
  exam_insufficient_data_student_count: 0,
  quiz_failed_count: 0,
  assignment_not_graded_count: 0,
}

function normalizeSummary(value?: Partial<TrainingSummary> | null): TrainingSummary {
  return {
    ...EMPTY_SUMMARY,
    ...(value || {}),
    relearn_student_count: Number(value?.relearn_student_count || 0),
    total_relearn_count: Number(value?.total_relearn_count || 0),
    deadline_late_student_count: Number(value?.deadline_late_student_count || 0),
    deadline_late_quiz_count: Number(value?.deadline_late_quiz_count || 0),
    exam_eligible_student_count: Number((value as any)?.exam_eligible_student_count || 0),
    exam_not_eligible_student_count: Number((value as any)?.exam_not_eligible_student_count || 0),
    exam_insufficient_data_student_count: Number((value as any)?.exam_insufficient_data_student_count || 0),
    quiz_failed_count: Number((value as any)?.quiz_failed_count || 0),
    assignment_not_graded_count: Number((value as any)?.assignment_not_graded_count || 0),
  }
}

function normalizePercentValue(value?: number | null) {
  if (typeof value !== 'number' || Number.isNaN(value)) return null
  if (value >= 0 && value <= 1) return value * 100
  return value
}

function percentLabel(value?: number | null) {
  const percent = normalizePercentValue(value)
  if (percent === null) return 'N/A'
  return `${Math.round(percent * 10) / 10}%`
}

function grade10Label(value?: number | null) {
  const percent = normalizePercentValue(value)
  if (percent === null) return 'N/A'
  const score = Math.max(0, Math.min(10, percent / 10))
  return `${Math.round(score * 10) / 10}/10`
}

function score10Label(value?: number | null) {
  if (typeof value !== 'number' || Number.isNaN(value)) return 'N/A'
  let score = value
  if (score >= 0 && score <= 1) score *= 10
  if (score > 10) score /= 10
  score = Math.max(0, Math.min(10, score))
  return `${Math.round(score * 10) / 10}/10`
}

function componentKey(score: AcademicLearningComponentScore) {
  return String(score.key || score.name || '').trim()
}

function componentDisplayName(score: AcademicLearningComponentScore) {
  return String(score.name || score.key || 'Đầu điểm').trim()
}

function gradeColumnCompare(left: { key: string; name: string }, right: { key: string; name: string }) {
  return left.name.localeCompare(right.name, 'vi', { numeric: true, sensitivity: 'base' })
}

function componentScoreText(score?: AcademicLearningComponentScore | null) {
  if (!score) return 'N/A'
  const percent = normalizePercentValue(score.percent)
  if (percent !== null) return grade10Label(percent)
  if (typeof score.earned === 'number' && typeof score.possible === 'number' && score.possible > 0) {
    const value = Math.max(0, Math.min(10, (score.earned / score.possible) * 10))
    return `${Math.round(value * 10) / 10}/10`
  }
  return 'N/A'
}

function countLabel(value?: number | null) {
  return String(value || 0)
}

function ratioLabel(done?: number | null, total?: number | null) {
  const cleanDone = done || 0
  const cleanTotal = total || 0
  return `${cleanDone}/${cleanTotal}`
}

function alertText(alerts?: string[]) {
  return alerts?.length ? alerts.slice(0, 3).join(', ') : 'Không có cảnh báo lớn'
}

function counterText(total: number, page: number, pageSize: number) {
  if (!total) return '0 giáo viên'
  const start = (page - 1) * pageSize + 1
  const end = Math.min(total, page * pageSize)
  return `${start}-${end} / ${total}`
}

function riskTone(item: AcademicTrainingTeacherReport) {
  if (item.classes_without_course_count || item.status_counts?.sync_error) return 'status-pill danger'
  if (item.risk_student_count) return 'status-pill warning'
  return 'status-pill success'
}


function formatDateTime(value?: string | null) {
  if (!value) return 'Chưa có cache'
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return String(value)
  return parsed.toLocaleString('vi-VN', { hour12: false })
}

function jobPercent(job?: AcademicTeacherReportJob | null) {
  if (!job) return 0
  const total = Math.max(1, Number(job.progress_total || 100))
  return Math.max(0, Math.min(100, Math.round((Number(job.progress_current || 0) / total) * 100)))
}

function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  window.setTimeout(() => URL.revokeObjectURL(url), 1000)
}

export default function TeacherManagementPage() {
  const { authHeaders } = useAppContext()
  const headers = useMemo(() => authHeaders(), [authHeaders])
  const [terms, setTerms] = useState<AcademicTerm[]>([])
  const [campuses, setCampuses] = useState<AcademicCampus[]>([])
  const [items, setItems] = useState<AcademicTrainingTeacherReport[]>([])
  const [summary, setSummary] = useState<TrainingSummary>(EMPTY_SUMMARY)
  const [summaryScope, setSummaryScope] = useState<string>('current_page')
  const [termId, setTermId] = useState('')
  const [branch, setBranch] = useState('poly')
  const [campus, setCampus] = useState('')
  const [search, setSearch] = useState('')
  const debouncedSearch = useDebouncedValue(search, 350)
  const [learningStatus, setLearningStatus] = useState('all')
  const [page, setPage] = useState(1)
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(false)
  const [exporting, setExporting] = useState(false)
  const [cacheInfo, setCacheInfo] = useState<{ status?: string; built_at?: string | null; row_count?: number | null } | null>(null)
  const [cacheJob, setCacheJob] = useState<AcademicTeacherReportJob | null>(null)
  const [exportJob, setExportJob] = useState<AcademicTeacherReportJob | null>(null)
  const [message, setMessage] = useState('')

  useEffect(() => {
    let cancelled = false
    getAcademicTerms(headers, { branch, active: true })
      .then((data) => {
        if (cancelled) return
        setTerms(data)
        setTermId((current) => {
          if (current && data.some((item) => item.id === current)) return current
          const preferred = data.find((item) => item.term_name === 'Summer 2026') || data[0]
          return preferred?.id || ''
        })
      })
      .catch((error) => setMessage(error instanceof Error ? error.message : 'Không tải được học kỳ'))
    return () => { cancelled = true }
  }, [headers, branch])

  useEffect(() => {
    let cancelled = false
    getAcademicCampuses(headers, { branch, active: true })
      .then((data) => {
        if (cancelled) return
        setCampuses(data)
        setCampus((current) => {
          if (current && data.some((item) => item.campus_code === current)) return current
          return data[0]?.campus_code || ''
        })
      })
      .catch(() => setCampuses([]))
    return () => { cancelled = true }
  }, [headers, branch])

  const resetReportState = () => {
    setItems([])
    setSummary(EMPTY_SUMMARY)
    setTotal(0)
  }

  const loadReport = async (cancelledRef?: { cancelled: boolean }) => {
    if (!termId) {
      resetReportState()
      setLoading(false)
      return
    }
    setLoading(true)
    setMessage('')
    try {
      const result = await getAcademicTrainingTeacherReport(headers, { termId, branch, campus, search: debouncedSearch, learningStatus, page, pageSize: PAGE_SIZE })
      if (cancelledRef?.cancelled) return
      setItems(result.items || [])
      setSummary(normalizeSummary(result.summary))
      setSummaryScope(result.summary_scope || 'current_page')
      setTotal(result.total || 0)
      setCacheInfo(result.cache || null)
    } catch (error) {
      if (!cancelledRef?.cancelled) setMessage(error instanceof Error ? error.message : 'Không tải được báo cáo quản lý đào tạo')
    } finally {
      if (!cancelledRef?.cancelled) setLoading(false)
    }
  }

  useEffect(() => {
    const cancelledRef = { cancelled: false }
    loadReport(cancelledRef)
    return () => { cancelledRef.cancelled = true }
  }, [headers, termId, branch, campus, debouncedSearch, learningStatus, page])



  useEffect(() => {
    const activeJob = cacheJob && ['queued', 'running'].includes(cacheJob.status) ? cacheJob : exportJob && ['queued', 'running'].includes(exportJob.status) ? exportJob : null
    if (!activeJob) return
    const timer = window.setInterval(async () => {
      try {
        const latest = await getAcademicTrainingTeacherReportJob(headers, activeJob.id)
        if (latest.job_type === 'rebuild_cache') {
          setCacheJob(latest)
          if (latest.status === 'completed') {
            setMessage('Đã tính lại báo cáo. Bảng sẽ đọc từ cache mới.')
            loadReport()
          }
        } else {
          setExportJob(latest)
          if (latest.status === 'completed') {
            setMessage('File Excel đã sẵn sàng. Bấm Tải Excel để tải về.')
          }
        }
      } catch (error) {
        setMessage(error instanceof Error ? error.message : 'Không kiểm tra được trạng thái job báo cáo')
      }
    }, 2500)
    return () => window.clearInterval(timer)
  }, [headers, cacheJob?.id, cacheJob?.status, exportJob?.id, exportJob?.status])

  const selectedTerm = terms.find((item) => item.id === termId)
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE))

  const classComponentColumns = (item: AcademicTrainingTeacherReport) => {
    const columns: Array<{ key: string; name: string }> = []
    const seen = new Set<string>()
    ;(item.classes || []).forEach((cls) => {
      ;(cls.learning_component_summaries || []).forEach((score) => {
        const key = componentKey(score)
        const name = componentDisplayName(score)
        const dedupeKey = (key || name).toLowerCase()
        if (!dedupeKey || seen.has(dedupeKey)) return
        seen.add(dedupeKey)
        columns.push({ key: key || name, name })
      })
    })
    return columns.sort(gradeColumnCompare)
  }

  const classComponentScore = (cls: any, column: { key: string; name: string }) => {
    return cls.learning_component_summaries?.find((score: AcademicLearningComponentScore) => componentKey(score) === column.key || score.name === column.name) || null
  }

  const exportExcel = async () => {
    setExporting(true)
    setMessage('')
    try {
      const blob = await downloadAcademicTrainingTeacherReport(headers, { termId, branch, campus, search: debouncedSearch, learningStatus })
      const termPart = (selectedTerm?.term_name || 'term').replace(/[^a-zA-Z0-9]+/g, '-')
      downloadBlob(blob, `bao-cao-quan-ly-giang-vien-${branch}-${termPart}.xlsx`)
      setMessage('Đã xuất Excel báo cáo quản lý đào tạo.')
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Không xuất được file Excel')
    } finally {
      setExporting(false)
    }
  }



  const rebuildCache = async () => {
    if (!termId) {
      setMessage('Chọn học kỳ trước khi tính lại báo cáo.')
      return
    }
    setMessage('')
    try {
      const job = await createAcademicTrainingTeacherCacheJob(headers, { termId, branch, campus })
      setCacheJob(job)
      setMessage('Đã đưa yêu cầu tính lại báo cáo vào hàng đợi.')
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Không tạo được job tính lại báo cáo')
    }
  }

  const exportExcelBackground = async () => {
    if (!termId) {
      setMessage('Chọn học kỳ trước khi xuất Excel.')
      return
    }
    setMessage('')
    try {
      const job = await createAcademicTrainingTeacherExportJob(headers, { termId, branch, campus, search: debouncedSearch, learningStatus })
      setExportJob(job)
      setMessage('Đã đưa yêu cầu xuất Excel vào hàng đợi.')
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Không tạo được job xuất Excel')
    }
  }

  const downloadBackgroundExcel = async () => {
    if (!exportJob?.id) return
    try {
      const blob = await downloadAcademicTrainingTeacherReportJob(headers, exportJob.id)
      downloadBlob(blob, exportJob.file_name || `teacher-management-report-${exportJob.id}.xlsx`)
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Không tải được file Excel')
    }
  }


  return <div className="page-stack student-management-page academic-flow-page training-management-page teacher-management-page ux-enterprise-page">
    <section className="card academic-unified-card ux-surface-card teacher-workspace-card">
      <div className="teacher-compact-toolbar">
        <div>
          <b>{selectedTerm?.term_name || 'Chưa chọn kỳ'} · {branch.toUpperCase()} · {campus ? campus.toUpperCase() : 'Tất cả cơ sở'}</b>
          <small>{counterText(total, page, PAGE_SIZE)} · Bấm Xem lớp để sang trang lớp riêng, không render nặng toàn hệ.</small>
        </div>
        <div className="teacher-compact-actions">
          <button className="btn secondary small" type="button" onClick={() => loadReport()} disabled={loading}>{loading ? 'Đang tải...' : 'Tải lại'}</button>
          <button className="btn secondary small" type="button" onClick={rebuildCache} disabled={!termId || cacheJob?.status === 'queued' || cacheJob?.status === 'running'}>{cacheJob && ['queued', 'running'].includes(cacheJob.status) ? `Đang tính ${jobPercent(cacheJob)}%` : 'Tính lại báo cáo'}</button>
          <button className="btn secondary small" type="button" onClick={exportExcelBackground} disabled={!termId || exportJob?.status === 'queued' || exportJob?.status === 'running'}>{exportJob && ['queued', 'running'].includes(exportJob.status) ? `Đang xuất ${jobPercent(exportJob)}%` : 'Xuất Excel nền'}</button>
          {exportJob?.status === 'completed' && <button className="btn primary small" type="button" onClick={downloadBackgroundExcel}>Tải Excel</button>}
          <button className="btn ghost small" type="button" onClick={exportExcel} disabled={exporting || loading}>{exporting ? 'Đang xuất...' : 'Xuất trực tiếp'}</button>
        </div>
      </div>

      <div className="academic-filter-bar ux-filter-grid teacher-filter-bar">
        <label>Hệ
          <select className="input" value={branch} onChange={(event) => { setBranch(event.target.value); setCampus(''); setPage(1) }}>
            <option value="poly">Poly</option>
            <option value="ptcd">PTCĐ</option>
          </select>
        </label>
        <label>Học kỳ
          <select className="input" value={termId} onChange={(event) => { setTermId(event.target.value); setPage(1) }}>
            {!terms.length && <option value="">Chưa có kỳ, tạo tại /semesters</option>}
            {terms.map((item) => <option key={item.id} value={item.id}>{item.term_name}</option>)}
          </select>
        </label>
        <label>Cơ sở
          <select className="input" value={campus} onChange={(event) => { setCampus(event.target.value); setPage(1) }}>
            <option value="">Tất cả cơ sở</option>
            {campuses.map((item) => <option key={item.id} value={item.campus_code}>{item.campus_code.toUpperCase()} · {item.campus_name}</option>)}
          </select>
        </label>
        <label>Trạng thái
          <select className="input" value={learningStatus} onChange={(event) => { setLearningStatus(event.target.value); setPage(1) }}>
            <option value="all">Tất cả giáo viên</option>
            <option value="no_course_map">Có lớp chưa map course</option>
            <option value="cms_not_synced">Có SV chưa đồng bộ CMS</option>
            <option value="not_fully_enrolled">Có SV chưa enroll</option>
            <option value="no_activity">Có SV chưa học</option>
            <option value="low_progress">Có SV tiến độ thấp</option>
            <option value="low_grade">Có SV điểm thấp</option>
            <option value="deadline_late">Có SV trễ deadline quiz</option>
            <option value="exam_not_eligible">Có SV không được thi</option>
            <option value="exam_insufficient_data">Có SV thiếu dữ liệu xét thi</option>
            <option value="has_alert">Có cảnh báo</option>
          </select>
        </label>
        <label className="academic-filter-search">Tìm giảng viên/lớp/môn
          <input className="input" value={search} onChange={(event) => { setSearch(event.target.value); setPage(1) }} placeholder="Tên GV, username, COM1071, lớp..." />
        </label>
      </div>

      <div className="academic-summary-strip training-summary-strip ux-kpi-grid">
        <div><span>Giảng viên</span><b>{countLabel(summary.teacher_count)}</b><small>{summaryScope === 'filtered' ? 'Theo bộ lọc' : 'Trang hiện tại'}</small></div>
        <div><span>Lớp</span><b>{countLabel(summary.class_count)}</b><small>Lượt lớp phân công</small></div>
        <div><span>Sinh viên</span><b>{countLabel(summary.student_count)}</b><small>Lượt SV theo lớp</small></div>
        <div><span>Đã đồng bộ CMS</span><b>{countLabel(summary.cms_synced_count)}</b><small>User CMS đã match</small></div>
        <div><span>Đã enroll</span><b>{countLabel(summary.learning_enrolled_count)}</b><small>Enrollment CMS</small></div>
        <div><span>Cần theo dõi</span><b>{countLabel(summary.risk_student_count)}</b><small>SV cảnh báo, không đếm trùng</small></div>
        <div><span>Trễ deadline</span><b>{countLabel(summary.deadline_late_student_count)}</b><small>{countLabel(summary.deadline_late_quiz_count)} lượt quiz trễ</small></div>
        <div><span>Không được thi</span><b>{countLabel(summary.exam_not_eligible_student_count)}</b><small>{countLabel(summary.exam_insufficient_data_student_count)} SV có dữ liệu chưa đủ</small></div>
      </div>


      <div className="academic-inline-error compact-notice cache-status-notice"><b>Báo cáo:</b><span>{cacheInfo?.status === 'hit' ? `Đang đọc cache cập nhật lúc ${formatDateTime(cacheInfo.built_at || null)} (${cacheInfo.row_count || 0} GV)` : 'Chưa có cache cho bộ lọc này; hệ thống đang tính động. Nên bấm Tính lại báo cáo sau khi đồng bộ AP/CMS.'}</span></div>
      {cacheJob && ['queued', 'running', 'failed'].includes(cacheJob.status) && <div className="academic-inline-error compact-notice"><b>Job báo cáo:</b><span>{cacheJob.progress_label} · {jobPercent(cacheJob)}%{cacheJob.status === 'failed' ? ` · ${cacheJob.error_message || 'Thất bại'}` : ''}</span></div>}
      {exportJob && ['queued', 'running', 'failed'].includes(exportJob.status) && <div className="academic-inline-error compact-notice"><b>Job Excel:</b><span>{exportJob.progress_label} · {jobPercent(exportJob)}%{exportJob.status === 'failed' ? ` · ${exportJob.error_message || 'Thất bại'}` : ''}</span></div>}

      {!campus && <div className="academic-inline-error compact-notice"><b>Lưu ý:</b><span>Đang xem tất cả cơ sở; nên lọc cơ sở khi dữ liệu lớn.</span></div>}

      {message && <div className="academic-inline-error"><b>Thông báo</b><span>{message}</span></div>}

      <div className="table-wrap academic-table-wrap training-table-wrap ux-table-card">
        <table className="data-table academic-data-table training-teacher-table">
          <thead>
            <tr>
              <th>Giảng viên</th>
              <th>Quy mô đào tạo</th>
              <th>Đồng bộ CMS</th>
              <th>Tiến độ học</th>
              <th>Sinh viên học như nào</th>
              <th>Thao tác</th>
            </tr>
          </thead>
          <tbody>
            {loading && Array.from({ length: 6 }).map((_, index) => <tr key={`teacher-skeleton-${index}`} className="ux-skeleton-row"><td colSpan={6}><span className="ux-skeleton-line wide" /><span className="ux-skeleton-line" /></td></tr>)}
            {!loading && !items.length && <tr><td colSpan={6}><div className="ux-empty-state"><b>Chưa có dữ liệu theo bộ lọc hiện tại</b><span>Đổi cơ sở, học kỳ hoặc xóa từ khóa tìm kiếm để xem danh sách giảng viên.</span><button className="btn secondary small" type="button" onClick={() => { setSearch(''); setLearningStatus('all'); setPage(1) }}>Xóa bộ lọc nhanh</button></div></td></tr>}
            {!loading && items.map((item) => {
              const statuses = item.status_counts || {}
              const teacherClassesParams = new URLSearchParams()
              if (termId) teacherClassesParams.set('term_id', termId)
              if (branch) teacherClassesParams.set('branch', branch)
              if (campus) teacherClassesParams.set('campus', campus)
              if (selectedTerm?.term_name) teacherClassesParams.set('term_name', selectedTerm.term_name)
              teacherClassesParams.set('teacher_name', item.teacher_name || item.teacher_username)
              return <tr key={item.teacher_id} className="teacher-row-compact">
                <td>
                  <div className="teacher-identity"><span className="teacher-avatar">{(item.teacher_name || item.teacher_username || 'GV').slice(0, 2).toUpperCase()}</span><div><b>{item.teacher_name || item.teacher_username}</b>
                  <small>{item.teacher_username}{item.teacher_email ? ` · ${item.teacher_email}` : ''}</small>
                  <small>{item.branch?.toUpperCase() || 'N/A'}{item.campus ? ` · ${item.campus.toUpperCase()}` : ''}</small></div></div>
                </td>
                <td>
                  <b>{item.class_count} lớp · {item.subject_count} môn</b>
                  <small>{item.subject_codes?.slice(0, 6).join(', ') || 'N/A'}</small>
                  <small>{item.student_count} lượt SV · {item.unique_student_count} SV riêng biệt</small>
                  <small>Học lại: {countLabel(item.relearn_student_count)} SV · {countLabel(item.total_relearn_count)} lượt</small>
                </td>
                <td>
                  <span className="status-pill success">Đã đồng bộ CMS {ratioLabel(item.cms_synced_count, item.student_count)}</span>
                  <small>Đã enroll {ratioLabel(item.learning_enrolled_count, item.student_count)}</small>
                  {item.classes_without_course_count ? <small className="danger-text">{item.classes_without_course_count} lớp chưa map Course CMS</small> : <small>Course CMS đã map cho các lớp có dữ liệu</small>}
                </td>
                <td>
                  <b>Completion {percentLabel(item.learning_avg_progress_percent)}</b>
                  <small>Điểm tổng {score10Label(item.learning_avg_grade_10)}</small>
                  <small>Có hoạt động {ratioLabel(item.learning_active_count, item.student_count)}</small>
                  <small>Trễ deadline {countLabel(item.deadline_late_student_count)} SV · {countLabel(item.deadline_late_quiz_count)} lượt quiz</small>
                </td>
                <td>
                  <span className={riskTone(item)}>{item.risk_student_count ? `${item.risk_student_count} SV cần theo dõi` : 'Ổn'}</span>
                  <small>Chưa học {countLabel(statuses.no_activity)} · Tiến độ thấp {countLabel(statuses.low_progress)} · Điểm thấp {countLabel(statuses.low_grade)}</small>
                  <small>Trễ deadline {countLabel(statuses.deadline_late)} SV · Không được thi {countLabel(statuses.exam_not_eligible)} SV</small>
                  <small>{alertText(item.learning_alerts)}</small>
                </td>
                <td>
                  <Link className="btn secondary small teacher-row-action" href={`/teacher-management/teachers/${encodeURIComponent(item.teacher_id)}/classes?${teacherClassesParams.toString()}`}>Xem lớp</Link>
                </td>
              </tr>
            })}
          </tbody>
        </table>
      </div>

      <div className="pagination-row">
        <button className="btn secondary" type="button" disabled={page <= 1 || loading} onClick={() => setPage((value) => Math.max(1, value - 1))}>Trang trước</button>
        <span>Trang {page}/{totalPages}</span>
        <button className="btn secondary" type="button" disabled={page >= totalPages || loading} onClick={() => setPage((value) => value + 1)}>Trang sau</button>
      </div>
    </section>
  </div>
}
