'use client'

import Link from 'next/link'
import { useEffect, useMemo, useState } from 'react'
import { useAppContext } from '../../context/AppContext'
import {
  autoMapAcademicSubjectCourse,
  getAcademicCampuses,
  getAcademicTeacherSubjects,
  getAcademicTerms,
} from '../../lib/api'
import { AcademicCampus, AcademicSubjectManagement, AcademicTerm } from '../../types'

const PAGE_SIZE = 50

function branchLabel(value?: string | null) {
  return value === 'ptcd' ? 'PTCĐ' : 'Poly'
}

function statusClass(status?: string | null) {
  const value = (status || '').toLowerCase()
  if (['mapped', 'already_mapped', 'auto_mapped'].includes(value)) return 'status-pill success'
  if (value === 'auto_candidate') return 'status-pill warning'
  if (['multiple_candidates', 'not_found'].includes(value)) return 'status-pill danger'
  return 'status-pill neutral'
}

function percentLabel(value?: number | null) {
  if (typeof value !== 'number' || Number.isNaN(value)) return 'N/A'
  return `${Math.round(value * 10) / 10}%`
}

function componentScoreText(score: { percent?: number | null; earned?: number | null; possible?: number | null }) {
  if (typeof score.percent === 'number' && !Number.isNaN(score.percent)) return percentLabel(score.percent)
  if (typeof score.earned === 'number' && typeof score.possible === 'number') return `${Math.round(score.earned * 100) / 100}/${Math.round(score.possible * 100) / 100}`
  return 'N/A'
}

function componentSummaryLine(scores?: { name?: string | null; percent?: number | null; earned?: number | null; possible?: number | null }[]) {
  if (!scores?.length) return 'N/A'
  return scores.slice(0, 3).map((score) => `${score.name || 'TP'}: ${componentScoreText(score)}`).join(' · ')
}

function alertText(alerts?: string[]) {
  return alerts && alerts.length ? alerts.slice(0, 2).join(', ') : 'Không có cảnh báo'
}

function counterText(total: number, page: number, pageSize: number) {
  if (!total) return '0 môn'
  const start = (page - 1) * pageSize + 1
  const end = Math.min(total, page * pageSize)
  return `${start}-${end} / ${total}`
}

