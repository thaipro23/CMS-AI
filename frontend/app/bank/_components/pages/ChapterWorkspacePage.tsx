'use client'

import { formatVNDateTime } from '../../../../lib/time'
import Link from 'next/link'
import { useRouter, useSearchParams } from 'next/navigation'
import { useEffect, useMemo, useRef, useState } from 'react'
import { useAppContext } from '../../../../context/AppContext'
import {
  BankRelease,
  BankReleasePublishAudit,
  BankDashboardOverview,
  BankSearchResult,
  DepartmentSummary,
  SubjectSummary,
  SubjectVersionSummary,
  ChapterSummary,
  BankGeneratePreview,
  BankReleaseReadiness,
  BankVersion,
  BankVersionDiffPreview,
  BankMaterialRecheckResult,
  BankVersionQuestion,
  CourseQuizInstance,
  AuditLogRow,
  Job,
  Department,
  MaterialChunk,
  MaterialVersion,
  Subject,
  SubjectChapter,
  SubjectOffering,
  BankOperationJob,
} from '../../../../types'
import {
  bulkReviewBankQuestions,
  createBankRelease,
  createBankVersion,
  createDepartment,
  createSubject,
  createSubjectChapter,
  createSubjectOffering,
  deleteDepartment,
  deleteSubject,
  deleteSubjectChapter,
  deleteSubjectOffering,
  deleteMaterialVersion,
  enqueueGenerateFromBankVersion,
  getBankDashboardOverview,
  getBankOperationJob,
  getBankOperationJobs,
  getAuditLogs,
  getJobs,
  searchBankDashboard,
  getDepartmentSummaries,
  getSubjectSummaries,
  getSubjectVersionSummaries,
  getChapterSummaries,
  getBankMaterialChunks,
  getBankReleaseReadiness,
  getBankReleases,
  getBankReleasePublishAudit,
  getBankVersionQuestion,
  getBankVersionQuestionPage,
  getBankVersions,
  getCourseQuizInstances,
  getDepartments,
  getDepartment,
  getMaterialVersions,
  getSubjectChapter,
  getSubjectChapters,
  getSubjectOffering,
  getSubjectOfferings,
  getSubject,
  getSubjects,
  markBankDiffResolved,
  previewBankVersionDiff,
  previewGenerateFromBankVersion,
  recheckBankMaterialCarryOver,
  publishBankRelease,
  reviewBankQuestion,
  rollbackCourseQuizInstance,
  enqueueBankMaterialUpload,
  updateBankQuestion,
  updateDepartment,
  updateSubject,
  updateSubjectChapter,
  updateSubjectOffering,
} from '../../../../lib/api'
import {
  TERMS,
  chapterDisplayName,
  normalizeLessonInput,
  buildChapterTitle,
  statusLabel,
  statusClass,
  useBankData,
  useAsyncMessage,
  Breadcrumb,
  Toolbar,
  SearchActionBar,
  Modal,
  EntityActions,
  matchesSearch,
  reviewStatusText,
  reviewStatusClass,
  StatLine,
  QuickSearchBox,
  questionStats,
  nextReleaseText,
  bankAnswerRows,
  bankQuestionErrorMessage,
  isQuestionWaitingForReview,
  BankQuestionEditForm,
  BankChartRow,
  toBankQuestionEditForm,
  BankBarChart,
  BankStackedChart,
  countRows,
  auditActionText,
} from '../shared'

type ChapterLongOperation = {
  id: string
  jobId: string
  bankVersionId: string
  chapterId: string
  type: 'generate' | 'material_upload'
  label: string
  successMessage: string
  questionCount?: number
  fileName?: string
  createdAt: number
}

type PopupMessage = { type: 'info' | 'success' | 'warning' | 'danger'; text: string }
type ChapterActionKey =
  | 'prepare_workspace'
  | 'generate_preview'
  | 'generate_enqueue'
  | 'material_upload_enqueue'
  | 'material_delete'
  | 'diff_check'
  | 'diff_apply'
  | 'release_create'
  | 'release_publish'
  | 'release_audit'
  | 'bulk_approve'
  | 'question_review'
  | 'question_edit'
  | 'question_reject'

const OPERATION_STEPS: Record<ChapterLongOperation['type'], string[]> = {
  material_upload: ['Tiếp nhận', 'Bóc tách học liệu', 'Chuẩn hóa văn bản', 'Đồng bộ'],
  generate: ['Dựng ngữ cảnh', 'Sinh câu hỏi', 'Đối chiếu trùng lặp', 'Ghi bộ câu hỏi'],
}

function BusyLabel({ text }: { text: string }) {
  return <span className="inline-busy-label"><span className="spinner tiny" aria-hidden="true" />{text}</span>
}

function operationDetailText(operation: ChapterLongOperation) {
  if (operation.type === 'material_upload') return 'Đang bóc tách nội dung, chuẩn hóa văn bản và cập nhật danh sách tài liệu.'
  return 'Đang dựng ngữ cảnh, sinh ứng viên câu hỏi và đối chiếu trùng lặp trước khi ghi vào ngân hàng.'
}

function ChapterOperationStatus({ operation }: { operation: ChapterLongOperation }) {
  const steps = OPERATION_STEPS[operation.type]
  return <div className="chapter-operation-status" role="status" aria-live="polite" aria-busy="true">
    <div className="chapter-operation-status__head"><div><b>{operation.label}</b><small>{operationDetailText(operation)}</small></div><span className="inline-busy-label"><span className="spinner tiny" aria-hidden="true" />Đang chạy nền</span></div>
    <div className="chapter-operation-progress" role="progressbar" aria-label="Tiến trình xử lý đang chạy"><span /></div>
    <div className="chapter-operation-steps">{steps.map((step) => <span key={step}>{step}</span>)}</div>
  </div>
}

const ACTIVE_OPERATION_STATUSES = ['queued', 'running']
const CHAPTER_OPERATION_TYPES = ['material_extract', 'bank_generate']

function jobCreatedAt(job: BankOperationJob) {
  const raw = job.created_at || job.enqueued_at || job.updated_at
  const parsed = raw ? Date.parse(raw) : NaN
  return Number.isFinite(parsed) ? parsed : Date.now()
}

function buildChapterLongOperationFromJob(job: BankOperationJob, chapterId: string): ChapterLongOperation | null {
  const request = job.request || {}
  const bankVersionId = job.bank_version_id || job.target_id || ''
  if (!bankVersionId) return null

  if (job.operation_type === 'material_extract') {
    const fileName = typeof request.filename === 'string' ? request.filename : (typeof request.title === 'string' ? request.title : undefined)
    return {
      id: `${job.id}:material_upload`,
      jobId: job.id,
      bankVersionId,
      chapterId,
      type: 'material_upload',
      label: `Hệ thống đang tiếp nhận học liệu${fileName ? ` ${fileName}` : ''} và kiểm tra định dạng tệp. Trạng thái sẽ tự cập nhật tại đây.`,
      successMessage: 'Hệ thống đã ghi nhận tài liệu. Bạn có thể tiếp tục bước tạo câu hỏi.',
      fileName,
      createdAt: jobCreatedAt(job),
    }
  }

  if (job.operation_type === 'bank_generate') {
    const rawCount = request.question_count
    const questionCount = typeof rawCount === 'number' ? rawCount : Number(rawCount || 0)
    const countText = Number.isFinite(questionCount) && questionCount > 0 ? `${questionCount} câu hỏi` : 'câu hỏi'
    return {
      id: `${job.id}:generate`,
      jobId: job.id,
      bankVersionId,
      chapterId,
      type: 'generate',
      label: `Hệ thống đang tạo ${countText} từ học liệu của bài này. Trạng thái sẽ tự cập nhật tại đây.`,
      successMessage: Number.isFinite(questionCount) && questionCount > 0
        ? `Hệ thống đã tạo xong ${questionCount} câu hỏi và đồng bộ danh sách bên dưới.`
        : 'Hệ thống đã tạo xong câu hỏi và đồng bộ danh sách bên dưới.',
      questionCount: Number.isFinite(questionCount) && questionCount > 0 ? questionCount : undefined,
      createdAt: jobCreatedAt(job),
    }
  }

  return null
}

function errorText(error: unknown, fallback = 'Thao tác thất bại. Vui lòng thử lại.') {
  if (error instanceof Error && error.message) return error.message
  if (typeof error === 'string' && error.trim()) return error
  return fallback
}

function operationResultMessage(result: Record<string, unknown> | null | undefined, fallback: string) {
  const userMessage = typeof result?.user_message === 'string' ? result.user_message : ''
  const message = typeof result?.message === 'string' ? result.message : ''
  return userMessage || message || fallback
}

