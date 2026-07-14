'use client'

import Link from 'next/link'
import { useEffect, useMemo, useState } from 'react'
import { useParams, useSearchParams } from 'next/navigation'
import { useAppContext } from '../../../../../context/AppContext'
import { getAcademicTrainingTeacherReport } from '../../../../../lib/api'
import { AcademicLearningComponentScore, AcademicTrainingClassReport, AcademicTrainingTeacherReport } from '../../../../../types'
import { PageHeader } from '../../../../../components/layout/PageHeader'
import { EnterpriseDataTable, EnterpriseTableColumn } from '../../../../../components/table/EnterpriseDataTable'
import { InlineNotice, InlineNoticeData, noticeError } from '../../../../../components/ui/InlineNotice'
import { TrainingContextChips, TrainingKpiStrip } from '../../../../../components/training/TrainingWorkspace'
import { useAcademicTableState } from '../../../../../hooks/useAcademicTableState'

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
  return `${Math.round(Math.max(0, Math.min(10, score)) * 10) / 10}/10`
}

function countLabel(value?: number | null) { return String(value || 0) }
function ratioLabel(done?: number | null, total?: number | null) { return `${done || 0}/${total || 0}` }

function componentScoreText(score?: AcademicLearningComponentScore | null) {
  if (!score) return 'N/A'
  const percent = normalizePercentValue(score.percent)
  if (percent !== null) return score10Label(percent / 10)
  if (typeof score.earned === 'number' && typeof score.possible === 'number' && score.possible > 0) return score10Label((score.earned / score.possible) * 10)
  return 'N/A'
}

function componentSummary(scores?: AcademicLearningComponentScore[]) {
  if (!scores?.length) return 'Chưa có đầu điểm'
  return scores.slice(0, 3).map((score) => `${score.name || score.key || 'TP'} ${componentScoreText(score)}`).join(' · ')
}

function riskTone(cls: AcademicTrainingClassReport) {
  if (!cls.openedx_course_id) return 'status-pill danger'
  if ((cls.risk_student_count || 0) > 0 || (cls.deadline_late_student_count || 0) > 0 || (cls.exam_not_eligible_student_count || 0) > 0) return 'status-pill warning'
  return 'status-pill success'
}

function riskLabel(cls: AcademicTrainingClassReport) {
  if (!cls.openedx_course_id) return 'Chưa ghép course'
  const total = (cls.risk_student_count || 0) + (cls.deadline_late_student_count || 0) + (cls.exam_not_eligible_student_count || 0)
  return total > 0 ? `${cls.risk_student_count || 0} SV cần xem` : 'Chưa thấy cảnh báo lớn'
}

function classDetailHref(cls: AcademicTrainingClassReport, teacher: AcademicTrainingTeacherReport | null, filters: { termId: string; branch: string; campus: string; termName: string }) {
  const params = new URLSearchParams()
  params.set('from', 'teacher-management')
  params.set('teacher_id', teacher?.teacher_id || '')
  params.set('teacher_name', teacher?.teacher_name || teacher?.teacher_username || '')
  if (filters.termId) params.set('term_id', filters.termId)
  if (filters.branch) params.set('branch', filters.branch)
  if (filters.campus) params.set('campus', filters.campus)
  params.set('list_campus', filters.campus || 'all')
  if (filters.termName) params.set('term_name', filters.termName)
  if (cls.subject_id) params.set('subject_id', cls.subject_id)
  if (cls.subject_code) params.set('subject_code', cls.subject_code)
  if (cls.subject_name) params.set('subject_name', cls.subject_name)
  return `/teacher-management/classes/${encodeURIComponent(cls.class_id)}?${params.toString()}`
}

function learningBehaviorHref(cls: AcademicTrainingClassReport, filters: { termId: string; branch: string; campus: string; termName: string }) {
  const params = new URLSearchParams()
  if (filters.termId) params.set('term_id', filters.termId)
  if (filters.branch) params.set('branch', filters.branch)
  if (filters.campus || cls.campus) params.set('campus', filters.campus || cls.campus || '')
  if (filters.termName) params.set('term_name', filters.termName)
  if (cls.subject_id) params.set('subject_id', cls.subject_id)
  if (cls.class_id) params.set('class_id', cls.class_id)
  params.set('classification', 'all')
  params.set('step', 'results')
  return `/analytics/learning?${params.toString()}`
}

