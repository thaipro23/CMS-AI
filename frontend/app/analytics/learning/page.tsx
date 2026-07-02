'use client'

import { useEffect, useMemo, useState } from 'react'
import { useAppContext } from '../../../context/AppContext'
import {
  getAcademicCampuses,
  getAcademicSubjectClasses,
  getAcademicTeacherSubjects,
  getAcademicTerms,
  getAnalyticsClassLearningBehavior,
  getAnalyticsClassLearningBehaviorSummary,
  getAnalyticsStudentLearningBehaviorDetail,
} from '../../../lib/api'
import {
  AcademicCampus,
  AcademicClass,
  AcademicSubjectManagement,
  AcademicTerm,
  AnalyticsLearningBehaviorRow,
  AnalyticsLearningBehaviorSummary,
  AnalyticsStudentLearningBehaviorDetail,
} from '../../../types'
import { formatVNDateTime } from '../../../lib/time'

const PAGE_SIZE = 200

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

function compactClassLabel(item: AcademicClass) {
  const code = item.class_code || item.class_name || item.id
  const count = typeof item.student_count === 'number' ? `${item.student_count} SV` : 'SV N/A'
  return `${code} · ${count}`
}

function compactSubjectLabel(item: AcademicSubjectManagement) {
  const code = item.subject_code || item.skill_code || 'Môn'
  const name = item.subject_name || item.subject_name_en || ''
  const suffix = typeof item.class_count === 'number' ? ` · ${item.class_count} lớp` : ''
  return `${code}${name ? ` — ${name}` : ''}${suffix}`
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
  const { authHeaders } = useAppContext()
  const headers = useMemo(() => authHeaders(), [authHeaders])
  const [terms, setTerms] = useState<AcademicTerm[]>([])
  const [campuses, setCampuses] = useState<AcademicCampus[]>([])
  const [subjects, setSubjects] = useState<AcademicSubjectManagement[]>([])
  const [classes, setClasses] = useState<AcademicClass[]>([])
  const [branch, setBranch] = useState('poly')
  const [termId, setTermId] = useState('')
  const [campus, setCampus] = useState('')
  const [subjectId, setSubjectId] = useState('')
  const [classId, setClassId] = useState('')
  const [classification, setClassification] = useState('all')
  const [summary, setSummary] = useState<AnalyticsLearningBehaviorSummary>(EMPTY_SUMMARY)
  const [rows, setRows] = useState<AnalyticsLearningBehaviorRow[]>([])
  const [totalRows, setTotalRows] = useState(0)
  const [loadingTerms, setLoadingTerms] = useState(false)
  const [loadingSubjects, setLoadingSubjects] = useState(false)
  const [loadingClasses, setLoadingClasses] = useState(false)
  const [loadingResults, setLoadingResults] = useState(false)
  const [message, setMessage] = useState('')
  const [selectedRow, setSelectedRow] = useState<AnalyticsLearningBehaviorRow | null>(null)
  const [detail, setDetail] = useState<AnalyticsStudentLearningBehaviorDetail | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)

  const selectedTerm = useMemo(() => terms.find((item) => item.id === termId) || null, [terms, termId])
  const selectedSubject = useMemo(() => subjects.find((item) => item.id === subjectId) || null, [subjects, subjectId])
  const selectedClass = useMemo(() => classes.find((item) => item.id === classId) || null, [classes, classId])
  const effectiveCourseId = selectedClass?.openedx_course_id || null

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
        setCampus((current) => items.some((item) => item.campus_code === current) ? current : (items[0]?.campus_code || ''))
      })
      .catch(() => { if (!cancelled) setCampuses([]) })
    return () => { cancelled = true }
  }, [headers, branch])

  useEffect(() => {
    if (!termId || !campus) {
      setSubjects([])
      setSubjectId('')
      return
    }
    let cancelled = false
    setLoadingSubjects(true)
    setSubjects([])
    setClasses([])
    setSubjectId('')
    setClassId('')
    setRows([])
    setTotalRows(0)
    setSummary(EMPTY_SUMMARY)
    getAcademicTeacherSubjects(headers, { termId, branch, campus, page: 1, pageSize: 500 })
      .then((result) => {
        if (cancelled) return
        const items = result.items || []
        setSubjects(items)
        setSubjectId((current) => items.some((item) => item.id === current) ? current : (items[0]?.id || ''))
      })
      .catch((error) => { if (!cancelled) setMessage(error instanceof Error ? error.message : 'Không tải được môn') })
      .finally(() => { if (!cancelled) setLoadingSubjects(false) })
    return () => { cancelled = true }
  }, [headers, termId, campus, branch])

  useEffect(() => {
    setClassId('')
    setClasses([])
  }, [subjectId])

  useEffect(() => {
    if (!subjectId) return
    let cancelled = false
    setLoadingClasses(true)
    getAcademicSubjectClasses(headers, subjectId, { termId, campus, branch, page: 1, pageSize: 500 })
      .then((result) => {
        if (cancelled) return
        const items = result.items || []
        setClasses(items)
        setClassId((current) => items.some((item) => item.id === current) ? current : (items[0]?.id || ''))
      })
      .catch((error) => { if (!cancelled) setMessage(error instanceof Error ? error.message : 'Không tải được lớp') })
      .finally(() => { if (!cancelled) setLoadingClasses(false) })
    return () => { cancelled = true }
  }, [headers, subjectId, termId, campus, branch])

  useEffect(() => {
    if (!classId) {
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
  }, [headers, classId, effectiveCourseId, classification])

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

  return <div className="page-stack analytics-learning-page analytics-learning-result-only-page">
    <section className="card academic-unified-card">
      <div className="section-head list-card-head">
        <div>
          <h2>Phân tích hành vi học</h2>
          <p>Chọn kỳ, cơ sở, môn và lớp để xem kết quả học online của sinh viên.</p>
        </div>
      </div>

      <div className="academic-filter-bar analytics-learning-flow-filters">
        <label>Hệ
          <select className="input" value={branch} onChange={(event) => setBranch(event.target.value)}>
            <option value="poly">Poly</option>
            <option value="ptcd">PTCĐ</option>
          </select>
        </label>
        <label>Học kỳ
          <select className="input" value={termId} onChange={(event) => setTermId(event.target.value)} disabled={loadingTerms}>
            {terms.map((item) => <option key={item.id} value={item.id}>{item.term_name}</option>)}
          </select>
        </label>
        <label>Cơ sở
          <select className="input" value={campus} onChange={(event) => setCampus(event.target.value)}>
            {campuses.map((item) => <option key={item.id || item.campus_code} value={item.campus_code}>{item.campus_code?.toUpperCase()} · {item.campus_name}</option>)}
          </select>
        </label>
        <label>Môn
          <select className="input" value={subjectId} onChange={(event) => setSubjectId(event.target.value)} disabled={loadingSubjects || !campus || !termId}>
            {subjects.map((item) => <option key={item.id} value={item.id}>{compactSubjectLabel(item)}</option>)}
          </select>
        </label>
        <label>Lớp
          <select className="input" value={classId} onChange={(event) => setClassId(event.target.value)} disabled={loadingClasses || !subjectId}>
            {classes.map((item) => <option key={item.id} value={item.id}>{compactClassLabel(item)}</option>)}
          </select>
        </label>
        <label>Kết quả
          <select className="input" value={classification} onChange={(event) => setClassification(event.target.value)} disabled={!classId}>
            {CLASSIFICATION_OPTIONS.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
          </select>
        </label>
      </div>

      <div className="analytics-flow-context">
        <span>{selectedTerm?.term_name || 'Chưa chọn kỳ'}</span>
        <span>{campus ? campus.toUpperCase() : 'Chưa chọn cơ sở'}</span>
        <span>{selectedSubject?.subject_code || 'Chưa chọn môn'}</span>
        <span>{selectedClass?.class_code || 'Chưa chọn lớp'}</span>
      </div>

      {message && <div className="academic-inline-error"><b>Cần kiểm tra</b><span>{message}</span></div>}
      {!effectiveCourseId && classId && <div className="alert warning compact-alert">Lớp này chưa map Course CMS nên kết quả học online có thể chưa đủ.</div>}
    </section>

    <section className="card academic-unified-card">
      <div className="section-head list-card-head">
        <div>
          <h3>Kết quả lớp</h3>
          <p>{selectedClass ? `${selectedClass.class_code} · ${selectedSubject?.subject_code || ''} · ${campus.toUpperCase()}` : 'Chọn lớp để xem kết quả.'}</p>
        </div>
        <span className="status-pill neutral">{totalRows ? `1-${Math.min(totalRows, PAGE_SIZE)} / ${totalRows}` : '0 sinh viên'}</span>
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
        <table className="data-table academic-data-table analytics-learning-table analytics-result-table">
          <thead>
            <tr>
              <th>STT</th>
              <th>Sinh viên</th>
              <th>Kết quả</th>
              <th>Độ tin cậy</th>
              <th>Lần học cuối</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row, index) => <tr key={`${row.class_id}-${row.course_id}-${row.username}`}>
              <td className="stt-cell">{index + 1}</td>
              <td><b>{row.username}</b><small>{row.course_id || effectiveCourseId || 'Course CMS N/A'}</small></td>
              <td>
                <button className="analytics-result-button" type="button" onClick={() => openReason(row)} aria-label={`Xem lý do kết quả của ${row.username}`}>
                  <span className={resultClass(row.classification)}>{resultLabel(row.classification, row.display_label)}</span>
                </button>
              </td>
              <td>{percent(row.confidence_score)}</td>
              <td>{row.last_activity_at ? formatVNDateTime(row.last_activity_at) : 'N/A'}</td>
            </tr>)}
            {!rows.length && <tr><td colSpan={5}><div className="empty-state compact">{loadingResults ? 'Đang tải kết quả...' : classId ? 'Chưa có kết quả cho lớp/bộ lọc này.' : 'Chọn kỳ, cơ sở, môn và lớp để xem kết quả.'}</div></td></tr>}
          </tbody>
        </table>
      </div>
    </section>

    <DetailDrawer row={selectedRow} detail={detail} loading={detailLoading} onClose={() => { setSelectedRow(null); setDetail(null) }} />
  </div>
}
