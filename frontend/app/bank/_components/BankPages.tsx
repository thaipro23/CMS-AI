'use client'

import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { useEffect, useMemo, useState } from 'react'
import { useAppContext } from '../../../context/AppContext'
import {
  BankRelease,
  BankReleaseReadiness,
  BankVersion,
  BankVersionQuestion,
  CourseQuizInstance,
  Department,
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
} from '../../../lib/api'

const TERMS = [
  ['SP25', 'Spring/Xuân 2025'], ['SU25', 'Summer/Hè 2025'], ['FA25', 'Fall/Đông 2025'],
  ['SP26', 'Spring/Xuân 2026'], ['SU26', 'Summer/Hè 2026'], ['FA26', 'Fall/Đông 2026'],
  ['SP27', 'Spring/Xuân 2027'], ['SU27', 'Summer/Hè 2027'], ['FA27', 'Fall/Đông 2027'],
]

function classNames(...items: Array<string | false | null | undefined>) {
  return items.filter(Boolean).join(' ')
}

function statusLabel(status?: string | null) {
  const value = status || 'draft'
  const labels: Record<string, string> = {
    active: 'Đang dùng', draft: 'Bản nháp', approved: 'Đã duyệt', published: 'Đã publish',
    pending_review: 'Chờ duyệt', rejected: 'Đã bỏ', failed: 'Lỗi', created: 'Đã tạo', rolled_back: 'Đã rollback',
  }
  return labels[value] || value
}

function statusClass(status?: string | null) {
  const value = status || ''
  if (['active', 'approved', 'published', 'created'].includes(value)) return 'status success'
  if (['failed', 'rejected', 'rolled_back'].includes(value)) return 'status danger'
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

function FilterBox({ value, onChange, placeholder = 'Tìm kiếm' }: { value: string; onChange: (value: string) => void; placeholder?: string }) {
  return <input className="input" value={value} onChange={(event) => onChange(event.target.value)} placeholder={placeholder} />
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
    approved: questions.filter((item) => item.status === 'approved' || item.status === 'published').length,
    pending: questions.filter((item) => item.status === 'pending_review').length,
    rejected: questions.filter((item) => item.status === 'rejected').length,
    draftError: questions.filter((item) => item.status === 'draft_error').length,
    families: families.size,
  }
}

export function DepartmentsPage() {
  const { headers, can } = useBankData()
  const { message, busy, run } = useAsyncMessage()
  const [departments, setDepartments] = useState<Department[]>([])
  const [subjects, setSubjects] = useState<Subject[]>([])
  const [search, setSearch] = useState('')
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
    <Toolbar title="Bộ môn" helper="Mỗi trang chỉ quản lý một nhóm việc. Trang này chỉ hiển thị bộ môn." action={<Link className="btn secondary" href="/bank/quiz">Tạo Quiz Open edX</Link>} />
    {message ? <div className="alert info">{message}</div> : null}

    <section className="card">
      <div className="section-head"><div><h2>Thêm bộ môn</h2><p className="helper">Ví dụ: Công nghệ thông tin, Thiết kế, Marketing.</p></div></div>
      <div className="inline-form compact-form">
        <input className="input mini-input" value={code} onChange={(event) => setCode(event.target.value)} placeholder="CNTT" />
        <input className="input" value={name} onChange={(event) => setName(event.target.value)} placeholder="Công nghệ thông tin" />
        <button className="btn" disabled={busy || !code.trim() || !name.trim() || !can('manage_settings')} onClick={() => run(async () => {
          await createDepartment(headers, { code, name })
          setCode(''); setName('')
        }, 'Đã thêm bộ môn', load)}>+ Thêm bộ môn</button>
      </div>
    </section>

    <section className="card">
      <div className="section-head"><div><h2>Danh sách bộ môn</h2><p className="helper">Click vào bộ môn để xem các môn bên trong.</p></div><FilterBox value={search} onChange={setSearch} placeholder="Tìm bộ môn" /></div>
      <div className="entity-list horizontal multipage-list">
        {visible.map((item) => <Link key={item.id} href={`/bank/departments/${item.id}/subjects`} className="entity-card link-card">
          <b>{item.name}</b>
          <small>{item.code} · {countSubjects(item.id)} môn</small>
          <span className={statusClass(item.status)}>{statusLabel(item.status)}</span>
        </Link>)}
      </div>
      {!visible.length ? <div className="empty-state">Chưa có bộ môn phù hợp.</div> : null}
    </section>
  </div>
}

