'use client'

import { useEffect, useMemo, useState } from 'react'
import { useAppContext } from '../../context/AppContext'
import {
  BankRelease,
  BankSummary,
  BankVersion,
  Department,
  EdxCourseMapping,
  Subject,
  SubjectChapter,
} from '../../types'
import {
  createBankRelease,
  createBankVersion,
  createCourseMapping,
  createDepartment,
  createSubject,
  createSubjectChapter,
  getBankReleases,
  getBankSummary,
  getBankVersions,
  getCourseMappings,
  getDepartments,
  getSubjectChapters,
  getSubjects,
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
}

export default function BankPage() {
  const { authHeaders, can } = useAppContext()
  const headers = useMemo(() => authHeaders(true), [authHeaders])
  const [summary, setSummary] = useState<BankSummary>(emptySummary)
  const [departments, setDepartments] = useState<Department[]>([])
  const [subjects, setSubjects] = useState<Subject[]>([])
  const [chapters, setChapters] = useState<SubjectChapter[]>([])
  const [versions, setVersions] = useState<BankVersion[]>([])
  const [releases, setReleases] = useState<BankRelease[]>([])
  const [mappings, setMappings] = useState<EdxCourseMapping[]>([])
  const [selectedDepartmentId, setSelectedDepartmentId] = useState('')
  const [selectedSubjectId, setSelectedSubjectId] = useState('')
  const [selectedChapterId, setSelectedChapterId] = useState('')
  const [selectedVersionId, setSelectedVersionId] = useState('')
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)

  const refresh = async () => {
    const [nextSummary, nextDepartments, nextSubjects, nextChapters, nextVersions, nextReleases, nextMappings] = await Promise.all([
      getBankSummary(headers),
      getDepartments(headers),
      getSubjects(headers),
      getSubjectChapters(headers),
      getBankVersions(headers),
      getBankReleases(headers),
      getCourseMappings(headers),
    ])
    setSummary(nextSummary)
    setDepartments(nextDepartments)
    setSubjects(nextSubjects)
    setChapters(nextChapters)
    setVersions(nextVersions)
    setReleases(nextReleases)
    setMappings(nextMappings)
    if (!selectedDepartmentId && nextDepartments[0]) setSelectedDepartmentId(nextDepartments[0].id)
    if (!selectedSubjectId && nextSubjects[0]) setSelectedSubjectId(nextSubjects[0].id)
    if (!selectedChapterId && nextChapters[0]) setSelectedChapterId(nextChapters[0].id)
    if (!selectedVersionId && nextVersions[0]) setSelectedVersionId(nextVersions[0].id)
  }

  useEffect(() => {
    refresh().catch((error) => setMessage(error instanceof Error ? error.message : 'Không tải được ngân hàng đề'))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  if (!can('view_questions')) return <div className="card empty-state">Bạn không có quyền xem ngân hàng đề.</div>

  const run = async (work: () => Promise<unknown>, ok: string) => {
    setBusy(true)
    setMessage('')
    try {
      await work()
      await refresh()
      setMessage(ok)
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Thao tác thất bại')
    } finally {
      setBusy(false)
    }
  }

  const selectedSubject = subjects.find((item) => item.id === selectedSubjectId)
  const selectedChapter = chapters.find((item) => item.id === selectedChapterId)

  return <div className="bank-page">
    <section className="card page-intro">
      <div className="eyebrow">v25.9.15.0 · Question Bank First</div>
      <h1>Ngân hàng đề theo phiên bản</h1>
      <p>Chuẩn mới: tạo Bộ môn → Môn → Chapter → Bank Version → Bank Release. Mỗi Bank Release sinh đúng một Open edX Library, sau đó nhiều course Open edX có thể map vào release đó.</p>
      {message ? <div className={message.includes('thất bại') || message.includes('lỗi') ? 'alert danger' : 'alert success'}>{message}</div> : null}
    </section>

    <section className="metrics-grid compact-summary">
      <div className="metric-card"><small>Bộ môn</small><b>{summary.departments}</b></div>
      <div className="metric-card"><small>Môn</small><b>{summary.subjects}</b></div>
      <div className="metric-card"><small>Chapter</small><b>{summary.chapters}</b></div>
      <div className="metric-card"><small>Release đã publish</small><b>{summary.published_releases}/{summary.releases}</b></div>
    </section>

    <section className="card">
      <h2>1. Khai báo chương trình học</h2>
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
        <label>Số bài<input id="chapter-no" className="input" type="number" defaultValue={1} /></label>
        <label>Tên chapter<input id="chapter-title" className="input" placeholder="Bài 1: Tổng quan" /></label>
        <button className="btn" disabled={busy || !selectedSubjectId || !can('manage_settings')} onClick={() => {
          const chapter_no = Number((document.getElementById('chapter-no') as HTMLInputElement)?.value || '1')
          const title = (document.getElementById('chapter-title') as HTMLInputElement)?.value || ''
          run(() => createSubjectChapter(headers, { subject_id: selectedSubjectId, chapter_no, title, sort_order: chapter_no }), 'Đã tạo chapter')
        }}>Tạo chapter</button>
      </div>
    </section>

    <section className="card">
      <h2>2. Tạo phiên bản ngân hàng đề</h2>
      <p className="muted">Tài liệu đổi thì tạo Bank Version mới. Câu hỏi đã duyệt ở release cũ không bị sửa đè.</p>
      <div className="inline-form compact-form">
        <label>Chapter<select className="input" value={selectedChapterId} onChange={(event) => setSelectedChapterId(event.target.value)}>{chapters.map((item) => <option key={item.id} value={item.id}>{item.chapter_no}. {item.title}</option>)}</select></label>
        <label>Version<input id="version-code" className="input" placeholder="v1.0" defaultValue="v1.0" /></label>
        <label>Ghi chú thay đổi<input id="change-note" className="input" placeholder="Tài liệu gốc ban đầu" /></label>
        <button className="btn" disabled={busy || !selectedSubjectId || !selectedChapterId || !can('edit_questions')} onClick={() => {
          const version_code = (document.getElementById('version-code') as HTMLInputElement)?.value || 'v1.0'
          const change_note = (document.getElementById('change-note') as HTMLInputElement)?.value || ''
          run(() => createBankVersion(headers, { subject_id: selectedSubjectId, chapter_id: selectedChapterId, version_code, title: `${selectedSubject?.code || ''} - ${selectedChapter?.title || ''} - ${version_code}`, change_note }), 'Đã tạo Bank Version')
        }}>Tạo Bank Version</button>
      </div>
    </section>

    <section className="card">
      <h2>3. Chốt Release và Library</h2>
      <p className="muted">Mỗi Bank Release sẽ có một Open edX Library riêng. Course cũ giữ release cũ, course mới có thể dùng release mới.</p>
      <div className="inline-form compact-form">
        <label>Bank Version<select className="input" value={selectedVersionId} onChange={(event) => setSelectedVersionId(event.target.value)}>{versions.map((item) => <option key={item.id} value={item.id}>{item.version_code} · {item.title || item.id}</option>)}</select></label>
        <label>Release code<input id="release-code" className="input" placeholder="DOM123-B1-v1.0" /></label>
        <button className="btn" disabled={busy || !selectedVersionId || !can('publish_questions')} onClick={() => {
          const release_code = (document.getElementById('release-code') as HTMLInputElement)?.value || undefined
          run(() => createBankRelease(headers, { bank_version_id: selectedVersionId, release_code, include_approved_questions: true }), 'Đã tạo Bank Release')
        }}>Tạo Release</button>
      </div>
      <div className="table-wrap"><table className="data-table compact-table"><thead><tr><th>Release</th><th>Trạng thái</th><th>Câu hỏi</th><th>Open edX Library</th></tr></thead><tbody>{releases.slice(0, 8).map((item) => <tr key={item.id}><td><b>{item.release_code}</b><small>{item.title}</small></td><td>{item.status}</td><td>{item.approved_question_count} câu · {item.family_count} family</td><td><code>{item.openedx_library_key}</code></td></tr>)}</tbody></table></div>
    </section>

    <section className="card">
      <h2>4. Map course Open edX vào ngân hàng đề</h2>
      <div className="inline-form compact-form">
        <label>Course ID<input id="map-course" className="input" placeholder="course-v1:FPT+DOM123+SU26" /></label>
        <label>Môn<select className="input" value={selectedSubjectId} onChange={(event) => setSelectedSubjectId(event.target.value)}>{subjects.map((item) => <option key={item.id} value={item.id}>{item.code}</option>)}</select></label>
        <label>Kỳ<input id="map-term" className="input" placeholder="SU26" /></label>
        <button className="btn" disabled={busy || !selectedSubjectId || !can('publish_questions')} onClick={() => {
          const openedx_course_id = (document.getElementById('map-course') as HTMLInputElement)?.value || ''
          const term = (document.getElementById('map-term') as HTMLInputElement)?.value || ''
          run(() => createCourseMapping(headers, { openedx_course_id, subject_id: selectedSubjectId, department_id: selectedDepartmentId || null, term }), 'Đã map course Open edX vào môn')
        }}>Map course</button>
      </div>
      <div className="table-wrap"><table className="data-table compact-table"><thead><tr><th>Course</th><th>Subject</th><th>Kỳ</th><th>Trạng thái</th></tr></thead><tbody>{mappings.slice(0, 8).map((item) => <tr key={item.id}><td><code>{item.openedx_course_id}</code></td><td>{subjects.find((subject) => subject.id === item.subject_id)?.code || item.subject_id}</td><td>{item.term || '—'}</td><td>{item.status}</td></tr>)}</tbody></table></div>
    </section>
  </div>
}
