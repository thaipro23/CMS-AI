'use client'

import { useEffect, useMemo, useState } from 'react'
import { useAppContext } from '../../context/AppContext'
import {
  downloadAcademicTrainingTeacherReport,
  getAcademicCampuses,
  getAcademicTerms,
  getAcademicTrainingTeacherReport,
} from '../../lib/api'
import { AcademicCampus, AcademicLearningComponentScore, AcademicTerm, AcademicTrainingTeacherReport } from '../../types'

const PAGE_SIZE = 50

type TrainingSummary = {
  teacher_count: number
  class_count: number
  subject_count: number
  student_count: number
  unique_student_count: number
  relearn_student_count: number
  total_relearn_count: number
  cms_synced_count: number
  learning_enrolled_count: number
  learning_active_count: number
  risk_student_count: number
  classes_without_course_count: number
  deadline_late_student_count: number
  deadline_late_quiz_count: number
}

const EMPTY_SUMMARY: TrainingSummary = {
  teacher_count: 0,
  class_count: 0,
  subject_count: 0,
  student_count: 0,
  unique_student_count: 0,
  relearn_student_count: 0,
  total_relearn_count: 0,
  cms_synced_count: 0,
  learning_enrolled_count: 0,
  learning_active_count: 0,
  risk_student_count: 0,
  classes_without_course_count: 0,
  deadline_late_student_count: 0,
  deadline_late_quiz_count: 0,
}

function normalizeSummary(value?: Partial<TrainingSummary> | null): TrainingSummary {
  return {
    ...EMPTY_SUMMARY,
    ...(value || {}),
    relearn_student_count: Number(value?.relearn_student_count || 0),
    total_relearn_count: Number(value?.total_relearn_count || 0),
    deadline_late_student_count: Number(value?.deadline_late_student_count || 0),
    deadline_late_quiz_count: Number(value?.deadline_late_quiz_count || 0),
  }
}

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

function grade10Label(value?: number | null) {
  const percent = normalizePercentValue(value)
  if (percent === null) return 'N/A'
  const score = Math.max(0, Math.min(10, percent / 10))
  return `${Math.round(score * 10) / 10}/10`
}

function componentKey(score: AcademicLearningComponentScore) {
  return String(score.key || score.name || '').trim()
}

function componentDisplayName(score: AcademicLearningComponentScore) {
  return String(score.name || score.key || 'Đầu điểm').trim()
}

function gradeColumnCompare(left: { key: string; name: string }, right: { key: string; name: string }) {
  return left.name.localeCompare(right.name, 'vi', { numeric: true, sensitivity: 'base' })
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
  const cleanDone = done || 0
  const cleanTotal = total || 0
  return `${cleanDone}/${cleanTotal}`
}

function alertText(alerts?: string[]) {
  return alerts?.length ? alerts.slice(0, 3).join(', ') : 'Không có cảnh báo lớn'
}

function counterText(total: number, page: number, pageSize: number) {
  if (!total) return '0 giáo viên'
  const start = (page - 1) * pageSize + 1
  const end = Math.min(total, page * pageSize)
  return `${start}-${end} / ${total}`
}

function riskTone(item: AcademicTrainingTeacherReport) {
  if (item.classes_without_course_count || item.status_counts?.sync_error) return 'status-pill danger'
  if (item.risk_student_count) return 'status-pill warning'
  return 'status-pill success'
}

function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

