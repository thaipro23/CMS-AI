'use client'

import Link from 'next/link'
import { useEffect, useMemo, useState } from 'react'
import { useParams } from 'next/navigation'
import { useAppContext } from '../../../../context/AppContext'
import {
  getAcademicClass,
  getAcademicClassMappingSummary,
  getAcademicClassStudents,
  checkAcademicClassCmsSync,
} from '../../../../lib/api'
import { AcademicClass, AcademicMappingSummary, AcademicStudent } from '../../../../types'

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

export default function ClassDetailPage() {
  const params = useParams<{ classId: string }>()
  const classId = decodeURIComponent(String(params.classId || ''))
  const { authHeaders } = useAppContext()
  const headers = useMemo(() => authHeaders(), [authHeaders])
  const jsonHeaders = useMemo(() => authHeaders(true), [authHeaders])
  const [classInfo, setClassInfo] = useState<AcademicClass | null>(null)
  const [students, setStudents] = useState<AcademicStudent[]>([])
  const [summary, setSummary] = useState<AcademicMappingSummary | null>(null)
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(false)
  const [checking, setChecking] = useState(false)
  const [message, setMessage] = useState('')

  const refreshStudents = async () => {
    const [studentPage, nextSummary] = await Promise.all([
      getAcademicClassStudents(headers, classId, { search, page, pageSize: PAGE_SIZE }),
      getAcademicClassMappingSummary(headers, classId),
    ])
    setStudents(studentPage.items)
    setTotal(studentPage.total)
    setSummary(nextSummary)
  }

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    Promise.all([getAcademicClass(headers, classId), getAcademicClassStudents(headers, classId, { search, page, pageSize: PAGE_SIZE }), getAcademicClassMappingSummary(headers, classId)])
      .then(([detail, studentPage, nextSummary]) => {
        if (cancelled) return
        setClassInfo(detail)
        setStudents(studentPage.items)
        setTotal(studentPage.total)
        setSummary(nextSummary)
      })
      .catch((error) => { if (!cancelled) setMessage(error instanceof Error ? error.message : 'Không tải được chi tiết lớp') })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [headers, classId, search, page])

  const runCmsSyncCheck = async () => {
    setChecking(true)
    setMessage('')
    try {
      const result = await checkAcademicClassCmsSync(jsonHeaders, classId, { force: true, limit: 5000 })
      setMessage(`Kiểm tra đồng bộ CMS hoàn tất: ${result.updated}/${result.total} sinh viên được cập nhật.`)
      await refreshStudents()
    } catch (error) {
      setMessage(error instanceof Error ? `${error.message}. Kiểm tra lại LMS Student Insight plugin/HMAC nếu API CMS chưa sẵn sàng.` : 'Kiểm tra đồng bộ CMS thất bại')
    } finally {
      setChecking(false)
    }
  }

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE))
  const counts = summary?.counts || {}
  const matched = counts.matched || 0
  const notChecked = counts.not_checked || 0
  const notSynced = Math.max(0, (summary?.total || 0) - matched - notChecked)

  return <div className="page-stack student-management-page">
    <section className="card hero-card compact-hero">
      <div>
        <p className="eyebrow">Student Management / Chi tiết lớp</p>
        <h1>{classInfo?.class_code || 'Chi tiết lớp'}</h1>
        <p>{classInfo?.subject_code} · {classInfo?.subject_name} · {classInfo?.term_name} · {branchLabel(classInfo?.branch)} · {classInfo?.campus?.toUpperCase() || '—'}</p>
      </div>
      <div className="hero-actions">
        <button className="btn primary" type="button" disabled={checking} onClick={runCmsSyncCheck}>{checking ? 'Đang kiểm tra...' : 'Kiểm tra đồng bộ CMS'}</button>
        <Link className="btn secondary" href="/student-management">Về màn môn</Link>
      </div>
    </section>

    <section className="summary-grid grid-4">
      <div className="metric-card"><span>Tổng sinh viên AP</span><b>{summary?.total ?? classInfo?.student_count ?? 0}</b><small>Trong lớp</small></div>
      <div className="metric-card"><span>Đã đồng bộ CMS</span><b>{matched}</b><small>User tồn tại theo username AP</small></div>
      <div className="metric-card"><span>Chưa đồng bộ/lỗi</span><b>{notSynced}</b><small>Missing, inactive hoặc cần xử lý</small></div>
      <div className="metric-card"><span>Course CMS</span><b>{classInfo?.openedx_course_id ? 'Đã map' : 'Chưa map'}</b><small>{mappingSourceLabel(classInfo?.openedx_mapping_source)}</small></div>
    </section>

    <section className="card">
      <div className="section-head">
        <div><h2>Thông tin lớp</h2><p>Lớp kế thừa mapping course từ màn môn/kỳ/hệ, không map riêng ở đây.</p></div>
      </div>
      <div className="academic-detail-grid">
        <div><span>Mã lớp</span><b>{classInfo?.class_code || '—'}</b></div>
        <div><span>Block</span><b>{classInfo?.block_name || '—'}</b></div>
        <div><span>Giảng viên</span><b>{classInfo?.teacher_name || classInfo?.teacher_username || '—'}</b></div>
        <div><span>Course CMS</span><b>{classInfo?.openedx_course_id || 'Chưa map ở màn môn'}</b></div>
      </div>
      {message && <p className="form-message">{message}</p>}
    </section>

    <section className="card">
      <div className="section-head">
        <div><h2>Danh sách sinh viên</h2><p>Trạng thái đồng bộ CMS được kiểm tra bằng AP username = CMS/Open edX username.</p></div>
        <input className="input compact-input" value={search} onChange={(event) => { setSearch(event.target.value); setPage(1) }} placeholder="Tìm mã SV, username, họ tên..." />
      </div>
      <div className="table-wrap">
        <table className="data-table">
          <thead><tr><th>Sinh viên</th><th>Username AP</th><th>Email</th><th>Username CMS</th><th>Trạng thái</th></tr></thead>
          <tbody>
            {loading && <tr><td colSpan={5}>Đang tải sinh viên...</td></tr>}
            {!loading && !students.length && <tr><td colSpan={5}>Không có sinh viên phù hợp.</td></tr>}
            {students.map((student) => <tr key={student.id}>
              <td><b>{student.student_code || '—'}</b><small>{student.full_name}</small></td>
              <td><b>{student.username}</b></td>
              <td>{student.email || '—'}</td>
              <td>{student.openedx_username || '—'}</td>
              <td><span className={cmsSyncClass(student.match_status)}>{cmsSyncLabel(student.match_status)}</span><small>{student.last_resolved_at ? `Kiểm tra: ${new Date(student.last_resolved_at).toLocaleString('vi-VN')}` : ''}</small></td>
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
