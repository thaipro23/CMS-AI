'use client'

import { useEffect, useMemo, useState } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import { useAppContext } from '../../../context/AppContext'
import {
  getAcademicCampuses,
  getAcademicTeacherSubjects,
  getAcademicTerms,
  getAnalyticsClassLearningBehavior,
  getAnalyticsClassLearningBehaviorSummary,
  getAnalyticsStudentLearningBehaviorDetail,
  getAnalyticsSubjectClassBehaviorOverview,
} from '../../../lib/api'
import {
  AcademicCampus,
  AcademicSubjectManagement,
  AcademicTerm,
  AnalyticsClassBehaviorOverviewItem,
  AnalyticsClassBehaviorOverviewSummary,
  AnalyticsLearningBehaviorRow,
  AnalyticsLearningBehaviorSummary,
  AnalyticsStudentLearningBehaviorDetail,
} from '../../../types'
import { formatVNDateTime } from '../../../lib/time'

const PAGE_SIZE = 200
const API_PAGE_SIZE = 200
const CLASS_OVERVIEW_PAGE_SIZE = 200

type AnalyticsFlowStep = 'subjects' | 'classes' | 'results'

const CLASSIFICATION_OPTIONS = [
  { value: 'all', label: 'Tất cả kết quả' },
  { value: 'LIKELY_REAL_LEARNING', label: 'Có dấu hiệu học thật' },
  { value: 'POSSIBLE_IDLE', label: 'Có khả năng treo máy' },
  { value: 'POSSIBLE_CHEATING', label: 'Dấu hiệu bất thường cần kiểm tra' },
  { value: 'INSUFFICIENT_DATA', label: 'Chưa đủ dữ liệu' },
  { value: 'NORMAL', label: 'Chưa thấy bất thường rõ' },
]

const EMPTY_SUMMARY: AnalyticsLearningBehaviorSummary = {
  total_students: 0,
  likely_real_learning_count: 0,
  possible_idle_count: 0,
  possible_suspicious_count: 0,
  insufficient_data_count: 0,
  normal_count: 0,
  data_quality_breakdown: {},
}

const EMPTY_CLASS_OVERVIEW_SUMMARY: AnalyticsClassBehaviorOverviewSummary = {
  total_classes: 0,
  total_students: 0,
  snapshot_count: 0,
  likely_real_learning_count: 0,
  possible_idle_count: 0,
  possible_suspicious_count: 0,
  insufficient_data_count: 0,
  normal_count: 0,
  not_calculated_class_count: 0,
}

const EMPTY_SUBJECT_SUMMARY = {
  subject_count: 0,
  class_count: 0,
  student_count: 0,
  course_mapped_count: 0,
  learning_enrolled_count: 0,
  learning_synced_count: 0,
  alert_subject_count: 0,
}

function percent(value?: number | null) {
  if (typeof value !== 'number' || Number.isNaN(value)) return 'N/A'
  return `${Math.round(value * 10) / 10}%`
}

function resultLabel(value?: string | null, fallback?: string | null) {
  const classification = String(value || '').toUpperCase()
  if (classification === 'LIKELY_REAL_LEARNING') return 'Có dấu hiệu học thật'
  if (classification === 'POSSIBLE_IDLE') return 'Có khả năng treo máy'
  if (classification === 'POSSIBLE_CHEATING') return 'Dấu hiệu bất thường cần kiểm tra'
  if (classification === 'INSUFFICIENT_DATA') return 'Chưa đủ dữ liệu'
  if (classification === 'NORMAL') return 'Chưa thấy bất thường rõ'
  return fallback || 'Chưa đủ dữ liệu'
}

function resultClass(value?: string | null) {
  const classification = String(value || '').toUpperCase()
  if (classification === 'LIKELY_REAL_LEARNING') return 'status-pill success'
  if (classification === 'POSSIBLE_IDLE') return 'status-pill warning'
  if (classification === 'POSSIBLE_CHEATING') return 'status-pill danger'
  if (classification === 'NORMAL') return 'status-pill neutral'
  return 'status-pill neutral'
}

function compactSubjectLabel(item: AcademicSubjectManagement) {
  const code = item.subject_code || item.skill_code || 'Môn'
  const name = item.subject_name || item.subject_name_en || ''
  return `${code}${name ? ` — ${name}` : ''}`
}

function classDataStatusLabel(item: AnalyticsClassBehaviorOverviewItem) {
  if (item.data_status === 'not_calculated') return 'Chưa có kết quả'
  return `${item.snapshot_count}/${item.student_count} SV có kết quả`
}

