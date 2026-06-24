'use client'

import Link from 'next/link'
import { useEffect, useMemo, useState } from 'react'
import { useAppContext } from '../../../context/AppContext'
import { CourseQuizInstance, QuizAutoMapResult } from '../../../types'
import {
  applyQuizAutoMap,
  createQuizFromBankRelease,
  getCourseQuizInstances,
  previewQuizAutoMap,
  rollbackCourseQuizInstance,
} from '../../../lib/api'

type QuizMapping = QuizAutoMapResult['mappings'][number]
type PendingCreate = { kind: 'one'; item: QuizMapping } | { kind: 'all' }

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



export default function BankQuizPage() {
  const { authHeaders, can } = useAppContext()
  const headers = useMemo(() => authHeaders(true), [authHeaders])
  const [courseId, setCourseId] = useState('')
  const [autoMap, setAutoMap] = useState<QuizAutoMapResult | null>(null)
  const [history, setHistory] = useState<CourseQuizInstance[]>([])
  const [busy, setBusy] = useState(false)
  const [historyBusy, setHistoryBusy] = useState(false)
  const [creatingKey, setCreatingKey] = useState<string>('')
  const [message, setMessage] = useState('')
  const [totalQuestions, setTotalQuestions] = useState(15)
  const [difficultyEasy, setDifficultyEasy] = useState(50)
  const [difficultyMedium, setDifficultyMedium] = useState(30)
  const [difficultyHard, setDifficultyHard] = useState(20)
  const [selectedOfferingId, setSelectedOfferingId] = useState<string>('')
  const [customTimerEnabled, setCustomTimerEnabled] = useState(true)
  const [timeLimitMinutes, setTimeLimitMinutes] = useState(15)
  const [retakeCooldownMinutes, setRetakeCooldownMinutes] = useState(5)
  const [autoSubmitOnTimeout, setAutoSubmitOnTimeout] = useState(false)
  const [lockAfterTimeout, setLockAfterTimeout] = useState(true)
  const [createModal, setCreateModal] = useState<PendingCreate | null>(null)

  const loadHistory = async (targetCourseId = courseId) => {
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

  useEffect(() => {
    loadHistory('').catch(() => undefined)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])


  const runPreview = async (offeringId = selectedOfferingId) => {
    setBusy(true)
    setMessage('')
    setAutoMap(null)
    try {
      const result = await previewQuizAutoMap(headers, {
        openedx_course_id: courseId.trim(),
        selected_subject_offering_id: offeringId || null,
        total_questions: totalQuestions,
        difficulty_easy: difficultyEasy,
        difficulty_medium: difficultyMedium,
        difficulty_hard: difficultyHard,
        max_families_per_bank: 2,
      })
      setAutoMap(result)
      const picked = result.summary?.selected_subject_offering_id || result.offering?.id || ''
      if (picked) setSelectedOfferingId(picked)
      setMessage('')
      await loadHistory(courseId.trim())
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Không tự kiểm tra được course Open edX')
    } finally {
      setBusy(false)
    }
  }

  const runApply = async () => {
    setBusy(true)
    setMessage('')
    try {
      const result = await applyQuizAutoMap(headers, {
        openedx_course_id: courseId.trim(),
        selected_subject_offering_id: selectedOfferingId || autoMap?.offering?.id || null,
        total_questions: totalQuestions,
        difficulty_easy: difficultyEasy,
        difficulty_medium: difficultyMedium,
        difficulty_hard: difficultyHard,
        max_families_per_bank: 2,
      })
      setAutoMap(result)
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

  const executeCreateOneQuiz = async (item: QuizMapping, refreshHistory = true) => {
    if (!item.release_id || !item.course_chapter_mapping_id) return
    setCreatingKey(item.chapter_id)
    setMessage('')
    try {
      const suffix = quizSuffixFromChapterTitle(item.chapter_title)
      const title = `Quiz ${suffix}`
      const result = await createQuizFromBankRelease(headers, item.release_id, {
        course_chapter_mapping_id: item.course_chapter_mapping_id,
        quiz_title: title,
        unit_title: 'Quiz',
        total_questions: totalQuestions,
        difficulty_easy: difficultyEasy,
        difficulty_medium: difficultyMedium,
        difficulty_hard: difficultyHard,
        max_families_per_bank: 2,
        custom_timer_enabled: customTimerEnabled,
        time_limit_minutes: timeLimitMinutes,
        retake_cooldown_minutes: retakeCooldownMinutes,
        auto_submit_on_timeout: autoSubmitOnTimeout,
        lock_after_timeout: lockAfterTimeout,
        native_timed_exam: false,
      })
      const timerText = customTimerEnabled ? ` · Timer ${timeLimitMinutes} phút · làm lại sau ${retakeCooldownMinutes} phút` : ''
      setMessage((result.message || `Đã tạo Quiz cho ${item.chapter_title}`) + timerText)
      if (refreshHistory) await loadHistory(courseId.trim())
    } catch (error) {
      setMessage(error instanceof Error ? error.message : `Tạo Quiz cho ${item.chapter_title} thất bại`)
    } finally {
      setCreatingKey('')
    }
  }

  const confirmCreateFromModal = async () => {
    if (!createModal) return
    if (createModal.kind === 'one') {
      const item = createModal.item
      setCreateModal(null)
      await executeCreateOneQuiz(item)
      return
    }
    if (!autoMap?.mappings?.length) return
    const ready = autoMap.mappings.filter((item) => item.ready && item.release_id && item.course_chapter_mapping_id)
    setCreateModal(null)
    setBusy(true)
    setMessage(`Đang tạo ${ready.length} Quiz. Vui lòng chờ...`)
    try {
      for (const item of ready) {
        // eslint-disable-next-line no-await-in-loop
        await executeCreateOneQuiz(item, false)
      }
      setMessage(`Đã gửi tạo Quiz cho ${ready.length} bài.`)
      await loadHistory(courseId.trim())
    } finally {
      setBusy(false)
      setCreatingKey('')
    }
  }

  useEffect(() => {
    const normalizedCourseId = courseId.trim()
    if (!normalizedCourseId) {
      setAutoMap(null)
      setSelectedOfferingId('')
      setHistory([])
      setMessage('')
      return undefined
    }
    const timer = window.setTimeout(() => {
      runPreview('').catch(() => undefined)
    }, 750)
    return () => window.clearTimeout(timer)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [courseId])

  if (!can('publish_questions')) return <div className="card empty-state">Bạn không có quyền map khóa học hoặc tạo quiz.</div>

  const applied = autoMap?.mode === 'applied'
  const readyRows = autoMap?.mappings?.filter((item) => item.ready) || []
  const candidates = autoMap?.summary?.candidates || []
  const canCreateQuiz = applied && readyRows.length > 0
  const difficultyTotal = difficultyEasy + difficultyMedium + difficultyHard
  const matchedCount = autoMap?.summary?.matched_count || 0
  const chapterCount = autoMap?.summary?.chapter_count || 0

  return <div className="page-stack bank-quiz-page quiz-workbench">
    <section className="card page-intro quiz-hero">
      <div>
        <div className="eyebrow">Open edX Quiz</div>
        <h1>Map khóa học và tạo Quiz</h1>
        <p>Nhập Khóa học ID ở panel bên phải. Hệ thống tự tìm version/section, lịch sử chỉ hiện đúng Khóa học ID đang nhập.</p>
      </div>
      <div className="button-row">
        <Link className="btn secondary" href="/bank">Tổng quan</Link>
        <Link className="btn secondary" href="/bank/departments">Quản lý bộ môn</Link>
      </div>
    </section>

    {message ? <div className={classNames('alert quiz-inline-message', isErrorMessage(message) ? 'danger' : 'success')}>{message}</div> : null}

    <div className="quiz-workbench-grid">
      <aside className="quiz-settings-panel card" aria-label="Cấu hình tạo Quiz">
        <div className="settings-panel-head">
          <div>
            <div className="eyebrow">Cấu hình</div>
            <h2>Tạo Quiz</h2>
            <p>Nhập Khóa học ID để hệ thống tự map. Cấu hình số câu, độ khó và timer sẽ chỉnh trong popup khi tạo Quiz.</p>
          </div>
          {applied ? <span className="status success">Đã lưu cấu hình</span> : autoMap ? <span className="status warning">Preview</span> : <span className="status pending">Chưa kiểm tra</span>}
        </div>

        <div className="settings-section course-control-section">
          <label>Khóa học ID
            <input className="input" value={courseId} onChange={(event) => { setCourseId(event.target.value); setSelectedOfferingId(''); setAutoMap(null); }} placeholder="course-v1:FPT+WEB107+SU26" />
          </label>
          <div className="course-auto-hint">
            {busy ? 'Đang tự tìm version và Section...' : autoMap ? `Đã tìm thấy ${matchedCount}/${chapterCount || 0} Section khớp.` : 'Nhập Khóa học ID, hệ thống sẽ tự tìm version và Section.'}
          </div>
          {candidates.length ? <label>Version môn
            <select className="input" value={selectedOfferingId || autoMap?.offering?.id || ''} disabled={busy} onChange={async (event) => {
              const next = event.target.value
              setSelectedOfferingId(next)
              if (next) await runPreview(next)
            }}>
              <option value="">Chọn version môn...</option>
              {candidates.map((item) => <option key={item.offering_id} value={item.offering_id} disabled={!item.all_ready}>
                {item.offering_code}{item.course_run_match ? ' · khớp Khóa học ID' : ''} · {item.ready_chapter_count}/{item.chapter_count} bài{item.all_ready ? '' : ` · ${item.disabled_reason || 'chưa đủ điều kiện'}`}
              </option>)}
            </select>
          </label> : null}
          <div className="settings-actions settings-actions-top">
            <button className="btn secondary full-width" disabled={busy || !autoMap?.can_apply} onClick={runApply}>{busy ? 'Đang lưu...' : 'Lưu cấu hình'}</button>
            <button className="btn success full-width" disabled={!canCreateQuiz || busy || Boolean(creatingKey)} onClick={() => setCreateModal({ kind: 'all' })}>Tạo Quiz ({readyRows.length || 0})</button>
          </div>
        </div>

        <div className="settings-section settings-card-soft quiz-config-summary">
          <div className="section-heading compact-heading">
            <div>
              <h3>Cấu hình hiện tại</h3>
              <p className="muted">Sẽ được chỉnh lại trong popup trước khi tạo Quiz.</p>
            </div>
            <span className={classNames('status', difficultyTotal === 100 ? 'success' : 'warning')}>{difficultyTotal}%</span>
          </div>
          <div className="quiz-config-summary-list">
            <span><b>{totalQuestions}</b> câu/Quiz</span>
            <span>Easy {difficultyEasy}% · Medium {difficultyMedium}% · Hard {difficultyHard}%</span>
            <span>{customTimerEnabled ? `Timer ${timeLimitMinutes} phút · chờ làm lại ${retakeCooldownMinutes} phút` : 'Không bật timer'}</span>
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
            </div>
            <span className={classNames('status', autoMap.can_apply ? 'success' : 'warning')}>{autoMap.can_apply ? 'Sẵn sàng lưu cấu hình' : 'Cần xử lý'}</span>
          </div>
          {autoMap.blocking_errors?.length ? <div className="alert danger"><b>Chưa thể tạo Quiz</b><ul>{autoMap.blocking_errors.map((item, index) => <li key={index}>{item}</li>)}</ul></div> : null}
          {autoMap.warnings?.length ? <div className="alert warning"><b>Cảnh báo</b><ul>{autoMap.warnings.map((item, index) => <li key={index}>{item}</li>)}</ul></div> : null}
          <div className="table-wrap quiz-map-table-wrap">
            <table className="data-table compact-table quiz-map-table">
              <thead><tr><th>Bài trong ngân hàng</th><th>Mục trong khóa học</th><th>Bộ đề</th><th>Khớp</th><th>Trạng thái</th><th></th></tr></thead>
              <tbody>{autoMap.mappings.map((item) => <tr key={item.chapter_id} className={item.ready ? 'row-ready' : 'row-blocked'}>
                <td><b>{item.chapter_title}</b></td>
                <td>{item.openedx_section_title ? <><b>{item.openedx_section_title}</b><small><code>{item.openedx_section_id}</code></small></> : <span className="status danger">Chưa tìm thấy</span>}</td>
                <td>{item.release_code ? <><b>{item.release_code}</b><small>{item.openedx_library_key}</small></> : <span className="status danger">Chưa publish</span>}</td>
                <td>{percent(item.match_score)}<small>{item.match_reason}</small></td>
                <td><span className={classNames('status', item.ready ? 'success' : 'danger')}>{item.ready ? 'Sẵn sàng' : 'Chưa sẵn sàng'}</span>{item.course_chapter_mapping_id ? <small>Đã lưu cấu hình</small> : null}</td>
                <td><button className="btn small" disabled={!item.ready || !item.course_chapter_mapping_id || creatingKey === item.chapter_id || busy} onClick={() => setCreateModal({ kind: 'one', item })}>{creatingKey === item.chapter_id ? 'Đang tạo...' : 'Tạo Quiz'}</button></td>
              </tr>)}</tbody>
            </table>
          </div>
        </section>}

        <section className="card quiz-history-card">
          <div className="section-heading result-heading">
            <div>
              <h2>Lịch sử Quiz</h2>
              <p className="muted">Chỉ hiển thị lịch sử của Khóa học ID đang nhập. Nếu tạo nhầm, bấm khôi phục.</p>
            </div>
            {historyBusy ? <span className="status pending">Đang tải</span> : <span className="status pending">{history.length} bản ghi</span>}
          </div>
          {!courseId.trim() ? <div className="empty-state">Nhập Khóa học ID để xem lịch sử Quiz của đúng khóa học đó.</div> : null}
          {courseId.trim() && historyBusy ? <div className="empty-state">Đang tải lịch sử Quiz...</div> : null}
          {courseId.trim() ? <div className="table-wrap"><table className="data-table compact-table"><thead><tr><th>Khóa học</th><th>Trạng thái</th><th>Bài kiểm tra Open edX</th><th>Timer</th><th>Thời gian</th><th></th></tr></thead><tbody>{history.map((item) => <tr key={item.id}><td><b>{item.openedx_course_id}</b><small>{item.metadata_json?.quiz_title || item.bank_release_id}</small></td><td><span className={classNames('status', item.status === 'created' ? 'success' : item.status?.includes('khôi phục') || item.status === 'failed' ? 'danger' : 'pending')}>{item.status}</span></td><td><code>{item.openedx_unit_node_id || '—'}</code></td><td>{item.metadata_json?.timer_config?.custom_timer_enabled ? <span className="status pending">{item.metadata_json.timer_config.time_limit_minutes || Math.round((item.metadata_json.timer_config.duration_seconds || 0) / 60)} phút</span> : <span className="muted">Không bật</span>}</td><td>{new Date(item.created_at).toLocaleString()}</td><td><button className="btn small secondary" disabled={busy || item.status === 'rolled_back'} onClick={async () => {
            setBusy(true)
            try {
              const result = await rollbackCourseQuizInstance(headers, item.id, { mode: 'safe', note: 'Khôi phục từ giao diện lịch sử Quiz' })
              setMessage(result.message)
              await loadHistory(courseId.trim())
            } catch (error) {
              setMessage(error instanceof Error ? error.message : 'Khôi phục thất bại')
            } finally {
              setBusy(false)
            }
          }}>Khôi phục</button></td></tr>)}</tbody></table></div> : null}
          {courseId.trim() && !history.length && !historyBusy ? <div className="empty-state">Chưa có Quiz nào được tạo cho Khóa học ID này.</div> : null}
        </section>
      </main>
    </div>

    {createModal ? <div className="modal-backdrop bank-popup-backdrop" onMouseDown={() => setCreateModal(null)}>
      <section className="modal-card bank-modal bank-modal-wide quiz-config-modal" role="dialog" aria-modal="true" onMouseDown={(event) => event.stopPropagation()}>
        <div className="section-heading bank-modal-head">
          <div>
            <div className="eyebrow">Cấu hình tạo Quiz</div>
            <h2>{createModal.kind === 'all' ? `Tạo Quiz cho ${readyRows.length} bài sẵn sàng` : `Tạo Quiz cho ${createModal.item.chapter_title}`}</h2>
            <p className="muted">Chỉnh số câu, độ khó và timer tại đây trước khi xác nhận tạo Quiz.</p>
          </div>
          <button className="btn secondary" type="button" onClick={() => setCreateModal(null)}>Đóng</button>
        </div>
        <div className="bank-modal-body quiz-config-modal-body">
          <div className="quiz-modal-grid">
            <div className="popup-action-panel">
              <div className="section-heading compact-heading">
                <div>
                  <h3>Kế hoạch câu hỏi</h3>
                  <p className="muted">Áp dụng cho từng Quiz được tạo.</p>
                </div>
                <span className={classNames('status', difficultyTotal === 100 ? 'success' : 'warning')}>{difficultyTotal}%</span>
              </div>
              <div className="quiz-small-grid">
                <label>Số câu<input className="input" type="number" min={1} max={200} value={totalQuestions} onChange={(event) => setTotalQuestions(Number(event.target.value || 15))} /></label>
                <label>Easy %<input className="input" type="number" value={difficultyEasy} onChange={(event) => setDifficultyEasy(Number(event.target.value || 0))} /></label>
                <label>Medium %<input className="input" type="number" value={difficultyMedium} onChange={(event) => setDifficultyMedium(Number(event.target.value || 0))} /></label>
                <label>Hard %<input className="input" type="number" value={difficultyHard} onChange={(event) => setDifficultyHard(Number(event.target.value || 0))} /></label>
              </div>
            </div>
            <div className="popup-action-panel">
              <div className="section-heading compact-heading">
                <div>
                  <h3>Timer quiz tự luyện</h3>
                  <p className="muted">Thời gian làm bài và chờ làm lại do plugin quản lý.</p>
                </div>
                <label className="toggle-line toggle-strong">
                  <input type="checkbox" checked={customTimerEnabled} onChange={(event) => setCustomTimerEnabled(event.target.checked)} />
                  <span>Bật</span>
                </label>
              </div>
              <div className="quiz-small-grid two-cols">
                <label>Thời gian làm bài/phút<input className="input" type="number" min={1} max={300} disabled={!customTimerEnabled} value={timeLimitMinutes} onChange={(event) => setTimeLimitMinutes(Number(event.target.value || 15))} /></label>
                <label>Chờ làm lại/phút<input className="input" type="number" min={0} max={10080} disabled={!customTimerEnabled} value={retakeCooldownMinutes} onChange={(event) => setRetakeCooldownMinutes(Number(event.target.value || 0))} /></label>
              </div>
              <div className="option-grid compact-options">
                <label className="toggle-line"><input type="checkbox" disabled={!customTimerEnabled} checked={autoSubmitOnTimeout} onChange={(event) => setAutoSubmitOnTimeout(event.target.checked)} /><span>Tự nộp khi hết giờ</span></label>
                <label className="toggle-line"><input type="checkbox" disabled={!customTimerEnabled} checked={lockAfterTimeout} onChange={(event) => setLockAfterTimeout(event.target.checked)} /><span>Khóa sau hết giờ</span></label>
              </div>
            </div>
          </div>
          <div className="quiz-create-preview">
            <b>Quy tắc FPT</b>
            <span>Section Bài 1 → Subsection Quiz 1 → Bài kiểm tra Quiz → Grade as Quiz.</span>
            <small>Khóa học ID: {courseId.trim() || '—'} · {createModal.kind === 'all' ? `${readyRows.length} bài` : createModal.item.chapter_title}</small>
          </div>
          <div className="modal-actions">
            <button className="btn secondary" type="button" disabled={busy || Boolean(creatingKey)} onClick={() => setCreateModal(null)}>Hủy</button>
            <button className="btn" type="button" disabled={busy || Boolean(creatingKey) || difficultyTotal !== 100} onClick={confirmCreateFromModal}>{createModal.kind === 'all' ? `Tạo ${readyRows.length} Quiz` : 'Tạo Quiz'}</button>
          </div>
        </div>
      </section>
    </div> : null}
  </div>
}
