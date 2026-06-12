'use client'

import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { useEffect, useMemo, useRef, useState } from 'react'
import { useAppContext } from '../../../context/AppContext'
import {
  BankRelease,
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
} from '../../../types'
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
  generateFromBankVersion,
  getBankDashboardOverview,
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
  getBankVersionQuestions,
  getBankVersions,
  getCourseQuizInstances,
  getDepartments,
  getMaterialVersions,
  getSubjectChapters,
  getSubjectOfferings,
  getSubjects,
  markBankDiffResolved,
  previewBankVersionDiff,
  previewGenerateFromBankVersion,
  publishBankRelease,
  reviewBankQuestion,
  rollbackCourseQuizInstance,
  uploadBankMaterial,
  updateBankQuestion,
  updateDepartment,
  updateSubject,
  updateSubjectChapter,
  updateSubjectOffering,
} from '../../../lib/api'

const TERMS = [
  ['SP25', 'Spring/Xuân 2025'], ['SU25', 'Summer/Hè 2025'], ['FA25', 'Fall/Đông 2025'],
  ['SP26', 'Spring/Xuân 2026'], ['SU26', 'Summer/Hè 2026'], ['FA26', 'Fall/Đông 2026'],
  ['SP27', 'Spring/Xuân 2027'], ['SU27', 'Summer/Hè 2027'], ['FA27', 'Fall/Đông 2027'],
]


function chapterDisplayName(chapter?: SubjectChapter | null) {
  if (!chapter) return 'Bài'
  const title = (chapter.title || '').trim()
  if (title) return title
  return 'Bài'
}

function normalizeLessonInput(value: string) {
  const raw = value.trim().replace(/^bài\s*/i, '').trim()
  return raw
}

function buildChapterTitle(value: string) {
  const raw = normalizeLessonInput(value)
  return raw ? `Bài ${raw}` : ''
}

function statusLabel(status?: string | null) {
  const value = status || 'draft'
  const labels: Record<string, string> = {
    active: 'Đang dùng', draft: 'Bản nháp', approved: 'Đã duyệt', published: 'Đã publish', ready: 'Sẵn sàng',
    pending_review: 'Chờ duyệt', rejected: 'Đã bỏ', failed: 'Lỗi', created: 'Đã tạo', rolled_back: 'Đã rollback', indexed: 'Đã xử lý', deleted: 'Đã xóa',
  }
  return labels[value] || value
}

function statusClass(status?: string | null) {
  const value = status || ''
  if (['active', 'approved', 'published', 'created', 'ready', 'indexed'].includes(value)) return 'status success'
  if (['failed', 'rejected', 'rolled_back', 'deleted'].includes(value)) return 'status danger'
  if (['draft', 'pending_review'].includes(value)) return 'status warning'
  return 'status'
}

function useBankData() {
  const { authHeaders, can, authReady } = useAppContext()
  const headers = useMemo(() => authHeaders(true), [authHeaders])
  return { headers, can, authReady }
}

function useAsyncMessage() {
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)
  const [busyLabel, setBusyLabel] = useState('Đang xử lý, vui lòng chờ...')
  const run = async (work: () => Promise<unknown>, ok: string, after?: () => Promise<void>, loadingText = 'Đang xử lý, vui lòng chờ...') => {
    setBusy(true)
    setBusyLabel(loadingText)
    setMessage('')
    try {
      await work()
      if (after) await after()
      setMessage(ok)
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Thao tác thất bại')
    } finally {
      setBusy(false)
    }
  }
  return { message, setMessage, busy, busyLabel, run }
}

function Breadcrumb({ items }: { items: Array<{ label: string; href?: string }> }) {
  return <div className="breadcrumb-row">
    {items.map((item, index) => <span key={`${item.label}-${index}`}>
      {item.href ? <Link href={item.href}>{item.label}</Link> : <b>{item.label}</b>}
      {index < items.length - 1 ? <em>›</em> : null}
    </span>)}
  </div>
}

function Toolbar({ title, helper, action }: { title: string; helper?: string; action?: React.ReactNode }) {
  return <div className="page-header compact-page-header">
    <div>
      <div className="eyebrow">Ngân hàng đề</div>
      <h1>{title}</h1>
      {helper ? <p>{helper}</p> : null}
    </div>
    {action ? <div className="button-row no-margin">{action}</div> : null}
  </div>
}

function SearchActionBar({ search, setSearch, placeholder, action }: { search: string; setSearch: (value: string) => void; placeholder: string; action?: React.ReactNode }) {
  return <div className="search-action-bar">
    <input className="input" value={search} onChange={(event) => setSearch(event.target.value)} placeholder={placeholder} />
    {action}
  </div>
}

function Modal({ open, title, children, onClose, wide = false }: { open: boolean; title: string; children: React.ReactNode; onClose: () => void; wide?: boolean }) {
  useEffect(() => {
    if (!open) return undefined
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onKeyDown)
    return () => {
      document.body.style.overflow = previousOverflow
      document.removeEventListener('keydown', onKeyDown)
    }
  }, [open, onClose])

  if (!open) return null
  return <div className="modal-backdrop bank-popup-backdrop" onMouseDown={onClose}>
    <div className={`modal-card bank-modal${wide ? ' bank-modal-wide' : ''}`} role="dialog" aria-modal="true" onMouseDown={(event) => event.stopPropagation()}>
      <div className="section-head bank-modal-head">
        <div><h2>{title}</h2></div>
        <button className="btn small secondary" type="button" onClick={onClose}>Đóng</button>
      </div>
      <div className="bank-modal-body">{children}</div>
    </div>
  </div>
}
function EntityActions({ canManage, onEdit, onDelete }: { canManage: boolean; onEdit: () => void; onDelete: () => void }) {
  const [open, setOpen] = useState(false)
  if (!canManage) return null

  const stop = (event: React.MouseEvent) => {
    event.preventDefault()
    event.stopPropagation()
  }

  const runAction = (event: React.MouseEvent, action: () => void) => {
    stop(event)
    setOpen(false)
    action()
  }

  return <div className={`entity-actions${open ? ' open' : ''}`} onClick={stop} onMouseDown={stop}>
    <button
      type="button"
      className="entity-actions-trigger"
      aria-label="Hành động"
      aria-expanded={open}
      title="Hành động"
      onClick={(event) => { stop(event); setOpen((current) => !current) }}
    >
      ⋮
    </button>
    {open ? <div className="entity-actions-menu" role="menu">
      <button type="button" role="menuitem" onClick={(event) => runAction(event, onEdit)}>Sửa thông tin</button>
      <button type="button" role="menuitem" className="danger" onClick={(event) => runAction(event, onDelete)}>Xóa</button>
    </div> : null}
  </div>
}

function promptText(label: string, current: string) {
  const value = window.prompt(label, current || '')
  return value === null ? null : value.trim()
}


function matchesSearch(text: string, search: string) {
  const s = search.trim().toLowerCase()
  if (!s) return true
  return text.toLowerCase().includes(s)
}


function reviewStatusText(status?: string | null) {
  const labels: Record<string, string> = {
    ready: 'Đã xử lý xong',
    needs_review: 'Còn câu cần duyệt',
    needs_fix: 'Có câu lỗi',
    empty: 'Chưa có dữ liệu',
    not_ready: 'Chưa sẵn sàng',
  }
  return labels[status || ''] || 'Chưa sẵn sàng'
}

function reviewStatusClass(status?: string | null) {
  if (status === 'ready') return 'bank-status-card status-ready'
  if (status === 'needs_fix') return 'bank-status-card status-danger'
  if (status === 'needs_review') return 'bank-status-card status-warning'
  if (status === 'empty') return 'bank-status-card status-empty'
  return 'bank-status-card status-warning'
}

function StatLine({ label, value }: { label: string; value: React.ReactNode }) {
  return <div className="bank-stat-line"><span>{label}</span><b>{value}</b></div>
}

function QuickSearchBox({ compact = false }: { compact?: boolean }) {
  const { headers } = useBankData()
  const [q, setQ] = useState('')
  const [results, setResults] = useState<BankSearchResult[]>([])
  const [loading, setLoading] = useState(false)
  useEffect(() => {
    const text = q.trim()
    if (text.length < 2) { setResults([]); return undefined }
    const timer = window.setTimeout(() => {
      setLoading(true)
      searchBankDashboard(headers, text, 8).then(setResults).catch(() => setResults([])).finally(() => setLoading(false))
    }, 250)
    return () => window.clearTimeout(timer)
  }, [q, headers])
  return <div className={compact ? 'quick-search quick-search-compact' : 'quick-search'}>
    <input className="input" value={q} onChange={(event) => setQ(event.target.value)} placeholder="Tìm nhanh bộ môn / môn / version / bài..." />
    {q.trim().length >= 2 ? <div className="quick-search-results">
      {loading ? <div className="quick-search-row muted">Đang tìm...</div> : null}
      {!loading && results.map((item) => <Link key={`${item.type}-${item.href}`} className="quick-search-row" href={item.href}>
        <b>{item.title}</b>
        <small>{item.subtitle}</small>
      </Link>)}
      {!loading && !results.length ? <div className="quick-search-row muted">Không tìm thấy kết quả phù hợp.</div> : null}
    </div> : null}
  </div>
}