export default function StudentManagementSubjectsPage() {
  const { authHeaders } = useAppContext()
  const headers = useMemo(() => authHeaders(), [authHeaders])
  const jsonHeaders = useMemo(() => authHeaders(true), [authHeaders])
  const [terms, setTerms] = useState<AcademicTerm[]>([])
  const [campuses, setCampuses] = useState<AcademicCampus[]>([])
  const [subjects, setSubjects] = useState<AcademicSubjectManagement[]>([])
  const [termId, setTermId] = useState('')
  const [branch, setBranch] = useState('poly')
  const [campus, setCampus] = useState('')
  const [search, setSearch] = useState('')
  const [learningStatus, setLearningStatus] = useState('all')
  const [page, setPage] = useState(1)
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(false)
  const [message, setMessage] = useState('')
  const [mappingSubjectId, setMappingSubjectId] = useState('')

  useEffect(() => {
    let cancelled = false
    getAcademicTerms(headers, { branch, active: true })
      .then((items) => {
        if (cancelled) return
        setTerms(items)
        if (!items.some((item) => item.id === termId)) {
          const preferred = items.find((item) => item.term_name === 'Summer 2026') || items[0]
          setTermId(preferred?.id || '')
        }
      })
      .catch((error) => setMessage(error instanceof Error ? error.message : 'Không tải được học kỳ'))
    return () => { cancelled = true }
  }, [headers, branch, termId])

  useEffect(() => {
    let cancelled = false
    getAcademicCampuses(headers, { branch, active: true })
      .then((items) => {
        if (cancelled) return
        setCampuses(items)
        if (campus && !items.some((item) => item.campus_code === campus)) setCampus('')
      })
      .catch(() => setCampuses([]))
    return () => { cancelled = true }
  }, [headers, branch, campus])

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    getAcademicTeacherSubjects(headers, { termId, branch, campus, search, learningStatus, page, pageSize: PAGE_SIZE })
      .then((result) => {
        if (cancelled) return
        setSubjects(result.items)
        setTotal(result.total)
      })
      .catch((error) => {
        if (!cancelled) setMessage(error instanceof Error ? error.message : 'Không tải được danh sách môn')
      })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [headers, termId, branch, campus, search, learningStatus, page])

  const selectedTerm = terms.find((item) => item.id === termId)
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE))

  const runAutoMap = async (subject: AcademicSubjectManagement) => {
    if (!termId) {
      setMessage('Cần chọn học kỳ trước khi tự động map course CMS.')
      return
    }
    setMappingSubjectId(subject.id)
    setMessage('')
    try {
      const result = await autoMapAcademicSubjectCourse(jsonHeaders, subject.id, { termId, branch })
      setMessage(result.message)
      const refreshed = await getAcademicTeacherSubjects(headers, { termId, branch, campus, search, learningStatus, page, pageSize: PAGE_SIZE })
      setSubjects(refreshed.items)
      setTotal(refreshed.total)
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Không tự động map được course CMS')
    } finally {
      setMappingSubjectId('')
    }
  }

  return <div className="page-stack student-management-page">
    <section className="card hero-card compact-hero">
      <div>
        <p className="eyebrow">Student Management</p>
        <h1>Quản lý theo môn</h1>
        <p>Chọn kỳ, hệ và cơ sở để xem các môn bạn có quyền hoặc được AP phân công. Từ môn đi xuống danh sách lớp, rồi vào chi tiết lớp/sinh viên.</p>
      </div>
      <div className="hero-actions">
        <Link className="btn secondary" href="/ap-sync">Đồng bộ AP</Link>
        <Link className="btn secondary" href="/semesters">Quản lý học kỳ</Link>
      </div>
    </section>

    <section className="card">
      <div className="section-head list-card-head">
        <div><h2>Danh sách môn</h2><p>{selectedTerm ? `${selectedTerm.term_name} · ${branchLabel(branch)} · lọc theo quyền/phân công AP` : 'Chọn kỳ để xem dữ liệu.'}</p></div>
        <div className="toolbar-actions"><span className="status-pill neutral">{counterText(total, page, PAGE_SIZE)}</span></div>
      </div>
      <div className="academic-filter-grid academic-list-filter">
        <label>Hệ
          <select className="input" value={branch} onChange={(event) => { setBranch(event.target.value); setCampus(''); setPage(1) }}>
            <option value="poly">Poly</option>
            <option value="ptcd">PTCĐ</option>
          </select>
        </label>
        <label>Học kỳ
          <select className="input" value={termId} onChange={(event) => { setTermId(event.target.value); setPage(1) }}>
            {!terms.length && <option value="">Chưa có kỳ, tạo tại /semesters</option>}
            {terms.map((item) => <option key={item.id} value={item.id}>{item.term_name}</option>)}
          </select>
        </label>
        <label>Cơ sở
          <select className="input" value={campus} onChange={(event) => { setCampus(event.target.value); setPage(1) }}>
            <option value="">Tất cả cơ sở</option>
            {campuses.map((item) => <option key={item.id} value={item.campus_code}>{item.campus_code.toUpperCase()} · {item.campus_name}</option>)}
          </select>
        </label>
        <label>Trạng thái học tập
          <select className="input" value={learningStatus} onChange={(event) => { setLearningStatus(event.target.value); setPage(1) }}>
            <option value="all">Tất cả môn</option>
            <option value="no_course_map">Chưa map course</option>
            <option value="cms_not_synced">Chưa đồng bộ CMS</option>
            <option value="no_learning_data">Chưa có progress</option>
            <option value="has_alert">Có cảnh báo</option>
          </select>
        </label>
        <label>Tìm môn
          <input className="input" value={search} onChange={(event) => { setSearch(event.target.value); setPage(1) }} placeholder="WEB107, thiết kế..." />
        </label>
      </div>
      {message && <p className="form-message">{message}</p>}
      <div className="table-wrap">
        <table className="data-table">
          <thead>
            <tr>
              <th>Môn</th>
              <th>Quy mô</th>
              <th>Đồng bộ CMS</th>
              <th>Course CMS</th>
              <th>Học tập CMS</th>
              <th>Thao tác</th>
            </tr>
          </thead>
          <tbody>
            {loading ? <tr><td colSpan={6}>Đang tải danh sách môn...</td></tr> : null}
            {!loading && !subjects.length ? <tr><td colSpan={6}>Chưa có môn phù hợp hoặc bạn chưa được phân quyền/phân công.</td></tr> : null}
            {subjects.map((subject) => <tr key={subject.id}>
              <td><b>{subject.subject_code}</b><small>{subject.subject_name}</small></td>
              <td>
                <b>{subject.class_count} lớp</b>
                <small>{subject.student_count} SV · {subject.teacher_count} GV · {subject.campus_count} cơ sở</small>
              </td>
              <td>
                <span className="status-pill success">{subject.cms_synced_count} đã đồng bộ</span>
                <small>{subject.cms_unsynced_count} chưa/khác trạng thái</small>
              </td>
              <td>
                <span className={statusClass(subject.course_mapping_status)}>{subject.course_mapping_label || subject.course_mapping_status}</span>
                <small>{subject.openedx_course_id || subject.suggested_openedx_course_id || 'N/A'}</small>
              </td>
              <td>
                <b>{subject.learning_enrolled_count || 0}/{subject.student_count} enroll</b>
                <small>Dữ liệu: {subject.learning_synced_count || 0}/{subject.student_count} · Đã học: {subject.learning_active_count || 0}/{subject.student_count}</small>
                <small>Tiến độ: {percentLabel(subject.learning_avg_progress_percent)} · Điểm tổng: {percentLabel(subject.learning_avg_grade_percent)}</small>
                <small>Điểm TP: {componentSummaryLine(subject.learning_component_summaries)}</small>
                <small>{alertText(subject.learning_alerts)}</small>
              </td>
              <td>
                <div className="toolbar-actions">
                  {subject.course_mapping_status === 'auto_candidate' && <button className="btn small primary" type="button" disabled={mappingSubjectId === subject.id} onClick={() => runAutoMap(subject)}>{mappingSubjectId === subject.id ? 'Đang map...' : 'Auto map'}</button>}
                  <Link className="btn small secondary" href={`/student-management/subjects/${encodeURIComponent(subject.id)}/classes?term_id=${encodeURIComponent(termId)}&branch=${encodeURIComponent(branch)}&campus=${encodeURIComponent(campus)}&term_name=${encodeURIComponent(selectedTerm?.term_name || '')}&subject_code=${encodeURIComponent(subject.subject_code)}&subject_name=${encodeURIComponent(subject.subject_name)}`}>Xem lớp</Link>
                </div>
              </td>
            </tr>)}
          </tbody>
        </table>
      </div>
      <div className="pagination-row">
        <button className="btn secondary small" disabled={page <= 1} onClick={() => setPage((value) => Math.max(1, value - 1))}>Trang trước</button>
        <span>{page} / {totalPages}</span>
        <button className="btn secondary small" disabled={page >= totalPages} onClick={() => setPage((value) => value + 1)}>Trang sau</button>
      </div>
    </section>
  </div>
}
