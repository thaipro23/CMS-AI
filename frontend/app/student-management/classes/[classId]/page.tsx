'use client'

import Link from 'next/link'
import { useEffect, useMemo, useState } from 'react'
import { useParams } from 'next/navigation'
import { useAppContext } from '../../../../context/AppContext'
import {
  getAcademicClass,
  getAcademicClassMappingSummary,
  getAcademicClassLearningSummary,
  getAcademicClassStudents,
  enqueueAcademicClassCmsSyncJob,
  enqueueAcademicClassEnrollmentSyncJob,
  enqueueAcademicClassLearningSyncJob,
  getAcademicClassSyncJob,
} from '../../../../lib/api'
import { AcademicClass, AcademicClassSyncJob, AcademicLearningSummary, AcademicMappingSummary, AcademicStudent } from '../../../../types'

const PAGE_SIZE = 50

function branchLabel(value?: string | null) { return value === 'ptcd' ? 'PTCĐ' : 'Poly' }
function cmsSyncLabel(status?: string | null) {
  const value = (status || 'not_checked').toLowerCase()
  if (value === 'matched') return 'Đã đồng bộ CMS'
  if (value === 'inactive') return 'User CMS inactive'
  if (value === 'missing') return 'Chưa có trên CMS'
  if (value === 'ambiguous') return 'Trùng user CMS'
  if (value === 'manual_required') return 'Cần xử lý tay'
  return 'Chưa kiểm tra'
}
function cmsSyncClass(status?: string | null) {
  const value = (status || 'not_checked').toLowerCase()
  if (value === 'matched') return 'status-pill success'
  if (['inactive', 'missing', 'ambiguous'].includes(value)) return 'status-pill danger'
  if (value === 'manual_required') return 'status-pill warning'
  return 'status-pill neutral'
}
function mappingSourceLabel(source?: string | null) {
  if (source === 'subject_term_mapping') return 'Kế thừa từ môn'
  if (source === 'class_override') return 'Map riêng lớp'
  return 'Chưa map'
}

function percentLabel(value?: number | null) {
  if (typeof value !== 'number' || Number.isNaN(value)) return 'N/A'
  return `${Math.round(value * 10) / 10}%`
}

function learningStatusLabel(value?: string | null) {
  const status = (value || 'not_synced').toLowerCase()
  if (status === 'cms_not_synced') return 'Chưa đồng bộ CMS'
  if (status === 'not_synced') return 'Chưa cập nhật học tập'
  if (status === 'not_enrolled') return 'Chưa enroll'
  if (status === 'no_activity') return 'Chưa vào học'
  if (status === 'low_progress') return 'Tiến độ thấp'
  if (status === 'low_grade') return 'Điểm thấp'
  if (status === 'sync_error') return 'Lỗi dữ liệu'
  if (status === 'good') return 'Hoàn thành tốt'
  if (status === 'in_progress') return 'Đang học'
  return 'Chưa cập nhật'
}

function learningStatusClass(value?: string | null) {
  const status = (value || 'not_synced').toLowerCase()
  if (['good', 'in_progress'].includes(status)) return 'status-pill success'
  if (['low_progress', 'low_grade', 'not_enrolled', 'cms_not_synced', 'sync_error'].includes(status)) return 'status-pill danger'
  if (status === 'no_activity') return 'status-pill warning'
  return 'status-pill neutral'
}

function componentScoreText(score: { percent?: number | null; earned?: number | null; possible?: number | null }) {
  if (typeof score.percent === 'number') return percentLabel(score.percent)
  if (typeof score.earned === 'number' && typeof score.possible === 'number') return `${Math.round(score.earned * 100) / 100}/${Math.round(score.possible * 100) / 100}`
  return 'N/A'
}
function enrollmentLabel(value?: string | null) {
  const status = (value || 'unknown').toLowerCase()
  if (status === 'enrolled') return 'Đã enroll'
  if (status === 'inactive') return 'Enroll inactive'
  if (status === 'not_enrolled') return 'Chưa enroll'
  if (status === 'missing_user') return 'Chưa có user CMS'
  return 'Chưa cập nhật'
}
function enrollmentClass(value?: string | null) {
  const status = (value || 'unknown').toLowerCase()
  if (status === 'enrolled') return 'status-pill success'
  if (['not_enrolled', 'missing_user', 'inactive'].includes(status)) return 'status-pill danger'
  return 'status-pill neutral'
}