export default function TeacherClassesPage() {
  const params = useParams<{ teacherId: string }>()
  const searchParams = useSearchParams()
  const teacherId = decodeURIComponent(String(params.teacherId || ''))
  const termName = searchParams.get('term_name') || ''
  const teacherNameFromQuery = searchParams.get('teacher_name') || ''
  const { state, update } = useAcademicTableState({ branch: 'poly', status: 'all', pageSize: 50 })
  const { termId, branch, campus, status, density } = state
  const { authHeaders } = useAppContext()
  const headers = useMemo(() => authHeaders(), [authHeaders])
  const [teacher, setTeacher] = useState<AcademicTrainingTeacherReport | null>(null)
  const [classes, setClasses] = useState<AcademicTrainingClassReport[]>([])
  const [loading, setLoading] = useState(false)
  const [message, setMessage] = useState<InlineNoticeData | null>(null)

  const load = async (cancelledRef?: { cancelled: boolean }) => {
    if (!termId || !teacherId) {
      setTeacher(null)
      setClasses([])
      setMessage(noticeError('Thiếu học kỳ hoặc mã giáo viên. Mở lại từ trang Quản lý giảng viên.'))
      return
    }
    setLoading(true)
    setMessage(null)
    try {
      const result = await getAcademicTrainingTeacherReport(headers, { termId, branch, campus, teacherId, learningStatus: status, page: 1, pageSize: 1, includeClasses: true })
      if (cancelledRef?.cancelled) return
      const item = result.items?.[0] || null
      setTeacher(item)
      setClasses(item?.classes || [])
      if (!item) setMessage(noticeError('Không tìm thấy lớp của giảng viên trong phạm vi hiện tại.'))
    } catch (error) {
      if (!cancelledRef?.cancelled) setMessage({ ...noticeError(error, 'Không tải được lớp của giảng viên.'), onRetry: () => load() })
    } finally {
      if (!cancelledRef?.cancelled) setLoading(false)
    }
  }

  useEffect(() => {
    const cancelledRef = { cancelled: false }
    load(cancelledRef)
    return () => { cancelledRef.cancelled = true }
  }, [headers, termId, branch, campus, teacherId, status])

  const filters = { termId, branch, campus, termName }
  const teacherTitle = teacher?.teacher_name || teacherNameFromQuery || teacher?.teacher_username || 'Giảng viên'
  const backHref = `/teacher-management?term_id=${encodeURIComponent(termId)}&branch=${encodeURIComponent(branch)}${campus ? `&campus=${encodeURIComponent(campus)}` : ''}`

  const columns = useMemo<EnterpriseTableColumn<AcademicTrainingClassReport>[]>(() => [
    { key: 'stt', header: 'STT', kind: 'index', width: 52, sticky: 'left', hideable: false, render: (_cls, index) => index + 1 },
    { key: 'class', header: 'Lớp', kind: 'identity', minWidth: 185, sticky: 'left', priority: 'required', hideable: false, render: (cls) => <><b>{cls.class_code}</b><small>{cls.term_name}{cls.block_name ? ` · ${cls.block_name}` : ''}</small></> },
    { key: 'subject', header: 'Môn', kind: 'identity', minWidth: 150, priority: 'important', hideable: true, render: (cls) => <><b>{cls.subject_code}</b><small>{cls.subject_name}</small></> },
    { key: 'students', header: 'Sinh viên', kind: 'number', width: 126, priority: 'important', hideable: true, render: (cls) => <><b>{cls.student_count} SV</b><small>CMS {ratioLabel(cls.cms_synced_count, cls.student_count)}</small></> },
    { key: 'course', header: 'Course CMS', kind: 'status', minWidth: 140, priority: 'important', hideable: true, render: (cls) => cls.openedx_course_id ? <><span className="status-pill success">Đã ghép</span><small className="enterprise-clamp-1">{cls.openedx_course_id}</small></> : <span className="status-pill warning">Chưa ghép</span> },
    { key: 'progress', header: 'Tiến độ', kind: 'progress', minWidth: 150, priority: 'important', hideable: true, render: (cls) => <><b>{percentLabel(cls.learning_avg_progress_percent)}</b><small>Điểm {score10Label(cls.learning_avg_grade_10)} · Enroll {ratioLabel(cls.learning_enrolled_count, cls.student_count)}</small></> },
    { key: 'assessment', header: 'Đầu điểm', kind: 'text', minWidth: 190, priority: 'optional', defaultVisible: false, hideable: true, truncateLines: 2, render: (cls) => <small>{componentSummary(cls.learning_component_summaries)}</small> },
    { key: 'eligibility', header: 'Điều kiện thi', kind: 'status', minWidth: 145, priority: 'optional', defaultVisible: false, hideable: true, render: (cls) => <><b>{countLabel(cls.exam_eligible_student_count)} được thi</b><small>{countLabel(cls.exam_not_eligible_student_count)} chưa đủ · {countLabel(cls.exam_insufficient_data_student_count)} thiếu dữ liệu</small></> },
    { key: 'risk', header: 'Cảnh báo', kind: 'status', minWidth: 145, priority: 'important', hideable: true, render: (cls) => <><span className={riskTone(cls)}>{riskLabel(cls)}</span><small>Trễ {countLabel(cls.deadline_late_student_count)} · Học lại {countLabel(cls.relearn_student_count)}</small></> },
    { key: 'actions', header: 'Thao tác', kind: 'actions', width: 118, sticky: 'right', hideable: false, render: (cls) => <div className="training-row-actions"><Link className="btn small primary" href={classDetailHref(cls, teacher, filters)}>Chi tiết</Link><details className="row-action-menu"><summary className="btn small ghost" aria-label="Mở thêm thao tác">•••</summary><div className="row-action-popover"><Link href={learningBehaviorHref(cls, filters)}>Phân tích học tập</Link></div></details></div> },
  ], [teacher, termId, branch, campus, termName])

  return <div className="page-stack training-management-page teacher-management-page teacher-classes-page training-operations-page">
    <PageHeader
      eyebrow="Vận hành đào tạo"
      title={`Lớp của ${teacherTitle}`}
      description={`${classes.length} lớp · ${teacher?.subject_count || 0} môn trong phạm vi được phân quyền`}
      secondaryActions={<><Link className="btn secondary" href={backHref}>Quay lại giảng viên</Link><button className="btn secondary" type="button" onClick={() => load()} disabled={loading}>Tải lại</button></>}
    />

    <section className="card academic-unified-card training-workspace-section">
      <TrainingContextChips items={[branch.toUpperCase(), termName || termId || 'Chưa rõ kỳ', campus ? campus.toUpperCase() : 'Tất cả cơ sở', teacher?.teacher_username]} />

      <div className="training-compact-filter">
        <label>Trạng thái lớp
          <select className="input" value={status} onChange={(event) => update({ status: event.target.value })}>
            <option value="all">Tất cả lớp</option>
            <option value="no_course_map">Chưa ghép Course CMS</option>
            <option value="cms_not_synced">Có SV chưa đồng bộ CMS</option>
            <option value="not_fully_enrolled">Có SV chưa ghi danh</option>
            <option value="no_activity">Có SV chưa học</option>
            <option value="low_progress">Có SV tiến độ thấp</option>
            <option value="low_grade">Có SV điểm thấp</option>
            <option value="deadline_late">Có SV trễ deadline</option>
            <option value="exam_not_eligible">Có SV chưa đủ điều kiện thi</option>
            <option value="has_alert">Có cảnh báo</option>
          </select>
        </label>
      </div>

      {teacher ? <TrainingKpiStrip compact items={[
        { key: 'classes', label: 'Lớp', value: teacher.class_count, hint: `${teacher.subject_count} môn` },
        { key: 'students', label: 'Sinh viên', value: teacher.student_count, hint: `${teacher.unique_student_count || 0} sinh viên riêng biệt` },
        { key: 'cms', label: 'CMS match', value: ratioLabel(teacher.cms_synced_count, teacher.student_count), hint: 'Tài khoản đã nhận diện' },
        { key: 'enrolled', label: 'Ghi danh', value: ratioLabel(teacher.learning_enrolled_count, teacher.student_count), hint: 'Enrollment CMS' },
        { key: 'progress', label: 'Hoàn thành TB', value: percentLabel(teacher.learning_avg_progress_percent), hint: `Điểm ${score10Label(teacher.learning_avg_grade_10)}` },
        { key: 'risk', label: 'Cần theo dõi', value: teacher.risk_student_count || 0, hint: 'Không đếm trùng sinh viên', tone: (teacher.risk_student_count || 0) > 0 ? 'warning' : 'success' },
      ]} /> : null}

      <InlineNotice notice={message} />

      <EnterpriseDataTable
        tableId="teacher-classes"
        caption="Danh sách lớp"
        rows={classes}
        columns={columns}
        rowKey={(cls) => cls.class_id}
        density={density}
        onDensityChange={(value) => update({ density: value }, { resetPage: false })}
        loading={loading}
        error={message?.type === 'error' ? message.body : undefined}
        onRetry={() => load()}
        emptyTitle="Chưa có lớp theo bộ lọc"
        emptyDescription="Đổi trạng thái hoặc quay lại chọn giảng viên khác."
        label="lớp"
      />
    </section>
  </div>
}
