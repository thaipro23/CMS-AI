'use client'

import Link from 'next/link'
import { Suspense, useEffect, useMemo, useState } from 'react'
import { useParams, useSearchParams } from 'next/navigation'
import { useAppContext } from '../../../../context/AppContext'
import {
  getAcademicClass,
  getAcademicClassMappingSummary,
  getAcademicClassLearningSummary,
  getAcademicClassProgressEmailPreview,
  getAcademicClassStudents,
  getAcademicClassAssignmentDefenseScores,
  enqueueAcademicClassFullCmsSyncJob,
  enqueueAcademicClassLearningSyncJob,
  getAcademicClassSyncJob,
  getAcademicClassSyncJobs,
  enqueueAcademicClassProgressEmailJob,
  getAcademicBulkOperationJob,
  getAcademicBulkOperationJobs,
  createAcademicTrainingClassExportJob,
  getAcademicTrainingTeacherReportJob,
  getAcademicTrainingTeacherReportJobs,
  downloadAcademicTrainingTeacherReportJob,
  getAnalyticsClassLearningBehaviorSummary,
  getAnalyticsClassLearningBehavior,
  enqueueAnalyticsClassLearningBehaviorJob,
  getAnalyticsStudentLearningBehaviorDetail,
} from '../../../../lib/api'
import { AcademicAssignmentDefenseScore, AcademicBulkOperationJob, AcademicClass, AcademicClassSyncJob, AcademicProgressEmailPreview, AcademicTeacherReportJob, AcademicLearningComponentScore, AcademicLearningSummary, AcademicMappingSummary, AcademicStudent, AnalyticsLearningBehaviorRow, AnalyticsLearningBehaviorSummary, AnalyticsStudentLearningBehaviorDetail, AnalyticsStudentSessionProgress } from '../../../../types'
import { formatVNDate, formatVNDateTime, formatVNTimeDate } from '../../../../lib/time'
import { useDebouncedValue } from '../../../../lib/useDebouncedValue'
import { SHOW_DIAGNOSTICS_UI } from '../../../../lib/runtime'
import { PageRoot } from '../../../../components/layout/PageHeader'
import { EnterpriseScreenHeader } from '../../../../components/layout/EnterpriseDesignContract'
import { TrainingContextChips, TrainingKpiStrip, TrainingMappingEmptyState } from '../../../../components/training/TrainingWorkspace'
import { AccessibleDialog } from '../../../../components/ui/AccessibleDialog'
import { InlineNotice, noticeInfo } from '../../../../components/ui/InlineNotice'
import { EnterpriseDataTable, type EnterpriseTableColumn } from '../../../../components/table/EnterpriseDataTable'
import { VisualIcon } from '../../../../components/ui/VisualIcon'
import { AppIcon } from '../../../../components/icons/AppIcon'
import { UdemyClassProgressPanel } from '../../../../components/student-management/UdemyClassProgressPanel'


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
  return 'Chưa ghép'
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
  if (status === 'inactive') return 'Ghi danh inactive'
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

function shouldSuggestFullCmsSync(student: AcademicStudent) {
  const match = String(student.match_status || 'not_checked').toLowerCase()
  const enrollment = String(student.learning_enrollment_status || 'unknown').toLowerCase()
  const learning = String(student.learning_status || 'not_synced').toLowerCase()
  return match !== 'matched' || enrollment !== 'enrolled' || ['cms_not_synced', 'not_synced', 'not_enrolled', 'sync_error'].includes(learning)
}

function safeBehaviorLabel(row?: AnalyticsLearningBehaviorRow | null) {
  const classification = String(row?.classification || '').toUpperCase()
  if (classification === 'LIKELY_REAL_LEARNING') return 'Có dấu hiệu học thật'
  if (classification === 'POSSIBLE_IDLE') return 'Có khả năng treo máy'
  if ((classification === 'POSSIBLE_ANOMALY' || classification === 'POSSIBLE_CHEATING')) return 'Dấu hiệu bất thường cần kiểm tra'
  if (classification === 'NORMAL') return 'Chưa thấy bất thường rõ'
  return 'Chưa đủ dữ liệu'
}
function behaviorStatusClass(row?: AnalyticsLearningBehaviorRow | null) {
  const classification = String(row?.classification || '').toUpperCase()
  if (classification === 'LIKELY_REAL_LEARNING') return 'status-pill success'
  if (classification === 'POSSIBLE_IDLE') return 'status-pill warning'
  if ((classification === 'POSSIBLE_ANOMALY' || classification === 'POSSIBLE_CHEATING')) return 'status-pill danger'
  if (classification === 'NORMAL') return 'status-pill neutral'
  return 'status-pill neutral'
}
function recommendedActionLabel(value?: string | null) {
  const action = String(value || '').toUpperCase()
  if (action === 'NO_ACTION') return 'Không cần xử lý'
  if (action === 'REMIND_STUDENT') return 'Nhắc sinh viên'
  if (action === 'TEACHER_REVIEW') return 'Giáo viên xem lại'
  if (action === 'CHECK_WITH_STUDENT') return 'Trao đổi thêm'
  if (action === 'REQUIRE_ADDITIONAL_ACTIVITY') return 'Yêu cầu học bổ sung'
  return 'Kiểm tra lại sau'
}
function compactDuration(seconds?: number | null) {
  if (typeof seconds !== 'number' || Number.isNaN(seconds) || seconds <= 0) return 'N/A'
  const minutes = Math.round(seconds / 60)
  if (minutes < 60) return `${minutes} phút`
  const hours = Math.floor(minutes / 60)
  const remain = minutes % 60
  return remain ? `${hours} giờ ${remain} phút` : `${hours} giờ`
}

