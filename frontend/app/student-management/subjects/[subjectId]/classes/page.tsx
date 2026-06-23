'use client'

import Link from 'next/link'
import { Suspense, useEffect, useMemo, useState } from 'react'
import { useParams, useSearchParams } from 'next/navigation'
import { useAppContext } from '../../../../../context/AppContext'
import { getAcademicBlocks, getAcademicSubjectClasses } from '../../../../../lib/api'
import { AcademicBlock, AcademicClass, AcademicLearningComponentScore } from '../../../../../types'

const PAGE_SIZE = 50

function branchLabel(value?: string | null) { return value === 'ptcd' ? 'PTCĐ' : 'Poly' }
function mappingSourceLabel(source?: string | null) {
  if (source === 'subject_term_mapping') return 'Map theo môn'
  if (source === 'class_override') return 'Map riêng lớp'
  return 'Chưa map'
}
function mappingClass(source?: string | null) {
  if (source === 'subject_term_mapping') return 'status-pill success'
  if (source === 'class_override') return 'status-pill warning'
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

function SubjectClassesContent() {
  const params = useParams<{ subjectId: string }>()
  const searchParams = useSearchParams()
  const { authHeaders } = useAppContext()
  const headers = useMemo(() => authHeaders(), [authHeaders])
  const subjectId = decodeURIComponent(String(params.subjectId || ''))
  const termId = searchParams.get('term_id') || ''
  const branch = searchParams.get('branch') || 'poly'
  const campus = searchParams.get('campus') || ''
  const termName = searchParams.get('term_name') || ''
  const subjectCode = searchParams.get('subject_code') || ''
  const subjectName = searchParams.get('subject_name') || ''
  const [blocks, setBlocks] = useState<AcademicBlock[]>([])
  const [blockId, setBlockId] = useState('')
  const [search, setSearch] = useState('')
  const [learningStatus, setLearningStatus] = useState('all')
  const [classes, setClasses] = useState<AcademicClass[]>([])
  const [page, setPage] = useState(1)
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(false)
  const [message, setMessage] = useState('')

  useEffect(() => {
    if (!termId) { setBlocks([]); return }
    let cancelled = false
    getAcademicBlocks(headers, termId).then((items) => {
      if (cancelled) return
      setBlocks(items)
      if (blockId && !items.some((item) => item.id === blockId)) setBlockId('')
    }).catch(() => setBlocks([]))
    return () => { cancelled = true }
  }, [headers, termId, blockId])

  const loadClasses = async (cancelledRef?: { cancelled: boolean }) => {
    setLoading(true)
    setMessage('')
    try {
      const result = await getAcademicSubjectClasses(headers, subjectId, { termId, branch, campus, blockId, search, learningStatus, page, pageSize: PAGE_SIZE })
      if (cancelledRef?.cancelled) return
      setClasses(result.items)
      setTotal(result.total)
    } catch (error) {
      if (!cancelledRef?.cancelled) setMessage(error instanceof Error ? error.message : 'Không tải được danh sách lớp')
    } finally {
      if (!cancelledRef?.cancelled) setLoading(false)
    }
  }

  useEffect(() => {
    const cancelledRef = { cancelled: false }
    loadClasses(cancelledRef)
    return () => { cancelledRef.cancelled = true }
  }, [headers, subjectId, termId, branch, campus, blockId, search, learningStatus, page])

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE))
  const listHref = '/student-management'
  const aggregate = useMemo(() => classes.reduce((acc, item) => {
    acc.students += item.student_count || 0
    acc.synced += item.cms_synced_count || 0
    acc.enrolled += item.learning_enrolled_count || 0
    acc.mapped += item.openedx_course_id ? 1 : 0
    acc.alerts += item.learning_alerts?.length ? 1 : 0
    return acc
  }, { students: 0, synced: 0, enrolled: 0, mapped: 0, alerts: 0 }), [classes])

  function classDetailHref(item: AcademicClass) {
    const detailParams = new URLSearchParams()
    if (termId) detailParams.set('term_id', termId)
    if (branch) detailParams.set('branch', branch)
    if (campus) detailParams.set('campus', campus)
    if (termName) detailParams.set('term_name', termName)
    if (subjectCode) detailParams.set('subject_code', subjectCode)
    if (subjectName) detailParams.set('subject_name', subjectName)
    detailParams.set('subject_id', subjectId)
    const qs = detailParams.toString()
    return `/student-management/classes/${encodeURIComponent(item.id)}${qs ? `?${qs}` : ''}`
  }

  return <div className="page-stack student-management-page academic-flow-page">
    <section className="academic-flow-header">
      <nav className="academic-breadcrumb" aria-label="Student Management breadcrumb">
        <Link href={listHref}>Student Management</Link>
        <span>/</span>
        <Link href={listHref}>Môn</Link>
        <span>/</span>
        <b>{subjectCode || 'Môn đã chọn'}</b>
      </nav>
      <div className="academic-flow-title-row">
        <div>
          <p className="eyebrow">Danh sách lớp</p>
          <h1>{subjectCode || 'Môn'} · {subjectName || 'Danh sách lớp'}</h1>
          <p className="academic-flow-subtitle">{termName || 'Kỳ đã chọn'} · {branchLabel(branch)}{campus ? ` · ${campus.toUpperCase()}` : ' · Tất cả cơ sở'}</p>
        </div>
        <div className="hero-actions">
          <Link className="btn secondary" href={listHref}>← Quay lại danh sách môn</Link>
        </div>
      </div>
    </section>

    <section className="card academic-unified-card">
      <div className="section-head list-card-head">
        <div>
          <h2>Lớp của môn {subjectCode || ''}</h2>
          <p>Chỉ hiển thị lớp có sinh viên đã sync từ AP. Admin xem toàn bộ; giảng viên xem lớp được phân công.</p>
        </div>
        <span className="status-pill neutral">{total} lớp</span>
      </div>

      <div className="academic-filter-bar class-filter-bar">
        <label>Block
          <select className="input" value={blockId} onChange={(event) => { setBlockId(event.target.value); setPage(1) }}>
            <option value="">Tất cả block</option>
            {blocks.map((item) => <option key={item.id} value={item.id}>{item.block_name}</option>)}
          </select>
        </label>
        <label>Trạng thái học tập
          <select className="input" value={learningStatus} onChange={(event) => { setLearningStatus(event.target.value); setPage(1) }}>
            <option value="all">Tất cả lớp</option>
            <option value="cms_not_synced">Lớp chưa đồng bộ CMS</option>
            <option value="not_fully_enrolled">Lớp chưa đủ enrollment</option>
            <option value="no_learning_data">Lớp chưa có dữ liệu học tập</option>
            <option value="low_grade">Lớp có điểm thấp</option>
          </select>
        </label>
        <label className="academic-filter-search">Tìm lớp/giáo viên
          <input className="input" value={search} onChange={(event) => { setSearch(event.target.value); setPage(1) }} placeholder="BUS2015.01, tên GV..." />
        </label>
      </div>

      <div className="academic-summary-strip">
        <div><span>Lớp hiển thị</span><b>{total}</b><small>Theo bộ lọc hiện tại</small></div>
        <div><span>Sinh viên</span><b>{aggregate.students}</b><small>Tổng trong trang</small></div>
        <div><span>Đồng bộ CMS</span><b>{aggregate.synced}</b><small>Sinh viên đã match user CMS</small></div>
        <div><span>Enrollment</span><b>{aggregate.enrolled}</b><small>Đã enroll CMS</small></div>
        <div><span>Course CMS</span><b>{aggregate.mapped}/{classes.length}</b><small>Lớp có mapping hiệu lực</small></div>
      </div>

      {message && <div className="academic-inline-error"><b>Không tải được danh sách lớp</b><span>{message}</span><button className="btn secondary small" type="button" onClick={() => loadClasses()}>Thử lại</button></div>}

      <div className="table-wrap academic-table-wrap">
        <table className="data-table academic-data-table class-table">
          <thead><tr><th>Lớp</th><th>Cơ sở / Block</th><th>Giảng viên</th><th>Sinh viên</th><th>Course CMS</th><th>Học tập CMS</th><th>Thao tác</th></tr></thead>
          <tbody>
            {loading && <tr><td colSpan={7}>Đang tải danh sách lớp...</td></tr>}
            {!loading && !classes.length && <tr><td colSpan={7}>Không có lớp phù hợp.</td></tr>}
            {classes.map((item) => <tr key={item.id}>
              <td className="main-entity-cell"><b>{item.class_code}</b><small>{item.class_name || item.subject_name}</small></td>
              <td><b>{item.campus?.toUpperCase() || '—'}</b><small>{item.block_name || '—'}</small></td>
              <td><b>{item.teacher_name || '—'}</b><small>{item.teacher_username || ''}</small></td>
              <td><b>{item.student_count}</b><small>{item.cms_synced_count || 0}/{item.student_count} đã đồng bộ CMS</small></td>
              <td><span className={mappingClass(item.openedx_mapping_source)}>{mappingSourceLabel(item.openedx_mapping_source)}</span><small>{item.openedx_course_id || 'N/A'}</small></td>
              <td className="learning-cell"><b>{item.learning_enrolled_count || 0}/{item.student_count} enroll</b><small>Dữ liệu: {item.learning_synced_count || 0}/{item.student_count} · Đã học: {item.learning_active_count || 0}/{item.student_count}</small><small>Tiến độ TB: {percentLabel(item.learning_avg_progress_percent)} · Điểm tổng TB: {percentLabel(item.learning_avg_grade_percent)}</small><small>TP: {componentSummaryLine(item.learning_component_summaries)}</small><small>{alertText(item.learning_alerts)}</small></td>
              <td><Link className="btn small primary" href={classDetailHref(item)}>Chi tiết lớp</Link></td>
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

export default function SubjectClassesPage() {
  return <Suspense fallback={<div className="card">Đang tải màn lớp...</div>}><SubjectClassesContent /></Suspense>
}
