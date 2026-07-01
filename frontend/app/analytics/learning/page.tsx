'use client'

import { useEffect, useMemo, useState } from 'react'
import Link from 'next/link'
import { useAppContext } from '../../../context/AppContext'
import { buildAnalyticsLearningExportUrl, enqueueAnalyticsBackfillJobs, getAnalyticsBackfillPlan, getAnalyticsDataQualityReport, getAnalyticsLearningDashboard, getAnalyticsProductionReadiness, getAnalyticsPilotAcceptance, getAnalyticsRolloutControl, getAnalyticsMonitoring } from '../../../lib/api'
import { AnalyticsBackfillPlanResponse, AnalyticsDataQualityReport, AnalyticsLearningDashboardResponse, AnalyticsProductionReadinessReport, AnalyticsPilotAcceptanceReport, AnalyticsRolloutControlReport, AnalyticsMonitoringReport, AnalyticsLearningDashboardStudent } from '../../../types'
import { formatVNDateTime } from '../../../lib/time'

const CLASSIFICATION_OPTIONS = [
  { value: 'all', label: 'Tất cả nhận định' },
  { value: 'LIKELY_REAL_LEARNING', label: 'Có dấu hiệu học thật' },
  { value: 'POSSIBLE_IDLE', label: 'Có khả năng treo máy' },
  { value: 'POSSIBLE_CHEATING', label: 'Dấu hiệu bất thường cần kiểm tra' },
  { value: 'INSUFFICIENT_DATA', label: 'Chưa đủ dữ liệu' },
  { value: 'NORMAL', label: 'Chưa thấy bất thường rõ' },
]

function percent(value?: number | null) {
  if (typeof value !== 'number' || Number.isNaN(value)) return 'N/A'
  return `${Math.round(value * 10) / 10}%`
}

function behaviorClass(value?: string | null) {
  const classification = String(value || '').toUpperCase()
  if (classification === 'LIKELY_REAL_LEARNING') return 'status-pill success'
  if (classification === 'POSSIBLE_IDLE') return 'status-pill warning'
  if (classification === 'POSSIBLE_CHEATING') return 'status-pill danger'
  return 'status-pill neutral'
}

function duration(seconds?: number | null) {
  if (typeof seconds !== 'number' || Number.isNaN(seconds) || seconds <= 0) return 'N/A'
  const minutes = Math.round(seconds / 60)
  if (minutes < 60) return `${minutes} phút`
  const hours = Math.floor(minutes / 60)
  const remain = minutes % 60
  return remain ? `${hours} giờ ${remain} phút` : `${hours} giờ`
}


function compactIssue(issue: { code?: string | null; message?: string | null; action?: string | null }) {
  const code = String(issue?.code || '').toUpperCase()
  if (code.includes('NO_BEHAVIOR') || code.includes('SNAPSHOT')) return 'Chưa có snapshot học online → bấm Backfill học online.'
  if (code.includes('MISSING_SESSION')) return 'Thiếu mapping Bài/Session → vẫn có thể backfill để tạo Chưa đủ dữ liệu, sau đó rebuild mapping.'
  if (code.includes('TRACKING_LOG')) return 'Tracking log đã mount/chưa mount → kiểm tra doctor nếu cần.'
  if (code.includes('NO_TRACKING_EVENTS')) return 'Chưa ingest event học online → chờ scheduler hoặc chạy ingest thủ công.'
  if (code.includes('COURSE_MAPPING')) return 'Có lớp thiếu Course CMS → kiểm tra map course.'
  const text = String(issue?.message || 'Cần kiểm tra dữ liệu học online')
  const action = String(issue?.action || '')
  return action ? `${text} → ${action}` : text
}

function actionText(value?: string | null) {
  const raw = String(value || '')
  if (!raw) return 'Kiểm tra lại sau'
  return raw
}