function sessionStatusLabel(value?: string | null) {
  const status = String(value || '').toUpperCase()
  if (status === 'LIKELY_COMPLETED') return 'Có dấu hiệu học thật'
  if (status === 'COMPLETED_LATE') return 'Hoàn thành muộn'
  if (status === 'POSSIBLE_IDLE') return 'Có khả năng treo máy'
  if (status === 'POSSIBLE_SUSPICIOUS') return 'Dấu hiệu bất thường cần kiểm tra'
  if (status === 'IN_PROGRESS') return 'Đang học'
  if (status === 'NOT_STARTED') return 'Chưa học'
  return 'Chưa đủ dữ liệu'
}
function sessionStatusClass(value?: string | null) {
  const status = String(value || '').toUpperCase()
  if (status === 'LIKELY_COMPLETED') return 'status-pill success'
  if (status === 'COMPLETED_LATE') return 'status-pill warning'
  if (status === 'POSSIBLE_SUSPICIOUS') return 'status-pill danger'
  if (status === 'POSSIBLE_IDLE') return 'status-pill warning'
  return 'status-pill neutral'
}
function deadlineSourceLabel(value?: string | null) {
  const source = String(value || '').toUpperCase()
  if (source === 'QUIZ_DEADLINE' || source === 'QUIZ_DEADLINE_CONFIGURED') return 'Mốc tiến độ Quiz'
  if (source === 'SEMESTER_WEEK_CONFIG') return 'Tuần học'
  if (source === 'MANUAL') return 'Cấu hình tay'
  if (source === 'INFERRED') return 'Suy luận 6 tuần'
  return source || 'N/A'
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
  if (column.deadlineMode === 'manual_required') return 'Cần chỉnh mốc tiến độ'
  if (!column.deadlineDate) return 'Mốc tiến độ: N/A'
  return `Mốc tiến độ: ${formatDateOnly(column.deadlineDate)}`
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
function defenseStatusClass(value?: string | null) {
  const status = String(value || 'not_graded').toLowerCase()
  if (status === 'graded') return 'status-pill success'
  if (status === 'waiting_defense') return 'status-pill warning'
  if (status === 'submitted') return 'status-pill neutral'
  if (['absent', 'needs_regrade'].includes(status)) return 'status-pill danger'
  return 'status-pill neutral'
}

function progressEmailIssueLabel(value?: string | null) {
  if (value === 'missing_email') return 'Thiếu email'
  if (value === 'inactive_student') return 'Sinh viên inactive'
  if (value === 'duplicate_email') return 'Trùng email'
  if (value === 'stale_after_refresh') return 'Dữ liệu CMS chưa mới'
  return value ? 'Không thể gửi' : 'Sẵn sàng gửi'
}
const DEFENSE_STATUS_OPTIONS = [
  { value: 'not_graded', label: 'Chưa có điểm' },
  { value: 'submitted', label: 'Đã nộp' },
  { value: 'waiting_defense', label: 'Chờ bảo vệ' },
  { value: 'graded', label: 'Đã chấm' },
  { value: 'absent', label: 'Vắng bảo vệ' },
  { value: 'needs_regrade', label: 'Cần chấm lại' },
]

function ClassDetailContent() {
  const params = useParams<{ classId: string }>()
  const searchParams = useSearchParams()
  const classId = decodeURIComponent(String(params.classId || ''))
  const { authHeaders, can } = useAppContext()
  const headers = useMemo(() => authHeaders(), [authHeaders])
  const jsonHeaders = useMemo(() => authHeaders(true), [authHeaders])
  const canRunFullCmsSync = can('manage_training_deadlines') || can('manage_settings')
  const canSendProgressEmail = can('view_training_reports') || can('manage_training_deadlines') || can('manage_settings')
  const canManageAssignmentScores = false // v25.9.16.7.2.64.13: Assignment score entry is handled by an external system.
  const [classInfo, setClassInfo] = useState<AcademicClass | null>(null)
  const [students, setStudents] = useState<AcademicStudent[]>([])
  const [summary, setSummary] = useState<AcademicMappingSummary | null>(null)
  const [learningSummary, setLearningSummary] = useState<AcademicLearningSummary | null>(null)
  const [search, setSearch] = useState('')
  const debouncedSearch = useDebouncedValue(search, 350)
  const [learningStatus, setLearningStatus] = useState('all')
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(50)
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(false)
  const [syncingFullFlow, setSyncingFullFlow] = useState(false)
  const [syncingScoreUpdate, setSyncingScoreUpdate] = useState(false)
  const [message, setMessage] = useState('')
  const [errorModal, setErrorModal] = useState('')
  const [activeJob, setActiveJob] = useState<AcademicClassSyncJob | null>(null)
  const [syncJobs, setSyncJobs] = useState<AcademicClassSyncJob[]>([])
  const [classExportJob, setClassExportJob] = useState<AcademicTeacherReportJob | null>(null)
  const [exportingClass, setExportingClass] = useState(false)
  const [recoveringJob, setRecoveringJob] = useState(false)
  const [progressEmailOpen, setProgressEmailOpen] = useState(false)
  const [progressEmailLoading, setProgressEmailLoading] = useState(false)
  const [progressEmailSubmitting, setProgressEmailSubmitting] = useState(false)
  const [progressEmailPreview, setProgressEmailPreview] = useState<AcademicProgressEmailPreview | null>(null)
  const [progressEmailSelected, setProgressEmailSelected] = useState<Set<string>>(new Set())
  const [progressEmailSubject, setProgressEmailSubject] = useState('')
  const [progressEmailBody, setProgressEmailBody] = useState('')
  const [progressEmailJob, setProgressEmailJob] = useState<AcademicBulkOperationJob | null>(null)
  const [selectedQuiz, setSelectedQuiz] = useState<{ student: AcademicStudent; column: GradeColumn; score: AcademicLearningComponentScore | null } | null>(null)
  const [assignmentModalOpen, setAssignmentModalOpen] = useState(false)
  const [assignmentRows, setAssignmentRows] = useState<AcademicAssignmentDefenseScore[]>([])
  const [assignmentStatusFilter, setAssignmentStatusFilter] = useState('all')
  const [assignmentBulkStatus, setAssignmentBulkStatus] = useState('waiting_defense')
  const [savingPolicy, setSavingPolicy] = useState(false)
  const [onlineSummary, setOnlineSummary] = useState<AnalyticsLearningBehaviorSummary | null>(null)
  const [onlineRows, setOnlineRows] = useState<AnalyticsLearningBehaviorRow[]>([])
  const [onlineLoading, setOnlineLoading] = useState(false)
  const [onlineRecalculating, setOnlineRecalculating] = useState(false)
  const [onlineMessage, setOnlineMessage] = useState('')
  const [selectedBehavior, setSelectedBehavior] = useState<AnalyticsLearningBehaviorRow | null>(null)
  const [selectedBehaviorDetail, setSelectedBehaviorDetail] = useState<AnalyticsStudentLearningBehaviorDetail | null>(null)
  const [selectedBehaviorLoading, setSelectedBehaviorLoading] = useState(false)
  const effectiveCourseId = learningSummary?.openedx_course_id || classInfo?.openedx_course_id || ''
  const isUdemyClass = classInfo?.learning_platform === 'udemy'

  const refreshStudentPage = async () => {
    const studentPage = await getAcademicClassStudents(headers, classId, { search: debouncedSearch, learningStatus, page, pageSize })
    setStudents(studentPage.items)
    setTotal(studentPage.total)
  }


  const refreshClassOverview = async () => {
    const [detail, nextSummary, nextLearning] = await Promise.all([
      getAcademicClass(headers, classId),
      getAcademicClassMappingSummary(headers, classId),
      getAcademicClassLearningSummary(headers, classId),
    ])
    setClassInfo(detail)
    setSummary(nextSummary)
    setLearningSummary(nextLearning)
  }

  const refreshAfterDataChange = async () => {
    await Promise.all([refreshClassOverview(), refreshStudentPage()])
    if (effectiveCourseId) refreshOnlineAnalytics().catch(() => undefined)
  }

  const refreshOnlineAnalytics = async () => {
    if (!effectiveCourseId) {
      setOnlineSummary(null)
      setOnlineRows([])
      return
    }
    setOnlineLoading(true)
    try {
      const [nextSummary, nextRows] = await Promise.all([
        getAnalyticsClassLearningBehaviorSummary(headers, classId, effectiveCourseId),
        getAnalyticsClassLearningBehavior(headers, classId, { courseId: effectiveCourseId, limit: 200, offset: 0 }),
      ])
      setOnlineSummary(nextSummary)
      setOnlineRows(nextRows.items || [])
    } finally {
      setOnlineLoading(false)
    }
  }

  const recalculateOnlineAnalytics = async () => {
    if (!effectiveCourseId) {
      setOnlineMessage('Chưa ghép Course CMS cho lớp này.')
      return
    }
    setOnlineRecalculating(true)
    setOnlineMessage('')
    try {
      const job = await enqueueAnalyticsClassLearningBehaviorJob(headers, classId, effectiveCourseId)
      setOnlineMessage(`Đã đưa tính lại học online vào hàng đợi: ${job.id?.slice(0, 8) || 'đang xử lý'}.`)
      await refreshOnlineAnalytics()
    } catch (error) {
      setErrorModal(error instanceof Error ? error.message : 'Không tính lại được học online')
    } finally {
      setOnlineRecalculating(false)
    }
  }

  const openBehaviorDetail = async (behavior: AnalyticsLearningBehaviorRow) => {
    setSelectedBehavior(behavior)
    setSelectedBehaviorDetail(null)
    if (!effectiveCourseId || !behavior.username) return
    setSelectedBehaviorLoading(true)
    try {
      const detail = await getAnalyticsStudentLearningBehaviorDetail(headers, classId, behavior.username, effectiveCourseId)
      setSelectedBehaviorDetail(detail)
    } catch (error) {
      setErrorModal(error instanceof Error ? error.message : 'Không tải được chi tiết học online')
    } finally {
      setSelectedBehaviorLoading(false)
    }
  }

  const isJobActive = (job?: AcademicClassSyncJob | null) => {
    const status = String(job?.status || '').toLowerCase()
    return Boolean(job?.id) && !['completed', 'failed'].includes(status)
  }

  const jobTypeLabel = (type?: string | null) => {
    if (type === 'full_cms_sync') return 'Đồng bộ full CMS'
    if (type === 'learning_sync') return 'Cập nhật điểm'
    if (type === 'cms_sync_check') return 'Kiểm tra tài khoản CMS'
    if (type === 'cms_enrollment_sync') return 'Kiểm tra ghi danh CMS'
    return 'Đồng bộ CMS'
  }

  const jobStatusLabel = (status?: string | null) => {
    const value = String(status || '').toLowerCase()
    if (value === 'queued') return 'Đang chờ'
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
    refreshClassOverview()
      .catch((error) => { if (!cancelled) setErrorModal(error instanceof Error ? error.message : 'Không tải được thông tin lớp') })
    return () => { cancelled = true }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [headers, classId])

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    getAcademicClassStudents(headers, classId, { search: debouncedSearch, learningStatus, page, pageSize })
      .then((studentPage) => {
        if (cancelled) return
        setStudents(studentPage.items)
        setTotal(studentPage.total)
      })
      .catch((error) => { if (!cancelled) setErrorModal(error instanceof Error ? error.message : 'Không tải được sinh viên') })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [headers, classId, debouncedSearch, learningStatus, page, pageSize])


  useEffect(() => {
    let cancelled = false
    if (!effectiveCourseId) {
      setOnlineSummary(null)
      setOnlineRows([])
      return () => { cancelled = true }
    }
    setOnlineLoading(true)
    Promise.all([
      getAnalyticsClassLearningBehaviorSummary(headers, classId, effectiveCourseId),
      getAnalyticsClassLearningBehavior(headers, classId, { courseId: effectiveCourseId, limit: 200, offset: 0 }),
    ])
      .then(([nextSummary, nextRows]) => {
        if (cancelled) return
        setOnlineSummary(nextSummary)
        setOnlineRows(nextRows.items || [])
      })
      .catch(() => {
        if (cancelled) return
        setOnlineSummary(null)
        setOnlineRows([])
      })
      .finally(() => { if (!cancelled) setOnlineLoading(false) })
    return () => { cancelled = true }
  }, [headers, classId, effectiveCourseId])

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
    setMessage(`${jobTypeLabel(running.job_type)} đang chạy.`)
    const finished = await waitForSyncJob(running)
    if (finished.status === 'failed') throw new Error(finished.error_message || 'Job đồng bộ đang chạy thất bại')
    await refreshAfterDataChange()
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
          setMessage(`${jobTypeLabel(running.job_type)} đang chạy.`)
          const finished = await waitForSyncJob(running)
          if (!cancelled) {
            if (finished.status === 'failed') setErrorModal(finished.error_message || 'Job đồng bộ thất bại')
            else {
              setMessage(`${jobTypeLabel(finished.job_type)} hoàn tất.`)
              await refreshAfterDataChange()
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


  const isReportJobActive = (job?: AcademicTeacherReportJob | null) => ['queued', 'running'].includes(String(job?.status || '').toLowerCase())

  const reportJobProgressPercent = (job?: AcademicTeacherReportJob | null) => {
    if (!job) return 0
    const current = Number(job.progress_current || 0)
    const total = Math.max(1, Number(job.progress_total || 100))
    return Math.min(100, Math.max(0, Math.round((current / total) * 100)))
  }

  const bulkJobProgressPercent = (job?: AcademicBulkOperationJob | null) => {
    if (!job) return 0
    const current = Number(job.progress_current || 0)
    const total = Math.max(1, Number(job.progress_total || 100))
    return Math.min(100, Math.max(0, Math.round((current / total) * 100)))
  }

  const loadProgressEmailPreview = async () => {
    setProgressEmailLoading(true)
    try {
      const preview = await getAcademicClassProgressEmailPreview(headers, classId)
      setProgressEmailPreview(preview)
      setProgressEmailSelected(new Set(preview.recipients.filter((item) => item.deliverable).slice(0, preview.max_recipients).map((item) => item.student_id)))
      setProgressEmailSubject(preview.default_subject)
      setProgressEmailBody(preview.default_body_template)
    } catch (error) {
      setProgressEmailOpen(false)
      setErrorModal(error instanceof Error ? error.message : 'Không tải được danh sách sinh viên chậm tiến độ')
    } finally {
      setProgressEmailLoading(false)
    }
  }

  const openProgressEmailDialog = () => {
    setProgressEmailPreview(null)
    setProgressEmailSelected(new Set())
    setProgressEmailOpen(true)
    loadProgressEmailPreview().catch(() => undefined)
  }

  const toggleProgressEmailRecipient = (studentId: string) => {
    setProgressEmailSelected((current) => {
      const next = new Set(current)
      if (next.has(studentId)) next.delete(studentId)
      else next.add(studentId)
      return next
    })
  }

  const toggleAllProgressEmailRecipients = () => {
    if (!progressEmailPreview) return
    const deliverableIds = progressEmailPreview.recipients.filter((item) => item.deliverable).slice(0, progressEmailPreview.max_recipients).map((item) => item.student_id)
    const allSelected = deliverableIds.length > 0 && deliverableIds.every((id) => progressEmailSelected.has(id))
    setProgressEmailSelected(allSelected ? new Set() : new Set(deliverableIds))
  }

  const sendProgressEmail = async () => {
    if (!progressEmailPreview?.mail_configured || progressEmailSelected.size === 0) return
    setProgressEmailSubmitting(true)
    try {
      const requestKey = typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
        ? crypto.randomUUID()
        : `progress-email-${Date.now()}`
      const queued = await enqueueAcademicClassProgressEmailJob(jsonHeaders, classId, {
        studentIds: Array.from(progressEmailSelected),
        subject: progressEmailSubject,
        bodyTemplate: progressEmailBody,
        requestKey,
      })
      setProgressEmailJob(queued)
      setProgressEmailOpen(false)
      setMessage(`Đã xếp hàng gửi nhắc tiến độ cho ${progressEmailSelected.size} sinh viên. Hệ thống đang cập nhật lại tiến độ CMS trước khi gửi.`)
    } catch (error) {
      setErrorModal(error instanceof Error ? error.message : 'Không tạo được tác vụ gửi nhắc tiến độ')
    } finally {
      setProgressEmailSubmitting(false)
    }
  }

  useEffect(() => {
    if (!canSendProgressEmail || isUdemyClass) return
    let cancelled = false
    getAcademicBulkOperationJobs(headers, { status: 'active', limit: 100 })
      .then((jobs) => {
        if (cancelled) return
        const active = jobs.find((job) => job.job_type === 'progress_reminder_email' && String(job.request_json?.class_id || '') === classId)
        if (active) setProgressEmailJob(active)
      })
      .catch(() => undefined)
    return () => { cancelled = true }
  }, [headers, classId, canSendProgressEmail, isUdemyClass])

  useEffect(() => {
    if (!progressEmailJob?.id || !['queued', 'running'].includes(String(progressEmailJob.status || '').toLowerCase())) return
    let cancelled = false
    const timer = window.setInterval(() => {
      getAcademicBulkOperationJob(headers, progressEmailJob.id)
        .then((job) => {
          if (cancelled) return
          setProgressEmailJob(job)
          if (job.status === 'completed') {
            const result = job.result_json || {}
            const sent = typeof result.sent_count === 'number' ? `${result.sent_count} email` : 'session email'
            const removed = Number(result.caught_up_or_no_longer_late_count || 0)
            setMessage(`Đã hoàn tất ${sent}.${removed > 0 ? ` Tự loại ${removed} sinh viên đã bắt kịp tiến độ.` : ''}`)
            refreshAfterDataChange().catch(() => undefined)
          }
          if (job.status === 'failed') setErrorModal(job.error_message || 'Gửi nhắc tiến độ thất bại')
        })
        .catch(() => undefined)
    }, 1500)
    return () => { cancelled = true; window.clearInterval(timer) }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [headers, progressEmailJob?.id, progressEmailJob?.status])

  const exportClassExcel = async () => {
    if (!classId || isUdemyClass) return
    setExportingClass(true)
    setMessage('')
    try {
      const queued = await createAcademicTrainingClassExportJob(headers, classId)
      setClassExportJob(queued)
      setMessage('Đã đưa xuất Excel lớp vào hàng đợi. Hệ thống sẽ lấy điểm CMS mới nhất trước khi tạo file.')
    } catch (error) {
      setErrorModal(error instanceof Error ? error.message : 'Không tạo được tác vụ xuất Excel lớp')
    } finally {
      setExportingClass(false)
    }
  }

  const downloadClassExcel = async () => {
    if (!classExportJob?.id || classExportJob.status !== 'completed') return
    try {
      const blob = await downloadAcademicTrainingTeacherReportJob(headers, classExportJob.id)
      const url = window.URL.createObjectURL(blob)
      const anchor = document.createElement('a')
      anchor.href = url
      anchor.download = classExportJob.file_name || `class-${classInfo?.class_code || classId}.xlsx`
      document.body.appendChild(anchor)
      anchor.click()
      anchor.remove()
      window.URL.revokeObjectURL(url)
    } catch (error) {
      setErrorModal(error instanceof Error ? error.message : 'Không tải được Excel lớp')
    }
  }

  useEffect(() => {
    let cancelled = false
    getAcademicTrainingTeacherReportJobs(headers, { status: 'active', limit: 40 })
      .then((jobs) => {
        if (cancelled) return
        const active = jobs.find((job) => String(job.request_json?.class_id || '') === classId && isReportJobActive(job))
        if (active) setClassExportJob(active)
      })
      .catch(() => undefined)
    return () => { cancelled = true }
  }, [headers, classId])

  useEffect(() => {
    if (!classExportJob?.id || !isReportJobActive(classExportJob)) return
    let cancelled = false
    const timer = window.setInterval(() => {
      getAcademicTrainingTeacherReportJob(headers, classExportJob.id)
        .then((job) => {
          if (cancelled) return
          setClassExportJob(job)
          if (job.status === 'completed') setMessage('Excel lớp đã sẵn sàng và được tạo từ điểm CMS mới nhất.')
          if (job.status === 'failed') setErrorModal(job.error_message || 'Xuất Excel lớp thất bại')
        })
        .catch(() => undefined)
    }, 1500)
    return () => { cancelled = true; window.clearInterval(timer) }
  }, [headers, classExportJob?.id, classExportJob?.status])

  const openAssignmentModal = async () => {
    setErrorModal('Workflow nhập điểm Assignment đã tắt. Điểm Assignment do hệ thống khác xử lý; AI Server chỉ hiển thị trạng thái đọc nếu đã được đồng bộ.')
  }

  const assignmentSummary = useMemo(() => {
    const counts = { total: assignmentRows.length, not_graded: 0, submitted: 0, waiting_defense: 0, graded: 0, absent: 0, needs_regrade: 0, scored: 0, missing_score: 0 }
    assignmentRows.forEach((row) => {
      const status = String(row.defense_status || 'not_graded').toLowerCase() as keyof typeof counts
      if (status in counts) counts[status] += 1
      if (typeof row.score_10 === 'number') counts.scored += 1
      if (status === 'graded' && typeof row.score_10 !== 'number') counts.missing_score += 1
    })
    return counts
  }, [assignmentRows])

  const filteredAssignmentRows = useMemo(() => {
    if (assignmentStatusFilter === 'all') return assignmentRows
    return assignmentRows.filter((row) => String(row.defense_status || 'not_graded').toLowerCase() === assignmentStatusFilter)
  }, [assignmentRows, assignmentStatusFilter])

  const updateAssignmentRow = (_studentId: string, _patch: Partial<AcademicAssignmentDefenseScore>) => {}

  const applyAssignmentBulkStatus = () => {}

  const saveAssignmentRows = async () => {
    setErrorModal('Không lưu được điểm Assignment trên AI Server. Điểm Assignment do hệ thống khác xử lý.')
  }

  const runFullCmsSync = async () => {
    if (!canRunFullCmsSync) return
    setSyncingFullFlow(true)
    setMessage('')
    try {
      if (await followExistingJobIfAny()) return
      const queued = await enqueueAcademicClassFullCmsSyncJob(jsonHeaders, classId, { force: true, limit: 500, autoMapCourse: true, syncLearning: true })
      if (queued.job_type !== 'full_cms_sync') {
        setMessage(`${jobTypeLabel(queued.job_type)} đang chạy.`)
        await waitForSyncJob(queued)
        await refreshAfterDataChange()
        return
      }
      const finished = await waitForSyncJob(queued)
      if (finished.status === 'failed') throw new Error(finished.error_message || 'Đồng bộ full CMS thất bại')
      const result = finished.result_json as any
      const learned = result?.learning?.updated || 0
      setMessage(`Đồng bộ xong: ${learned} sinh viên.`)
      await refreshAfterDataChange()
    } catch (error) {
      setErrorModal(error instanceof Error ? error.message : 'Đồng bộ full CMS thất bại')
    } finally {
      setSyncingFullFlow(false)
      setActiveJob(null)
    }
  }

  const runScoreUpdate = async () => {
    if (!canRunFullCmsSync) return
    setSyncingScoreUpdate(true)
    setMessage('')
    try {
      if (await followExistingJobIfAny()) return
      const queued = await enqueueAcademicClassLearningSyncJob(jsonHeaders, classId, { force: true, limit: 500 })
      if (queued.job_type !== 'learning_sync') {
        setMessage(`${jobTypeLabel(queued.job_type)} đang chạy.`)
        await waitForSyncJob(queued)
        await refreshAfterDataChange()
        return
      }
      const finished = await waitForSyncJob(queued)
      if (finished.status === 'failed') throw new Error(finished.error_message || 'Cập nhật điểm CMS thất bại')
      const result = finished.result_json as any
      const learned = result?.updated || result?.learning?.updated || result?.counts?.learning_synced || 0
      setMessage(`Cập nhật xong: ${learned} sinh viên.`)
      await refreshAfterDataChange()
    } catch (error) {
      setErrorModal(error instanceof Error ? error.message : 'Cập nhật điểm thất bại')
    } finally {
      setSyncingScoreUpdate(false)
      setActiveJob(null)
    }
  }

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== 'Escape') return
      if (progressEmailOpen && !progressEmailSubmitting) setProgressEmailOpen(false)
      else if (selectedQuiz) setSelectedQuiz(null)
      else if (selectedBehavior) { setSelectedBehavior(null); setSelectedBehaviorDetail(null) }
      else if (assignmentModalOpen) setAssignmentModalOpen(false)
      else if (errorModal) setErrorModal('')
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [progressEmailOpen, progressEmailSubmitting, selectedQuiz, selectedBehavior, assignmentModalOpen, errorModal])

  const totalPages = Math.max(1, Math.ceil(total / pageSize))
  const counts = summary?.counts || {}
  const matched = counts.matched || 0
  const needsCmsAction = Math.max(0, (summary?.total || 0) - matched)
  const activeJobRunning = isJobActive(activeJob)
  const progressEmailJobActive = ['queued', 'running'].includes(String(progressEmailJob?.status || '').toLowerCase())
  const progressEmailDeliverable = progressEmailPreview?.recipients.filter((item) => item.deliverable).slice(0, progressEmailPreview.max_recipients) || []
  const progressEmailAllSelected = progressEmailDeliverable.length > 0 && progressEmailDeliverable.every((item) => progressEmailSelected.has(item.student_id))
  const actionBusy = activeJobRunning || syncingFullFlow || syncingScoreUpdate || recoveringJob || isReportJobActive(classExportJob) || progressEmailJobActive
  const debugMode = searchParams.get('debug') === '1'

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

  const onlineBehaviorByUsername = useMemo(() => {
    const map = new Map<string, AnalyticsLearningBehaviorRow>()
    onlineRows.forEach((row) => {
      if (row.username) map.set(row.username, row)
    })
    return map
  }, [onlineRows])

  const studentBehavior = (student: AcademicStudent) => {
    return onlineBehaviorByUsername.get(student.username || '') || onlineBehaviorByUsername.get(student.openedx_username || '') || null
  }

  const studentComponentScore = (student: AcademicStudent, column: GradeColumn) => {
    return student.learning_component_scores?.find((score) => gradeColumnIdentity(score) === column.key || componentKey(score) === column.key || score.name === column.name) || null
  }

  const navigationPlatform = searchParams.get('platform') === 'udemy' || isUdemyClass ? 'udemy' : 'cms'
  const navigationPlatformLabel = navigationPlatform === 'udemy' ? 'Udemy' : 'CMS'
  const subjectIdForBack = searchParams.get('subject_id') || classInfo?.subject_id || ''
  const subjectBackParams = new URLSearchParams()
  const backTermId = searchParams.get('term_id') || classInfo?.term_id || ''
  const backBranch = searchParams.get('branch') || classInfo?.branch || 'poly'
  const listCampusParam = searchParams.get('list_campus')
  const cameFromScopedList = listCampusParam !== null
  const backCampus = cameFromScopedList
    ? (listCampusParam && listCampusParam !== 'all' ? listCampusParam : '')
    : (searchParams.get('campus') || classInfo?.campus || '')
  const classCampus = classInfo?.campus || searchParams.get('campus') || ''
  const backTermName = searchParams.get('term_name') || classInfo?.term_name || ''
  const backSubjectCode = searchParams.get('subject_code') || classInfo?.subject_code || ''
  const backSubjectName = searchParams.get('subject_name') || classInfo?.subject_name || ''
  if (backTermId) subjectBackParams.set('term_id', backTermId)
  if (backBranch) subjectBackParams.set('branch', backBranch)
  if (backCampus) subjectBackParams.set('campus', backCampus)
  if (backTermName) subjectBackParams.set('term_name', backTermName)
  if (backSubjectCode) subjectBackParams.set('subject_code', backSubjectCode)
  if (backSubjectName) subjectBackParams.set('subject_name', backSubjectName)
  subjectBackParams.set('platform', navigationPlatform)
  const backToClassesHref = subjectIdForBack ? `/student-management/subjects/${encodeURIComponent(subjectIdForBack)}/classes?${subjectBackParams.toString()}` : `/student-management/${navigationPlatform}`
  const teacherIdForBack = searchParams.get('teacher_id') || ''
  const teacherBackParams = new URLSearchParams()
  if (backTermId) teacherBackParams.set('term_id', backTermId)
  if (backBranch) teacherBackParams.set('branch', backBranch)
  if (backCampus) teacherBackParams.set('campus', backCampus)
  if (backTermName) teacherBackParams.set('term_name', backTermName)
  if (searchParams.get('teacher_name')) teacherBackParams.set('teacher_name', searchParams.get('teacher_name') || '')
  teacherBackParams.set('platform', navigationPlatform)
  const backToTeacherClassesHref = teacherIdForBack ? `/teacher-management/teachers/${encodeURIComponent(teacherIdForBack)}/classes?${teacherBackParams.toString()}` : ''
  const operationalBackHref = backToTeacherClassesHref || backToClassesHref
  const behaviorParams = new URLSearchParams()
  if (backBranch) behaviorParams.set('branch', backBranch)
  if (backTermId) behaviorParams.set('term_id', backTermId)
  if (classCampus) behaviorParams.set('campus', classCampus)
  if (subjectIdForBack) behaviorParams.set('subject_id', subjectIdForBack)
  if (classId) behaviorParams.set('class_id', classId)
  behaviorParams.set('classification', 'all')
  const behaviorHref = `/analytics/learning?${behaviorParams.toString()}`

  const studentColumns: EnterpriseTableColumn<AcademicStudent>[] = [
    { key: 'stt', header: 'STT', kind: 'index', width: 52, sticky: 'left', hideable: false, render: (_student, index) => (page - 1) * pageSize + index + 1 },
    { key: 'student', header: 'Sinh viên', kind: 'identity', minWidth: 250, sticky: 'left', hideable: false, render: (student) => <div className="student-identity-cell"><b>{student.student_code || '—'} · {student.full_name || 'Chưa có họ tên'}</b><small>{student.email || 'Chưa có email'}</small><small>Học lại: {student.total_relearn || 0}</small></div> },
    { key: 'cms', header: 'Tài khoản CMS', kind: 'status', minWidth: 180, priority: 'important', hideable: true, render: (student) => <div className="student-status-cell"><span className={cmsSyncClass(student.match_status)}>{cmsSyncLabel(student.match_status)}</span><small>{student.openedx_username || student.username || 'Chưa có username'}</small></div> },
    { key: 'enrollment', header: 'Ghi danh', kind: 'status', minWidth: 150, priority: 'important', hideable: true, render: (student) => <span className={enrollmentClass(student.learning_enrollment_status)}>{enrollmentLabel(student.learning_enrollment_status)}</span> },
    { key: 'progress', header: 'Tiến độ học', kind: 'progress', minWidth: 240, priority: 'important', hideable: true, render: (student) => <div className="learning-progress-cell compact-learning-progress-cell"><b>Hoàn thành: {percentLabel(student.learning_progress_percent)}</b><small>Điểm tổng: {grade10Label(student.learning_grade_percent)}</small><div className="student-learning-status-stack"><span className={learningStatusClass(student.learning_status)}>{learningStatusLabel(student.learning_status)}</span>{shouldSuggestFullCmsSync(student) ? <span className="cms-full-sync-hint">Cần đồng bộ full CMS</span> : null}</div></div> },
    { key: 'online', header: 'Học online', kind: 'status', minWidth: 210, priority: 'important', hideable: true, render: (student) => { const behavior = studentBehavior(student); return behavior ? <button className="online-behavior-button" type="button" onClick={() => openBehaviorDetail(behavior)}><span className={behaviorStatusClass(behavior)}>{safeBehaviorLabel(behavior)}</span><small>Độ tin cậy: {Math.round(behavior.confidence_score || 0)}%</small><small>{recommendedActionLabel(behavior.recommended_action)}</small></button> : <span className="status-pill neutral">Chưa đủ dữ liệu</span> } },
    { key: 'exam', header: 'Điều kiện thi', kind: 'status', minWidth: 220, priority: 'important', hideable: true, render: (student) => <div className="exam-policy-cell"><span className={examStatusClass(student.exam_status)}>{examStatusLabel(student)}</span><small>{student.exam_reasons?.slice(0, 2).join('; ') || 'Chưa đủ dữ liệu'}</small><small>Assignment: {defenseStatusLabel(student.assignment_defense_status)}{typeof student.assignment_score_10 === 'number' ? ` · ${student.assignment_score_10}/10` : ''}</small></div> },
    ...componentColumns.map((column): EnterpriseTableColumn<AcademicStudent> => ({
      key: `component-${column.key}`,
      header: column.name,
      kind: 'status',
      minWidth: 128,
      priority: 'optional',
      hideable: true,
      render: (student) => { const score = studentComponentScore(student, column); return <button className="quiz-grade-cell-button" type="button" title={componentDeadlineLabel(column)} onClick={() => setSelectedQuiz({ student, column, score })}><b>{componentScoreText(score)}</b><span className={quizStatusClass(score)}>{quizStatusLabel(score)}</span><small>{componentDeadlineLabel(column)}</small></button> },
    })),
  ]

  return <PageRoot className="page-stack enterprise-standard-page student-management-page academic-flow-page class-detail-flow training-operations-page">
    <EnterpriseScreenHeader
      eyebrow="Vận hành đào tạo"
      title={`Chi tiết lớp ${classInfo?.class_code || ''}`.trim()}
      description={isUdemyClass ? 'Lớp đang học trên Udemy. Theo dõi tiến độ và cảnh báo từ báo cáo Udemy, không thực hiện Full CMS hoặc Enrollment Open edX.' : 'Theo dõi sinh viên, đồng bộ CMS, ghi danh, tiến độ học, đầu điểm và các tín hiệu cần giáo viên xác minh.'}
      icon="students"
      tone="blue"
      breadcrumbs={teacherIdForBack
        ? [{ label: 'Vận hành đào tạo' }, { label: `Quản lý giảng viên ${navigationPlatformLabel}`, href: `/teacher-management/${navigationPlatform}` }, { label: 'Lớp giảng viên', href: operationalBackHref }, { label: classInfo?.class_code || 'Chi tiết lớp' }]
        : [{ label: 'Vận hành đào tạo' }, { label: `Quản lý sinh viên ${navigationPlatformLabel}`, href: `/student-management/${navigationPlatform}` }, { label: 'Danh sách lớp', href: operationalBackHref }, { label: classInfo?.class_code || 'Chi tiết lớp' }]}
      secondaryActions={<Link className="btn secondary" href={operationalBackHref}>Quay lại danh sách lớp</Link>}
      primaryAction={!isUdemyClass ? <Link className="btn primary" href={behaviorHref}>Phân tích học tập</Link> : undefined}
    />
    <section className="card academic-unified-card training-workspace-section">
      <div className="class-action-row compact-sync-action-strip clean-sync-action-strip class-primary-actions">
        <div className="toolbar-actions">
          {!isUdemyClass && canRunFullCmsSync && <button className="btn primary class-action-button action-full-sync" type="button" disabled={actionBusy} onClick={runFullCmsSync}><AppIcon name="sync" size={16} />{syncingFullFlow ? 'Đang đồng bộ full CMS...' : 'Đồng bộ full CMS'}</button>}
          {!isUdemyClass && canRunFullCmsSync && <button className="btn secondary class-action-button action-score-update" type="button" disabled={actionBusy} onClick={runScoreUpdate}><AppIcon name="analytics" size={16} />{syncingScoreUpdate ? 'Đang cập nhật điểm...' : 'Cập nhật điểm'}</button>}
          {!isUdemyClass && canSendProgressEmail && <button className="btn secondary class-action-button action-progress-email" type="button" disabled={actionBusy || !effectiveCourseId} onClick={openProgressEmailDialog}><AppIcon name="alert" size={16} />{progressEmailJobActive ? 'Đang gửi nhắc tiến độ...' : 'Gửi nhắc tiến độ'}</button>}
          {!isUdemyClass && <button className="btn secondary class-action-button action-class-export" type="button" disabled={actionBusy || exportingClass} onClick={exportClassExcel}><AppIcon name="download" size={16} />{isReportJobActive(classExportJob) ? `Đang xuất Excel ${reportJobProgressPercent(classExportJob)}%` : 'Xuất Excel lớp'}</button>}
          {!isUdemyClass && classExportJob?.status === 'completed' && <button className="btn secondary class-action-button action-class-download" type="button" onClick={downloadClassExcel}><AppIcon name="download" size={16} />Tải Excel lớp</button>}
          {can('manage_settings') && <Link className="btn secondary class-action-button action-week-settings" href="/semesters"><AppIcon name="calendar" size={16} />Cấu hình tuần học</Link>}
        </div>
      </div>
      {classExportJob && <div className="sync-job-status persistent-sync-job-status">
        <div className="sync-job-main-row">
          <div>
            <b>{classExportJob.progress_label || 'Đang xuất Excel lớp...'}</b>
            <small>Xuất Excel lớp · {jobStatusLabel(classExportJob.status)} · {reportJobProgressPercent(classExportJob)}%</small>
          </div>
          {classExportJob.status === 'completed' ? <button className="btn secondary small" type="button" onClick={downloadClassExcel}>Tải Excel</button> : null}
        </div>
        <div className="progress-track"><span style={{ width: `${reportJobProgressPercent(classExportJob)}%` }} /></div>
      </div>}
      {activeJob && <div className="sync-job-status persistent-sync-job-status">
        <div className="sync-job-main-row">
          <div>
            <b>{activeJob.progress_label || 'Đang xử lý job đồng bộ...'}</b>
            <small>{jobTypeLabel(activeJob.job_type)} · {jobStatusLabel(activeJob.status)} · {activeJob.progress_current || 0}/{activeJob.progress_total || 100}</small>
          </div>
          <button className="btn secondary small" type="button" onClick={() => getAcademicClassSyncJob(headers, classId, activeJob.id).then((job) => { setActiveJob(job); setSyncJobs((items) => [job, ...items.filter((item) => item.id !== job.id)].slice(0, 10)) }).catch((error) => setErrorModal(error instanceof Error ? error.message : 'Không làm mới được tiến trình'))}>Làm mới</button>
        </div>
        <div className="progress-track"><span style={{ width: `${jobProgressPercent(activeJob)}%` }} /></div>
      </div>}
      {progressEmailJob && <div className={`sync-job-status persistent-sync-job-status progress-email-job-status is-${String(progressEmailJob.status || 'queued').toLowerCase()}`}>
        <div className="sync-job-main-row">
          <div>
            <b>{progressEmailJob.progress_label || 'Đang xử lý gửi nhắc tiến độ...'}</b>
            <small>
              Gửi nhắc tiến độ · {jobStatusLabel(progressEmailJob.status)} · {bulkJobProgressPercent(progressEmailJob)}%
              {typeof progressEmailJob.result_json?.sent_count === 'number' ? ` · ${progressEmailJob.result_json.sent_count} đã gửi` : ''}
              {Number(progressEmailJob.result_json?.caught_up_or_no_longer_late_count || 0) > 0 ? ` · ${progressEmailJob.result_json?.caught_up_or_no_longer_late_count} đã bắt kịp được loại` : ''}
            </small>
          </div>
          <button className="btn secondary small" type="button" onClick={() => getAcademicBulkOperationJob(headers, progressEmailJob.id).then(setProgressEmailJob).catch((error) => setErrorModal(error instanceof Error ? error.message : 'Không làm mới được tiến trình gửi mail'))}>Làm mới</button>
        </div>
        <div className="progress-track"><span style={{ width: `${bulkJobProgressPercent(progressEmailJob)}%` }} /></div>
      </div>}
      {message && <p className="form-message">{message}</p>}


      <TrainingContextChips items={[classInfo?.block_name || 'Chưa có block', classInfo?.teacher_name || classInfo?.teacher_username || 'Chưa phân công giảng viên', classInfo?.exam_cutoff_date ? `Ngày cuối xét cấm thi: ${formatDateOnly(classInfo.exam_cutoff_date)}` : 'Chưa có ngày cuối xét cấm thi', isUdemyClass ? 'Nền tảng Udemy' : (classInfo?.openedx_course_id || 'Chưa ghép Course CMS')]} />
      <TrainingKpiStrip compact items={isUdemyClass ? [
        { key: 'students', label: 'Sinh viên AP', value: classInfo?.student_count ?? 0 },
        { key: 'udemyImported', label: 'Đã có tiến độ', value: classInfo?.udemy_progress_student_count ?? 0 },
        { key: 'udemyLate', label: 'Chậm tiến độ', value: classInfo?.udemy_progress_late_count ?? 0, tone: (classInfo?.udemy_progress_late_count || 0) > 0 ? 'warning' : 'success' },
        { key: 'udemyAverage', label: 'Tiến độ TB', value: percentLabel(classInfo?.udemy_progress_average_percent) },
        { key: 'platform', label: 'Nền tảng', value: 'Udemy', tone: 'success' },
        { key: 'updated', label: 'Cập nhật gần nhất', value: classInfo?.udemy_progress_last_imported_at ? formatVNTimeDate(classInfo.udemy_progress_last_imported_at) : 'Chưa import' },
      ] : [
        { key: 'students', label: 'Sinh viên', value: summary?.total ?? classInfo?.student_count ?? 0 },
        { key: 'cms', label: 'CMS match', value: `${matched}/${summary?.total ?? classInfo?.student_count ?? 0}`, hint: `${needsCmsAction} cần xử lý`, tone: needsCmsAction > 0 ? 'warning' : 'success' },
        { key: 'enrolled', label: 'Đã ghi danh', value: learningSummary?.counts?.enrolled || 0 },
        { key: 'active', label: 'Đã vào học', value: learningSummary?.active_count || 0 },
        { key: 'progress', label: 'Hoàn thành TB', value: percentLabel(learningSummary?.avg_progress_percent) },
        { key: 'grade', label: 'Điểm tổng TB', value: grade10Label(learningSummary?.avg_grade_percent), hint: learningSummary?.last_synced_at ? `Cập nhật ${formatVNTimeDate(learningSummary.last_synced_at)}` : 'Chưa cập nhật' },
      ]} />
      {!isUdemyClass && !effectiveCourseId ? <TrainingMappingEmptyState action={canRunFullCmsSync ? <button className="btn secondary small" type="button" disabled={actionBusy} onClick={runFullCmsSync}>Đồng bộ full CMS</button> : undefined} /> : null}

    </section>

    {isUdemyClass && classInfo?.subject_delivery_id ? <UdemyClassProgressPanel
      headers={headers}
      deliveryId={classInfo.subject_delivery_id}
      classId={classId}
      classCode={classInfo.class_code || 'Lớp'}
    /> : null}

    {!isUdemyClass ? <>
    <section className="card academic-unified-card online-learning-card">
      <div className="enterprise-content-section-head">
        <div className="enterprise-section-heading-identity">
          <VisualIcon label="Học online" icon="analytics" tone="blue" className="enterprise-section-heading-icon" />
          <div className="enterprise-section-heading-copy">
            <h2>Học online</h2>
            <p>Nhận định dựa trên log hệ thống, chỉ là tín hiệu hỗ trợ giáo viên xác minh.</p>
          </div>
        </div>
        <div className="toolbar-actions">
          {SHOW_DIAGNOSTICS_UI && canRunFullCmsSync && <button className="btn secondary small" type="button" disabled={onlineRecalculating || !effectiveCourseId} onClick={recalculateOnlineAnalytics}>{onlineRecalculating ? 'Đang tính...' : 'Tính lại học online'}</button>}
        </div>
      </div>
      <div className="online-learning-summary-strip">
        <div><span>Tổng đánh giá</span><b>{onlineSummary?.total_students || 0}</b></div>
        <div><span>Có dấu hiệu học thật</span><b>{onlineSummary?.likely_real_learning_count || 0}</b></div>
        <div><span>Có khả năng treo máy</span><b>{onlineSummary?.possible_idle_count || 0}</b></div>
        <div><span>Dấu hiệu cần kiểm tra</span><b>{onlineSummary?.possible_suspicious_count || 0}</b></div>
        <div><span>Chưa đủ dữ liệu</span><b>{onlineSummary?.insufficient_data_count || 0}</b></div>
      </div>
      <p className="online-learning-disclaimer">Đây là nhận định dựa trên log hệ thống, không phải kết luận vi phạm. Cần giáo viên/quản lý xác minh trước khi xử lý.</p>
      {onlineLoading && <p className="form-message">Đang tải học online...</p>}
      {onlineMessage && <p className="form-message">{onlineMessage}</p>}
    </section>

    <section className="card academic-unified-card student-list-card">
      <div className="enterprise-content-section-head student-list-section-head">
        <div className="enterprise-section-heading-identity">
          <VisualIcon label="Danh sách sinh viên" icon="students" tone="blue" className="enterprise-section-heading-icon" />
          <div className="enterprise-section-heading-copy"><h2>Danh sách sinh viên</h2><p>{studentListUpdatedAt ? `Cập nhật: ${formatVNTimeDate(studentListUpdatedAt)}` : 'Cập nhật: chưa có dữ liệu đồng bộ học tập'}</p></div>
        </div>
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
      <EnterpriseDataTable
        tableId={`class-students-${classId}`}
        caption="Danh sách sinh viên"
        showSummary={false}
        stickyHorizontalScroll
        rows={students}
        columns={studentColumns}
        rowKey={(student) => student.id}
        density="compact"
        loading={loading}
        page={page}
        pageSize={pageSize}
        total={total}
        totalPages={totalPages}
        onPageChange={setPage}
        onPageSizeChange={(value) => { setPageSize(value); setPage(1) }}
        label="sinh viên"
        emptyTitle="Không có sinh viên phù hợp"
        emptyDescription="Đổi trạng thái hoặc từ khóa tìm kiếm; nếu vẫn trống, kiểm tra roster AP và đồng bộ CMS."
      />
    </section>
    </> : null}



    <AccessibleDialog
      open={progressEmailOpen}
      title="Gửi nhắc sinh viên chậm tiến độ"
      description={classInfo ? `${classInfo.subject_code || 'Môn học'} · ${classInfo.class_code || 'Lớp học'}` : 'Mail Send AI Server'}
      onClose={() => { if (!progressEmailSubmitting) setProgressEmailOpen(false) }}
      size="xlarge"
      busy={progressEmailSubmitting}
      className="progress-email-dialog"
      bodyClassName="progress-email-dialog-body"
      footer={<div className="progress-email-dialog-footer">
        <div>
          <b>{progressEmailSelected.size} sinh viên được chọn</b>
          <small>Hệ thống sẽ cập nhật lại CMS và tự loại người đã bắt kịp trước khi gửi.</small>
        </div>
        <div className="dialog-action-row">
          <button className="btn secondary" type="button" disabled={progressEmailSubmitting} onClick={() => setProgressEmailOpen(false)}>Hủy</button>
          <button
            className="btn primary"
            data-dialog-autofocus
            type="button"
            disabled={progressEmailLoading || progressEmailSubmitting || !progressEmailPreview?.mail_configured || progressEmailSelected.size === 0 || !progressEmailSubject.trim() || !progressEmailBody.trim() || progressEmailSelected.size > Number(progressEmailPreview?.max_recipients || 1000)}
            onClick={sendProgressEmail}
          >
            <AppIcon name="alert" size={16} />{progressEmailSubmitting ? 'Đang tạo tác vụ...' : `Gửi cho ${progressEmailSelected.size} sinh viên`}
          </button>
        </div>
      </div>}
    >
      {progressEmailLoading ? <div className="progress-email-loading"><span className="spinner" aria-hidden="true" /><b>Đang xác định sinh viên chậm tiến độ...</b></div> : null}
      {!progressEmailLoading && progressEmailPreview ? <>
        {!progressEmailPreview.mail_configured ? <InlineNotice notice={{
          type: 'warning',
          title: 'AI Server chưa có Mail Send ProxyKey',
          body: 'Quản trị viên cần bật MAILSEND_ENABLED và khai báo MAILSEND_PROXY_API_KEY cho backend và worker-heavy. Danh sách vẫn xem được nhưng chưa thể gửi.',
        }} /> : null}
        <div className="progress-email-policy-note">
          <AppIcon name="info" size={18} />
          <div><b>Chỉ nhắc người đang trễ mốc Quiz</b><p>{progressEmailPreview.policy_note}</p></div>
        </div>
        <div className="progress-email-summary">
          <div><span>Roster lớp</span><b>{progressEmailPreview.roster_total}</b></div>
          <div className="is-warning"><span>Đang chậm tiến độ</span><b>{progressEmailPreview.candidate_count}</b></div>
          <div className="is-ready"><span>Có thể gửi</span><b>{progressEmailPreview.deliverable_count}</b></div>
          <div><span>Thiếu email / inactive</span><b>{progressEmailPreview.missing_email_count + progressEmailPreview.inactive_student_count}</b></div>
        </div>

        <section className="progress-email-recipients">
          <div className="progress-email-section-head">
            <div><h3>Người nhận</h3><p>Email được che trên giao diện; địa chỉ thật chỉ dùng bên trong worker gửi mail.</p></div>
            <button className="btn secondary small" type="button" disabled={!progressEmailDeliverable.length} onClick={toggleAllProgressEmailRecipients}>{progressEmailAllSelected ? 'Bỏ chọn tất cả' : 'Chọn tất cả có thể gửi'}</button>
          </div>
          <div className="progress-email-recipient-table" role="table" aria-label="Sinh viên chậm tiến độ">
            <div className="progress-email-recipient-head" role="row">
              <span role="columnheader">Chọn</span><span role="columnheader">Sinh viên</span><span role="columnheader">Tiến độ</span><span role="columnheader">Quiz đang trễ</span><span role="columnheader">Trạng thái gửi</span>
            </div>
            <div className="progress-email-recipient-body">
              {progressEmailPreview.recipients.map((recipient) => <label key={recipient.student_id} className={`progress-email-recipient-row ${recipient.deliverable ? '' : 'is-disabled'}`} role="row">
                <span role="cell"><input type="checkbox" checked={progressEmailSelected.has(recipient.student_id)} disabled={!recipient.deliverable} onChange={() => toggleProgressEmailRecipient(recipient.student_id)} aria-label={`Chọn ${recipient.student_code || recipient.full_name}`} /></span>
                <span role="cell" className="progress-email-student"><b>{recipient.student_code || 'Chưa có mã SV'} · {recipient.full_name}</b><small>{recipient.masked_email || 'Chưa có email hợp lệ'}</small></span>
                <span role="cell"><b>{percentLabel(recipient.progress_percent)}</b><small>{recipient.last_synced_at ? `CMS ${formatVNTimeDate(recipient.last_synced_at)}` : 'Chưa đồng bộ'}</small></span>
                <span role="cell"><b>{recipient.overdue_quiz_count} Quiz</b><small title={recipient.overdue_quizzes.join(', ')}>{recipient.overdue_quizzes.slice(0, 3).join(', ')}{recipient.overdue_quizzes.length > 3 ? '…' : ''}</small></span>
                <span role="cell"><span className={`status-pill ${recipient.deliverable ? 'success' : 'warning'}`}>{progressEmailIssueLabel(recipient.delivery_issue)}</span></span>
              </label>)}
              {!progressEmailPreview.recipients.length ? <div className="progress-email-empty"><AppIcon name="check" size={22} /><b>Không có sinh viên đang chậm mốc Quiz</b><span>Hiện chưa cần gửi thông báo cho lớp này.</span></div> : null}
            </div>
          </div>
        </section>

        <section className="progress-email-compose">
          <div className="progress-email-section-head"><div><h3>Nội dung thông báo</h3><p>Có thể dùng <code>{'{{maHs}}'}</code> để Mail Send điền mã sinh viên theo từng người nhận.</p></div></div>
          <label><span>Tiêu đề</span><input className="input" maxLength={200} value={progressEmailSubject} onChange={(event) => setProgressEmailSubject(event.target.value)} /></label>
          <label><span>Nội dung</span><textarea className="input" rows={9} maxLength={12000} value={progressEmailBody} onChange={(event) => setProgressEmailBody(event.target.value)} /></label>
        </section>
      </> : null}
    </AccessibleDialog>

    <AccessibleDialog
      open={Boolean(selectedBehavior)}
      title="Chi tiết học online"
      description={selectedBehavior?.username}
      onClose={() => { setSelectedBehavior(null); setSelectedBehaviorDetail(null) }}
      size="xlarge"
      className="online-behavior-modal online-behavior-deadline-modal"
    >
      {selectedBehavior ? <>
        <div className="quiz-detail-grid online-behavior-grid">
          <div><span>Nhận định</span><b>{safeBehaviorLabel(selectedBehavior)}</b></div>
          <div><span>Độ tin cậy</span><b>{Math.round(selectedBehavior.confidence_score || 0)}%</b></div>
          <div><span>Điểm học thật</span><b>{Math.round(selectedBehavior.real_learning_score || 0)}%</b></div>
          <div><span>Điểm treo máy</span><b>{Math.round(selectedBehavior.idle_score || 0)}%</b></div>
          <div><span>Điểm bất thường</span><b>{Math.round(selectedBehavior.suspicious_score || 0)}%</b></div>
          <div><span>Chất lượng dữ liệu</span><b>{selectedBehavior.data_quality || 'MISSING'}</b></div>
          <div><span>Lần học cuối</span><b>{selectedBehavior.last_activity_at ? formatVNDateTime(selectedBehavior.last_activity_at) : 'N/A'}</b></div>
          <div><span>Tính lúc</span><b>{selectedBehavior.calculated_at ? formatVNDateTime(selectedBehavior.calculated_at) : 'N/A'}</b></div>
        </div>
        <div className="online-behavior-evidence">
          <b>Tóm tắt</b>
          <p>{selectedBehavior.human_readable_summary || 'Chưa đủ dữ liệu để tóm tắt.'}</p>
          <b>Dấu hiệu chính</b>
          <p>{selectedBehavior.reason_codes?.length ? selectedBehavior.reason_codes.join(', ') : 'Chưa có dấu hiệu nổi bật.'}</p>
          <b>Hành động đề xuất</b>
          <p>{recommendedActionLabel(selectedBehavior.recommended_action)}</p>
        </div>

        <div className="online-deadline-section">
          <div className="section-head compact-section-head">
            <div>
              <h3>Theo Bài / Deadline</h3>
              <p>Deadline ưu tiên lấy từ cấu hình Quiz đã có; chỉ suy luận 6 tuần khi thật sự thiếu.</p>
            </div>
          </div>
          {selectedBehaviorLoading && <p className="form-message">Đang tải timeline học online...</p>}
          {!selectedBehaviorLoading && selectedBehaviorDetail?.sessions?.length ? <div className="online-week-timeline">
            {[1, 2, 3, 4, 5, 6].map((week) => {
              const sessions = selectedBehaviorDetail.sessions.filter((item) => Number(item.week_index || 0) === week)
              if (!sessions.length) return null
              return <div key={week} className="online-week-card">
                <h4>Tuần {week}</h4>
                <div className="online-session-list">
                  {sessions.map((session: AnalyticsStudentSessionProgress) => <div key={`${session.session_index}-${session.session_title}`} className="online-session-card">
                    <div className="online-session-head">
                      <b>{session.session_title || `Bài ${session.session_index}`}</b>
                      <span className={sessionStatusClass(session.session_learning_status)}>{sessionStatusLabel(session.session_learning_status)}</span>
                    </div>
                    <div className="online-session-metrics">
                      <span>Video: {session.videos_completed || 0}/{session.total_videos || 0}</span>
                      <span>Hoàn thành TB: {percentLabel(session.avg_video_completion_percent)}</span>
                      <span>Thời gian xem: {compactDuration(session.estimated_watch_seconds)}</span>
                      <span>Quiz cuối Bài: {session.quiz_completed ? 'Đạt' : session.quiz_attempted ? 'Đã làm' : 'Chưa làm'}</span>
                      <span>Deadline: {formatDateOnly(session.deadline_at)} · {deadlineSourceLabel(session.deadline_source)}</span>
                    </div>
                    <small>{session.completed_before_deadline ? 'Hoàn thành trước deadline' : session.completed_late ? 'Hoàn thành sau deadline' : 'Chưa xác nhận hoàn thành theo deadline'}</small>
                    {session.reason_codes?.length ? <small>Dấu hiệu: {session.reason_codes.slice(0, 4).join(', ')}</small> : null}
                  </div>)}
                </div>
              </div>
            })}
          </div> : null}
          {!selectedBehaviorLoading && selectedBehaviorDetail && !selectedBehaviorDetail.sessions?.length ? <p className="form-message">Chưa có dữ liệu theo Bài/Session. Hãy chạy ingest và Tính lại học online.</p> : null}
        </div>

        <p className="online-learning-disclaimer">Đây là nhận định dựa trên log hệ thống, không phải kết luận vi phạm. Cần giáo viên/quản lý xác minh trước khi xử lý.</p>
        <div className="modal-actions"><button className="btn primary" type="button" onClick={() => { setSelectedBehavior(null); setSelectedBehaviorDetail(null) }}>Đóng</button></div>
      </> : null}
    </AccessibleDialog>

    <AccessibleDialog
      open={Boolean(selectedQuiz)}
      title={selectedQuiz?.column.name || 'Chi tiết đầu điểm'}
      description={selectedQuiz ? `${selectedQuiz.student.student_code || selectedQuiz.student.username} · ${selectedQuiz.student.full_name}` : undefined}
      onClose={() => setSelectedQuiz(null)}
      size="medium"
      className="quiz-detail-modal"
    >
      {selectedQuiz ? <>
        <div className="quiz-detail-grid">
          <div><span>Điểm</span><b>{componentScoreText(selectedQuiz.score)}</b></div>
          <div><span>Trạng thái</span><b>{quizStatusLabel(selectedQuiz.score)}</b></div>
          <div><span>Thời gian bắt đầu hợp lệ</span><b>{formatDateOnly(selectedQuiz.score?.available_from || selectedQuiz.column.availableFrom)}</b></div>
          <div><span>Deadline</span><b>{formatDateOnly(selectedQuiz.score?.deadline_date || selectedQuiz.column.deadlineDate)}</b></div>
          <div><span>Ngày làm/nộp</span><b>{formatDateOnly(selectedQuiz.score?.submitted_at)}</b></div>
          {debugMode && <div><span>Nguồn dữ liệu</span><b>{selectedQuiz.score?.source || 'CMS/Open edX'}</b></div>}
        </div>
        {(selectedQuiz.score?.schedule_warning || selectedQuiz.column.scheduleWarning) && <p className="form-message warning-message">{selectedQuiz.score?.schedule_warning || selectedQuiz.column.scheduleWarning}</p>}
        <div className="modal-actions"><button className="btn primary" type="button" onClick={() => setSelectedQuiz(null)}>Đóng</button></div>
      </> : null}
    </AccessibleDialog>
    <AccessibleDialog
      open={Boolean(errorModal)}
      title="Không thực hiện được thao tác"
      onClose={() => setErrorModal('')}
      size="small"
      footer={<div className="dialog-action-row"><button className="btn primary" data-dialog-autofocus type="button" onClick={() => setErrorModal('')}>Đã hiểu</button></div>}
    >
      <p>{errorModal}</p>
    </AccessibleDialog>
  </PageRoot>
}

export default function ClassDetailPage() {
  return <Suspense fallback={<div className="card">Đang tải chi tiết lớp...</div>}><ClassDetailContent /></Suspense>
}
