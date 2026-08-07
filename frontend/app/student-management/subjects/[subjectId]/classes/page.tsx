'use client'

import Link from 'next/link'
import { Suspense, useEffect, useMemo, useState } from 'react'
import { useParams, useSearchParams } from 'next/navigation'
import { useAppContext } from '../../../../../context/AppContext'
import { getAcademicBlocks, getAcademicSubjectClasses } from '../../../../../lib/api'
import { AcademicBlock, AcademicClass } from '../../../../../types'
import { PageRoot } from '../../../../../components/layout/PageHeader'
import { EnterpriseScreenHeader } from '../../../../../components/layout/EnterpriseDesignContract'
import { EnterpriseDataTable, EnterpriseTableColumn } from '../../../../../components/table/EnterpriseDataTable'
import { InlineNotice, InlineNoticeData, noticeError } from '../../../../../components/ui/InlineNotice'
import { TrainingContextChips, TrainingKpiStrip } from '../../../../../components/training/TrainingWorkspace'
import { useAcademicTableState } from '../../../../../hooks/useAcademicTableState'
import { useDebouncedValue } from '../../../../../lib/useDebouncedValue'

function mappingSourceLabel(source?: string | null) {
  if (source === 'subject_term_mapping') return 'Ghép theo môn'
  if (source === 'class_override') return 'Map riêng lớp'
  return 'Chưa ghép'
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

function SubjectClassesContent() {
  const params = useParams<{ subjectId: string }>()
  const searchParams = useSearchParams()
  const { authHeaders } = useAppContext()
  const headers = useMemo(() => authHeaders(), [authHeaders])
  const subjectId = decodeURIComponent(String(params.subjectId || ''))
  const termName = searchParams.get('term_name') || ''
  const subjectCode = searchParams.get('subject_code') || ''
  const subjectName = searchParams.get('subject_name') || ''
  const platform = searchParams.get('platform') === 'udemy' ? 'udemy' : 'cms'
  const isCms = platform === 'cms'
  const platformLabel = isCms ? 'CMS' : 'Udemy'
  const { state, update } = useAcademicTableState({ branch: 'poly', status: 'all', pageSize: 50 })
  const { termId, branch, campus, blockId, q, status, page, pageSize, density } = state
  const debouncedSearch = useDebouncedValue(q, 350)
  const [blocks, setBlocks] = useState<AcademicBlock[]>([])
  const [classes, setClasses] = useState<AcademicClass[]>([])
  const [summary, setSummary] = useState({ class_count: 0, student_count: 0, cms_synced_count: 0, learning_enrolled_count: 0, course_mapped_count: 0, udemy_progress_student_count: 0, udemy_progress_late_count: 0, udemy_progress_average_percent: null as number | null })
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(false)
  const [message, setMessage] = useState<InlineNoticeData | null>(null)

  useEffect(() => {
    if (!termId) { setBlocks([]); return }
    let cancelled = false
    getAcademicBlocks(headers, termId).then((items) => {
      if (cancelled) return
      setBlocks(items)
      if (blockId && !items.some((item) => item.id === blockId)) update({ blockId: '' })
    }).catch(() => setBlocks([]))
    return () => { cancelled = true }
  }, [headers, termId, blockId, update])

  const loadClasses = async (cancelledRef?: { cancelled: boolean }) => {
    setLoading(true)
    setMessage(null)
    try {
      const result = await getAcademicSubjectClasses(headers, subjectId, {
        termId,
        branch,
        campus,
        blockId,
        search: debouncedSearch,
        learningStatus: status,
        learningPlatform: platform,
        page,
        pageSize,
      })
      if (cancelledRef?.cancelled) return
      setClasses(result.items)
      setTotal(result.total)
      setSummary({
        class_count: Number(result.summary?.class_count ?? result.total ?? 0),
        student_count: Number(result.summary?.student_count ?? 0),
        cms_synced_count: Number(result.summary?.cms_synced_count ?? 0),
        learning_enrolled_count: Number(result.summary?.learning_enrolled_count ?? 0),
        course_mapped_count: Number(result.summary?.course_mapped_count ?? 0),
        udemy_progress_student_count: Number(result.summary?.udemy_progress_student_count ?? 0),
        udemy_progress_late_count: Number(result.summary?.udemy_progress_late_count ?? 0),
        udemy_progress_average_percent: typeof result.summary?.udemy_progress_average_percent === 'number' ? result.summary.udemy_progress_average_percent : null,
      })
    } catch (error) {
      if (!cancelledRef?.cancelled) setMessage({ ...noticeError(error, 'Không tải được danh sách lớp.'), onRetry: () => loadClasses() })
    } finally {
      if (!cancelledRef?.cancelled) setLoading(false)
    }
  }

  useEffect(() => {
    const cancelledRef = { cancelled: false }
    loadClasses(cancelledRef)
    return () => { cancelledRef.cancelled = true }
  }, [headers, subjectId, termId, branch, campus, blockId, debouncedSearch, status, page, pageSize, platform])

  const totalPages = Math.max(1, Math.ceil(total / pageSize))
  useEffect(() => {
    if (page > totalPages) update({ page: totalPages }, { resetPage: false })
  }, [page, totalPages, update])

  const listParams = new URLSearchParams()
  if (termId) listParams.set('term_id', termId)
  if (branch) listParams.set('branch', branch)
  if (campus) listParams.set('campus', campus)
  if (termName) listParams.set('term_name', termName)
  if (subjectCode) listParams.set('q', subjectCode)
  listParams.set('platform', platform)
  const listHref = `/student-management/${platform}${listParams.toString() ? `?${listParams.toString()}` : ''}`

  const classDetailHref = (item: AcademicClass) => {
    const detailParams = new URLSearchParams()
    if (termId) detailParams.set('term_id', termId)
    if (branch) detailParams.set('branch', branch)
    if (campus) detailParams.set('campus', campus)
    detailParams.set('list_campus', campus || 'all')
    if (termName) detailParams.set('term_name', termName)
    if (subjectCode) detailParams.set('subject_code', subjectCode)
    if (subjectName) detailParams.set('subject_name', subjectName)
    detailParams.set('subject_id', subjectId)
    detailParams.set('platform', platform)
    return `/student-management/classes/${encodeURIComponent(item.id)}?${detailParams.toString()}`
  }

  const learningBehaviorHref = (item: AcademicClass) => {
    const query = new URLSearchParams({ branch, term_id: termId, campus: item.campus || campus || '', subject_id: subjectId, class_id: item.id, classification: 'all', step: 'results' })
    return `/analytics/learning?${query.toString()}`
  }

  const columns = useMemo<EnterpriseTableColumn<AcademicClass>[]>(() => {
    const shared: EnterpriseTableColumn<AcademicClass>[] = [
      { key: 'stt', header: 'STT', kind: 'index', width: 52, sticky: 'left', hideable: false, render: (_item, index) => (page - 1) * pageSize + index + 1 },
      { key: 'class', header: 'Lớp', kind: 'identity', minWidth: 190, sticky: 'left', priority: 'required', hideable: false, render: (item) => <><b>{item.class_code}</b><small>{item.class_name || item.subject_name}</small></> },
      { key: 'scope', header: 'Phạm vi', kind: 'text', minWidth: 120, priority: 'important', hideable: true, render: (item) => <><b>{item.campus?.toUpperCase() || '—'}</b><small>{item.block_name || 'Chưa có block'}</small></> },
      { key: 'teacher', header: 'Giảng viên', kind: 'identity', minWidth: 155, priority: 'important', hideable: true, render: (item) => <><b>{item.teacher_name || item.teacher_username || 'Chưa phân công'}</b>{item.teacher_name && item.teacher_username ? <small>{item.teacher_username}</small> : null}</> },
    ]
    const platformColumns: EnterpriseTableColumn<AcademicClass>[] = isCms ? [
      { key: 'course', header: 'Course CMS', kind: 'status', minWidth: 145, priority: 'important', hideable: true, render: (item) => <><span className={mappingClass(item.openedx_mapping_source)}>{mappingSourceLabel(item.openedx_mapping_source)}</span><small className="enterprise-clamp-1">{item.openedx_course_id || 'Chưa có Course ID'}</small></> },
      { key: 'learning', header: 'Học tập CMS', kind: 'progress', minWidth: 230, priority: 'important', hideable: true, render: (item) => <><b>{item.learning_enrolled_count || 0}/{item.student_count} ghi danh</b><small>{item.learning_active_count || 0} đã học · TB {percentLabel(item.learning_avg_progress_percent)}</small><small>CMS {item.cms_synced_count || 0}/{item.student_count}</small></> },
    ] : [
      { key: 'udemy', header: 'Tiến độ Udemy', kind: 'progress', minWidth: 220, priority: 'important', hideable: true, render: (item) => <><b>{item.udemy_progress_student_count || 0}/{item.student_count} đã có tiến độ</b><small>Tiến độ TB {percentLabel(item.udemy_progress_average_percent)}</small><small className={(item.udemy_progress_late_count || 0) > 0 ? 'danger-text' : undefined}>{item.udemy_progress_late_count || 0} SV chậm tiến độ</small></> },
      { key: 'import', header: 'Import gần nhất', kind: 'status', minWidth: 150, priority: 'important', hideable: true, render: (item) => item.udemy_progress_last_imported_at ? <><span className="status-pill success">Đã import</span><small>{new Date(item.udemy_progress_last_imported_at).toLocaleString('vi-VN')}</small></> : <span className="status-pill warning">Chưa có dữ liệu</span> },
    ]
    return [
      ...shared,
      ...platformColumns,
      { key: 'actions', header: 'Thao tác', kind: 'actions', width: isCms ? 132 : 100, sticky: 'right', hideable: false, render: (item) => <div className="training-row-actions"><Link className="btn small primary" href={classDetailHref(item)}>Chi tiết</Link>{isCms ? <Link className="btn small secondary" href={learningBehaviorHref(item)}>Phân tích</Link> : null}</div> },
    ]
  }, [branch, campus, isCms, page, pageSize, platform, subjectId, termId])

  return <PageRoot className="page-stack enterprise-standard-page student-management-page academic-flow-page training-operations-page student-subject-classes-page">
    <EnterpriseScreenHeader
      eyebrow="Vận hành đào tạo"
      title={`Lớp của môn ${subjectCode || subjectName || ''}`.trim()}
      description={isCms ? `Theo dõi lớp, Course CMS, số lượng sinh viên và tiến độ học của ${subjectName || subjectCode || 'môn học đã chọn'}.` : `Theo dõi lớp Udemy theo từng Block, sinh viên đã import, tiến độ và cảnh báo của ${subjectName || subjectCode || 'môn học đã chọn'}.`}
      icon="students"
      tone="blue"
      breadcrumbs={[{ label: 'Vận hành đào tạo' }, { label: `Quản lý sinh viên ${platformLabel}`, href: `/student-management/${platform}` }, { label: 'Môn học' }, { label: subjectCode || subjectName || 'Danh sách lớp' }]}
      secondaryActions={<Link className="btn secondary" href={listHref}>Quay lại danh sách môn</Link>}
    />

    <section className="card academic-unified-card training-workspace-section subject-classes-workspace">
      <TrainingContextChips items={[branch.toUpperCase(), termName || termId || 'Chưa rõ kỳ', campus ? campus.toUpperCase() : 'Tất cả cơ sở', subjectName || subjectCode]} />

      <div className="training-compact-filter">
        <label className="is-narrow">Block
          <select className="input" value={blockId} onChange={(event) => update({ blockId: event.target.value })}>
            <option value="">Tất cả block</option>
            {blocks.map((item) => <option key={item.id} value={item.id}>{item.block_name}</option>)}
          </select>
        </label>
        <label>Trạng thái
          <select className="input" value={status} onChange={(event) => update({ status: event.target.value })}>
            <option value="all">Tất cả lớp</option>
            {isCms ? <>
              <option value="cms_not_synced">Chưa đồng bộ CMS</option>
              <option value="not_fully_enrolled">Chưa đủ ghi danh</option>
              <option value="no_learning_data">Chưa có dữ liệu học tập</option>
              <option value="low_grade">Có điểm thấp</option>
            </> : <>
              <option value="udemy_not_imported">Chưa có dữ liệu tiến độ</option>
              <option value="udemy_late">Có sinh viên chậm tiến độ</option>
              <option value="has_alert">Có cảnh báo</option>
            </>}
          </select>
        </label>
        <label className="is-wide">Tìm lớp hoặc giảng viên
          <input className="input" value={q} onChange={(event) => update({ q: event.target.value })} placeholder="BUS2015.01, tên giảng viên..." />
        </label>
      </div>

      <TrainingKpiStrip compact items={isCms ? [
        { key: 'classes', label: 'Lớp CMS', value: summary.class_count || total, hint: 'Theo bộ lọc hiện tại' },
        { key: 'students', label: 'Sinh viên', value: summary.student_count, hint: 'Không phụ thuộc trang đang xem' },
        { key: 'cms', label: 'CMS match', value: `${summary.cms_synced_count}/${summary.student_count}`, hint: 'Tài khoản đã nhận diện' },
        { key: 'course', label: 'Course CMS', value: `${summary.course_mapped_count}/${summary.class_count || total}`, hint: 'Lớp có mapping hiệu lực', tone: summary.course_mapped_count < (summary.class_count || total) ? 'warning' : 'success' },
        { key: 'enrolled', label: 'Ghi danh', value: summary.learning_enrolled_count, hint: 'Sinh viên đã enroll CMS' },
      ] : [
        { key: 'classes', label: 'Lớp Udemy', value: summary.class_count || total, hint: 'Vẫn chia theo Block' },
        { key: 'students', label: 'Sinh viên', value: summary.student_count, hint: 'Theo roster AP' },
        { key: 'imported', label: 'Đã có tiến độ', value: `${summary.udemy_progress_student_count}/${summary.student_count}`, hint: 'Snapshot mới nhất' },
        { key: 'progress', label: 'Tiến độ trung bình', value: percentLabel(summary.udemy_progress_average_percent), hint: 'Theo file import mới nhất' },
        { key: 'late', label: 'Chậm tiến độ', value: summary.udemy_progress_late_count, hint: 'Theo mốc kế hoạch đến hạn', tone: summary.udemy_progress_late_count > 0 ? 'warning' : 'success' },
      ]} />

      <InlineNotice notice={message} />

      <EnterpriseDataTable
        tableId={`student-subject-classes-${platform}`}
        caption={`Danh sách lớp ${platformLabel}`}
        rows={classes}
        columns={columns}
        rowKey={(item) => item.id}
        density={density}
        onDensityChange={(value) => update({ density: value }, { resetPage: false })}
        loading={loading}
        error={message?.type === 'error' ? message.body : undefined}
        onRetry={() => loadClasses()}
        emptyTitle="Không có lớp phù hợp"
        emptyDescription="Đổi block, trạng thái hoặc từ khóa tìm kiếm."
        page={page}
        pageSize={pageSize}
        total={total}
        totalPages={totalPages}
        onPageChange={(value) => update({ page: value }, { resetPage: false })}
        onPageSizeChange={(value) => update({ pageSize: value, page: 1 }, { resetPage: false })}
        label="lớp"
      />
    </section>
  </PageRoot>
}

export default function SubjectClassesPage() {
  return <Suspense fallback={<div className="card">Đang tải danh sách lớp...</div>}><SubjectClassesContent /></Suspense>
}
