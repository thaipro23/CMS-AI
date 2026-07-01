'use client'

import Link from 'next/link'
import { useEffect, useMemo, useState } from 'react'
import { useParams, useSearchParams } from 'next/navigation'
import { useAppContext } from '../../../../../context/AppContext'
import { getAcademicTrainingTeacherReport } from '../../../../../lib/api'
import { AcademicLearningComponentScore, AcademicTrainingClassReport, AcademicTrainingTeacherReport } from '../../../../../types'

const PAGE_SIZE = 50

function normalizePercentValue(value?: number | null) {
  if (typeof value !== 'number' || Number.isNaN(value)) return null
  if (value >= 0 && value <= 1) return value * 100
  return value
}

function percentLabel(value?: number | null) {
  const percent = normalizePercentValue(value)
  if (percent === null) return 'N/A'
  return `${Math.round(percent * 10) / 10}%`
}

function score10Label(value?: number | null) {
  if (typeof value !== 'number' || Number.isNaN(value)) return 'N/A'
  let score = value
  if (score >= 0 && score <= 1) score *= 10
  if (score > 10) score /= 10
  score = Math.max(0, Math.min(10, score))
  return `${Math.round(score * 10) / 10}/10`
}

function grade10Label(value?: number | null) {
  const percent = normalizePercentValue(value)
  if (percent === null) return 'N/A'
  return score10Label(percent / 10)
}

function componentKey(score: AcademicLearningComponentScore) {
  return String(score.key || score.name || '').trim()
}

function componentDisplayName(score: AcademicLearningComponentScore) {
  return String(score.name || score.key || 'Đầu điểm').trim()
}

function componentScoreText(score?: AcademicLearningComponentScore | null) {
  if (!score) return 'N/A'
  const percent = normalizePercentValue(score.percent)
  if (percent !== null) return grade10Label(percent)
  if (typeof score.earned === 'number' && typeof score.possible === 'number' && score.possible > 0) {
    const value = Math.max(0, Math.min(10, (score.earned / score.possible) * 10))
    return `${Math.round(value * 10) / 10}/10`
  }
  return 'N/A'
}

function countLabel(value?: number | null) {
  return String(value || 0)
}

function ratioLabel(done?: number | null, total?: number | null) {
  return `${done || 0}/${total || 0}`
}

function alertText(alerts?: string[]) {
  return alerts?.length ? alerts.slice(0, 3).join(', ') : 'Không có cảnh báo lớn'
}

function classComponentColumns(classes: AcademicTrainingClassReport[]) {
  const columns: Array<{ key: string; name: string }> = []
  const seen = new Set<string>()
  classes.forEach((cls) => {
    ;(cls.learning_component_summaries || []).forEach((score) => {
      const key = componentKey(score)
      const name = componentDisplayName(score)
      const dedupeKey = (key || name).toLowerCase()
      if (!dedupeKey || seen.has(dedupeKey)) return
      seen.add(dedupeKey)
      columns.push({ key: key || name, name })
    })
  })
  return columns.sort((left, right) => left.name.localeCompare(right.name, 'vi', { numeric: true, sensitivity: 'base' }))
}

function classComponentScore(cls: AcademicTrainingClassReport, column: { key: string; name: string }) {
  return cls.learning_component_summaries?.find((score) => componentKey(score) === column.key || score.name === column.name) || null
}

function riskTone(cls: AcademicTrainingClassReport) {
  if (!cls.openedx_course_id) return 'status-pill danger'
  if ((cls.risk_student_count || 0) > 0 || (cls.deadline_late_student_count || 0) > 0 || (cls.exam_not_eligible_student_count || 0) > 0) return 'status-pill warning'
  return 'status-pill success'
}

function classDetailHref(cls: AcademicTrainingClassReport, teacher: AcademicTrainingTeacherReport | null, filters: { termId: string; branch: string; campus: string; termName: string }) {
  const params = new URLSearchParams()
  params.set('from', 'teacher-management')
  params.set('teacher_id', teacher?.teacher_id || '')
  params.set('teacher_name', teacher?.teacher_name || teacher?.teacher_username || '')
  if (filters.termId) params.set('term_id', filters.termId)
  if (filters.branch) params.set('branch', filters.branch)
  if (filters.campus) params.set('campus', filters.campus)
  if (filters.termName) params.set('term_name', filters.termName)
  if (cls.subject_id) params.set('subject_id', cls.subject_id)
  if (cls.subject_code) params.set('subject_code', cls.subject_code)
  if (cls.subject_name) params.set('subject_name', cls.subject_name)
  return `/teacher-management/classes/${encodeURIComponent(cls.class_id)}?${params.toString()}`
}