function campusLabel(campus: string, campuses: AcademicCampus[]) {
  if (!campus) return 'Tất cả cơ sở'
  const found = campuses.find((item) => item.campus_code === campus)
  return found ? `${found.campus_code?.toUpperCase()} · ${found.campus_name}` : campus.toUpperCase()
}

async function loadAllSubjects(
  headers: HeadersInit,
  filters: { termId: string; branch: string; campus: string; search?: string; learningStatus?: string },
): Promise<AcademicSubjectManagement[]> {
  const items: AcademicSubjectManagement[] = []
  let page = 1
  let hasNext = true
  while (hasNext) {
    const result = await getAcademicTeacherSubjects(headers, { ...filters, page, pageSize: API_PAGE_SIZE })
    items.push(...(result.items || []))
    hasNext = Boolean(result.has_next) && page < 40
    page += 1
  }
  return items
}

function reasonText(code?: string | null) {
  const value = String(code || '').toUpperCase()
  if (!value) return ''
  if (value.includes('INSUFFICIENT') || value.includes('MISSING')) return 'Thiếu dữ liệu để kết luận chắc chắn.'
  if (value.includes('IDLE') || value.includes('LOW_INTERACTION')) return 'Có dấu hiệu xem video nhưng ít tương tác học tập.'
  if (value.includes('WATCH') || value.includes('VIDEO')) return 'Tín hiệu video chưa đủ mạnh hoặc chưa khớp tiến độ bài.'
  if (value.includes('DEADLINE') || value.includes('LATE')) return 'Có hoạt động học sát hạn hoặc sau hạn.'
  if (value.includes('QUIZ')) return 'Thứ tự/tín hiệu quiz cần kiểm tra thêm.'
  if (value.includes('REAL') || value.includes('NORMAL')) return 'Tín hiệu học tập ổn định hơn nhóm cần theo dõi.'
  return code || ''
}

function normalizeStep(value?: string | null): AnalyticsFlowStep {
  const normalized = String(value || '').toLowerCase()
  if (normalized === 'results') return 'results'
  if (normalized === 'classes') return 'classes'
  return 'subjects'
}

function DetailDrawer({
  row,
  detail,
  loading,
  onClose,
}: {
  row: AnalyticsLearningBehaviorRow | null
  detail: AnalyticsStudentLearningBehaviorDetail | null
  loading: boolean
  onClose: () => void
}) {
  if (!row) return null
  const behavior = detail?.behavior || row
  const reasons = Array.from(new Set([...(behavior.reason_codes || []), ...(row.reason_codes || [])])).filter(Boolean)
  const sessions = detail?.sessions || []
  const videos = detail?.videos || []

  return <div className="analytics-result-drawer-backdrop" role="dialog" aria-modal="true" aria-labelledby="analytics-result-title">
    <div className="analytics-result-drawer">
      <div className="section-head list-card-head">
        <div>
          <h3 id="analytics-result-title">Lý do ra kết quả</h3>
          <p>{row.username} · {row.class_id || 'Lớp N/A'}</p>
        </div>
        <button className="btn secondary small" type="button" onClick={onClose} aria-label="Đóng chi tiết kết quả">Đóng</button>
      </div>

      <div className="analytics-result-main">
        <span className={resultClass(behavior.classification)}>{resultLabel(behavior.classification, behavior.display_label)}</span>
        <b>{behavior.human_readable_summary || 'Chưa có tóm tắt lý do.'}</b>
        <small>{behavior.recommended_action || 'Cần giáo viên xác minh khi cần xử lý.'}</small>
      </div>

      {loading && <div className="empty-state compact">Đang tải lý do chi tiết...</div>}

      {!loading && <>
        <div className="academic-summary-strip analytics-result-score-strip">
          <div><span>Độ tin cậy</span><b>{percent(behavior.confidence_score)}</b></div>
          <div><span>Học thật</span><b>{percent(behavior.real_learning_score)}</b></div>
          <div><span>Khả năng treo máy</span><b>{percent(behavior.idle_score)}</b></div>
          <div><span>Dấu hiệu bất thường</span><b>{percent(behavior.suspicious_score)}</b></div>
          <div><span>Đúng hạn</span><b>{percent(behavior.deadline_compliance_percent)}</b></div>
        </div>

        <div className="analytics-reason-list">
          <h4>Lý do chính</h4>
          {reasons.length ? reasons.slice(0, 8).map((code) => <div key={code} className="analytics-reason-item">
            <b>{reasonText(code)}</b>
            <small>Lý do được rút gọn từ tín hiệu học online.</small>
          </div>) : <div className="empty-state compact">Không có mã lý do chi tiết. Xem tóm tắt kết quả ở trên.</div>}
        </div>

        <div className="analytics-detail-grid">
          <div className="analytics-detail-box">
            <h4>Tiến độ bài</h4>
            <div className="academic-mini-lines">
              <span>{sessions.length} bài/session có dữ liệu.</span>
              <span>Học dồn: {behavior.crammed_session_count || 0}</span>
              <span>Quiz trước video: {behavior.quiz_before_video_count || 0}</span>
              <span>Lần học cuối: {behavior.last_activity_at ? formatVNDateTime(behavior.last_activity_at) : 'N/A'}</span>
            </div>
          </div>
          <div className="analytics-detail-box">
            <h4>Video</h4>
            <div className="academic-mini-lines">
              <span>{videos.length} video có dữ liệu.</span>
              <span>Video hoàn thành: {videos.filter((item) => item.is_completed).length}</span>
              <span>Video cần kiểm tra: {videos.filter((item) => item.is_suspicious).length}</span>
            </div>
          </div>
        </div>

        {!!sessions.length && <div className="table-wrap analytics-result-table-wrap">
          <table className="data-table academic-data-table">
            <thead>
              <tr><th>STT</th><th>Bài</th><th>Video</th><th>Quiz</th><th>Deadline</th></tr>
            </thead>
            <tbody>
              {sessions.slice(0, 12).map((item, index) => <tr key={`${item.session_index}-${index}`}>
                <td className="stt-cell">{index + 1}</td>
                <td><b>{item.session_title || `Bài ${item.session_index || index + 1}`}</b></td>
                <td>{item.videos_completed || 0}/{item.total_videos || 0}</td>
                <td>{item.quiz_attempted ? 'Đã làm' : 'Chưa thấy'}</td>
                <td>{item.completed_before_deadline ? 'Đúng hạn' : item.completed_late ? 'Trễ hạn' : 'Chưa đủ dữ liệu'}</td>
              </tr>)}
            </tbody>
          </table>
        </div>}
      </>}
    </div>
  </div>
}

