'use client'

import { useEffect, useMemo, useState } from 'react'
import { useAppContext } from '../../context/AppContext'
import {
  BankRelease,
  BankSummary,
  MappingValidation,
  BankVersion,
  MaterialChunk,
  BankVersionQuestion,
  BankVersionDiffPreview,
  Department,
  EdxCourseMapping,
  Subject,
  SubjectOffering,
  SubjectChapter,
} from '../../types'
import {
  createBankRelease,
  publishBankRelease,
  createBankVersion,
  createCourseMapping,
  validateCourseMapping,
  createDepartment,
  createSubject,
  createSubjectOffering,
  createSubjectChapter,
  getBankReleases,
  getBankSummary,
  getBankVersions,
  getBankMaterialChunks,
  getBankVersionQuestions,
  getCourseMappings,
  getDepartments,
  getSubjectChapters,
  getSubjects,
  getSubjectOfferings,
  uploadBankMaterial,
  generateFromBankVersion,
  validateCourseChapterMapping,
  previewBankVersionDiff,
  carryOverBankQuestions,
  retireBankQuestions,
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
  const [mappings, setMappings] = useState<EdxCourseMapping[]>([])
  const [materialChunks, setMaterialChunks] = useState<MaterialChunk[]>([])
  const [bankQuestions, setBankQuestions] = useState<BankVersionQuestion[]>([])
  const [diffPreview, setDiffPreview] = useState<BankVersionDiffPreview | null>(null)
  const [selectedDepartmentId, setSelectedDepartmentId] = useState('')
  const [selectedSubjectId, setSelectedSubjectId] = useState('')
  const [selectedOfferingId, setSelectedOfferingId] = useState('')
  const [selectedChapterId, setSelectedChapterId] = useState('')
  const [selectedVersionId, setSelectedVersionId] = useState('')
  const [message, setMessage] = useState('')
  const [mappingValidation, setMappingValidation] = useState<MappingValidation | null>(null)
  const [chapterValidation, setChapterValidation] = useState<MappingValidation | null>(null)
  const [busy, setBusy] = useState(false)

  const refresh = async () => {
    const [nextSummary, nextDepartments, nextSubjects, nextOfferings, nextChapters, nextVersions, nextReleases, nextMappings] = await Promise.all([
      getBankSummary(headers),
      getDepartments(headers),
      getSubjects(headers),
      getSubjectOfferings(headers),
      getSubjectChapters(headers),
      getBankVersions(headers),
      getBankReleases(headers),
      getCourseMappings(headers),
    ])
    setSummary(nextSummary)
    setDepartments(nextDepartments)
    setSubjects(nextSubjects)
    setOfferings(nextOfferings)
    setChapters(nextChapters)
    setVersions(nextVersions)
    setReleases(nextReleases)
    setMappings(nextMappings)
    if (!selectedDepartmentId && nextDepartments[0]) setSelectedDepartmentId(nextDepartments[0].id)
    if (!selectedSubjectId && nextSubjects[0]) setSelectedSubjectId(nextSubjects[0].id)
    if (!selectedOfferingId && nextOfferings[0]) setSelectedOfferingId(nextOfferings[0].id)
    if (!selectedChapterId && nextChapters[0]) setSelectedChapterId(nextChapters[0].id)
    if (!selectedVersionId && nextVersions[0]) setSelectedVersionId(nextVersions[0].id)
  }

  useEffect(() => {
    refresh().catch((error) => setMessage(error instanceof Error ? error.message : 'Không tải được ngân hàng đề'))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    if (!selectedVersionId) return
    Promise.all([
      getBankMaterialChunks(headers, selectedVersionId).catch(() => []),
      getBankVersionQuestions(headers, selectedVersionId).catch(() => []),
    ]).then(([chunks, questions]) => {
      setMaterialChunks(chunks)
      setBankQuestions(questions)
    }).catch(() => null)
  }, [headers, selectedVersionId])

  if (!can('view_questions')) return <div className="card empty-state">Bạn không có quyền xem ngân hàng đề.</div>

  const run = async (work: () => Promise<unknown>, ok: string) => {
    setBusy(true)
    setMessage('')
    try {
      await work()
      await refresh()
      if (selectedVersionId) {
        const [chunks, questions] = await Promise.all([
          getBankMaterialChunks(headers, selectedVersionId).catch(() => []),
          getBankVersionQuestions(headers, selectedVersionId).catch(() => []),
        ])
        setMaterialChunks(chunks)
        setBankQuestions(questions)
      }
      setMessage(ok)
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Thao tác thất bại')
    } finally {
      setBusy(false)
    }
  }

  const selectedSubject = subjects.find((item) => item.id === selectedSubjectId)
  const selectedOffering = offerings.find((item) => item.id === selectedOfferingId)
  const selectedChapter = chapters.find((item) => item.id === selectedChapterId)
  const selectedVersion = versions.find((item) => item.id === selectedVersionId)

  return <div className="bank-page">
    <section className="card page-intro">
      <div className="eyebrow">v25.9.15.3.4 · Phiên bản môn SP/SU/FA · Clone version</div>
      <h1>Ngân hàng đề theo phiên bản</h1>
      <p>Chuẩn mới: tạo Bộ môn → Môn → Phiên bản môn (SP25/SU26/FA27) → Bài/Chapter → Bank Release. Mỗi Bank Release sinh đúng một Open edX Library, sau đó nhiều course Open edX có thể map vào release đó.</p>
      {message ? <div className={message.includes('thất bại') || message.includes('lỗi') ? 'alert danger' : 'alert success'}>{message}</div> : null}
    </section>

    <section className="metrics-grid compact-summary">
      <div className="metric-card"><small>Bộ môn</small><b>{summary.departments}</b></div>
      <div className="metric-card"><small>Môn</small><b>{summary.subjects}</b></div>
      <div className="metric-card"><small>Phiên bản môn / Bài</small><b>{summary.subject_offerings || 0}/{summary.chapters}</b></div>
      <div className="metric-card"><small>Release đã publish</small><b>{summary.published_releases}/{summary.releases}</b></div>
      <div className="metric-card"><small>Tài liệu/chunk</small><b>{summary.material_versions}/{summary.material_chunks}</b></div>
      <div className="metric-card"><small>Câu ngân hàng</small><b>{summary.bank_questions}</b></div>
      <div className="metric-card"><small>Clone dùng lại / Loại khỏi version</small><b>{summary.carry_over_questions || 0}/{summary.retired_questions || 0}</b></div>
    </section>

    <section className="card">
      <h2>1. Khai báo Bộ môn → Môn → Phiên bản môn → Bài</h2>
      <div className="inline-form compact-form">
        <label>Bộ môn code<input id="dept-code" className="input" placeholder="DESIGN" /></label>
        <label>Tên bộ môn<input id="dept-name" className="input" placeholder="Bộ môn Thiết kế" /></label>
        <button className="btn" disabled={busy || !can('manage_settings')} onClick={() => {
          const code = (document.getElementById('dept-code') as HTMLInputElement)?.value || ''
          const name = (document.getElementById('dept-name') as HTMLInputElement)?.value || ''
          run(() => createDepartment(headers, { code, name }), 'Đã tạo bộ môn')
        }}>Tạo bộ môn</button>
      </div>
      <div className="inline-form compact-form">
        <label>Chọn bộ môn<select className="input" value={selectedDepartmentId} onChange={(event) => setSelectedDepartmentId(event.target.value)}>{departments.map((item) => <option key={item.id} value={item.id}>{item.code} · {item.name}</option>)}</select></label>
        <label>Mã môn<input id="subject-code" className="input" placeholder="DOM123" /></label>
        <label>Tên môn<input id="subject-name" className="input" placeholder="Thiết kế nhận diện thương hiệu" /></label>
        <button className="btn" disabled={busy || !selectedDepartmentId || !can('manage_settings')} onClick={() => {
          const code = (document.getElementById('subject-code') as HTMLInputElement)?.value || ''
          const name = (document.getElementById('subject-name') as HTMLInputElement)?.value || ''
          run(() => createSubject(headers, { department_id: selectedDepartmentId, code, name }), 'Đã tạo môn học')
        }}>Tạo môn</button>
      </div>
      <div className="inline-form compact-form">
        <label>Chọn môn<select className="input" value={selectedSubjectId} onChange={(event) => setSelectedSubjectId(event.target.value)}>{subjects.map((item) => <option key={item.id} value={item.id}>{item.code} · {item.name}</option>)}</select></label>
        <label>Kỳ<select id="offering-term" className="input" defaultValue="SP25"><option value="SP25">SP25 · Spring/Xuân 2025</option><option value="SU25">SU25 · Summer/Hè 2025</option><option value="FA25">FA25 · Fall/Đông 2025</option><option value="SP26">SP26 · Spring/Xuân 2026</option><option value="SU26">SU26 · Summer/Hè 2026</option><option value="FA26">FA26 · Fall/Đông 2026</option><option value="SP27">SP27 · Spring/Xuân 2027</option><option value="SU27">SU27 · Summer/Hè 2027</option><option value="FA27">FA27 · Fall/Đông 2027</option></select></label>
        <label>Clone từ phiên bản môn<select id="clone-offering-id" className="input" defaultValue=""><option value="">Tạo version trống</option>{offerings.filter((item) => item.subject_id === selectedSubjectId).map((item) => <option key={item.id} value={item.id}>{item.code}</option>)}</select></label>
        <button className="btn" disabled={busy || !selectedSubjectId || !can('manage_settings')} onClick={() => {
          const term = (document.getElementById('offering-term') as HTMLSelectElement)?.value || 'SP25'
          const clone_from_offering_id = (document.getElementById('clone-offering-id') as HTMLSelectElement)?.value || null
          run(() => createSubjectOffering(headers, { subject_id: selectedSubjectId, term, clone_from_offering_id, clone_chapters: true, clone_materials: true, clone_questions: true }), clone_from_offering_id ? 'Đã clone phiên bản môn thành bản ghi mới' : 'Đã tạo phiên bản môn')
        }}>Tạo / clone phiên bản môn</button>
      </div>
      <div className="inline-form compact-form">
        <label>Chọn phiên bản môn<select className="input" value={selectedOfferingId} onChange={(event) => setSelectedOfferingId(event.target.value)}>{offerings.filter((item) => item.subject_id === selectedSubjectId).map((item) => <option key={item.id} value={item.id}>{item.code} · {item.name}</option>)}</select></label>
        <label>Số bài<input id="chapter-no" className="input" type="number" defaultValue={1} /></label>
        <label>Tên bài/chapter<input id="chapter-title" className="input" placeholder="Bài 1: Tổng quan" /></label>
        <button className="btn" disabled={busy || !selectedSubjectId || !can('manage_settings')} onClick={() => {
          const chapter_no = Number((document.getElementById('chapter-no') as HTMLInputElement)?.value || '1')
          const title = (document.getElementById('chapter-title') as HTMLInputElement)?.value || ''
          run(() => createSubjectChapter(headers, { subject_id: selectedSubjectId, subject_offering_id: selectedOfferingId || null, chapter_no, title, sort_order: chapter_no }), 'Đã tạo bài/chapter')
        }}>Tạo chapter</button>
      </div>
    </section>

    <section className="card">
      <h2>2. Tạo phiên bản ngân hàng đề</h2>
      <p className="muted">Phiên bản môn chính là version triển khai của môn. Mỗi version có các bài riêng và câu hỏi riêng; câu dùng lại được sẽ clone sang version mới và approved luôn.</p>
      <div className="inline-form compact-form">
        <label>Bài/Chapter<select className="input" value={selectedChapterId} onChange={(event) => setSelectedChapterId(event.target.value)}>{chapters.map((item) => <option key={item.id} value={item.id}>{item.chapter_no}. {item.title}</option>)}</select></label>
        <label>Version<input id="version-code" className="input" placeholder="v1.0" defaultValue="v1.0" /></label>
        <label>Ghi chú thay đổi<input id="change-note" className="input" placeholder="Tài liệu gốc ban đầu" /></label>
        <button className="btn" disabled={busy || !selectedSubjectId || !selectedChapterId || !can('edit_questions')} onClick={() => {
          const version_code = (document.getElementById('version-code') as HTMLInputElement)?.value || 'v1.0'
          const change_note = (document.getElementById('change-note') as HTMLInputElement)?.value || ''
          run(() => createBankVersion(headers, { subject_id: selectedSubjectId, subject_offering_id: selectedOfferingId || selectedChapter?.subject_offering_id || null, chapter_id: selectedChapterId, version_code, title: `${selectedSubject?.code || ''} - ${selectedOffering?.term || ''} - ${selectedChapter?.title || ''} - ${version_code}`, change_note }), 'Đã tạo Bank Version')
        }}>Tạo Bank Version</button>
      </div>
    </section>

    <section className="card">
      <h2>3. Upload tài liệu và sinh câu hỏi</h2>
      <p className="muted">Chọn Bank Version, upload PDF/DOCX/PPTX/XLSX/CSV/TXT. AI Server tách chunk, sau đó generate câu hỏi vào chính Bank Version này. Câu hỏi sinh ra vẫn cần review trước khi tạo Release.</p>
      <div className="inline-form compact-form">
        <label>Bank Version<select className="input" value={selectedVersionId} onChange={(event) => setSelectedVersionId(event.target.value)}>{versions.map((item) => <option key={item.id} value={item.id}>{item.version_code} · {item.title || item.id}</option>)}</select></label>
        <label>Tài liệu<input id="bank-material-file" className="input" type="file" /></label>
        <button className="btn" disabled={busy || !selectedVersionId || !can('edit_questions')} onClick={() => {
          const input = document.getElementById('bank-material-file') as HTMLInputElement
          const file = input?.files?.[0]
          if (!file) { setMessage('Chưa chọn file tài liệu'); return }
          run(() => uploadBankMaterial(authHeaders(false), selectedVersionId, file, { title: file.name, change_type: 'initial', replace_existing: false }), 'Đã upload và tách tài liệu vào Bank Version')
        }}>Upload tài liệu</button>
      </div>
      <div className="inline-form compact-form">
        <label>Số câu<input id="bank-generate-count" className="input" type="number" defaultValue={10} min={1} max={200} /></label>
        <label>Easy %<input id="bank-easy" className="input" type="number" defaultValue={50} /></label>
        <label>Medium %<input id="bank-medium" className="input" type="number" defaultValue={30} /></label>
        <label>Hard %<input id="bank-hard" className="input" type="number" defaultValue={20} /></label>
        <button className="btn primary" disabled={busy || !selectedVersionId || materialChunks.length === 0 || !can('generate_questions')} onClick={() => {
          const question_count = Number((document.getElementById('bank-generate-count') as HTMLInputElement)?.value || '10')
          const difficulty_easy = Number((document.getElementById('bank-easy') as HTMLInputElement)?.value || '50')
          const difficulty_medium = Number((document.getElementById('bank-medium') as HTMLInputElement)?.value || '30')
          const difficulty_hard = Number((document.getElementById('bank-hard') as HTMLInputElement)?.value || '20')
          run(() => generateFromBankVersion(headers, selectedVersionId, { question_count, difficulty_easy, difficulty_medium, difficulty_hard, provider: 'openai', approve_after_generate: false }), 'Đã tạo câu hỏi từ Bank Version, vui lòng review trước khi tạo Release')
        }}>Generate từ Bank Version</button>
      </div>
      <div className="mini-status-grid">
        <div><b>{selectedVersion?.version_code || '-'}</b><small>Version đang chọn</small></div>
        <div><b>{materialChunks.length}</b><small>Chunk tài liệu</small></div>
        <div><b>{materialChunks.reduce((sum, item) => sum + (item.token_count || 0), 0)}</b><small>Tokens đã index</small></div>
        <div><b>{bankQuestions.length}</b><small>Câu trong version</small></div>
      </div>
      {bankQuestions.length ? <div className="compact-table"><table><thead><tr><th>Trạng thái</th><th>Độ khó</th><th>Concept/Family</th><th>Câu hỏi mới nhất</th></tr></thead><tbody>{bankQuestions.slice(0, 5).map((item) => <tr key={item.id}><td>{item.status}</td><td>{item.difficulty}</td><td><small>{item.concept_version_id || item.question_family_id || '—'}</small></td><td>{item.question_text}</td></tr>)}</tbody></table></div> : <p className="muted">Chưa có câu hỏi trong Bank Version này.</p>}
    </section>

    <section className="card">
      <h2>4. So sánh version và kế thừa câu hỏi</h2>
      <p className="muted">Dùng khi tài liệu thay đổi: so sánh version cũ và version mới. Câu còn dùng được sẽ clone sang version mới và approved luôn; câu không còn phù hợp thì không clone vào version mới.</p>
      <div className="inline-form compact-form">
        <label>Version cũ<select id="base-version-id" className="input" defaultValue=""> <option value="">Chọn version cũ</option>{versions.filter((item) => item.id !== selectedVersionId).map((item) => <option key={item.id} value={item.id}>{item.version_code} · {item.title || item.id}</option>)}</select></label>
        <label>Version mới<select className="input" value={selectedVersionId} onChange={(event) => setSelectedVersionId(event.target.value)}>{versions.map((item) => <option key={item.id} value={item.id}>{item.version_code} · {item.title || item.id}</option>)}</select></label>
        <button className="btn" disabled={busy || !selectedVersionId || !can('view_questions')} onClick={() => {
          const base_bank_version_id = (document.getElementById('base-version-id') as HTMLSelectElement)?.value || undefined
          if (!base_bank_version_id) { setMessage('Chưa chọn version cũ để so sánh'); return }
          run(async () => { const result = await previewBankVersionDiff(headers, selectedVersionId, { base_bank_version_id, persist: true }); setDiffPreview(result) }, 'Đã so sánh version ngân hàng đề')
        }}>So sánh version</button>
      </div>
      {diffPreview ? <div className="mini-status-grid">
        <div><b>{Math.round((diffPreview.summary.material_similarity || 0) * 100)}%</b><small>Độ giống tài liệu</small></div>
        <div><b>{diffPreview.summary.carry_over_candidate_count}</b><small>Câu có thể carry-over</small></div>
        <div><b>{diffPreview.summary.retire_candidate_count}</b><small>Câu không đưa vào version mới</small></div>
        <div><b>{diffPreview.summary.review_candidate_count}</b><small>Phần cần sinh/review mới</small></div>
        <div><b>{diffPreview.summary.new_concept_count}</b><small>Concept mới</small></div>
        <div><b>{diffPreview.summary.removed_concept_count}</b><small>Concept bị bỏ</small></div>
      </div> : <p className="muted">Chưa có kết quả so sánh version.</p>}
      {diffPreview ? <div className="inline-form compact-form">
        <button className="btn primary" disabled={busy || !diffPreview.carry_over_candidates.length || !can('edit_questions')} onClick={() => run(() => carryOverBankQuestions(headers, selectedVersionId, { base_bank_version_id: diffPreview.summary.from_bank_version_id, question_ids: diffPreview.carry_over_candidates, require_review: false, diff_id: diffPreview.diff_id || null }), 'Đã clone câu còn dùng được sang version mới và approved luôn')}>Clone câu dùng lại được</button>
        <button className="btn danger" disabled={busy || !diffPreview.retire_candidates.length || !can('review_questions')} onClick={() => run(() => retireBankQuestions(headers, diffPreview.summary.to_bank_version_id, { question_ids: diffPreview.retire_candidates, reason: `Không clone vào ${diffPreview.summary.to_version_code} vì không còn phù hợp` }), 'Đã ghi nhận các câu không clone vào version mới; version cũ giữ nguyên')}>Không clone câu không còn phù hợp</button>
      </div> : null}
    </section>

    <section className="card">
      <h2>5. Chốt Release và Library</h2>
      <p className="muted">Mỗi Bank Release sẽ có một Open edX Library riêng. Course cũ giữ release cũ, course mới có thể dùng release mới.</p>
      <div className="inline-form compact-form">
        <label>Bank Version<select className="input" value={selectedVersionId} onChange={(event) => setSelectedVersionId(event.target.value)}>{versions.map((item) => <option key={item.id} value={item.id}>{item.version_code} · {item.title || item.id}</option>)}</select></label>
        <label>Release code<input id="release-code" className="input" placeholder="DOM123-B1-v1.0" /></label>
        <button className="btn" disabled={busy || !selectedVersionId || !can('publish_questions')} onClick={() => {
          const release_code = (document.getElementById('release-code') as HTMLInputElement)?.value || undefined
          run(() => createBankRelease(headers, { bank_version_id: selectedVersionId, release_code, include_approved_questions: true }), 'Đã tạo Bank Release')
        }}>Tạo Release</button>
      </div>
      <div className="table-wrap"><table className="data-table compact-table"><thead><tr><th>Release</th><th>Trạng thái</th><th>Câu hỏi</th><th>Open edX Library</th><th></th></tr></thead><tbody>{releases.slice(0, 8).map((item) => <tr key={item.id}><td><b>{item.release_code}</b><small>{item.title}</small></td><td>{item.status}</td><td>{item.approved_question_count} câu · {item.family_count} family</td><td><code>{item.openedx_library_key}</code></td><td><button className="btn secondary" disabled={busy || item.status === 'published' || !can('publish_questions')} onClick={() => run(() => publishBankRelease(headers, item.id, {}), 'Đã publish release sang Open edX Library')}>Publish Library</button></td></tr>)}</tbody></table></div>
    </section>

    <section className="card">
      <h2>6. Map course Open edX vào ngân hàng đề</h2>
      <p className="muted">Luôn bấm kiểm tra trước khi lưu. Hệ thống chặn nếu mã course không khớp mã môn hoặc release/chapter sai.</p>
      <div className="inline-form compact-form">
        <label>Course ID<input id="map-course" className="input" placeholder="course-v1:FPT+DOM123+SU26" /></label>
        <label>Tên course (tuỳ chọn)<input id="map-course-title" className="input" placeholder="Tên khóa học trong Studio" /></label>
        <label>Môn<select className="input" value={selectedSubjectId} onChange={(event) => setSelectedSubjectId(event.target.value)}>{subjects.map((item) => <option key={item.id} value={item.id}>{item.code}</option>)}</select></label>
        <label>Kỳ<input id="map-term" className="input" placeholder="SU26" /></label>
      </div>
      <div className="button-row">
        <button className="btn secondary" disabled={busy || !selectedSubjectId || !can('publish_questions')} onClick={async () => {
          const openedx_course_id = (document.getElementById('map-course') as HTMLInputElement)?.value || ''
          const openedx_course_title = (document.getElementById('map-course-title') as HTMLInputElement)?.value || ''
          const term = (document.getElementById('map-term') as HTMLInputElement)?.value || ''
          setBusy(true)
          try {
            const result = await validateCourseMapping(headers, { openedx_course_id, subject_id: selectedSubjectId, department_id: selectedDepartmentId || null, term, openedx_course_title })
            setMappingValidation(result)
            setMessage(result.message)
          } catch (error) {
            setMessage(error instanceof Error ? error.message : 'Kiểm tra mapping thất bại')
          } finally {
            setBusy(false)
          }
        }}>Kiểm tra mapping</button>
        <button className="btn" disabled={busy || !selectedSubjectId || mappingValidation?.can_create_mapping !== true || mappingValidation?.risk_level === 'high' || !can('publish_questions')} onClick={() => {
          const openedx_course_id = (document.getElementById('map-course') as HTMLInputElement)?.value || ''
          const openedx_course_title = (document.getElementById('map-course-title') as HTMLInputElement)?.value || ''
          const term = (document.getElementById('map-term') as HTMLInputElement)?.value || ''
          run(() => createCourseMapping(headers, { openedx_course_id, subject_id: selectedSubjectId, department_id: selectedDepartmentId || null, term, openedx_course_title, allow_warnings: mappingValidation?.risk_level === 'medium' }), 'Đã map course Open edX vào môn')
        }}>Lưu mapping an toàn</button>
      </div>
      {mappingValidation ? <div className={`alert ${mappingValidation.risk_level === 'high' ? 'danger' : mappingValidation.risk_level === 'medium' ? 'warning' : 'success'}`}>
        <b>{mappingValidation.risk_level === 'low' ? 'An toàn để map' : mappingValidation.risk_level === 'medium' ? 'Có cảnh báo cần kiểm tra' : 'Rủi ro cao, không được map'}</b>
        <ul>{mappingValidation.checks.map((check) => <li key={check.code}>{check.status.toUpperCase()} · {check.message}</li>)}</ul>
      </div> : null}
      <div className="table-wrap"><table className="data-table compact-table"><thead><tr><th>Course</th><th>Subject</th><th>Kỳ</th><th>Validate</th><th>Trạng thái</th></tr></thead><tbody>{mappings.slice(0, 8).map((item) => <tr key={item.id}><td><code>{item.openedx_course_id}</code></td><td>{subjects.find((subject) => subject.id === item.subject_id)?.code || item.subject_id}</td><td>{item.term || '—'}</td><td>{item.validation_status || '—'}</td><td>{item.status}</td></tr>)}</tbody></table></div>
    </section>

    <section className="card">
      <h2>5. Map chapter vào Bank Release</h2>
      <p className="muted">Chỉ map release đã publish. Node Open edX phải thuộc đúng course và khớp bài/chapter.</p>
      <div className="inline-form compact-form">
        <label>Course mapping<select id="chapter-course-mapping" className="input">{mappings.map((item) => <option key={item.id} value={item.id}>{item.openedx_course_id}</option>)}</select></label>
        <label>Chapter ngân hàng<select id="chapter-bank" className="input" value={selectedChapterId} onChange={(event) => setSelectedChapterId(event.target.value)}>{chapters.map((item) => <option key={item.id} value={item.id}>{item.chapter_no}. {item.title}</option>)}</select></label>
        <label>Release<select id="chapter-release" className="input">{releases.map((item) => <option key={item.id} value={item.id}>{item.release_code} · {item.status}</option>)}</select></label>
        <label>Node Open edX<input id="chapter-node" className="input" placeholder="block-v1:...+type@chapter+block@..." /></label>
        <label>Tên node<input id="chapter-node-title" className="input" placeholder="Bài 4 ..." /></label>
      </div>
      <div className="button-row">
        <button className="btn secondary" disabled={busy || !can('publish_questions')} onClick={async () => {
          const course_mapping_id = (document.getElementById('chapter-course-mapping') as HTMLSelectElement)?.value || ''
          const bank_release_id = (document.getElementById('chapter-release') as HTMLSelectElement)?.value || ''
          const openedx_parent_node_id = (document.getElementById('chapter-node') as HTMLInputElement)?.value || ''
          const openedx_node_title = (document.getElementById('chapter-node-title') as HTMLInputElement)?.value || ''
          setBusy(true)
          try {
            const result = await validateCourseChapterMapping(headers, { course_mapping_id, subject_chapter_id: selectedChapterId, bank_release_id, openedx_parent_node_id, openedx_node_title })
            setChapterValidation(result)
            setMessage(result.message)
          } catch (error) {
            setMessage(error instanceof Error ? error.message : 'Kiểm tra chapter mapping thất bại')
          } finally {
            setBusy(false)
          }
        }}>Kiểm tra chapter</button>
        <button className="btn" disabled={busy || chapterValidation?.can_create_mapping !== true || chapterValidation?.risk_level === 'high' || !can('publish_questions')} onClick={() => {
          const course_mapping_id = (document.getElementById('chapter-course-mapping') as HTMLSelectElement)?.value || ''
          const bank_release_id = (document.getElementById('chapter-release') as HTMLSelectElement)?.value || ''
          const openedx_parent_node_id = (document.getElementById('chapter-node') as HTMLInputElement)?.value || ''
          const openedx_node_title = (document.getElementById('chapter-node-title') as HTMLInputElement)?.value || ''
          run(() => createCourseChapterMapping(headers, { course_mapping_id, subject_chapter_id: selectedChapterId, bank_release_id, openedx_parent_node_id, openedx_node_title, allow_warnings: chapterValidation?.risk_level === 'medium' }), 'Đã map chapter vào Bank Release')
        }}>Lưu chapter mapping</button>
      </div>
      {chapterValidation ? <div className={`alert ${chapterValidation.risk_level === 'high' ? 'danger' : chapterValidation.risk_level === 'medium' ? 'warning' : 'success'}`}>
        <b>{chapterValidation.message}</b>
        <ul>{chapterValidation.checks.map((check) => <li key={check.code}>{check.status.toUpperCase()} · {check.message}</li>)}</ul>
      </div> : null}
    </section>
  </div>
}