export default function TrainingManagementPage() {
  const { authHeaders } = useAppContext()
  const headers = useMemo(() => authHeaders(), [authHeaders])
  const [terms, setTerms] = useState<AcademicTerm[]>([])
  const [campuses, setCampuses] = useState<AcademicCampus[]>([])
  const [items, setItems] = useState<AcademicTrainingTeacherReport[]>([])
  const [summary, setSummary] = useState<TrainingSummary>(EMPTY_SUMMARY)
  const [termId, setTermId] = useState('')
  const [branch, setBranch] = useState('poly')
  const [campus, setCampus] = useState('')
  const [search, setSearch] = useState('')
  const [learningStatus, setLearningStatus] = useState('all')
  const [page, setPage] = useState(1)
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(false)
  const [exporting, setExporting] = useState(false)
  const [message, setMessage] = useState('')
  const [expandedTeacherId, setExpandedTeacherId] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    getAcademicTerms(headers, { branch, active: true })
      .then((data) => {
        if (cancelled) return
        setTerms(data)
        if (!data.some((item) => item.id === termId)) {
          const preferred = data.find((item) => item.term_name === 'Summer 2026') || data[0]
          setTermId(preferred?.id || '')
        }
      })
      .catch((error) => setMessage(error instanceof Error ? error.message : 'Không tải được học kỳ'))
    return () => { cancelled = true }
  }, [headers, branch, termId])

  useEffect(() => {
    let cancelled = false
    getAcademicCampuses(headers, { branch, active: true })
      .then((data) => {
        if (cancelled) return
        setCampuses(data)
        if (campus && !data.some((item) => item.campus_code === campus)) setCampus('')
      })
      .catch(() => setCampuses([]))
    return () => { cancelled = true }
  }, [headers, branch, campus])

  const loadReport = async (cancelledRef?: { cancelled: boolean }) => {
    setLoading(true)
    setMessage('')
    try {
      const result = await getAcademicTrainingTeacherReport(headers, { termId, branch, campus, search, learningStatus, page, pageSize: PAGE_SIZE })
      if (cancelledRef?.cancelled) return
      setItems(result.items || [])
      setSummary(normalizeSummary(result.summary))
      setTotal(result.total || 0)
    } catch (error) {
      if (!cancelledRef?.cancelled) setMessage(error instanceof Error ? error.message : 'Không tải được báo cáo quản lý đào tạo')
    } finally {
      if (!cancelledRef?.cancelled) setLoading(false)
    }
  }

  useEffect(() => {
    const cancelledRef = { cancelled: false }
    loadReport(cancelledRef)
    return () => { cancelledRef.cancelled = true }
  }, [headers, termId, branch, campus, search, learningStatus, page])

  const selectedTerm = terms.find((item) => item.id === termId)
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE))

  const classComponentColumns = (item: AcademicTrainingTeacherReport) => {
    const columns: Array<{ key: string; name: string }> = []
    const seen = new Set<string>()
    ;(item.classes || []).forEach((cls) => {
      ;(cls.learning_component_summaries || []).forEach((score) => {
        const key = componentKey(score)
        const name = componentDisplayName(score)
        const dedupeKey = (key || name).toLowerCase()
        if (!dedupeKey || seen.has(dedupeKey)) return
        seen.add(dedupeKey)
        columns.push({ key: key || name, name })
      })
    })
    return columns.sort(gradeColumnCompare)
  }

  const classComponentScore = (cls: any, column: { key: string; name: string }) => {
    return cls.learning_component_summaries?.find((score: AcademicLearningComponentScore) => componentKey(score) === column.key || score.name === column.name) || null
  }

  const exportExcel = async () => {
    setExporting(true)
    setMessage('')
    try {
      const blob = await downloadAcademicTrainingTeacherReport(headers, { termId, branch, campus, search, learningStatus })
      const termPart = (selectedTerm?.term_name || 'term').replace(/[^a-zA-Z0-9]+/g, '-')
      downloadBlob(blob, `bao-cao-quan-ly-dao-tao-${branch}-${termPart}.xlsx`)
      setMessage('Đã xuất Excel báo cáo quản lý đào tạo.')
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Không xuất được file Excel')
    } finally {
      setExporting(false)
    }
  }

  return <div className="page-stack student-management-page academic-flow-page training-management-page">
    <section className="card academic-unified-card">
      <div className="section-head list-card-head">
        <div>
          <h2>Quản lý đào tạo</h2>
          <p>Thống kê theo giảng viên: số lớp đang dạy, quy mô sinh viên, trạng thái đồng bộ CMS, Course completion, điểm tổng hệ 10 và cảnh báo trễ deadline quiz theo lịch tuần/block.</p>
        </div>
        <div className="toolbar-actions">
          <span className="status-pill neutral">{counterText(total, page, PAGE_SIZE)}</span>
          <button className="btn secondary" type="button" onClick={() => loadReport()} disabled={loading}>Tải lại</button>
          <button className="btn primary" type="button" onClick={exportExcel} disabled={exporting || loading}>{exporting ? 'Đang xuất...' : 'Xuất Excel'}</button>
        </div>
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
        <label>Trạng thái
          <select className="input" value={learningStatus} onChange={(event) => { setLearningStatus(event.target.value); setPage(1) }}>
            <option value="all">Tất cả giáo viên</option>
            <option value="no_course_map">Có lớp chưa map course</option>
            <option value="cms_not_synced">Có SV chưa đồng bộ CMS</option>
            <option value="not_fully_enrolled">Có SV chưa enroll</option>
            <option value="no_activity">Có SV chưa học</option>
            <option value="low_progress">Có SV tiến độ thấp</option>
            <option value="low_grade">Có SV điểm thấp</option>
            <option value="deadline_late">Có SV trễ deadline quiz</option>
            <option value="has_alert">Có cảnh báo</option>
          </select>
        </label>
        <label className="academic-filter-search">Tìm giảng viên/lớp/môn
          <input className="input" value={search} onChange={(event) => { setSearch(event.target.value); setPage(1) }} placeholder="Tên GV, username, COM1071, lớp..." />
        </label>
      </div>

      <div className="academic-summary-strip training-summary-strip">
        <div><span>Giảng viên</span><b>{countLabel(summary.teacher_count)}</b><small>Theo bộ lọc</small></div>
        <div><span>Lớp</span><b>{countLabel(summary.class_count)}</b><small>Lượt lớp phân công</small></div>
        <div><span>Sinh viên</span><b>{countLabel(summary.student_count)}</b><small>Lượt SV theo lớp</small></div>
        <div><span>Đã đồng bộ CMS</span><b>{countLabel(summary.cms_synced_count)}</b><small>User CMS đã match</small></div>
        <div><span>Đã enroll</span><b>{countLabel(summary.learning_enrolled_count)}</b><small>Enrollment CMS</small></div>
        <div><span>Cần theo dõi</span><b>{countLabel(summary.risk_student_count)}</b><small>SV có cảnh báo học tập</small></div>
        <div><span>Trễ deadline</span><b>{countLabel(summary.deadline_late_student_count)}</b><small>{countLabel(summary.deadline_late_quiz_count)} lượt quiz trễ</small></div>
      </div>

      {message && <div className="academic-inline-error"><b>Thông báo</b><span>{message}</span></div>}

      <div className="table-wrap academic-table-wrap training-table-wrap">
        <table className="data-table academic-data-table training-teacher-table">
          <thead>
            <tr>
              <th>Giảng viên</th>
              <th>Quy mô đào tạo</th>
              <th>Đồng bộ CMS</th>
              <th>Tiến độ học</th>
              <th>Sinh viên học như nào</th>
              <th>Thao tác</th>
            </tr>
          </thead>
          <tbody>
            {loading && <tr><td colSpan={6}>Đang tải báo cáo...</td></tr>}
            {!loading && !items.length && <tr><td colSpan={6}>Chưa có dữ liệu theo bộ lọc hiện tại.</td></tr>}
            {!loading && items.map((item) => {
              const expanded = expandedTeacherId === item.teacher_id
              const statuses = item.status_counts || {}
              return <tr key={item.teacher_id} className={expanded ? 'expanded-row' : undefined}>
                <td>
                  <b>{item.teacher_name || item.teacher_username}</b>
                  <small>{item.teacher_username}{item.teacher_email ? ` · ${item.teacher_email}` : ''}</small>
                  <small>{item.branch?.toUpperCase() || 'N/A'}{item.campus ? ` · ${item.campus.toUpperCase()}` : ''}</small>
                </td>
                <td>
                  <b>{item.class_count} lớp · {item.subject_count} môn</b>
                  <small>{item.subject_codes?.slice(0, 6).join(', ') || 'N/A'}</small>
                  <small>{item.student_count} lượt SV · {item.unique_student_count} SV riêng biệt</small>
                  <small>Học lại: {countLabel(item.relearn_student_count)} SV · {countLabel(item.total_relearn_count)} lượt</small>
                </td>
                <td>
                  <span className="status-pill success">Đã đồng bộ CMS {ratioLabel(item.cms_synced_count, item.student_count)}</span>
                  <small>Đã enroll {ratioLabel(item.learning_enrolled_count, item.student_count)}</small>
                  {item.classes_without_course_count ? <small className="danger-text">{item.classes_without_course_count} lớp chưa map Course CMS</small> : <small>Course CMS đã map cho các lớp có dữ liệu</small>}
                </td>
                <td>
                  <b>Completion {percentLabel(item.learning_avg_progress_percent)}</b>
                  <small>Điểm tổng {grade10Label(item.learning_avg_grade_10)}</small>
                  <small>Có hoạt động {ratioLabel(item.learning_active_count, item.student_count)}</small>
                  <small>Trễ deadline {countLabel(item.deadline_late_student_count)} SV · {countLabel(item.deadline_late_quiz_count)} lượt quiz</small>
                </td>
                <td>
                  <span className={riskTone(item)}>{item.risk_student_count ? `${item.risk_student_count} SV cần theo dõi` : 'Ổn'}</span>
                  <small>Chưa học {countLabel(statuses.no_activity)} · Tiến độ thấp {countLabel(statuses.low_progress)} · Điểm thấp {countLabel(statuses.low_grade)}</small>
                  <small>Trễ deadline {countLabel(statuses.deadline_late)} SV</small>
                  <small>{alertText(item.learning_alerts)}</small>
                </td>
                <td>
                  <button className="btn secondary small" type="button" onClick={() => setExpandedTeacherId(expanded ? null : item.teacher_id)}>{expanded ? 'Thu gọn' : 'Xem lớp'}</button>
                </td>
              </tr>
            })}
          </tbody>
        </table>
      </div>

      {expandedTeacherId && <div className="training-class-detail-panel">
        {items.filter((item) => item.teacher_id === expandedTeacherId).map((item) => <div key={item.teacher_id} className="academic-unified-card nested-card">
          <div className="section-head list-card-head"><div><h3>Chi tiết lớp của {item.teacher_name}</h3><p>Mỗi lớp có Course completion, điểm tổng hệ 10 và deadline quiz tính theo 6 tuần đầu của block.</p></div></div>
          <div className="table-wrap academic-table-wrap dynamic-grade-table-wrap">
            {(() => {
              const columns = classComponentColumns(item)
              return <table className="data-table academic-data-table training-class-grade-table">
                <thead><tr><th>Lớp</th><th>Môn</th><th>Course CMS</th><th>Sinh viên</th><th>Học lại</th><th>Tiến độ học</th>{columns.map((column) => <th key={column.key} className="component-grade-th">{column.name}</th>)}<th>Deadline quiz</th><th>Cảnh báo</th></tr></thead>
                <tbody>
                  {item.classes.map((cls) => <tr key={cls.class_id}>
                    <td><b>{cls.class_code}</b><small>{cls.term_name}{cls.block_name ? ` · ${cls.block_name}` : ''}</small></td>
                    <td><b>{cls.subject_code}</b><small>{cls.subject_name}</small></td>
                    <td>{cls.openedx_course_id ? <><b>{cls.openedx_course_id}</b><small>{cls.openedx_mapping_source}</small></> : <span className="status-pill warning">Chưa map</span>}</td>
                    <td><b>{cls.student_count} SV</b><small>CMS {ratioLabel(cls.cms_synced_count, cls.student_count)} · Enroll {ratioLabel(cls.learning_enrolled_count, cls.student_count)}</small></td>
                    <td><b>{countLabel(cls.relearn_student_count)} SV</b><small>{countLabel(cls.total_relearn_count)} lượt học lại</small></td>
                    <td><b>Course completion {percentLabel(cls.learning_avg_progress_percent)}</b><small>Điểm tổng {grade10Label(cls.learning_avg_grade_10)}</small></td>
                    {columns.map((column) => <td key={`${cls.class_id}-${column.key}`} className="component-grade-cell"><b>{componentScoreText(classComponentScore(cls, column))}</b></td>)}
                    <td>
                      <b>{countLabel(cls.deadline_late_student_count)} SV trễ</b>
                      <small>{countLabel(cls.deadline_late_quiz_count)} lượt quiz trễ · Đã đến hạn {countLabel(cls.deadline_due_quiz_count)}/{countLabel(cls.deadline_quiz_count)} quiz</small>
                      <small>{cls.deadline_next_quiz_label ? `${cls.deadline_next_quiz_label}: ${cls.deadline_next_quiz_from_date || 'N/A'} → ${cls.deadline_next_quiz_due_date || 'N/A'}` : 'Đã qua lịch quiz hoặc chưa có Detailed grades'}</small>
                    </td>
                    <td><span className={cls.learning_alerts?.length ? 'status-pill warning' : 'status-pill success'}>{cls.learning_alerts?.length ? 'Có cảnh báo' : 'Ổn'}</span><small>{alertText(cls.learning_alerts)}</small></td>
                  </tr>)}
                  {!columns.length && <tr><td colSpan={9}>Chưa có cột Detailed grades. Hãy chạy Đồng bộ full CMS cho lớp sau khi Course CMS đã map đúng.</td></tr>}
                </tbody>
              </table>
            })()}
          </div>
        </div>)}
      </div>}

      <div className="pagination-row">
        <button className="btn secondary" type="button" disabled={page <= 1 || loading} onClick={() => setPage((value) => Math.max(1, value - 1))}>Trang trước</button>
        <span>Trang {page}/{totalPages}</span>
        <button className="btn secondary" type="button" disabled={page >= totalPages || loading} onClick={() => setPage((value) => value + 1)}>Trang sau</button>
      </div>
    </section>
  </div>
}
