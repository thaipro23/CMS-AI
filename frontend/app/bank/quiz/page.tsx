'use client'

import { formatVNDateTime } from '../../../lib/time'
import Link from 'next/link'
import { useEffect, useMemo, useState } from 'react'
import { useAppContext } from '../../../context/AppContext'
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

function isErrorMessage(message: string) {
  const lower = message.toLowerCase()
  return lower.includes('lỗi') || lower.includes('thất bại') || lower.includes('không') || lower.includes('failed')
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
  if (!item.effectiveRequiresQuiz) return 'Không tạo'
  if (item.effectiveReady) return item.action === 'final_test' ? 'Sẵn sàng tạo Final test' : 'Sẵn sàng tạo Quiz'
  return 'Cần Release + Section'
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
  const [message, setMessage] = useState('')
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
    const normalizedCourseId = String(targetCourseId || '').trim()
    if (!normalizedCourseId) {
      setHistory([])
      return
    }
    setHistoryBusy(true)
    try {
      const data = await getCourseQuizInstances(headers, { openedx_course_id: normalizedCourseId, limit: 100 }).catch(() => [])
      setHistory(data.filter((item) => item.openedx_course_id === normalizedCourseId))
    } finally {
      setHistoryBusy(false)
    }
  }

  async function runPreview(offeringId = selectedOfferingId, keepPlan = false) {
    setBusy(true)
    setMessage('')
    setAutoMap(null)
    try {
      const result = await previewQuizAutoMap(headers, {
        openedx_course_id: courseId.trim(),
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
      await loadHistory(courseId.trim())
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Không tự kiểm tra được course Open edX')
    } finally {
      setBusy(false)
    }
  }

  async function runApply() {
    setBusy(true)
    setMessage('')
    try {
      const result = await applyQuizAutoMap(headers, {
        openedx_course_id: courseId.trim(),
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
      setMessage(result.message || 'Đã lưu cấu hình map Khóa học ID.')
      await loadHistory(courseId.trim())
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Lưu cấu hình tự động thất bại')
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
    setMessage('')
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
      setMessage((result.message || `Đã tạo ${actionLabel(item.action)} cho ${item.chapter_title}`) + timerText)
      if (refreshHistory) await loadHistory(courseId.trim())
    } catch (error) {
      setMessage(error instanceof Error ? error.message : `Tạo bài kiểm tra cho ${item.chapter_title} thất bại`)
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
    setMessage(`Đang tạo ${readyRows.length} bài kiểm tra. Vui lòng chờ...`)
    try {
      for (const item of readyRows) {
        // eslint-disable-next-line no-await-in-loop
        await executeCreateOneQuiz(item, false)
      }
      setMessage(`Đã gửi tạo ${readyRows.length} bài kiểm tra.`)
      await loadHistory(courseId.trim())
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
    const normalizedCourseId = courseId.trim()
    if (!normalizedCourseId) {
      setAutoMap(null)
      setSelectedOfferingId('')
      setHistory([])
      setMessage('')
      setChapterActions({})
      return undefined
    }
    const timer = window.setTimeout(() => {
      runPreview('', false).catch(() => undefined)
    }, 750)
    return () => window.clearTimeout(timer)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [courseId])

  if (!can('publish_questions')) return <div className="card empty-state">Bạn không có quyền map khóa học hoặc tạo quiz.</div>

  return <div className="page-stack bank-quiz-page quiz-workbench">
    <section className="card page-intro quiz-hero">
      <div>
        <div className="eyebrow">Open edX assessment</div>
        <h1>Map khóa học và chọn bài cần tạo Quiz</h1>
        <p>Không bắt buộc mọi bài đều tạo bài kiểm tra. Ở cột Trạng thái, chọn Tạo Quiz, Tạo Final test hoặc Không tạo.</p>
      </div>
      <div className="button-row">
        <Link className="btn secondary" href="/bank">Tổng quan</Link>
        <Link className="btn secondary" href="/bank/departments">Quản lý bộ môn</Link>
      </div>
    </section>

    {message ? <div className={classNames('alert quiz-inline-message', isErrorMessage(message) ? 'danger' : 'success')}>{message}</div> : null}

    <div className="quiz-workbench-grid">
      <aside className="quiz-settings-panel card" aria-label="Cấu hình tạo bài kiểm tra">
        <div className="settings-panel-head">
          <div>
            <div className="eyebrow">Cấu hình</div>
            <h2>Version và phạm vi tạo</h2>
            <p>Chọn version môn, sau đó đặt Trạng thái cho từng bài: Tạo Quiz, Tạo Final test hoặc Không tạo.</p>
          </div>
          {applied ? <span className="status success">Đã lưu cấu hình</span> : autoMap ? <span className="status warning">Preview</span> : <span className="status pending">Chưa kiểm tra</span>}
        </div>

        <div className="settings-section course-control-section">
          <label>Khóa học ID
            <input className="input" value={courseId} onChange={(event) => { setCourseId(event.target.value); setSelectedOfferingId(''); setAutoMap(null); setChapterActions({}) }} placeholder="course-v1:FPT+WEB107+SU26" />
          </label>
          <div className="course-auto-hint">
            {busy ? 'Đang tự tìm version và Section...' : autoMap ? `Đã tìm thấy ${matchedCount}/${chapterCount || 0} Section khớp.` : 'Nhập Khóa học ID, hệ thống sẽ tự tìm version và Section.'}
          </div>
          {candidates.length ? <label>Version môn
            <select className="input" value={selectedOfferingId || autoMap?.offering?.id || ''} disabled={busy} onChange={async (event) => {
              const next = event.target.value
              setSelectedOfferingId(next)
              if (next) await runPreview(next, false)
            }}>
              <option value="">Chọn version môn...</option>
              {candidates.map((item) => <option key={item.offering_id} value={item.offering_id}>
                {item.offering_code}{item.course_run_match ? ' · khớp Khóa học ID' : ''} · {item.ready_chapter_count}/{item.chapter_count} bài có Release{item.all_ready ? '' : ' · vẫn có thể chọn'}
              </option>)}
            </select>
          </label> : null}
          <div className="settings-actions settings-actions-top">
            <button className="btn secondary full-width" disabled={busy || !autoMap} onClick={runApply}>{busy ? 'Đang lưu...' : 'Lưu cấu hình'}</button>
            <button className="btn success full-width" disabled={!canCreateQuiz || busy || Boolean(creatingKey)} onClick={() => setCreateModal({ kind: 'all' })}>Tạo bài kiểm tra ({readyRows.length || 0})</button>
          </div>
        </div>

        <div className="settings-section settings-card-soft quiz-config-summary">
          <div className="section-heading compact-heading">
            <div>
              <h3>Phạm vi hiện tại</h3>
              <p className="muted">Có thể đổi từng dòng trong bảng map.</p>
            </div>
            <span className="status pending">{selectedQuizCount} tạo · {skippedCount} bỏ qua</span>
          </div>
          <div className="quiz-config-summary-list">
            <span><b>Quiz:</b> {quizConfig.totalQuestions} câu · {quizConfig.timeLimitMinutes} phút</span>
            <span><b>Final test:</b> {finalConfig.totalQuestions} câu · {finalConfig.timeLimitMinutes} phút</span>
            <span>Easy/Medium/Hard tách riêng theo từng loại bài kiểm tra.</span>
          </div>
        </div>
      </aside>

      <main className="quiz-workspace-main">
        {!autoMap ? <section className="card empty-state quiz-empty-guide">
          <b>Chưa có kết quả map.</b>
          <span>Nhập Khóa học ID ở panel bên phải. Hệ thống tự tìm version môn và Section phù hợp, kết quả sẽ hiện tại đây.</span>
        </section> : <section className="card quiz-result-card">
          <div className="section-heading result-heading">
            <div>
              <h2>Kết quả map</h2>
              <p className="muted">Chỉ các dòng chọn Tạo Quiz hoặc Tạo Final test mới cần Release published. Dòng Không tạo không chặn lưu cấu hình.</p>
            </div>
            <span className={classNames('status', autoMap.can_apply ? 'success' : 'warning')}>{autoMap.can_apply ? 'Có thể lưu cấu hình' : 'Cần xử lý'}</span>
          </div>
          {autoMap.blocking_errors?.length ? <div className="alert danger"><b>Chưa thể lưu/tạo</b><ul>{autoMap.blocking_errors.map((item, index) => <li key={index}>{item}</li>)}</ul></div> : null}
          {autoMap.warnings?.length ? <div className="alert warning"><b>Cảnh báo</b><ul>{autoMap.warnings.map((item, index) => <li key={index}>{item}</li>)}</ul></div> : null}
          <div className="table-wrap quiz-map-table-wrap">
            <table className="data-table compact-table quiz-map-table">
              <thead><tr><th>STT</th><th>Bài trong ngân hàng</th><th>Mục trong khóa học</th><th>Bộ đề</th><th>Khớp</th><th>Trạng thái</th><th></th></tr></thead>
              <tbody>{effectiveMappings.map((item, index) => <tr key={item.chapter_id} className={item.effectiveReady || !item.effectiveRequiresQuiz ? 'row-ready' : 'row-blocked'}>
                <td className="stt-cell">{index + 1}</td>
                <td><b>{item.chapter_title}</b></td>
                <td>{item.openedx_section_title ? <><b>{item.openedx_section_title}</b><small><code>{item.openedx_section_id}</code></small></> : <span className="status danger">Chưa tìm thấy</span>}</td>
                <td>{item.release_code ? <><b>{item.release_code}</b><small>{item.openedx_library_key}</small></> : item.effectiveRequiresQuiz ? <span className="status danger">Chưa publish</span> : <span className="muted">Không cần Release</span>}</td>
                <td>{percent(item.match_score)}<small>{item.match_reason}</small></td>
                <td>
                  <select className="input compact-select" value={item.action === 'assignment' ? 'skip' : item.action} disabled={busy || Boolean(creatingKey)} onChange={(event) => {
                    const next = event.target.value as QuizChapterAction
                    setChapterActions((current) => ({ ...current, [item.chapter_id]: next }))
                  }} aria-label={`Chọn trạng thái ${item.chapter_title}`}>
                    <option value="quiz">Tạo Quiz</option>
                    <option value="final_test">Tạo Final test</option>
                    <option value="skip">Không tạo</option>
                  </select>
                  <span className={classNames('status', actionStatusClass(item))}>{actionStatusText(item)}</span>
                  {item.course_chapter_mapping_id ? <small>Đã lưu cấu hình</small> : applied && item.effectiveRequiresQuiz ? <small>Cần bấm Lưu cấu hình</small> : null}
                </td>
                <td><button className="btn small" disabled={!item.effectiveReady || !item.course_chapter_mapping_id || creatingKey === item.chapter_id || busy} onClick={() => setCreateModal({ kind: 'one', item })}>{creatingKey === item.chapter_id ? 'Đang tạo...' : item.action === 'final_test' ? 'Tạo Final test' : 'Tạo Quiz'}</button></td>
              </tr>)}</tbody>
            </table>
          </div>
        </section>}

        <section className="card quiz-history-card">
          <div className="section-heading result-heading">
            <div>
              <h2>Lịch sử bài kiểm tra</h2>
              <p className="muted">Chỉ hiển thị lịch sử của Khóa học ID đang nhập. Nếu tạo nhầm, bấm khôi phục.</p>
            </div>
            {historyBusy ? <span className="status pending">Đang tải</span> : <span className="status pending">{history.length} bản ghi</span>}
          </div>
          {!courseId.trim() ? <div className="empty-state">Nhập Khóa học ID để xem lịch sử bài kiểm tra của đúng khóa học đó.</div> : null}
          {courseId.trim() && historyBusy ? <div className="empty-state">Đang tải lịch sử bài kiểm tra...</div> : null}
          {courseId.trim() ? <div className="table-wrap"><table className="data-table compact-table"><thead><tr><th>STT</th><th>Khóa học</th><th>Loại</th><th>Trạng thái</th><th>Bài kiểm tra Open edX</th><th>Timer</th><th>Thời gian</th><th></th></tr></thead><tbody>{history.map((item, index) => <tr key={item.id}><td className="stt-cell">{index + 1}</td><td><b>{item.openedx_course_id}</b><small>{item.metadata_json?.quiz_title || item.bank_release_id}</small></td><td>{item.metadata_json?.assessment_type === 'final_test' ? <span className="status warning">Final test</span> : <span className="status pending">Quiz</span>}</td><td><span className={classNames('status', item.status === 'created' ? 'success' : item.status?.includes('khôi phục') || item.status === 'failed' ? 'danger' : 'pending')}>{item.status}</span></td><td><code>{item.openedx_unit_node_id || '—'}</code></td><td>{item.metadata_json?.timer_config?.custom_timer_enabled ? <span className="status pending">{item.metadata_json.timer_config.time_limit_minutes || Math.round((item.metadata_json.timer_config.duration_seconds || 0) / 60)} phút</span> : <span className="muted">Không bật</span>}</td><td>{formatVNDateTime(item.created_at)}</td><td><button className="btn small secondary" disabled={busy || item.status === 'rolled_back'} onClick={async () => {
            setBusy(true)
            try {
              const result = await rollbackCourseQuizInstance(headers, item.id, { mode: 'safe', note: 'Khôi phục từ giao diện lịch sử bài kiểm tra' })
              setMessage(result.message)
              await loadHistory(courseId.trim())
            } catch (error) {
              setMessage(error instanceof Error ? error.message : 'Khôi phục thất bại')
            } finally {
              setBusy(false)
            }
          }}>Khôi phục</button></td></tr>)}</tbody></table></div> : null}
          {courseId.trim() && !history.length && !historyBusy ? <div className="empty-state">Chưa có bài kiểm tra nào được tạo cho Khóa học ID này.</div> : null}
        </section>
      </main>
    </div>

    {createModal ? <div className="modal-backdrop bank-popup-backdrop" onMouseDown={() => setCreateModal(null)}>
      <section className="modal-card bank-modal bank-modal-wide quiz-config-modal" role="dialog" aria-modal="true" onMouseDown={(event) => event.stopPropagation()}>
        <div className="section-heading bank-modal-head">
          <div>
            <div className="eyebrow">Cấu hình tạo bài kiểm tra</div>
            <h2>{createModal.kind === 'all' ? `Tạo ${readyRows.length} bài kiểm tra` : `${actionLabel(createModal.item.action)} cho ${createModal.item.chapter_title}`}</h2>
            <p className="muted">Quiz tự luyện và Final test có cấu hình riêng. Dòng Không tạo sẽ được bỏ qua.</p>
          </div>
          <button className="btn secondary" type="button" onClick={() => setCreateModal(null)}>Đóng</button>
        </div>
        <div className="bank-modal-body quiz-config-modal-body">
          <div className="quiz-modal-grid">
            {(createModal.kind === 'all' || createModal.item.action === 'quiz') ? <ConfigPanel kind="quiz" config={quizConfig} /> : null}
            {(createModal.kind === 'all' || createModal.item.action === 'final_test') ? <ConfigPanel kind="final" config={finalConfig} /> : null}
          </div>
          <div className="quiz-create-preview">
            <b>Quy tắc tạo</b>
            <span>Quiz: tạo Subsection/Unit dạng Quiz. Final test: dùng title và timer riêng, không ép theo cấu hình Quiz tự luyện.</span>
            <small>Khóa học ID: {courseId.trim() || '—'} · {createModal.kind === 'all' ? `${readyRows.length} bài kiểm tra` : createModal.item.chapter_title}</small>
          </div>
          <div className="modal-actions">
            <button className="btn secondary" type="button" disabled={busy || Boolean(creatingKey)} onClick={() => setCreateModal(null)}>Hủy</button>
            <button className="btn" type="button" disabled={busy || Boolean(creatingKey) || quizDifficultyTotal !== 100 || finalDifficultyTotal !== 100} onClick={confirmCreateFromModal}>{createModal.kind === 'all' ? `Tạo ${readyRows.length} bài kiểm tra` : actionLabel(createModal.item.action)}</button>
          </div>
        </div>
      </section>
    </div> : null}
  </div>
}