export function DepartmentSubjectsPage({ departmentId }: { departmentId: string }) {
  const { headers, can } = useBankData()
  const { message, busy, run } = useAsyncMessage()
  const [departments, setDepartments] = useState<Department[]>([])
  const [subjects, setSubjects] = useState<Subject[]>([])
  const [offerings, setOfferings] = useState<SubjectOffering[]>([])
  const [search, setSearch] = useState('')
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
    <Toolbar title={department ? `Môn trong ${department.name}` : 'Môn trong bộ môn'} helper="Trang này chỉ quản lý danh sách môn thuộc một bộ môn." />
    {message ? <div className="alert info">{message}</div> : null}

    <section className="card">
      <div className="section-head"><div><h2>Thêm môn</h2><p className="helper">Ví dụ: WEB107 - Thiết kế trang web, DBI102 - Database.</p></div></div>
      <div className="inline-form compact-form">
        <input className="input mini-input" value={code} onChange={(event) => setCode(event.target.value)} placeholder="WEB107" />
        <input className="input" value={name} onChange={(event) => setName(event.target.value)} placeholder="Thiết kế trang web" />
        <button className="btn" disabled={busy || !code.trim() || !name.trim() || !can('manage_settings')} onClick={() => run(async () => {
          await createSubject(headers, { department_id: departmentId, code, name })
          setCode(''); setName('')
        }, 'Đã thêm môn', load)}>+ Thêm môn</button>
      </div>
    </section>

    <section className="card">
      <div className="section-head"><div><h2>Danh sách môn</h2><p className="helper">Click vào môn để quản lý các phiên bản môn.</p></div><FilterBox value={search} onChange={setSearch} placeholder="Tìm môn" /></div>
      <div className="entity-list horizontal multipage-list">
        {visible.map((item) => <Link key={item.id} href={`/bank/subjects/${item.id}/versions`} className="entity-card link-card">
          <b>{item.code} - {item.name}</b>
          <small>{countVersions(item.id)} phiên bản môn</small>
          <span className={statusClass(item.status)}>{statusLabel(item.status)}</span>
        </Link>)}
      </div>
      {!visible.length ? <div className="empty-state">Chưa có môn phù hợp.</div> : null}
    </section>
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
    <Toolbar title={subject ? `Phiên bản môn ${subject.code}` : 'Phiên bản môn'} helper="Tạo kỳ mới hoặc clone 100% từ kỳ cũ. Không chạy diff khi clone." />
    {message ? <div className="alert info">{message}</div> : null}

    <section className="card">
      <div className="section-head"><div><h2>Tạo version môn</h2><p className="helper">Clone là copy bản làm việc sang kỳ mới: bài, tài liệu, câu hỏi approved. Release sẽ chốt bằng tay sau.</p></div></div>
      <div className="inline-form compact-form version-create-grid">
        <label><span>Kỳ mới</span><select className="input" value={term} onChange={(event) => setTerm(event.target.value)}>{TERMS.map(([value, label]) => <option key={value} value={value}>{value} · {label}</option>)}</select></label>
        <label><span>Cách tạo</span><select className="input" value={mode} onChange={(event) => setMode(event.target.value as 'blank' | 'clone')}><option value="clone">Clone 100% từ version khác</option><option value="blank">Tạo mới trống</option></select></label>
        {mode === 'clone' ? <label><span>Clone từ</span><select className="input" value={cloneFromId} onChange={(event) => setCloneFromId(event.target.value)}>{offerings.map((item) => <option key={item.id} value={item.id}>{item.code}</option>)}</select></label> : null}
        <button className="btn" disabled={busy || !can('manage_settings') || (mode === 'clone' && !cloneFromId)} onClick={() => run(async () => {
          const saved = await createSubjectOffering(headers, { subject_id: subjectId, term, version_code: term, clone_from_offering_id: mode === 'clone' ? cloneFromId : null })
          router.push(`/bank/subject-versions/${saved.id}/chapters`)
        }, 'Đã tạo version môn', load)}>+ Tạo version môn</button>
      </div>
    </section>

    <section className="card">
      <div className="section-head"><div><h2>Các version môn</h2><p className="helper">Click vào version để xem các bài/chapter.</p></div></div>
      <div className="entity-list horizontal multipage-list">
        {offerings.map((item) => <Link key={item.id} href={`/bank/subject-versions/${item.id}/chapters`} className="entity-card link-card">
          <b>{item.code}</b>
          <small>{chapterCount(item.id)} bài · {questionCount(item.id)} câu · {releaseCount(item.id)} release</small>
          <small>{publishedCount(item.id)} release đã publish</small>
          <span className={statusClass(item.status)}>{statusLabel(item.status)}</span>
        </Link>)}
      </div>
      {!offerings.length ? <div className="empty-state">Chưa có version môn. Hãy tạo mới hoặc clone từ kỳ trước.</div> : null}
    </section>
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
  const [chapterNo, setChapterNo] = useState('1')
  const [chapterTitle, setChapterTitle] = useState('Bài 1: Tổng quan')

  const load = async () => {
    const [nextDepartments, nextSubjects, nextOfferings, nextChapters, nextVersions, nextReleases] = await Promise.all([
      getDepartments(headers), getSubjects(headers), getSubjectOfferings(headers), getSubjectChapters(headers, undefined, versionId), getBankVersions(headers, undefined, undefined, versionId), getBankReleases(headers),
    ])
    setDepartments(nextDepartments); setSubjects(nextSubjects); setOfferings(nextOfferings); setChapters(nextChapters); setVersions(nextVersions); setReleases(nextReleases)
    const nextNo = nextChapters.length + 1
    setChapterNo(String(nextNo)); setChapterTitle(`Bài ${nextNo}: `)
  }
  useEffect(() => { load().catch(() => null) }, [versionId]) // eslint-disable-line react-hooks/exhaustive-deps

  const offering = offerings.find((item) => item.id === versionId)
  const subject = subjects.find((item) => item.id === offering?.subject_id)
  const department = departments.find((item) => item.id === subject?.department_id)
  const countBankVersions = (chapterId: string) => versions.filter((item) => item.chapter_id === chapterId).length
  const countReleases = (chapterId: string) => releases.filter((release) => versions.some((bv) => bv.chapter_id === chapterId && bv.id === release.bank_version_id)).length

  return <div className="page-stack bank-multipage">
    <Breadcrumb items={[{ label: 'Bộ môn', href: '/bank/departments' }, { label: department?.name || 'Bộ môn', href: department ? `/bank/departments/${department.id}/subjects` : undefined }, { label: subject?.code || 'Môn', href: subject ? `/bank/subjects/${subject.id}/versions` : undefined }, { label: offering?.code || 'Version môn' }, { label: 'Bài' }]} />
    <Toolbar title={offering ? `Bài trong ${offering.code}` : 'Bài trong version môn'} helper="Trang này chỉ quản lý danh sách bài/chapter của một version môn." />
    {message ? <div className="alert info">{message}</div> : null}

    <section className="card">
      <div className="section-head"><div><h2>Thêm bài</h2><p className="helper">Sau khi thêm bài, click vào bài để vào workspace tài liệu/câu hỏi.</p></div></div>
      <div className="inline-form compact-form">
        <input className="input mini-input" value={chapterNo} onChange={(event) => setChapterNo(event.target.value)} placeholder="1" />
        <input className="input" value={chapterTitle} onChange={(event) => setChapterTitle(event.target.value)} placeholder="Bài 1: Tổng quan" />
        <button className="btn" disabled={busy || !offering || !chapterTitle.trim() || !can('manage_settings')} onClick={() => run(async () => {
          if (!offering) return
          await createSubjectChapter(headers, { subject_id: offering.subject_id, subject_offering_id: offering.id, chapter_no: Number(chapterNo || 1), title: chapterTitle, sort_order: Number(chapterNo || 1) })
        }, 'Đã thêm bài', load)}>+ Thêm bài</button>
      </div>
    </section>

    <section className="card">
      <div className="section-head"><div><h2>Danh sách bài</h2><p className="helper">Click vào bài để gắn tài liệu, tạo câu hỏi, duyệt và chốt release.</p></div></div>
      <div className="entity-list horizontal multipage-list">
        {chapters.map((item) => <Link key={item.id} href={`/bank/chapters/${item.id}`} className="entity-card link-card">
          <b>Bài {item.chapter_no}: {item.title}</b>
          <small>{countBankVersions(item.id)} bộ câu hỏi · {countReleases(item.id)} release</small>
          <span className={statusClass(item.status)}>{statusLabel(item.status)}</span>
        </Link>)}
      </div>
      {!chapters.length ? <div className="empty-state">Chưa có bài trong version môn này.</div> : null}
    </section>
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
  const [releaseCode, setReleaseCode] = useState('')

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
    setMaterials(nextMaterials); setQuestions(nextQuestions); setReadiness(nextReadiness)
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

  const ensureBankVersion = async () => {
    if (!chapter) throw new Error('Không tìm thấy bài')
    if (selectedBankVersion) return selectedBankVersion
    return createBankVersion(headers, { subject_id: chapter.subject_id, subject_offering_id: chapter.subject_offering_id, chapter_id: chapter.id, version_code: 'v1.0', title: `${offering?.code || ''} - Bài ${chapter.chapter_no}`.trim(), change_note: 'Khởi tạo bộ câu hỏi cho bài' })
  }

  return <div className="page-stack bank-multipage">
    <Breadcrumb items={[{ label: 'Bộ môn', href: '/bank/departments' }, { label: department?.name || 'Bộ môn', href: department ? `/bank/departments/${department.id}/subjects` : undefined }, { label: subject?.code || 'Môn', href: subject ? `/bank/subjects/${subject.id}/versions` : undefined }, { label: offering?.code || 'Version môn', href: offering ? `/bank/subject-versions/${offering.id}/chapters` : undefined }, { label: chapter ? `Bài ${chapter.chapter_no}` : 'Bài' }]} />
    <Toolbar title={chapter ? `${offering?.code || ''} / Bài ${chapter.chapter_no}` : 'Workspace của bài'} helper={chapter?.title || 'Quản lý tài liệu, câu hỏi và release của một bài.'} action={<Link className="btn secondary" href="/bank/quiz">Tạo Quiz Open edX</Link>} />
    {message ? <div className="alert info">{message}</div> : null}
    {diffRequired ? <div className="alert warning"><b>Tài liệu đã thay đổi.</b> Hãy kiểm tra khác biệt trước khi chốt Release.</div> : null}

    <section className="summary-grid compact-summary">
      <div><span>Tài liệu</span><b>{materials.length}</b></div>
      <div><span>Câu đã duyệt</span><b>{stats.approved}</b></div>
      <div><span>Câu chờ duyệt</span><b>{stats.pending}</b></div>
      <div><span>Câu bị loại</span><b>{stats.rejected}</b></div>
      <div><span>Nhóm kiến thức</span><b>{stats.families}</b></div>
      <div><span>Release public</span><b>{publishedRelease ? 'Có' : 'Chưa'}</b><small>{publishedRelease?.openedx_library_key || latestRelease?.status || 'Chưa chốt'}</small></div>
    </section>

    {!selectedBankVersion ? <section className="card">
      <div className="section-head"><div><h2>Bắt đầu làm câu hỏi cho bài này</h2><p className="helper">Hệ thống sẽ tạo không gian làm việc nội bộ. Giáo viên không cần quan tâm ID kỹ thuật.</p></div></div>
      <button className="btn" disabled={busy || !can('edit_questions')} onClick={() => run(async () => { await ensureBankVersion() }, 'Đã khởi tạo bài', async () => { await load() })}>Bắt đầu</button>
    </section> : null}

    {selectedBankVersion ? <section className="workspace-grid multipage-workspace">
      <div className="workspace-panel">
        <h3>1. Tài liệu</h3>
        <p className="helper">Upload tài liệu mới ở version clone sẽ đánh dấu cần kiểm tra khác biệt.</p>
        <div className="mini-form">
          <input className="input" type="file" onChange={(event) => setFile(event.target.files?.[0] || null)} />
          <button className="btn" disabled={busy || !file || !can('edit_questions')} onClick={() => run(async () => {
            if (!file) return
            await uploadBankMaterial(headers, selectedBankVersion.id, file, { title: file.name, change_type: diffBaseBankVersionId ? 'updated_after_clone' : 'initial', replace_existing: false })
            setFile(null)
          }, 'Đã gắn tài liệu', async () => { await load(); await loadDetail(selectedBankVersion.id) })}>+ Gắn tài liệu</button>
        </div>
        <div className="entity-list compact-list small-chunk-list">
          {materials.slice(0, 8).map((item) => <div className="entity-card" key={item.id}><b>{item.title || item.file_name}</b><small>{item.file_type} · {new Date(item.created_at).toLocaleString('vi-VN')}</small></div>)}
        </div>
      </div>

      <div className="workspace-panel">
        <h3>2. Tạo câu hỏi</h3>
        <p className="helper">Tạo câu hỏi từ tài liệu đã gắn vào bài.</p>
        <div className="mini-form">
          <input className="input" value={generateCount} onChange={(event) => setGenerateCount(event.target.value)} placeholder="Số câu" />
          <div className="three-col-form">
            <input className="input" value={difficultyEasy} onChange={(event) => setDifficultyEasy(event.target.value)} placeholder="Easy %" />
            <input className="input" value={difficultyMedium} onChange={(event) => setDifficultyMedium(event.target.value)} placeholder="Medium %" />
            <input className="input" value={difficultyHard} onChange={(event) => setDifficultyHard(event.target.value)} placeholder="Hard %" />
          </div>
          <button className="btn" disabled={busy || !can('generate_questions')} onClick={() => run(async () => {
            await generateFromBankVersion(headers, selectedBankVersion.id, { question_count: Number(generateCount || 5), difficulty_easy: Number(difficultyEasy || 50), difficulty_medium: Number(difficultyMedium || 30), difficulty_hard: Number(difficultyHard || 20) })
          }, 'Đã tạo câu hỏi', async () => { await loadDetail(selectedBankVersion.id) })}>Tạo câu hỏi</button>
        </div>
      </div>

      <div className="workspace-panel">
        <h3>3. Kiểm tra thay đổi</h3>
        <p className="helper">Chỉ dùng khi tài liệu bị thay đổi sau clone.</p>
        <div className="button-row no-margin">
          <button className="btn secondary" disabled={busy || !diffBaseBankVersionId} onClick={() => run(async () => {
            await previewBankVersionDiff(headers, selectedBankVersion.id, { base_bank_version_id: diffBaseBankVersionId, persist: true })
          }, 'Đã kiểm tra khác biệt', async () => { await load(); await loadDetail(selectedBankVersion.id) })}>Kiểm tra khác biệt</button>
          <button className="btn secondary" disabled={busy || !diffRequired} onClick={() => run(async () => { await markBankDiffResolved(headers, selectedBankVersion.id, { note: 'Đã xử lý thay đổi tài liệu' }) }, 'Đã đánh dấu xử lý xong', async () => { await load(); await loadDetail(selectedBankVersion.id) })}>Đã xử lý</button>
        </div>
      </div>

      <div className="workspace-panel">
        <h3>4. Chốt Release</h3>
        <p className="helper">Chỉ chốt khi câu hỏi đã ổn. Sau đó mới publish Library để tạo Quiz.</p>
        {readiness ? <div className={readiness.can_create_release ? 'alert success' : 'alert warning'}>{readiness.message}</div> : null}
        <div className="mini-form">
          <input className="input" value={releaseCode} onChange={(event) => setReleaseCode(event.target.value)} placeholder="Release v1.0" />
          <div className="button-row no-margin">
            <button className="btn" disabled={busy || !can('publish_questions') || !readiness?.can_create_release} onClick={() => run(async () => { await createBankRelease(headers, { bank_version_id: selectedBankVersion.id, release_code: releaseCode || undefined, include_approved_questions: true }) }, 'Đã chốt Release', async () => { await load(); await loadDetail(selectedBankVersion.id) })}>Chốt bộ đề</button>
            {latestRelease ? <button className="btn secondary" disabled={busy || !can('publish_questions') || latestRelease.status === 'published'} onClick={() => run(async () => { await publishBankRelease(headers, latestRelease.id, {}) }, 'Đã publish Library sang Open edX', async () => { await load(); await loadDetail(selectedBankVersion.id) })}>Publish Library</button> : null}
          </div>
        </div>
      </div>

      <div className="workspace-panel full">
        <div className="section-head"><div><h3>5. Danh sách câu hỏi</h3><p className="helper">Duyệt câu hỏi ở đây. Không tạo Quiz trong workspace này.</p></div><button className="btn secondary" disabled={busy || !can('review_questions') || stats.pending === 0} onClick={() => run(async () => { await bulkReviewBankQuestions(headers, selectedBankVersion.id, { action: 'approve', approve_all_pending: true, note: 'Duyệt hết câu chờ' }) }, 'Đã duyệt hết câu chờ', async () => { await loadDetail(selectedBankVersion.id) })}>Duyệt hết câu chờ</button></div>
        <div className="table-wrap"><table className="data-table compact-table"><thead><tr><th>Câu hỏi</th><th>Độ khó</th><th>Trạng thái</th><th>Hành động</th></tr></thead><tbody>{questions.slice(0, 120).map((item) => <tr key={item.id}><td><b>{item.question_text}</b><small>{item.correct_answer ? `Đáp án: ${item.correct_answer}` : ''}</small></td><td>{item.difficulty}</td><td><span className={statusClass(item.status)}>{statusLabel(item.status)}</span></td><td><div className="button-row no-margin">{item.status !== 'approved' && item.status !== 'published' ? <button className="btn small" disabled={busy || !can('review_questions')} onClick={() => run(async () => { await reviewBankQuestion(headers, selectedBankVersion.id, item.id, { action: 'approve', note: 'Giữ câu hỏi này' }) }, 'Đã duyệt câu hỏi', async () => { await loadDetail(selectedBankVersion.id) })}>Duyệt</button> : null}{item.status !== 'rejected' && item.status !== 'published' ? <button className="btn small secondary" disabled={busy || !can('review_questions')} onClick={() => run(async () => { await reviewBankQuestion(headers, selectedBankVersion.id, item.id, { action: 'reject', note: 'Không dùng câu này' }) }, 'Đã bỏ câu hỏi', async () => { await loadDetail(selectedBankVersion.id) })}>Bỏ</button> : null}</div></td></tr>)}</tbody></table></div>
        {!questions.length ? <div className="empty-state">Chưa có câu hỏi.</div> : null}
      </div>
    </section> : null}
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