export default function TeacherClassesPage() {
  const params = useParams<{ teacherId: string }>()
  const searchParams = useSearchParams()
  const teacherId = decodeURIComponent(String(params.teacherId || ''))
  const termId = searchParams.get('term_id') || ''
  const branch = searchParams.get('branch') || 'poly'
  const campus = searchParams.get('campus') || ''
  const termName = searchParams.get('term_name') || ''
  const teacherNameFromQuery = searchParams.get('teacher_name') || ''
  const { authHeaders } = useAppContext()
  const headers = useMemo(() => authHeaders(), [authHeaders])

  const [teacher, setTeacher] = useState<AcademicTrainingTeacherReport | null>(null)
  const [classes, setClasses] = useState<AcademicTrainingClassReport[]>([])
  const [loading, setLoading] = useState(false)
  const [message, setMessage] = useState('')
  const [learningStatus, setLearningStatus] = useState('all')

  const load = async () => {
    if (!termId || !teacherId) {
      setTeacher(null)
      setClasses([])
      setMessage('Thiếu học kỳ hoặc mã giáo viên. Quay lại trang giáo viên và mở lại từ nút Xem lớp.')
      return
    }
    setLoading(true)
    setMessage('')
    try {
      const result = await getAcademicTrainingTeacherReport(headers, { termId, branch, campus, teacherId, learningStatus, page: 1, pageSize: 1 })
      const item = result.items?.[0] || null
      setTeacher(item)
      setClasses(item?.classes || [])
      if (!item) setMessage('Không tìm thấy lớp của giáo viên theo bộ lọc hiện tại.')
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Không tải được danh sách lớp của giáo viên')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [headers, termId, branch, campus, teacherId, learningStatus])

  const columns = useMemo(() => classComponentColumns(classes), [classes])
  const filters = { termId, branch, campus, termName }
  const teacherTitle = teacher?.teacher_name || teacherNameFromQuery || teacher?.teacher_username || 'Giảng viên'

  return <div className="page-stack student-management-page academic-flow-page training-management-page teacher-management-page teacher-classes-page ux-enterprise-page">
    <section className="card academic-unified-card ux-surface-card teacher-workspace-card">
      <div className="teacher-compact-toolbar">
        <div>
          <b>Lớp của {teacherTitle}</b>
          <small>{termName || termId || 'Chưa rõ kỳ'} · {branch.toUpperCase()} · {campus ? campus.toUpperCase() : 'Tất cả cơ sở'} · {classes.length} lớp</small>
        </div>
        <div className="teacher-compact-actions">
          <Link className="btn secondary small" href={`/teacher-management?term_id=${encodeURIComponent(termId)}&branch=${encodeURIComponent(branch)}&campus=${encodeURIComponent(campus)}`}>Về trang giáo viên</Link>
          <button className="btn secondary small" type="button" onClick={load} disabled={loading}>{loading ? 'Đang tải...' : 'Tải lại lớp'}</button>
        </div>
      </div>

      <div className="academic-filter-bar ux-filter-grid teacher-filter-bar">
        <label>Trạng thái lớp
          <select className="input" value={learningStatus} onChange={(event) => setLearningStatus(event.target.value)}>
            <option value="all">Tất cả lớp</option>
            <option value="no_course_map">Lớp chưa map course</option>
            <option value="cms_not_synced">Có SV chưa đồng bộ CMS</option>
            <option value="not_fully_enrolled">Có SV chưa enroll</option>
            <option value="no_activity">Có SV chưa học</option>
            <option value="low_progress">Có SV tiến độ thấp</option>
            <option value="low_grade">Có SV điểm thấp</option>
            <option value="deadline_late">Có SV trễ deadline quiz</option>
            <option value="exam_not_eligible">Có SV không được thi</option>
            <option value="has_alert">Có cảnh báo</option>
          </select>
        </label>
      </div>

      {teacher && <div className="academic-summary-strip training-summary-strip ux-kpi-grid">
        <div><span>Lớp</span><b>{countLabel(teacher.class_count)}</b><small>{teacher.subject_count} môn</small></div>
        <div><span>Sinh viên</span><b>{countLabel(teacher.student_count)}</b><small>{countLabel(teacher.unique_student_count)} SV riêng biệt</small></div>
        <div><span>Đã đồng bộ CMS</span><b>{ratioLabel(teacher.cms_synced_count, teacher.student_count)}</b><small>User CMS đã match</small></div>
        <div><span>Đã enroll</span><b>{ratioLabel(teacher.learning_enrolled_count, teacher.student_count)}</b><small>Enrollment CMS</small></div>
        <div><span>Course completion TB</span><b>{percentLabel(teacher.learning_avg_progress_percent)}</b><small>Điểm tổng {score10Label(teacher.learning_avg_grade_10)}</small></div>
        <div><span>Cần theo dõi</span><b>{countLabel(teacher.risk_student_count)}</b><small>Không đếm trùng SV</small></div>
      </div>}

      {message && <div className="academic-inline-error"><b>Thông báo</b><span>{message}</span></div>}

      <div className="table-wrap academic-table-wrap training-table-wrap ux-table-card">
        <table className="data-table academic-data-table training-class-grade-table">
          <thead><tr><th>STT</th><th>Lớp</th><th>Môn</th><th>Course CMS</th><th>Sinh viên</th><th>Học lại</th><th>Tiến độ học</th>{columns.map((column) => <th key={column.key} className="component-grade-th">{column.name}</th>)}<th>Deadline quiz</th><th>Điều kiện thi</th><th>Cảnh báo</th><th>Thao tác</th></tr></thead>
          <tbody>
            {loading && Array.from({ length: 5 }).map((_, index) => <tr key={`class-skeleton-${index}`} className="ux-skeleton-row"><td colSpan={11 + columns.length}><span className="ux-skeleton-line wide" /><span className="ux-skeleton-line" /></td></tr>)}
            {!loading && !classes.length && <tr><td colSpan={11 + columns.length}><div className="ux-empty-state"><b>Chưa có lớp theo bộ lọc hiện tại</b><span>Đổi trạng thái hoặc quay lại trang giáo viên để chọn giáo viên khác.</span></div></td></tr>}
            {!loading && classes.map((cls) => <tr key={cls.class_id}>
              <td><b>{cls.class_code}</b><small>{cls.term_name}{cls.block_name ? ` · ${cls.block_name}` : ''}</small></td>
              <td><b>{cls.subject_code}</b><small>{cls.subject_name}</small></td>
              <td>{cls.openedx_course_id ? <><b>{cls.openedx_course_id}</b><small>{cls.openedx_mapping_source}</small></> : <span className="status-pill warning">Chưa map</span>}</td>
              <td><b>{cls.student_count} SV</b><small>CMS {ratioLabel(cls.cms_synced_count, cls.student_count)} · Enroll {ratioLabel(cls.learning_enrolled_count, cls.student_count)}</small></td>
              <td><b>{countLabel(cls.relearn_student_count)} SV</b><small>{countLabel(cls.total_relearn_count)} lượt học lại</small></td>
              <td><b>Course completion {percentLabel(cls.learning_avg_progress_percent)}</b><small>Điểm tổng {score10Label(cls.learning_avg_grade_10)}</small></td>
              {columns.map((column) => <td key={`${cls.class_id}-${column.key}`} className="component-grade-cell"><b>{componentScoreText(classComponentScore(cls, column))}</b></td>)}
              <td><b>{countLabel(cls.deadline_late_student_count)} SV trễ</b><small>{countLabel(cls.deadline_late_quiz_count)} lượt quiz trễ · Đã đến hạn {countLabel(cls.deadline_due_quiz_count)}/{countLabel(cls.deadline_quiz_count)} quiz</small><small>{cls.deadline_next_quiz_label ? `${cls.deadline_next_quiz_label}: ${cls.deadline_next_quiz_from_date || 'N/A'} → ${cls.deadline_next_quiz_due_date || 'N/A'}` : 'Đã qua lịch quiz hoặc chưa có Detailed grades'}</small></td>
              <td><b>{countLabel(cls.exam_eligible_student_count)} được thi</b><small>{countLabel(cls.exam_not_eligible_student_count)} không được thi · {countLabel(cls.exam_insufficient_data_student_count)} thiếu dữ liệu</small><small>Quiz chưa đạt: {countLabel(cls.quiz_failed_count)} · Assignment chưa chấm: {countLabel(cls.assignment_not_graded_count)}</small></td>
              <td><span className={riskTone(cls)}>{cls.learning_alerts?.length ? 'Có cảnh báo' : 'Ổn'}</span><small>{alertText(cls.learning_alerts)}</small></td>
              <td><Link className="btn primary small" href={classDetailHref(cls, teacher, filters)}>Chi tiết lớp</Link></td>
            </tr>)}
          </tbody>
        </table>
      </div>
    </section>
  </div>
}
