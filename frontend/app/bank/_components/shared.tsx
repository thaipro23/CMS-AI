'use client'

import Link from 'next/link'
import { Breadcrumbs } from '../../../components/navigation/Breadcrumbs'
import type { MouseEvent, ReactNode } from 'react'
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
  getBankVersionQuestion,
  getBankVersionQuestionPage,
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

export const TERMS = [
  ['SP25', 'Spring/Xuân 2025'], ['SU25', 'Summer/Hè 2025'], ['FA25', 'Fall/Đông 2025'],
  ['SP26', 'Spring/Xuân 2026'], ['SU26', 'Summer/Hè 2026'], ['FA26', 'Fall/Đông 2026'],
  ['SP27', 'Spring/Xuân 2027'], ['SU27', 'Summer/Hè 2027'], ['FA27', 'Fall/Đông 2027'],
]


export function chapterDisplayName(chapter?: SubjectChapter | null) {
  if (!chapter) return 'Bài'
  const title = (chapter.title || '').trim()
  if (title) return title
  return 'Bài'
}

export function normalizeLessonInput(value: string) {
  const raw = value.trim()
  if (!raw) return ''
  const withoutBai = raw.replace(/^bài\s*/i, '').trim()
  if (/^final\s*test$/i.test(withoutBai)) return 'Final test'
  if (/^assignment$/i.test(withoutBai)) return 'Assignment'
  return withoutBai
}

export function buildChapterTitle(value: string) {
  const raw = normalizeLessonInput(value)
  if (!raw) return ''
  if (/^final\s*test$/i.test(raw)) return 'Final test'
  if (/^assignment$/i.test(raw)) return 'Assignment'
  if (/^[0-9]+(?:\.[0-9]+)*$/.test(raw)) return `Bài ${raw}`
  if (/^bài\s+/i.test(raw)) return raw
  return raw
}

export function statusLabel(status?: string | null) {
  const value = status || 'draft'
  const labels: Record<string, string> = {
    active: 'Đang dùng', draft: 'Bản nháp', approved: 'Đã duyệt', published: 'Đã đưa lên CMS', ready: 'Sẵn sàng',
    pending_review: 'Chờ duyệt', rejected: 'Đã bỏ', failed: 'Lỗi', created: 'Đã tạo', rolled_back: 'Đã khôi phục', indexed: 'Đã xử lý', deleted: 'Đã xóa',
  }
  return labels[value] || value
}

export function statusClass(status?: string | null) {
  const value = status || ''
  if (['active', 'approved', 'published', 'created', 'ready', 'indexed'].includes(value)) return 'status success'
  if (['failed', 'rejected', 'rolled_back', 'deleted'].includes(value)) return 'status danger'
  if (['draft', 'pending_review'].includes(value)) return 'status warning'
  return 'status'
}

export function useBankData() {
  const { authHeaders, can, authReady } = useAppContext()
  const headers = useMemo(() => authHeaders(true), [authHeaders])
  return { headers, can, authReady }
}

export function useAsyncMessage() {
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)
  const [busyLabel, setBusyLabel] = useState('Đang xử lý, vui lòng chờ...')
  const run = async (work: () => Promise<unknown>, ok: string, after?: () => Promise<void>, loadingText = 'Đang xử lý, vui lòng chờ...') => {
    setBusy(true)
    setBusyLabel(loadingText)
    setMessage('')
    try {
      const result = await work()
      if (after) await after()
      const record = result && typeof result === 'object' ? result as Record<string, unknown> : null
      const userMessage = typeof record?.user_message === 'string' ? record.user_message : typeof record?.message === 'string' ? record.message : ''
      setMessage(userMessage || ok)
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Thao tác thất bại')
    } finally {
      setBusy(false)
    }
  }
  return { message, setMessage, busy, busyLabel, run }
}

export function Breadcrumb({ items }: { items: Array<{ label: string; href?: string }> }) {
  return <Breadcrumbs items={items} ariaLabel="Điều hướng Ngân hàng câu hỏi" />
}

