'use client'

import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { useEffect, useMemo, useState } from 'react'
import { useAppContext } from '../../../context/AppContext'
import {
  BankRelease,
  BankReleaseReadiness,
  BankVersion,
  BankVersionDiffPreview,
  BankVersionQuestion,
  CourseQuizInstance,
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
  deleteMaterialVersion,
  generateFromBankVersion,
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
  publishBankRelease,
  reviewBankQuestion,
  rollbackCourseQuizInstance,
  uploadBankMaterial,
  updateBankQuestion,
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
  const { authHeaders, can } = useAppContext()
  const headers = useMemo(() => authHeaders(true), [authHeaders])
  return { headers, can }
}

function useAsyncMessage() {
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)
  const run = async (work: () => Promise<unknown>, ok: string, after?: () => Promise<void>) => {
    setBusy(true)
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
  return { message, setMessage, busy, run }
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

function matchesSearch(text: string, search: string) {
  const s = search.trim().toLowerCase()
  if (!s) return true
  return text.toLowerCase().includes(s)
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

export function DepartmentsPage() {
  const { headers, can } = useBankData()
  const { message, busy, run } = useAsyncMessage()
  const [departments, setDepartments] = useState<Department[]>([])
  const [subjects, setSubjects] = useState<Subject[]>([])
  const [search, setSearch] = useState('')
  const [createOpen, setCreateOpen] = useState(false)
  const [code, setCode] = useState('')
  const [name, setName] = useState('')

  const load = async () => {
    const [nextDepartments, nextSubjects] = await Promise.all([getDepartments(headers), getSubjects(headers)])
    setDepartments(nextDepartments)
    setSubjects(nextSubjects)
  }
  useEffect(() => { load().catch(() => null) }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const visible = departments.filter((item) => matchesSearch(`${item.code} ${item.name}`, search))
  const countSubjects = (departmentId: string) => subjects.filter((item) => item.department_id === departmentId).length

  return <div className="page-stack bank-multipage">
    <Breadcrumb items={[{ label: 'Bộ môn' }]} />
    <Toolbar title="Bộ môn" helper="Trang này chỉ quản lý danh sách bộ môn." action={<Link className="btn secondary" href="/bank/quiz">Tạo Quiz Open edX</Link>} />
    {message ? <div className="alert info">{message}</div> : null}
    <section className="card">
      <div className="section-head"><div><h2>Danh sách bộ môn</h2><p className="helper">Click vào bộ môn để xem các môn bên trong.</p></div></div>
      <SearchActionBar search={search} setSearch={setSearch} placeholder="Tìm bộ môn" action={<button className="btn" disabled={!can('manage_settings')} onClick={() => setCreateOpen(true)}>+ Thêm bộ môn</button>} />
      <div className="entity-list horizontal multipage-list">
        {visible.map((item) => <Link key={item.id} href={`/bank/departments/${item.id}/subjects`} className="entity-card link-card">
          <b>{item.name}</b>
          <small>{item.code} · {countSubjects(item.id)} môn</small>
          <span className={statusClass(item.status)}>{statusLabel(item.status)}</span>
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
  const [subjects, setSubjects] = useState<Subject[]>([])
  const [offerings, setOfferings] = useState<SubjectOffering[]>([])
  const [search, setSearch] = useState('')
  const [createOpen, setCreateOpen] = useState(false)
  const [code, setCode] = useState('')
  const [name, setName] = useState('')

  const load = async () => {
    const [nextDepartments, nextSubjects, nextOfferings] = await Promise.all([
      getDepartments(headers), getSubjects(headers, departmentId), getSubjectOfferings(headers),
    ])
    setDepartments(nextDepartments); setSubjects(nextSubjects); setOfferings(nextOfferings)
  }
  useEffect(() => { load().catch(() => null) }, [departmentId]) // eslint-disable-line react-hooks/exhaustive-deps

  const department = departments.find((item) => item.id === departmentId)
  const visible = subjects.filter((item) => matchesSearch(`${item.code} ${item.name}`, search))
  const countVersions = (subjectId: string) => offerings.filter((item) => item.subject_id === subjectId).length

  return <div className="page-stack bank-multipage">
    <Breadcrumb items={[{ label: 'Bộ môn', href: '/bank/departments' }, { label: department?.name || 'Bộ môn' }, { label: 'Môn' }]} />
    <Toolbar title={department ? `Môn trong ${department.name}` : 'Môn trong bộ môn'} helper="Trang này chỉ quản lý danh sách môn." />
    {message ? <div className="alert info">{message}</div> : null}
    <section className="card">
      <div className="section-head"><div><h2>Danh sách môn</h2><p className="helper">Click vào môn để quản lý các phiên bản theo kỳ.</p></div></div>
      <SearchActionBar search={search} setSearch={setSearch} placeholder="Tìm môn" action={<button className="btn" disabled={!can('manage_settings')} onClick={() => setCreateOpen(true)}>+ Thêm môn</button>} />
      <div className="entity-list horizontal multipage-list">
        {visible.map((item) => <Link key={item.id} href={`/bank/subjects/${item.id}/versions`} className="entity-card link-card">
          <b>{item.code} - {item.name}</b>
          <small>{countVersions(item.id)} phiên bản môn</small>
          <span className={statusClass(item.status)}>{statusLabel(item.status)}</span>
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
  const [offerings, setOfferings] = useState<SubjectOffering[]>([])
  const [chapters, setChapters] = useState<SubjectChapter[]>([])
  const [versions, setVersions] = useState<BankVersion[]>([])
  const [releases, setReleases] = useState<BankRelease[]>([])
  const [search, setSearch] = useState('')
  const [createOpen, setCreateOpen] = useState(false)
  const [term, setTerm] = useState('SU25')
  const [mode, setMode] = useState<'blank' | 'clone'>('clone')
  const [cloneFromId, setCloneFromId] = useState('')

  const load = async () => {
    const [nextDepartments, nextSubjects, nextOfferings, nextChapters, nextVersions, nextReleases] = await Promise.all([
      getDepartments(headers), getSubjects(headers), getSubjectOfferings(headers, subjectId), getSubjectChapters(headers, subjectId), getBankVersions(headers, undefined, subjectId), getBankReleases(headers),
    ])
    setDepartments(nextDepartments); setSubjects(nextSubjects); setOfferings(nextOfferings); setChapters(nextChapters); setVersions(nextVersions); setReleases(nextReleases)
    if (!cloneFromId && nextOfferings.length) setCloneFromId(nextOfferings[0].id)
  }
  useEffect(() => { load().catch(() => null) }, [subjectId]) // eslint-disable-line react-hooks/exhaustive-deps

  const subject = subjects.find((item) => item.id === subjectId)
  const department = departments.find((item) => item.id === subject?.department_id)
  const visible = offerings.filter((item) => matchesSearch(`${item.code} ${item.name} ${item.term || ''}`, search))
  const chapterCount = (offeringId: string) => chapters.filter((item) => item.subject_offering_id === offeringId).length
  const questionCount = (offeringId: string) => versions.filter((item) => item.subject_offering_id === offeringId).reduce((sum, bv) => sum + (Number((bv.metadata_json as any)?.question_count || 0) || 0), 0)
  const releaseCount = (offeringId: string) => releases.filter((release) => {
    const bv = versions.find((item) => item.id === release.bank_version_id)
    return bv?.subject_offering_id === offeringId
  }).length
  const publishedCount = (offeringId: string) => releases.filter((release) => {
    const bv = versions.find((item) => item.id === release.bank_version_id)
    return bv?.subject_offering_id === offeringId && release.status === 'published'
  }).length

  return <div className="page-stack bank-multipage">
    <Breadcrumb items={[{ label: 'Bộ môn', href: '/bank/departments' }, { label: department?.name || 'Bộ môn', href: department ? `/bank/departments/${department.id}/subjects` : undefined }, { label: subject?.code || 'Môn' }, { label: 'Phiên bản môn' }]} />
    <Toolbar title={subject ? `Phiên bản môn ${subject.code}` : 'Phiên bản môn'} helper="Quản lý các kỳ/version của môn. Clone không chạy diff và không bắt duyệt lại." />
    {message ? <div className="alert info">{message}</div> : null}
    <section className="card">
      <div className="section-head"><div><h2>Các phiên bản theo kỳ</h2><p className="helper">Click vào version để xem các bài.</p></div></div>
      <SearchActionBar search={search} setSearch={setSearch} placeholder="Tìm version môn" action={<button className="btn" disabled={!can('manage_settings')} onClick={() => setCreateOpen(true)}>+ Tạo version môn</button>} />
      <div className="entity-list horizontal multipage-list">
        {visible.map((item) => <Link key={item.id} href={`/bank/subject-versions/${item.id}/chapters`} className="entity-card link-card">
          <b>{item.code}</b>
          <small>{chapterCount(item.id)} bài · {questionCount(item.id)} câu · {releaseCount(item.id)} release</small>
          <small>{publishedCount(item.id)} release đã publish</small>
          <span className={statusClass(item.status)}>{statusLabel(item.status)}</span>
        </Link>)}
      </div>
      {!visible.length ? <div className="empty-state">Chưa có version môn phù hợp.</div> : null}
    </section>
    <Modal open={createOpen} title="Tạo version môn" onClose={() => setCreateOpen(false)}>
      <div className="mini-form">
        <label><span>Kỳ mới</span><select className="input" value={term} onChange={(event) => setTerm(event.target.value)}>{TERMS.map(([value, label]) => <option key={value} value={value}>{value} · {label}</option>)}</select></label>
        <label><span>Cách tạo</span><select className="input" value={mode} onChange={(event) => setMode(event.target.value as 'blank' | 'clone')}><option value="clone">Clone 100% từ version khác</option><option value="blank">Tạo mới trống</option></select></label>
        {mode === 'clone' ? <label><span>Clone từ</span><select className="input" value={cloneFromId} onChange={(event) => setCloneFromId(event.target.value)}>{offerings.map((item) => <option key={item.id} value={item.id}>{item.code}</option>)}</select></label> : null}
        <p className="helper">Clone sẽ copy bài, tài liệu và câu hỏi đã duyệt sang bản ghi mới. Release vẫn chốt tay sau khi giáo viên sửa xong.</p>
        <button className="btn" type="button" disabled={busy || (mode === 'clone' && !cloneFromId)} onClick={() => run(async () => {
          const saved = await createSubjectOffering(headers, { subject_id: subjectId, term, version_code: term, clone_from_offering_id: mode === 'clone' ? cloneFromId : null })
          setCreateOpen(false)
          router.push(`/bank/subject-versions/${saved.id}/chapters`)
        }, 'Đã tạo version môn', load)}>Tạo version môn</button>
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
  const [chapters, setChapters] = useState<SubjectChapter[]>([])
  const [versions, setVersions] = useState<BankVersion[]>([])
  const [releases, setReleases] = useState<BankRelease[]>([])
  const [search, setSearch] = useState('')
  const [createOpen, setCreateOpen] = useState(false)
  const [chapterInput, setChapterInput] = useState('')

  const load = async () => {
    const [nextDepartments, nextSubjects, nextOfferings, nextChapters, nextVersions, nextReleases] = await Promise.all([
      getDepartments(headers), getSubjects(headers), getSubjectOfferings(headers), getSubjectChapters(headers, undefined, versionId), getBankVersions(headers, undefined, undefined, versionId), getBankReleases(headers),
    ])
    setDepartments(nextDepartments); setSubjects(nextSubjects); setOfferings(nextOfferings); setChapters(nextChapters); setVersions(nextVersions); setReleases(nextReleases)
  }
  useEffect(() => { load().catch(() => null) }, [versionId]) // eslint-disable-line react-hooks/exhaustive-deps

  const offering = offerings.find((item) => item.id === versionId)
  const subject = subjects.find((item) => item.id === offering?.subject_id)
  const department = departments.find((item) => item.id === subject?.department_id)
  const visible = chapters.filter((item) => matchesSearch(chapterDisplayName(item), search))
  const countBankVersions = (chapterId: string) => versions.filter((item) => item.chapter_id === chapterId).length
  const countReleases = (chapterId: string) => releases.filter((item) => versions.some((bv) => bv.chapter_id === chapterId && bv.id === item.bank_version_id)).length

  return <div className="page-stack bank-multipage">
    <Breadcrumb items={[{ label: 'Bộ môn', href: '/bank/departments' }, { label: department?.name || 'Bộ môn', href: department ? `/bank/departments/${department.id}/subjects` : undefined }, { label: subject?.code || 'Môn', href: subject ? `/bank/subjects/${subject.id}/versions` : undefined }, { label: offering?.code || 'Version môn' }, { label: 'Bài' }]} />
    <Toolbar title={offering ? `Bài trong ${offering.code}` : 'Bài trong version môn'} helper="Trang này chỉ quản lý danh sách bài/chapter." />
    {message ? <div className="alert info">{message}</div> : null}
    <section className="card">
      <div className="section-head"><div><h2>Danh sách bài</h2><p className="helper">Click vào bài là vào ngay workspace, không cần bấm bắt đầu.</p></div></div>
      <SearchActionBar search={search} setSearch={setSearch} placeholder="Tìm bài" action={<button className="btn" disabled={!can('manage_settings')} onClick={() => setCreateOpen(true)}>+ Thêm bài</button>} />
      <div className="entity-list horizontal multipage-list">
        {visible.map((item) => <Link key={item.id} href={`/bank/chapters/${item.id}`} className="entity-card link-card">
          <b>{chapterDisplayName(item)}</b>
          <small>{countBankVersions(item.id)} bộ câu hỏi · {countReleases(item.id)} release</small>
          <span className={statusClass(item.status)}>{statusLabel(item.status)}</span>
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
            const nextNo = (chapters.reduce((max, item) => Math.max(max, Number(item.sort_order || item.chapter_no || 0)), 0) || 0) + 1
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
  const { message, busy, run } = useAsyncMessage()
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
  const [editingQuestion, setEditingQuestion] = useState<BankVersionQuestion | null>(null)
  const [editForm, setEditForm] = useState<BankQuestionEditForm | null>(null)

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
  const chapterQuestionLimit = 100
  const usedQuestionCount = stats.total
  const unresolvedQuestionCount = stats.pending + stats.draftError
  const releaseReviewBlocked = unresolvedQuestionCount > 0
  const remainingQuota = Math.max(0, chapterQuestionLimit - usedQuestionCount)
  const difficultyTotal = Number(difficultyEasy || 0) + Number(difficultyMedium || 0) + Number(difficultyHard || 0)
  const overQuota = numericGenerateCount > remainingQuota
  const invalidDifficulty = difficultyTotal !== 100
  const canGenerateNow = Boolean(selectedBankVersion && materials.length && can('generate_questions') && !overQuota && !invalidDifficulty && numericGenerateCount >= 1 && remainingQuota > 0)

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

  const materialPreviewChunks = (materialView?.chunks || []).slice(0, 80)
  const materialPreviewText = materialPreviewChunks.map((chunk, index) => `Đoạn ${index + 1}
${chunk.content}`).join('\n\n')

  return <div className="page-stack bank-multipage">
    <Breadcrumb items={[{ label: 'Bộ môn', href: '/bank/departments' }, { label: department?.name || 'Bộ môn', href: department ? `/bank/departments/${department.id}/subjects` : undefined }, { label: subject?.code || 'Môn', href: subject ? `/bank/subjects/${subject.id}/versions` : undefined }, { label: offering?.code || 'Version môn', href: offering ? `/bank/subject-versions/${offering.id}/chapters` : undefined }, { label: chapterDisplayName(chapter) }]} />
    <Toolbar title={chapter ? `${offering?.code || ''} / ${chapterDisplayName(chapter)}` : 'Workspace của bài'} helper={'Quản lý tài liệu, câu hỏi và release của một bài.'} />
    {message ? <div className="alert info">{message}</div> : null}
    {diffRequired ? <div className="alert warning"><b>Tài liệu đã thay đổi.</b> Hệ thống sẽ kiểm tra khác biệt và hiển thị kết quả để giáo viên xác nhận.</div> : null}

    <section className="summary-grid compact-summary">
      <div><span>Tài liệu</span><b>{materials.length}</b></div>
      <div><span>Câu đã duyệt</span><b>{stats.approved}</b></div>
      <div><span>Câu chờ duyệt</span><b>{stats.pending}</b></div>
      <div><span>Câu bị loại</span><b>{stats.rejected}</b></div>
      <div><span>Nhóm kiến thức</span><b>{stats.families}</b></div>
      <div><span>Release</span><b>{publishedRelease ? 'Đã publish' : latestRelease ? 'Đã chốt' : 'Chưa chốt'}</b><small>{nextReleaseText(publishedRelease || latestRelease)}</small></div>
    </section>

    <section className="card chapter-top-actions">
      <div>
        <b>Thao tác nhanh</b>
        <p className="helper">Chỉ dùng 2 nút chính. Chỉ được chốt bộ đề khi tất cả câu hỏi đã được duyệt hoặc bỏ.</p>
      </div>
      <div className="button-row no-margin">
        <button className="btn secondary" disabled={busy || !selectedBankVersion || !diffBaseBankVersionId} onClick={() => run(async () => {
          if (!selectedBankVersion) return
          await runDiffNow(selectedBankVersion.id, diffBaseBankVersionId)
        }, 'Đã kiểm tra khác biệt', refreshCurrent)}>Kiểm tra thay đổi</button>
        {!latestRelease ? <button className="btn" disabled={busy || !selectedBankVersion || !can('publish_questions') || !readiness?.can_create_release || releaseReviewBlocked} title={releaseReviewBlocked ? 'Phải duyệt hoặc bỏ hết tất cả câu hỏi trước khi chốt bộ đề.' : undefined} onClick={() => run(async () => {
          if (!selectedBankVersion) return
          await createBankRelease(headers, { bank_version_id: selectedBankVersion.id, include_approved_questions: true })
        }, 'Đã chốt Release', refreshCurrent)}>Chốt bộ đề</button> : latestRelease.status !== 'published' ? <button className="btn" disabled={busy || !can('publish_questions')} onClick={() => run(async () => { await publishBankRelease(headers, latestRelease.id, {}) }, 'Đã publish Library sang Open edX', refreshCurrent)}>Publish Library</button> : <button className="btn secondary" disabled>Đã publish</button>}
      </div>
      {releaseReviewBlocked ? <div className="alert warning"><b>Chưa thể chốt bộ đề.</b> Còn {stats.pending} câu chờ duyệt và {stats.draftError} câu lỗi. Hãy duyệt hoặc bỏ hết tất cả câu hỏi trước.</div> : null}
    </section>

    {!selectedBankVersion ? <section className="card"><div className="empty-state">Đang chuẩn bị workspace cho bài này...</div></section> : <section className="workspace-grid multipage-workspace">
      <div className="workspace-panel">
        <h3>Tài liệu</h3>
        <p className="helper">Gắn tài liệu để hệ thống tạo câu hỏi. Nếu version clone bị đổi tài liệu, hệ thống tự kiểm tra khác biệt.</p>
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
        <div className="entity-list compact-list small-chunk-list">
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

      <div className="workspace-panel">
        <h3>Tạo câu hỏi từ tài liệu</h3>
        <p className="helper">Luồng này giống phần tạo câu hỏi theo course trước đây: lấy tài liệu đã gắn làm nguồn, chia EASY/MEDIUM/HARD, kiểm tra chất lượng và chống trùng trước khi đưa vào danh sách duyệt.</p>
        <div className="quota-box"><b>{usedQuestionCount}/{chapterQuestionLimit}</b><small>Tổng câu đã tạo / tối đa 100 câu cho bài này · còn {remainingQuota} câu</small></div>
        <div className="generation-plan-box">
          <div><span>Nguồn tạo</span><b>{materials.length ? `${materials.length} tài liệu đã gắn` : 'Chưa có tài liệu'}</b></div>
          <div><span>Sẽ tạo</span><b>{Math.max(0, numericGenerateCount || 0)} câu mới</b></div>
          <div><span>Tỷ lệ</span><b>{difficultyEasy}/{difficultyMedium}/{difficultyHard}</b><small>Dễ / Trung bình / Khó</small></div>
        </div>
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
          {remainingQuota === 0 ? <div className="alert warning">Bài này đã đạt giới hạn 100 câu. Không thể tạo thêm.</div> : null}
          <button className="btn" disabled={busy || !canGenerateNow} onClick={() => run(async () => {
            if (!selectedBankVersion) return
            await generateFromBankVersion(headers, selectedBankVersion.id, { question_count: numericGenerateCount, target_question_count: 100, difficulty_easy: Number(difficultyEasy || 50), difficulty_medium: Number(difficultyMedium || 30), difficulty_hard: Number(difficultyHard || 20) })
          }, 'Đã tạo câu hỏi', refreshCurrent)}>Tạo câu hỏi</button>
        </div>
      </div>


      <div className="workspace-panel full">
        <div className="section-head"><div><h3>Danh sách câu hỏi</h3><p className="helper">Giao diện giống trang /review: đọc câu hỏi, xem đủ đáp án, rồi duyệt hoặc bỏ. Phải xử lý hết mới được chốt bộ đề.</p></div><button className="btn secondary" disabled={busy || !can('review_questions') || stats.pending === 0} onClick={() => run(async () => {
          if (!selectedBankVersion) return
          await bulkReviewBankQuestions(headers, selectedBankVersion.id, { action: 'approve', approve_all_pending: true, note: 'Duyệt hết câu chờ' })
        }, 'Đã duyệt hết câu chờ', refreshCurrent)}>Duyệt hết câu chờ</button></div>
        <div className="question-card-list bank-review-list">
          {questions.slice(0, 120).map((item, index) => {
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
                    {item.status !== 'rejected' && item.status !== 'published' ? <button className="btn small danger" disabled={busy || !can('review_questions')} onClick={() => run(async () => {
                      if (!selectedBankVersion) return
                      await reviewBankQuestion(headers, selectedBankVersion.id, item.id, { action: 'reject', note: item.status === 'draft_error' ? 'Bỏ câu lỗi' : 'Không dùng câu này' })
                    }, 'Đã bỏ câu hỏi', refreshCurrent)}>{item.status === 'draft_error' ? 'Bỏ câu lỗi' : 'Bỏ'}</button> : null}
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
        {!questions.length ? <div className="empty-state">Chưa có câu hỏi.</div> : null}
      </div>
    </section>}

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
