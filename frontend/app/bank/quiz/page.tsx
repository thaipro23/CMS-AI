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
  const [autoSubmitOnTimeout, setAutoSubmitOnTimeout] = useState(true)
  const [lockAfterTimeout, setLockAfterTimeout] = useState(true)

  const loadHistory = async (targetCourseId = courseId) => {
    setHistoryBusy(true)
    try {
      const data = await getCourseQuizInstances(headers, { openedx_course_id: targetCourseId || undefined, limit: 100 }).catch(() => [])
      setHistory(data)
    } finally {
      setHistoryBusy(false)
    }
  }

  useEffect(() => {
    loadHistory('').catch(() => undefined)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  if (!can('publish_questions')) return <div className="card empty-state">Bạn không có quyền map khóa học hoặc tạo quiz.</div>

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
      setMessage(result.message)
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
      setMessage(result.message)
      await loadHistory(courseId.trim())
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Lưu mapping tự động thất bại')
    } finally {
      setBusy(false)
    }
  }

  const createOneQuiz = async (item: QuizAutoMapResult['mappings'][number]) => {
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
      await loadHistory(courseId.trim())
    } catch (error) {
      setMessage(error instanceof Error ? error.message : `Tạo Quiz cho ${item.chapter_title} thất bại`)
    } finally {
      setCreatingKey('')
    }
  }

  const createAllQuiz = async () => {
    if (!autoMap?.mappings?.length) return
    const ready = autoMap.mappings.filter((item) => item.ready && item.release_id && item.course_chapter_mapping_id)
    setBusy(true)
    setMessage(`Đang tạo ${ready.length} Quiz. Vui lòng chờ...`)
    try {
      for (const item of ready) {
        // eslint-disable-next-line no-await-in-loop
        await createOneQuiz(item)
      }
      setMessage(`Đã gửi tạo Quiz cho ${ready.length} bài.`)
      await loadHistory(courseId.trim())
    } finally {
      setBusy(false)
      setCreatingKey('')
    }
  }

  const applied = autoMap?.mode === 'applied'
  const readyRows = autoMap?.mappings?.filter((item) => item.ready) || []
  const candidates = autoMap?.summary?.candidates || []
  const canCreateQuiz = applied && readyRows.length > 0

  return <div className="page-stack bank-quiz-page">
    <section className="card page-intro">
      <div>
        <div className="eyebrow">Open edX Quiz</div>
        <h1>Map khóa học và tạo Quiz</h1>
        <p>Dán Course ID. Hệ thống tự tìm version môn có Release đã publish đủ tất cả bài, rồi tự map Section Open edX vào đúng bài cùng tên.</p>
      </div>
      <div className="button-row">
        <Link className="btn secondary" href="/bank">Dashboard</Link>
        <Link className="btn secondary" href="/bank/departments">Quản lý bộ môn</Link>
      </div>
    </section>

    {message ? <div className={classNames('alert', message.toLowerCase().includes('lỗi') || message.toLowerCase().includes('thất bại') || message.toLowerCase().includes('không') ? 'danger' : 'success')}>{message}</div> : null}

    <section className="card">
      <h2>1. Dán Course ID</h2>
      <p className="muted">Ví dụ: <code>course-v1:FPT+WEB107+SU25</code>. Hệ thống sẽ tự tìm môn WEB107, version WEB107_SU25 và các Section trùng tên với Bài.</p>
      <div className="inline-form compact-form">
        <label className="wide-field">Course ID<input className="input" value={courseId} onChange={(event) => { setCourseId(event.target.value); setSelectedOfferingId(''); setAutoMap(null); }} placeholder="course-v1:FPT+WEB107+SU25" /></label>
        <label>Số câu/Quiz<input className="input" type="number" min={1} max={200} value={totalQuestions} onChange={(event) => setTotalQuestions(Number(event.target.value || 15))} /></label>
      </div>
      <div className="inline-form compact-form">
        <label>Easy %<input className="input" type="number" value={difficultyEasy} onChange={(event) => setDifficultyEasy(Number(event.target.value || 0))} /></label>
        <label>Medium %<input className="input" type="number" value={difficultyMedium} onChange={(event) => setDifficultyMedium(Number(event.target.value || 0))} /></label>
        <label>Hard %<input className="input" type="number" value={difficultyHard} onChange={(event) => setDifficultyHard(Number(event.target.value || 0))} /></label>
      </div>

      <div className="card-soft timer-config-panel">
        <div className="section-heading">
          <div>
            <h3>Timer quiz tự luyện</h3>
            <p className="muted">Không dùng Timed Exam native. Hệ thống dùng đồng hồ riêng để tự nộp, khóa submit và cho làm lại theo cooldown.</p>
          </div>
          <label className="toggle-line">
            <input type="checkbox" checked={customTimerEnabled} onChange={(event) => setCustomTimerEnabled(event.target.checked)} />
            <span>Bật timer</span>
          </label>
        </div>
        <div className="inline-form compact-form">
          <label>Thời gian làm bài/phút<input className="input" type="number" min={1} max={300} disabled={!customTimerEnabled} value={timeLimitMinutes} onChange={(event) => setTimeLimitMinutes(Number(event.target.value || 15))} /></label>
          <label>Thời gian chờ làm lại/phút<input className="input" type="number" min={0} max={10080} disabled={!customTimerEnabled} value={retakeCooldownMinutes} onChange={(event) => setRetakeCooldownMinutes(Number(event.target.value || 0))} /></label>
        </div>
        <div className="option-grid">
          <label className="toggle-line"><input type="checkbox" disabled={!customTimerEnabled} checked={autoSubmitOnTimeout} onChange={(event) => setAutoSubmitOnTimeout(event.target.checked)} /><span>Tự nộp các câu đã chọn khi hết giờ</span></label>
          <label className="toggle-line"><input type="checkbox" disabled={!customTimerEnabled} checked={lockAfterTimeout} onChange={(event) => setLockAfterTimeout(event.target.checked)} /><span>Khóa submit sau khi hết giờ</span></label>
        </div>
        <div className="alert info">Quy định FPT: Section có tên <b>Bài 1</b> thì Subsection quiz tự tạo là <b>Quiz 1</b>, Unit luôn tên <b>Quiz</b>, Grade as luôn là <b>Quiz</b>.</div>
      </div>

      <div className="button-row">
        <button className="btn" disabled={busy || !courseId.trim()} onClick={() => runPreview()}>{busy ? 'Đang kiểm tra...' : 'Tự tìm version và Section'}</button>
        <button className="btn secondary" disabled={busy || !autoMap?.can_apply} onClick={runApply}>{busy ? 'Đang lưu...' : 'Lưu mapping tự động'}</button>
      </div>
    </section>

    {autoMap ? <section className="card">
      <h2>2. Kết quả tự map</h2>
      <div className={classNames('alert', autoMap.can_apply ? 'success' : 'warning')}>
        <b>{autoMap.message}</b>
        {autoMap.subject ? <div>Môn: <b>{autoMap.subject.code}</b> · {autoMap.subject.name}</div> : null}
        {autoMap.offering ? <div>Version môn: <b>{autoMap.offering.code}</b> · Release đã publish: {autoMap.summary?.published_release_count || 0}/{autoMap.summary?.chapter_count || 0} bài</div> : null}
        <div>Section Open edX: {autoMap.summary?.matched_count || 0}/{autoMap.summary?.chapter_count || 0} bài đã khớp</div>
      </div>

      {candidates.length ? <div className="card-soft version-picker-panel">
        <label className="wide-field">Version môn dùng để tạo Quiz
          <select className="input" value={selectedOfferingId || autoMap?.offering?.id || ''} disabled={busy} onChange={async (event) => {
            const next = event.target.value
            setSelectedOfferingId(next)
            if (next) await runPreview(next)
          }}>
            <option value="">Chọn version môn...</option>
            {candidates.map((item) => <option key={item.offering_id} value={item.offering_id} disabled={!item.all_ready}>
              {item.offering_code}{item.course_run_match ? ' · khớp Course ID' : ''} · {item.ready_chapter_count}/{item.chapter_count} bài đã publish{item.all_ready ? '' : ` · ${item.disabled_reason || 'chưa đủ điều kiện'}`}
            </option>)}
          </select>
        </label>
        <p className="muted">Hệ thống đã chọn sẵn version khớp Course ID. Bạn có thể đổi sang version khác của cùng môn nếu version đó đã publish Release đủ tất cả bài.</p>
      </div> : null}
      {autoMap.blocking_errors?.length ? <div className="alert danger"><b>Chưa thể tạo Quiz</b><ul>{autoMap.blocking_errors.map((item, index) => <li key={index}>{item}</li>)}</ul></div> : null}
      {autoMap.warnings?.length ? <div className="alert warning"><b>Cảnh báo</b><ul>{autoMap.warnings.map((item, index) => <li key={index}>{item}</li>)}</ul></div> : null}
      <div className="table-wrap">
        <table className="data-table compact-table">
          <thead><tr><th>Bài trong ngân hàng</th><th>Section Open edX</th><th>Release</th><th>Khớp</th><th>Trạng thái</th><th></th></tr></thead>
          <tbody>{autoMap.mappings.map((item) => <tr key={item.chapter_id}>
            <td><b>{item.chapter_title}</b></td>
            <td>{item.openedx_section_title ? <><b>{item.openedx_section_title}</b><small><code>{item.openedx_section_id}</code></small></> : <span className="status danger">Chưa tìm thấy</span>}</td>
            <td>{item.release_code ? <><b>{item.release_code}</b><small>{item.openedx_library_key}</small></> : <span className="status danger">Chưa publish</span>}</td>
            <td>{percent(item.match_score)}<small>{item.match_reason}</small></td>
            <td><span className={classNames('status', item.ready ? 'success' : 'danger')}>{item.ready ? 'Sẵn sàng' : 'Chưa sẵn sàng'}</span>{item.course_chapter_mapping_id ? <small>Đã lưu mapping</small> : null}</td>
            <td><button className="btn small" disabled={!item.ready || !item.course_chapter_mapping_id || creatingKey === item.chapter_id || busy} onClick={() => createOneQuiz(item)}>{creatingKey === item.chapter_id ? 'Đang tạo...' : 'Tạo Quiz'}</button></td>
          </tr>)}</tbody>
        </table>
      </div>
      <div className="button-row">
        <button className="btn" disabled={!canCreateQuiz || busy || Boolean(creatingKey)} onClick={createAllQuiz}>Tạo Quiz cho tất cả bài đã map</button>
      </div>
    </section> : null}

    <section className="card">
      <h2>3. Lịch sử Quiz</h2>
      <p className="muted">Dùng để biết Quiz nào đã tạo trên Open edX. Nếu tạo nhầm, bấm rollback.</p>
      {historyBusy ? <div className="empty-state">Đang tải lịch sử Quiz...</div> : null}
      <div className="table-wrap"><table className="data-table compact-table"><thead><tr><th>Course</th><th>Trạng thái</th><th>Unit Open edX</th><th>Timer</th><th>Thời gian</th><th></th></tr></thead><tbody>{history.map((item) => <tr key={item.id}><td><b>{item.openedx_course_id}</b><small>{item.metadata_json?.quiz_title || item.bank_release_id}</small></td><td><span className={classNames('status', item.status === 'created' ? 'success' : item.status?.includes('rollback') || item.status === 'failed' ? 'danger' : 'pending')}>{item.status}</span></td><td><code>{item.openedx_unit_node_id || '—'}</code></td><td>{item.metadata_json?.timer_config?.custom_timer_enabled ? <span className="status pending">{item.metadata_json.timer_config.time_limit_minutes || Math.round((item.metadata_json.timer_config.duration_seconds || 0) / 60)} phút</span> : <span className="muted">Không bật</span>}</td><td>{new Date(item.created_at).toLocaleString()}</td><td><button className="btn small secondary" disabled={busy || item.status === 'rolled_back'} onClick={async () => {
        setBusy(true)
        try {
          const result = await rollbackCourseQuizInstance(headers, item.id, { mode: 'safe', note: 'Rollback từ giao diện lịch sử Quiz' })
          setMessage(result.message)
          await loadHistory(courseId.trim())
        } catch (error) {
          setMessage(error instanceof Error ? error.message : 'Rollback thất bại')
        } finally {
          setBusy(false)
        }
      }}>Rollback</button></td></tr>)}</tbody></table></div>
      {!history.length && !historyBusy ? <div className="empty-state">Chưa có Quiz nào được tạo từ ngân hàng đề.</div> : null}
    </section>
  </div>
}
