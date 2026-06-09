'use client'

import Link from 'next/link'
import { useEffect, useMemo, useState } from 'react'
import { useAppContext } from '../../context/AppContext'
import {
  BankRelease,
  BankSummary,
  BankVersion,
  BankReleaseReadiness,
  BankVersionQuestion,
  Department,
  MaterialChunk,
  Subject,
  SubjectChapter,
  SubjectOffering,
} from '../../types'
import {
  createBankRelease,
  publishBankRelease,
  createBankVersion,
  createDepartment,
  createSubject,
  createSubjectOffering,
  createSubjectChapter,
  getBankReleases,
  getBankSummary,
  getBankVersions,
  getBankMaterialChunks,
  getBankVersionQuestions,
  getDepartments,
  getSubjectChapters,
  getSubjects,
  getSubjectOfferings,
  uploadBankMaterial,
  generateFromBankVersion,
  previewBankVersionDiff,
  reviewBankQuestion,
  bulkReviewBankQuestions,
  markBankDiffResolved,
  getBankReleaseReadiness,
} from '../../lib/api'

const emptySummary: BankSummary = {
  departments: 0,
  subjects: 0,
  chapters: 0,
  bank_versions: 0,
  releases: 0,
  published_releases: 0,
  course_mappings: 0,
  quiz_blueprints: 0,
  material_versions: 0,
  material_chunks: 0,
  bank_questions: 0,
  bank_diffs: 0,
  carry_over_questions: 0,
  retired_questions: 0,
}

const TERMS = [
  ['SP25', 'Spring/Xuân 2025'], ['SU25', 'Summer/Hè 2025'], ['FA25', 'Fall/Đông 2025'],
  ['SP26', 'Spring/Xuân 2026'], ['SU26', 'Summer/Hè 2026'], ['FA26', 'Fall/Đông 2026'],
  ['SP27', 'Spring/Xuân 2027'], ['SU27', 'Summer/Hè 2027'], ['FA27', 'Fall/Đông 2027'],
]

function questionStats(questions: BankVersionQuestion[]) {
  const families = new Set(questions.map((item) => item.question_family_id).filter(Boolean))
  return {
    total: questions.length,
    approved: questions.filter((item) => item.status === 'approved').length,
    pending: questions.filter((item) => item.status === 'pending_review').length,
    rejected: questions.filter((item) => item.status === 'rejected').length,
    published: questions.filter((item) => item.status === 'published').length,
    draftError: questions.filter((item) => item.status === 'draft_error').length,
    families: families.size,
  }
}

function classNames(...items: Array<string | false | null | undefined>) {
  return items.filter(Boolean).join(' ')
}