function StudentRows({ rows, emptyText }: { rows?: AnalyticsLearningDashboardStudent[]; emptyText: string }) {
  const items = rows || []
  if (!items.length) return <div className="empty-state compact">{emptyText}</div>
  return <div className="table-wrap analytics-dashboard-table-wrap">
    <table className="data-table academic-data-table analytics-learning-table">
      <thead>
        <tr>
          <th>STT</th>
          <th>Sinh viên</th>
          <th>Lớp</th>
          <th>Nhận định</th>
          <th>Điểm tín hiệu</th>
          <th>Deadline</th>
          <th>Dấu hiệu chính</th>
          <th>Hành động</th>
          <th>Lần học cuối</th>
        </tr>
      </thead>
      <tbody>
        {items.map((row, index) => <tr key={`${row.class_id}-${row.course_id}-${row.username}`}>
          <td className="stt-cell">{index + 1}</td>
          <td>
            <b>{row.username}</b>
            <small>{row.course_id}</small>
          </td>
          <td>
            <b>{row.class_code || row.class_id || 'N/A'}</b>
            <small>{row.campus || ''}</small>
          </td>
          <td><span className={behaviorClass(row.classification)}>{row.display_label || 'Chưa đủ dữ liệu'}</span></td>
          <td>
            <div className="academic-mini-lines">
              <span>Độ tin cậy: {percent(row.confidence_score)}</span>
              <span>Học thật: {percent(row.real_learning_score)}</span>
              <span>Treo máy: {percent(row.idle_score)}</span>
              <span>Bất thường: {percent(row.suspicious_score)}</span>
            </div>
          </td>
          <td>
            <div className="academic-mini-lines">
              <span>Đúng hạn: {percent(row.deadline_compliance_percent)}</span>
              <span>Học dồn: {row.crammed_session_count || 0}</span>
              <span>Quiz trước video: {row.quiz_before_video_count || 0}</span>
            </div>
          </td>
          <td><small>{(row.reason_codes || []).slice(0, 4).join(', ') || row.human_readable_summary || 'N/A'}</small></td>
          <td>{actionText(row.recommended_action)}</td>
          <td>{row.last_activity_at ? formatVNDateTime(row.last_activity_at) : 'N/A'}</td>
        </tr>)}
      </tbody>
    </table>
  </div>
}