function diffImpactGroups(diff: BankVersionDiffPreview | null) {
  const summary = diff?.summary
  if (!summary) return { critical: [] as string[], warning: [] as string[], info: [] as string[] }
  const similarity = Number(summary.material_similarity ?? diff?.material_similarity ?? 0)
  const critical: string[] = []
  const warning: string[] = []
  const info: string[] = []

  if (summary.removed_concept_count > 0) critical.push(`${summary.removed_concept_count} concept nguồn không còn trong tài liệu mới; các câu hỏi bám vào concept này nên bị bỏ hoặc review lại.`)
  if (summary.retire_candidate_count > 0) critical.push(`${summary.retire_candidate_count} câu nên bỏ vì không còn căn cứ rõ trong tài liệu hiện tại.`)
  if (summary.review_candidate_count > 0) warning.push(`${summary.review_candidate_count} câu cần giáo viên xem lại vì concept/tài liệu đã thay đổi hoặc hệ thống chưa đủ chắc để giữ tự động.`)
  if (summary.new_concept_count > 0) warning.push(`${summary.new_concept_count} concept mới xuất hiện; nên sinh/bổ sung câu hỏi để phủ nội dung mới.`)
  if (summary.changed_concept_count > 0) warning.push(`${summary.changed_concept_count} concept có nội dung thay đổi; cần rà lại câu hỏi liên quan.`)
  if (summary.carry_over_candidate_count > 0) info.push(`${summary.carry_over_candidate_count} câu có thể giữ vì concept ổn định hoặc tài liệu đủ giống.`)
  if (summary.already_exists_count > 0) info.push(`${summary.already_exists_count} câu đã tồn tại trong version hiện tại nên không cần tạo lại.`)
  if (similarity < 0.72) critical.push(`Độ giống tài liệu chỉ khoảng ${Math.round(similarity * 100)}%; không nên giữ câu cũ hàng loạt.`)
  if (!critical.length && !warning.length) info.push('Không phát hiện thay đổi có rủi ro cao so với Bank Version gốc. Không cần xử lý thêm nếu giáo viên đã kiểm tra nội dung.')
  return { critical, warning, info }
}

function diffActionHint(diff: BankVersionDiffPreview | null) {
  const summary = diff?.summary
  if (!summary) return 'Chưa có kết quả kiểm tra.'
  if (summary.retire_candidate_count || summary.review_candidate_count || summary.removed_concept_count) return 'Nên bấm “Áp dụng xử lý tự động” để hệ thống tự loại câu clone không còn căn cứ, rồi giáo viên review các câu còn lại.'
  if (summary.new_concept_count || summary.changed_concept_count) return 'Nên bổ sung/sinh thêm câu hỏi cho concept mới hoặc concept đã thay đổi.'
  return 'Không cần đồng bộ mù. Có thể tiếp tục duyệt/chốt bộ đề nếu câu hỏi đã đạt.'
}

