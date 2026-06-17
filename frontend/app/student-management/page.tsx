'use client'

import { useEffect, useMemo, useState } from 'react'
import { useAppContext } from '../../context/AppContext'
import {
  getAcademicBlocks,
  getAcademicClassStudents,
  getAcademicSubjects,
  getAcademicTeacherClasses,
  getAcademicTerms,
  syncAcademicFromAp,
} from '../../lib/api'
import { AcademicBlock, AcademicClass, AcademicStudent, AcademicSubject, AcademicTerm } from '../../types'

function formatDate(value?: string | null) {
  if (!value) return '—'
  try { return new Date(value).toLocaleDateString('vi-VN') } catch { return '—' }
}

function counterText(total: number, page: number, pageSize: number) {
  if (!total) return '0 bản ghi'
  const start = (page - 1) * pageSize + 1
  const end = Math.min(total, page * pageSize)
  return `${start}-${end} / ${total}`
}

export default function StudentManagementPage() {
  const { authHeaders, can } = useAppContext()
  const headers = useMemo(() => authHeaders(), [authHeaders])
  const jsonHeaders = useMemo(() => authHeaders(true), [authHeaders])
  const [terms, setTerms] = useState<AcademicTerm[]>([])
  const [blocks, setBlocks] = useState<AcademicBlock[]>([])
  const [subjects, setSubjects] = useState<AcademicSubject[]>([])
  const [classes, setClasses] = useState<AcademicClass[]>([])
  const [students, setStudents] = useState<AcademicStudent[]>([])
  const [selectedTermId, setSelectedTermId] = useState('')
  const [selectedBlockId, setSelectedBlockId] = useState('')
  const [selectedSubjectId, setSelectedSubjectId] = useState('')
  const [selectedClass, setSelectedClass] = useState<AcademicClass | null>(null)
  const [search, setSearch] = useState('')
  const [studentSearch, setStudentSearch] = useState('')
  const [classTotal, setClassTotal] = useState(0)
  const [classPage, setClassPage] = useState(1)
  const [studentTotal, setStudentTotal] = useState(0)
  const [studentPage, setStudentPage] = useState(1)
  const [loading, setLoading] = useState(false)
  const [studentLoading, setStudentLoading] = useState(false)
  const [message, setMessage] = useState('')
  const [syncOpen, setSyncOpen] = useState(false)
  const [syncTermName, setSyncTermName] = useState('Spring 2026')
  const [syncCampus, setSyncCampus] = useState('pc')
  const [syncSubjects, setSyncSubjects] = useState('')
  const [syncRunning, setSyncRunning] = useState(false)

  useEffect(() => {
    let cancelled = false
    getAcademicTerms(headers)
      .then((items) => {
        if (cancelled) return
        setTerms(items)
        if (!selectedTermId && items[0]) setSelectedTermId(items[0].id)
      })
      .catch((error) => setMessage(error instanceof Error ? error.message : 'Không tải được kỳ học'))
    return () => { cancelled = true }
  }, [headers, selectedTermId])

  useEffect(() => {
    if (!selectedTermId) { setBlocks([]); setSubjects([]); return }
    let cancelled = false
    Promise.all([
      getAcademicBlocks(headers, selectedTermId),
      getAcademicSubjects(headers, { termId: selectedTermId }),
    ]).then(([nextBlocks, nextSubjects]) => {
      if (cancelled) return
      setBlocks(nextBlocks)
      setSubjects(nextSubjects)
      if (selectedBlockId && !nextBlocks.some((item) => item.id === selectedBlockId)) setSelectedBlockId('')
      if (selectedSubjectId && !nextSubjects.some((item) => item.id === selectedSubjectId)) setSelectedSubjectId('')
    }).catch((error) => setMessage(error instanceof Error ? error.message : 'Không tải được bộ lọc'))
    return () => { cancelled = true }
  }, [headers, selectedTermId, selectedBlockId, selectedSubjectId])

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    getAcademicTeacherClasses(headers, {
      termId: selectedTermId,
      blockId: selectedBlockId,
      subjectId: selectedSubjectId,
      search,
      page: classPage,
      pageSize: 50,
    }).then((page) => {
      if (cancelled) return
      setClasses(page.items)
      setClassTotal(page.total)
      if (selectedClass && !page.items.some((item) => item.id === selectedClass.id)) {
        setSelectedClass(null)
        setStudents([])
      }
    }).catch((error) => {
      if (!cancelled) setMessage(error instanceof Error ? error.message : 'Không tải được danh sách lớp')
    }).finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [headers, selectedTermId, selectedBlockId, selectedSubjectId, search, classPage, selectedClass])

  useEffect(() => {
    if (!selectedClass) return
    let cancelled = false
    setStudentLoading(true)
    getAcademicClassStudents(headers, selectedClass.id, { search: studentSearch, page: studentPage, pageSize: 50 })
      .then((page) => {
        if (cancelled) return
        setStudents(page.items)
        setStudentTotal(page.total)
      })
      .catch((error) => { if (!cancelled) setMessage(error instanceof Error ? error.message : 'Không tải được sinh viên') })
      .finally(() => { if (!cancelled) setStudentLoading(false) })
    return () => { cancelled = true }
  }, [headers, selectedClass, studentSearch, studentPage])

  const selectedTerm = terms.find((item) => item.id === selectedTermId)

  const runSync = async (dryRun = false) => {
    setSyncRunning(true)
    setMessage('')
    try {
      const codes = syncSubjects.split(/[\n,;\s]+/).map((item) => item.trim().toUpperCase()).filter(Boolean)
      const result = await syncAcademicFromAp(jsonHeaders, {
        term_name: syncTermName,
        campus: syncCampus.trim().toLowerCase(),
        branch: 'poly',
        subject_codes: codes,
        max_subjects: codes.length ? codes.length : 50,
        dry_run: dryRun,
      })
      setMessage(dryRun ? 'AP kết nối được. Kiểm tra danh sách môn trong kết quả sync.' : `Đã đồng bộ AP: ${JSON.stringify(result.counters)}`)
      if (!dryRun) {
        const nextTerms = await getAcademicTerms(headers)
        setTerms(nextTerms)
        if (!selectedTermId && nextTerms[0]) setSelectedTermId(nextTerms[0].id)
        setClassPage(1)
      }
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Đồng bộ AP thất bại')
    } finally {
      setSyncRunning(false)
    }
  }

  return <div className="page-stack student-management-page">
    <section className="hero-card compact-hero">
      <div>
        <div className="eyebrow">AP → AI Server</div>
        <h1>Quản lý lớp & sinh viên</h1>
        <p>AI Server lấy phân công từ AP, giáo viên chỉ thấy lớp mình được phân công. Open edX sẽ dùng ở bước sau để lấy tiến độ và điểm quiz.</p>
      </div>
      <div className="hero-actions">
        <button className="btn secondary" onClick={() => { setClassPage(1); setMessage('Đã làm mới danh sách lớp') }}>Làm mới</button>
        {can('manage_settings') ? <button className="btn" onClick={() => setSyncOpen(true)}>Đồng bộ AP</button> : null}
      </div>
    </section>

    {message ? <div className="alert">{message}</div> : null}

    <section className="card">
      <div className="section-head">
        <div>
          <h2>Bộ lọc lớp</h2>
          <p>{selectedTerm ? `Đang xem ${selectedTerm.term_name}` : 'Chọn kỳ để xem lớp theo phân công AP.'}</p>
        </div>
      </div>
      <div className="filter-grid academic-filter-grid">
        <label>Kỳ
          <select className="input" value={selectedTermId} onChange={(event) => { setSelectedTermId(event.target.value); setClassPage(1) }}>
            <option value="">Tất cả kỳ</option>
            {terms.map((term) => <option key={term.id} value={term.id}>{term.term_name}{term.branch ? ` · ${term.branch}` : ''}</option>)}
          </select>
        </label>
        <label>Block
          <select className="input" value={selectedBlockId} onChange={(event) => { setSelectedBlockId(event.target.value); setClassPage(1) }}>
            <option value="">Tất cả block</option>
            {blocks.map((block) => <option key={block.id} value={block.id}>{block.block_name}</option>)}
          </select>
        </label>
        <label>Môn
          <select className="input" value={selectedSubjectId} onChange={(event) => { setSelectedSubjectId(event.target.value); setClassPage(1) }}>
            <option value="">Tất cả môn</option>
            {subjects.map((subject) => <option key={subject.id} value={subject.id}>{subject.subject_code} · {subject.subject_name}</option>)}
          </select>
        </label>
        <label>Tìm lớp/môn/GV
          <input className="input" value={search} onChange={(event) => { setSearch(event.target.value); setClassPage(1) }} placeholder="SD19301, WEB107, gianglh22..." />
        </label>
      </div>
    </section>

    <section className="card">
      <div className="section-head">
        <div>
          <h2>Danh sách lớp</h2>
          <p>{loading ? 'Đang tải lớp...' : counterText(classTotal, classPage, 50)}</p>
        </div>
        <div className="toolbar-actions">
          <button className="btn small secondary" disabled={classPage <= 1} onClick={() => setClassPage((value) => Math.max(1, value - 1))}>Trước</button>
          <button className="btn small secondary" disabled={classPage * 50 >= classTotal} onClick={() => setClassPage((value) => value + 1)}>Sau</button>
        </div>
      </div>
      <div className="table-wrap">
        <table className="data-table compact-table">
          <thead><tr><th>Lớp</th><th>Môn</th><th>Kỳ / Block</th><th>Giáo viên</th><th>Sinh viên</th><th>Open edX</th><th>Thao tác</th></tr></thead>
          <tbody>
            {classes.map((item) => <tr key={item.id} className={selectedClass?.id === item.id ? 'row-selected' : ''}>
              <td><b>{item.class_code}</b><small>{item.class_name || '—'} · {item.campus || '—'}</small></td>
              <td><b>{item.subject_code}</b><small>{item.subject_name}</small></td>
              <td><b>{item.term_name || '—'}</b><small>{item.block_name || 'Chưa có block'} · {formatDate(item.start_date)} - {formatDate(item.end_date)}</small></td>
              <td><b>{item.teacher_username || '—'}</b><small>{item.teacher_name || ''}</small></td>
              <td>{item.student_count}</td>
              <td>{item.openedx_course_id ? <><b>{item.openedx_course_id}</b><small>{item.openedx_cohort_name || 'Chưa map cohort'}</small></> : <span className="status-pill warning">Chưa map</span>}</td>
              <td><button className="btn small" onClick={() => { setSelectedClass(item); setStudentPage(1); setStudentSearch('') }}>Xem SV</button></td>
            </tr>)}
            {!classes.length ? <tr><td colSpan={7}><div className="empty-state">Chưa có lớp phù hợp hoặc tài khoản này chưa được AP phân công lớp.</div></td></tr> : null}
          </tbody>
        </table>
      </div>
    </section>

    {selectedClass ? <section className="card">
      <div className="section-head">
        <div>
          <h2>Sinh viên lớp {selectedClass.class_code}</h2>
          <p>{studentLoading ? 'Đang tải sinh viên...' : counterText(studentTotal, studentPage, 50)}</p>
        </div>
        <div className="toolbar-actions">
          <input className="input compact-input" value={studentSearch} onChange={(event) => { setStudentSearch(event.target.value); setStudentPage(1) }} placeholder="Mã SV, username, họ tên..." />
          <button className="btn small secondary" disabled={studentPage <= 1} onClick={() => setStudentPage((value) => Math.max(1, value - 1))}>Trước</button>
          <button className="btn small secondary" disabled={studentPage * 50 >= studentTotal} onClick={() => setStudentPage((value) => value + 1)}>Sau</button>
        </div>
      </div>
      <div className="table-wrap">
        <table className="data-table compact-table">
          <thead><tr><th>Mã SV</th><th>Họ tên</th><th>Username AP</th><th>Email</th><th>Trạng thái</th><th>Lần sync</th></tr></thead>
          <tbody>
            {students.map((student) => <tr key={student.id}>
              <td><b>{student.student_code || '—'}</b></td>
              <td>{student.full_name}</td>
              <td><b>{student.username}</b><small>Khóa map Open edX ở bản sau</small></td>
              <td>{student.email || '—'}</td>
              <td><span className={student.active ? 'status-pill success' : 'status-pill warning'}>{student.active ? 'Đang học' : 'Ngừng học'}</span></td>
              <td>{formatDate(student.synced_at)}</td>
            </tr>)}
            {!students.length ? <tr><td colSpan={6}><div className="empty-state">Chưa có sinh viên trong lớp này.</div></td></tr> : null}
          </tbody>
        </table>
      </div>
    </section> : null}

    {syncOpen ? <div className="modal-backdrop" onClick={() => !syncRunning && setSyncOpen(false)}>
      <div className="card modal-card bank-modal" onClick={(event) => event.stopPropagation()}>
        <div className="section-head">
          <div><h2>Đồng bộ dữ liệu AP</h2><p>Token AP đang hardcode trong backend theo yêu cầu triển khai hiện tại. Token không hiển thị trên UI và không ghi vào audit.</p></div>
          <button className="btn small secondary" disabled={syncRunning} onClick={() => setSyncOpen(false)}>Đóng</button>
        </div>
        <div className="mini-form">
          <label><span>Kỳ</span><input className="input" value={syncTermName} onChange={(event) => setSyncTermName(event.target.value)} placeholder="Spring 2026" /></label>
          <label><span>Cơ sở / campus</span><input className="input" value={syncCampus} onChange={(event) => setSyncCampus(event.target.value)} placeholder="pc" /></label>
          <label><span>Mã môn cần sync</span><textarea className="input" rows={5} value={syncSubjects} onChange={(event) => setSyncSubjects(event.target.value)} placeholder="WEB107, DBI102...\nĐể trống: lấy danh sách môn từ AP, giới hạn 50 môn đầu." /></label>
        </div>
        <div className="modal-actions">
          <button className="btn secondary" disabled={syncRunning} onClick={() => runSync(true)}>Kiểm tra AP</button>
          <button className="btn" disabled={syncRunning || !syncTermName.trim() || !syncCampus.trim()} onClick={() => runSync(false)}>{syncRunning ? 'Đang đồng bộ...' : 'Đồng bộ vào AI Server'}</button>
        </div>
      </div>
    </div> : null}
  </div>
}