export default function AnalyticsLearningPage() {
  const { authHeaders } = useAppContext()
  const headers = useMemo(() => authHeaders(), [authHeaders])
  const [campus, setCampus] = useState('')
  const [branch, setBranch] = useState('')
  const [classId, setClassId] = useState('')
  const [courseId, setCourseId] = useState('')
  const [classification, setClassification] = useState('all')
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [data, setData] = useState<AnalyticsLearningDashboardResponse | null>(null)
  const [dataQuality, setDataQuality] = useState<AnalyticsDataQualityReport | null>(null)
  const [backfillPlan, setBackfillPlan] = useState<AnalyticsBackfillPlanResponse | null>(null)
  const [productionReadiness, setProductionReadiness] = useState<AnalyticsProductionReadinessReport | null>(null)
  const [pilotAcceptance, setPilotAcceptance] = useState<AnalyticsPilotAcceptanceReport | null>(null)
  const [rolloutControl, setRolloutControl] = useState<AnalyticsRolloutControlReport | null>(null)
  const [monitoring, setMonitoring] = useState<AnalyticsMonitoringReport | null>(null)
  const [loading, setLoading] = useState(false)
  const [backfillLoading, setBackfillLoading] = useState(false)
  const [message, setMessage] = useState('')

  const filters = useMemo(() => ({ campus, branch, classId, courseId, classification, dateFrom, dateTo, limit: 50 }), [campus, branch, classId, courseId, classification, dateFrom, dateTo])

  const load = async () => {
    setLoading(true)
    setMessage('')
    try {
      const [result, quality, plan, production, pilot, rollout, monitor] = await Promise.all([
        getAnalyticsLearningDashboard(headers, filters),
        getAnalyticsDataQualityReport(headers, { classId, courseId }),
        getAnalyticsBackfillPlan(headers, { campus, branch, classId, courseId, limit: 20 }),
        getAnalyticsProductionReadiness(headers),
        getAnalyticsPilotAcceptance(headers, { campus, branch, classId, courseId, sampleLimit: 5 }),
        getAnalyticsRolloutControl(headers, { campus, branch, classId, courseId, limit: 100 }),
        getAnalyticsMonitoring(headers, { classId, courseId }),
      ])
      setData(result)
      setDataQuality(quality)
      setBackfillPlan(plan)
      setProductionReadiness(production)
      setPilotAcceptance(pilot)
      setRolloutControl(rollout)
      setMonitoring(monitor)
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Không tải được dữ liệu học online')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
  }, [headers, filters])


  const readinessLabel = (value?: string | null) => {
    if (value === 'READY') return 'Sẵn sàng dùng'
    if (value === 'NEEDS_BACKFILL') return 'Cần backfill/cập nhật'
    if (value === 'CONFIG_NEEDED') return 'Cần cấu hình dữ liệu'
    if (value === 'NO_SCOPE') return 'Không có quyền'
    return value || 'Chưa kiểm tra'
  }

  const readinessClass = (value?: string | null) => {
    if (value === 'READY') return 'status-pill success'
    if (value === 'CONFIG_NEEDED') return 'status-pill danger'
    if (value === 'NEEDS_BACKFILL') return 'status-pill warning'
    return 'status-pill neutral'
  }

  const productionReadinessLabel = (value?: string | null) => {
    if (value === 'PRODUCTION_READY') return 'Sẵn sàng production'
    if (value === 'NOT_READY') return 'Chưa sẵn sàng production'
    return value || 'Chưa kiểm tra production'
  }

  const productionReadinessClass = (value?: string | null) => {
    if (value === 'PRODUCTION_READY') return 'status-pill success'
    if (value === 'NOT_READY') return 'status-pill danger'
    return 'status-pill neutral'
  }

  const rolloutStatusClass = (value?: string | null) => {
    if (value === 'READY') return 'status-pill success'
    if (value === 'READY_WITH_WARNINGS') return 'status-pill warning'
    if (value === 'DISABLED') return 'status-pill danger'
    return 'status-pill neutral'
  }

  const monitoringStatusClass = (value?: string | null) => {
    if (value === 'OK') return 'status-pill success'
    if (value === 'WARNING') return 'status-pill warning'
    if (value === 'BLOCKED') return 'status-pill danger'
    return 'status-pill neutral'
  }

  const enqueueBackfill = async () => {
    setBackfillLoading(true)
    setMessage('')
    try {
      const result = await enqueueAnalyticsBackfillJobs(headers, { campus, branch, classId, courseId, limit: 20 })
      setMessage(`Đã đưa ${result.queued_jobs || 0} lớp vào hàng đợi học online. Bỏ qua ${result.skipped_count || 0} lớp.`)
      await load()
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Không đưa được backfill học online vào hàng đợi')
    } finally {
      setBackfillLoading(false)
    }
  }

  const exportCsv = () => {
    const url = buildAnalyticsLearningExportUrl(filters)
    window.open(url, '_blank', 'noopener,noreferrer')
  }

  return <div className="page-stack analytics-learning-page">
    <section className="card academic-unified-card">
      <div className="section-head list-card-head">
        <div>
          <h2>Học online</h2>
          <p>Tổng hợp tín hiệu học theo log video, quiz cuối Bài và deadline. Đây là nhận định hỗ trợ kiểm tra, không phải kết luận vi phạm.</p>
        </div>
        <div className="header-actions compact">
          <button className="btn secondary" type="button" onClick={load} disabled={loading}>{loading ? 'Đang tải...' : 'Tải lại'}</button>
          <button className="btn secondary" type="button" onClick={enqueueBackfill} disabled={backfillLoading}>{backfillLoading ? 'Đang đưa vào hàng đợi...' : 'Backfill học online'}</button>
          <button className="btn primary" type="button" onClick={exportCsv}>Xuất CSV</button>
        </div>
      </div>

      <div className="academic-filter-bar analytics-learning-filters">
        <label>Hệ
          <input className="input" value={branch} onChange={(event) => setBranch(event.target.value)} placeholder="poly / ptcd" />
        </label>
        <label>Cơ sở
          <input className="input" value={campus} onChange={(event) => setCampus(event.target.value)} placeholder="HN, HCM..." />
        </label>
        <label>Lớp
          <input className="input" value={classId} onChange={(event) => setClassId(event.target.value)} placeholder="class_id" />
        </label>
        <label>Course ID
          <input className="input" value={courseId} onChange={(event) => setCourseId(event.target.value)} placeholder="course-v1:..." />
        </label>
        <label>Nhận định
          <select className="input" value={classification} onChange={(event) => setClassification(event.target.value)}>
            {CLASSIFICATION_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
          </select>
        </label>
        <label>Từ ngày
          <input className="input" type="date" value={dateFrom} onChange={(event) => setDateFrom(event.target.value)} />
        </label>
        <label>Đến ngày
          <input className="input" type="date" value={dateTo} onChange={(event) => setDateTo(event.target.value)} />
        </label>
      </div>

      {message && <div className="academic-inline-error"><b>Không tải được dữ liệu</b><span>{message}</span></div>}


      <div className="academic-summary-strip analytics-quality-strip">
        <div><span>Pilot acceptance</span><b><span className={pilotAcceptance?.pilot_status === 'PASS' ? 'status-pill success' : pilotAcceptance?.pilot_status === 'PASS_WITH_WARNINGS' ? 'status-pill warning' : 'status-pill danger'}>{pilotAcceptance?.pilot_status === 'PASS' ? 'Pilot đạt' : pilotAcceptance?.pilot_status === 'PASS_WITH_WARNINGS' ? 'Pilot đạt có cảnh báo' : 'Pilot chưa đạt'}</span></b><small>{pilotAcceptance?.blocker_count || 0} blocker, {pilotAcceptance?.warning_count || 0} cảnh báo</small></div>
        <div><span>Production readiness</span><b><span className={productionReadinessClass(productionReadiness?.readiness)}>{productionReadinessLabel(productionReadiness?.readiness)}</span></b><small>{productionReadiness?.blocker_count || 0} blocker, {productionReadiness?.warning_count || 0} cảnh báo</small></div>
        <div><span>Rollout</span><b><span className={rolloutStatusClass(rolloutControl?.rollout_status)}>{rolloutControl?.enabled ? (rolloutControl?.mode === 'PRODUCTION' ? 'Mở production' : 'Mở pilot') : 'Đang tắt'}</span></b><small>{rolloutControl?.counters?.in_rollout || 0} lớp trong phạm vi</small></div>
        <div><span>Monitoring</span><b><span className={monitoringStatusClass(monitoring?.monitoring_status)}>{monitoring?.monitoring_status === 'OK' ? 'Ổn định' : monitoring?.monitoring_status === 'WARNING' ? 'Có cảnh báo' : monitoring?.monitoring_status === 'BLOCKED' ? 'Có blocker' : 'Chưa kiểm tra'}</span></b><small>{monitoring?.stuck_analytics_job_count || 0} job treo, {monitoring?.stale_snapshot_count || 0} snapshot cũ</small></div>
        <div><span>Trạng thái dữ liệu</span><b><span className={readinessClass(dataQuality?.readiness)}>{readinessLabel(dataQuality?.readiness)}</span></b><small>{dataQuality?.issues?.length || 0} việc cần kiểm tra</small></div>
        <div><span>Tracking log</span><b>{dataQuality?.ingest?.file_exists ? 'Đã mount' : 'Chưa thấy'}</b><small>{dataQuality?.ingest?.file_path || '/openedx-data/lms/logs/tracking.log'}</small></div>
        <div><span>Events đã ingest</span><b>{dataQuality?.counts?.tracking_events_inserted || 0}</b><small>Không đọc raw log khi mở dashboard</small></div>
        <div><span>Snapshot học online</span><b>{dataQuality?.counts?.behavior_snapshot_count || 0}</b><small>{dataQuality?.latest_behavior_calculated_at ? formatVNDateTime(dataQuality.latest_behavior_calculated_at) : 'Chưa có'}</small></div>
        <div><span>Lớp có thể backfill</span><b>{backfillPlan?.counters?.enqueueable || 0}</b><small>{backfillPlan?.total || 0} lớp trong phạm vi</small></div>
      </div>
      {!!productionReadiness?.issues?.length && <div className="alert warning compact-alert analytics-quality-issues">
        <b>Cần xử lý trước production</b>
        <span>{Array.from(new Set(productionReadiness.issues.slice(0, 4).map(compactIssue))).join(' | ')}</span>
      </div>}
      {!!rolloutControl?.issues?.length && <div className="alert warning compact-alert analytics-quality-issues">
        <b>Rollout cần kiểm tra</b>
        <span>{Array.from(new Set(rolloutControl.issues.slice(0, 4).map(compactIssue))).join(' | ')}</span>
      </div>}
      {!!monitoring?.issues?.length && <div className="alert warning compact-alert analytics-quality-issues">
        <b>Monitoring cần kiểm tra</b>
        <span>{Array.from(new Set(monitoring.issues.slice(0, 4).map(compactIssue))).join(' | ')}</span>
      </div>}
      {!!pilotAcceptance?.classes?.length && <div className="table-wrap analytics-dashboard-table-wrap pilot-acceptance-table-wrap">
        <table className="data-table academic-data-table analytics-pilot-table">
          <thead>
            <tr><th>STT</th><th>Lớp pilot</th><th>Trạng thái</th><th>Sinh viên</th><th>Snapshot</th><th>Session</th><th>Video</th><th>Việc cần làm</th></tr>
          </thead>
          <tbody>
            {pilotAcceptance.classes.slice(0, 3).map((row, index) => <tr key={row.class_id}>
              <td className="stt-cell">{index + 1}</td>
              <td><b>{row.class_code || row.class_id}</b><small>{row.course_id || 'Chưa map course'}</small></td>
              <td><span className={row.acceptance_status === 'PASS' ? 'status-pill success' : row.acceptance_status === 'WARN' ? 'status-pill warning' : 'status-pill danger'}>{row.acceptance_status === 'PASS' ? 'Đạt pilot' : row.acceptance_status === 'WARN' ? 'Có cảnh báo' : 'Chưa đạt'}</span></td>
              <td>{row.student_count}</td>
              <td>{row.behavior_snapshot_count}</td>
              <td>{row.session_count}</td>
              <td>{row.video_progress_count}</td>
              <td><small>{row.recommended_action || (row.reasons || []).join(', ') || 'Kiểm tra lại sau'}</small></td>
            </tr>)}
          </tbody>
        </table>
      </div>}

      <div className="academic-summary-strip analytics-summary-strip">
        <div><span>Tổng sinh viên</span><b>{data?.total_students || 0}</b><small>Theo bộ lọc</small></div>
        <div><span>Có dấu hiệu học thật</span><b>{data?.likely_real_learning_count || 0}</b><small>Tín hiệu tốt</small></div>
        <div><span>Có khả năng treo máy</span><b>{data?.possible_idle_count || 0}</b><small>Cần nhắc/kiểm tra</small></div>
        <div><span>Dấu hiệu bất thường</span><b>{data?.possible_suspicious_count || 0}</b><small>Cần giáo viên xác minh</small></div>
        <div><span>Chưa đủ dữ liệu</span><b>{data?.insufficient_data_count || 0}</b><small>Log/mapping còn thiếu</small></div>
        <div><span>Bình thường</span><b>{data?.normal_count || 0}</b><small>Chưa thấy bất thường rõ</small></div>
      </div>
      <div className="alert neutral compact-alert">{data?.disclaimer || 'Dữ liệu chỉ phản ánh dấu hiệu từ log hệ thống, không phải kết luận vi phạm.'}</div>
    </section>

    <section className="card academic-unified-card">
      <div className="section-head list-card-head">
        <div>
          <h3>Lớp cần chú ý</h3>
          <p>Lớp có nhiều tín hiệu cần giáo viên kiểm tra trước.</p>
        </div>
      </div>
      <div className="table-wrap analytics-dashboard-table-wrap">
        <table className="data-table academic-data-table analytics-class-table">
          <thead>
            <tr>
              <th>STT</th>
              <th>Lớp</th>
              <th>Course</th>
              <th>Sinh viên</th>
              <th>Học thật</th>
              <th>Treo máy</th>
              <th>Bất thường</th>
              <th>Thiếu dữ liệu</th>
              <th>Deadline</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {(data?.class_items || []).map((row, index) => <tr key={row.class_id}>
              <td className="stt-cell">{index + 1}</td>
              <td><b>{row.class_code || row.class_id}</b><small>{row.campus || ''} {row.class_name || ''}</small></td>
              <td><small>{row.course_id || 'N/A'}</small></td>
              <td>{row.total_students}</td>
              <td>{row.likely_real_learning_count}</td>
              <td>{row.possible_idle_count}</td>
              <td>{row.possible_suspicious_count}</td>
              <td>{row.insufficient_data_count}</td>
              <td>{percent(row.avg_deadline_compliance_percent)}</td>
              <td><Link className="btn secondary small" href={`/student-management/classes/${encodeURIComponent(row.class_id)}`}>Mở lớp</Link></td>
            </tr>)}
            {!data?.class_items?.length && <tr><td colSpan={10}><div className="empty-state compact">Chưa có snapshot học online. Hãy ingest log và tính lại học online cho lớp.</div></td></tr>}
          </tbody>
        </table>
      </div>
    </section>

    <section className="card academic-unified-card">
      <div className="section-head list-card-head">
        <div>
          <h3>Dấu hiệu bất thường cần kiểm tra</h3>
          <p>Danh sách ưu tiên để giáo viên xem thêm bằng chứng, không phải danh sách kết luận vi phạm.</p>
        </div>
      </div>
      <StudentRows rows={data?.top_possible_suspicious || []} emptyText="Chưa có sinh viên cần kiểm tra theo bộ lọc hiện tại." />
    </section>

    <section className="card academic-unified-card">
      <div className="section-head list-card-head">
        <div>
          <h3>Có khả năng treo máy</h3>
          <p>Tín hiệu video chạy dài, ít tương tác hoặc thiếu hoạt động quiz sau video.</p>
        </div>
      </div>
      <StudentRows rows={data?.top_possible_idle || []} emptyText="Chưa có tín hiệu treo máy rõ theo bộ lọc hiện tại." />
    </section>

    <section className="card academic-unified-card">
      <div className="section-head list-card-head">
        <div>
          <h3>Deadline cần chú ý</h3>
          <p>Sinh viên có học dồn, trễ hạn hoặc tỷ lệ đúng hạn thấp.</p>
        </div>
      </div>
      <StudentRows rows={data?.deadline_attention || []} emptyText="Chưa có tín hiệu deadline cần chú ý theo bộ lọc hiện tại." />
    </section>
  </div>
}