function questionStats(questions: BankVersionQuestion[]) {
  const families = new Set(questions.map((item) => item.question_family_id).filter(Boolean))
  return {
    total: questions.length,
    active: questions.filter((item) => ['pending_review', 'approved', 'published'].includes(item.status)).length,
    approved: questions.filter((item) => item.status === 'approved' || item.status === 'published').length,
    pending: questions.filter((item) => item.status === 'pending_review').length,
    rejected: questions.filter((item) => item.status === 'rejected').length,
    draftError: questions.filter((item) => item.status === 'draft_error').length,
    families: families.size,
  }
}

function nextReleaseText(release?: BankRelease | null) {
  if (!release) return 'Chưa có Release'
  return `${release.release_code} · ${statusLabel(release.status)} · ${release.approved_question_count} câu`
}


const bankAnswerRows = [
  ['A', 'option_a'],
  ['B', 'option_b'],
  ['C', 'option_c'],
  ['D', 'option_d'],
] as const

function bankQuestionErrorMessage(question: BankVersionQuestion) {
  const reason = question.draft_error_reason || (question.quality_flags || [])[0]
  if (!reason) return null
  const detail = question.draft_error_detail || {}
  if (reason === 'duplicate_question') {
    const score = question.duplicate_score || detail.duplicate_score
    return `Trùng/gần trùng${score ? ` (${Math.round(Number(score) * 100)}%)` : ''}${question.duplicate_of_question_id ? ` với ${question.duplicate_of_question_id.slice(0, 8)}` : ''}`
  }
  const labels: Record<string, string> = {
    invalid_answer: 'Đáp án đúng không hợp lệ',
    invalid_source_chunk: 'Source chunk không tồn tại',
    similar_options: 'Các đáp án quá giống nhau',
    duplicate_options: 'Đáp án bị trùng',
    anti_trick: 'Vi phạm anti-trick rule',
    double_negative: 'Câu hỏi có phủ định kép',
    missing_options: 'Thiếu đáp án',
    missing_question: 'Thiếu câu hỏi',
    quality_failed: 'Không đạt kiểm tra chất lượng',
  }
  return labels[reason] || reason
}

function isQuestionWaitingForReview(question: BankVersionQuestion) {
  return question.status === 'pending_review' || question.status === 'needs_review' || question.status === 'draft_error'
}

type BankQuestionEditForm = {
  difficulty: string
  cognitive_level: string
  learning_objective: string
  question_text: string
  option_a: string
  option_b: string
  option_c: string
  option_d: string
  correct_answer: string
  explanation: string
  concept_title: string
  question_family_id: string
  source_ref: string
  source_type: string
  source_excerpt: string
  source_evidence: string
  target_status: string
}

function toBankQuestionEditForm(question: BankVersionQuestion): BankQuestionEditForm {
  return {
    difficulty: question.difficulty || 'easy',
    cognitive_level: question.cognitive_level || 'remember',
    learning_objective: question.learning_objective || '',
    question_text: question.question_text || '',
    option_a: question.option_a || '',
    option_b: question.option_b || '',
    option_c: question.option_c || '',
    option_d: question.option_d || '',
    correct_answer: question.correct_answer || 'A',
    explanation: question.explanation || '',
    concept_title: question.concept_title || '',
    question_family_id: question.question_family_id || '',
    source_ref: question.source_ref || '',
    source_type: question.source_type || 'bank_material',
    source_excerpt: question.source_excerpt || '',
    source_evidence: question.source_evidence || '',
    target_status: ['pending_review', 'approved', 'rejected'].includes(question.status) ? question.status : 'pending_review',
  }
}


type BankChartRow = { label: string; value: number; tone?: 'blue' | 'green' | 'amber' | 'red' | 'slate' }

function BankBarChart({ title, helper, rows, empty }: { title: string; helper?: string; rows: BankChartRow[]; empty?: string }) {
  const max = Math.max(...rows.map((row) => row.value), 0)
  return <div className="card bank-chart-card">
    <div className="section-head compact-section-head"><div><h2>{title}</h2>{helper ? <p className="helper">{helper}</p> : null}</div></div>
    {max <= 0 ? <div className="empty-state small-empty">{empty || 'Chưa có dữ liệu.'}</div> : <div className="bank-bar-chart">
      {rows.map((row) => {
        const width = max > 0 ? Math.max(4, Math.round((row.value / max) * 100)) : 0
        return <div className="bank-bar-row" key={row.label}>
          <div className="bank-bar-label"><span>{row.label}</span><b>{row.value}</b></div>
          <div className="bank-bar-track"><span className={`bank-bar-fill tone-${row.tone || 'blue'}`} style={{ width: `${width}%` }} /></div>
        </div>
      })}
    </div>}
  </div>
}

function BankStackedChart({ title, helper, rows }: { title: string; helper?: string; rows: BankChartRow[] }) {
  const total = rows.reduce((sum, row) => sum + row.value, 0)
  return <div className="card bank-chart-card">
    <div className="section-head compact-section-head"><div><h2>{title}</h2>{helper ? <p className="helper">{helper}</p> : null}</div><b className="chart-total">{total}</b></div>
    {total <= 0 ? <div className="empty-state small-empty">Chưa có dữ liệu.</div> : <>
      <div className="bank-stacked-bar">
        {rows.filter((row) => row.value > 0).map((row) => <span key={row.label} className={`tone-${row.tone || 'blue'}`} style={{ width: `${Math.max(3, (row.value / total) * 100)}%` }} title={`${row.label}: ${row.value}`} />)}
      </div>
      <div className="bank-chart-legend">
        {rows.map((row) => <span key={row.label}><i className={`tone-${row.tone || 'blue'}`} />{row.label}: <b>{row.value}</b></span>)}
      </div>
    </>}
  </div>
}

function countRows<T>(items: T[], getter: (item: T) => string | null | undefined, tones: Record<string, BankChartRow['tone']> = {}) {
  const counts: Record<string, number> = {}
  items.forEach((item) => {
    const key = getter(item) || 'unknown'
    counts[key] = (counts[key] || 0) + 1
  })
  return Object.entries(counts).map(([label, value]) => ({ label: statusLabel(label), value, tone: tones[label] || 'blue' }))
}

function auditActionText(action?: string | null) {
  const map: Record<string, string> = {
    'question_bank.release.quiz.create': 'Tạo Quiz Open edX',
    'question_bank.course_quiz.rollback': 'Rollback Quiz',
    'question_bank.release.publish_openedx': 'Publish Release',
    'question_bank.version.question.review': 'Duyệt câu hỏi',
    'question_bank.version.question.bulk_review': 'Duyệt hàng loạt',
    'question_bank.bank_version.generate': 'Tạo câu hỏi',
    'question_bank.material.upload': 'Upload tài liệu',
    'question_bank.quiz.auto_map.apply': 'Lưu cấu hình map Quiz',
  }
  return map[action || ''] || action || '—'
}