export function Toolbar({ title, helper, action }: { title: string; helper?: string; action?: React.ReactNode }) {
  return <div className="page-header compact-page-header">
    <div>
      <div className="eyebrow">Ngân hàng câu hỏi</div>
      <h1>{title}</h1>
      {helper ? <p>{helper}</p> : null}
    </div>
    {action ? <div className="button-row no-margin">{action}</div> : null}
  </div>
}

export function SearchActionBar({ search, setSearch, placeholder, action }: { search: string; setSearch: (value: string) => void; placeholder: string; action?: React.ReactNode }) {
  return <div className="search-action-bar">
    <input className="input" aria-label={placeholder} value={search} onChange={(event) => setSearch(event.target.value)} placeholder={placeholder} />
    {action}
  </div>
}

export type BankTableStatusFilter = 'all' | 'published' | 'ready' | 'needs_work' | 'empty'

export function bankStatusBucket(stats?: Record<string, any> | null): BankTableStatusFilter | 'done' {
  const s = stats || {}
  const status = String(s.status || '')
  const isPublished = Boolean(s.is_published || s.release_status === 'published' || Number(s.published_release_count || 0) > 0 || status === 'published')
  if (isPublished) return 'published'
  if (Boolean(s.ready_to_release) || Number(s.ready_to_release_chapter_count || 0) > 0 || status === 'ready') return 'ready'
  const hasAnyData = Boolean(
    Number(s.total_questions || 0) ||
    Number(s.approved_count || 0) ||
    Number(s.pending_review_count || 0) ||
    Number(s.draft_error_count || 0) ||
    Number(s.unresolved_count || 0) ||
    Number(s.material_count || 0) ||
    Number(s.subject_count || 0) ||
    Number(s.subject_version_count || 0) ||
    Number(s.chapter_count || 0) ||
    Number(s.release_count || 0) ||
    status && status !== 'empty'
  )
  if (!hasAnyData || status === 'empty') return 'empty'
  if (
    status === 'needs_review' ||
    status === 'needs_fix' ||
    status === 'not_ready' ||
    Number(s.pending_review_count || 0) > 0 ||
    Number(s.draft_error_count || 0) > 0 ||
    Number(s.unresolved_count || 0) > 0 ||
    Number(s.review_not_done_subject_count || 0) > 0 ||
    Number(s.review_not_done_version_count || 0) > 0 ||
    Number(s.review_not_done_chapter_count || 0) > 0
  ) return 'needs_work'
  return 'done'
}

export function bankStatusMatches(stats: Record<string, any> | null | undefined, filter: BankTableStatusFilter) {
  if (filter === 'all') return true
  return bankStatusBucket(stats) === filter
}

export function BankTableToolbar({
  search,
  setSearch,
  placeholder,
  statusFilter,
  setStatusFilter,
  resultCount,
  totalCount,
  action,
}: {
  search: string
  setSearch: (value: string) => void
  placeholder: string
  statusFilter: BankTableStatusFilter
  setStatusFilter: (value: BankTableStatusFilter) => void
  resultCount: number
  totalCount: number
  action?: React.ReactNode
}) {
  const hasFilter = Boolean(search.trim()) || statusFilter !== 'all'
  return <div className="bank-table-toolbar" aria-label="Bộ lọc bảng ngân hàng đề">
    <div className="bank-table-toolbar-fields">
      <label className="bank-table-filter-field bank-table-search-field">
        <span>Tìm kiếm</span>
        <input className="input" aria-label={placeholder} value={search} onChange={(event) => setSearch(event.target.value)} placeholder={placeholder} />
      </label>
      <label className="bank-table-filter-field bank-table-status-field">
        <span>Trạng thái</span>
        <select className="input" value={statusFilter} onChange={(event) => setStatusFilter(event.target.value as BankTableStatusFilter)} aria-label="Lọc trạng thái ngân hàng đề">
          <option value="all">Tất cả</option>
          <option value="published">Đã đưa lên CMS</option>
          <option value="ready">Sẵn sàng chốt</option>
          <option value="needs_work">Cần xử lý</option>
          <option value="empty">Chưa có dữ liệu</option>
        </select>
      </label>
    </div>
    <div className="bank-table-toolbar-actions">
      <span className="bank-table-result-count">Hiện <b>{resultCount}</b>/<b>{totalCount}</b></span>
      {hasFilter ? <button className="btn small secondary" type="button" onClick={() => { setSearch(''); setStatusFilter('all') }}>Xóa lọc</button> : null}
      {action}
    </div>
  </div>
}

