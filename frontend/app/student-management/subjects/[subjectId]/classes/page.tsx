'use client'

import Link from 'next/link'
import { Suspense, useEffect, useMemo, useState } from 'react'
import { useParams, useSearchParams } from 'next/navigation'
import { useAppContext } from '../../../../../context/AppContext'
import { getAcademicBlocks, getAcademicSubjectClasses } from '../../../../../lib/api'
import { AcademicBlock, AcademicClass, AcademicLearningComponentScore } from '../../../../../types'

const PAGE_SIZE = 50

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
  const [summary, setSummary] = useState({ class_count: 0, student_count: 0, cms_synced_count: 0, learning_enrolled_count: 0, course_mapped_count: 0 })
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
      setSummary({
        class_count: Number(result.summary?.class_count ?? result.total ?? 0),
        student_count: Number(result.summary?.student_count ?? 0),
        cms_synced_count: Number(result.summary?.cms_synced_count ?? 0),
        learning_enrolled_count: Number(result.summary?.learning_enrolled_count ?? 0),
        course_mapped_count: Number(result.summary?.course_mapped_count ?? 0),
      })
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
  const listParams = new URLSearchParams()
  if (termId) listParams.set('term_id', termId)
  if (branch) listParams.set('branch', branch)
  if (campus) listParams.set('campus', campus)
  if (termName) listParams.set('term_name', termName)
  if (subjectCode) listParams.set('search', subjectCode)
  const listHref = `/student-management${listParams.toString() ? `?${listParams.toString()}` : ''}`

  function classDetailHref(item: AcademicClass) {
    const detailParams = new URLSearchParams()
    if (termId) detailParams.set('term_id', termId)
    if (branch) detailParams.set('branch', branch)
    if (campus) detailParams.set('campus', campus)
    detailParams.set('list_campus', campus || 'all')
    if (termName) detailParams.set('term_name', termName)
    if (subjectCode) detailParams.set('subject_code', subjectCode)
    if (subjectName) detailParams.set('subject_name', subjectName)
    detailParams.set('subject_id', subjectId)
    const qs = detailParams.toString()
    return `/student-management/classes/${encodeURIComponent(item.id)}${qs ? `?${qs}` : ''}`
  }

  return <div className="page-stack student-management-page academic-flow-page">
    <section className="card academic-unified-card">
      <div className="section-head list-card-head">
        <div>
          <h2>Lớp của môn {subjectCode || ''}</h2>
          <p>Phạm vi: {branch.toUpperCase()} · {termName || termId || 'Chưa rõ kỳ'} · {campus ? campus.toUpperCase() : 'Tất cả cơ sở'}. Admin xem toàn bộ; giảng viên xem lớp được phân công.</p>
        </div>
        <span className="status-pill neutral">{total} lớp</span>
      </div>

      <div className="teacher-breadcrumb-row clean-breadcrumb-row"><Link className="btn secondary small" href={listHref}>← Quay lại danh sách môn</Link></div>

      <div className="academic-filter-bar class-filter-bar">
        <label>Hệ
          <input className="input" value={branch.toUpperCase()} readOnly />
        </label>
        <label>Học kỳ
          <input className="input" value={termName || termId || 'Chưa rõ kỳ'} readOnly />
        </label>
        <label>Cơ sở
          <input className="input" value={campus ? campus.toUpperCase() : 'Tất cả cơ sở'} readOnly />
        </label>
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
        <div><span>Tổng số lớp</span><b>{summary.class_count || total}</b><small>Theo bộ lọc hiện tại</small></div>
        <div><span>Tổng số sinh viên</span><b>{summary.student_count}</b><small>Không phụ thuộc trang đang xem</small></div>
        <div><span>Đồng bộ CMS</span><b>{summary.cms_synced_count}</b><small>Sinh viên đã match user CMS</small></div>
        <div><span>Enrollment</span><b>{summary.learning_enrolled_count}</b><small>Đã enroll CMS</small></div>
        <div><span>Course CMS</span><b>{summary.course_mapped_count}/{summary.class_count || total}</b><small>Lớp có mapping hiệu lực</small></div>
      </div>

      {message && <div className="academic-inline-error"><b>Không tải được danh sách lớp</b><span>{message}</span><button className="btn secondary small" type="button" onClick={() => loadClasses()}>Thử lại</button></div>}

      <div className="table-wrap academic-table-wrap">
        <table className="data-table academic-data-table class-table">
          <thead><tr><th>STT</th><th>Lớp</th><th>Cơ sở / Block</th><th>Giảng viên</th><th>Sinh viên</th><th>Course CMS</th><th>Học tập CMS</th><th>Thao tác</th></tr></thead>
          <tbody>
            {loading && <tr><td colSpan={8}>Đang tải danh sách lớp...</td></tr>}
            {!loading && !classes.length && <tr><td colSpan={8}>Không có lớp phù hợp.</td></tr>}
            {classes.map((item, index) => <tr key={item.id}>
              <td className="stt-cell">{(page - 1) * PAGE_SIZE + index + 1}</td>
              <td className="main-entity-cell"><b>{item.class_code}</b><small>{item.class_name || item.subject_name}</small></td>
              <td><b>{item.campus?.toUpperCase() || '—'}</b><small>{item.block_name || '—'}</small></td>
              <td><b>{item.teacher_name || '—'}</b><small>{item.teacher_username || ''}</small></td>
              <td><b>{item.student_count}</b><small>{item.cms_synced_count || 0}/{item.student_count} đã đồng bộ CMS</small></td>
              <td><span className={mappingClass(item.openedx_mapping_source)}>{mappingSourceLabel(item.openedx_mapping_source)}</span><small>{item.openedx_course_id || 'N/A'}</small></td>
              <td className="learning-cell"><b>{item.learning_enrolled_count || 0}/{item.student_count} enroll</b><small>Dữ liệu: {item.learning_synced_count || 0}/{item.student_count} · Đã học: {item.learning_active_count || 0}/{item.student_count}</small><small>Tiến độ TB: {percentLabel(item.learning_avg_progress_percent)} · Điểm tổng TB: {percentLabel(item.learning_avg_grade_percent)}</small><small>TP: {componentSummaryLine(item.learning_component_summaries)}</small><small>{alertText(item.learning_alerts)}</small></td>
              <td><div className="teacher-row-actions-stack"><Link className="btn small primary" href={classDetailHref(item)}>Chi tiết lớp</Link><Link className="btn small secondary" href={`/analytics/learning?branch=${encodeURIComponent(branch)}&term_id=${encodeURIComponent(termId)}&campus=${encodeURIComponent(item.campus || campus || '')}&subject_id=${encodeURIComponent(subjectId)}&class_id=${encodeURIComponent(item.id)}&classification=all`}>Hành vi học</Link></div></td>
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