export function BankDashboardPage() {
  const { headers, authReady } = useBankData()
  const [overview, setOverview] = useState<BankDashboardOverview | null>(null)
  const [quizInstances, setQuizInstances] = useState<CourseQuizInstance[]>([])
  const [auditRows, setAuditRows] = useState<AuditLogRow[]>([])
  const [jobs, setJobs] = useState<Job[]>([])
  const overviewLoadKey = useRef('')

  const load = async () => {
    const [nextOverview, nextQuizInstances, nextAudit, nextJobs] = await Promise.all([
      getBankDashboardOverview(headers),
      getCourseQuizInstances(headers, { limit: 50 }),
      getAuditLogs('', { page: 1, pageSize: 8 }, headers),
      getJobs('', headers),
    ])
    setOverview(nextOverview)
    setQuizInstances(nextQuizInstances)
    setAuditRows(nextAudit.items || [])
    setJobs(nextJobs)
  }

  useEffect(() => {
    if (!authReady) return
    const key = JSON.stringify(headers)
    if (overviewLoadKey.current === key) return
    overviewLoadKey.current = key
    let cancelled = false
    load().catch(() => { if (!cancelled) overviewLoadKey.current = '' })
    return () => { cancelled = true }
  }, [authReady, headers]) // eslint-disable-line react-hooks/exhaustive-deps

  const questionRows: BankChartRow[] = [
    { label: 'Đã duyệt', value: overview?.approved_count || 0, tone: 'green' },
    { label: 'Chờ duyệt', value: overview?.pending_review_count || 0, tone: 'amber' },
    { label: 'Câu lỗi', value: overview?.draft_error_count || 0, tone: 'red' },
  ]
  const hierarchyRows: BankChartRow[] = [
    { label: 'Bộ môn', value: overview?.departments_total || 0, tone: 'blue' },
    { label: 'Môn', value: overview?.subjects_total || 0, tone: 'green' },
    { label: 'Version', value: overview?.subject_versions_total || 0, tone: 'amber' },
    { label: 'Bài', value: overview?.chapters_total || 0, tone: 'slate' },
  ]
  const quizRows = countRows(quizInstances, (row) => row.status, { created: 'green', failed: 'red', rolled_back: 'amber' })
  const jobRows = countRows(jobs, (row) => row.status, { completed: 'green', failed: 'red', running: 'blue', queued: 'amber' })

  return <div className="page-stack bank-multipage">
    <Breadcrumb items={[{ label: 'Ngân hàng đề' }]} />
    <Toolbar title="Tổng quan ngân hàng đề" helper="Gộp Dashboard Bank và vận hành vào một màn hình: việc cần làm, biểu đồ thống kê, Quiz Open edX, job và nhật ký gần đây." action={<div className="button-row no-margin"><button className="btn secondary" type="button" onClick={load}>Tải lại</button><Link className="btn secondary" href="/bank/departments">Quản lý bộ môn</Link><Link className="btn" href="/bank/quiz">Tạo Quiz Open edX</Link></div>} />
    <section className="card bank-guide-card">
      <div className="section-head"><div><h2>Tìm nhanh</h2><p className="helper">Gõ WEB107, WEB107_SU25, Bài 1, HTML/CSS, Database hoặc tên bộ môn để đi thẳng tới nơi cần xử lý.</p></div></div>
      <QuickSearchBox />
    </section>
    <section className="summary-grid compact-summary dashboard-summary">
      <div><span>Bộ môn</span><b>{overview?.departments_total ?? '—'}</b><small>{overview?.departments_done ?? 0} đã xong · {overview?.departments_not_done ?? 0} còn việc</small></div>
      <div><span>Môn</span><b>{overview?.subjects_total ?? '—'}</b><small>{overview?.subjects_done ?? 0} đã xong · {overview?.subjects_not_done ?? 0} còn việc</small></div>
      <div><span>Version môn</span><b>{overview?.subject_versions_total ?? '—'}</b><small>{overview?.subject_versions_done ?? 0} đã xong · {overview?.subject_versions_not_done ?? 0} còn việc</small></div>
      <div><span>Bài cần xử lý</span><b>{overview?.chapters_needing_review ?? '—'}</b><small>{overview?.chapters_ready_to_release ?? 0} bài sẵn sàng chốt</small></div>
      <div><span>Tổng câu hỏi</span><b>{overview?.total_questions ?? '—'}</b><small>{overview?.approved_count ?? 0} đã duyệt</small></div>
      <div><span>Quiz Open edX</span><b>{quizInstances.length}</b><small>{quizInstances.filter((item) => item.status === 'created').length} đã tạo · {quizInstances.filter((item) => item.status === 'failed').length} lỗi</small></div>
    </section>
    <section className="bank-chart-grid">
      <BankStackedChart title="Tình trạng câu hỏi" helper="Tỷ lệ câu đã duyệt, chờ duyệt và lỗi trong toàn ngân hàng." rows={questionRows} />
      <BankBarChart title="Quy mô ngân hàng" helper="Số lượng entity chính theo luồng Bank-first." rows={hierarchyRows} />
      <BankBarChart title="Quiz Open edX" helper="Trạng thái các Quiz đã tạo từ Bank Release." rows={quizRows} empty="Chưa có Quiz Open edX." />
      <BankBarChart title="Job generate" helper="Theo dõi job tạo câu hỏi/publish/quiz gần đây." rows={jobRows} empty="Chưa có job." />
    </section>
    <section className="card">
      <div className="section-head"><div><h2>Việc cần làm</h2><p className="helper">Hệ thống tự gom những nơi còn câu chưa duyệt, câu lỗi hoặc bài đã sẵn sàng chốt bộ đề.</p></div></div>
      <div className="entity-list dashboard-task-list">
        {(overview?.next_actions || []).map((item) => <Link href={item.href} className={`entity-card link-card ${item.type === 'fix_errors' ? 'danger-card' : item.type === 'review_questions' ? 'warning-card' : 'success-card'}`} key={`${item.type}-${item.href}`}>
          <b>{item.title}</b>
          <small>{item.message}</small>
          <span className={item.type === 'create_release' ? 'status success' : item.type === 'fix_errors' ? 'status danger' : 'status warning'}>{item.type === 'create_release' ? 'Sẵn sàng chốt' : item.type === 'fix_errors' ? 'Cần sửa lỗi' : 'Cần duyệt'}</span>
        </Link>)}
      </div>
      {overview && !overview.next_actions.length ? <div className="empty-state">Chưa có việc cần xử lý. Có thể bắt đầu từ Quản lý bộ môn hoặc Tạo Quiz Open edX.</div> : null}
      {!overview ? <div className="empty-state">Đang tải tổng quan...</div> : null}
    </section>
    <section className="card">
      <div className="section-head"><div><h2>Hoạt động gần đây</h2><p className="helper">Nhật ký toàn hệ thống theo luồng Bank/Quiz-first.</p></div><Link className="btn secondary" href="/audit">Xem nhật ký</Link></div>
      <div className="table-wrap"><table className="table"><thead><tr><th>Thời điểm</th><th>Người</th><th>Hành động</th><th>Kết quả</th><th>Nội dung</th></tr></thead><tbody>{auditRows.length ? auditRows.map((row) => <tr key={row.id}><td>{row.created_at ? new Date(row.created_at).toLocaleString('vi-VN') : '—'}</td><td><b>{row.actor_id}</b><br /><span className="helper">{row.actor_role || '—'}</span></td><td>{auditActionText(row.action)}</td><td><span className={row.status === 'failed' ? 'status danger' : 'status success'}>{row.status}</span></td><td>{row.message || '—'}</td></tr>) : <tr><td colSpan={5}><div className="empty-state">Chưa có hoạt động.</div></td></tr>}</tbody></table></div>
    </section>
  </div>
}

