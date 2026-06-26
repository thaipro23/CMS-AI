'use client'

import Link from 'next/link'
import { Suspense, useEffect, useMemo, useState } from 'react'
import { useParams, useSearchParams } from 'next/navigation'
import { useAppContext } from '../../../../context/AppContext'
import {
  getAcademicClass,
  getAcademicClassMappingSummary,
  getAcademicClassLearningSummary,
  getAcademicClassStudents,
  enqueueAcademicClassFullCmsSyncJob,
  getAcademicClassSyncJob,
  getAcademicClassSyncJobs,
} from '../../../../lib/api'
import { AcademicClass, AcademicClassSyncJob, AcademicLearningComponentScore, AcademicLearningSummary, AcademicMappingSummary, AcademicStudent } from '../../../../types'
import { formatVNDateTime } from '../../../../lib/time'

const PAGE_SIZE = 50

function cmsSyncLabel(status?: string | null) {
  const value = (status || 'not_checked').toLowerCase()
  if (value === 'matched') return 'Đã đồng bộ CMS'
  if (value === 'inactive') return 'User CMS inactive'
  if (value === 'missing') return 'Chưa có trên CMS'
  if (value === 'ambiguous') return 'Trùng user CMS'
  if (value === 'manual_required') return 'Cần xử lý tay'
  return 'Chưa kiểm tra'
}
function cmsSyncClass(status?: string | null) {
  const value = (status || 'not_checked').toLowerCase()
  if (value === 'matched') return 'status-pill success'
  if (['inactive', 'missing', 'ambiguous'].includes(value)) return 'status-pill danger'
  if (value === 'manual_required') return 'status-pill warning'
  return 'status-pill neutral'
}
function mappingSourceLabel(source?: string | null) {
  if (source === 'subject_term_mapping') return 'Kế thừa từ môn'
  if (source === 'class_override') return 'Map riêng lớp'
  return 'Chưa map'
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
function learningStatusLabel(value?: string | null) {
  const status = (value || 'not_synced').toLowerCase()
  if (status === 'cms_not_synced') return 'Chưa đồng bộ CMS'
  if (status === 'not_synced') return 'Chưa cập nhật học tập'
  if (status === 'not_enrolled') return 'Chưa enroll'
  if (status === 'no_activity') return 'Chưa vào học'
  if (status === 'low_progress') return 'Tiến độ thấp'
  if (status === 'low_grade') return 'Điểm thấp'
  if (status === 'sync_error') return 'Lỗi dữ liệu'
  if (status === 'good') return 'Hoàn thành tốt'
  if (status === 'in_progress') return 'Đang học'
  return 'Chưa cập nhật'
}
function learningStatusClass(value?: string | null) {
  const status = (value || 'not_synced').toLowerCase()
  if (['good', 'in_progress'].includes(status)) return 'status-pill success'
  if (['low_progress', 'low_grade', 'not_enrolled', 'cms_not_synced', 'sync_error'].includes(status)) return 'status-pill danger'
  if (status === 'no_activity') return 'status-pill warning'
  return 'status-pill neutral'
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
function componentKey(score: AcademicLearningComponentScore) {
  return String(score.key || score.name || '').trim()
}
function componentDisplayName(score: AcademicLearningComponentScore) {
  return String(score.name || score.key || 'Đầu điểm').trim()
}
function gradeColumnCompare(left: { key: string; name: string }, right: { key: string; name: string }) {
  return left.name.localeCompare(right.name, 'vi', { numeric: true, sensitivity: 'base' })
}
function enrollmentLabel(value?: string | null) {
  const status = (value || 'unknown').toLowerCase()
  if (status === 'enrolled') return 'Đã enroll'
  if (status === 'inactive') return 'Enroll inactive'
  if (status === 'not_enrolled') return 'Chưa enroll'
  if (status === 'missing_user') return 'Chưa có user CMS'
  return 'Chưa cập nhật'
}
function enrollmentClass(value?: string | null) {
  const status = (value || 'unknown').toLowerCase()
  if (status === 'enrolled') return 'status-pill success'
  if (['not_enrolled', 'missing_user', 'inactive'].includes(status)) return 'status-pill danger'
  return 'status-pill neutral'
}

function ClassDetailContent() {
  const params = useParams<{ classId: string }>()
  const searchParams = useSearchParams()
  const classId = decodeURIComponent(String(params.classId || ''))
  const { authHeaders } = useAppContext()
  const headers = useMemo(() => authHeaders(), [authHeaders])
  const jsonHeaders = useMemo(() => authHeaders(true), [authHeaders])
  const [classInfo, setClassInfo] = useState<AcademicClass | null>(null)
  const [students, setStudents] = useState<AcademicStudent[]>([])
  const [summary, setSummary] = useState<AcademicMappingSummary | null>(null)
  const [learningSummary, setLearningSummary] = useState<AcademicLearningSummary | null>(null)
  const [search, setSearch] = useState('')
  const [learningStatus, setLearningStatus] = useState('all')
  const [page, setPage] = useState(1)
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(false)
  const [syncingFullFlow, setSyncingFullFlow] = useState(false)
  const [message, setMessage] = useState('')
  const [errorModal, setErrorModal] = useState('')
  const [activeJob, setActiveJob] = useState<AcademicClassSyncJob | null>(null)
  const [syncJobs, setSyncJobs] = useState<AcademicClassSyncJob[]>([])
  const [recoveringJob, setRecoveringJob] = useState(false)

  const refreshStudents = async () => {
    const [studentPage, nextSummary, nextLearning] = await Promise.all([
      getAcademicClassStudents(headers, classId, { search, learningStatus, page, pageSize: PAGE_SIZE }),
      getAcademicClassMappingSummary(headers, classId),
      getAcademicClassLearningSummary(headers, classId),
    ])
    setStudents(studentPage.items)
    setTotal(studentPage.total)
    setSummary(nextSummary)
    setLearningSummary(nextLearning)
  }

  const isJobActive = (job?: AcademicClassSyncJob | null) => {
    const status = String(job?.status || '').toLowerCase()
    return Boolean(job?.id) && !['completed', 'failed'].includes(status)
  }

  const jobTypeLabel = (type?: string | null) => {
    if (type === 'full_cms_sync') return 'Đồng bộ full CMS'
    if (['cms_sync_check', 'cms_enrollment_sync', 'learning_sync'].includes(String(type || ''))) return 'Đồng bộ full CMS'
    return 'Đồng bộ CMS'
  }

  const jobStatusLabel = (status?: string | null) => {
    const value = String(status || '').toLowerCase()
    if (value === 'queued') return 'Đang chờ worker'
    if (value === 'running') return 'Đang chạy'
    if (value === 'completed') return 'Hoàn tất'
    if (value === 'failed') return 'Thất bại'
    return status || 'Chưa rõ'
  }

  const jobProgressPercent = (job?: AcademicClassSyncJob | null) => {
    if (!job) return 0
    const current = Number(job.progress_current || 0)
    const total = Math.max(1, Number(job.progress_total || 100))
    return Math.min(100, Math.max(0, Math.round((current / total) * 100)))
  }

  const refreshSyncJobs = async () => {
    const jobs = await getAcademicClassSyncJobs(headers, classId, 10)
    setSyncJobs(jobs)
    return jobs
  }

  const rememberActiveJob = (job?: AcademicClassSyncJob | null) => {
    if (typeof window === 'undefined') return
    const key = `academic-class-sync-active-job:${classId}`
    if (isJobActive(job)) window.localStorage.setItem(key, job!.id)
    else window.localStorage.removeItem(key)
  }

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    Promise.all([getAcademicClass(headers, classId), getAcademicClassStudents(headers, classId, { search, learningStatus, page, pageSize: PAGE_SIZE }), getAcademicClassMappingSummary(headers, classId), getAcademicClassLearningSummary(headers, classId)])
      .then(([detail, studentPage, nextSummary, nextLearning]) => {
        if (cancelled) return
        setClassInfo(detail)
        setStudents(studentPage.items)
        setTotal(studentPage.total)
        setSummary(nextSummary)
        setLearningSummary(nextLearning)
      })
      .catch((error) => { if (!cancelled) setErrorModal(error instanceof Error ? error.message : 'Không tải được chi tiết lớp') })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [headers, classId, search, learningStatus, page])

  const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms))
  const waitForSyncJob = async (job: AcademicClassSyncJob): Promise<AcademicClassSyncJob> => {
    setActiveJob(job)
    setSyncJobs((items) => [job, ...items.filter((item) => item.id !== job.id)].slice(0, 10))
    rememberActiveJob(job)
    let current = job
    for (let attempt = 0; attempt < 240; attempt += 1) {
      if (!isJobActive(current)) {
        rememberActiveJob(null)
        await refreshSyncJobs().catch(() => [])
        return current
      }
      await sleep(1500)
      current = await getAcademicClassSyncJob(headers, classId, current.id)
      setActiveJob(current)
      setSyncJobs((items) => [current, ...items.filter((item) => item.id !== current.id)].slice(0, 10))
      rememberActiveJob(current)
    }
    throw new Error('Job đồng bộ đang chạy quá lâu. Vui lòng mở lại trang hoặc kiểm tra worker Celery.')
  }

  const followExistingJobIfAny = async () => {
    const jobs = await refreshSyncJobs()
    const running = jobs.find(isJobActive)
    if (!running) return false
    setMessage(`Đang có tiến trình ${jobTypeLabel(running.job_type)} chạy. Hệ thống sẽ tiếp tục theo dõi, không tạo job mới.`)
    const finished = await waitForSyncJob(running)
    if (finished.status === 'failed') throw new Error(finished.error_message || 'Job đồng bộ đang chạy thất bại')
    await refreshStudents()
    return true
  }

  useEffect(() => {
    let cancelled = false
    const recover = async () => {
      setRecoveringJob(true)
      try {
        const jobs = await getAcademicClassSyncJobs(headers, classId, 10)
        if (cancelled) return
        setSyncJobs(jobs)
        let running = jobs.find(isJobActive) || null
        if (!running && typeof window !== 'undefined') {
          const rememberedId = window.localStorage.getItem(`academic-class-sync-active-job:${classId}`)
          if (rememberedId) {
            try {
              const remembered = await getAcademicClassSyncJob(headers, classId, rememberedId)
              if (!cancelled && isJobActive(remembered)) running = remembered
              if (!isJobActive(remembered)) rememberActiveJob(null)
            } catch {
              rememberActiveJob(null)
            }
          }
        }
        if (running && !cancelled) {
          setMessage(`Khôi phục tiến trình ${jobTypeLabel(running.job_type)} đang chạy sau khi tải lại trang.`)
          const finished = await waitForSyncJob(running)
          if (!cancelled) {
            if (finished.status === 'failed') setErrorModal(finished.error_message || 'Job đồng bộ thất bại')
            else {
              setMessage(`${jobTypeLabel(finished.job_type)} hoàn tất.`)
              await refreshStudents()
            }
          }
        }
      } catch (error) {
        if (!cancelled) setErrorModal(error instanceof Error ? error.message : 'Không tải được tiến trình đồng bộ')
      } finally {
        if (!cancelled) setRecoveringJob(false)
      }
    }
    recover()
    return () => { cancelled = true }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [classId])

  const runFullCmsSync = async () => {
    setSyncingFullFlow(true)
    setMessage('')
    try {
      if (await followExistingJobIfAny()) return
      const queued = await enqueueAcademicClassFullCmsSyncJob(jsonHeaders, classId, { force: true, limit: 500, autoMapCourse: true, syncLearning: true })
      if (queued.job_type !== 'full_cms_sync') {
        setMessage(`Đang có tiến trình ${jobTypeLabel(queued.job_type)} chạy. Không tạo job mới để tránh đồng bộ trùng.`)
        await waitForSyncJob(queued)
        await refreshStudents()
        return
      }
      const finished = await waitForSyncJob(queued)
      if (finished.status === 'failed') throw new Error(finished.error_message || 'Đồng bộ full CMS thất bại')
      const result = finished.result_json as any
      const cmsUpdated = result?.cms_users?.updated || 0
      const cmsTotal = result?.cms_users?.total || 0
      const created = result?.counts?.cms_created_user || 0
      const mapped = result?.mapping?.openedx_course_id || result?.openedx_course_id || 'chưa map Course CMS'
      const enrolled = result?.enrollment?.updated || 0
      const enrolledTotal = result?.enrollment?.total || 0
      const learned = result?.learning?.updated || 0
      setMessage(`Đồng bộ full CMS hoàn tất: user CMS ${cmsUpdated}/${cmsTotal}, tạo mới ${created}, course ${mapped}, đã enroll ${enrolled}/${enrolledTotal}, đã lấy Course completion/điểm cho ${learned} sinh viên.`)
      await refreshStudents()
    } catch (error) {
      setErrorModal(error instanceof Error ? `${error.message}. Đồng bộ full CMS chỉ chạy đủ luồng sau khi lớp đã map được Course CMS; hãy map Course CMS rồi chạy lại.` : 'Đồng bộ full CMS thất bại')
    } finally {
      setSyncingFullFlow(false)
      setActiveJob(null)
    }
  }

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE))
  const counts = summary?.counts || {}
  const matched = counts.matched || 0
  const notChecked = counts.not_checked || 0
  const needsCmsAction = Math.max(0, (summary?.total || 0) - matched)
  const syncIssue = Math.max(0, (summary?.total || 0) - matched - notChecked)
  const activeJobRunning = isJobActive(activeJob)
  const actionBusy = activeJobRunning || syncingFullFlow || recoveringJob

  const componentColumns = useMemo(() => {
    const columns: Array<{ key: string; name: string }> = []
    const seen = new Set<string>()
    const push = (score?: AcademicLearningComponentScore | null) => {
      if (!score) return
      const key = componentKey(score)
      const name = componentDisplayName(score)
      const dedupeKey = (key || name).toLowerCase()
      if (!dedupeKey || seen.has(dedupeKey)) return
      seen.add(dedupeKey)
      columns.push({ key: key || name, name })
    }
    learningSummary?.component_summaries?.forEach(push)
    students.forEach((student) => student.learning_component_scores?.forEach(push))
    return columns.sort(gradeColumnCompare)
  }, [learningSummary, students])

  const studentComponentScore = (student: AcademicStudent, column: { key: string; name: string }) => {
    return student.learning_component_scores?.find((score) => componentKey(score) === column.key || score.name === column.name) || null
  }

  const subjectIdForBack = searchParams.get('subject_id') || classInfo?.subject_id || ''
  const subjectBackParams = new URLSearchParams()
  const backTermId = searchParams.get('term_id') || classInfo?.term_id || ''
  const backBranch = searchParams.get('branch') || classInfo?.branch || 'poly'
  const backCampus = searchParams.get('campus') || classInfo?.campus || ''
  const backTermName = searchParams.get('term_name') || classInfo?.term_name || ''
  const backSubjectCode = searchParams.get('subject_code') || classInfo?.subject_code || ''
  const backSubjectName = searchParams.get('subject_name') || classInfo?.subject_name || ''
  if (backTermId) subjectBackParams.set('term_id', backTermId)
  if (backBranch) subjectBackParams.set('branch', backBranch)
  if (backCampus) subjectBackParams.set('campus', backCampus)
  if (backTermName) subjectBackParams.set('term_name', backTermName)
  if (backSubjectCode) subjectBackParams.set('subject_code', backSubjectCode)
  if (backSubjectName) subjectBackParams.set('subject_name', backSubjectName)
  const backToClassesHref = subjectIdForBack ? `/student-management/subjects/${encodeURIComponent(subjectIdForBack)}/classes?${subjectBackParams.toString()}` : '/student-management'

  return <div className="page-stack student-management-page academic-flow-page class-detail-flow">
    <section className="card academic-unified-card">
      <div className="class-action-row compact-sync-action-strip">
        <div className="compact-sync-copy">
          <b>Đồng bộ CMS</b>
          <span>Một nút xử lý trọn luồng: tạo/kiểm tra user CMS, enroll Course CMS và lấy Course completion/điểm.</span>
        </div>
        <div className="toolbar-actions">
          <button className="btn primary" type="button" disabled={actionBusy} onClick={runFullCmsSync}>{syncingFullFlow ? 'Đang đồng bộ full CMS...' : 'Đồng bộ full CMS'}</button>
          <button className="btn secondary" type="button" disabled={loading || activeJobRunning} onClick={() => Promise.all([refreshStudents(), refreshSyncJobs()]).catch((error) => setErrorModal(error instanceof Error ? error.message : 'Không làm mới được dữ liệu'))}>Làm mới</button>
        </div>
      </div>
      {activeJob && <div className="sync-job-status persistent-sync-job-status">
        <div className="sync-job-main-row">
          <div>
            <b>{activeJob.progress_label || 'Đang xử lý job đồng bộ...'}</b>
            <small>{jobTypeLabel(activeJob.job_type)} · {jobStatusLabel(activeJob.status)} · Tiến độ: {activeJob.progress_current || 0}/{activeJob.progress_total || 100}</small>
          </div>
          <button className="btn secondary small" type="button" onClick={() => getAcademicClassSyncJob(headers, classId, activeJob.id).then((job) => { setActiveJob(job); setSyncJobs((items) => [job, ...items.filter((item) => item.id !== job.id)].slice(0, 10)) }).catch((error) => setErrorModal(error instanceof Error ? error.message : 'Không làm mới được tiến trình'))}>Làm mới tiến trình</button>
        </div>
        <div className="progress-track"><span style={{ width: `${jobProgressPercent(activeJob)}%` }} /></div>
        <small>Tiến trình được lưu trong database. F5 không làm mất trạng thái; khi còn job đang chạy, các nút đồng bộ sẽ bị khóa để tránh bấm nhiều lần.</small>
      </div>}
      {message && <p className="form-message">{message}</p>}

      <div className="academic-summary-strip class-summary-strip">
        <div><span>Tổng SV AP</span><b>{summary?.total ?? classInfo?.student_count ?? 0}</b><small>Trong lớp</small></div>
        <div><span>Đã đồng bộ CMS</span><b>{matched}</b><small>Cần xử lý: {needsCmsAction}</small></div>
        <div><span>Đã enroll</span><b>{learningSummary?.counts?.enrolled || 0}</b><small>Course: {learningSummary?.openedx_course_id || classInfo?.openedx_course_id || 'N/A'}</small></div>
        <div><span>Đã vào học</span><b>{learningSummary?.active_count || 0}</b><small>Có hoạt động CMS</small></div>
        <div><span>Course completion TB</span><b>{percentLabel(learningSummary?.avg_progress_percent)}</b><small>Dữ liệu từ CMS</small></div>
        <div><span>Điểm tổng TB</span><b>{grade10Label(learningSummary?.avg_grade_percent)}</b><small>{learningSummary?.last_synced_at ? `Cập nhật: ${formatVNDateTime(learningSummary.last_synced_at)}` : 'Chưa cập nhật'}</small></div>
      </div>

      <div className="academic-detail-grid compact-class-info">
        <div><span>Mã lớp</span><b>{classInfo?.class_code || '—'}</b></div>
        <div><span>Block</span><b>{classInfo?.block_name || '—'}</b></div>
        <div><span>Giảng viên</span><b>{classInfo?.teacher_name || classInfo?.teacher_username || '—'}</b></div>
        <div><span>Course CMS</span><b>{classInfo?.openedx_course_id || 'N/A'}</b><small>{mappingSourceLabel(classInfo?.openedx_mapping_source)}</small></div>
      </div>

      <div className="component-summary-inline">
        <b>Các đầu điểm CMS</b>
        {componentColumns.length ? componentColumns.slice(0, 8).map((column) => {
          const score = learningSummary?.component_summaries?.find((item) => componentKey(item) === column.key || item.name === column.name)
          return <span key={column.key}>{column.name}: <b>{componentScoreText(score)}</b></span>
        }) : <span>CMS/Open edX chưa trả Detailed grades cho course này. Bảng sinh viên sẽ hiển thị N/A ở phần đầu điểm.</span>}
      </div>
    </section>

    <section className="card academic-unified-card">
      <div className="section-head">
        <div><h2>Danh sách sinh viên</h2><p>Tiến độ học hiển thị Course completion và điểm tổng hệ 10. Các cột điểm được tạo động từ Detailed grades của Course CMS; mỗi course có bao nhiêu đầu điểm thì bảng tự mở bấy nhiêu cột.</p></div>
        <div className="toolbar-actions">
          <select className="input compact-input" value={learningStatus} onChange={(event) => { setLearningStatus(event.target.value); setPage(1) }}>
            <option value="all">Tất cả trạng thái</option>
            <option value="cms_not_synced">Chưa đồng bộ CMS</option>
            <option value="not_enrolled">Chưa enroll</option>
            <option value="no_activity">Chưa vào học</option>
            <option value="low_progress">Tiến độ thấp</option>
            <option value="low_grade">Điểm thấp</option>
            <option value="sync_error">Lỗi dữ liệu</option>
          </select>
          <input className="input compact-input" value={search} onChange={(event) => { setSearch(event.target.value); setPage(1) }} placeholder="Tìm mã SV, username, họ tên..." />
        </div>
      </div>
      <div className="table-wrap academic-table-wrap dynamic-grade-table-wrap">
        <table className="data-table academic-data-table student-grade-table">
          <thead><tr><th className="sticky-col">Sinh viên</th><th>Username</th><th>Email</th><th>Đồng bộ CMS</th><th>Đã enroll</th><th>Tiến độ học</th>{componentColumns.map((column) => <th key={column.key} className="component-grade-th">{column.name}</th>)}</tr></thead>
          <tbody>
            {loading && <tr><td colSpan={6 + componentColumns.length}>Đang tải sinh viên...</td></tr>}
            {!loading && !students.length && <tr><td colSpan={6 + componentColumns.length}>Không có sinh viên phù hợp.</td></tr>}
            {students.map((student) => <tr key={student.id}>
              <td className="main-entity-cell sticky-col"><b>{student.student_code || '—'}</b><small>{student.full_name}</small></td>
              <td className="username-combined-cell"><b>{student.username || 'N/A'}</b>{student.openedx_username && student.openedx_username !== student.username ? <small>CMS: {student.openedx_username}</small> : <small>AP/CMS</small>}</td>
              <td>{student.email || 'N/A'}</td>
              <td><span className={cmsSyncClass(student.match_status)}>{cmsSyncLabel(student.match_status)}</span><small>{student.last_resolved_at ? `Kiểm tra: ${formatVNDateTime(student.last_resolved_at)}` : ''}</small></td>
              <td><span className={enrollmentClass(student.learning_enrollment_status)}>{enrollmentLabel(student.learning_enrollment_status)}</span><small>{student.learning_enrollment_synced_at ? `Kiểm tra: ${formatVNDateTime(student.learning_enrollment_synced_at)}` : ''}</small></td>
              <td className="learning-progress-cell"><b>Course completion: {percentLabel(student.learning_progress_percent)}</b><small>Điểm tổng: {grade10Label(student.learning_grade_percent)}</small><span className={learningStatusClass(student.learning_status)}>{learningStatusLabel(student.learning_status)}</span>{student.learning_last_synced_at ? <small>Cập nhật: {formatVNDateTime(student.learning_last_synced_at)}</small> : null}</td>
              {componentColumns.map((column) => <td key={`${student.id}-${column.key}`} className="component-grade-cell"><b>{componentScoreText(studentComponentScore(student, column))}</b></td>)}
            </tr>)}
          </tbody>
        </table>
      </div>
      <div className="pagination-row">
        <button className="btn secondary small" disabled={page <= 1} onClick={() => setPage((value) => Math.max(1, value - 1))}>Trang trước</button>
        <span>{page} / {totalPages}</span>
        <button className="btn secondary small" disabled={page >= totalPages} onClick={() => setPage((value) => value + 1)}>Trang sau</button>
      </div>
    </section>
    {errorModal && <div className="modal-backdrop">
      <div className="card bank-modal academic-confirm-modal">
        <div className="section-head"><div><h2>Không thực hiện được thao tác</h2><p>{errorModal}</p></div></div>
        <div className="modal-actions"><button className="btn primary" type="button" onClick={() => setErrorModal('')}>Đã hiểu</button></div>
      </div>
    </div>}
  </div>
}

export default function ClassDetailPage() {
  return <Suspense fallback={<div className="card">Đang tải chi tiết lớp...</div>}><ClassDetailContent /></Suspense>
}