export function Modal({ open, title, children, onClose, wide = false }: { open: boolean; title: string; children: React.ReactNode; onClose: () => void; wide?: boolean }) {
  useEffect(() => {
    if (!open) return undefined
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onKeyDown)
    return () => { document.removeEventListener('keydown', onKeyDown) }
  }, [open, onClose])

  if (!open) return null
  return <div className="modal-backdrop bank-popup-backdrop" onMouseDown={onClose}>
    <div className={`modal-card bank-modal${wide ? ' bank-modal-wide' : ''}`} role="dialog" aria-modal="true" aria-label={title} onMouseDown={(event) => event.stopPropagation()}>
      <div className="section-head bank-modal-head">
        <div><h2>{title}</h2></div>
        <button className="btn small secondary" type="button" onClick={onClose}>Đóng</button>
      </div>
      <div className="bank-modal-body">{children}</div>
    </div>
  </div>
}


export function ConfirmDialog({ open, title, description, confirmLabel = 'Xác nhận', cancelLabel = 'Hủy', danger = false, busy = false, onClose, onConfirm }: {
  open: boolean
  title: string
  description?: ReactNode
  confirmLabel?: string
  cancelLabel?: string
  danger?: boolean
  busy?: boolean
  onClose: () => void
  onConfirm: () => void
}) {
  return <Modal open={open} title={title} onClose={onClose}>
    <div className="mini-form">
      {description ? <div className="helper">{description}</div> : null}
      <div className="modal-actions">
        <button className="btn secondary" type="button" disabled={busy} onClick={onClose}>{cancelLabel}</button>
        <button className={`btn${danger ? ' danger' : ''}`} type="button" disabled={busy} onClick={onConfirm}>{busy ? 'Đang xử lý...' : confirmLabel}</button>
      </div>
    </div>
  </Modal>
}

