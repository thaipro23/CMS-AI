'use client'

import { formatVNDateTime } from '../../../lib/time'
import { inlineMessageFromBackend } from '../../../lib/backendNotice'
import { normalizeOpenEdxCourseId } from '../../../lib/openedx'
import { useEffect, useMemo, useState } from 'react'
import { useAppContext } from '../../../context/AppContext'
import { PageHeader, PageRoot } from '../../../components/layout/PageHeader'
import { BankPageIdentity, BankSection, BankWorkflowStepper } from '../_components/BankDesignContract'
import { VisualIcon } from '../../../components/ui/VisualIcon'
import { EnterpriseDataTable, type EnterpriseTableColumn } from '../../../components/table/EnterpriseDataTable'
import { AccessibleDialog } from '../../../components/ui/AccessibleDialog'
import { CourseQuizInstance, QuizAutoMapResult, QuizChapterAction, QuizChapterPlanItem } from '../../../types'
import {
  applyQuizAutoMap,
  createQuizFromBankRelease,
  getCourseQuizInstances,
  previewQuizAutoMap,
  rollbackCourseQuizInstance,
} from '../../../lib/api'

type QuizMapping = QuizAutoMapResult['mappings'][number]
type EffectiveQuizMapping = QuizMapping & { action: QuizChapterAction; effectiveReady: boolean; effectiveRequiresQuiz: boolean }
type PendingCreate = { kind: 'one'; item: EffectiveQuizMapping } | { kind: 'all' }

type AssessmentConfig = {
  totalQuestions: number
  easy: number
  medium: number
  hard: number
  timerEnabled: boolean
  timeLimitMinutes: number
  retakeCooldownMinutes: number
  autoSubmitOnTimeout: boolean
  lockAfterTimeout: boolean
}

function classNames(...items: Array<string | false | null | undefined>) {
  return items.filter(Boolean).join(' ')
}

function percent(value: number | undefined | null) {
  return `${Math.round((Number(value || 0)) * 100)}%`
}

function quizSuffixFromChapterTitle(title: string | undefined | null) {
  const text = String(title || '').trim()
  const withoutPrefix = text.replace(/^bài\s*/i, '').trim()
  return withoutPrefix || text || '1'
}

type InlineMessage = { tone: 'success' | 'danger' | 'warning' | 'info'; text: string }

function messageClass(message: InlineMessage) {
  return message.tone === 'danger' ? 'danger' : message.tone === 'warning' ? 'warning' : message.tone === 'info' ? 'info' : 'success'
}

function defaultActionFromMapping(item: QuizMapping): QuizChapterAction {
  if (item.action) return item.action
  const title = String(item.chapter_title || '').toLowerCase()
  if (title.includes('final')) return 'final_test'
  if (title.includes('assignment') || title.includes('asm')) return 'skip'
  return 'quiz'
}

function actionLabel(action: QuizChapterAction) {
  switch (action) {
    case 'quiz': return 'Tạo Quiz'
    case 'final_test': return 'Tạo Final test'
    case 'assignment': return 'Không tạo'
    default: return 'Không tạo'
  }
}

function requiresQuiz(action: QuizChapterAction) {
  return action === 'quiz' || action === 'final_test'
}

function actionStatusClass(item: EffectiveQuizMapping) {
  if (!item.effectiveRequiresQuiz) return 'pending'
  return item.effectiveReady ? 'success' : 'danger'
}

function actionStatusText(item: EffectiveQuizMapping) {
  if (!item.effectiveRequiresQuiz) return 'Bỏ qua'
  if (item.effectiveReady) return item.action === 'final_test' ? 'Sẵn sàng tạo Final test' : 'Sẵn sàng tạo Quiz'
  return 'Cần Release + Section'
}

function productionStatusClass(item: EffectiveQuizMapping) {
  if (!item.effectiveRequiresQuiz) return 'pending'
  const severity = String((item as any).status_severity || '').toLowerCase()
  if (severity === 'success') return 'success'
  if (severity === 'danger' || severity === 'error') return 'danger'
  if (severity === 'warning') return 'warning'
  return item.effectiveReady ? 'success' : 'danger'
}

function missingRequirementLabel(code: string) {
  if (code === 'SECTION') return 'Thiếu Section'
  if (code === 'RELEASE') return 'Thiếu Release'
  if (code === 'COURSE_TREE') return 'Chưa đọc được cây course'
  return code
}

function actionTypeBadge(item: EffectiveQuizMapping) {
  if (item.action === 'final_test') return { label: 'Final test', tone: 'warning' }
  if (item.action === 'quiz') return { label: 'Quiz', tone: 'pending' }
  return { label: 'Không tạo', tone: 'neutral' }
}

function buildPlan(mappings: EffectiveQuizMapping[]): QuizChapterPlanItem[] {
  return mappings.map((item) => ({ chapter_id: item.chapter_id, action: item.action }))
}

function normalizeNumber(value: number, fallback: number, min: number, max: number) {
  const next = Number.isFinite(value) ? value : fallback
  return Math.max(min, Math.min(max, Math.trunc(next)))
}

