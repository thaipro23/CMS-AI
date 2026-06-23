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
import { AcademicCampus, AcademicLearningComponentScore, AcademicSubjectManagement, AcademicTerm } from '../../types'

const PAGE_SIZE = 50


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

function componentScoreText(score: AcademicLearningComponentScore) {
  if (typeof score.percent === 'number' && !Number.isNaN(score.percent)) return percentLabel(score.percent)
  if (typeof score.earned === 'number' && typeof score.possible === 'number') return `${Math.round(score.earned * 100) / 100}/${Math.round(score.possible * 100) / 100}`
  return 'N/A'
}

function componentSummaryLine(scores?: AcademicLearningComponentScore[]) {
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

function buildSubjectClassesHref(subject: AcademicSubjectManagement, context: { termId: string; termName?: string; branch: string; campus: string }) {
  const params = new URLSearchParams()
  if (context.termId) params.set('term_id', context.termId)
  if (context.branch) params.set('branch', context.branch)
  if (context.campus) params.set('campus', context.campus)
  if (context.termName) params.set('term_name', context.termName)
  params.set('subject_code', subject.subject_code || '')
  params.set('subject_name', subject.subject_name || '')
  const qs = params.toString()
  return `/student-management/subjects/${encodeURIComponent(subject.id)}/classes${qs ? `?${qs}` : ''}`
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

  const loadSubjects = async (cancelledRef?: { cancelled: boolean }) => {
    setLoading(true)
    setMessage('')
    try {
      const result = await getAcademicTeacherSubjects(headers, { termId, branch, campus, search, learningStatus, page, pageSize: PAGE_SIZE })
      if (cancelledRef?.cancelled) return
      setSubjects(result.items)
      setTotal(result.total)
    } catch (error) {
      if (!cancelledRef?.cancelled) setMessage(error instanceof Error ? error.message : 'Không tải được danh sách môn')
    } finally {
      if (!cancelledRef?.cancelled) setLoading(false)
    }
  }

  useEffect(() => {
    const cancelledRef = { cancelled: false }
    loadSubjects(cancelledRef)
    return () => { cancelledRef.cancelled = true }
  }, [headers, termId, branch, campus, search, learningStatus, page])

  const selectedTerm = terms.find((item) => item.id === termId)
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE))
  const aggregate = useMemo(() => subjects.reduce((acc, item) => {
    acc.classes += item.class_count || 0
    acc.students += item.student_count || 0
    acc.mapped += ['mapped', 'already_mapped', 'auto_mapped'].includes(String(item.course_mapping_status || '').toLowerCase()) ? 1 : 0
    acc.alerts += item.learning_alerts?.length ? 1 : 0
    return acc
  }, { classes: 0, students: 0, mapped: 0, alerts: 0 }), [subjects])

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

  return <div className="page-stack student-management-page academic-flow-page">
    <section className="card academic-unified-card">
      <div className="section-head list-card-head">
        <div>
          <h2>Danh sách môn</h2>
          <p>Admin xem toàn bộ môn đã có lớp/sinh viên; giảng viên chỉ thấy môn được phân công.</p>
        </div>
        <span className="status-pill neutral">{counterText(total, page, PAGE_SIZE)}</span>
      </div>

      <div className="academic-filter-bar">
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
        <label className="academic-filter-search">Tìm môn
          <input className="input" value={search} onChange={(event) => { setSearch(event.target.value); setPage(1) }} placeholder="WEB107, BUS2015, thiết kế..." />
        </label>
      </div>

      <div className="academic-summary-strip">
        <div><span>Môn hiển thị</span><b>{total}</b><small>Theo bộ lọc hiện tại</small></div>
        <div><span>Lớp</span><b>{aggregate.classes}</b><small>Chỉ lớp có sinh viên</small></div>
        <div><span>Sinh viên</span><b>{aggregate.students}</b><small>Đã sync từ AP</small></div>
        <div><span>Course CMS</span><b>{aggregate.mapped}/{subjects.length}</b><small>Môn đã map trong trang này</small></div>
        <div><span>Cảnh báo</span><b>{aggregate.alerts}</b><small>Môn có vấn đề học tập</small></div>
      </div>

      {message && <div className="academic-inline-error"><b>Không tải được dữ liệu</b><span>{message}</span><button className="btn secondary small" type="button" onClick={() => loadSubjects()}>Thử lại</button></div>}

      <div className="table-wrap academic-table-wrap">
        <table className="data-table academic-data-table subject-table">
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
              <td className="main-entity-cell"><b>{subject.subject_code}</b><small>{subject.subject_name}</small></td>
              <td>
                <b>{subject.class_count} lớp</b>
                <small>{subject.student_count} SV · {subject.teacher_count} GV · {subject.campus_count} cơ sở</small>
              </td>
              <td>
                <span className={subject.cms_unsynced_count ? 'status-pill warning' : 'status-pill success'}>{subject.cms_synced_count}/{subject.student_count} đã đồng bộ</span>
                <small>{subject.cms_unsynced_count} chưa/khác trạng thái</small>
              </td>
              <td>
                <span className={statusClass(subject.course_mapping_status)}>{subject.course_mapping_label || subject.course_mapping_status}</span>
                <small>{subject.openedx_course_id || subject.suggested_openedx_course_id || 'N/A'}</small>
              </td>
              <td className="learning-cell">
                <b>{subject.learning_enrolled_count || 0}/{subject.student_count} enroll</b>
                <small>Dữ liệu: {subject.learning_synced_count || 0}/{subject.student_count} · Đã học: {subject.learning_active_count || 0}/{subject.student_count}</small>
                <small>Tiến độ TB: {percentLabel(subject.learning_avg_progress_percent)} · Điểm tổng TB: {percentLabel(subject.learning_avg_grade_percent)}</small>
                <small>TP: {componentSummaryLine(subject.learning_component_summaries)}</small>
                <small>{alertText(subject.learning_alerts)}</small>
              </td>
              <td>
                <div className="row-actions">
                  <Link className="btn small primary" href={buildSubjectClassesHref(subject, { termId, termName: selectedTerm?.term_name, branch, campus })}>Xem lớp</Link>
                  {!['mapped', 'already_mapped', 'auto_mapped'].includes(String(subject.course_mapping_status || '').toLowerCase()) && <button className="btn small secondary" type="button" disabled={mappingSubjectId === subject.id} onClick={() => runAutoMap(subject)}>{mappingSubjectId === subject.id ? 'Đang map...' : 'Auto map'}</button>}
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