export function DepartmentsPage() {
  const { headers, can } = useBankData()
  const { message, busy, busyLabel, run } = useAsyncMessage()
  const [summaries, setSummaries] = useState<DepartmentSummary[]>([])
  const [search, setSearch] = useState('')
  const [createOpen, setCreateOpen] = useState(false)
  const [code, setCode] = useState('')
  const [name, setName] = useState('')

  const load = async () => { setSummaries(await getDepartmentSummaries(headers)) }
  useEffect(() => { load().catch(() => null) }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const visible = summaries.filter(({ department }) => matchesSearch(`${department.code} ${department.name}`, search))

  const editDepartment = (department: Department) => {
    const nextCode = promptText('Sửa mã bộ môn', department.code)
    if (nextCode === null) return
    const nextName = promptText('Sửa tên bộ môn', department.name)
    if (nextName === null) return
    run(async () => { await updateDepartment(headers, department.id, { code: nextCode, name: nextName }) }, 'Đã sửa bộ môn', load)
  }
  const removeDepartment = (department: Department) => {
    if (!window.confirm(`Chỉ xóa được khi bộ môn chưa có môn bên trong. Xóa ${department.name}?`)) return
    run(async () => { await deleteDepartment(headers, department.id) }, 'Đã xóa bộ môn', load)
  }

  return <div className="page-stack bank-multipage">
    {busy ? <div className="bank-loading-overlay"><div className="bank-loading-card"><div className="spinner" /><b>{busyLabel}</b><small>Không tắt trang trong lúc hệ thống đang xử lý.</small></div></div> : null}
    <Breadcrumb items={[{ label: 'Ngân hàng đề', href: '/bank' }, { label: 'Bộ môn' }]} />
    <Toolbar title="Bộ môn" helper="Nhìn card là biết bộ môn nào đã xử lý xong, bộ môn nào còn câu cần duyệt." action={<Link className="btn secondary" href="/bank/quiz">Tạo Quiz Open edX</Link>} />
    <QuickSearchBox compact />
    {message ? <div className="alert info">{message}</div> : null}
    <section className="card">
      <div className="section-head"><div><h2>Danh sách bộ môn</h2><p className="helper">Click vào bộ môn để xem các môn bên trong.</p></div></div>
      <SearchActionBar search={search} setSearch={setSearch} placeholder="Tìm bộ môn" action={<button className="btn" disabled={!can('manage_settings')} onClick={() => setCreateOpen(true)}>+ Thêm bộ môn</button>} />
      <div className="entity-list horizontal multipage-list">
        {visible.map(({ department, stats }) => <Link key={department.id} href={`/bank/departments/${department.id}/subjects`} className={`entity-card link-card ${reviewStatusClass(stats.status)}`}>
          <EntityActions canManage={can('manage_settings')} onEdit={() => editDepartment(department)} onDelete={() => removeDepartment(department)} />
          <div className="entity-card-head"><b>{department.name}</b><span className="status-pill">{reviewStatusText(stats.status)}</span></div>
          <small>{department.code}</small>
          <StatLine label="Môn" value={stats.subject_count || 0} />
          <StatLine label="Đã duyệt xong" value={`${stats.review_done_subject_count || 0} môn`} />
          <StatLine label="Chưa duyệt xong" value={`${stats.review_not_done_subject_count || 0} môn`} />
          <StatLine label="Câu chờ xử lý" value={stats.unresolved_count || 0} />
          <StatLine label="Bài sẵn sàng chốt" value={stats.ready_to_release_chapter_count || 0} />
        </Link>)}
      </div>
      {!visible.length ? <div className="empty-state">Chưa có bộ môn phù hợp.</div> : null}
    </section>
    <Modal open={createOpen} title="Thêm bộ môn" onClose={() => setCreateOpen(false)}>
      <div className="mini-form">
        <input className="input" value={code} onChange={(event) => setCode(event.target.value)} placeholder="Mã bộ môn, ví dụ CNTT" />
        <input className="input" value={name} onChange={(event) => setName(event.target.value)} placeholder="Tên bộ môn, ví dụ Công nghệ thông tin" />
        <button className="btn" type="button" disabled={busy || !code.trim() || !name.trim()} onClick={() => run(async () => {
          await createDepartment(headers, { code, name })
          setCode(''); setName(''); setCreateOpen(false)
        }, 'Đã thêm bộ môn', load)}>Lưu bộ môn</button>
      </div>
    </Modal>
  </div>
}

export function DepartmentSubjectsPage({ departmentId }: { departmentId: string }) {
  const { headers, can } = useBankData()
  const { message, busy, run } = useAsyncMessage()
  const [departments, setDepartments] = useState<Department[]>([])
  const [summaries, setSummaries] = useState<SubjectSummary[]>([])
  const [search, setSearch] = useState('')
  const [createOpen, setCreateOpen] = useState(false)
  const [code, setCode] = useState('')
  const [name, setName] = useState('')

  const load = async () => {
    const [nextDepartments, nextSummaries] = await Promise.all([getDepartments(headers), getSubjectSummaries(headers, departmentId)])
    setDepartments(nextDepartments); setSummaries(nextSummaries)
  }
  useEffect(() => { load().catch(() => null) }, [departmentId]) // eslint-disable-line react-hooks/exhaustive-deps

  const department = departments.find((item) => item.id === departmentId)
  const visible = summaries.filter(({ subject }) => matchesSearch(`${subject.code} ${subject.name}`, search))

  const editSubject = (subject: Subject) => {
    const nextCode = promptText('Sửa mã môn', subject.code)
    if (nextCode === null) return
    const nextName = promptText('Sửa tên môn', subject.name)
    if (nextName === null) return
    run(async () => { await updateSubject(headers, subject.id, { code: nextCode, name: nextName }) }, 'Đã sửa môn', load)
  }
  const removeSubject = (subject: Subject) => {
    if (!window.confirm(`Chỉ xóa được khi môn chưa có version/bài/câu hỏi bên trong. Xóa ${subject.code}?`)) return
    run(async () => { await deleteSubject(headers, subject.id) }, 'Đã xóa môn', load)
  }

  return <div className="page-stack bank-multipage">
    <Breadcrumb items={[{ label: 'Ngân hàng đề', href: '/bank' }, { label: 'Bộ môn', href: '/bank/departments' }, { label: department?.name || 'Bộ môn' }, { label: 'Môn' }]} />
    <Toolbar title={department ? `Môn trong ${department.name}` : 'Môn trong bộ môn'} helper="Mỗi môn hiển thị version đã duyệt xong, version còn việc và số câu chờ xử lý." />
    <QuickSearchBox compact />
    {message ? <div className="alert info">{message}</div> : null}
    <section className="card">
      <div className="section-head"><div><h2>Danh sách môn</h2><p className="helper">Click vào môn để quản lý các phiên bản theo kỳ.</p></div></div>
      <SearchActionBar search={search} setSearch={setSearch} placeholder="Tìm môn" action={<button className="btn" disabled={!can('manage_settings')} onClick={() => setCreateOpen(true)}>+ Thêm môn</button>} />
      <div className="entity-list horizontal multipage-list">
        {visible.map(({ subject, stats }) => <Link key={subject.id} href={`/bank/subjects/${subject.id}/versions`} className={`entity-card link-card ${reviewStatusClass(stats.status)}`}>
          <EntityActions canManage={can('manage_settings')} onEdit={() => editSubject(subject)} onDelete={() => removeSubject(subject)} />
          <div className="entity-card-head"><b>{subject.code} - {subject.name}</b><span className="status-pill">{reviewStatusText(stats.status)}</span></div>
          <StatLine label="Phiên bản môn" value={stats.subject_version_count || 0} />
          <StatLine label="Đã duyệt xong" value={`${stats.review_done_version_count || 0} version`} />
          <StatLine label="Chưa duyệt xong" value={`${stats.review_not_done_version_count || 0} version`} />
          <StatLine label="Tổng câu" value={stats.total_questions || 0} />
          <StatLine label="Câu chờ xử lý" value={stats.unresolved_count || 0} />
          <StatLine label="Bài sẵn sàng chốt" value={stats.ready_to_release_chapter_count || 0} />
        </Link>)}
      </div>
      {!visible.length ? <div className="empty-state">Chưa có môn phù hợp.</div> : null}
    </section>
    <Modal open={createOpen} title="Thêm môn" onClose={() => setCreateOpen(false)}>
      <div className="mini-form">
        <input className="input" value={code} onChange={(event) => setCode(event.target.value)} placeholder="Mã môn, ví dụ WEB107" />
        <input className="input" value={name} onChange={(event) => setName(event.target.value)} placeholder="Tên môn, ví dụ Thiết kế trang web" />
        <button className="btn" type="button" disabled={busy || !code.trim() || !name.trim()} onClick={() => run(async () => {
          await createSubject(headers, { department_id: departmentId, code, name })
          setCode(''); setName(''); setCreateOpen(false)
        }, 'Đã thêm môn', load)}>Lưu môn</button>
      </div>
    </Modal>
  </div>
}

export function SubjectVersionsPage({ subjectId }: { subjectId: string }) {
  const { headers, can } = useBankData()
  const { message, busy, run } = useAsyncMessage()
  const router = useRouter()
  const [departments, setDepartments] = useState<Department[]>([])
  const [subjects, setSubjects] = useState<Subject[]>([])
  const [summaries, setSummaries] = useState<SubjectVersionSummary[]>([])
  const [search, setSearch] = useState('')
  const [createOpen, setCreateOpen] = useState(false)
  const [term, setTerm] = useState('SU25')
  const [mode, setMode] = useState<'blank' | 'clone'>('clone')
  const [cloneFromId, setCloneFromId] = useState('')

  const load = async () => {
    const [nextDepartments, nextSubjects, nextSummaries] = await Promise.all([
      getDepartments(headers), getSubjects(headers), getSubjectVersionSummaries(headers, subjectId),
    ])
    setDepartments(nextDepartments); setSubjects(nextSubjects); setSummaries(nextSummaries)
    if (!cloneFromId && nextSummaries.length) setCloneFromId(nextSummaries[0].subject_version.id)
  }
  useEffect(() => { load().catch(() => null) }, [subjectId]) // eslint-disable-line react-hooks/exhaustive-deps

  const subject = subjects.find((item) => item.id === subjectId)
  const department = departments.find((item) => item.id === subject?.department_id)
  const visible = summaries.filter(({ subject_version }) => matchesSearch(`${subject_version.code} ${subject_version.name} ${subject_version.term || ''}`, search))

  const editSubjectVersion = (subjectVersion: SubjectOffering) => {
    const nextCode = promptText('Sửa mã version môn', subjectVersion.code)
    if (nextCode === null) return
    const nextName = promptText('Sửa tên version môn', subjectVersion.name || '')
    if (nextName === null) return
    run(async () => { await updateSubjectOffering(headers, subjectVersion.id, { code: nextCode, name: nextName }) }, 'Đã sửa version môn', load)
  }
  const removeSubjectVersion = (subjectVersion: SubjectOffering) => {
    if (!window.confirm(`Chỉ xóa được khi version môn chưa có bài/tài liệu/câu hỏi/release. Xóa ${subjectVersion.code}?`)) return
    run(async () => { await deleteSubjectOffering(headers, subjectVersion.id) }, 'Đã xóa version môn', load)
  }

  return <div className="page-stack bank-multipage">
    <Breadcrumb items={[{ label: 'Ngân hàng đề', href: '/bank' }, { label: 'Bộ môn', href: '/bank/departments' }, { label: department?.name || 'Bộ môn', href: department ? `/bank/departments/${department.id}/subjects` : undefined }, { label: subject?.code || 'Môn' }, { label: 'Phiên bản môn' }]} />
    <Toolbar title={subject ? `Phiên bản môn ${subject.code}` : 'Phiên bản môn'} helper="Mỗi version hiển thị tổng số bài, số câu đã duyệt/chưa duyệt và release đã publish." />
    <QuickSearchBox compact />
    {message ? <div className="alert info">{message}</div> : null}
    <section className="card">
      <div className="section-head"><div><h2>Danh sách phiên bản theo kỳ</h2><p className="helper">Tạo version mới trống hoặc clone 100% bản làm việc từ kỳ cũ.</p></div></div>
      <SearchActionBar search={search} setSearch={setSearch} placeholder="Tìm version môn" action={<button className="btn" disabled={!can('manage_settings')} onClick={() => setCreateOpen(true)}>+ Tạo version môn</button>} />
      <div className="entity-list horizontal multipage-list">
        {visible.map(({ subject_version, stats }) => <Link key={subject_version.id} href={`/bank/subject-versions/${subject_version.id}/chapters`} className={`entity-card link-card ${reviewStatusClass(stats.status)}`}>
          <EntityActions canManage={can('manage_settings')} onEdit={() => editSubjectVersion(subject_version)} onDelete={() => removeSubjectVersion(subject_version)} />
          <div className="entity-card-head"><b>{subject_version.code}</b><span className="status-pill">{reviewStatusText(stats.status)}</span></div>
          <small>{subject_version.name || subject_version.term || 'Version môn'}</small>
          <StatLine label="Bài" value={stats.chapter_count || 0} />
          <StatLine label="Tổng câu" value={`${stats.total_questions || 0}/100`} />
          <StatLine label="Đã duyệt" value={stats.approved_count || 0} />
          <StatLine label="Chưa duyệt/lỗi" value={stats.unresolved_count || 0} />
          <StatLine label="Release đã publish" value={`${stats.published_release_count || 0}/${stats.chapter_count || 0} bài`} />
        </Link>)}
      </div>
      {!visible.length ? <div className="empty-state">Chưa có version phù hợp.</div> : null}
    </section>
    <Modal open={createOpen} title="Tạo version môn" onClose={() => setCreateOpen(false)}>
      <div className="mini-form">
        <div className="button-row"><button className={mode === 'clone' ? 'btn' : 'btn secondary'} onClick={() => setMode('clone')}>Clone từ version khác</button><button className={mode === 'blank' ? 'btn' : 'btn secondary'} onClick={() => setMode('blank')}>Tạo mới trống</button></div>
        <select className="input" value={term} onChange={(event) => setTerm(event.target.value)}>{TERMS.map(([value, label]) => <option value={value} key={value}>{value} - {label}</option>)}</select>
        {mode === 'clone' ? <select className="input" value={cloneFromId} onChange={(event) => setCloneFromId(event.target.value)}>{summaries.map(({ subject_version }) => <option value={subject_version.id} key={subject_version.id}>Clone từ {subject_version.code}</option>)}</select> : null}
        <p className="helper">Clone 100% bản làm việc: bài, tài liệu, bank version, câu hỏi approved. Không clone Release/Open edX Library và không chạy diff khi clone.</p>
        <div className="modal-actions"><button className="btn secondary" onClick={() => setCreateOpen(false)}>Hủy</button><button className="btn" disabled={busy || !term || (mode === 'clone' && !cloneFromId)} onClick={() => run(async () => {
          const created = await createSubjectOffering(headers, { subject_id: subjectId, term, clone_from_offering_id: mode === 'clone' ? cloneFromId : null, version_code: term, clone_chapters: true, clone_materials: true, clone_questions: true })
          setCreateOpen(false)
          router.push(`/bank/subject-versions/${created.id}/chapters`)
        }, 'Đã tạo version môn', load)}>Tạo version</button></div>
      </div>
    </Modal>
  </div>
}

export function SubjectVersionChaptersPage({ versionId }: { versionId: string }) {
  const { headers, can } = useBankData()
  const { message, busy, run } = useAsyncMessage()
  const [departments, setDepartments] = useState<Department[]>([])
  const [subjects, setSubjects] = useState<Subject[]>([])
  const [offerings, setOfferings] = useState<SubjectOffering[]>([])
  const [summaries, setSummaries] = useState<ChapterSummary[]>([])
  const [search, setSearch] = useState('')
  const [createOpen, setCreateOpen] = useState(false)
  const [chapterInput, setChapterInput] = useState('')

  const load = async () => {
    const [nextDepartments, nextSubjects, nextOfferings, nextSummaries] = await Promise.all([
      getDepartments(headers), getSubjects(headers), getSubjectOfferings(headers), getChapterSummaries(headers, versionId),
    ])
    setDepartments(nextDepartments); setSubjects(nextSubjects); setOfferings(nextOfferings); setSummaries(nextSummaries)
  }
  useEffect(() => { load().catch(() => null) }, [versionId]) // eslint-disable-line react-hooks/exhaustive-deps

  const offering = offerings.find((item) => item.id === versionId)
  const subject = subjects.find((item) => item.id === offering?.subject_id)
  const department = departments.find((item) => item.id === subject?.department_id)
  const visible = summaries.filter(({ chapter }) => matchesSearch(chapterDisplayName(chapter), search))

  const editChapter = (chapter: SubjectChapter) => {
    const current = normalizeLessonInput(chapterDisplayName(chapter))
    const nextLesson = promptText('Sửa bài, ví dụ 1, 2, 1.1, 1.2', current)
    if (nextLesson === null) return
    const nextTitle = buildChapterTitle(nextLesson) || nextLesson
    run(async () => { await updateSubjectChapter(headers, chapter.id, { title: nextTitle }) }, 'Đã sửa bài', load)
  }
  const removeChapter = (chapter: SubjectChapter) => {
    if (!window.confirm(`Chỉ xóa được khi bài chưa có tài liệu/câu hỏi/release/mapping. Xóa ${chapterDisplayName(chapter)}?`)) return
    run(async () => { await deleteSubjectChapter(headers, chapter.id) }, 'Đã xóa bài', load)
  }

  return <div className="page-stack bank-multipage">
    <Breadcrumb items={[{ label: 'Ngân hàng đề', href: '/bank' }, { label: 'Bộ môn', href: '/bank/departments' }, { label: department?.name || 'Bộ môn', href: department ? `/bank/departments/${department.id}/subjects` : undefined }, { label: subject?.code || 'Môn', href: subject ? `/bank/subjects/${subject.id}/versions` : undefined }, { label: offering?.code || 'Version môn' }, { label: 'Bài' }]} />
    <Toolbar title={offering ? `Bài trong ${offering.code}` : 'Bài trong version môn'} helper="Mỗi bài hiển thị tài liệu, tổng câu, câu đã duyệt, câu chưa duyệt/lỗi và trạng thái Release." />
    <QuickSearchBox compact />
    {message ? <div className="alert info">{message}</div> : null}
    <section className="card">
      <div className="section-head"><div><h2>Danh sách bài</h2><p className="helper">Click vào bài là vào ngay workspace, không cần bấm bắt đầu.</p></div></div>
      <SearchActionBar search={search} setSearch={setSearch} placeholder="Tìm bài" action={<button className="btn" disabled={!can('manage_settings')} onClick={() => setCreateOpen(true)}>+ Thêm bài</button>} />
      <div className="entity-list horizontal multipage-list">
        {visible.map(({ chapter, stats }) => <Link key={chapter.id} href={`/bank/chapters/${chapter.id}`} className={`entity-card link-card ${reviewStatusClass(stats.status)}`}>
          <EntityActions canManage={can('manage_settings')} onEdit={() => editChapter(chapter)} onDelete={() => removeChapter(chapter)} />
          <div className="entity-card-head"><b>{chapterDisplayName(chapter)}</b><span className="status-pill">{reviewStatusText(stats.status)}</span></div>
          <StatLine label="Tài liệu" value={stats.material_count || 0} />
          <StatLine label="Tổng câu" value={`${stats.total_questions || 0}/${stats.question_limit || 100}`} />
          <StatLine label="Đã duyệt" value={stats.approved_count || 0} />
          <StatLine label="Chưa duyệt/lỗi" value={stats.unresolved_count || 0} />
          <StatLine label="Release" value={stats.release_status === 'published' ? 'Đã publish' : stats.ready_to_release ? 'Sẵn sàng chốt' : stats.release_count ? 'Đã chốt' : 'Chưa chốt'} />
          {stats.ready_to_release ? <span className="status success">Sẵn sàng chốt bộ đề</span> : null}
        </Link>)}
      </div>
      {!visible.length ? <div className="empty-state">Chưa có bài phù hợp.</div> : null}
    </section>
    <Modal open={createOpen} title="Thêm bài" onClose={() => setCreateOpen(false)}>
      <div className="mini-form">
        <label className="field-label" htmlFor="chapter-lesson-input">Bài:</label>
        <div className="chapter-input-row">
          <span className="input-prefix">Bài</span>
          <input id="chapter-lesson-input" className="input" value={chapterInput} onChange={(event) => setChapterInput(event.target.value)} placeholder="1, 2, 1.1, 1.2..." />
        </div>
        <p className="helper">Ví dụ nhập 1.2, hệ thống tự tạo tên “Bài 1.2”. ID do hệ thống tự sinh.</p>
        <div className="modal-actions">
          <button className="btn secondary" type="button" onClick={() => { setChapterInput(''); setCreateOpen(false) }}>Hủy</button>
          <button className="btn" type="button" disabled={busy || !offering || !normalizeLessonInput(chapterInput)} onClick={() => run(async () => {
            if (!offering) return
            const nextNo = (summaries.reduce((max, item) => Math.max(max, Number(item.chapter.sort_order || item.chapter.chapter_no || 0)), 0) || 0) + 1
            const title = buildChapterTitle(chapterInput)
            await createSubjectChapter(headers, { subject_id: offering.subject_id, subject_offering_id: offering.id, title, sort_order: nextNo })
            setChapterInput(''); setCreateOpen(false)
          }, 'Đã thêm bài', load)}>Tạo bài</button>
        </div>
      </div>
    </Modal>
  </div>
}

export function ChapterWorkspacePage({ chapterId }: { chapterId: string }) {
  const { headers, can } = useBankData()
  const { message, busy, busyLabel, run } = useAsyncMessage()
  const [departments, setDepartments] = useState<Department[]>([])
  const [subjects, setSubjects] = useState<Subject[]>([])
  const [offerings, setOfferings] = useState<SubjectOffering[]>([])
  const [chapters, setChapters] = useState<SubjectChapter[]>([])
  const [bankVersions, setBankVersions] = useState<BankVersion[]>([])
  const [releases, setReleases] = useState<BankRelease[]>([])
  const [materials, setMaterials] = useState<MaterialVersion[]>([])
  const [questions, setQuestions] = useState<BankVersionQuestion[]>([])
  const [readiness, setReadiness] = useState<BankReleaseReadiness | null>(null)
  const [file, setFile] = useState<File | null>(null)
  const [generateCount, setGenerateCount] = useState('10')
  const [difficultyEasy, setDifficultyEasy] = useState('50')
  const [difficultyMedium, setDifficultyMedium] = useState('30')
  const [difficultyHard, setDifficultyHard] = useState('20')
  const [autoCreateTried, setAutoCreateTried] = useState(false)
  const [materialView, setMaterialView] = useState<{ material: MaterialVersion; chunks: MaterialChunk[] } | null>(null)
  const [diffPreview, setDiffPreview] = useState<BankVersionDiffPreview | null>(null)
  const [generatePreview, setGeneratePreview] = useState<BankGeneratePreview | null>(null)
  const [editingQuestion, setEditingQuestion] = useState<BankVersionQuestion | null>(null)
  const [editForm, setEditForm] = useState<BankQuestionEditForm | null>(null)
  const [rejectingQuestion, setRejectingQuestion] = useState<BankVersionQuestion | null>(null)
  const [rejectReason, setRejectReason] = useState('')
  const [materialManagerOpen, setMaterialManagerOpen] = useState(false)
  const [generateManagerOpen, setGenerateManagerOpen] = useState(false)
  const [questionStatusFilter, setQuestionStatusFilter] = useState('all')
  const [questionDifficultyFilter, setQuestionDifficultyFilter] = useState('all')
  const [questionSort, setQuestionSort] = useState('needs_review')

  const load = async () => {
    const [nextDepartments, nextSubjects, nextOfferings, nextChapters, nextBankVersions, nextReleases] = await Promise.all([
      getDepartments(headers), getSubjects(headers), getSubjectOfferings(headers), getSubjectChapters(headers), getBankVersions(headers, chapterId), getBankReleases(headers, undefined, chapterId),
    ])
    setDepartments(nextDepartments); setSubjects(nextSubjects); setOfferings(nextOfferings); setChapters(nextChapters); setBankVersions(nextBankVersions); setReleases(nextReleases)
  }

  const selectedBankVersion = bankVersions[0] || null
  const loadDetail = async (bankVersionId?: string | null) => {
    if (!bankVersionId) { setMaterials([]); setQuestions([]); setReadiness(null); return }
    const [nextMaterials, nextQuestions, nextReadiness] = await Promise.all([
      getMaterialVersions(headers, bankVersionId).catch(() => []),
      getBankVersionQuestions(headers, bankVersionId, undefined, 300).catch(() => []),
      getBankReleaseReadiness(headers, bankVersionId).catch(() => null),
    ])
    setMaterials(nextMaterials.filter((item) => item.status !== 'deleted'))
    setQuestions(nextQuestions)
    setReadiness(nextReadiness)
  }

  useEffect(() => { load().catch(() => null) }, [chapterId]) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { loadDetail(selectedBankVersion?.id).catch(() => null) }, [selectedBankVersion?.id]) // eslint-disable-line react-hooks/exhaustive-deps

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
  const numericGenerateCount = Number(generateCount || 0)
  const chapterQuestionLimit = Number((readiness?.stats as any)?.chapter_question_limit || 100)
  const usedQuestionCount = Number((readiness?.stats as any)?.chapter_total_count ?? stats.total)
  const unresolvedQuestionCount = Number((readiness?.stats as any)?.unresolved_count ?? (stats.pending + stats.draftError))
  const releaseReviewBlocked = unresolvedQuestionCount > 0
  const remainingQuota = Math.max(0, chapterQuestionLimit - usedQuestionCount)
  const difficultyTotal = Number(difficultyEasy || 0) + Number(difficultyMedium || 0) + Number(difficultyHard || 0)
  const overQuota = numericGenerateCount > remainingQuota
  const invalidDifficulty = difficultyTotal !== 100
  const canGenerateNow = Boolean(selectedBankVersion && materials.length && can('generate_questions') && !overQuota && !invalidDifficulty && numericGenerateCount >= 1 && remainingQuota > 0)
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
    if (chapter && !selectedBankVersion && !autoCreateTried && can('edit_questions')) {
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
    setDiffPreview(diff)
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

  const startEditQuestion = (question: BankVersionQuestion) => {
    setEditingQuestion(question)
    setEditForm(toBankQuestionEditForm(question))
  }

  const updateEditForm = <K extends keyof BankQuestionEditForm>(key: K, value: BankQuestionEditForm[K]) => {
    setEditForm((current) => current ? { ...current, [key]: value } : current)
  }

  const saveEditedQuestion = async () => {
    if (!selectedBankVersion || !editingQuestion || !editForm) return
    await run(async () => {
      await updateBankQuestion(headers, selectedBankVersion.id, editingQuestion.id, { ...editForm, note: 'Giáo viên sửa câu hỏi trong workspace bài' })
      setEditingQuestion(null)
      setEditForm(null)
    }, 'Đã lưu câu hỏi', refreshCurrent)
  }



  const openRejectQuestion = (question: BankVersionQuestion) => {
    setRejectingQuestion(question)
    setRejectReason(question.status === 'draft_error' ? 'Bỏ câu lỗi: ' : '')
  }

  const confirmRejectQuestion = async () => {
    if (!selectedBankVersion || !rejectingQuestion || !rejectReason.trim()) return
    await run(async () => {
      await reviewBankQuestion(headers, selectedBankVersion.id, rejectingQuestion.id, { action: 'reject', note: rejectReason.trim() })
      setRejectingQuestion(null)
      setRejectReason('')
    }, 'Đã bỏ câu hỏi', refreshCurrent)
  }
  const generationPayload = { question_count: numericGenerateCount, target_question_count: 100, difficulty_easy: Number(difficultyEasy || 50), difficulty_medium: Number(difficultyMedium || 30), difficulty_hard: Number(difficultyHard || 20) }

  const openGenerateConfirm = async () => {
    if (!selectedBankVersion) return
    await run(async () => {
      const preview = await previewGenerateFromBankVersion(headers, selectedBankVersion.id, generationPayload)
      setGeneratePreview(preview)
    }, 'Đã tính chi phí dự kiến', undefined, 'Đang tính chi phí dự kiến...')
  }

  const confirmGenerateQuestions = async () => {
    if (!selectedBankVersion || !generatePreview) return
    await run(async () => {
      await generateFromBankVersion(headers, selectedBankVersion.id, generationPayload)
      setGeneratePreview(null)
    }, 'Đã tạo câu hỏi', refreshCurrent, 'Đang tạo câu hỏi bằng GPT, vui lòng chờ...')
  }

  const materialPreviewChunks = (materialView?.chunks || []).slice(0, 80)
  const materialPreviewText = materialPreviewChunks.map((chunk, index) => `Đoạn ${index + 1}
${chunk.content}`).join('\n\n')

  return <div className="page-stack bank-multipage">
    {busy ? <div className="bank-loading-overlay"><div className="bank-loading-card"><div className="spinner" /><b>{busyLabel}</b><small>Không tắt trang trong lúc hệ thống đang xử lý.</small></div></div> : null}
    <Breadcrumb items={[{ label: 'Bộ môn', href: '/bank/departments' }, { label: department?.name || 'Bộ môn', href: department ? `/bank/departments/${department.id}/subjects` : undefined }, { label: subject?.code || 'Môn', href: subject ? `/bank/subjects/${subject.id}/versions` : undefined }, { label: offering?.code || 'Version môn', href: offering ? `/bank/subject-versions/${offering.id}/chapters` : undefined }, { label: chapterDisplayName(chapter) }]} />
    <Toolbar title={chapter ? `${offering?.code || ''} / ${chapterDisplayName(chapter)}` : 'Workspace của bài'} helper={'Một màn hình để quản lý tài liệu, tạo câu hỏi, duyệt câu và chốt release cho bài.'} />
    {message ? <div className="alert info">{message}</div> : null}
    {diffRequired ? <div className="alert warning"><b>Tài liệu đã thay đổi.</b> Hệ thống sẽ kiểm tra khác biệt và hiển thị kết quả để giáo viên xác nhận.</div> : null}
    {unresolvedQuestionCount > 0 ? <div className="alert warning"><b>Còn câu chưa xử lý.</b> Hiện có {stats.pending} câu chờ duyệt và {stats.draftError} câu lỗi. Phải duyệt, sửa hoặc bỏ hết thì mới chốt bộ đề được.</div> : null}

    <section className={`card teacher-next-step ${unresolvedQuestionCount > 0 ? 'warning-card' : readiness?.can_create_release ? 'success-card' : ''}`}>
      <div className="section-head"><div><h2>Bạn cần làm gì tiếp?</h2><p className="helper">Hệ thống tự đọc trạng thái bài và chỉ ra bước tiếp theo, không cần giáo viên tự đoán.</p></div></div>
      {stats.draftError > 0 ? <div className="next-step-message"><b>Còn {stats.draftError} câu lỗi.</b><span>Hãy bấm Sửa hoặc Bỏ câu lỗi. Khi bấm Bỏ, hệ thống yêu cầu nhập lý do để sau này fine-tune AI.</span></div> : stats.pending > 0 ? <div className="next-step-message"><b>Còn {stats.pending} câu chưa duyệt.</b><span>Hãy duyệt hoặc bỏ hết các câu này. Sau đó mới chốt bộ đề.</span></div> : readiness?.can_create_release ? <div className="next-step-message"><b>Sẵn sàng chốt bộ đề.</b><span>Tất cả câu đã được xử lý. Có thể bấm Chốt bộ đề.</span></div> : <div className="next-step-message"><b>Chưa có việc cần duyệt.</b><span>Hãy gắn tài liệu và tạo câu hỏi nếu bài này chưa đủ câu.</span></div>}
      <div className="button-row no-margin chapter-primary-actions"><button className="btn secondary chapter-action-button review" onClick={() => document.getElementById('bank-question-list')?.scrollIntoView({ behavior: 'smooth' })}>Duyệt câu hỏi</button>{!latestRelease ? <button className="btn chapter-action-button release" disabled={busy || !selectedBankVersion || !can('publish_questions') || !readiness?.can_create_release || releaseReviewBlocked} onClick={() => run(async () => { if (!selectedBankVersion) return; await createBankRelease(headers, { bank_version_id: selectedBankVersion.id, include_approved_questions: true }) }, 'Đã chốt Release', refreshCurrent)}>Chốt bộ đề</button> : null}</div>
    </section>

    <section className="summary-grid compact-summary">
      <div><span>Tài liệu</span><b>{materials.length}</b></div>
      <div><span>Tổng câu hiện có</span><b>{usedQuestionCount}/{chapterQuestionLimit}</b><small>Còn {remainingQuota} câu</small></div>
      <div><span>Câu đã duyệt</span><b>{stats.approved}</b></div>
      <div><span>Câu chờ duyệt</span><b>{stats.pending}</b></div>
      <div><span>Câu bị loại</span><b>{stats.rejected}</b></div>
      <div><span>Nhóm kiến thức</span><b>{stats.families}</b></div>
      <div><span>Release</span><b>{publishedRelease ? 'Đã publish' : latestRelease ? 'Đã chốt' : 'Chưa chốt'}</b><small>{nextReleaseText(publishedRelease || latestRelease)}</small></div>
    </section>

    <section className="card chapter-command-bar">
      <div>
        <div className="eyebrow">Workspace bài</div>
        <h2>{chapterDisplayName(chapter)}</h2>
        <p className="helper">Các thao tác chính nằm trong popup để màn hình duyệt câu hỏi không bị rời rạc.</p>
      </div>
      <div className="button-row no-margin">
        <button className="btn secondary chapter-action-button material" disabled={!selectedBankVersion} onClick={() => setMaterialManagerOpen(true)}>Tài liệu ({materials.length})</button>
        <button className="btn chapter-action-button generate" disabled={!selectedBankVersion} onClick={() => setGenerateManagerOpen(true)}>Tạo câu hỏi</button>
        <button className="btn secondary chapter-action-button review" onClick={() => document.getElementById('bank-question-list')?.scrollIntoView({ behavior: 'smooth' })}>Duyệt câu hỏi</button>
        <button className="btn secondary chapter-action-button diff" disabled={busy || !selectedBankVersion || !diffBaseBankVersionId} onClick={() => run(async () => {
          if (!selectedBankVersion) return
          await runDiffNow(selectedBankVersion.id, diffBaseBankVersionId)
        }, 'Đã kiểm tra khác biệt', refreshCurrent)}>Kiểm tra thay đổi</button>
        {!latestRelease ? <button className="btn" disabled={busy || !selectedBankVersion || !can('publish_questions') || !readiness?.can_create_release || releaseReviewBlocked} title={releaseReviewBlocked ? 'Phải duyệt hoặc bỏ hết tất cả câu hỏi trước khi chốt bộ đề.' : undefined} onClick={() => run(async () => {
          if (!selectedBankVersion) return
          await createBankRelease(headers, { bank_version_id: selectedBankVersion.id, include_approved_questions: true })
        }, 'Đã chốt Release', refreshCurrent)}>Chốt bộ đề</button> : latestRelease.status !== 'published' ? <button className="btn" disabled={busy || !can('publish_questions')} onClick={() => run(async () => { await publishBankRelease(headers, latestRelease.id, {}) }, 'Đã publish Library sang Open edX', refreshCurrent)}>Publish Library</button> : <button className="btn secondary chapter-action-button published" disabled>Đã publish</button>}
      </div>
      {releaseReviewBlocked ? <div className="alert warning full-row"><b>Chưa thể chốt bộ đề.</b> Còn {stats.pending} câu chờ duyệt và {stats.draftError} câu lỗi. Hãy duyệt hoặc bỏ hết tất cả câu hỏi trước.</div> : null}
    </section>

    {!selectedBankVersion ? <section className="card"><div className="empty-state">Đang chuẩn bị workspace cho bài này...</div></section> : <section className="workspace-grid multipage-workspace chapter-question-workspace">
      <div className="workspace-panel full" id="bank-question-list">
        <div className="section-head question-list-head"><div><h3>Danh sách câu hỏi</h3><p className="helper">Lọc nhanh theo trạng thái, độ khó và sắp xếp để giáo viên xử lý hết câu trước khi chốt bộ đề.</p></div><button className="btn secondary chapter-action-button review" disabled={busy || !can('review_questions') || stats.pending === 0} onClick={() => run(async () => {
          if (!selectedBankVersion) return
          await bulkReviewBankQuestions(headers, selectedBankVersion.id, { action: 'approve', approve_all_pending: true, note: 'Duyệt hết câu chờ' })
        }, 'Đã duyệt hết câu chờ', refreshCurrent)}>Duyệt hết câu chờ</button></div>
        <div className="question-filter-bar">
          <label>Trạng thái<select className="input" value={questionStatusFilter} onChange={(event) => setQuestionStatusFilter(event.target.value)}><option value="all">Tất cả</option><option value="needs_action">Cần xử lý</option><option value="pending_review">Chờ duyệt</option><option value="draft_error">Câu lỗi</option><option value="approved">Đã duyệt</option><option value="rejected">Đã bỏ</option><option value="published">Đã publish</option></select></label>
          <label>Độ khó<select className="input" value={questionDifficultyFilter} onChange={(event) => setQuestionDifficultyFilter(event.target.value)}><option value="all">Tất cả</option><option value="easy">Dễ</option><option value="medium">Trung bình</option><option value="hard">Khó</option></select></label>
          <label>Sắp xếp<select className="input" value={questionSort} onChange={(event) => setQuestionSort(event.target.value)}><option value="needs_review">Cần xử lý trước</option><option value="difficulty">Theo độ khó</option><option value="quality_low">Điểm chất lượng thấp trước</option><option value="quality_high">Điểm chất lượng cao trước</option></select></label>
          <button className="btn secondary" type="button" onClick={() => { setQuestionStatusFilter('all'); setQuestionDifficultyFilter('all'); setQuestionSort('needs_review') }}>Xóa lọc</button>
          <span className="filter-result-count">Hiện {filteredQuestions.length}/{questions.length} câu</span>
        </div>
        <div className="question-card-list bank-review-list">
          {filteredQuestions.slice(0, 160).map((item, index) => {
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
                    {item.status !== 'published' ? <button className="btn small secondary" disabled={busy || !can('review_questions')} onClick={() => startEditQuestion(item)}>Sửa</button> : null}
                    {(item.status === 'pending_review' || item.status === 'needs_review' || item.status === 'rejected') ? <button className="btn small success" disabled={busy || !can('review_questions')} onClick={() => run(async () => {
                      if (!selectedBankVersion) return
                      await reviewBankQuestion(headers, selectedBankVersion.id, item.id, { action: 'approve', note: 'Giữ câu hỏi này' })
                    }, 'Đã duyệt câu hỏi', refreshCurrent)}>{item.status === 'rejected' ? 'Duyệt lại' : 'Duyệt'}</button> : null}
                    {item.status !== 'rejected' && item.status !== 'published' ? <button className="btn small danger" disabled={busy || !can('review_questions')} onClick={() => openRejectQuestion(item)}>{item.status === 'draft_error' ? 'Bỏ câu lỗi' : 'Bỏ'}</button> : null}
                    {item.status === 'approved' ? <button className="btn small secondary" disabled={busy || !can('review_questions')} onClick={() => run(async () => {
                      if (!selectedBankVersion) return
                      await reviewBankQuestion(headers, selectedBankVersion.id, item.id, { action: 'back_to_review', note: 'Đưa về chờ duyệt' })
                    }, 'Đã đưa câu hỏi về chờ duyệt', refreshCurrent)}>Hoàn tác</button> : null}
                  </div>
                </div>
              </div>
            </article>
          })}
        </div>
        {!filteredQuestions.length ? <div className="empty-state">Không có câu hỏi phù hợp bộ lọc.</div> : null}
      </div>
    </section>}

    <Modal open={materialManagerOpen} title="Tài liệu của bài" onClose={() => setMaterialManagerOpen(false)} wide>
      <div className="chapter-popup-grid">
        <div className="popup-action-panel">
          <h3>Gắn tài liệu</h3>
          <p className="helper">Tài liệu là nguồn để AI tạo câu hỏi cho đúng bài này. Nếu version clone bị đổi tài liệu, hệ thống sẽ kiểm tra khác biệt.</p>
          <div className="mini-form">
            <input className="input" type="file" onChange={(event) => setFile(event.target.files?.[0] || null)} />
            <button className="btn" disabled={busy || !file || !can('edit_questions')} onClick={() => run(async () => {
              if (!file || !selectedBankVersion) return
              const result = await uploadBankMaterial(headers, selectedBankVersion.id, file, { title: file.name, change_type: diffBaseBankVersionId ? 'updated_after_clone' : 'initial', replace_existing: false })
              setFile(null)
              if (result.diff_required && result.diff_base_bank_version_id) {
                await runDiffNow(selectedBankVersion.id, result.diff_base_bank_version_id)
              }
            }, 'Đã gắn tài liệu', refreshCurrent)}>+ Gắn tài liệu</button>
          </div>
        </div>
        <div className="popup-list-panel">
          <h3>Tài liệu đã gắn</h3>
          <div className="entity-list compact-list small-chunk-list popup-scroll-list">
            {materials.map((item) => <div className="entity-card" key={item.id}>
              <b>{item.title || item.file_name}</b>
              <small>{item.file_type} · {new Date(item.created_at).toLocaleString('vi-VN')}</small>
              <div className="button-row no-margin">
                <button className="btn small secondary" onClick={() => openMaterial(item)}>Xem</button>
                <button className="btn small danger" disabled={busy || !can('edit_questions')} onClick={() => run(async () => { await deleteMaterialVersion(headers, item.id) }, 'Đã xóa tài liệu', refreshCurrent)}>Xóa</button>
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
            <div className="modal-actions"><button className="btn secondary" onClick={() => setGenerateManagerOpen(false)}>Đóng</button><button className="btn" disabled={busy || !canGenerateNow} onClick={openGenerateConfirm}>Tính chi phí & tạo</button></div>
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
        <div className="button-row"><button className="btn secondary" disabled={busy} onClick={() => setGeneratePreview(null)}>Hủy</button><button className="btn" disabled={busy} onClick={confirmGenerateQuestions}>Xác nhận tạo câu hỏi</button></div>
      </div> : null}
    </Modal>


    <Modal open={Boolean(rejectingQuestion)} title={rejectingQuestion?.status === 'draft_error' ? 'Bỏ câu lỗi' : 'Bỏ câu hỏi'} onClose={() => { setRejectingQuestion(null); setRejectReason('') }}>
      <div className="mini-form">
        <p className="helper">Nhập lý do hủy/bỏ câu. Lý do này được lưu lại để biết ai làm gì và dùng làm dữ liệu fine-tune AI sau này.</p>
        {rejectingQuestion ? <div className="reject-question-preview"><b>{rejectingQuestion.question_text || 'Câu lỗi chưa có nội dung'}</b>{rejectingQuestion.status === 'draft_error' ? <small>Lý do lỗi: {bankQuestionErrorMessage(rejectingQuestion) || 'Không rõ'}</small> : null}</div> : null}
        <textarea className="input" rows={4} value={rejectReason} onChange={(event) => setRejectReason(event.target.value)} placeholder="Ví dụ: Câu hỏi không đúng tài liệu, đáp án sai, câu lỗi không sửa được..." />
        <div className="modal-actions"><button className="btn secondary" disabled={busy} onClick={() => { setRejectingQuestion(null); setRejectReason('') }}>Hủy</button><button className="btn danger" disabled={busy || !rejectReason.trim()} onClick={confirmRejectQuestion}>Xác nhận bỏ câu</button></div>
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
        <div className="button-row"><button className="btn" disabled={busy || !editForm.question_text.trim() || !editForm.option_a.trim() || !editForm.option_b.trim() || !editForm.option_c.trim() || !editForm.option_d.trim()} onClick={saveEditedQuestion}>Lưu chỉnh sửa</button><button className="btn secondary" onClick={() => { setEditingQuestion(null); setEditForm(null) }}>Hủy</button></div>
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

    <Modal open={Boolean(diffPreview)} title="Kết quả kiểm tra thay đổi tài liệu" onClose={() => setDiffPreview(null)}>
      {diffPreview ? <div className="diff-result-box">
        <div className="summary-grid compact-summary">
          <div><span>Tài liệu giống nhau</span><b>{Math.round(Number(diffPreview.summary.material_similarity ?? diffPreview.material_similarity ?? 0) * 100)}%</b></div>
          <div><span>Câu có thể giữ</span><b>{diffPreview.summary.carry_over_candidate_count}</b></div>
          <div><span>Câu nên bỏ</span><b>{diffPreview.summary.retire_candidate_count}</b></div>
          <div><span>Câu cần xem lại</span><b>{diffPreview.summary.review_candidate_count}</b></div>
        </div>
        <p className="helper">Giáo viên chỉ cần chọn cách xử lý. Hệ thống sẽ tự cập nhật danh sách câu hỏi.</p>
        <div className="button-row">
          <button className="btn" disabled={busy} onClick={() => run(keepReusableOnly, 'Đã giữ câu phù hợp và bỏ câu không còn chắc phù hợp')}>Giữ câu còn phù hợp</button>
          <button className="btn secondary" disabled={busy} onClick={() => run(rejectAllCarryOver, 'Đã bỏ các câu clone từ tài liệu cũ')}>Không giữ câu cũ</button>
        </div>
      </div> : null}
    </Modal>
  </div>
}

export function BankHistoryPage() {
  const { headers, can } = useBankData()
  const { message, busy, run } = useAsyncMessage()
  const [history, setHistory] = useState<CourseQuizInstance[]>([])
  const load = async () => { setHistory(await getCourseQuizInstances(headers, { limit: 100 })) }
  useEffect(() => { load().catch(() => null) }, []) // eslint-disable-line react-hooks/exhaustive-deps
  return <div className="page-stack bank-multipage">
    <Breadcrumb items={[{ label: 'Bộ môn', href: '/bank/departments' }, { label: 'Lịch sử publish / quiz' }]} />
    <Toolbar title="Lịch sử Quiz" helper="Xem Quiz đã tạo trên Open edX và rollback nếu tạo nhầm." action={<Link className="btn secondary" href="/bank/quiz">Tạo Quiz Open edX</Link>} />
    {message ? <div className="alert info">{message}</div> : null}
    <section className="card">
      <div className="table-wrap"><table className="data-table compact-table"><thead><tr><th>Course</th><th>Trạng thái</th><th>Unit Open edX</th><th>Thời gian</th><th></th></tr></thead><tbody>{history.map((item) => <tr key={item.id}><td><b>{item.openedx_course_id}</b><small>{item.metadata_json?.quiz_title || item.bank_release_id}</small></td><td><span className={statusClass(item.status)}>{statusLabel(item.status)}</span></td><td><code>{item.openedx_unit_node_id || '—'}</code></td><td>{new Date(item.created_at).toLocaleString('vi-VN')}</td><td><button className="btn small secondary" disabled={busy || !can('publish_questions') || item.status === 'rolled_back'} onClick={() => run(async () => { await rollbackCourseQuizInstance(headers, item.id, { mode: 'safe', note: 'Rollback từ trang lịch sử Quiz' }) }, 'Đã gửi yêu cầu rollback Quiz', load)}>Rollback</button></td></tr>)}</tbody></table></div>
      {!history.length ? <div className="empty-state">Chưa có Quiz nào được tạo.</div> : null}
    </section>
  </div>
}