export default function AnalyticsLearningPage() {
  const searchParams = useSearchParams()
  const router = useRouter()
  const queryBranch = searchParams.get('branch') || 'poly'
  const queryTermId = searchParams.get('term_id') || ''
  const queryCampusRaw = searchParams.get('campus') || ''
  const queryCampus = queryCampusRaw === 'all' ? '' : queryCampusRaw
  const querySubjectId = searchParams.get('subject_id') || ''
  const queryClassId = searchParams.get('class_id') || ''
  const queryClassification = searchParams.get('classification') || 'all'
  const initialStep = queryClassId ? 'results' : (querySubjectId ? normalizeStep(searchParams.get('step') || 'classes') : 'subjects')

  const { authHeaders } = useAppContext()
  const headers = useMemo(() => authHeaders(), [authHeaders])
  const [terms, setTerms] = useState<AcademicTerm[]>([])
  const [campuses, setCampuses] = useState<AcademicCampus[]>([])
  const [subjects, setSubjects] = useState<AcademicSubjectManagement[]>([])
  const [classOverview, setClassOverview] = useState<AnalyticsClassBehaviorOverviewItem[]>([])
  const [classOverviewTotal, setClassOverviewTotal] = useState(0)
  const [classOverviewSummary, setClassOverviewSummary] = useState<AnalyticsClassBehaviorOverviewSummary>(EMPTY_CLASS_OVERVIEW_SUMMARY)
  const [branch, setBranch] = useState(queryBranch)
  const [termId, setTermId] = useState(queryTermId)
  const [campus, setCampus] = useState(queryCampus)
  const [subjectId, setSubjectId] = useState(querySubjectId)
  const [classId, setClassId] = useState(queryClassId)
  const [classification, setClassification] = useState(queryClassification)
  const [step, setStep] = useState<AnalyticsFlowStep>(initialStep)
  const [subjectSearch, setSubjectSearch] = useState(searchParams.get('search') || '')
  const [classOverviewPage, setClassOverviewPage] = useState(1)
  const [summary, setSummary] = useState<AnalyticsLearningBehaviorSummary>(EMPTY_SUMMARY)
  const [rows, setRows] = useState<AnalyticsLearningBehaviorRow[]>([])
  const [totalRows, setTotalRows] = useState(0)
  const [loadingTerms, setLoadingTerms] = useState(false)
  const [loadingSubjects, setLoadingSubjects] = useState(false)
  const [loadingClassOverview, setLoadingClassOverview] = useState(false)
  const [loadingResults, setLoadingResults] = useState(false)
  const [message, setMessage] = useState('')
  const [permissionScope, setPermissionScope] = useState<Record<string, unknown> | null>(null)
  const [selectedRow, setSelectedRow] = useState<AnalyticsLearningBehaviorRow | null>(null)
  const [detail, setDetail] = useState<AnalyticsStudentLearningBehaviorDetail | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)

  const selectedTerm = useMemo(() => terms.find((item) => item.id === termId) || null, [terms, termId])
  const selectedSubject = useMemo(() => subjects.find((item) => item.id === subjectId) || null, [subjects, subjectId])
  const selectedClassOverview = useMemo(() => classOverview.find((item) => item.class_id === classId) || null, [classOverview, classId])
  const effectiveCourseId = selectedClassOverview?.openedx_course_id || null
  const subjectSummary = useMemo(() => {
    return subjects.reduce((acc, item) => {
      acc.subject_count += 1
      acc.class_count += Number(item.class_count || 0)
      acc.student_count += Number(item.student_count || 0)
      acc.course_mapped_count += String(item.course_mapping_status || '').toLowerCase() === 'mapped' ? 1 : 0
      acc.learning_enrolled_count += Number(item.learning_enrolled_count || 0)
      acc.learning_synced_count += Number(item.learning_synced_count || 0)
      acc.alert_subject_count += item.learning_alerts?.length ? 1 : 0
      return acc
    }, { ...EMPTY_SUBJECT_SUMMARY })
  }, [subjects])

  const updateUrl = (next: Partial<{ step: AnalyticsFlowStep; branch: string; termId: string; campus: string; subjectId: string; classId: string; classification: string; search: string }>) => {
    const nextStep = next.step ?? step
    const nextBranch = next.branch ?? branch
    const nextTermId = next.termId ?? termId
    const nextCampus = next.campus ?? campus
    const nextSubjectId = next.subjectId ?? subjectId
    const nextClassId = next.classId ?? classId
    const nextClassification = next.classification ?? classification
    const nextSearch = next.search ?? subjectSearch
    const params = new URLSearchParams()
    params.set('step', nextStep)
    if (nextBranch) params.set('branch', nextBranch)
    if (nextTermId) params.set('term_id', nextTermId)
    params.set('campus', nextCampus || 'all')
    if (nextSubjectId) params.set('subject_id', nextSubjectId)
    if (nextClassId && nextStep === 'results') params.set('class_id', nextClassId)
    if (nextClassification && nextClassification !== 'all') params.set('classification', nextClassification)
    if (nextSearch) params.set('search', nextSearch)
    router.replace(`/analytics/learning?${params.toString()}`, { scroll: false })
  }

  const setFlowStep = (nextStep: AnalyticsFlowStep, overrides: Partial<{ subjectId: string; classId: string }> = {}) => {
    const nextSubjectId = overrides.subjectId ?? subjectId
    const nextClassId = overrides.classId ?? (nextStep === 'results' ? classId : '')
    setStep(nextStep)
    setSubjectId(nextSubjectId)
    setClassId(nextClassId)
    if (nextStep === 'subjects') {
      setClassOverview([])
      setRows([])
      setSummary(EMPTY_SUMMARY)
    }
    if (nextStep === 'classes') {
      setRows([])
      setSummary(EMPTY_SUMMARY)
      setClassOverviewPage(1)
    }
    updateUrl({ step: nextStep, subjectId: nextSubjectId, classId: nextClassId })
  }

  useEffect(() => {
    let cancelled = false
    setLoadingTerms(true)
    getAcademicTerms(headers, { branch, active: true })
      .then((items) => {
        if (cancelled) return
        setTerms(items)
        const preferred = items.find((item) => item.term_name === 'Summer 2026') || items[0]
        setTermId((current) => items.some((item) => item.id === current) ? current : (preferred?.id || ''))
      })
      .catch((error) => { if (!cancelled) setMessage(error instanceof Error ? error.message : 'Không tải được học kỳ') })
      .finally(() => { if (!cancelled) setLoadingTerms(false) })
    return () => { cancelled = true }
  }, [headers, branch])

  useEffect(() => {
    let cancelled = false
    getAcademicCampuses(headers, { branch, active: true })
      .then((items) => {
        if (cancelled) return
        setCampuses(items)
        setCampus((current) => current && !items.some((item) => item.campus_code === current) ? '' : current)
      })
      .catch(() => { if (!cancelled) setCampuses([]) })
    return () => { cancelled = true }
  }, [headers, branch])

  useEffect(() => {
    if (!termId) {
      setSubjects([])
      setSubjectId('')
      return
    }
    let cancelled = false
    setLoadingSubjects(true)
    setMessage('')
    loadAllSubjects(headers, { termId, branch, campus, search: subjectSearch, learningStatus: 'all' })
      .then((items) => {
        if (cancelled) return
        setSubjects(items)
        setSubjectId((current) => items.some((item) => item.id === current) ? current : '')
      })
      .catch((error) => { if (!cancelled) setMessage(error instanceof Error ? error.message : 'Không tải được môn') })
      .finally(() => { if (!cancelled) setLoadingSubjects(false) })
    return () => { cancelled = true }
  }, [headers, termId, campus, branch, subjectSearch])

  useEffect(() => {
    setClassOverviewPage(1)
  }, [subjectId, classification, campus, branch, termId])

  useEffect(() => {
    if (!subjectId || step === 'subjects') {
      setClassOverview([])
      setClassOverviewTotal(0)
      setClassOverviewSummary(EMPTY_CLASS_OVERVIEW_SUMMARY)
      return
    }
    let cancelled = false
    const exactClassId = step === 'results' && classId ? classId : undefined
    setLoadingClassOverview(true)
    getAnalyticsSubjectClassBehaviorOverview(headers, subjectId, {
      termId,
      campus,
      branch,
      classification,
      classId: exactClassId,
      limit: CLASS_OVERVIEW_PAGE_SIZE,
      offset: step === 'classes' ? (classOverviewPage - 1) * CLASS_OVERVIEW_PAGE_SIZE : 0,
    })
      .then((result) => {
        if (cancelled) return
        const items = result.items || []
        setClassOverview(items)
        setClassOverviewTotal(result.total || 0)
        setClassOverviewSummary(result.summary || EMPTY_CLASS_OVERVIEW_SUMMARY)
        setPermissionScope(result.permission_scope || null)
        if (step === 'results' && classId && !items.some((item) => item.class_id === classId)) {
          setMessage('Bạn không có quyền xem lớp này hoặc lớp không còn trong bộ lọc hiện tại.')
        }
      })
      .catch((error) => {
        if (!cancelled) {
          setClassOverview([])
          setClassOverviewTotal(0)
          setClassOverviewSummary(EMPTY_CLASS_OVERVIEW_SUMMARY)
          setMessage(error instanceof Error ? error.message : 'Không tải được danh sách lớp theo quyền')
        }
      })
      .finally(() => { if (!cancelled) setLoadingClassOverview(false) })
    return () => { cancelled = true }
  }, [headers, subjectId, termId, campus, branch, classification, classOverviewPage, step, classId])

  useEffect(() => {
    if (step !== 'results' || !classId) {
      setSummary(EMPTY_SUMMARY)
      setRows([])
      setTotalRows(0)
      return
    }
    let cancelled = false
    setLoadingResults(true)
    setMessage('')
    Promise.all([
      getAnalyticsClassLearningBehaviorSummary(headers, classId, effectiveCourseId),
      getAnalyticsClassLearningBehavior(headers, classId, { courseId: effectiveCourseId, classification, limit: PAGE_SIZE, offset: 0 }),
    ])
      .then(([nextSummary, result]) => {
        if (cancelled) return
        setSummary(nextSummary || EMPTY_SUMMARY)
        setRows(result.items || [])
        setTotalRows(result.total || 0)
      })
      .catch((error) => {
        if (!cancelled) {
          setSummary(EMPTY_SUMMARY)
          setRows([])
          setTotalRows(0)
          setMessage(error instanceof Error ? error.message : 'Không tải được kết quả học online')
        }
      })
      .finally(() => { if (!cancelled) setLoadingResults(false) })
    return () => { cancelled = true }
  }, [headers, classId, effectiveCourseId, classification, step])

  const resetScope = (next: Partial<{ branch: string; termId: string; campus: string; classification: string; search: string }>) => {
    const nextBranch = next.branch ?? branch
    const nextTermId = next.termId ?? termId
    const nextCampus = next.campus ?? campus
    const nextClassification = next.classification ?? classification
    const nextSearch = next.search ?? subjectSearch
    setBranch(nextBranch)
    setTermId(nextTermId)
    setCampus(nextCampus)
    setClassification(nextClassification)
    setSubjectSearch(nextSearch)
    setSubjectId('')
    setClassId('')
    setStep('subjects')
    setRows([])
    setClassOverview([])
    updateUrl({ step: 'subjects', branch: nextBranch, termId: nextTermId, campus: nextCampus, subjectId: '', classId: '', classification: nextClassification, search: nextSearch })
  }

  const openReason = async (row: AnalyticsLearningBehaviorRow) => {
    setSelectedRow(row)
    setDetail(null)
    setDetailLoading(true)
    try {
      const next = await getAnalyticsStudentLearningBehaviorDetail(headers, classId, row.username, effectiveCourseId)
      setDetail(next)
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Không tải được lý do chi tiết')
    } finally {
      setDetailLoading(false)
    }
  }

  const scopeMode = String(permissionScope?.['mode'] || '')
  const permissionText = scopeMode === 'all'
    ? 'Quyền xem: toàn hệ thống.'
    : 'Quyền xem: hệ thống đã lọc theo phân quyền cơ sở, môn hoặc lớp AP được phân công.'

  return <div className="page-stack analytics-learning-page analytics-learning-result-only-page analytics-three-step-flow-page">
    <section className="card academic-unified-card">
      <div className="section-head list-card-head">
        <div>
          <h2>Phân tích hành vi học</h2>
          <p>Luồng quản lý tách 3 màn: chọn môn → chọn lớp → xem kết quả. Backend luôn lọc theo phân quyền thật, không chỉ ẩn trên giao diện.</p>
        </div>
      </div>

      <div className="academic-filter-bar analytics-learning-flow-filters">
        <label>Hệ
          <select className="input" value={branch} onChange={(event) => resetScope({ branch: event.target.value })}>
            <option value="poly">Poly</option>
            <option value="ptcd">PTCĐ</option>
          </select>
        </label>
        <label>Học kỳ
          <select className="input" value={termId} onChange={(event) => resetScope({ termId: event.target.value })} disabled={loadingTerms}>
            {terms.map((item) => <option key={item.id} value={item.id}>{item.term_name}</option>)}
          </select>
        </label>
        <label>Cơ sở
          <select className="input" value={campus} onChange={(event) => resetScope({ campus: event.target.value })}>
            <option value="">Tất cả cơ sở</option>
            {campuses.map((item) => <option key={item.id || item.campus_code} value={item.campus_code}>{item.campus_code?.toUpperCase()} · {item.campus_name}</option>)}
          </select>
        </label>
        <label>Kết quả
          <select className="input" value={classification} onChange={(event) => { setClassification(event.target.value); updateUrl({ classification: event.target.value }) }}>
            {CLASSIFICATION_OPTIONS.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
          </select>
        </label>
      </div>

      <div className="analytics-stepper" aria-label="Luồng phân tích hành vi học">
        <button className={step === 'subjects' ? 'active' : ''} type="button" onClick={() => setFlowStep('subjects', { subjectId: '', classId: '' })}>1. Môn</button>
        <button className={step === 'classes' ? 'active' : ''} type="button" disabled={!subjectId} onClick={() => setFlowStep('classes', { classId: '' })}>2. Lớp</button>
        <button className={step === 'results' ? 'active' : ''} type="button" disabled={!classId} onClick={() => setFlowStep('results')}>3. Xem kết quả</button>
      </div>

      <div className="analytics-flow-context">
        <span>{selectedTerm?.term_name || 'Chưa chọn kỳ'}</span>
        <span>{campusLabel(campus, campuses)}</span>
        <span>{selectedSubject?.subject_code || 'Chưa chọn môn'}</span>
        <span>{selectedClassOverview?.class_code || 'Chưa chọn lớp'}</span>
      </div>

      <div className="alert info compact-alert">{permissionText}</div>
      {message && <div className="academic-inline-error"><b>Cần kiểm tra</b><span>{message}</span></div>}
      {!effectiveCourseId && step === 'results' && classId && <div className="alert warning compact-alert">Lớp này chưa map Course CMS nên kết quả học online có thể chưa đủ. Giáo viên vẫn xem được trạng thái Chưa đủ dữ liệu.</div>}
    </section>

    {step === 'subjects' && <section className="card academic-unified-card analytics-subject-picker-card">
      <div className="section-head list-card-head">
        <div>
          <h3>Môn</h3>
          <p>Chọn môn trước, sau đó mới sang màn danh sách lớp.</p>
        </div>
        <span className="status-pill neutral">{subjects.length} môn theo quyền</span>
      </div>
      <div className="academic-filter-bar compact-filter-row">
        <label>Tìm môn
          <input className="input" value={subjectSearch} onChange={(event) => resetScope({ search: event.target.value })} placeholder="COM1071, Tin học..." />
        </label>
      </div>
      <div className="academic-summary-strip analytics-class-overview-summary">
        <div><span>Môn</span><b>{subjectSummary.subject_count}</b></div>
        <div><span>Lớp</span><b>{subjectSummary.class_count}</b></div>
        <div><span>Sinh viên</span><b>{subjectSummary.student_count}</b></div>
        <div><span>Course CMS</span><b>{subjectSummary.course_mapped_count}/{subjectSummary.subject_count}</b></div>
        <div><span>Enrollment</span><b>{subjectSummary.learning_enrolled_count}</b></div>
      </div>
      <div className="table-wrap analytics-dashboard-table-wrap">
        <table className="data-table academic-data-table analytics-subject-picker-table">
          <thead>
            <tr><th>STT</th><th>Môn</th><th>Lớp</th><th>Sinh viên</th><th>Course CMS</th><th>Thao tác</th></tr>
          </thead>
          <tbody>
            {subjects.map((item, index) => <tr key={item.id}>
              <td className="stt-cell">{index + 1}</td>
              <td><b>{compactSubjectLabel(item)}</b><small>{item.branch?.toUpperCase() || branch.toUpperCase()}</small></td>
              <td>{item.class_count || 0}</td>
              <td>{item.student_count || 0}</td>
              <td><span className={item.openedx_course_id ? 'status-pill success' : 'status-pill warning'}>{item.openedx_course_id ? 'Đã map' : 'Chưa map'}</span></td>
              <td><button className="btn small primary" type="button" onClick={() => setFlowStep('classes', { subjectId: item.id, classId: '' })}>Xem lớp</button></td>
            </tr>)}
            {!subjects.length && <tr><td colSpan={6}><div className="empty-state compact">{loadingSubjects ? 'Đang tải môn theo phân quyền...' : 'Không có môn nào trong phân quyền/bộ lọc hiện tại.'}</div></td></tr>}
          </tbody>
        </table>
      </div>
    </section>}

    {step === 'classes' && <section className="card academic-unified-card analytics-class-overview-card">
      <div className="section-head list-card-head">
        <div>
          <h3>Lớp của môn {selectedSubject?.subject_code || ''}</h3>
          <p>{selectedSubject ? `${compactSubjectLabel(selectedSubject)} · ${classOverviewSummary.total_classes || 0} lớp · ${classOverviewSummary.total_students || 0} sinh viên` : 'Chọn môn để xem lớp.'}</p>
        </div>
        <div className="teacher-compact-actions">
          <button className="btn secondary small" type="button" onClick={() => setFlowStep('subjects', { subjectId: '', classId: '' })}>Quay lại môn</button>
          <span className="status-pill neutral">{classOverviewTotal ? `${(classOverviewPage - 1) * CLASS_OVERVIEW_PAGE_SIZE + 1}-${Math.min(classOverviewTotal, classOverviewPage * CLASS_OVERVIEW_PAGE_SIZE)} / ${classOverviewTotal}` : '0 lớp'}</span>
        </div>
      </div>

      <div className="academic-summary-strip analytics-class-overview-summary">
        <div><span>Tổng lớp</span><b>{classOverviewSummary.total_classes || 0}</b></div>
        <div><span>Tổng sinh viên</span><b>{classOverviewSummary.total_students || 0}</b></div>
        <div><span>Có dấu hiệu học thật</span><b>{classOverviewSummary.likely_real_learning_count || 0}</b></div>
        <div><span>Cần kiểm tra</span><b>{(classOverviewSummary.possible_idle_count || 0) + (classOverviewSummary.possible_suspicious_count || 0)}</b></div>
        <div><span>Chưa đủ dữ liệu</span><b>{classOverviewSummary.insufficient_data_count || 0}</b></div>
      </div>

      <div className="table-wrap analytics-dashboard-table-wrap analytics-class-overview-table-wrap">
        <table className="data-table academic-data-table analytics-class-overview-table">
          <thead>
            <tr>
              <th>STT</th>
              <th>Lớp</th>
              <th>Cơ sở</th>
              <th>Kết quả lớp</th>
              <th>Học thật</th>
              <th>Cần xem</th>
              <th>Chưa đủ dữ liệu</th>
              <th>Thao tác</th>
            </tr>
          </thead>
          <tbody>
            {classOverview.map((item, index) => <tr key={item.class_id}>
              <td className="stt-cell">{(classOverviewPage - 1) * CLASS_OVERVIEW_PAGE_SIZE + index + 1}</td>
              <td>
                <b>{item.class_code || item.class_name || item.class_id}</b>
                <small>{classDataStatusLabel(item)}{item.openedx_course_id ? ` · ${item.openedx_course_id}` : ' · Chưa map Course CMS'}</small>
              </td>
              <td>{item.campus?.toUpperCase() || 'N/A'}</td>
              <td><span className={resultClass(item.dominant_classification)}>{item.data_status === 'not_calculated' ? 'Chưa có kết quả' : resultLabel(item.dominant_classification, item.dominant_label)}</span></td>
              <td>{item.likely_real_learning_count || 0}</td>
              <td>{(item.possible_idle_count || 0) + (item.possible_suspicious_count || 0)}</td>
              <td>{item.insufficient_data_count || 0}</td>
              <td><button className="btn small primary" type="button" onClick={() => setFlowStep('results', { classId: item.class_id })}>Xem kết quả</button></td>
            </tr>)}
            {!classOverview.length && <tr><td colSpan={8}><div className="empty-state compact">{loadingClassOverview ? 'Đang tải lớp theo phân quyền...' : subjectId ? 'Không có lớp phù hợp với phân quyền/bộ lọc kết quả.' : 'Chọn môn để xem lớp.'}</div></td></tr>}
          </tbody>
        </table>
      </div>
      {classOverviewTotal > CLASS_OVERVIEW_PAGE_SIZE && <div className="pagination-row">
        <button className="btn secondary" type="button" disabled={classOverviewPage <= 1 || loadingClassOverview} onClick={() => setClassOverviewPage((value) => Math.max(1, value - 1))}>Trang trước</button>
        <span>Trang {classOverviewPage}/{Math.max(1, Math.ceil(classOverviewTotal / CLASS_OVERVIEW_PAGE_SIZE))}</span>
        <button className="btn secondary" type="button" disabled={classOverviewPage >= Math.ceil(classOverviewTotal / CLASS_OVERVIEW_PAGE_SIZE) || loadingClassOverview} onClick={() => setClassOverviewPage((value) => value + 1)}>Trang sau</button>
      </div>}
    </section>}

    {step === 'results' && <section className="card academic-unified-card">
      <div className="section-head list-card-head">
        <div>
          <h3>Xem kết quả lớp</h3>
          <p>{selectedClassOverview ? `${selectedClassOverview.class_code} · ${selectedSubject?.subject_code || ''} · ${selectedClassOverview.campus?.toUpperCase() || campusLabel(campus, campuses)} · ${selectedClassOverview.snapshot_count}/${selectedClassOverview.student_count} SV có kết quả` : 'Đang tải lớp đã chọn.'}</p>
        </div>
        <div className="teacher-compact-actions">
          <button className="btn secondary small" type="button" onClick={() => setFlowStep('classes', { classId: '' })}>Quay lại lớp</button>
          <button className="btn secondary small" type="button" onClick={() => setFlowStep('subjects', { subjectId: '', classId: '' })}>Quay lại môn</button>
          <span className="status-pill neutral">{totalRows ? `1-${Math.min(totalRows, PAGE_SIZE)} / ${totalRows}` : '0 sinh viên'}</span>
        </div>
      </div>

      <div className="academic-summary-strip analytics-summary-strip analytics-result-only-summary">
        <div><span>Tổng sinh viên</span><b>{summary.total_students || 0}</b></div>
        <div><span>Có dấu hiệu học thật</span><b>{summary.likely_real_learning_count || 0}</b></div>
        <div><span>Có khả năng treo máy</span><b>{summary.possible_idle_count || 0}</b></div>
        <div><span>Dấu hiệu bất thường cần kiểm tra</span><b>{summary.possible_suspicious_count || 0}</b></div>
        <div><span>Chưa đủ dữ liệu</span><b>{summary.insufficient_data_count || 0}</b></div>
        <div><span>Chưa thấy bất thường rõ</span><b>{summary.normal_count || 0}</b></div>
      </div>

      <div className="table-wrap analytics-dashboard-table-wrap">
        <table className="data-table academic-data-table analytics-learning-table analytics-result-table two-col-sticky-table analytics-two-col-sticky-table">
          <thead>
            <tr>
              <th className="stt-col sticky-index-col">STT</th>
              <th className="student-sticky-col">Sinh viên</th>
              <th>Kết quả</th>
              <th>Độ tin cậy</th>
              <th>Lần học cuối</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row, index) => <tr key={`${row.class_id}-${row.course_id}-${row.username}`}>
              <td className="stt-cell sticky-index-col">{index + 1}</td>
              <td className="student-sticky-col analytics-student-identity-cell"><b>{row.username}</b><small>{row.course_id || effectiveCourseId || 'Course CMS N/A'}</small></td>
              <td>
                <button className="analytics-result-button" type="button" onClick={() => openReason(row)} aria-label={`Xem lý do kết quả của ${row.username}`}>
                  <span className={resultClass(row.classification)}>{resultLabel(row.classification, row.display_label)}</span>
                </button>
              </td>
              <td>{percent(row.confidence_score)}</td>
              <td>{row.last_activity_at ? formatVNDateTime(row.last_activity_at) : 'N/A'}</td>
            </tr>)}
            {!rows.length && <tr><td colSpan={5}><div className="empty-state compact">{loadingResults ? 'Đang tải kết quả...' : classId ? 'Chưa có kết quả cho lớp/bộ lọc này.' : 'Chọn lớp trong danh sách để xem chi tiết kết quả.'}</div></td></tr>}
          </tbody>
        </table>
      </div>
    </section>}

    <DetailDrawer row={selectedRow} detail={detail} loading={detailLoading} onClose={() => { setSelectedRow(null); setDetail(null) }} />
  </div>
}
