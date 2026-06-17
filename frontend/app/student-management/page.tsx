'use client'

import { useEffect, useMemo, useState } from 'react'
import { useAppContext } from '../../context/AppContext'
import {
  getAcademicBlocks,
  getAcademicClassStudents,
  getAcademicClassCourseMappingProposal,
  getAcademicSubjects,
  getAcademicTeacherClasses,
  getAcademicTerms,
  resolveAcademicClassOpenEdxUsers,
  saveAcademicClassCourseMapping,
  validateAcademicClassCourseMapping,
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

function mappingLabel(status?: string | null) {
  switch ((status || 'not_checked').toLowerCase()) {
    case 'matched': return 'Đã map'
    case 'inactive': return 'User inactive'
    case 'missing': return 'Chưa có Open edX'
    case 'ambiguous': return 'Trùng user'
    case 'manual_required': return 'Cần xử lý tay'
    default: return 'Chưa kiểm tra'
  }
}

function mappingClass(status?: string | null) {
  const value = (status || 'not_checked').toLowerCase()
  if (value === 'matched') return 'status-pill success'
  if (value === 'inactive' || value === 'missing' || value === 'ambiguous') return 'status-pill danger'
  if (value === 'manual_required') return 'status-pill warning'
  return 'status-pill neutral'
}

function courseMappingSourceLabel(source?: string | null) {
  if (source === 'class_override') return 'Map riêng lớp'
  if (source === 'subject_term_mapping') return 'Map theo môn/kỳ'
  return 'Chưa map'
}

function validationClass(status?: string | null) {
  const value = (status || '').toLowerCase()
  if (value === 'low') return 'status-pill success'
  if (value === 'medium') return 'status-pill warning'
  if (value === 'high') return 'status-pill danger'
  return 'status-pill neutral'
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
  const [mappingRunning, setMappingRunning] = useState(false)
  const [courseMapOpen, setCourseMapOpen] = useState(false)
  const [courseMapRunning, setCourseMapRunning] = useState(false)
  const [courseMapCourseId, setCourseMapCourseId] = useState('')
  const [courseMapCohort, setCourseMapCohort] = useState('')
  const [courseMapTitle, setCourseMapTitle] = useState('')
  const [courseMapValidation, setCourseMapValidation] = useState<any | null>(null)

  useEffect(() => {
    let cancelled = false
    getAcademicTerms(headers)
      .then((items) => {
        if (cancelled) return
        setTerms(items)
        if (!selectedTermId && items.length) {
          const preferred = items.find((item) => item.term_name === 'Summer 2026') || items[0]
          setSelectedTermId(preferred.id)
        }
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



  const runOpenEdxMapping = async () => {
    if (!selectedClass) return
    setMappingRunning(true)
    setMessage('')
    try {
      const result = await resolveAcademicClassOpenEdxUsers(jsonHeaders, selectedClass.id, { force: true, limit: 1000 })
      setMessage(`${result.message}: ${JSON.stringify(result.counts)}`)
      const page = await getAcademicClassStudents(headers, selectedClass.id, { search: studentSearch, page: studentPage, pageSize: 50 })
      setStudents(page.items)
      setStudentTotal(page.total)
    } catch (error) {
      setMessage(error instanceof Error ? `${error.message}. Nếu chưa cài LMS Student Insight plugin, hãy dùng import mapping thủ công hoặc chờ bản plugin.` : 'Map Open edX thất bại')
    } finally {
      setMappingRunning(false)
    }
  }


  const openCourseMapping = async (targetClass: AcademicClass) => {
    setSelectedClass(targetClass)
    setCourseMapOpen(true)
    setCourseMapValidation(null)
    setCourseMapRunning(true)
    setMessage('')
    try {
      const proposal = await getAcademicClassCourseMappingProposal(headers, targetClass.id)
      setCourseMapCourseId(proposal.effective_openedx_course_id || proposal.suggested_openedx_course_id || targetClass.openedx_course_id || '')
      setCourseMapCohort(proposal.effective_openedx_cohort_name || proposal.suggested_cohort_name || targetClass.openedx_cohort_name || targetClass.class_code)
      setCourseMapTitle('')
    } catch (error) {
      setCourseMapCourseId(targetClass.openedx_course_id || '')
      setCourseMapCohort(targetClass.openedx_cohort_name || targetClass.class_code)
      setMessage(error instanceof Error ? error.message : 'Không lấy được đề xuất mapping')
    } finally {
      setCourseMapRunning(false)
    }
  }

  const validateCourseMapping = async () => {
    if (!selectedClass) return
    setCourseMapRunning(true)
    setMessage('')
    try {
      const result = await validateAcademicClassCourseMapping(jsonHeaders, selectedClass.id, {
        openedx_course_id: courseMapCourseId.trim(),
        openedx_cohort_name: courseMapCohort.trim() || null,
        openedx_course_title: courseMapTitle.trim() || null,
      })
      setCourseMapValidation(result)
      setMessage(result.message)
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Validate mapping thất bại')
    } finally {
      setCourseMapRunning(false)
    }
  }

  const saveCourseMapping = async () => {
    if (!selectedClass) return
    setCourseMapRunning(true)
    setMessage('')
    try {
      const saved = await saveAcademicClassCourseMapping(jsonHeaders, selectedClass.id, {
        openedx_course_id: courseMapCourseId.trim(),
        openedx_cohort_name: courseMapCohort.trim() || null,
        openedx_course_title: courseMapTitle.trim() || null,
        allow_warnings: true,
      })
      setMessage(`Đã lưu mapping: ${saved.openedx_course_id}${saved.openedx_cohort_name ? ` · cohort ${saved.openedx_cohort_name}` : ''}`)
      setCourseMapOpen(false)
      setClasses((items) => items.map((item) => item.id === selectedClass.id ? { ...item, openedx_course_id: saved.openedx_course_id, openedx_cohort_name: saved.openedx_cohort_name, openedx_mapping_source: 'class_override', openedx_mapping_validation_status: saved.validation_status } : item))
      setSelectedClass((item) => item && item.id === selectedClass.id ? { ...item, openedx_course_id: saved.openedx_course_id, openedx_cohort_name: saved.openedx_cohort_name, openedx_mapping_source: 'class_override', openedx_mapping_validation_status: saved.validation_status } : item)
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Lưu mapping thất bại')
    } finally {
      setCourseMapRunning(false)
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
        {can('manage_settings') ? <a className="btn" href="/ap-sync">Đồng bộ AP</a> : null}
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
              <td>{item.openedx_course_id ? <><b>{item.openedx_course_id}</b><small>{item.openedx_cohort_name || 'Chưa map cohort'} · {courseMappingSourceLabel(item.openedx_mapping_source)}</small>{item.openedx_mapping_validation_status ? <span className={validationClass(item.openedx_mapping_validation_status)}>{item.openedx_mapping_validation_status}</span> : null}</> : <span className="status-pill warning">Chưa map</span>}</td>
              <td><div className="row-actions"><button className="btn small" onClick={() => { setSelectedClass(item); setStudentPage(1); setStudentSearch('') }}>Xem SV</button>{can('manage_settings') ? <button className="btn small secondary" onClick={() => openCourseMapping(item)}>Map course</button> : null}</div></td>
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
          <button className="btn small" disabled={mappingRunning} onClick={runOpenEdxMapping}>{mappingRunning ? 'Đang map...' : 'Map Open edX'}</button>
          <input className="input compact-input" value={studentSearch} onChange={(event) => { setStudentSearch(event.target.value); setStudentPage(1) }} placeholder="Mã SV, username, họ tên..." />
          <button className="btn small secondary" disabled={studentPage <= 1} onClick={() => setStudentPage((value) => Math.max(1, value - 1))}>Trước</button>
          <button className="btn small secondary" disabled={studentPage * 50 >= studentTotal} onClick={() => setStudentPage((value) => value + 1)}>Sau</button>
        </div>
      </div>
      <div className="table-wrap">
        <table className="data-table compact-table">
          <thead><tr><th>Mã SV</th><th>Họ tên</th><th>Username AP</th><th>Username Open edX</th><th>Map</th><th>Trạng thái</th><th>Lần kiểm tra</th></tr></thead>
          <tbody>
            {students.map((student) => <tr key={student.id}>
              <td><b>{student.student_code || '—'}</b></td>
              <td>{student.full_name}<small>{student.email || '—'}</small></td>
              <td><b>{student.username}</b><small>Khóa map chính</small></td>
              <td><b>{student.openedx_username || '—'}</b><small>{student.openedx_user_id ? `ID ${student.openedx_user_id}` : student.mapping_note || 'AP.username = Open edX username'}</small></td>
              <td><span className={mappingClass(student.match_status)}>{mappingLabel(student.match_status)}</span></td>
              <td><span className={student.active ? 'status-pill success' : 'status-pill warning'}>{student.active ? 'Đang học' : 'Ngừng học'}</span></td>
              <td>{formatDate(student.last_resolved_at || student.synced_at)}</td>
            </tr>)}
            {!students.length ? <tr><td colSpan={7}><div className="empty-state">Chưa có sinh viên trong lớp này.</div></td></tr> : null}
          </tbody>
        </table>
      </div>
    </section> : null}

    {courseMapOpen && selectedClass ? <div className="modal-backdrop" onClick={() => !courseMapRunning && setCourseMapOpen(false)}>
      <div className="card modal-card bank-modal" onClick={(event) => event.stopPropagation()}>
        <div className="section-head">
          <div><h2>Map lớp {selectedClass.class_code} sang Open edX</h2><p>Ưu tiên mapping riêng lớp. Nếu không có, hệ thống dùng mapping cấp môn/kỳ/block.</p></div>
          <button className="btn small secondary" disabled={courseMapRunning} onClick={() => setCourseMapOpen(false)}>Đóng</button>
        </div>
        <div className="mini-form">
          <label><span>Course ID Open edX</span><input className="input" value={courseMapCourseId} onChange={(event) => { setCourseMapCourseId(event.target.value); setCourseMapValidation(null) }} placeholder="course-v1:FPT+WEB107+SP2026" /></label>
          <label><span>Cohort / mã lớp</span><input className="input" value={courseMapCohort} onChange={(event) => { setCourseMapCohort(event.target.value); setCourseMapValidation(null) }} placeholder={selectedClass.class_code} /></label>
          <label><span>Tên course nếu biết</span><input className="input" value={courseMapTitle} onChange={(event) => setCourseMapTitle(event.target.value)} placeholder="WEB107 - Thiết kế web..." /></label>
        </div>
        {courseMapValidation ? <div className="alert soft-alert">
          <b>{courseMapValidation.message}</b>
          <ul className="compact-list">{courseMapValidation.checks?.map((check: any) => <li key={check.code}><span className={validationClass(check.status === 'fail' ? 'high' : check.status === 'warn' ? 'medium' : 'low')}>{check.status}</span> {check.message}</li>)}</ul>
        </div> : null}
        <div className="modal-actions">
          {can('manage_settings') ? <>
            <button className="btn secondary" disabled={courseMapRunning || !courseMapCourseId.trim()} onClick={validateCourseMapping}>Kiểm tra</button>
            <button className="btn" disabled={courseMapRunning || !courseMapCourseId.trim()} onClick={saveCourseMapping}>{courseMapRunning ? 'Đang lưu...' : 'Lưu mapping'}</button>
          </> : <span className="status-pill warning">Chỉ quản trị được sửa mapping</span>}
        </div>
      </div>
    </div> : null}

  </div>
}
