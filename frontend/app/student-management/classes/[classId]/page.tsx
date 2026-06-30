'use client'

import Link from 'next/link'
import { Suspense, useEffect, useMemo, useRef, useState, type MouseEvent, type PointerEvent, type WheelEvent } from 'react'
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
  getAcademicClassAssignmentDefenseScores,
  saveAcademicClassAssignmentDefenseScores,
} from '../../../../lib/api'
import { AcademicAssignmentDefenseScore, AcademicClass, AcademicClassSyncJob, AcademicLearningComponentScore, AcademicLearningSummary, AcademicMappingSummary, AcademicStudent } from '../../../../types'
import { formatVNDate, formatVNDateTime, formatVNTimeDate } from '../../../../lib/time'
import { useDebouncedValue } from '../../../../lib/useDebouncedValue'

const PAGE_SIZE = 50

type GradeColumn = { key: string; name: string; quizNumber?: number | null; deadlineDate?: string | null; availableFrom?: string | null; deadlineMode?: string | null; scheduleWarning?: string | null }

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
function learningStatusSentence(value?: string | null) {
  const label = learningStatusLabel(value)
  return label.endsWith('.') ? label : `${label}.`
}
function latestTimestamp(values: Array<string | null | undefined>) {
  let selected: string | null = null
  let selectedTime = 0
  values.forEach((value) => {
    if (!value) return
    const time = new Date(value).getTime()
    if (!Number.isFinite(time)) return
    if (!selected || time > selectedTime) {
      selected = value
      selectedTime = time
    }
  })
  return selected
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

function formatDateOnly(value?: string | null) {
  if (!value) return 'N/A'
  const formatted = formatVNDate(value)
  return formatted === '—' ? 'N/A' : formatted
}
function quizNumbersFromText(value?: string | null) {
  const text = String(value || '').toLowerCase()
  const numbers: number[] = []
  const patterns = [/quiz\s*#?\s*(\d{1,3})/gi, /learning\s*check\s*#?\s*(\d{1,3})/gi, /\blc\s*#?\s*(\d{1,3})/gi]
  patterns.forEach((pattern) => {
    let match: RegExpExecArray | null
    while ((match = pattern.exec(text)) !== null) {
      const number = Number(match[1])
      if (number > 0 && number <= 200 && !numbers.includes(number)) numbers.push(number)
    }
  })
  return numbers.sort((a, b) => a - b)
}
function quizNumber(score?: AcademicLearningComponentScore | null) {
  if (!score) return null
  if (typeof score.quiz_number === 'number' && score.quiz_number > 0) return score.quiz_number
  // Only parse human-facing labels. Do not parse storage keys like
  // `block@quiz-14-...`, otherwise a random usage key can create a phantom `Quiz 14` column.
  const fromText = quizNumbersFromText(`${score.name || ''} ${(score as any).label || ''} ${(score as any).display_name || ''} ${(score as any).title || ''}`)
  return fromText[0] || null
}
function gradeColumnIdentity(score: AcademicLearningComponentScore) {
  const number = quizNumber(score)
  if (number) return `quiz:${number}`
  return String(score.key || score.name || '').trim().toLowerCase().replace(/[^a-z0-9]+/gi, '')
}
function gradeColumnCompare(left: { key: string; name: string; quizNumber?: number | null }, right: { key: string; name: string; quizNumber?: number | null }) {
  const leftQuiz = left.quizNumber || quizNumbersFromText(left.name)[0] || null
  const rightQuiz = right.quizNumber || quizNumbersFromText(right.name)[0] || null
  if (leftQuiz && rightQuiz) return leftQuiz - rightQuiz
  if (leftQuiz) return -1
  if (rightQuiz) return 1
  return left.name.localeCompare(right.name, 'vi', { numeric: true, sensitivity: 'base' })
}
function quizStatusLabel(score?: AcademicLearningComponentScore | null) {
  const status = String(score?.quiz_status || '').toLowerCase()
  if (status === 'early_before_start') return 'Làm trước thời gian học'
  if (status === 'late') return 'Quá hạn'
  if (status === 'late_not_100') return 'Quá hạn / chưa đạt 100%'
  if (status === 'not_100') return 'Chưa đạt 100%'
  if (status === 'not_attempted') return 'Chưa làm'
  if (status === 'on_time') return 'Đúng hạn'
  if (!score || score.percent == null) return 'Chưa làm'
  return 'Đã có điểm'
}
function quizStatusClass(score?: AcademicLearningComponentScore | null) {
  const status = String(score?.quiz_status || '').toLowerCase()
  if (status === 'on_time') return 'quiz-status-badge success'
  if (status === 'early_before_start') return 'quiz-status-badge warning'
  if (['late', 'late_not_100'].includes(status)) return 'quiz-status-badge danger'
  if (['not_100', 'not_attempted'].includes(status)) return 'quiz-status-badge neutral'
  return 'quiz-status-badge neutral'
}
function componentDeadlineLabel(column: { deadlineDate?: string | null; deadlineMode?: string | null }) {
  if (column.deadlineMode === 'manual_required') return 'Cần chỉnh deadline tay'
  if (!column.deadlineDate) return 'Deadline: N/A'
  return `Deadline: ${formatDateOnly(column.deadlineDate)}`
}

function examStatusClass(value?: string | null) {
  const status = String(value || '').toLowerCase()
  if (status === 'eligible') return 'status-pill success'
  if (status === 'not_eligible') return 'status-pill danger'
  return 'status-pill warning'
}
function examStatusLabel(student: AcademicStudent) {
  return student.exam_status_label || (student.exam_status === 'eligible' ? 'Được thi' : student.exam_status === 'not_eligible' ? 'Không được thi' : 'Chưa đủ dữ liệu')
}
function defenseStatusLabel(value?: string | null) {
  const status = String(value || 'not_graded').toLowerCase()
  if (status === 'graded') return 'Đã chấm'
  if (status === 'waiting_defense') return 'Chờ bảo vệ'
  if (status === 'submitted') return 'Đã nộp'
  if (status === 'absent') return 'Vắng bảo vệ'
  if (status === 'needs_regrade') return 'Cần chấm lại'
  return 'Chưa có điểm'
}

function ClassDetailContent() {
  const params = useParams<{ classId: string }>()
  const searchParams = useSearchParams()
  const classId = decodeURIComponent(String(params.classId || ''))
  const { authHeaders, can } = useAppContext()
  const headers = useMemo(() => authHeaders(), [authHeaders])
  const jsonHeaders = useMemo(() => authHeaders(true), [authHeaders])
  const canRunFullCmsSync = can('manage_training_deadlines') || can('manage_settings')
  const canManageAssignmentScores = can('manage_assignment_scores') || can('manage_settings')
  const [classInfo, setClassInfo] = useState<AcademicClass | null>(null)
  const [students, setStudents] = useState<AcademicStudent[]>([])
  const [summary, setSummary] = useState<AcademicMappingSummary | null>(null)
  const [learningSummary, setLearningSummary] = useState<AcademicLearningSummary | null>(null)
  const [search, setSearch] = useState('')
  const debouncedSearch = useDebouncedValue(search, 350)
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
  const [selectedQuiz, setSelectedQuiz] = useState<{ student: AcademicStudent; column: GradeColumn; score: AcademicLearningComponentScore | null } | null>(null)
  const [assignmentModalOpen, setAssignmentModalOpen] = useState(false)
  const [assignmentRows, setAssignmentRows] = useState<AcademicAssignmentDefenseScore[]>([])
  const [savingPolicy, setSavingPolicy] = useState(false)
  const tableScrollRef = useRef<HTMLDivElement | null>(null)
  const studentTableRef = useRef<HTMLTableElement | null>(null)
  const studentTableDragRef = useRef({ active: false, startX: 0, scrollLeft: 0, moved: false, pointerId: -1 })
  const suppressStudentTableClickRef = useRef(false)
  const [studentTableDragging, setStudentTableDragging] = useState(false)

  const refreshStudents = async () => {
    const [studentPage, nextSummary, nextLearning] = await Promise.all([
      getAcademicClassStudents(headers, classId, { search: debouncedSearch, learningStatus, page, pageSize: PAGE_SIZE }),
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
    Promise.all([getAcademicClass(headers, classId), getAcademicClassStudents(headers, classId, { search: debouncedSearch, learningStatus, page, pageSize: PAGE_SIZE }), getAcademicClassMappingSummary(headers, classId), getAcademicClassLearningSummary(headers, classId)])
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
  }, [headers, classId, debouncedSearch, learningStatus, page])

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


  const openAssignmentModal = async () => {
    if (!canManageAssignmentScores) return
    try {
      const rows = await getAcademicClassAssignmentDefenseScores(headers, classId, classInfo?.openedx_course_id)
      setAssignmentRows(rows)
      setAssignmentModalOpen(true)
    } catch (error) {
      setErrorModal(error instanceof Error ? error.message : 'Không tải được điểm bảo vệ Assignment')
    }
  }

  const saveAssignmentRows = async () => {
    if (!canManageAssignmentScores) return
    setSavingPolicy(true)
    try {
      await saveAcademicClassAssignmentDefenseScores(jsonHeaders, classId, assignmentRows)
      setAssignmentModalOpen(false)
      await refreshStudents()
      setMessage('Đã lưu điểm bảo vệ Assignment. Điều kiện thi sẽ được tính lại.')
    } catch (error) {
      setErrorModal(error instanceof Error ? error.message : 'Không lưu được điểm bảo vệ Assignment')
    } finally {
      setSavingPolicy(false)
    }
  }

  const runFullCmsSync = async () => {
    if (!canRunFullCmsSync) return
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

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== 'Escape') return
      if (selectedQuiz) setSelectedQuiz(null)
      else if (assignmentModalOpen) setAssignmentModalOpen(false)
      else if (errorModal) setErrorModal('')
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [selectedQuiz, assignmentModalOpen, errorModal])

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE))
  const counts = summary?.counts || {}
  const matched = counts.matched || 0
  const notChecked = counts.not_checked || 0
  const needsCmsAction = Math.max(0, (summary?.total || 0) - matched)
  const syncIssue = Math.max(0, (summary?.total || 0) - matched - notChecked)
  const activeJobRunning = isJobActive(activeJob)
  const actionBusy = activeJobRunning || syncingFullFlow || recoveringJob

  const componentColumns = useMemo<GradeColumn[]>(() => {
    const sourceScores: AcademicLearningComponentScore[] = []
    if (learningSummary?.component_summaries?.length) {
      sourceScores.push(...learningSummary.component_summaries)
    } else {
      students.forEach((student) => student.learning_component_scores?.forEach((score) => sourceScores.push(score)))
    }
    const byIdentity = new Map<string, GradeColumn>()
    sourceScores.forEach((score) => {
      const identity = gradeColumnIdentity(score)
      if (!identity) return
      const number = quizNumber(score)
      const existing = byIdentity.get(identity)
      const next: GradeColumn = {
        key: identity,
        name: number ? `Quiz ${number}` : componentDisplayName(score),
        quizNumber: number,
        deadlineDate: score.deadline_date || existing?.deadlineDate || null,
        availableFrom: score.available_from || existing?.availableFrom || null,
        deadlineMode: score.deadline_mode || existing?.deadlineMode || null,
        scheduleWarning: score.schedule_warning || existing?.scheduleWarning || null,
      }
      byIdentity.set(identity, existing ? { ...existing, ...next, deadlineDate: next.deadlineDate || existing.deadlineDate, availableFrom: next.availableFrom || existing.availableFrom } : next)
    })
    return Array.from(byIdentity.values()).sort(gradeColumnCompare)
  }, [learningSummary, students])



  const studentListUpdatedAt = useMemo(() => latestTimestamp([
    learningSummary?.last_synced_at,
    ...students.map((student) => student.learning_last_synced_at),
  ]), [learningSummary?.last_synced_at, students])

  const handleStudentTableWheel = (event: WheelEvent<HTMLDivElement>) => {
    const container = tableScrollRef.current
    if (!container) return
    const hasHorizontalOverflow = container.scrollWidth > container.clientWidth + 2
    if (!hasHorizontalOverflow) return
    const shouldScrollHorizontal = event.shiftKey || Math.abs(event.deltaX) > Math.abs(event.deltaY)
    if (!shouldScrollHorizontal) return
    const delta = event.shiftKey ? event.deltaY : event.deltaX
    if (!delta) return
    container.scrollLeft += delta
    event.preventDefault()
  }

  const startStudentTableDrag = (event: PointerEvent<HTMLDivElement>) => {
    const container = tableScrollRef.current
    if (!container || container.scrollWidth <= container.clientWidth + 2) return
    if (event.pointerType === 'mouse' && event.button !== 0) return
    studentTableDragRef.current = { active: true, startX: event.clientX, scrollLeft: container.scrollLeft, moved: false, pointerId: event.pointerId }
    try { container.setPointerCapture(event.pointerId) } catch {}
  }

  const moveStudentTableDrag = (event: PointerEvent<HTMLDivElement>) => {
    const state = studentTableDragRef.current
    const container = tableScrollRef.current
    if (!state.active || !container) return
    const deltaX = event.clientX - state.startX
    if (Math.abs(deltaX) > 3) {
      state.moved = true
      setStudentTableDragging(true)
      container.scrollLeft = state.scrollLeft - deltaX
      event.preventDefault()
    }
  }

  const endStudentTableDrag = (event: PointerEvent<HTMLDivElement>) => {
    const state = studentTableDragRef.current
    const container = tableScrollRef.current
    if (!state.active) return
    if (state.moved) {
      suppressStudentTableClickRef.current = true
      window.setTimeout(() => { suppressStudentTableClickRef.current = false }, 80)
    }
    state.active = false
    setStudentTableDragging(false)
    try { container?.releasePointerCapture(event.pointerId) } catch {}
  }

  const suppressStudentTableClickAfterDrag = (event: MouseEvent<HTMLDivElement>) => {
    if (!suppressStudentTableClickRef.current) return
    event.preventDefault()
    event.stopPropagation()
  }

  const studentComponentScore = (student: AcademicStudent, column: GradeColumn) => {
    return student.learning_component_scores?.find((score) => gradeColumnIdentity(score) === column.key || componentKey(score) === column.key || score.name === column.name) || null
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
          <Link className="btn secondary" href="/semesters">Cấu hình tuần học</Link>
          <button className="btn secondary" type="button" onClick={openAssignmentModal}>Nhập điểm Assignment</button>
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
          const score = learningSummary?.component_summaries?.find((item) => gradeColumnIdentity(item) === column.key || componentKey(item) === column.key || item.name === column.name)
          return <span key={column.key}>{column.name}: <b>{componentScoreText(score)}</b></span>
        }) : <span>CMS/Open edX chưa trả Detailed grades cho course này. Bảng sinh viên sẽ hiển thị N/A ở phần đầu điểm.</span>}
      </div>
    </section>

    <section className="card academic-unified-card student-list-card">
      <div className="section-head">
        <div><h2>Danh sách sinh viên</h2><p>{studentListUpdatedAt ? `Cập nhật: ${formatVNTimeDate(studentListUpdatedAt)}` : 'Cập nhật: chưa có dữ liệu đồng bộ học tập'}</p></div>
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
      <div className="class-student-table-shell">
        <div className="student-table-scroll-hint">Kéo ngang trực tiếp trong bảng, dùng touchpad, hoặc giữ Shift và lăn chuột để xem các cột Quiz. Chỉ bảng sinh viên cuộn ngang, các thẻ khác giữ nguyên.</div>
        <div
          className={`table-wrap academic-table-wrap dynamic-grade-table-wrap class-student-table-scroll${studentTableDragging ? ' is-dragging' : ''}`}
          ref={tableScrollRef}
          onWheel={handleStudentTableWheel}
          onPointerDown={startStudentTableDrag}
          onPointerMove={moveStudentTableDrag}
          onPointerUp={endStudentTableDrag}
          onPointerCancel={endStudentTableDrag}
          onClickCapture={suppressStudentTableClickAfterDrag}
        >
        <table className="data-table academic-data-table student-grade-table" ref={studentTableRef}>
          <thead><tr><th className="sticky-col">Sinh viên</th><th>Username</th><th>Email</th><th>Số lần học lại</th><th>Đồng bộ CMS</th><th>Đã enroll</th><th>Tiến độ học</th><th>Điều kiện thi</th>{componentColumns.map((column) => <th key={column.key} className="component-grade-th"><span>{column.name}</span><small>{componentDeadlineLabel(column)}</small></th>)}</tr></thead>
          <tbody>
            {loading && <tr><td colSpan={8 + componentColumns.length}>Đang tải sinh viên...</td></tr>}
            {!loading && !students.length && <tr><td colSpan={8 + componentColumns.length}>Không có sinh viên phù hợp.</td></tr>}
            {students.map((student) => <tr key={student.id}>
              <td className="main-entity-cell sticky-col"><b>{student.student_code || '—'}</b><small>{student.full_name}</small></td>
              <td className="username-combined-cell"><b>{student.username || 'N/A'}</b>{student.openedx_username && student.openedx_username !== student.username ? <small>CMS: {student.openedx_username}</small> : <small>AP/CMS</small>}</td>
              <td>{student.email || 'N/A'}</td>
              <td className="relearn-count-cell"><b>{student.total_relearn || 0}</b><small>Số lần học lại</small></td>
              <td><span className={cmsSyncClass(student.match_status)}>{cmsSyncLabel(student.match_status)}</span><small>{student.last_resolved_at ? `Kiểm tra: ${formatVNDateTime(student.last_resolved_at)}` : ''}</small></td>
              <td><span className={enrollmentClass(student.learning_enrollment_status)}>{enrollmentLabel(student.learning_enrollment_status)}</span><small>{student.learning_enrollment_synced_at ? `Kiểm tra: ${formatVNDateTime(student.learning_enrollment_synced_at)}` : ''}</small></td>
              <td className="learning-progress-cell"><b>Hoàn thành khóa học: {percentLabel(student.learning_progress_percent)}</b><small>Điểm tổng: {grade10Label(student.learning_grade_percent)}</small><span className={learningStatusClass(student.learning_status)}>{learningStatusSentence(student.learning_status)}</span></td>
              <td className="exam-policy-cell"><span className={examStatusClass(student.exam_status)}>{examStatusLabel(student)}</span><small>{student.exam_reasons?.slice(0, 2).join('; ') || 'Final test chưa áp dụng rule'}</small><small>Assignment: {defenseStatusLabel(student.assignment_defense_status)}{typeof student.assignment_score_10 === 'number' ? ` · ${student.assignment_score_10}/10` : ''}</small></td>
              {componentColumns.map((column) => {
                const score = studentComponentScore(student, column)
                return <td key={`${student.id}-${column.key}`} className="component-grade-cell">
                  <button className="quiz-grade-cell-button" type="button" onClick={() => setSelectedQuiz({ student, column, score })}>
                    <b>{componentScoreText(score)}</b>
                    <span className={quizStatusClass(score)}>{quizStatusLabel(score)}</span>
                  </button>
                </td>
              })}
            </tr>)}
          </tbody>
        </table>
        </div>
      </div>
      <div className="pagination-row">
        <button className="btn secondary small" disabled={page <= 1} onClick={() => setPage((value) => Math.max(1, value - 1))}>Trang trước</button>
        <span>{page} / {totalPages}</span>
        <button className="btn secondary small" disabled={page >= totalPages} onClick={() => setPage((value) => value + 1)}>Trang sau</button>
      </div>
    </section>


    {canManageAssignmentScores && assignmentModalOpen && <div className="modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) setAssignmentModalOpen(false) }}>
      <div className="card bank-modal academic-confirm-modal wide-policy-modal" role="dialog" aria-modal="true" aria-labelledby="assignment-modal-title">
        <div className="section-head"><div><h2 id="assignment-modal-title">Nhập điểm bảo vệ Assignment</h2><p>Điểm này là điểm chính thức sau buổi bảo vệ; điểm Assignment từ CMS chỉ dùng tham khảo.</p></div></div>
        <div className="policy-edit-table-wrap"><table className="data-table compact-table"><thead><tr><th>Sinh viên</th><th>Trạng thái</th><th>Điểm /10</th><th>Ghi chú</th></tr></thead><tbody>
          {assignmentRows.map((row, index) => <tr key={row.student_id}><td><b>{row.student_code || row.student_username}</b><small>{row.student_name}</small></td><td><select value={row.defense_status || 'not_graded'} onChange={(event) => setAssignmentRows((items) => items.map((item, idx) => idx === index ? { ...item, defense_status: event.target.value } : item))}><option value="not_graded">Chưa có điểm</option><option value="submitted">Đã nộp</option><option value="waiting_defense">Chờ bảo vệ</option><option value="graded">Đã chấm</option><option value="absent">Vắng bảo vệ</option><option value="needs_regrade">Cần chấm lại</option></select></td><td><input type="number" min="0" max="10" step="0.1" value={row.score_10 ?? ''} onChange={(event) => setAssignmentRows((items) => items.map((item, idx) => idx === index ? { ...item, score_10: event.target.value === '' ? null : Number(event.target.value), course_id: classInfo?.openedx_course_id || item.course_id || null, assignment_key: item.assignment_key || 'assignment', assignment_label: item.assignment_label || 'Assignment' } : item))} /></td><td><input value={row.note || ''} onChange={(event) => setAssignmentRows((items) => items.map((item, idx) => idx === index ? { ...item, note: event.target.value } : item))} /></td></tr>)}
        </tbody></table></div>
        <div className="modal-actions"><button className="btn secondary" onClick={() => setAssignmentModalOpen(false)}>Đóng</button><button className="btn primary" disabled={savingPolicy} onClick={saveAssignmentRows}>{savingPolicy ? 'Đang lưu...' : 'Lưu điểm Assignment'}</button></div>
      </div>
    </div>}

    {selectedQuiz && <div className="modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) setSelectedQuiz(null) }}>
      <div className="card bank-modal academic-confirm-modal quiz-detail-modal" role="dialog" aria-modal="true" aria-labelledby="quiz-detail-modal-title">
        <div className="section-head">
          <div>
            <h2 id="quiz-detail-modal-title">{selectedQuiz.column.name}</h2>
            <p>{selectedQuiz.student.student_code || selectedQuiz.student.username} · {selectedQuiz.student.full_name}</p>
          </div>
        </div>
        <div className="quiz-detail-grid">
          <div><span>Điểm</span><b>{componentScoreText(selectedQuiz.score)}</b></div>
          <div><span>Trạng thái</span><b>{quizStatusLabel(selectedQuiz.score)}</b></div>
          <div><span>Thời gian bắt đầu hợp lệ</span><b>{formatDateOnly(selectedQuiz.score?.available_from || selectedQuiz.column.availableFrom)}</b></div>
          <div><span>Deadline</span><b>{formatDateOnly(selectedQuiz.score?.deadline_date || selectedQuiz.column.deadlineDate)}</b></div>
          <div><span>Ngày làm/nộp</span><b>{formatDateOnly(selectedQuiz.score?.submitted_at)}</b></div>
          <div><span>Nguồn dữ liệu</span><b>{selectedQuiz.score?.source || 'CMS/Open edX'}</b></div>
        </div>
        {(selectedQuiz.score?.schedule_warning || selectedQuiz.column.scheduleWarning) && <p className="form-message warning-message">{selectedQuiz.score?.schedule_warning || selectedQuiz.column.scheduleWarning}</p>}
        <div className="modal-actions"><button className="btn primary" type="button" onClick={() => setSelectedQuiz(null)}>Đóng</button></div>
      </div>
    </div>}
    {errorModal && <div className="modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) setErrorModal('') }}>
      <div className="card bank-modal academic-confirm-modal" role="dialog" aria-modal="true" aria-labelledby="error-modal-title">
        <div className="section-head"><div><h2 id="error-modal-title">Không thực hiện được thao tác</h2><p>{errorModal}</p></div></div>
        <div className="modal-actions"><button className="btn primary" type="button" onClick={() => setErrorModal('')}>Đã hiểu</button></div>
      </div>
    </div>}
  </div>
}

export default function ClassDetailPage() {
  return <Suspense fallback={<div className="card">Đang tải chi tiết lớp...</div>}><ClassDetailContent /></Suspense>
}