export function EntityActions({
  canManage,
  onEdit,
  onDelete,
  variant = 'menu',
  lockedLabel = '—',
}: {
  canManage: boolean
  onEdit: () => void
  onDelete: () => void
  variant?: 'menu' | 'inline'
  lockedLabel?: string
}) {
  const [open, setOpen] = useState(false)

  if (!canManage) {
    return <span className="entity-actions-placeholder" title={lockedLabel}>{lockedLabel}</span>
  }

  const stop = (event: MouseEvent) => {
    event.preventDefault()
    event.stopPropagation()
  }

  const runAction = (event: MouseEvent, action: () => void) => {
    stop(event)
    setOpen(false)
    action()
  }

  if (variant === 'inline') {
    return <div className="entity-actions-inline" onClick={stop} onMouseDown={stop} aria-label="Thao tác dòng">
      <button type="button" className="btn small secondary" onClick={(event) => runAction(event, onEdit)}>Sửa</button>
      <button type="button" className="btn small danger-soft" onClick={(event) => runAction(event, onDelete)}>Xóa</button>
    </div>
  }

  return <div className={`entity-actions${open ? ' open' : ''}`} onClick={stop} onMouseDown={stop}>
    <button
      type="button"
      className="entity-actions-trigger"
      aria-label="Mở menu hành động"
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


export function matchesSearch(text: string, search: string) {
  const s = search.trim().toLowerCase()
  if (!s) return true
  return text.toLowerCase().includes(s)
}


export function reviewStatusText(status?: string | null) {
  const value = status || 'empty'
  const labels: Record<string, string> = {
    published: 'Đã đưa lên CMS',
    ready: 'Sẵn sàng chốt',
    needs_review: 'Cần xử lý tiếp',
    needs_fix: 'Cần sửa câu hỏi',
    empty: 'Chưa có dữ liệu',
    not_ready: 'Cần hoàn thiện',
  }
  return labels[value] || 'Cần hoàn thiện'
}

export function reviewStatusClass(status?: string | null) {
  const value = status || 'empty'
  if (value === 'published') return 'bank-status-card status-published'
  if (value === 'ready') return 'bank-status-card status-ready'
  if (value === 'needs_fix') return 'bank-status-card status-danger'
  if (value === 'empty') return 'bank-status-card status-empty'
  return 'bank-status-card status-incomplete'
}

export function emptyReviewStats(extra: Record<string, unknown> = {}) {
  return {
    total_questions: 0,
    approved_count: 0,
    pending_review_count: 0,
    draft_error_count: 0,
    unresolved_count: 0,
    rejected_count: 0,
    is_review_done: false,
    has_questions: false,
    status: 'empty',
    published_release_count: 0,
    ready_to_release_chapter_count: 0,
    ...extra,
  }
}

export function StatLine({ label, value }: { label: string; value: React.ReactNode }) {
  return <div className="bank-stat-line"><span>{label}</span><b>{value}</b></div>
}

export function QuickSearchBox({ compact = false }: { compact?: boolean }) {
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
    <input className="input" value={q} onChange={(event) => setQ(event.target.value)} aria-label="Tìm nhanh bộ môn, môn, phiên bản, bài hoặc câu hỏi" placeholder="Tìm nhanh bộ môn, môn, phiên bản, bài hoặc câu hỏi..." />
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

export function questionStats(questions: BankVersionQuestion[]) {
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

export function nextReleaseText(release?: BankRelease | null) {
  if (!release) return 'Chưa chốt bộ đề'
  return `${release.release_code} · ${statusLabel(release.status)} · ${release.approved_question_count} câu`
}


export const bankAnswerRows = [
  ['A', 'option_a'],
  ['B', 'option_b'],
  ['C', 'option_c'],
  ['D', 'option_d'],
] as const

export function bankQuestionErrorMessage(question: BankVersionQuestion) {
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

export function isQuestionWaitingForReview(question: BankVersionQuestion) {
  return question.status === 'pending_review' || question.status === 'needs_review' || question.status === 'draft_error'
}

export type BankQuestionEditForm = {
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

export function toBankQuestionEditForm(question: BankVersionQuestion): BankQuestionEditForm {
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


export type BankChartRow = { label: string; value: number; tone?: 'blue' | 'green' | 'amber' | 'red' | 'slate' }

export function BankBarChart({ title, helper, rows, empty }: { title: string; helper?: string; rows: BankChartRow[]; empty?: string }) {
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

export function BankStackedChart({ title, helper, rows }: { title: string; helper?: string; rows: BankChartRow[] }) {
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

export function countRows<T>(items: T[], getter: (item: T) => string | null | undefined, tones: Record<string, BankChartRow['tone']> = {}) {
  const counts: Record<string, number> = {}
  items.forEach((item) => {
    const key = getter(item) || 'unknown'
    counts[key] = (counts[key] || 0) + 1
  })
  return Object.entries(counts).map(([label, value]) => ({ label: statusLabel(label), value, tone: tones[label] || 'blue' }))
}

export function auditActionText(action?: string | null) {
  const map: Record<string, string> = {
    'question_bank.release.quiz.create': 'Tạo Quiz trên CMS',
    'question_bank.course_quiz.rollback': 'Khôi phục Quiz',
    'question_bank.release.publish_openedx': 'Đưa bộ đề lên CMS',
    'question_bank.version.question.review': 'Duyệt câu hỏi',
    'question_bank.version.question.bulk_review': 'Duyệt hàng loạt',
    'question_bank.bank_version.generate': 'Tạo câu hỏi',
    'question_bank.material.upload': 'Tải tài liệu lên',
    'question_bank.quiz.auto_map.apply': 'Lưu cấu hình tạo Quiz',
  }
  return map[action || ''] || action || '—'
}