export default function BankPage() {
  const { authHeaders, can } = useAppContext()
  const headers = useMemo(() => authHeaders(true), [authHeaders])
  const [summary, setSummary] = useState<BankSummary>(emptySummary)
  const [departments, setDepartments] = useState<Department[]>([])
  const [subjects, setSubjects] = useState<Subject[]>([])
  const [offerings, setOfferings] = useState<SubjectOffering[]>([])
  const [chapters, setChapters] = useState<SubjectChapter[]>([])
  const [versions, setVersions] = useState<BankVersion[]>([])
  const [releases, setReleases] = useState<BankRelease[]>([])
  const [materialChunks, setMaterialChunks] = useState<MaterialChunk[]>([])
  const [bankQuestions, setBankQuestions] = useState<BankVersionQuestion[]>([])
  const [releaseReadiness, setReleaseReadiness] = useState<BankReleaseReadiness | null>(null)

  const [selectedDepartmentId, setSelectedDepartmentId] = useState('')
  const [selectedSubjectId, setSelectedSubjectId] = useState('')
  const [selectedOfferingId, setSelectedOfferingId] = useState('')
  const [selectedChapterId, setSelectedChapterId] = useState('')
  const [selectedVersionId, setSelectedVersionId] = useState('')

  const [deptCode, setDeptCode] = useState('')
  const [deptName, setDeptName] = useState('')
  const [subjectCode, setSubjectCode] = useState('')
  const [subjectName, setSubjectName] = useState('')
  const [term, setTerm] = useState('SP25')
  const [cloneFromOfferingId, setCloneFromOfferingId] = useState('')
  const [chapterNo, setChapterNo] = useState('1')
  const [chapterTitle, setChapterTitle] = useState('Bài 1: Tổng quan')
  const [bankVersionCode, setBankVersionCode] = useState('v1.0')
  const [bankVersionNote, setBankVersionNote] = useState('Tài liệu gốc ban đầu')
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [generateCount, setGenerateCount] = useState('5')
  const [difficultyEasy, setDifficultyEasy] = useState('50')
  const [difficultyMedium, setDifficultyMedium] = useState('30')
  const [difficultyHard, setDifficultyHard] = useState('20')
  const [releaseCode, setReleaseCode] = useState('')

  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)

  const load = async () => {
    const [nextSummary, nextDepartments, nextSubjects, nextOfferings, nextChapters, nextVersions, nextReleases] = await Promise.all([
      getBankSummary(headers),
      getDepartments(headers),
      getSubjects(headers),
      getSubjectOfferings(headers),
      getSubjectChapters(headers),
      getBankVersions(headers),
      getBankReleases(headers),
    ])
    setSummary(nextSummary)
    setDepartments(nextDepartments)
    setSubjects(nextSubjects)
    setOfferings(nextOfferings)
    setChapters(nextChapters)
    setVersions(nextVersions)
    setReleases(nextReleases)

    const nextDepartmentId = selectedDepartmentId || nextDepartments[0]?.id || ''
    const nextSubjectId = selectedSubjectId || nextSubjects.find((item) => item.department_id === nextDepartmentId)?.id || nextSubjects[0]?.id || ''
    const nextOfferingId = selectedOfferingId || nextOfferings.find((item) => item.subject_id === nextSubjectId)?.id || ''
    const nextChapterId = selectedChapterId || nextChapters.find((item) => item.subject_offering_id === nextOfferingId)?.id || ''
    const nextVersionId = selectedVersionId || nextVersions.find((item) => item.chapter_id === nextChapterId)?.id || ''

    setSelectedDepartmentId(nextDepartmentId)
    setSelectedSubjectId(nextSubjectId)
    setSelectedOfferingId(nextOfferingId)
    setSelectedChapterId(nextChapterId)
    setSelectedVersionId(nextVersionId)
  }

  const loadVersionDetail = async (bankVersionId: string) => {
    if (!bankVersionId) {
      setMaterialChunks([])
      setBankQuestions([])
      setReleaseReadiness(null)
      return
    }
    const [chunks, questions, readiness] = await Promise.all([
      getBankMaterialChunks(headers, bankVersionId).catch(() => []),
      getBankVersionQuestions(headers, bankVersionId).catch(() => []),
      getBankReleaseReadiness(headers, bankVersionId).catch(() => null),
    ])
    setMaterialChunks(chunks)
    setBankQuestions(questions)
    setReleaseReadiness(readiness)
  }

  useEffect(() => {
    load().catch((error) => setMessage(error instanceof Error ? error.message : 'Không tải được ngân hàng đề'))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    loadVersionDetail(selectedVersionId).catch(() => null)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedVersionId])

  const run = async (work: () => Promise<unknown>, ok: string) => {
    setBusy(true)
    setMessage('')
    try {
      await work()
      await load()
      await loadVersionDetail(selectedVersionId)
      setMessage(ok)
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Thao tác thất bại')
    } finally {
      setBusy(false)
    }
  }

  const subjectsOfDepartment = subjects.filter((item) => item.department_id === selectedDepartmentId)
  const versionsOfSubject = offerings.filter((item) => item.subject_id === selectedSubjectId)
  const chaptersOfVersion = chapters.filter((item) => item.subject_offering_id === selectedOfferingId)
  const bankVersionsOfChapter = versions.filter((item) => item.chapter_id === selectedChapterId && (!selectedOfferingId || item.subject_offering_id === selectedOfferingId))
  const releasesOfVersion = releases.filter((item) => item.bank_version_id === selectedVersionId)
  const publishedReleases = releasesOfVersion.filter((item) => item.status === 'published')
  const selectedDepartment = departments.find((item) => item.id === selectedDepartmentId)
  const selectedSubject = subjects.find((item) => item.id === selectedSubjectId)
  const selectedOffering = offerings.find((item) => item.id === selectedOfferingId)
  const selectedChapter = chapters.find((item) => item.id === selectedChapterId)
  const selectedVersion = versions.find((item) => item.id === selectedVersionId)
  const selectedVersionMeta = selectedVersion?.metadata_json || {}
  const diffRequired = Boolean(selectedVersionMeta.diff_required)
  const diffBaseBankVersionId = String(selectedVersionMeta.diff_base_bank_version_id || selectedVersion?.based_on_version_id || '')
  const isClonedBankVersion = Boolean(selectedVersion?.based_on_version_id || selectedVersionMeta.cloned_from_bank_version_id)
  const stats = questionStats(bankQuestions)

  const runDiffPreview = async () => {
    if (!selectedVersionId || !diffBaseBankVersionId) return
    setBusy(true)
    setMessage('')
    try {
      const result = await previewBankVersionDiff(headers, selectedVersionId, { base_bank_version_id: diffBaseBankVersionId, persist: true })
      await load()
      await loadVersionDetail(selectedVersionId)
      setMessage(`Đã kiểm tra khác biệt tài liệu: độ giống ${Math.round((result.material_similarity || 0) * 100)}%, ${result.summary.review_candidate_count} câu cần xem lại, ${result.summary.retire_candidate_count} câu có thể cần bỏ, ${result.summary.carry_over_candidate_count} câu có thể dùng lại.`)
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Không kiểm tra được khác biệt tài liệu')
    } finally {
      setBusy(false)
    }
  }

  const selectDepartment = (id: string) => {
    setSelectedDepartmentId(id)
    const firstSubject = subjects.find((item) => item.department_id === id)
    setSelectedSubjectId(firstSubject?.id || '')
    const firstOffering = firstSubject ? offerings.find((item) => item.subject_id === firstSubject.id) : undefined
    setSelectedOfferingId(firstOffering?.id || '')
    const firstChapter = firstOffering ? chapters.find((item) => item.subject_offering_id === firstOffering.id) : undefined
    setSelectedChapterId(firstChapter?.id || '')
    const firstVersion = firstChapter ? versions.find((item) => item.chapter_id === firstChapter.id) : undefined
    setSelectedVersionId(firstVersion?.id || '')
  }

  const selectSubject = (id: string) => {
    setSelectedSubjectId(id)
    const firstOffering = offerings.find((item) => item.subject_id === id)
    setSelectedOfferingId(firstOffering?.id || '')
    const firstChapter = firstOffering ? chapters.find((item) => item.subject_offering_id === firstOffering.id) : undefined
    setSelectedChapterId(firstChapter?.id || '')
    const firstVersion = firstChapter ? versions.find((item) => item.chapter_id === firstChapter.id) : undefined
    setSelectedVersionId(firstVersion?.id || '')
  }

  const selectOffering = (id: string) => {
    setSelectedOfferingId(id)
    const firstChapter = chapters.find((item) => item.subject_offering_id === id)
    setSelectedChapterId(firstChapter?.id || '')
    const firstVersion = firstChapter ? versions.find((item) => item.chapter_id === firstChapter.id) : undefined
    setSelectedVersionId(firstVersion?.id || '')
  }

  const selectChapter = (id: string) => {
    setSelectedChapterId(id)
    const firstVersion = versions.find((item) => item.chapter_id === id && (!selectedOfferingId || item.subject_offering_id === selectedOfferingId))
    setSelectedVersionId(firstVersion?.id || '')
  }

  if (!can('view_questions')) return <div className="card empty-state">Bạn không có quyền xem ngân hàng đề.</div>

  return <div className="bank-workspace page-stack">
    <section className="card page-intro">
      <div>
        <div className="eyebrow">v25.9.15.9 · Review, chốt Release, lịch sử Quiz</div>
        <h1>Ngân hàng đề</h1>
        <p>Bộ môn → Môn → Phiên bản môn → Bài. Clone version môn chỉ copy bản làm việc; Release vẫn là nút chốt riêng sau khi sửa xong.</p>
      </div>
      <Link className="btn secondary" href="/bank/quiz">Map Open edX & tạo Quiz</Link>
    </section>

    {message ? <div className={classNames('alert', message.toLowerCase().includes('lỗi') || message.toLowerCase().includes('thất bại') ? 'danger' : 'success')}>{message}</div> : null}

    <section className="metrics-grid compact-summary">
      <div className="metric-card"><small>Bộ môn</small><b>{summary.departments}</b></div>
      <div className="metric-card"><small>Môn</small><b>{summary.subjects}</b></div>
      <div className="metric-card"><small>Phiên bản môn</small><b>{summary.subject_offerings || 0}</b></div>
      <div className="metric-card"><small>Bài</small><b>{summary.chapters}</b></div>
      <div className="metric-card"><small>Câu ngân hàng</small><b>{summary.bank_questions}</b></div>
      <div className="metric-card"><small>Release public</small><b>{summary.published_releases}/{summary.releases}</b></div>
    </section>

    <section className="bank-browser-grid">
      <div className="card bank-column">
        <div className="section-head"><div><h2>Bộ môn</h2><small>Click bộ môn để xem môn bên trong.</small></div></div>
        <div className="mini-form">
          <input className="input" placeholder="Code: DESIGN" value={deptCode} onChange={(event) => setDeptCode(event.target.value)} />
          <input className="input" placeholder="Tên bộ môn" value={deptName} onChange={(event) => setDeptName(event.target.value)} />
          <button className="btn" disabled={busy || !can('manage_settings')} onClick={() => run(() => createDepartment(headers, { code: deptCode, name: deptName }), 'Đã thêm bộ môn')}>+ Thêm bộ môn</button>
        </div>
        <div className="entity-list">
          {departments.map((item) => <button key={item.id} className={classNames('entity-card', selectedDepartmentId === item.id && 'active')} onClick={() => selectDepartment(item.id)}>
            <b>{item.name}</b><small>{item.code}</small>
          </button>)}
        </div>
      </div>

      <div className="card bank-column">
        <div className="section-head"><div><h2>Môn</h2><small>{selectedDepartment ? `Trong ${selectedDepartment.name}` : 'Chọn bộ môn trước.'}</small></div></div>
        <div className="mini-form">
          <input className="input" placeholder="Mã môn: WEB107" value={subjectCode} onChange={(event) => setSubjectCode(event.target.value)} />
          <input className="input" placeholder="Tên môn" value={subjectName} onChange={(event) => setSubjectName(event.target.value)} />
          <button className="btn" disabled={busy || !selectedDepartmentId || !can('manage_settings')} onClick={() => run(() => createSubject(headers, { department_id: selectedDepartmentId, code: subjectCode, name: subjectName }), 'Đã thêm môn')}>+ Thêm môn</button>
        </div>
        <div className="entity-list">
          {subjectsOfDepartment.map((item) => <button key={item.id} className={classNames('entity-card', selectedSubjectId === item.id && 'active')} onClick={() => selectSubject(item.id)}>
            <b>{item.code}</b><small>{item.name}</small>
          </button>)}
          {!subjectsOfDepartment.length ? <div className="empty-state">Chưa có môn trong bộ môn này.</div> : null}
        </div>
      </div>

      <div className="card bank-column wide">
        <div className="section-head"><div><h2>Phiên bản môn</h2><small>{selectedSubject ? `Ví dụ ${selectedSubject.code}_SP25, ${selectedSubject.code}_SU25, ${selectedSubject.code}_FA25` : 'Chọn môn trước.'}</small></div></div>
        <div className="mini-form version-form">
          <select className="input" value={term} onChange={(event) => setTerm(event.target.value)}>{TERMS.map(([value, label]) => <option key={value} value={value}>{value} · {label}</option>)}</select>
          <select className="input" value={cloneFromOfferingId} onChange={(event) => setCloneFromOfferingId(event.target.value)}>
            <option value="">Tạo version trống</option>
            {versionsOfSubject.map((item) => <option key={item.id} value={item.id}>Clone từ {item.code}</option>)}
          </select>
          <button className="btn" disabled={busy || !selectedSubjectId || !can('manage_settings')} onClick={() => run(() => createSubjectOffering(headers, {
            subject_id: selectedSubjectId,
            term,
            clone_from_offering_id: cloneFromOfferingId || null,
          }), cloneFromOfferingId ? 'Đã clone 100% bản làm việc sang version mới. Release chưa tạo; hãy chốt sau khi sửa xong.' : 'Đã tạo phiên bản môn')}>+ Tạo / clone version</button>
          <small className="muted full-row">{cloneFromOfferingId ? 'Clone sẽ copy bài, tài liệu, câu hỏi đã duyệt và nhóm kiến thức sang ID mới. Không clone Release, không publish Open edX, không chạy diff lúc clone.' : 'Tạo version trống nếu kỳ mới chưa muốn lấy dữ liệu từ kỳ cũ.'}</small>
        </div>
        <div className="entity-list horizontal">
          {versionsOfSubject.map((item) => <button key={item.id} className={classNames('entity-card', selectedOfferingId === item.id && 'active')} onClick={() => selectOffering(item.id)}>
            <b>{item.code}</b><small>{item.name || item.term || item.version_code}</small>
          </button>)}
          {!versionsOfSubject.length ? <div className="empty-state">Chưa có version môn. Có thể tạo mới hoặc clone từ kỳ trước.</div> : null}
        </div>
      </div>
    </section>

    {selectedOffering ? <section className="card">
      <div className="section-head">
        <div><h2>{selectedOffering.code} · Bài/Chapter</h2><small>Click vào bài để mở workspace tài liệu, câu hỏi và release.</small></div>
        <div className="inline-form compact-form no-margin">
          <input className="input mini-input" placeholder="Số bài" value={chapterNo} onChange={(event) => setChapterNo(event.target.value)} />
          <input className="input" placeholder="Tên bài/chapter" value={chapterTitle} onChange={(event) => setChapterTitle(event.target.value)} />
          <button className="btn" disabled={busy || !selectedSubjectId || !selectedOfferingId || !can('edit_questions')} onClick={() => run(() => createSubjectChapter(headers, {
            subject_id: selectedSubjectId,
            subject_offering_id: selectedOfferingId,
            chapter_no: Number(chapterNo || 1),
            sort_order: Number(chapterNo || 1),
            title: chapterTitle,
          }), 'Đã thêm chapter')}>+ Thêm chapter</button>
        </div>
      </div>
      <div className="entity-list horizontal">
        {chaptersOfVersion.map((item) => <button key={item.id} className={classNames('entity-card', selectedChapterId === item.id && 'active')} onClick={() => selectChapter(item.id)}>
          <b>Bài {item.chapter_no}</b><small>{item.title}</small>
        </button>)}
        {!chaptersOfVersion.length ? <div className="empty-state">Version này chưa có bài nào.</div> : null}
      </div>
    </section> : null}

    {selectedChapter ? <section className="card chapter-workspace">
      <div className="section-head">
        <div>
          <div className="eyebrow">{selectedSubject?.code} / {selectedOffering?.code}</div>
          <h2>Bài {selectedChapter.chapter_no}: {selectedChapter.title}</h2>
          <small>Workspace chính: gắn tài liệu, tạo câu hỏi, duyệt câu hỏi và publish bộ đề.</small>
        </div>
        <Link className="btn secondary" href="/bank/quiz">Tạo Quiz ở trang Open edX</Link>
      </div>

      <div className="metrics-grid compact-summary">
        <div className="metric-card"><small>Tài liệu chunks</small><b>{materialChunks.length}</b></div>
        <div className="metric-card"><small>Tổng câu</small><b>{stats.total}</b></div>
        <div className="metric-card"><small>Đã duyệt</small><b>{stats.approved}</b></div>
        <div className="metric-card"><small>Chờ duyệt</small><b>{stats.pending}</b></div>
        <div className="metric-card"><small>Nhóm kiến thức</small><b>{stats.families}</b></div>
        <div className="metric-card"><small>Release public</small><b>{publishedReleases.length}</b></div>
      </div>

      {selectedVersion && isClonedBankVersion ? <div className={classNames('alert', diffRequired ? 'warning' : 'success')}>
        {diffRequired ? <>Tài liệu của version clone này đã thay đổi. Hãy bấm kiểm tra khác biệt trước khi chốt Release. <button className="btn small secondary" disabled={busy || !diffBaseBankVersionId} onClick={runDiffPreview}>Kiểm tra thay đổi</button> <button className="btn small" disabled={busy || !can('review_questions')} onClick={() => run(() => markBankDiffResolved(headers, selectedVersionId, { note: 'Đã kiểm tra và xử lý thay đổi tài liệu' }), 'Đã đánh dấu tài liệu đã xử lý')}>Đánh dấu đã xử lý</button></> : <>Version này đang là bản clone sạch từ kỳ trước. Chưa cần kiểm tra khác biệt. Khi upload tài liệu mới, hệ thống sẽ tự đánh dấu cần kiểm tra.</>}
      </div> : null}

      <div className="workspace-grid">
        <div className="workspace-panel">
          <h3>1. Bank Version của bài</h3>
          <p className="muted">Mỗi bài có thể có v1.0, v2.0... để giữ lịch sử thay đổi tài liệu/câu hỏi.</p>
          <div className="inline-form compact-form no-margin">
            <input className="input mini-input" value={bankVersionCode} onChange={(event) => setBankVersionCode(event.target.value)} placeholder="v1.0" />
            <input className="input" value={bankVersionNote} onChange={(event) => setBankVersionNote(event.target.value)} placeholder="Ghi chú" />
            <button className="btn" disabled={busy || !can('edit_questions')} onClick={() => run(() => createBankVersion(headers, {
              subject_id: selectedSubjectId,
              subject_offering_id: selectedOfferingId,
              chapter_id: selectedChapterId,
              version_code: bankVersionCode,
              title: '',
              change_note: bankVersionNote,
            }), 'Đã tạo Bank Version')}>+ Tạo Bank Version</button>
          </div>
          <div className="entity-list horizontal compact-list">
            {bankVersionsOfChapter.map((item) => <button key={item.id} className={classNames('entity-card', selectedVersionId === item.id && 'active')} onClick={() => setSelectedVersionId(item.id)}>
              <b>{item.version_code}</b><small>{item.title || `${selectedOffering?.code || ''} · Bài ${selectedChapter.chapter_no}`}</small>
            </button>)}
          </div>
        </div>

        <div className="workspace-panel">
          <h3>2. Gắn tài liệu và sinh câu hỏi</h3>
          <p className="muted">Chọn Bank Version, upload tài liệu, rồi generate câu hỏi vào đúng version đó.</p>
          <select className="input" value={selectedVersionId} onChange={(event) => setSelectedVersionId(event.target.value)}>
            <option value="">Chọn Bank Version</option>
            {bankVersionsOfChapter.map((item) => <option key={item.id} value={item.id}>{item.version_code} · {item.title || selectedChapter.title}</option>)}
          </select>
          <div className="inline-form compact-form no-margin">
            <input className="input" type="file" onChange={(event) => setSelectedFile(event.target.files?.[0] || null)} />
            <button className="btn" disabled={busy || !selectedVersionId || !selectedFile || !can('edit_questions')} onClick={() => run(() => uploadBankMaterial(headers, selectedVersionId, selectedFile as File, { title: selectedFile?.name }), 'Đã upload tài liệu vào Bank Version. Nếu đây là version clone, hệ thống đã đánh dấu cần kiểm tra khác biệt.')}>Upload tài liệu</button>
          </div>
          <div className="inline-form compact-form no-margin">
            <input className="input mini-input" value={generateCount} onChange={(event) => setGenerateCount(event.target.value)} placeholder="Số câu" />
            <input className="input mini-input" value={difficultyEasy} onChange={(event) => setDifficultyEasy(event.target.value)} placeholder="Easy %" />
            <input className="input mini-input" value={difficultyMedium} onChange={(event) => setDifficultyMedium(event.target.value)} placeholder="Medium %" />
            <input className="input mini-input" value={difficultyHard} onChange={(event) => setDifficultyHard(event.target.value)} placeholder="Hard %" />
            <button className="btn" disabled={busy || !selectedVersionId || !can('generate_questions')} onClick={() => run(() => generateFromBankVersion(headers, selectedVersionId, {
              question_count: Number(generateCount || 5),
              difficulty_easy: Number(difficultyEasy || 50),
              difficulty_medium: Number(difficultyMedium || 30),
              difficulty_hard: Number(difficultyHard || 20),
              provider: 'openai',
              approve_after_generate: false,
            }), 'Đã generate câu hỏi vào Bank Version')}>Tạo câu hỏi</button>
          </div>
        </div>
      </div>

      <div className="workspace-grid">
        <div className="workspace-panel">
          <h3>3. Chốt bộ đề đã duyệt</h3>
          <p className="muted">Release là bước chốt tay sau cùng. Chỉ tạo sau khi đã sửa tài liệu, kiểm tra thay đổi nếu có, và duyệt xong câu hỏi.</p>
          {releaseReadiness ? <div className={classNames('alert', releaseReadiness.can_create_release ? 'success' : 'warning')}>
            <b>{releaseReadiness.message}</b>
            <div className="mini-readiness">
              <span>Đã duyệt: {releaseReadiness.stats?.approved_count || 0}</span>
              <span>Chờ duyệt: {releaseReadiness.stats?.pending_review_count || 0}</span>
              <span>Lỗi nháp: {releaseReadiness.stats?.draft_error_count || 0}</span>
            </div>
            {releaseReadiness.recommended_actions?.length ? <ul>{releaseReadiness.recommended_actions.map((item) => <li key={item}>{item}</li>)}</ul> : null}
          </div> : null}
          <div className="inline-form compact-form no-margin">
            <input className="input" value={releaseCode} onChange={(event) => setReleaseCode(event.target.value)} placeholder={`${selectedSubject?.code || 'MON'}-${selectedOffering?.term || 'SU26'}-B${selectedChapter.chapter_no}-${selectedVersion?.version_code || 'v1.0'}`} />
            <button className="btn" disabled={busy || !selectedVersionId || !releaseReadiness?.can_create_release || !can('publish_questions')} onClick={() => run(() => createBankRelease(headers, { bank_version_id: selectedVersionId, release_code: releaseCode || undefined, include_approved_questions: true }), 'Đã tạo Release từ câu đã duyệt')}>Chốt bộ đề</button>
          </div>
          <div className="table-wrap"><table className="data-table compact-table"><thead><tr><th>Release</th><th>Trạng thái</th><th>Câu</th><th>Library</th><th></th></tr></thead><tbody>{releasesOfVersion.map((item) => <tr key={item.id}><td><b>{item.release_code}</b><small>{item.title}</small></td><td><span className={classNames('status', item.status === 'published' ? 'success' : 'pending')}>{item.status}</span></td><td>{item.approved_question_count}</td><td><code>{item.openedx_library_key || '—'}</code></td><td><button className="btn small secondary" disabled={busy || item.status === 'published' || !can('publish_questions')} onClick={() => run(() => publishBankRelease(headers, item.id, {}), 'Đã publish Release sang Open edX Library')}>Publish Library</button></td></tr>)}</tbody></table></div>
        </div>

        <div className="workspace-panel">
          <h3>4. Tài liệu đã gắn</h3>
          <p className="muted">{materialChunks.length} chunk đang được dùng để sinh câu hỏi cho Bank Version này.</p>
          <div className="chunk-list small-chunk-list">
            {materialChunks.slice(0, 6).map((chunk) => <div key={chunk.id} className="chunk-card readonly"><div className="chunk-title">#{chunk.chunk_index} · {chunk.token_count} tokens</div><p>{chunk.content.slice(0, 220)}...</p></div>)}
            {!materialChunks.length ? <div className="empty-state">Chưa có tài liệu/chunk.</div> : null}
          </div>
        </div>
      </div>

      <div className="workspace-panel full">
        <div className="section-head"><div><h3>Duyệt câu hỏi</h3><small>Giữ giao diện đơn giản: đọc câu hỏi, bấm Duyệt hoặc Bỏ. Hệ thống tự dùng dữ liệu kỹ thuật phía sau.</small></div><button className="btn small" disabled={busy || !selectedVersionId || !stats.pending || !can('review_questions')} onClick={() => run(() => bulkReviewBankQuestions(headers, selectedVersionId, { action: 'approve', approve_all_pending: true, note: 'Duyệt nhanh toàn bộ câu đang chờ' }), 'Đã duyệt toàn bộ câu đang chờ')}>Duyệt hết câu chờ</button></div>
        <div className="table-wrap"><table className="data-table compact-table"><thead><tr><th>Câu hỏi</th><th>Độ khó</th><th>Trạng thái</th><th>Hành động</th></tr></thead><tbody>{bankQuestions.slice(0, 60).map((item) => <tr key={item.id}><td><b>{item.question_text}</b><small>{item.correct_answer ? `Đáp án: ${item.correct_answer}` : ''}</small></td><td>{item.difficulty}</td><td><span className={classNames('status', item.status === 'approved' || item.status === 'published' ? 'success' : item.status === 'rejected' ? 'danger' : 'pending')}>{item.status === 'pending_review' ? 'Chờ duyệt' : item.status === 'approved' ? 'Đã duyệt' : item.status === 'rejected' ? 'Đã bỏ' : item.status}</span></td><td><div className="button-row no-margin">{item.status !== 'approved' && item.status !== 'published' ? <button className="btn small" disabled={busy || !can('review_questions')} onClick={() => run(() => reviewBankQuestion(headers, selectedVersionId, item.id, { action: 'approve', note: 'Giữ câu hỏi này' }), 'Đã duyệt câu hỏi')}>Duyệt</button> : null}{item.status !== 'rejected' && item.status !== 'published' ? <button className="btn small secondary" disabled={busy || !can('review_questions')} onClick={() => run(() => reviewBankQuestion(headers, selectedVersionId, item.id, { action: 'reject', note: 'Không dùng câu này trong version hiện tại' }), 'Đã bỏ câu hỏi khỏi bộ đang chốt')}>Bỏ</button> : null}</div></td></tr>)}</tbody></table></div>
        {!bankQuestions.length ? <div className="empty-state">Chưa có câu hỏi trong Bank Version này.</div> : null}
      </div>
    </section> : null}
  </div>
}