export default function BankQuizPage() {
  const { authHeaders, can } = useAppContext()
  const headers = useMemo(() => authHeaders(true), [authHeaders])
  const [courseId, setCourseId] = useState('')
  const [autoMap, setAutoMap] = useState<QuizAutoMapResult | null>(null)
  const [chapterActions, setChapterActions] = useState<Record<string, QuizChapterAction>>({})
  const [history, setHistory] = useState<CourseQuizInstance[]>([])
  const [busy, setBusy] = useState(false)
  const [historyBusy, setHistoryBusy] = useState(false)
  const [creatingKey, setCreatingKey] = useState<string>('')
  const [message, setMessage] = useState<InlineMessage | null>(null)
  const [selectedOfferingId, setSelectedOfferingId] = useState<string>('')
  const [createModal, setCreateModal] = useState<PendingCreate | null>(null)

  const [quizConfig, setQuizConfig] = useState<AssessmentConfig>({
    totalQuestions: 15,
    easy: 50,
    medium: 30,
    hard: 20,
    timerEnabled: true,
    timeLimitMinutes: 15,
    retakeCooldownMinutes: 5,
    autoSubmitOnTimeout: true,
    lockAfterTimeout: true,
  })
  const [finalConfig, setFinalConfig] = useState<AssessmentConfig>({
    totalQuestions: 30,
    easy: 20,
    medium: 40,
    hard: 40,
    timerEnabled: true,
    timeLimitMinutes: 60,
    retakeCooldownMinutes: 0,
    autoSubmitOnTimeout: true,
    lockAfterTimeout: true,
  })

  const effectiveMappings = useMemo<EffectiveQuizMapping[]>(() => {
    return (autoMap?.mappings || []).map((item) => {
      const action = chapterActions[item.chapter_id] || defaultActionFromMapping(item)
      const effectiveRequiresQuiz = requiresQuiz(action)
      const effectiveReady = Boolean(effectiveRequiresQuiz && item.release_id && item.openedx_section_id && (item.ready || item.can_create !== false))
      return { ...item, action, effectiveReady, effectiveRequiresQuiz }
    })
  }, [autoMap, chapterActions])

  const actionPlan = useMemo(() => buildPlan(effectiveMappings), [effectiveMappings])
  const applied = autoMap?.mode === 'applied'
  const readyRows = effectiveMappings.filter((item) => item.effectiveRequiresQuiz && item.effectiveReady && item.course_chapter_mapping_id)
  const selectedQuizCount = effectiveMappings.filter((item) => item.effectiveRequiresQuiz).length
  const skippedCount = effectiveMappings.filter((item) => !item.effectiveRequiresQuiz).length
  const candidates = autoMap?.summary?.candidates || []
  const canCreateQuiz = applied && readyRows.length > 0
  const matchedCount = autoMap?.summary?.matched_count || 0
  const chapterCount = autoMap?.summary?.chapter_count || 0
  const productionGate = autoMap?.summary?.production_gate || {}
  const regularQuizCount = effectiveMappings.filter((item) => item.action === 'quiz').length
  const finalTestCount = effectiveMappings.filter((item) => item.action === 'final_test').length
  const courseTreeUnavailable = autoMap?.course_tree?.source === 'unavailable'
  const missingSectionCount = courseTreeUnavailable ? 0 : effectiveMappings.filter((item: any) => item.effectiveRequiresQuiz && (!item.openedx_section_id || (item.missing_requirements || []).includes('SECTION'))).length
  const missingReleaseCount = effectiveMappings.filter((item: any) => item.effectiveRequiresQuiz && (!item.release_id || (item.missing_requirements || []).includes('RELEASE'))).length
  const quizDifficultyTotal = quizConfig.easy + quizConfig.medium + quizConfig.hard
  const finalDifficultyTotal = finalConfig.easy + finalConfig.medium + finalConfig.hard

  function hydrateActionDefaults(result: QuizAutoMapResult) {
    setChapterActions((prev) => {
      const next: Record<string, QuizChapterAction> = {}
      for (const item of result.mappings || []) {
        next[item.chapter_id] = prev[item.chapter_id] || defaultActionFromMapping(item)
      }
      return next
    })
  }

  async function loadHistory(targetCourseId = courseId) {
    const normalizedCourseId = normalizeOpenEdxCourseId(targetCourseId)
    if (!normalizedCourseId) {
      setHistory([])
      return
    }
    setHistoryBusy(true)
    try {
      const data = await getCourseQuizInstances(headers, { openedx_course_id: normalizedCourseId, limit: 100 })
      setHistory(data.filter((item) => normalizeOpenEdxCourseId(item.openedx_course_id) === normalizedCourseId))
    } catch (error) {
      setHistory([])
      setMessage({ tone: 'warning', text: error instanceof Error ? `Không tải được lịch sử Quiz: ${error.message}` : 'Không tải được lịch sử Quiz' })
    } finally {
      setHistoryBusy(false)
    }
  }

  async function runPreview(offeringId = selectedOfferingId, keepPlan = false) {
    const normalizedCourseId = normalizeOpenEdxCourseId(courseId)
    if (!normalizedCourseId) {
      setMessage({ tone: 'danger', text: 'Course ID phải có dạng course-v1:ORG+COURSE+RUN.' })
      return
    }
    setCourseId(normalizedCourseId)
    setBusy(true)
    setMessage(null)
    setAutoMap(null)
    try {
      const result = await previewQuizAutoMap(headers, {
        openedx_course_id: normalizedCourseId,
        selected_subject_offering_id: offeringId || null,
        total_questions: quizConfig.totalQuestions,
        difficulty_easy: quizConfig.easy,
        difficulty_medium: quizConfig.medium,
        difficulty_hard: quizConfig.hard,
        max_families_per_bank: 2,
        chapter_plan: keepPlan ? actionPlan : [],
      })
      setAutoMap(result)
      hydrateActionDefaults(result)
      const picked = result.summary?.selected_subject_offering_id || result.offering?.id || ''
      if (picked) setSelectedOfferingId(picked)
      await loadHistory(normalizedCourseId)
    } catch (error) {
      setMessage({ tone: 'danger', text: error instanceof Error ? error.message : 'Không tự kiểm tra được course Open edX' })
    } finally {
      setBusy(false)
    }
  }

  async function runApply() {
    const normalizedCourseId = normalizeOpenEdxCourseId(courseId)
    if (!normalizedCourseId) {
      setMessage({ tone: 'danger', text: 'Course ID phải có dạng course-v1:ORG+COURSE+RUN.' })
      return
    }
    setCourseId(normalizedCourseId)
    setBusy(true)
    setMessage(null)
    try {
      const result = await applyQuizAutoMap(headers, {
        openedx_course_id: normalizedCourseId,
        selected_subject_offering_id: selectedOfferingId || autoMap?.offering?.id || null,
        total_questions: quizConfig.totalQuestions,
        difficulty_easy: quizConfig.easy,
        difficulty_medium: quizConfig.medium,
        difficulty_hard: quizConfig.hard,
        max_families_per_bank: 2,
        chapter_plan: actionPlan,
      })
      setAutoMap(result)
      hydrateActionDefaults(result)
      const picked = result.summary?.selected_subject_offering_id || result.offering?.id || ''
      if (picked) setSelectedOfferingId(picked)
      setMessage(inlineMessageFromBackend(result, result.message || 'Đã lưu cấu hình map Khóa học ID.', result.ok ? 'success' : 'warning'))
      await loadHistory(normalizedCourseId)
    } catch (error) {
      setMessage({ tone: 'danger', text: error instanceof Error ? error.message : 'Lưu cấu hình tự động thất bại' })
    } finally {
      setBusy(false)
    }
  }

  function configForAction(action: QuizChapterAction) {
    return action === 'final_test' ? finalConfig : quizConfig
  }

  function titleForItem(item: EffectiveQuizMapping) {
    if (item.action === 'final_test') return item.recommended_quiz_title || 'Final test'
    const suffix = quizSuffixFromChapterTitle(item.chapter_title)
    return item.recommended_quiz_title || `Quiz ${suffix}`
  }

  async function executeCreateOneQuiz(item: EffectiveQuizMapping, refreshHistory = true) {
    if (!item.release_id || !item.course_chapter_mapping_id || !item.effectiveRequiresQuiz) return
    const config = configForAction(item.action)
    setCreatingKey(item.chapter_id)
    setMessage(null)
    try {
      const result = await createQuizFromBankRelease(headers, item.release_id, {
        course_chapter_mapping_id: item.course_chapter_mapping_id,
        quiz_title: titleForItem(item),
        unit_title: item.action === 'final_test' ? 'Final test' : 'Quiz',
        assessment_type: item.action === 'final_test' ? 'final_test' : 'quiz',
        total_questions: config.totalQuestions,
        difficulty_easy: config.easy,
        difficulty_medium: config.medium,
        difficulty_hard: config.hard,
        max_families_per_bank: 2,
        custom_timer_enabled: config.timerEnabled,
        time_limit_minutes: config.timeLimitMinutes,
        retake_cooldown_minutes: config.retakeCooldownMinutes,
        auto_submit_on_timeout: config.autoSubmitOnTimeout,
        lock_after_timeout: config.lockAfterTimeout,
        native_timed_exam: false,
      })
      const timerText = config.timerEnabled ? ` · Timer ${config.timeLimitMinutes} phút · làm lại sau ${config.retakeCooldownMinutes} phút` : ''
      setMessage(inlineMessageFromBackend(result, (result.message || `Đã tạo ${actionLabel(item.action)} cho ${item.chapter_title}`) + timerText, result.ok ? 'success' : 'warning'))
      if (refreshHistory) await loadHistory(normalizeOpenEdxCourseId(courseId))
    } catch (error) {
      setMessage({ tone: 'danger', text: error instanceof Error ? error.message : `Tạo bài kiểm tra cho ${item.chapter_title} thất bại` })
    } finally {
      setCreatingKey('')
    }
  }

  async function confirmCreateFromModal() {
    if (!createModal) return
    const invalidDifficulty = quizDifficultyTotal !== 100 || finalDifficultyTotal !== 100
    if (invalidDifficulty) return
    if (createModal.kind === 'one') {
      const item = createModal.item
      setCreateModal(null)
      await executeCreateOneQuiz(item)
      return
    }
    setCreateModal(null)
    setBusy(true)
    setMessage({ tone: 'info', text: `Đang tạo ${readyRows.length} bài kiểm tra. Vui lòng chờ...` })
    try {
      for (const item of readyRows) {
        // eslint-disable-next-line no-await-in-loop
        await executeCreateOneQuiz(item, false)
      }
      setMessage({ tone: 'success', text: `Đã gửi tạo ${readyRows.length} bài kiểm tra.` })
      await loadHistory(normalizeOpenEdxCourseId(courseId))
    } finally {
      setBusy(false)
      setCreatingKey('')
    }
  }

  function updateConfig(kind: 'quiz' | 'final', patch: Partial<AssessmentConfig>) {
    const updater = (current: AssessmentConfig): AssessmentConfig => ({ ...current, ...patch })
    if (kind === 'final') setFinalConfig(updater)
    else setQuizConfig(updater)
  }

  function ConfigPanel({ kind, config }: { kind: 'quiz' | 'final'; config: AssessmentConfig }) {
    const total = config.easy + config.medium + config.hard
    const title = kind === 'final' ? 'Cấu hình Final test' : 'Cấu hình Quiz tự luyện'
    const note = kind === 'final' ? 'Dùng riêng cho dòng chọn Tạo Final test.' : 'Dùng cho các dòng chọn Tạo Quiz.'
    return <div className="popup-action-panel">
      <div className="section-heading compact-heading">
        <div>
          <h3>{title}</h3>
          <p className="muted">{note}</p>
        </div>
        <span className={classNames('status', total === 100 ? 'success' : 'warning')}>{total}%</span>
      </div>
      <div className="quiz-small-grid">
        <label>Số câu<input className="input" type="number" min={1} max={200} value={config.totalQuestions} onChange={(event) => updateConfig(kind, { totalQuestions: normalizeNumber(Number(event.target.value), kind === 'final' ? 30 : 15, 1, 200) })} /></label>
        <label>Easy %<input className="input" type="number" value={config.easy} onChange={(event) => updateConfig(kind, { easy: normalizeNumber(Number(event.target.value), 0, 0, 100) })} /></label>
        <label>Medium %<input className="input" type="number" value={config.medium} onChange={(event) => updateConfig(kind, { medium: normalizeNumber(Number(event.target.value), 0, 0, 100) })} /></label>
        <label>Hard %<input className="input" type="number" value={config.hard} onChange={(event) => updateConfig(kind, { hard: normalizeNumber(Number(event.target.value), 0, 0, 100) })} /></label>
      </div>
      <div className="section-heading compact-heading quiz-timer-subhead">
        <div>
          <h3>Timer</h3>
          <p className="muted">Thời gian làm bài và chờ làm lại.</p>
        </div>
        <label className="toggle-line toggle-strong">
          <input type="checkbox" checked={config.timerEnabled} onChange={(event) => updateConfig(kind, { timerEnabled: event.target.checked })} />
          <span>Bật</span>
        </label>
      </div>
      <div className="quiz-small-grid two-cols">
        <label>Thời gian/phút<input className="input" type="number" min={1} max={300} disabled={!config.timerEnabled} value={config.timeLimitMinutes} onChange={(event) => updateConfig(kind, { timeLimitMinutes: normalizeNumber(Number(event.target.value), kind === 'final' ? 60 : 15, 1, 300) })} /></label>
        <label>Chờ làm lại/phút<input className="input" type="number" min={0} max={10080} disabled={!config.timerEnabled} value={config.retakeCooldownMinutes} onChange={(event) => updateConfig(kind, { retakeCooldownMinutes: normalizeNumber(Number(event.target.value), 0, 0, 10080) })} /></label>
      </div>
      <div className="option-grid compact-options">
        <label className="toggle-line"><input type="checkbox" disabled={!config.timerEnabled} checked={config.autoSubmitOnTimeout} onChange={(event) => updateConfig(kind, { autoSubmitOnTimeout: event.target.checked })} /><span>Tự nộp khi hết giờ</span></label>
        <label className="toggle-line"><input type="checkbox" disabled={!config.timerEnabled} checked={config.lockAfterTimeout} onChange={(event) => updateConfig(kind, { lockAfterTimeout: event.target.checked })} /><span>Khóa sau hết giờ</span></label>
      </div>
    </div>
  }

  useEffect(() => {
    const normalizedCourseId = normalizeOpenEdxCourseId(courseId)
    if (!courseId.trim()) {
      setAutoMap(null)
      setSelectedOfferingId('')
      setHistory([])
      setMessage(null)
      setChapterActions({})
      return undefined
    }
    if (!normalizedCourseId) return undefined
    const timer = window.setTimeout(() => {
      runPreview('', false).catch(() => undefined)
    }, 750)
    return () => window.clearTimeout(timer)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [courseId])

  const mappingColumns = useMemo<EnterpriseTableColumn<EffectiveQuizMapping>[]>(() => [
    {
      key: 'stt', header: 'STT', kind: 'index', width: 52, sticky: 'left', hideable: false,
      render: (_row, index) => index + 1,
    },
    {
      key: 'chapter', header: 'Bài trong ngân hàng', kind: 'identity', minWidth: 230, priority: 'required', hideable: false,
      render: (item) => <div className="quiz-map-identity"><b>{item.chapter_title}</b><small>{titleForItem(item)}</small></div>,
    },
    {
      key: 'cms_mapping', header: 'Map Course CMS', kind: 'identity', minWidth: 290, priority: 'required', hideable: false, truncateLines: 2,
      render: (item) => <div className="quiz-map-target">
        {item.openedx_section_title ? <><b>{item.openedx_section_title}</b><small>{item.openedx_section_id}</small></> : <span className={classNames('status', item.effectiveRequiresQuiz ? 'danger' : 'pending')}>{courseTreeUnavailable ? 'Chưa đọc được cây Course CMS' : 'Chưa tìm thấy Section'}</span>}
        {item.release_code ? <small><strong>Release:</strong> {item.release_code}{item.openedx_library_key ? ` · ${item.openedx_library_key}` : ''}</small> : <small>{item.effectiveRequiresQuiz ? 'Chưa có Release published' : 'Không yêu cầu Release'}</small>}
      </div>,
    },
    {
      key: 'action', header: 'Tạo gì', kind: 'status', width: 172, priority: 'required', hideable: false,
      render: (item) => <select className="input compact-select" value={item.action === 'assignment' ? 'skip' : item.action} disabled={busy || Boolean(creatingKey)} onChange={(event) => {
        const next = event.target.value as QuizChapterAction
        setChapterActions((current) => ({ ...current, [item.chapter_id]: next }))
      }} aria-label={`Chọn hành động cho ${item.chapter_title}`}>
        <option value="quiz">Tạo Quiz</option>
        <option value="final_test">Tạo Final test</option>
        <option value="skip">Không tạo</option>
      </select>,
    },
    {
      key: 'readiness', header: 'Điều kiện', kind: 'status', width: 168, priority: 'important', hideable: true,
      render: (item) => <div className="quiz-requirement-stack"><span className={classNames('status', productionStatusClass(item))}>{item.effectiveRequiresQuiz ? ((item as any).status_label || actionStatusText(item)) : 'Không tạo'}</span>{item.effectiveRequiresQuiz && ((item as any).missing_requirements || []).length ? <small>{((item as any).missing_requirements || []).map(missingRequirementLabel).join(' · ')}</small> : <small>{item.effectiveRequiresQuiz ? 'Đủ Section + Release' : 'Không yêu cầu'}</small>}</div>,
    },
    {
      key: 'match', header: 'Khớp', kind: 'number', width: 86, priority: 'optional', hideable: true, defaultVisible: false,
      render: (item) => <span title={item.match_reason || ''}>{percent(item.match_score)}</span>,
    },
    {
      key: 'actions', header: 'Thao tác', kind: 'actions', width: 126, sticky: 'right', hideable: false,
      render: (item) => item.effectiveRequiresQuiz ? <button className="btn small" disabled={!item.effectiveReady || !item.course_chapter_mapping_id || creatingKey === item.chapter_id || busy} onClick={() => setCreateModal({ kind: 'one', item })}>{creatingKey === item.chapter_id ? 'Đang tạo...' : item.action === 'final_test' ? 'Tạo Final' : 'Tạo Quiz'}</button> : <span className="muted">Bỏ qua</span>,
    },
  ], [busy, courseTreeUnavailable, creatingKey, titleForItem])

  const historyColumns = useMemo<EnterpriseTableColumn<CourseQuizInstance>[]>(() => [
    { key: 'stt', header: 'STT', kind: 'index', width: 52, hideable: false, render: (_row, index) => index + 1 },
    { key: 'quiz', header: 'Bài kiểm tra', kind: 'identity', minWidth: 250, priority: 'required', hideable: false, render: (item) => <div className="quiz-history-identity"><b>{item.metadata_json?.quiz_title || 'Bài kiểm tra Open edX'}</b><small>{item.openedx_unit_node_id || item.bank_release_id}</small></div> },
    { key: 'type', header: 'Loại', kind: 'status', width: 108, priority: 'important', hideable: true, render: (item) => item.metadata_json?.assessment_type === 'final_test' ? <span className="status warning">Final test</span> : <span className="status pending">Quiz</span> },
    { key: 'status', header: 'Trạng thái', kind: 'status', width: 122, priority: 'important', hideable: true, render: (item) => <span className={classNames('status', item.status === 'created' || item.status === 'published' ? 'success' : item.status === 'rolled_back' || item.status === 'failed' ? 'danger' : 'pending')}>{item.status}</span> },
    { key: 'timer', header: 'Timer', kind: 'number', width: 94, priority: 'optional', hideable: true, render: (item) => item.metadata_json?.timer_config?.custom_timer_enabled ? `${item.metadata_json.timer_config.time_limit_minutes || Math.round((item.metadata_json.timer_config.duration_seconds || 0) / 60)} phút` : 'Tắt' },
    { key: 'created_at', header: 'Thời điểm', kind: 'date', width: 138, priority: 'important', hideable: true, render: (item) => formatVNDateTime(item.created_at) },
    { key: 'actions', header: 'Thao tác', kind: 'actions', width: 116, hideable: false, render: (item) => <button className="btn small secondary" disabled={busy || item.status === 'rolled_back'} onClick={async () => {
      setBusy(true)
      try {
        const result = await rollbackCourseQuizInstance(headers, item.id, { mode: 'safe', note: 'Khôi phục từ giao diện lịch sử bài kiểm tra' })
        setMessage(inlineMessageFromBackend(result, result.message || 'Đã khôi phục bài kiểm tra.', result.ok ? 'success' : 'warning'))
        await loadHistory(normalizeOpenEdxCourseId(courseId))
      } catch (error) {
        setMessage({ tone: 'danger', text: error instanceof Error ? error.message : 'Khôi phục thất bại' })
      } finally {
        setBusy(false)
      }
    }}>Khôi phục</button> },
  ], [busy, courseId, headers])

  if (!can('publish_questions')) return <PageRoot className="page-stack bank-multipage bank-contract-page bank-quiz-page">
    <PageHeader eyebrow="Ngân hàng đề" title="Tạo Quiz trên Open edX" icon="quiz" breadcrumbs={[{ label: 'Ngân hàng đề', href: '/bank/departments' }, { label: 'Tạo Quiz' }]} />
    <BankPageIdentity title="Tạo Quiz trên Open edX" description="Map Course CMS và tạo Quiz hoặc Final test từ Release đã publish." icon="quiz" tone="violet" />
    <div className="bank-contract-empty-state bank-permission-state"><VisualIcon icon="shield" tone="violet" label="Không có quyền" size={24} /><div><b>Không có quyền thực hiện</b><p>Bạn không có quyền map khóa học hoặc tạo Quiz trên CMS.</p></div></div>
  </PageRoot>

  const workflowStep = !autoMap ? 1 : !applied ? 2 : 3

  return <PageRoot className="page-stack bank-multipage bank-contract-page bank-quiz-page quiz-creation-workbench">
    <PageHeader
      eyebrow="Ngân hàng đề"
      title="Tạo Quiz trên Open edX"
      icon="quiz"
      breadcrumbs={[{ label: 'Ngân hàng đề', href: '/bank/departments' }, { label: 'Tạo Quiz' }]}
    />

    <BankPageIdentity
      title="Tạo Quiz trên Open edX"
      description="Map Course CMS, chọn phạm vi từ Release đã publish và tạo Quiz hoặc Final test theo quy trình có kiểm soát."
      icon="quiz"
      tone="violet"
      meta={applied ? <span className="status success">Đã lưu cấu hình</span> : autoMap ? <span className="status warning">Đang preview</span> : <span className="status pending">Chưa map</span>}
    />

    {message ? <div className={classNames('academic-inline-notice', messageClass(message))} role="alert" aria-live="polite">
      <VisualIcon label={message.text} icon={message.tone === 'danger' ? 'alert' : message.tone === 'success' ? 'check' : 'info'} tone={message.tone === 'danger' ? 'red' : message.tone === 'success' ? 'green' : message.tone === 'warning' ? 'amber' : 'blue'} size={18} className="notice-visual-icon" />
      <div className="notice-copy"><b>{message.tone === 'danger' ? 'Không thể hoàn tất thao tác' : message.tone === 'success' ? 'Đã hoàn tất' : message.tone === 'warning' ? 'Cần kiểm tra' : 'Thông tin'}</b><span>{message.text}</span></div>
    </div> : null}

    <BankWorkflowStepper
      currentStep={workflowStep}
      steps={[
        { title: 'Map khóa học', description: 'Nhập Course ID và chọn version', icon: 'link', tone: 'blue' },
        { title: 'Chọn phạm vi', description: 'Quiz, Final test hoặc bỏ qua', icon: 'filter', tone: 'violet' },
        { title: 'Tạo trên CMS', description: 'Kiểm tra cấu hình và xác nhận', icon: 'quiz', tone: 'green' },
      ]}
    />

    <div className="bank-quiz-main-grid">
      <BankSection
        title="Kết quả map"
        description="Kết quả map, trạng thái Release và Section của từng bài được hiển thị tại đây."
        icon="layers"
        tone="blue"
        meta={applied ? <span className="status success">Đã map</span> : autoMap ? <span className="status warning">Preview</span> : <span className="status pending">Chưa map</span>}
        className="bank-quiz-result-section"
        bodyClassName="bank-quiz-result-body"
      >
        {!autoMap ? <div className="bank-quiz-empty-map">
          <VisualIcon label="Chưa có kết quả map" icon="layers" tone="blue" size={28} className="bank-quiz-empty-map__icon" />
          <div><h3>Chưa có kết quả map</h3><p>Nhập Course ID và bấm “Kiểm tra map”. Sau khi resolve thành công, bảng bài học và trạng thái Release sẽ xuất hiện tại đây.</p></div>
          <div className="bank-quiz-empty-metrics" aria-label="Thông tin map chưa có dữ liệu">
            <div><span>Khóa học</span><b>—</b></div><div><span>Version môn</span><b>—</b></div><div><span>Release</span><b>—</b></div><div><span>Bài đã map</span><b>—</b></div>
          </div>
        </div> : <>
          <div className="bank-quiz-summary-grid" aria-label="Tóm tắt kết quả map">
            <div><span>Khóa học</span><b>{autoMap.openedx_course_id || normalizeOpenEdxCourseId(courseId) || '—'}</b></div>
            <div><span>Version môn</span><b>{autoMap.offering?.code || autoMap.offering?.id || selectedOfferingId || '—'}</b></div>
            <div><span>Bài đã map</span><b>{matchedCount}/{chapterCount || 0}</b></div>
            <div><span>Sẵn sàng tạo</span><b>{readyRows.length}</b></div>
          </div>

          <div className="quiz-summary-strip bank-quiz-action-summary" aria-label="Tóm tắt phạm vi tạo">
            <div><span>Quiz</span><b>{regularQuizCount}</b><small>{quizConfig.totalQuestions} câu · {quizConfig.timeLimitMinutes} phút</small></div>
            <div><span>Final test</span><b>{finalTestCount}</b><small>{finalConfig.totalQuestions} câu · {finalConfig.timeLimitMinutes} phút</small></div>
            <div><span>Bỏ qua</span><b>{skippedCount}</b><small>Không tạo trên CMS</small></div>
            <div className={missingSectionCount ? 'is-warning' : ''}><span>Thiếu Section</span><b>{missingSectionCount}</b><small>Course CMS</small></div>
            <div className={missingReleaseCount ? 'is-warning' : ''}><span>Thiếu Release</span><b>{missingReleaseCount}</b><small>Bank published</small></div>
          </div>

          {autoMap.course_tree ? <div className={`alert ${autoMap.course_tree.source === 'unavailable' ? 'danger' : autoMap.course_tree.source === 'cached' ? 'warning' : 'info'}`}><b>Nguồn cây Course CMS:</b> {autoMap.course_tree.source === 'direct' ? 'Open edX trực tiếp' : autoMap.course_tree.source === 'cached' ? `Dữ liệu sync cũ (${autoMap.course_tree.cached_block_count || 0} block)` : `Không khả dụng${autoMap.course_tree.error_code ? ` · ${autoMap.course_tree.error_code}` : ''}`}</div> : null}
          {autoMap.blocking_errors?.length ? <div className="alert danger"><b>Chưa thể lưu hoặc tạo</b><ul>{autoMap.blocking_errors.slice(0, 5).map((item, index) => <li key={index}>{item}</li>)}</ul></div> : null}
          {autoMap.warnings?.length ? <details className="quiz-warning-details"><summary>Có {autoMap.warnings.length} cảnh báo cần xem</summary><ul>{autoMap.warnings.map((item, index) => <li key={index}>{item}</li>)}</ul></details> : null}

          <EnterpriseDataTable
            tableId="bank-quiz-course-mappings"
            caption="Danh sách bài và mapping"
            rows={effectiveMappings}
            columns={mappingColumns}
            rowKey={(item) => item.chapter_id}
            density="compact"
            emptyTitle="Version môn chưa có bài"
            emptyDescription="Kiểm tra lại version môn hoặc dữ liệu Chapter trong ngân hàng đề."
            label="bài"
          />

          <div className="quiz-mapping-action-bar bank-quiz-result-actions">
            <div><b>{applied ? 'Cấu hình đã được lưu.' : 'Cần lưu cấu hình trước khi tạo.'}</b><small>{missingSectionCount || missingReleaseCount ? 'Đổi dòng bị chặn sang Không tạo hoặc hoàn thiện Section/Release.' : `${readyRows.length} bài đã sẵn sàng tạo trên Open edX.`}</small></div>
            <div className="button-row no-margin"><button className="btn secondary" disabled={busy || !autoMap} onClick={runApply}>{busy ? 'Đang lưu...' : 'Lưu cấu hình'}</button><button className="btn" disabled={!canCreateQuiz || busy || Boolean(creatingKey)} onClick={() => setCreateModal({ kind: 'all' })}>Tạo {readyRows.length} bài kiểm tra</button></div>
          </div>
        </>}
      </BankSection>

      <BankSection
        title="Cấu hình map"
        description="Nhập Course ID, kiểm tra version môn và lưu cấu hình trước khi tạo trên CMS."
        icon="settings"
        tone="violet"
        className="bank-quiz-config-section"
        bodyClassName="bank-quiz-config-body"
      >
        <div className="bank-quiz-config-form">
          <label>Khóa học ID<input className="input" value={courseId} onBlur={() => { const normalized = normalizeOpenEdxCourseId(courseId); if (normalized) setCourseId(normalized) }} onChange={(event) => { setCourseId(event.target.value); setSelectedOfferingId(''); setAutoMap(null); setChapterActions({}) }} placeholder="course-v1:FPT+WEB107+SU26" /></label>
          <label>Version môn<select className="input" value={selectedOfferingId || autoMap?.offering?.id || ''} disabled={busy || !candidates.length} onChange={async (event) => {
            const next = event.target.value
            setSelectedOfferingId(next)
            if (next) await runPreview(next, false)
          }}><option value="">{candidates.length ? 'Chọn version môn...' : 'Hệ thống tự xác định'}</option>{candidates.map((item) => <option key={item.offering_id} value={item.offering_id}>{item.offering_code}{item.course_run_match ? ' · khớp Course ID' : ''} · {item.ready_chapter_count}/{item.chapter_count} bài có Release</option>)}</select></label>
          <div className="bank-quiz-config-actions">
            <button className="btn secondary" type="button" disabled={busy || !normalizeOpenEdxCourseId(courseId)} onClick={() => runPreview(selectedOfferingId, true)}>{busy ? 'Đang kiểm tra...' : autoMap ? 'Kiểm tra lại' : 'Kiểm tra map'}</button>
            <button className="btn" type="button" disabled={busy || !autoMap} onClick={runApply}>{busy ? 'Đang lưu...' : 'Lưu cấu hình'}</button>
          </div>
          <div className="course-auto-hint bank-quiz-config-hint" role="status">{busy ? 'Đang tìm version môn và Section phù hợp...' : autoMap ? `Đã khớp ${matchedCount}/${chapterCount || 0} bài. ${selectedQuizCount} bài sẽ tạo, ${skippedCount} bài bỏ qua.` : 'Nhập Khóa học ID để bắt đầu. Hệ thống chỉ dùng Release đã publish.'}</div>
          <div className="bank-quiz-config-rules">
            <div><VisualIcon icon="info" tone="blue" label="Điều kiện map" size={16} /><span>Course ID phải đúng định dạng Open edX.</span></div>
            <div><VisualIcon icon="check" tone="green" label="Release published" size={16} /><span>Chỉ Release đã publish mới được dùng để tạo Quiz.</span></div>
            <div><VisualIcon icon="link" tone="violet" label="Section mapping" size={16} /><span>Mỗi bài cần map được Section tương ứng trên Course CMS.</span></div>
          </div>
          {autoMap ? <button className="btn secondary bank-quiz-config-secondary" type="button" disabled={busy} onClick={() => setCreateModal({ kind: 'all' })}>Cấu hình Quiz và Final test</button> : null}
        </div>
      </BankSection>
    </div>

    <BankSection
      title="Lịch sử của khóa học"
      description="Chỉ hiển thị bài kiểm tra thuộc Course ID đang nhập. Khôi phục là thao tác có audit."
      icon="audit"
      tone="slate"
      meta={historyBusy ? <span className="status pending">Đang tải</span> : <span className="status pending">{history.length} bản ghi</span>}
      className="bank-quiz-history-section"
    >
      {!normalizeOpenEdxCourseId(courseId) ? <div className="bank-contract-empty-state"><VisualIcon icon="audit" tone="slate" label="Chưa có Course ID" size={24} /><div><b>Chưa có Course ID</b><p>Nhập Course ID để xem lịch sử đúng khóa học.</p></div></div> : <EnterpriseDataTable tableId="bank-quiz-course-history" caption="Lịch sử bài kiểm tra" rows={history} columns={historyColumns} rowKey={(item) => item.id} density="compact" loading={historyBusy} label="bản ghi" emptyTitle="Chưa có bài kiểm tra" emptyDescription="Khóa học này chưa có Quiz hoặc Final test được tạo từ AI Server." />}
    </BankSection>

    <AccessibleDialog
      open={Boolean(createModal)}
      title={createModal?.kind === 'all' ? `Tạo ${readyRows.length} bài kiểm tra` : createModal ? `${actionLabel(createModal.item.action)} cho ${createModal.item.chapter_title}` : 'Cấu hình tạo bài kiểm tra'}
      description="Quiz tự luyện và Final test có cấu hình riêng. Kiểm tra tỷ lệ độ khó trước khi xác nhận."
      onClose={() => setCreateModal(null)}
      size="xlarge"
      className="quiz-config-modal"
      bodyClassName="quiz-config-modal-body"
    >
      {createModal ? <>
          <div className="quiz-modal-grid">{(createModal.kind === 'all' || createModal.item.action === 'quiz') ? <ConfigPanel kind="quiz" config={quizConfig} /> : null}{(createModal.kind === 'all' || createModal.item.action === 'final_test') ? <ConfigPanel kind="final" config={finalConfig} /> : null}</div>
          <div className="quiz-create-preview"><b>Phạm vi xác nhận</b><span>{createModal.kind === 'all' ? `${readyRows.length} bài đủ điều kiện sẽ được tạo. Các dòng Không tạo hoặc còn thiếu điều kiện được bỏ qua.` : `${createModal.item.chapter_title} sẽ được tạo bằng Release ${createModal.item.release_code || 'đã chọn'}.`}</span><small>Course ID: {normalizeOpenEdxCourseId(courseId) || '—'} · Quiz {quizConfig.easy}/{quizConfig.medium}/{quizConfig.hard} · Final {finalConfig.easy}/{finalConfig.medium}/{finalConfig.hard}</small></div>
          {(quizDifficultyTotal !== 100 || finalDifficultyTotal !== 100) ? <div className="alert warning">Tổng tỷ lệ Easy/Medium/Hard của mỗi loại phải bằng 100%.</div> : null}
          <div className="modal-actions"><button className="btn secondary" type="button" disabled={busy || Boolean(creatingKey)} onClick={() => setCreateModal(null)}>Hủy</button><button className="btn" type="button" disabled={busy || Boolean(creatingKey) || quizDifficultyTotal !== 100 || finalDifficultyTotal !== 100 || (createModal.kind === 'all' && !readyRows.length)} onClick={confirmCreateFromModal}>{createModal.kind === 'all' ? `Tạo ${readyRows.length} bài kiểm tra` : actionLabel(createModal.item.action)}</button></div>
      </> : null}
    </AccessibleDialog>
  </PageRoot>
}