export function ChapterWorkspacePage({ chapterId }: { chapterId: string }) {
  const { headers, can } = useBankData()
  const searchParams = useSearchParams()
  const { message, setMessage, busy, busyLabel, run } = useAsyncMessage()
  const [departments, setDepartments] = useState<Department[]>([])
  const [subjects, setSubjects] = useState<Subject[]>([])
  const [offerings, setOfferings] = useState<SubjectOffering[]>([])
  const [chapters, setChapters] = useState<SubjectChapter[]>([])
  const [bankVersions, setBankVersions] = useState<BankVersion[]>([])
  const [releases, setReleases] = useState<BankRelease[]>([])
  const [materials, setMaterials] = useState<MaterialVersion[]>([])
  const [questions, setQuestions] = useState<BankVersionQuestion[]>([])
  const [questionCursor, setQuestionCursor] = useState<{ created_at: string; id: string } | null>(null)
  const [questionHasNext, setQuestionHasNext] = useState(false)
  const [questionLoadingMore, setQuestionLoadingMore] = useState(false)
  const [readiness, setReadiness] = useState<BankReleaseReadiness | null>(null)
  const [releaseAudit, setReleaseAudit] = useState<BankReleasePublishAudit | null>(null)
  const [file, setFile] = useState<File | null>(null)
  const [generateCount, setGenerateCount] = useState('10')
  const [difficultyEasy, setDifficultyEasy] = useState('50')
  const [difficultyMedium, setDifficultyMedium] = useState('30')
  const [difficultyHard, setDifficultyHard] = useState('20')
  const [autoCreateTried, setAutoCreateTried] = useState(false)
  const [materialView, setMaterialView] = useState<{ material: MaterialVersion; chunks: MaterialChunk[] } | null>(null)
  const [diffPreview, setDiffPreview] = useState<BankVersionDiffPreview | null>(null)
  const [materialRecheckResult, setMaterialRecheckResult] = useState<BankMaterialRecheckResult | null>(null)
  const [generatePreview, setGeneratePreview] = useState<BankGeneratePreview | null>(null)
  const [editingQuestion, setEditingQuestion] = useState<BankVersionQuestion | null>(null)
  const [editForm, setEditForm] = useState<BankQuestionEditForm | null>(null)
  const [rejectingQuestion, setRejectingQuestion] = useState<BankVersionQuestion | null>(null)
  const [rejectReason, setRejectReason] = useState('')
  const [materialManagerOpen, setMaterialManagerOpen] = useState(false)
  const [generateManagerOpen, setGenerateManagerOpen] = useState(false)
  const [popupMessage, setPopupMessage] = useState<PopupMessage | null>(null)
  const [submittingLabel, setSubmittingLabel] = useState('')
  const [actionBusy, setActionBusy] = useState<ChapterActionKey | null>(null)
  const [activeOperation, setActiveOperation] = useState<ChapterLongOperation | null>(null)
  const [questionStatusFilter, setQuestionStatusFilter] = useState(() => searchParams.get('status') || 'all')
  const [questionDifficultyFilter, setQuestionDifficultyFilter] = useState(() => searchParams.get('difficulty') || 'all')
  const [questionSort, setQuestionSort] = useState('needs_review')

  const load = async () => {
    const chapter = await getSubjectChapter(headers, chapterId)
    const [subject, offering, nextBankVersions, nextReleases] = await Promise.all([
      getSubject(headers, chapter.subject_id),
      chapter.subject_offering_id ? getSubjectOffering(headers, chapter.subject_offering_id) : Promise.resolve(null),
      getBankVersions(headers, chapterId),
      getBankReleases(headers, undefined, chapterId),
    ])
    const department = await getDepartment(headers, subject.department_id)
    setDepartments([department]); setSubjects([subject]); setOfferings(offering ? [offering] : []); setChapters([chapter]); setBankVersions(nextBankVersions); setReleases(nextReleases)
  }

  const selectedBankVersion = bankVersions[0] || null
  const loadDetail = async (bankVersionId?: string | null) => {
    if (!bankVersionId) {
      setMaterials([])
      setQuestions([])
      setQuestionCursor(null)
      setQuestionHasNext(false)
      setReadiness(null)
      setReleaseAudit(null)
      return
    }
    const [nextMaterials, questionPage, nextReadiness] = await Promise.all([
      getMaterialVersions(headers, bankVersionId).catch(() => []),
      getBankVersionQuestionPage(headers, bankVersionId, { limit: 100 }).catch(() => ({ items: [], has_next: false, next_cursor: null } as any)),
      getBankReleaseReadiness(headers, bankVersionId).catch(() => null),
    ])
    setMaterials(nextMaterials.filter((item) => item.status !== 'deleted'))
    setQuestions(questionPage.items || [])
    setQuestionCursor(questionPage.next_cursor?.created_at && questionPage.next_cursor?.id ? { created_at: questionPage.next_cursor.created_at, id: questionPage.next_cursor.id } : null)
    setQuestionHasNext(Boolean(questionPage.has_next))
    setReadiness(nextReadiness)
  }

  const loadMoreQuestions = async () => {
    if (!selectedBankVersion || !questionCursor || questionLoadingMore) return
    setQuestionLoadingMore(true)
    try {
      const page = await getBankVersionQuestionPage(headers, selectedBankVersion.id, {
        limit: 100,
        cursorCreatedAt: questionCursor.created_at,
        cursorId: questionCursor.id,
      })
      setQuestions((current) => {
        const seen = new Set(current.map((item) => item.id))
        const extra = (page.items || []).filter((item) => !seen.has(item.id))
        return [...current, ...extra]
      })
      setQuestionCursor(page.next_cursor?.created_at && page.next_cursor?.id ? { created_at: page.next_cursor.created_at, id: page.next_cursor.id } : null)
      setQuestionHasNext(Boolean(page.has_next))
    } finally {
      setQuestionLoadingMore(false)
    }
  }

  useEffect(() => { load().catch(() => null) }, [chapterId]) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { loadDetail(selectedBankVersion?.id).catch(() => null) }, [selectedBankVersion?.id]) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    const nextStatus = searchParams.get('status') || 'all'
    const nextDifficulty = searchParams.get('difficulty') || 'all'
    setQuestionStatusFilter(nextStatus === 'overdue' ? 'pending_review' : nextStatus)
    setQuestionDifficultyFilter(nextDifficulty)
  }, [searchParams])

  useEffect(() => {
    if (!selectedBankVersion?.id) return
    let canceled = false

    const loadActiveOperationFromServer = async () => {
      try {
        const pages = await Promise.all(ACTIVE_OPERATION_STATUSES.map((status) => getBankOperationJobs(headers, {
          status,
          targetType: 'bank_version',
          targetId: selectedBankVersion.id,
          page: 1,
          pageSize: 20,
        })))
        if (canceled) return
        const activeJob = pages
          .flatMap((page) => page.items || [])
          .filter((job) => CHAPTER_OPERATION_TYPES.includes(job.operation_type))
          .sort((a, b) => jobCreatedAt(b) - jobCreatedAt(a))[0]
        const operation = activeJob ? buildChapterLongOperationFromJob(activeJob, chapterId) : null
        setActiveOperation((current) => {
          if (current?.jobId && activeJob?.id === current.jobId) return current
          return operation
        })
      } catch {
        // Trạng thái vận hành dài là dữ liệu phụ trợ cho UX. Nếu không đọc được,
        // không chặn người dùng làm việc với phần còn lại của trang.
      }
    }

    loadActiveOperationFromServer().catch(() => null)
    return () => { canceled = true }
  }, [selectedBankVersion?.id, chapterId]) // eslint-disable-line react-hooks/exhaustive-deps

  const setRunningOperation = (operation: ChapterLongOperation) => {
    setActiveOperation(operation)
  }

  const clearRunningOperation = () => {
    setActiveOperation(null)
  }

  const isActionBusy = (key: ChapterActionKey) => actionBusy === key
  const runAction = async (key: ChapterActionKey, work: () => Promise<unknown>, ok: string, after?: () => Promise<void>, fail = 'Thao tác thất bại. Vui lòng thử lại.') => {
    if (actionBusy) return
    setActionBusy(key)
    try {
      await work()
      setMessage(ok)
      if (after) await after()
    } catch (error) {
      const text = errorText(error, fail)
      setPopupMessage({ type: 'danger', text })
      setMessage(text)
    } finally {
      setActionBusy(null)
    }
  }

  useEffect(() => {
    if (!activeOperation?.jobId) return
    let canceled = false
    let timer: ReturnType<typeof setTimeout> | null = null

    const poll = async () => {
      try {
        const job = await getBankOperationJob(headers, activeOperation.jobId)
        if (canceled) return
        if (['completed', 'failed', 'canceled'].includes(job.status)) {
          clearRunningOperation()
          const result = (job.result || {}) as Record<string, unknown>
          if (job.status === 'completed') {
            const text = operationResultMessage(result, activeOperation.successMessage)
            setPopupMessage({ type: 'success', text })
            setMessage(text)
            await refreshCurrent()
            if (activeOperation.type === 'material_upload' && result.diff_required && result.diff_base_bank_version_id && activeOperation.bankVersionId) {
              await runDiffNow(activeOperation.bankVersionId, String(result.diff_base_bank_version_id))
            }
          } else {
            const text = operationResultMessage(result, job.error_message || job.progress_label || 'Việc xử lý thất bại. Vui lòng thử lại hoặc xem trang Tiến trình xử lý.')
            setPopupMessage({ type: 'danger', text })
            setMessage(text)
          }
          return
        }
      } catch (error) {
        if (!canceled) {
          const text = errorText(error, 'Không kiểm tra được trạng thái việc xử lý. Vui lòng tải lại trang hoặc xem Tiến trình xử lý.')
          setPopupMessage({ type: 'warning', text })
          setMessage(text)
        }
      }
      if (!canceled) timer = setTimeout(poll, 1500)
    }

    poll()
    return () => {
      canceled = true
      if (timer) clearTimeout(timer)
    }
  }, [activeOperation?.jobId]) // eslint-disable-line react-hooks/exhaustive-deps


  const chapter = chapters.find((item) => item.id === chapterId)
  const offering = offerings.find((item) => item.id === chapter?.subject_offering_id)
  const subject = subjects.find((item) => item.id === chapter?.subject_id)
  const department = departments.find((item) => item.id === subject?.department_id)
  const stats = questionStats(questions)
  const metadata = selectedBankVersion?.metadata_json || {}
  const diffRequired = Boolean((metadata as any).diff_required)
  const diffBaseBankVersionId = String((metadata as any).diff_base_bank_version_id || selectedBankVersion?.based_on_version_id || '')
  const publishedRelease = releases.find((item) => item.status === 'published')
  const latestRelease = releases[0]

  const refreshReleaseAudit = async (releaseId?: string | null) => {
    if (!releaseId) {
      setReleaseAudit(null)
      return
    }
    try {
      const audit = await getBankReleasePublishAudit(headers, releaseId)
      setReleaseAudit(audit)
    } catch {
      setReleaseAudit(null)
    }
  }

  useEffect(() => {
    refreshReleaseAudit(latestRelease?.id).catch(() => null)
  }, [latestRelease?.id]) // eslint-disable-line react-hooks/exhaustive-deps
  const chapterPublished = Boolean(
    publishedRelease
    || selectedBankVersion?.status === 'published'
    || selectedBankVersion?.published_at
    || (readiness?.status === 'published')
    || Boolean((readiness?.stats as any)?.is_published)
    || Number((readiness?.stats as any)?.published_release_count || 0) > 0
  )
  const numericGenerateCount = Number(generateCount || 0)
  const chapterQuestionLimit = Number((readiness?.stats as any)?.chapter_question_limit || 100)
  const usedQuestionCount = Number((readiness?.stats as any)?.chapter_total_count ?? stats.total)
  const unresolvedQuestionCount = Number((readiness?.stats as any)?.unresolved_count ?? (stats.pending + stats.draftError))
  const releaseReviewBlocked = unresolvedQuestionCount > 0
  const remainingQuota = Math.max(0, chapterQuestionLimit - usedQuestionCount)
  const difficultyTotal = Number(difficultyEasy || 0) + Number(difficultyMedium || 0) + Number(difficultyHard || 0)
  const overQuota = numericGenerateCount > remainingQuota
  const invalidDifficulty = difficultyTotal !== 100
  const canGenerateNow = Boolean(!chapterPublished && selectedBankVersion && materials.length && can('generate_questions') && !overQuota && !invalidDifficulty && numericGenerateCount >= 1 && remainingQuota > 0)
  const materialOperationBusy = activeOperation?.type === 'material_upload'
  const generateOperationBusy = activeOperation?.type === 'generate'
  const longOperationBusy = Boolean(activeOperation)
  const activeOperationMessage = activeOperation?.label || ''
  const filteredQuestions = useMemo(() => {
    const reviewRank = (q: BankVersionQuestion) => {
      if (q.status === 'draft_error') return 0
      if (q.status === 'pending_review' || q.status === 'needs_review') return 1
      if (q.status === 'approved') return 2
      if (q.status === 'rejected') return 3
      if (q.status === 'published') return 4
      return 5
    }
    const difficultyRank = (difficulty?: string | null) => ({ easy: 1, medium: 2, hard: 3 } as Record<string, number>)[String(difficulty || '').toLowerCase()] || 9
    const result = questions.filter((question) => {
      const statusOk = questionStatusFilter === 'all'
        || (questionStatusFilter === 'needs_action' && isQuestionWaitingForReview(question))
        || question.status === questionStatusFilter
      const difficultyOk = questionDifficultyFilter === 'all' || String(question.difficulty || '').toLowerCase() === questionDifficultyFilter
      return statusOk && difficultyOk
    })
    return result.sort((a, b) => {
      if (questionSort === 'difficulty') return difficultyRank(a.difficulty) - difficultyRank(b.difficulty)
      if (questionSort === 'quality_low') return Number(a.quality_score || 0) - Number(b.quality_score || 0)
      if (questionSort === 'quality_high') return Number(b.quality_score || 0) - Number(a.quality_score || 0)
      return reviewRank(a) - reviewRank(b)
    })
  }, [questions, questionStatusFilter, questionDifficultyFilter, questionSort])

  const ensureBankVersion = async () => {
    if (!chapter) throw new Error('Không tìm thấy bài')
    if (selectedBankVersion) return selectedBankVersion
    return createBankVersion(headers, { subject_id: chapter.subject_id, subject_offering_id: chapter.subject_offering_id, chapter_id: chapter.id, version_code: 'v1.0', title: `${offering?.code || ''} - ${chapterDisplayName(chapter)}`.trim(), change_note: 'Khởi tạo bộ câu hỏi cho bài' })
  }

  useEffect(() => {
    if (chapter && !chapterPublished && !selectedBankVersion && !autoCreateTried && can('edit_questions')) {
      setAutoCreateTried(true)
      run(async () => { await ensureBankVersion() }, 'Đã chuẩn bị workspace cho bài', load).catch(() => null)
    }
  }, [chapter?.id, selectedBankVersion?.id, autoCreateTried]) // eslint-disable-line react-hooks/exhaustive-deps

  const refreshCurrent = async () => {
    await load()
    await loadDetail(selectedBankVersion?.id)
  }

  const openMaterial = async (material: MaterialVersion) => {
    if (!selectedBankVersion) return
    const chunks = await getBankMaterialChunks(headers, selectedBankVersion.id, material.id)
    setMaterialView({ material, chunks })
  }

  const runDiffNow = async (bankVersionId: string, baseId: string) => {
    const diff = await previewBankVersionDiff(headers, bankVersionId, { base_bank_version_id: baseId, persist: true })
    setMaterialRecheckResult(null)
    setDiffPreview(diff)
  }

  const applyMaterialRecheck = async () => {
    if (!selectedBankVersion) return
    const result = await recheckBankMaterialCarryOver(headers, selectedBankVersion.id)
    setMaterialRecheckResult(result)
    setPopupMessage({ type: 'success', text: result.user_message || result.message || 'Đã áp dụng xử lý tự động sau khi kiểm tra thay đổi tài liệu.' })
    await refreshCurrent()
  }

  const rejectQuestionsByPreviousIds = async (sourceIds: string[], note: string) => {
    if (!selectedBankVersion || !sourceIds.length) return
    const set = new Set(sourceIds)
    const ids = questions.filter((q) => q.previous_question_id && set.has(q.previous_question_id) && q.status !== 'rejected' && q.status !== 'published').map((q) => q.id)
    if (ids.length) await bulkReviewBankQuestions(headers, selectedBankVersion.id, { action: 'reject', question_ids: ids, note })
  }

  const rejectAllCarryOver = async () => {
    if (!selectedBankVersion) return
    const ids = questions.filter((q) => q.is_carry_over && q.status !== 'rejected' && q.status !== 'published').map((q) => q.id)
    if (ids.length) await bulkReviewBankQuestions(headers, selectedBankVersion.id, { action: 'reject', question_ids: ids, note: 'Không giữ câu hỏi từ tài liệu cũ sau khi tài liệu thay đổi' })
    await markBankDiffResolved(headers, selectedBankVersion.id, { note: 'Không giữ câu hỏi cũ sau khi đổi tài liệu' })
    setDiffPreview(null)
    await refreshCurrent()
  }

  const keepReusableOnly = async () => {
    if (!selectedBankVersion || !diffPreview) return
    await rejectQuestionsByPreviousIds([...(diffPreview.retire_candidates || []), ...(diffPreview.review_candidates || [])], 'Bỏ câu không còn chắc phù hợp sau khi tài liệu thay đổi')
    await markBankDiffResolved(headers, selectedBankVersion.id, { note: 'Giữ câu phù hợp, bỏ câu không còn chắc phù hợp' })
    setDiffPreview(null)
    await refreshCurrent()
  }

  const startEditQuestion = async (question: BankVersionQuestion) => {
    if (!selectedBankVersion || chapterPublished) return
    const detail = await getBankVersionQuestion(headers, selectedBankVersion.id, question.id).catch(() => question)
    setEditingQuestion(detail)
    setEditForm(toBankQuestionEditForm(detail))
  }

  const updateEditForm = <K extends keyof BankQuestionEditForm>(key: K, value: BankQuestionEditForm[K]) => {
    setEditForm((current) => current ? { ...current, [key]: value } : current)
  }

  const saveEditedQuestion = async () => {
    if (!selectedBankVersion || chapterPublished || !editingQuestion || !editForm) return
    await run(async () => {
      await updateBankQuestion(headers, selectedBankVersion.id, editingQuestion.id, { ...editForm, note: 'Giáo viên sửa câu hỏi trong workspace bài' })
      setEditingQuestion(null)
      setEditForm(null)
    }, 'Đã lưu câu hỏi', refreshCurrent)
  }



  const openRejectQuestion = async (question: BankVersionQuestion) => {
    if (chapterPublished) return
    const detail = selectedBankVersion ? await getBankVersionQuestion(headers, selectedBankVersion.id, question.id).catch(() => question) : question
    setRejectingQuestion(detail)
    setRejectReason(detail.status === 'draft_error' ? 'Bỏ câu lỗi: ' : '')
  }

  const confirmRejectQuestion = async () => {
    if (!selectedBankVersion || chapterPublished || !rejectingQuestion || !rejectReason.trim()) return
    await run(async () => {
      await reviewBankQuestion(headers, selectedBankVersion.id, rejectingQuestion.id, { action: 'reject', note: rejectReason.trim() })
      setRejectingQuestion(null)
      setRejectReason('')
    }, 'Đã bỏ câu hỏi', refreshCurrent)
  }
  const generationPayload = { question_count: numericGenerateCount, target_question_count: chapterQuestionLimit, difficulty_easy: difficultyEasy === '' ? 50 : Number(difficultyEasy), difficulty_medium: difficultyMedium === '' ? 30 : Number(difficultyMedium), difficulty_hard: difficultyHard === '' ? 20 : Number(difficultyHard) }

  const openGenerateConfirm = async () => {
    if (!selectedBankVersion || chapterPublished || isActionBusy('generate_preview') || generateOperationBusy || materialOperationBusy) return
    await runAction('generate_preview', async () => {
      const preview = await previewGenerateFromBankVersion(headers, selectedBankVersion.id, generationPayload)
      setGeneratePreview(preview)
    }, 'Đã tính chi phí dự kiến', undefined, 'Không tính được chi phí dự kiến. Vui lòng thử lại.')
  }

  const confirmGenerateQuestions = async () => {
    if (!selectedBankVersion || chapterPublished || !generatePreview || generateOperationBusy || materialOperationBusy || isActionBusy('generate_enqueue')) return
    const questionCount = generatePreview.question_count || numericGenerateCount
    setPopupMessage(null)
    setActionBusy('generate_enqueue')
    try {
      const queued = await enqueueGenerateFromBankVersion(headers, selectedBankVersion.id, generationPayload)
      const label = `Hệ thống đang tạo ${questionCount} câu hỏi từ học liệu của bài này. Trạng thái sẽ tự cập nhật tại đây.`
      setRunningOperation({
        id: `${queued.job.id}:generate`,
        jobId: queued.job.id,
        bankVersionId: selectedBankVersion.id,
        chapterId,
        type: 'generate',
        label,
        successMessage: `Hệ thống đã tạo xong ${questionCount} câu hỏi và đồng bộ danh sách bên dưới.`,
        questionCount,
        createdAt: Date.now(),
      })
      setGeneratePreview(null)
      setGenerateManagerOpen(false)
      setMessage(label)
    } catch (error) {
      const text = errorText(error, 'Không tạo được câu hỏi. Vui lòng kiểm tra tài liệu hoặc thử lại.')
      setPopupMessage({ type: 'danger', text })
      setMessage(text)
    } finally {
      setActionBusy(null)
      setSubmittingLabel('')
    }
  }

  const uploadSelectedMaterial = async () => {
    if (!file || !selectedBankVersion || chapterPublished || materialOperationBusy || generateOperationBusy || isActionBusy('material_upload_enqueue')) return
    const selectedFile = file
    setPopupMessage(null)
    setActionBusy('material_upload_enqueue')
    try {
      const queued = await enqueueBankMaterialUpload(headers, selectedBankVersion.id, selectedFile, { title: selectedFile.name, change_type: diffBaseBankVersionId ? 'updated_after_clone' : 'initial', replace_existing: false })
      const label = `Hệ thống đang tiếp nhận học liệu và kiểm tra định dạng tệp ${selectedFile.name}. Trạng thái sẽ tự cập nhật tại đây.`
      setRunningOperation({
        id: `${queued.job.id}:material_upload`,
        jobId: queued.job.id,
        bankVersionId: selectedBankVersion.id,
        chapterId,
        type: 'material_upload',
        label,
        successMessage: 'Hệ thống đã ghi nhận tài liệu. Bạn có thể tiếp tục bước tạo câu hỏi.',
        fileName: selectedFile.name,
        createdAt: Date.now(),
      })
      setFile(null)
      setMessage(label)
    } catch (error) {
      const text = errorText(error, 'Không thêm được tài liệu. Vui lòng kiểm tra file hoặc thử lại.')
      setPopupMessage({ type: 'danger', text })
      setMessage(text)
    } finally {
      setActionBusy(null)
      setSubmittingLabel('')
    }
  }

  const materialPreviewChunks = (materialView?.chunks || []).slice(0, 80)
  const materialPreviewText = materialPreviewChunks.map((chunk, index) => `Đoạn ${index + 1}
${chunk.content}`).join('\n\n')

  return <div className="page-stack bank-multipage">
    <Breadcrumb items={[{ label: 'Bộ môn', href: '/bank/departments' }, { label: department?.name || 'Bộ môn', href: department ? `/bank/departments/${department.id}/subjects` : undefined }, { label: subject?.code || 'Môn', href: subject ? `/bank/subjects/${subject.id}/versions` : undefined }, { label: offering?.code || 'Version môn', href: offering ? `/bank/subject-versions/${offering.id}/chapters` : undefined }, { label: chapterDisplayName(chapter) }]} />
    {message ? <div className="alert info">{message}</div> : null}
    {activeOperation ? <ChapterOperationStatus operation={activeOperation} /> : null}
    {chapterPublished ? <div className="alert success"><b>Bài đã publish.</b> Các thao tác sửa tài liệu, tạo câu hỏi, duyệt/bỏ câu, kiểm tra thay đổi và chốt lại đã được khóa. Muốn thay đổi, hãy clone/tạo version mới.</div> : null}
    {!chapterPublished && diffRequired ? <div className="alert warning"><b>Tài liệu đã thay đổi.</b> Hệ thống sẽ kiểm tra khác biệt và hiển thị kết quả để giáo viên xác nhận.</div> : null}
    {!chapterPublished && unresolvedQuestionCount > 0 ? <div className="alert warning"><b>Còn câu chưa xử lý.</b> Hiện có {stats.pending} câu chờ duyệt và {stats.draftError} câu lỗi. Phải duyệt, sửa hoặc bỏ hết thì mới chốt bộ đề được.</div> : null}

    <section className="card chapter-command-bar">
      <div>
        <div className="eyebrow">Bài học</div>
        <h2>{chapterDisplayName(chapter)}</h2>
        <p className="helper">Quản lý tài liệu, tạo câu hỏi, duyệt câu và chốt bộ đề cho bài này.</p>
        <div className="chapter-inline-stats" aria-label="Tóm tắt bài học">
          <span className={materialOperationBusy ? 'is-busy' : ''}>Tài liệu <b>{materials.length}</b>{materialOperationBusy ? <em><BusyLabel text="Đang up" /></em> : null}</span>
          <span>Tổng câu <b>{usedQuestionCount}/{chapterQuestionLimit}</b><small>Còn {remainingQuota}</small></span>
          <span>Đã duyệt <b>{stats.approved}</b></span>
          <span>Chờ duyệt <b>{stats.pending}</b></span>
          <span>Bị loại <b>{stats.rejected}</b></span>
          <span>Nhóm KT <b>{stats.families}</b></span>
          <span>Bộ đề <b>{publishedRelease ? 'Đã đưa lên CMS' : latestRelease ? 'Đã chốt' : 'Chưa chốt'}</b></span>
        </div>
      </div>
      <div className="button-row no-margin">
        <button className="btn secondary chapter-action-button material" disabled={!selectedBankVersion} onClick={() => setMaterialManagerOpen(true)}>{materialOperationBusy ? <BusyLabel text="Đang up tài liệu" /> : `Tài liệu (${materials.length})`}</button>
        {!chapterPublished && can('generate_questions') ? <button className="btn chapter-action-button generate" disabled={!selectedBankVersion} onClick={() => setGenerateManagerOpen(true)}>{generateOperationBusy ? <BusyLabel text="Đang tạo câu hỏi" /> : 'Tạo câu hỏi'}</button> : null}
        <button className="btn secondary chapter-action-button review" onClick={() => document.getElementById('bank-question-list')?.scrollIntoView({ behavior: 'smooth' })}>{chapterPublished ? 'Xem câu hỏi' : 'Duyệt câu hỏi'}</button>
        {!chapterPublished ? <button className="btn secondary chapter-action-button diff" disabled={isActionBusy('diff_check') || longOperationBusy || !selectedBankVersion || !diffBaseBankVersionId} onClick={() => runAction('diff_check', async () => {
          if (!selectedBankVersion) return
          await runDiffNow(selectedBankVersion.id, diffBaseBankVersionId)
        }, 'Hệ thống đã kiểm tra khác biệt tài liệu.', refreshCurrent, 'Không kiểm tra được khác biệt tài liệu. Vui lòng thử lại.')}>{isActionBusy('diff_check') ? <BusyLabel text="Đang kiểm tra" /> : 'Kiểm tra thay đổi'}</button> : null}
        {latestRelease ? <button className="btn secondary chapter-action-button release-audit" disabled={isActionBusy('release_audit')} onClick={() => runAction('release_audit', async () => { await refreshReleaseAudit(latestRelease.id) }, 'Đã kiểm tra trạng thái bộ đề.', undefined, 'Không kiểm tra được trạng thái bộ đề.')}>{isActionBusy('release_audit') ? <BusyLabel text="Đang kiểm tra" /> : 'Kiểm tra bộ đề'}</button> : null}
        {can('publish_questions') ? (chapterPublished ? <button className="btn secondary chapter-action-button published" disabled>Đã đưa lên CMS</button> : !latestRelease ? <button className="btn" disabled={isActionBusy('release_create') || longOperationBusy || !selectedBankVersion || !readiness?.can_create_release || releaseReviewBlocked} title={releaseReviewBlocked ? 'Phải duyệt hoặc bỏ hết tất cả câu hỏi trước khi chốt bộ đề.' : undefined} onClick={() => runAction('release_create', async () => {
          if (!selectedBankVersion) return
          await createBankRelease(headers, { bank_version_id: selectedBankVersion.id, include_approved_questions: true })
        }, 'Hệ thống đã chốt bộ đề. Bạn có thể đưa lên CMS khi sẵn sàng.', refreshCurrent, 'Không chốt được bộ đề. Vui lòng kiểm tra câu hỏi còn chờ xử lý.')}>{isActionBusy('release_create') ? <BusyLabel text="Đang chốt" /> : 'Chốt bộ đề'}</button> : latestRelease.status !== 'published' ? <button className="btn" disabled={isActionBusy('release_publish') || longOperationBusy} onClick={() => runAction('release_publish', async () => { await publishBankRelease(headers, latestRelease.id, {}) }, 'Hệ thống đã đưa lên CMS lên CMS.', refreshCurrent, 'Không public được thư viện. Vui lòng thử lại.')}>{isActionBusy('release_publish') ? <BusyLabel text="Đang public" /> : 'Đưa lên CMS'}</button> : <button className="btn secondary chapter-action-button published" disabled>Đã đưa lên CMS</button>) : null}
      </div>
      {!chapterPublished && releaseReviewBlocked ? <div className="alert warning full-row"><b>Chưa thể chốt bộ đề.</b> Còn {stats.pending} câu chờ duyệt và {stats.draftError} câu lỗi. Hãy duyệt hoặc bỏ hết tất cả câu hỏi trước.</div> : null}
    </section>

    {latestRelease && releaseAudit ? <section className={`card bank-release-audit-panel status-${String(releaseAudit.audit_status || '').toLowerCase()}`}>
      <div className="section-head"><div><div className="eyebrow">QA publish/rollback</div><h3>Độ tin cậy bộ đề</h3><p className="helper">Kiểm tra nhanh Release trước khi đưa lên CMS, tạo Quiz/Final test hoặc rollback. Báo cáo này chỉ đọc dữ liệu AI Server, không gọi Open edX và không thay đổi dữ liệu.</p></div><span className={`status-badge ${releaseAudit.ok ? 'success' : 'danger'}`}>{releaseAudit.audit_status}</span></div>
      <div className="chapter-inline-stats bank-release-audit-stats" aria-label="Tóm tắt QA bộ đề">
        <span>Release <b>{releaseAudit.release_code || latestRelease.release_code}</b><small>{releaseAudit.release_status || latestRelease.status}</small></span>
        <span>Câu trong bộ <b>{releaseAudit.counts?.release_question_count ?? 0}</b><small>Component {releaseAudit.counts?.component_count ?? 0}</small></span>
        <span>Quiz/Final test <b>{releaseAudit.counts?.active_course_quiz_instance_count ?? 0}</b><small>Tổng {releaseAudit.counts?.course_quiz_instance_count ?? 0}</small></span>
        <span>Blocker <b>{releaseAudit.blockers?.length || 0}</b></span>
        <span>Cảnh báo <b>{releaseAudit.warnings?.length || 0}</b></span>
      </div>
      {releaseAudit.message ? <div className={releaseAudit.ok ? 'alert success' : 'alert warning'}><b>{releaseAudit.message}</b></div> : null}
      {(releaseAudit.blockers?.length || releaseAudit.warnings?.length) ? <div className="bank-release-audit-grid">
        {(releaseAudit.blockers || []).slice(0, 4).map((item) => <div className="bank-release-audit-item danger" key={`blocker-${item.code}`}><b>{item.code}</b><span>{item.message}</span></div>)}
        {(releaseAudit.warnings || []).slice(0, 4).map((item) => <div className="bank-release-audit-item warning" key={`warning-${item.code}`}><b>{item.code}</b><span>{item.message}</span></div>)}
      </div> : null}
      {releaseAudit.next_actions?.length ? <div className="bank-release-next-actions"><b>Việc cần làm tiếp theo</b><ul>{releaseAudit.next_actions.slice(0, 5).map((item) => <li key={item}>{item}</li>)}</ul></div> : null}
    </section> : null}

    {!selectedBankVersion ? <section className="card"><div className="empty-state">Đang chuẩn bị workspace cho bài này...</div></section> : <section className="workspace-grid multipage-workspace chapter-question-workspace">
      <div className="workspace-panel full" id="bank-question-list">
        <div className="section-head question-list-head"><div><h3>Danh sách câu hỏi</h3><p className="helper">Lọc nhanh theo trạng thái, độ khó và sắp xếp để giáo viên xử lý hết câu trước khi chốt bộ đề.</p></div>{!chapterPublished && can('review_questions') ? <button className="btn secondary chapter-action-button review" disabled={isActionBusy('bulk_approve') || stats.pending === 0} onClick={() => runAction('bulk_approve', async () => {
          if (!selectedBankVersion) return
          await bulkReviewBankQuestions(headers, selectedBankVersion.id, { action: 'approve', approve_all_pending: true, note: 'Duyệt hết câu chờ' })
        }, 'Hệ thống đã duyệt hết câu chờ.', refreshCurrent, 'Không duyệt được câu hỏi. Vui lòng thử lại.')}>{isActionBusy('bulk_approve') ? <BusyLabel text="Đang duyệt" /> : 'Duyệt hết câu chờ'}</button> : null}</div>
        <div className="question-filter-bar">
          <label>Trạng thái<select className="input" value={questionStatusFilter} onChange={(event) => setQuestionStatusFilter(event.target.value)}><option value="all">Tất cả</option><option value="needs_action">Cần xử lý</option><option value="pending_review">Chờ duyệt</option><option value="draft_error">Câu lỗi</option><option value="approved">Đã duyệt</option><option value="rejected">Đã bỏ</option><option value="published">Đã đưa lên CMS</option></select></label>
          <label>Độ khó<select className="input" value={questionDifficultyFilter} onChange={(event) => setQuestionDifficultyFilter(event.target.value)}><option value="all">Tất cả</option><option value="easy">Dễ</option><option value="medium">Trung bình</option><option value="hard">Khó</option></select></label>
          <label>Sắp xếp<select className="input" value={questionSort} onChange={(event) => setQuestionSort(event.target.value)}><option value="needs_review">Cần xử lý trước</option><option value="difficulty">Theo độ khó</option><option value="quality_low">Điểm chất lượng thấp trước</option><option value="quality_high">Điểm chất lượng cao trước</option></select></label>
          <button className="btn secondary" type="button" onClick={() => { setQuestionStatusFilter('all'); setQuestionDifficultyFilter('all'); setQuestionSort('needs_review') }}>Xóa lọc</button>
          <span className="filter-result-count">Hiện {filteredQuestions.length}/{questions.length} câu</span>
        </div>
        <div className="question-card-list bank-review-list">
          {filteredQuestions.map((item, index) => {
            const draftReason = item.status === 'draft_error' ? bankQuestionErrorMessage(item) : null
            const waitingForReview = isQuestionWaitingForReview(item)
            return <article className="question-review-card" key={item.id}>
              <div className="question-main-box">
                <div className="question-main-head"><span className="question-index">Câu {index + 1}</span><span className={statusClass(item.status)}>{statusLabel(item.status)}</span></div>
                <div className="question-prompt">{item.question_text}</div>
                <div className="answer-grid">
                  {bankAnswerRows.map(([letter, field]) => {
                    const isCorrect = item.correct_answer === letter
                    return <div key={letter} className={isCorrect ? 'answer-option correct' : 'answer-option'}>
                      <span className="answer-letter">{letter}</span>
                      <span>{item[field] || '—'}</span>
                    </div>
                  })}
                </div>
                <div className="question-meta-row">
                  <span>Độ khó: <b>{item.difficulty}</b></span>
                  {item.concept_title ? <span>Concept: <b>{item.concept_title}</b></span> : null}
                  {item.question_family_id ? <span>Family: <code>{item.question_family_id}</code></span> : null}
                  {item.variant_no ? <span>Variant: <b>{item.variant_no}</b></span> : null}
                  {item.is_carry_over ? <span>Clone từ kỳ trước</span> : null}
                  <span>Điểm chất lượng: {Math.round(Number(item.quality_score || 0) * 100)}%</span>
                </div>
                {item.explanation ? <div className="question-explanation"><b>Giải thích:</b> {item.explanation}</div> : null}
                {draftReason ? <div className="draft-error-reason"><strong>Lý do lỗi:</strong> {draftReason}{item.draft_error_detail?.message ? <span> · {String(item.draft_error_detail.message)}</span> : null}</div> : null}
              </div>
              <div className="question-control-box">
                <div className="question-control-status"><div className="box-label">Trạng thái</div><span className={statusClass(item.status)}>{statusLabel(item.status)}</span><small className="control-note">{waitingForReview ? 'Cần xử lý trước khi chốt bộ đề' : 'Đã xử lý'}</small></div>
                <div className="question-control-actions">
                  <div className="box-label">Thao tác</div>
                  <div className="question-actions">
                    {!chapterPublished && can('review_questions') && item.status !== 'published' ? <button className="btn small secondary" disabled={isActionBusy('question_review')} onClick={() => startEditQuestion(item)}>Sửa</button> : null}
                    {!chapterPublished && can('review_questions') && (item.status === 'pending_review' || item.status === 'needs_review' || item.status === 'rejected') ? <button className="btn small success" disabled={isActionBusy('question_review')} onClick={() => run(async () => {
                      if (!selectedBankVersion) return
                      await reviewBankQuestion(headers, selectedBankVersion.id, item.id, { action: 'approve', note: 'Giữ câu hỏi này' })
                    }, 'Đã duyệt câu hỏi', refreshCurrent)}>{item.status === 'rejected' ? 'Duyệt lại' : 'Duyệt'}</button> : null}
                    {!chapterPublished && can('review_questions') && item.status !== 'rejected' && item.status !== 'published' ? <button className="btn small danger" disabled={isActionBusy('question_review')} onClick={() => openRejectQuestion(item)}>{item.status === 'draft_error' ? 'Bỏ câu lỗi' : 'Bỏ'}</button> : null}
                    {!chapterPublished && can('review_questions') && item.status === 'approved' ? <button className="btn small secondary" disabled={isActionBusy('question_review')} onClick={() => run(async () => {
                      if (!selectedBankVersion) return
                      await reviewBankQuestion(headers, selectedBankVersion.id, item.id, { action: 'back_to_review', note: 'Đưa về chờ duyệt' })
                    }, 'Đã đưa câu hỏi về chờ duyệt', refreshCurrent)}>Hoàn tác</button> : null}
                  </div>
                </div>
              </div>
            </article>
          })}
        </div>
        {questionHasNext ? <div className="load-more-row"><button className="btn secondary" type="button" disabled={questionLoadingMore} onClick={loadMoreQuestions}>{questionLoadingMore ? 'Đang tải thêm...' : 'Tải thêm 100 câu'}</button><span className="helper">Đang hiển thị {questions.length} câu đầu. Danh sách dùng cursor/keyset nên không kéo toàn bộ bank vào trình duyệt.</span></div> : null}
        {!filteredQuestions.length ? <div className="empty-state">Không có câu hỏi phù hợp bộ lọc.</div> : null}
      </div>
    </section>}

    <Modal open={materialManagerOpen} title="Tài liệu của bài" onClose={() => setMaterialManagerOpen(false)} wide>
      <div className="chapter-popup-grid">
        {!chapterPublished && can('edit_questions') ? <div className="popup-action-panel">
          <h3>Gắn tài liệu</h3>
          <p className="helper">Tài liệu là nguồn để AI tạo câu hỏi cho đúng bài này. Nếu version clone bị đổi tài liệu, hệ thống sẽ kiểm tra khác biệt.</p>
          {popupMessage ? <div className={`alert ${popupMessage.type}`}>{popupMessage.text}</div> : null}
          {activeOperation?.type === 'material_upload' ? <div className="alert info" role="status" aria-live="polite"><b>Hệ thống đang xử lý tài liệu.</b> {activeOperation.label}</div> : null}
          <div className="mini-form">
            <input className="input" type="file" onChange={(event) => setFile(event.target.files?.[0] || null)} />
            <button className="btn" disabled={materialOperationBusy || generateOperationBusy || isActionBusy('material_upload_enqueue') || !file} onClick={uploadSelectedMaterial}>{isActionBusy('material_upload_enqueue') || materialOperationBusy ? <BusyLabel text="Đang up tài liệu" /> : '+ Gắn tài liệu'}</button>
          </div>
        </div> : <div className="popup-action-panel"><h3>Đã đưa lên CMS</h3><p className="helper">Tài liệu của bài đã khóa. Bạn chỉ có thể xem lại tài liệu đã dùng để tạo bộ đề.</p></div>}
        <div className="popup-list-panel">
          <h3>Tài liệu đã gắn</h3>
          <div className="entity-list compact-list small-chunk-list popup-scroll-list">
            {materials.map((item) => <div className="entity-card" key={item.id}>
              <b>{item.title || item.file_name}</b>
              <small>{item.file_type} · {formatVNDateTime(item.created_at)}</small>
              <div className="button-row no-margin">
                <button className="btn small secondary" onClick={() => openMaterial(item)}>Xem</button>
                {!chapterPublished && can('edit_questions') ? <button className="btn small danger" disabled={isActionBusy('material_delete')} onClick={() => runAction('material_delete', async () => { await deleteMaterialVersion(headers, item.id) }, 'Hệ thống đã xóa tài liệu khỏi bài.', refreshCurrent, 'Không xóa được tài liệu. Vui lòng thử lại.')}>{isActionBusy('material_delete') ? <BusyLabel text="Đang xóa" /> : 'Xóa'}</button> : null}
              </div>
            </div>)}
            {!materials.length ? <div className="empty-state">Chưa có tài liệu.</div> : null}
          </div>
        </div>
      </div>
    </Modal>

    <Modal open={generateManagerOpen} title="Tạo câu hỏi từ tài liệu" onClose={() => setGenerateManagerOpen(false)} wide>
      <div className="chapter-popup-grid">
        <div className="popup-action-panel">
          <h3>Kế hoạch tạo câu hỏi</h3>
          <p className="helper">AI dùng tài liệu đã gắn để tạo câu hỏi theo tỷ lệ EASY/MEDIUM/HARD, kiểm tra chất lượng rồi đưa vào hàng chờ duyệt.</p>
          {popupMessage ? <div className={`alert ${popupMessage.type}`}>{popupMessage.text}</div> : null}
          {activeOperation?.type === 'generate' ? <div className="alert info" role="status" aria-live="polite"><b>Hệ thống đang tạo câu hỏi.</b> {activeOperation.label}</div> : null}
          {chapterPublished ? <div className="alert warning">Bài đã publish nên không thể tạo thêm câu hỏi trên version này.</div> : null}
          <div className="quota-box"><b>{usedQuestionCount}/{chapterQuestionLimit}</b><small>Tổng câu đã tạo / giới hạn của bài · còn {remainingQuota} câu</small></div>
          <div className="generation-plan-box">
            <div><span>Nguồn tạo</span><b>{materials.length ? `${materials.length} tài liệu đã gắn` : 'Chưa có tài liệu'}</b></div>
            <div><span>Sẽ tạo</span><b>{Math.max(0, numericGenerateCount || 0)} câu mới</b></div>
            <div><span>Tỷ lệ</span><b>{difficultyEasy}/{difficultyMedium}/{difficultyHard}</b><small>Dễ / Trung bình / Khó</small></div>
          </div>
        </div>
        <div className="popup-list-panel">
          <div className="mini-form">
            <label>Số câu muốn tạo thêm</label>
            <input className="input" type="number" min={1} max={remainingQuota || 1} value={generateCount} onChange={(event) => setGenerateCount(event.target.value)} placeholder="Ví dụ: 10" />
            <div className="three-col-form">
              <label>Dễ %<input className="input" type="number" min={0} max={100} value={difficultyEasy} onChange={(event) => setDifficultyEasy(event.target.value)} /></label>
              <label>Trung bình %<input className="input" type="number" min={0} max={100} value={difficultyMedium} onChange={(event) => setDifficultyMedium(event.target.value)} /></label>
              <label>Khó %<input className="input" type="number" min={0} max={100} value={difficultyHard} onChange={(event) => setDifficultyHard(event.target.value)} /></label>
            </div>
            {!materials.length ? <div className="alert warning">Chưa có tài liệu. Hãy gắn tài liệu trước rồi mới tạo câu hỏi.</div> : null}
            {invalidDifficulty ? <div className="alert warning">Tổng tỷ lệ Dễ/Trung bình/Khó phải bằng 100%.</div> : null}
            {overQuota ? <div className="alert warning">Vượt giới hạn. Bài này chỉ còn được tạo thêm {remainingQuota} câu.</div> : null}
            {remainingQuota === 0 ? <div className="alert warning">Bài này đã đạt giới hạn {chapterQuestionLimit} câu. Không thể tạo thêm.</div> : null}
            <div className="modal-actions"><button className="btn secondary" onClick={() => setGenerateManagerOpen(false)}>Đóng</button><button className="btn" disabled={isActionBusy('generate_preview') || generateOperationBusy || materialOperationBusy || !canGenerateNow} onClick={openGenerateConfirm}>{isActionBusy('generate_preview') ? <BusyLabel text="Đang tính" /> : generateOperationBusy ? <BusyLabel text="Đang tạo câu hỏi" /> : 'Tính chi phí & tạo'}</button></div>
          </div>
        </div>
      </div>
    </Modal>

    <Modal open={Boolean(generatePreview)} title="Xác nhận tạo câu hỏi" onClose={() => setGeneratePreview(null)}>
      {generatePreview ? <div className="generate-confirm-box">
        <div className="summary-grid compact-summary">
          <div><span>Số câu</span><b>{generatePreview.question_count}</b></div>
          <div><span>Dễ</span><b>{generatePreview.difficulty_counts.easy || 0}</b></div>
          <div><span>Trung bình</span><b>{generatePreview.difficulty_counts.medium || 0}</b></div>
          <div><span>Khó</span><b>{generatePreview.difficulty_counts.hard || 0}</b></div>
          <div><span>Đã có trong bài</span><b>{generatePreview.current_question_count}/{generatePreview.chapter_question_limit}</b></div>
          <div><span>Còn lại sau lần này</span><b>{Math.max(0, generatePreview.remaining_quota - generatePreview.question_count)}</b></div>
        </div>
        <div className="cost-preview-box">
          <div><span>Chi phí dự kiến</span><b>{Number(generatePreview.estimated_cost_vnd || 0).toLocaleString('vi-VN')} ₫</b><small>~ ${Number(generatePreview.estimated_cost_usd || 0).toFixed(6)} USD</small></div>
          <div><span>Token dự kiến</span><b>{Number(generatePreview.estimated_input_tokens + generatePreview.estimated_output_tokens).toLocaleString('vi-VN')}</b><small>Input {generatePreview.estimated_input_tokens.toLocaleString('vi-VN')} · Output {generatePreview.estimated_output_tokens.toLocaleString('vi-VN')}</small></div>
        </div>
        <p className="helper">{generatePreview.message}</p>
        <div className="button-row"><button className="btn secondary" disabled={isActionBusy('generate_enqueue')} onClick={() => setGeneratePreview(null)}>Hủy</button><button className="btn" disabled={chapterPublished || generateOperationBusy || materialOperationBusy || isActionBusy('generate_enqueue')} onClick={confirmGenerateQuestions}>{isActionBusy('generate_enqueue') ? <BusyLabel text="Đang gửi yêu cầu" /> : 'Xác nhận tạo câu hỏi'}</button></div>
      </div> : null}
    </Modal>


    <Modal open={Boolean(rejectingQuestion)} title={rejectingQuestion?.status === 'draft_error' ? 'Bỏ câu lỗi' : 'Bỏ câu hỏi'} onClose={() => { setRejectingQuestion(null); setRejectReason('') }}>
      <div className="mini-form">
        <p className="helper">Nhập lý do hủy/bỏ câu. Lý do này được lưu lại để biết ai làm gì và dùng làm dữ liệu fine-tune AI sau này.</p>
        {rejectingQuestion ? <div className="reject-question-preview"><b>{rejectingQuestion.question_text || 'Câu lỗi chưa có nội dung'}</b>{rejectingQuestion.status === 'draft_error' ? <small>Lý do lỗi: {bankQuestionErrorMessage(rejectingQuestion) || 'Không rõ'}</small> : null}</div> : null}
        <textarea className="input" rows={4} value={rejectReason} onChange={(event) => setRejectReason(event.target.value)} placeholder="Ví dụ: Câu hỏi không đúng tài liệu, đáp án sai, câu lỗi không sửa được..." />
        <div className="modal-actions"><button className="btn secondary" disabled={Boolean(actionBusy)} onClick={() => { setRejectingQuestion(null); setRejectReason('') }}>Hủy</button><button className="btn danger" disabled={chapterPublished || isActionBusy('question_reject') || !rejectReason.trim()} onClick={confirmRejectQuestion}>Xác nhận bỏ câu</button></div>
      </div>
    </Modal>

    <Modal open={Boolean(editingQuestion && editForm)} title="Sửa câu hỏi" onClose={() => { setEditingQuestion(null); setEditForm(null) }} wide>
      {editingQuestion && editForm ? <div className="bank-question-edit-form">
        <p className="helper">Sửa nội dung câu hỏi giống trang /review. Sau khi sửa, giáo viên chọn trạng thái phù hợp rồi lưu.</p>
        <div className="grid grid-3">
          <label>Độ khó<select className="input" value={editForm.difficulty} onChange={(event) => updateEditForm('difficulty', event.target.value)}><option value="easy">Dễ</option><option value="medium">Trung bình</option><option value="hard">Khó</option></select></label>
          <label>Mức nhận thức<select className="input" value={editForm.cognitive_level} onChange={(event) => updateEditForm('cognitive_level', event.target.value)}><option value="remember">Ghi nhớ</option><option value="understand">Hiểu</option><option value="recognize_example">Nhận diện ví dụ</option><option value="simple_apply">Áp dụng đơn giản</option></select></label>
          <label>Trạng thái sau khi lưu<select className="input" value={editForm.target_status} onChange={(event) => updateEditForm('target_status', event.target.value)}><option value="pending_review">Chờ duyệt</option><option value="approved">Đã duyệt</option><option value="rejected">Đã bỏ</option></select></label>
        </div>
        <label>Mục tiêu học tập<input className="input" value={editForm.learning_objective} onChange={(event) => updateEditForm('learning_objective', event.target.value)} /></label>
        <label>Câu hỏi<textarea className="input" rows={3} value={editForm.question_text} onChange={(event) => updateEditForm('question_text', event.target.value)} /></label>
        <div className="grid grid-2">
          <label>A<input className="input" value={editForm.option_a} onChange={(event) => updateEditForm('option_a', event.target.value)} /></label>
          <label>B<input className="input" value={editForm.option_b} onChange={(event) => updateEditForm('option_b', event.target.value)} /></label>
          <label>C<input className="input" value={editForm.option_c} onChange={(event) => updateEditForm('option_c', event.target.value)} /></label>
          <label>D<input className="input" value={editForm.option_d} onChange={(event) => updateEditForm('option_d', event.target.value)} /></label>
        </div>
        <div className="grid grid-3">
          <label>Đáp án đúng<select className="input" value={editForm.correct_answer} onChange={(event) => updateEditForm('correct_answer', event.target.value)}><option>A</option><option>B</option><option>C</option><option>D</option></select></label>
          <label>Concept<input className="input" value={editForm.concept_title} onChange={(event) => updateEditForm('concept_title', event.target.value)} /></label>
          <label>Family<input className="input" value={editForm.question_family_id} onChange={(event) => updateEditForm('question_family_id', event.target.value)} /></label>
        </div>
        <label>Giải thích<textarea className="input" rows={2} value={editForm.explanation} onChange={(event) => updateEditForm('explanation', event.target.value)} /></label>
        <div className="grid grid-2">
          <label>Nguồn tham chiếu<input className="input" value={editForm.source_ref} onChange={(event) => updateEditForm('source_ref', event.target.value)} /></label>
          <label>Loại nguồn<input className="input" value={editForm.source_type} onChange={(event) => updateEditForm('source_type', event.target.value)} /></label>
        </div>
        <label>Trích đoạn nguồn<textarea className="input" rows={2} value={editForm.source_excerpt} onChange={(event) => updateEditForm('source_excerpt', event.target.value)} /></label>
        <label>Bằng chứng nguồn<textarea className="input" rows={2} value={editForm.source_evidence} onChange={(event) => updateEditForm('source_evidence', event.target.value)} /></label>
        <div className="button-row"><button className="btn" disabled={chapterPublished || isActionBusy('question_edit') || !editForm.question_text.trim() || !editForm.option_a.trim() || !editForm.option_b.trim() || !editForm.option_c.trim() || !editForm.option_d.trim()} onClick={saveEditedQuestion}>Lưu chỉnh sửa</button><button className="btn secondary" onClick={() => { setEditingQuestion(null); setEditForm(null) }}>Hủy</button></div>
      </div> : null}
    </Modal>

    <Modal open={Boolean(materialView)} title={materialView?.material.title || 'Tài liệu'} onClose={() => setMaterialView(null)} wide>
      <div className="material-preview material-preview-single">
        <div className="material-preview-meta">
          <span>{materialView?.material.file_name}</span>
          <b>{materialView?.chunks.length || 0} đoạn nội dung</b>
        </div>
        <pre className="material-preview-text">{materialPreviewText || 'Không có nội dung để hiển thị.'}</pre>
        {materialView && materialView.chunks.length > materialPreviewChunks.length ? <div className="empty-state">Đang hiển thị {materialPreviewChunks.length} đoạn đầu để popup không quá nặng.</div> : null}
      </div>
    </Modal>

    <Modal open={Boolean(diffPreview)} title="Kết quả kiểm tra thay đổi tài liệu" onClose={() => { setDiffPreview(null); setMaterialRecheckResult(null) }} wide>
      {diffPreview ? <div className="diff-result-box">
        <div className="summary-grid compact-summary">
          <div><span>Tài liệu giống nhau</span><b>{Math.round(Number(diffPreview.summary.material_similarity ?? diffPreview.material_similarity ?? 0) * 100)}%</b></div>
          <div><span>Câu có thể giữ</span><b>{diffPreview.summary.carry_over_candidate_count}</b></div>
          <div><span>Câu nên bỏ</span><b>{diffPreview.summary.retire_candidate_count}</b></div>
          <div><span>Câu cần xem lại</span><b>{diffPreview.summary.review_candidate_count}</b></div>
          <div><span>Concept mới</span><b>{diffPreview.summary.new_concept_count}</b></div>
          <div><span>Concept bị xóa</span><b>{diffPreview.summary.removed_concept_count}</b></div>
        </div>
        {(() => {
          const impact = diffImpactGroups(diffPreview)
          return <div className="diff-impact-panel">
            {impact.critical.length ? <div className="diff-impact-section danger"><b>Ảnh hưởng nghiêm trọng</b><ul>{impact.critical.map((item) => <li key={item}>{item}</li>)}</ul></div> : null}
            {impact.warning.length ? <div className="diff-impact-section warning"><b>Cần xử lý</b><ul>{impact.warning.map((item) => <li key={item}>{item}</li>)}</ul></div> : null}
            {impact.info.length ? <div className="diff-impact-section"><b>Thông tin</b><ul>{impact.info.map((item) => <li key={item}>{item}</li>)}</ul></div> : null}
          </div>
        })()}
        {diffPreview.summary.changed_concepts?.length ? <div className="diff-chip-group"><b>Concept đổi:</b>{diffPreview.summary.changed_concepts.slice(0, 12).map((item) => <span key={item}>{item}</span>)}</div> : null}
        {diffPreview.summary.new_concepts?.length ? <div className="diff-chip-group"><b>Concept mới:</b>{diffPreview.summary.new_concepts.slice(0, 12).map((item) => <span key={item}>{item}</span>)}</div> : null}
        {diffPreview.summary.removed_concepts?.length ? <div className="diff-chip-group danger"><b>Concept bị xóa:</b>{diffPreview.summary.removed_concepts.slice(0, 12).map((item) => <span key={item}>{item}</span>)}</div> : null}
        <div className="alert warning"><b>Gợi ý xử lý:</b> {diffActionHint(diffPreview)}</div>
        {materialRecheckResult ? <div className="alert success"><b>Đã áp dụng xử lý tự động.</b> Giữ {materialRecheckResult.kept_count + materialRecheckResult.safe_skipped_count} câu, tự loại {materialRecheckResult.retired_count} câu, gỡ {materialRecheckResult.release_removed_count || 0} mapping release.</div> : null}
        <div className="button-row">
          <button className="btn" disabled={Boolean(actionBusy)} onClick={() => runAction('diff_apply', applyMaterialRecheck, 'Đã áp dụng xử lý tự động sau khi kiểm tra thay đổi tài liệu.', undefined, 'Không áp dụng được xử lý tự động. Vui lòng thử lại.')}>Áp dụng xử lý tự động</button>
          <button className="btn secondary" disabled={Boolean(actionBusy)} onClick={() => run(keepReusableOnly, 'Đã giữ câu phù hợp và bỏ câu không còn chắc phù hợp')}>Giữ câu còn phù hợp</button>
          <button className="btn secondary" disabled={Boolean(actionBusy)} onClick={() => run(rejectAllCarryOver, 'Đã bỏ các câu clone từ tài liệu cũ')}>Không giữ câu cũ</button>
        </div>
      </div> : null}
    </Modal>
  </div>
}