export default function ClassDetailPage() {
  const params = useParams<{ classId: string }>()
  const classId = decodeURIComponent(String(params.classId || ''))
  const { authHeaders } = useAppContext()
  const headers = useMemo(() => authHeaders(), [authHeaders])
  const jsonHeaders = useMemo(() => authHeaders(true), [authHeaders])
  const [classInfo, setClassInfo] = useState<AcademicClass | null>(null)
  const [students, setStudents] = useState<AcademicStudent[]>([])
  const [summary, setSummary] = useState<AcademicMappingSummary | null>(null)
  const [learningSummary, setLearningSummary] = useState<AcademicLearningSummary | null>(null)
  const [search, setSearch] = useState('')
  const [learningStatus, setLearningStatus] = useState('all')
  const [page, setPage] = useState(1)
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(false)
  const [checking, setChecking] = useState(false)
  const [syncingEnrollment, setSyncingEnrollment] = useState(false)
  const [syncingLearning, setSyncingLearning] = useState(false)
  const [message, setMessage] = useState('')
  const [errorModal, setErrorModal] = useState('')
  const [activeJob, setActiveJob] = useState<AcademicClassSyncJob | null>(null)

  const refreshStudents = async () => {
    const [studentPage, nextSummary, nextLearning] = await Promise.all([
      getAcademicClassStudents(headers, classId, { search, learningStatus, page, pageSize: PAGE_SIZE }),
      getAcademicClassMappingSummary(headers, classId),
      getAcademicClassLearningSummary(headers, classId),
    ])
    setStudents(studentPage.items)
    setTotal(studentPage.total)
    setSummary(nextSummary)
    setLearningSummary(nextLearning)
  }

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    Promise.all([getAcademicClass(headers, classId), getAcademicClassStudents(headers, classId, { search, learningStatus, page, pageSize: PAGE_SIZE }), getAcademicClassMappingSummary(headers, classId), getAcademicClassLearningSummary(headers, classId)])
      .then(([detail, studentPage, nextSummary, nextLearning]) => {
        if (cancelled) return
        setClassInfo(detail)
        setStudents(studentPage.items)
        setTotal(studentPage.total)
        setSummary(nextSummary)
        setLearningSummary(nextLearning)
      })
      .catch((error) => { if (!cancelled) setErrorModal(error instanceof Error ? error.message : 'Không tải được chi tiết lớp') })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [headers, classId, search, learningStatus, page])


  const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms))

  const waitForSyncJob = async (job: AcademicClassSyncJob): Promise<AcademicClassSyncJob> => {
    setActiveJob(job)
    let current = job
    for (let attempt = 0; attempt < 180; attempt += 1) {
      if (['completed', 'failed'].includes(String(current.status || '').toLowerCase())) return current
      await sleep(1500)
      current = await getAcademicClassSyncJob(headers, classId, current.id)
      setActiveJob(current)
    }
    throw new Error('Job đồng bộ đang chạy quá lâu. Vui lòng mở lại trang hoặc kiểm tra worker Celery.')
  }

  const runCmsSyncCheck = async () => {
    setChecking(true)
    setMessage('')
    try {
      const queued = await enqueueAcademicClassCmsSyncJob(jsonHeaders, classId, { force: true, limit: 500 })
      const finished = await waitForSyncJob(queued)
      if (finished.status === 'failed') throw new Error(finished.error_message || 'Đồng bộ CMS thất bại')
      const result = finished.result_json as any
      const teacherMsg = result?.teachers?.total ? ` Giảng viên: ${result.teachers.updated || 0}/${result.teachers.total} được kiểm tra/tạo tài khoản CMS.` : ''
      const enrollMsg = result?.enrollment?.ok ? ` Course CMS: ${result.enrollment.updated}/${result.enrollment.total} sinh viên đã enroll; ${result.enrollment.teachers?.updated || 0}/${result.enrollment.teachers?.total || 0} giảng viên được gán vào course.` : ''
      setMessage(`Kiểm tra đồng bộ CMS hoàn tất: ${result?.updated || 0}/${result?.total || 0} sinh viên được cập nhật.${teacherMsg}${enrollMsg}`)
      await refreshStudents()
    } catch (error) {
      setErrorModal(error instanceof Error ? `${error.message}. Kiểm tra lại LMS Student Insight plugin/HMAC nếu API CMS chưa sẵn sàng.` : 'Kiểm tra đồng bộ CMS thất bại')
    } finally {
      setChecking(false)
      setActiveJob(null)
    }
  }


  const runEnrollmentSync = async () => {
    setSyncingEnrollment(true)
    setMessage('')
    try {
      const queued = await enqueueAcademicClassEnrollmentSyncJob(jsonHeaders, classId, { force: true, limit: 500 })
      const finished = await waitForSyncJob(queued)
      if (finished.status === 'failed') throw new Error(finished.error_message || 'Enrollment CMS thất bại')
      const result = finished.result_json as any
      setMessage(`Course CMS hoàn tất: ${result?.updated || 0}/${result?.total || 0} sinh viên được enroll; ${result?.teachers?.updated || 0}/${result?.teachers?.total || 0} giảng viên được tạo/gán Course Staff.`)
      await refreshStudents()
    } catch (error) {
      setErrorModal(error instanceof Error ? `${error.message}. Chỉ sinh viên đã đồng bộ CMS và lớp đã map Course CMS mới được enroll.` : 'Enrollment CMS thất bại')
    } finally {
      setSyncingEnrollment(false)
      setActiveJob(null)
    }
  }

  const runLearningSync = async () => {
    setSyncingLearning(true)
    setMessage('')
    try {
      const queued = await enqueueAcademicClassLearningSyncJob(jsonHeaders, classId, { force: true, limit: 500 })
      const finished = await waitForSyncJob(queued)
      if (finished.status === 'failed') throw new Error(finished.error_message || 'Cập nhật tiến độ/điểm CMS thất bại')
      const result = finished.result_json as any
      setMessage(`Cập nhật tiến độ/điểm CMS hoàn tất: ${result?.updated || 0}/${result?.total || 0} sinh viên được cập nhật.`)
      await refreshStudents()
    } catch (error) {
      setErrorModal(error instanceof Error ? `${error.message}. Kiểm tra Course CMS mapping và Student Insight plugin/HMAC.` : 'Cập nhật tiến độ/điểm CMS thất bại')
    } finally {
      setSyncingLearning(false)
      setActiveJob(null)
    }
  }

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE))
  const counts = summary?.counts || {}
  const matched = counts.matched || 0
  const notChecked = counts.not_checked || 0
  const needsCmsAction = Math.max(0, (summary?.total || 0) - matched)
  const syncIssue = Math.max(0, (summary?.total || 0) - matched - notChecked)

  return <div className="page-stack student-management-page">
    <section className="card hero-card compact-hero">
      <div>
        <p className="eyebrow">Student Management / Chi tiết lớp</p>
        <h1>{classInfo?.class_code || 'Chi tiết lớp'}</h1>
        <p>{classInfo?.subject_code} · {classInfo?.subject_name} · {classInfo?.term_name} · {branchLabel(classInfo?.branch)} · {classInfo?.campus?.toUpperCase() || '—'}</p>
      </div>
      <div className="hero-actions">
        <Link className="btn secondary" href="/student-management">Về màn môn</Link>
      </div>
    </section>

    <section className="card">
      <div className="section-head">
        <div><h2>Thao tác học tập CMS</h2><p>Các nút dưới đây mới gọi CMS/Open edX. Mở trang hoặc F5 chỉ đọc dữ liệu đã lưu trong AI Server.</p></div>
      </div>
      <div className="toolbar-actions">
        <button className="btn primary" type="button" disabled={checking} onClick={runCmsSyncCheck}>{checking ? 'Đang đồng bộ...' : 'Đồng bộ CMS'}</button>
        <button className="btn secondary" type="button" disabled={syncingEnrollment || !classInfo?.openedx_course_id} onClick={runEnrollmentSync}>{syncingEnrollment ? 'Đang xử lý...' : 'Enrollment Course CMS'}</button>
        <button className="btn secondary" type="button" disabled={syncingLearning || !classInfo?.openedx_course_id} onClick={runLearningSync}>{syncingLearning ? 'Đang cập nhật...' : 'Cập nhật tiến độ/điểm'}</button>
        <button className="btn secondary" type="button" disabled={loading} onClick={() => refreshStudents().catch((error) => setErrorModal(error instanceof Error ? error.message : 'Không làm mới được dữ liệu'))}>Làm mới dữ liệu</button>
      </div>
      {activeJob && <div className="sync-job-status">
        <b>{activeJob.progress_label || 'Đang xử lý job đồng bộ...'}</b>
        <small>Trạng thái: {activeJob.status} · Tiến độ: {activeJob.progress_current || 0}/{activeJob.progress_total || 100}</small>
        <div className="progress-track"><span style={{ width: `${Math.min(100, Math.round(((activeJob.progress_current || 0) / Math.max(1, activeJob.progress_total || 100)) * 100))}%` }} /></div>
      </div>}
      {message && <p className="form-message">{message}</p>}
    </section>

    <section className="summary-grid grid-4">
      <div className="metric-card"><span>Tổng sinh viên AP</span><b>{summary?.total ?? classInfo?.student_count ?? 0}</b><small>Trong lớp</small></div>
      <div className="metric-card"><span>Đã đồng bộ CMS</span><b>{matched}</b><small>User tồn tại theo username AP</small></div>
      <div className="metric-card"><span>Chưa kiểm tra CMS</span><b>{notChecked}</b><small>Chưa chạy kiểm tra đồng bộ</small></div>
      <div className="metric-card"><span>Cần xử lý CMS</span><b>{needsCmsAction}</b><small>Lỗi/không match: {syncIssue}</small></div>
      <div className="metric-card"><span>Course CMS</span><b>{classInfo?.openedx_course_id ? 'Đã map' : 'Chưa map'}</b><small>{mappingSourceLabel(classInfo?.openedx_mapping_source)}</small></div>
    </section>

    <section className="summary-grid grid-4">
      <div className="metric-card"><span>Đã enroll CMS</span><b>{learningSummary?.counts?.enrolled || 0}</b><small>Course: {learningSummary?.openedx_course_id || classInfo?.openedx_course_id || 'N/A'}</small></div>
      <div className="metric-card"><span>Đã vào học</span><b>{learningSummary?.active_count || 0}</b><small>Có progress, điểm hoặc hoạt động CMS</small></div>
      <div className="metric-card"><span>Tiến độ TB</span><b>{percentLabel(learningSummary?.avg_progress_percent)}</b><small>Dữ liệu từ CMS/Open edX</small></div>
      <div className="metric-card"><span>Điểm TB</span><b>{percentLabel(learningSummary?.avg_grade_percent)}</b><small>{learningSummary?.last_synced_at ? `Cập nhật: ${new Date(learningSummary.last_synced_at).toLocaleString('vi-VN')}` : 'Chưa cập nhật'}</small></div>
    </section>

    <section className="card">
      <div className="section-head">
        <div><h2>Điểm thành phần của lớp</h2><p>Trung bình từng subsection/component lấy từ CMS/Open edX. Nếu Course chưa lưu subsection grade, hệ thống hiển thị N/A thay vì để trống.</p></div>
      </div>
      <div className="component-score-grid">
        {learningSummary?.component_summaries?.length ? learningSummary.component_summaries.map((item) => <div className="component-score-card" key={item.key || item.name}>
          <span>{item.name}</span>
          <b>{componentScoreText(item)}</b>
          <small>{item.source || item.category || 'Điểm thành phần'}</small>
        </div>) : <div className="component-score-card"><span>Điểm thành phần</span><b>N/A</b><small>CMS/Open edX chưa có subsection/component grade</small></div>}
      </div>
    </section>

    <section className="card">
      <div className="section-head">
        <div><h2>Thông tin lớp</h2><p>Lớp kế thừa mapping course từ màn môn/kỳ/hệ. Khi kiểm tra đồng bộ CMS xong, hệ thống tự tạo tài khoản CMS nếu thiếu, enroll sinh viên và gán giảng viên làm Course Staff.</p></div>
      </div>
      <div className="academic-detail-grid">
        <div><span>Mã lớp</span><b>{classInfo?.class_code || '—'}</b></div>
        <div><span>Block</span><b>{classInfo?.block_name || '—'}</b></div>
        <div><span>Giảng viên</span><b>{classInfo?.teacher_name || classInfo?.teacher_username || '—'}</b></div>
        <div><span>Course CMS</span><b>{classInfo?.openedx_course_id || 'N/A'}</b></div>
      </div>
    </section>

    <section className="card">
      <div className="section-head">
        <div><h2>Danh sách sinh viên</h2><p>Trạng thái đồng bộ CMS, enrollment, tiến độ và điểm thành phần theo từng sinh viên.</p></div>
        <div className="toolbar-actions">
          <select className="input compact-input" value={learningStatus} onChange={(event) => { setLearningStatus(event.target.value); setPage(1) }}>
            <option value="all">Tất cả trạng thái</option>
            <option value="cms_not_synced">Chưa đồng bộ CMS</option>
            <option value="not_enrolled">Chưa enroll</option>
            <option value="no_activity">Chưa vào học</option>
            <option value="low_progress">Tiến độ thấp</option>
            <option value="low_grade">Điểm thấp</option>
            <option value="sync_error">Lỗi dữ liệu</option>
          </select>
          <input className="input compact-input" value={search} onChange={(event) => { setSearch(event.target.value); setPage(1) }} placeholder="Tìm mã SV, username, họ tên..." />
        </div>
      </div>
      <div className="table-wrap">
        <table className="data-table">
          <thead><tr><th>Sinh viên</th><th>Username AP</th><th>Email</th><th>Username CMS</th><th>Đồng bộ CMS</th><th>Học tập CMS</th><th>Điểm tổng</th><th>Điểm thành phần</th></tr></thead>
          <tbody>
            {loading && <tr><td colSpan={8}>Đang tải sinh viên...</td></tr>}
            {!loading && !students.length && <tr><td colSpan={8}>Không có sinh viên phù hợp.</td></tr>}
            {students.map((student) => <tr key={student.id}>
              <td><b>{student.student_code || '—'}</b><small>{student.full_name}</small></td>
              <td><b>{student.username}</b></td>
              <td>{student.email || 'N/A'}</td>
              <td>{student.openedx_username || 'N/A'}</td>
              <td><span className={cmsSyncClass(student.match_status)}>{cmsSyncLabel(student.match_status)}</span><small>{student.last_resolved_at ? `Kiểm tra: ${new Date(student.last_resolved_at).toLocaleString('vi-VN')}` : ''}</small></td>
              <td><span className={enrollmentClass(student.learning_enrollment_status)}>{enrollmentLabel(student.learning_enrollment_status)}</span><small>Tiến độ: {percentLabel(student.learning_progress_percent)}</small><span className={learningStatusClass(student.learning_status)}>{learningStatusLabel(student.learning_status)}</span></td>
              <td><b>{percentLabel(student.learning_grade_percent)}</b><small>{student.learning_last_synced_at ? `Cập nhật: ${new Date(student.learning_last_synced_at).toLocaleString('vi-VN')}` : ''}</small></td>
              <td><div className="component-score-list">{student.learning_component_scores?.length ? student.learning_component_scores.slice(0, 5).map((score) => <span className="component-score-chip" key={score.key || score.name}><b>{score.name}</b> {componentScoreText(score)}</span>) : <span className="muted">N/A</span>}</div></td>
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
    {errorModal && <div className="modal-backdrop">
      <div className="card bank-modal academic-confirm-modal">
        <div className="section-head"><div><h2>Không thực hiện được thao tác</h2><p>{errorModal}</p></div></div>
        <div className="modal-actions"><button className="btn primary" type="button" onClick={() => setErrorModal('')}>Đã hiểu</button></div>
      </div>
    </div>}
  </div>
}
