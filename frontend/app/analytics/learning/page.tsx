'use client'

import { useEffect, useMemo, useState } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import { useAppContext } from '../../../context/AppContext'
import {
  getAcademicCampuses,
  getAcademicTeacherSubjects,
  getAcademicTerms,
  getAnalyticsClassWorkspace,
  getAnalyticsClassResultDoctor,
  getAnalyticsProductionReadiness,
  getAnalyticsSlaReport,
  getAnalyticsPilotAcceptance,
  getAnalyticsEvidencePack,
  getAnalyticsCourseClassMappingReport,
  getPerformanceReadiness,
  getSecurityReadiness,
  getReleaseCandidateReadiness,
  getPilotOperationsReadiness,
  enqueueAnalyticsClassDoctorRecalculate,
  getAnalyticsStudentLearningBehaviorDetail,
  getAnalyticsSubjectClassBehaviorOverview,
} from '../../../lib/api'
import {
  AcademicCampus,
  AcademicSubjectManagement,
  AcademicTerm,
  AnalyticsClassBehaviorOverviewItem,
  AnalyticsClassBehaviorOverviewSummary,
  AnalyticsClassResultDoctor,
  AnalyticsLearningBehaviorRow,
  AnalyticsLearningBehaviorSummary,
  AnalyticsProductionReadinessReport,
  AnalyticsSlaReport,
  AnalyticsPilotAcceptanceReport,
  AnalyticsEvidencePackReport,
  AnalyticsCourseClassMappingReport,
  PerformanceReadinessReport,
  SecurityReadinessReport,
  ReleaseCandidateReport,
  PilotOperationsReport,
  AnalyticsDataQualityIssue,
  AnalyticsStudentLearningBehaviorDetail,
  AnalyticsStudentSessionProgress,
} from '../../../types'
import { formatVNDateTime } from '../../../lib/time'
import { useDebouncedValue } from '../../../lib/useDebouncedValue'
import { SHOW_DIAGNOSTICS_UI } from '../../../lib/runtime'
import { PageRoot } from '../../../components/layout/PageHeader'
import { EnterpriseScreenHeader } from '../../../components/layout/EnterpriseDesignContract'
import { AccessibleDialog } from '../../../components/ui/AccessibleDialog'
import { EnterpriseDataTable, EnterpriseTableColumn } from '../../../components/table/EnterpriseDataTable'
import { TrainingContextChips, TrainingKpiStrip, TrainingMappingEmptyState, TrainingWorkflowSteps } from '../../../components/training/TrainingWorkspace'

const PAGE_SIZE = 200
const SUBJECT_PAGE_SIZE = 50
const CLASS_OVERVIEW_PAGE_SIZE = 200

type AnalyticsFlowStep = 'subjects' | 'classes' | 'results'

const CLASSIFICATION_OPTIONS = [
  { value: 'all', label: 'Tất cả trạng thái' },
  { value: 'LIKELY_REAL_LEARNING', label: 'Có dấu hiệu học thật' },
  { value: 'POSSIBLE_IDLE', label: 'Có khả năng treo máy' },
  { value: 'POSSIBLE_ANOMALY', label: 'Dấu hiệu bất thường cần kiểm tra' },
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


function analyticsErrorMessage(error: unknown, fallback: string) {
  const raw = error instanceof Error ? error.message : typeof error === 'string' ? error : ''
  if (!raw) return fallback
  if (/failed to fetch|networkerror|load failed|network request failed/i.test(raw)) {
    return 'Không kết nối được API phân tích học tập. Vui lòng tải lại; nếu lớp chưa ghép Course CMS, hãy hoàn tất mapping trước.'
  }
  if (/403|forbidden|permission/i.test(raw)) return 'Bạn không có quyền xem dữ liệu lớp này trong phạm vi hiện tại.'
  if (/404|not found/i.test(raw)) return 'Không tìm thấy dữ liệu lớp hoặc Course CMS tương ứng.'
  return raw.length > 220 ? fallback : raw
}

function resultLabel(value?: string | null, fallback?: string | null) {
  const classification = String(value || '').toUpperCase()
  if (classification === 'LIKELY_REAL_LEARNING') return 'Có dấu hiệu học thật'
  if (classification === 'POSSIBLE_IDLE') return 'Có khả năng treo máy'
  if ((classification === 'POSSIBLE_ANOMALY' || classification === 'POSSIBLE_CHEATING')) return 'Dấu hiệu bất thường cần kiểm tra'
  if (classification === 'INSUFFICIENT_DATA') return 'Chưa đủ dữ liệu'
  if (classification === 'NORMAL') return 'Chưa thấy bất thường rõ'
  return fallback || 'Chưa đủ dữ liệu'
}

function resultClass(value?: string | null) {
  const classification = String(value || '').toUpperCase()
  if (classification === 'LIKELY_REAL_LEARNING') return 'status-pill success'
  if (classification === 'POSSIBLE_IDLE') return 'status-pill warning'
  if ((classification === 'POSSIBLE_ANOMALY' || classification === 'POSSIBLE_CHEATING')) return 'status-pill danger'
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

function doctorStatusClass(status?: string | null) {
  const value = String(status || '').toLowerCase()
  if (value === 'ready') return 'status-pill success'
  if (value === 'partial' || value === 'waiting' || value === 'needs_recalculate') return 'status-pill warning'
  return 'status-pill danger'
}

function doctorGapLabel(gap?: string | null) {
  const value = String(gap || '').toUpperCase()
  if (value === 'READY') return 'Dữ liệu sẵn sàng'
  if (value === 'PARTIAL_SNAPSHOT') return 'Thiếu một phần snapshot'
  if (value === 'HAS_ACTIVITY_NO_SNAPSHOT') return 'Có hoạt động, thiếu snapshot'
  if (value === 'NO_TRACKING_EVENTS') return 'Chưa thấy event học online'
  if (value === 'NO_COURSE_MAPPING') return 'Chưa ghép Course CMS'
  if (value === 'AMBIGUOUS_COURSE_MAPPING') return 'Mapping Course chưa rõ'
  if (value === 'NO_ROSTER') return 'Chưa có roster AP'
  if (value === 'CLASS_NOT_FOUND') return 'Không tìm thấy lớp'
  return value || 'Chưa kiểm tra'
}



function slaTone(report?: AnalyticsSlaReport | null) {
  const status = String(report?.sla_status || '').toUpperCase()
  if (status === 'OK') return 'success'
  if (status === 'BLOCKED') return 'danger'
  return 'warning'
}

function slaSectionTone(status?: string | null) {
  const value = String(status || '').toUpperCase()
  if (value === 'OK') return 'status-pill success'
  if (value === 'BLOCKED') return 'status-pill danger'
  return 'status-pill warning'
}

function pilotTone(report?: AnalyticsPilotAcceptanceReport | null) {
  const status = String(report?.pilot_status || '').toUpperCase()
  if (status === 'PASS') return 'success'
  if (status === 'FAIL') return 'danger'
  return 'warning'
}

function pilotLabel(report?: AnalyticsPilotAcceptanceReport | null) {
  if (!report) return 'Chưa kiểm tra pilot'
  const status = String(report.pilot_status || '').toUpperCase()
  if (status === 'PASS') return 'Đạt điều kiện pilot'
  if (status === 'PASS_WITH_WARNINGS') return 'Có thể pilot, cần theo dõi'
  if (status === 'FAIL') return 'Chưa đạt pilot'
  return report.ready_for_pilot ? 'Có thể pilot' : 'Chưa đạt pilot'
}


function evidenceTone(report?: AnalyticsEvidencePackReport | null) {
  const status = String(report?.evidence_status || '').toUpperCase()
  if (status === 'PASS') return 'success'
  if (status === 'FAIL') return 'danger'
  return 'warning'
}

function evidenceLabel(report?: AnalyticsEvidencePackReport | null) {
  if (!report) return 'Chưa xuất gói bằng chứng'
  const status = String(report.evidence_status || '').toUpperCase()
  if (status === 'PASS') return 'Gói bằng chứng đạt'
  if (status === 'PASS_WITH_WARNINGS') return 'Gói bằng chứng có cảnh báo'
  if (status === 'FAIL') return 'Gói bằng chứng chưa đạt'
  return report.evidence_status || 'Chưa kiểm tra'
}

function mappingReliabilityTone(report?: AnalyticsCourseClassMappingReport | null) {
  const status = String(report?.status || '').toUpperCase()
  if (status === 'READY') return 'success'
  if (status === 'BLOCKED') return 'danger'
  return 'warning'
}

function mappingReliabilityLabel(report?: AnalyticsCourseClassMappingReport | null) {
  if (!report) return 'Chưa kiểm tra mapping Course/Lớp'
  const status = String(report.status || '').toUpperCase()
  if (status === 'READY') return 'Mapping đủ tin cậy'
  if (status === 'READY_WITH_WARNINGS') return 'Mapping đủ rõ, còn cảnh báo'
  if (status === 'BLOCKED') return 'Mapping chưa đủ tin cậy'
  return report.summary_label || report.status || 'Chưa kiểm tra mapping'
}


function securityReadinessTone(report?: SecurityReadinessReport | null) {
  const status = String(report?.status || '').toUpperCase()
  if (status === 'READY') return 'success'
  if (status === 'BLOCKED') return 'danger'
  return 'warning'
}

function securityReadinessLabel(report?: SecurityReadinessReport | null) {
  if (!report) return 'Chưa kiểm tra security gate'
  const status = String(report.status || '').toUpperCase()
  if (status === 'READY') return 'Security gate đạt'
  if (status === 'READY_WITH_WARNINGS') return 'Security gate có cảnh báo'
  if (status === 'BLOCKED') return 'Security gate còn blocker'
  return report.summary_label || report.status || 'Chưa kiểm tra security gate'
}

function securitySectionClass(status?: string | null) {
  const value = String(status || '').toUpperCase()
  if (value === 'OK') return 'status-pill success'
  if (value === 'BLOCKED') return 'status-pill danger'
  return 'status-pill warning'
}


function releaseCandidateTone(report?: ReleaseCandidateReport | null) {
  const status = String(report?.status || '').toUpperCase()
  if (status === 'PASS') return 'success'
  if (status === 'FAIL') return 'danger'
  return 'warning'
}

function releaseCandidateLabel(report?: ReleaseCandidateReport | null) {
  if (!report) return 'Chưa kiểm tra release candidate'
  const status = String(report.status || '').toUpperCase()
  if (status === 'PASS') return 'Release candidate đạt'
  if (status === 'PASS_WITH_WARNINGS') return 'Release candidate có cảnh báo'
  if (status === 'FAIL') return 'Release candidate còn blocker'
  return report.summary_label || report.status || 'Chưa kiểm tra release candidate'
}

function releaseGateClass(status?: string | null) {
  const value = String(status || '').toUpperCase()
  if (value === 'OK') return 'status-pill success'
  if (value === 'BLOCKED') return 'status-pill danger'
  return 'status-pill warning'
}


function pilotOperationsTone(report?: PilotOperationsReport | null) {
  const status = String(report?.status || '').toUpperCase()
  if (status === 'PILOT_READY') return 'success'
  if (status === 'HOLD') return 'danger'
  return 'warning'
}

function pilotOperationsLabel(report?: PilotOperationsReport | null) {
  if (!report) return 'Chưa kiểm tra runbook pilot'
  const status = String(report.status || '').toUpperCase()
  if (status === 'PILOT_READY') return 'Sẵn sàng chạy pilot'
  if (status === 'PILOT_WITH_MONITORING') return 'Pilot có kiểm soát, cần theo dõi'
  if (status === 'HOLD') return 'Tạm dừng pilot, còn blocker'
  return report.summary_label || report.status || 'Chưa kiểm tra runbook pilot'
}

function pilotPhaseClass(status?: string | null) {
  const value = String(status || '').toUpperCase()
  if (value === 'READY') return 'status-pill success'
  if (value === 'BLOCKED') return 'status-pill danger'
  return 'status-pill warning'
}

function performanceReadinessTone(report?: PerformanceReadinessReport | null) {
  const status = String(report?.status || '').toUpperCase()
  if (status === 'READY') return 'success'
  if (status === 'BLOCKED') return 'danger'
  return 'warning'
}

function performanceReadinessLabel(report?: PerformanceReadinessReport | null) {
  if (!report) return 'Chưa kiểm tra hiệu năng'
  const status = String(report.status || '').toUpperCase()
  if (status === 'READY') return 'Hiệu năng đủ điều kiện UAT/pilot'
  if (status === 'READY_WITH_WARNINGS') return 'Có thể UAT, cần theo dõi hiệu năng'
  if (status === 'BLOCKED') return 'Cần xử lý hiệu năng trước khi mở rộng'
  return report.summary_label || report.status || 'Chưa kiểm tra hiệu năng'
}

function performanceSectionClass(status?: string | null) {
  const value = String(status || '').toUpperCase()
  if (value === 'OK') return 'status-pill success'
  if (value === 'BLOCKED') return 'status-pill danger'
  return 'status-pill warning'
}

function mappingReliabilityStatusClass(status?: string | null) {
  const value = String(status || '').toUpperCase()
  if (value === 'READY') return 'status-pill success'
  if (value.includes('AMBIGUOUS') || value.includes('NO_COURSE') || value.includes('NO_ROSTER')) return 'status-pill danger'
  return 'status-pill warning'
}

function pilotChecklistCount(report?: AnalyticsPilotAcceptanceReport | null) {
  const items = Array.isArray(report?.checklist) ? report!.checklist! : []
  const passed = items.filter((item) => item.passed).length
  return { passed, total: items.length }
}

function pilotAcceptanceStatusClass(status?: string | null) {
  const value = String(status || '').toUpperCase()
  if (value === 'PASS') return 'status-pill success'
  if (value === 'WARN' || value === 'PASS_WITH_WARNINGS') return 'status-pill warning'
  return 'status-pill danger'
}

function formatDurationSeconds(value?: number | null) {
  if (typeof value !== 'number' || Number.isNaN(value)) return 'Chưa có'
  if (value < 60) return `${value}s`
  if (value < 3600) return `${Math.round(value / 60)} phút`
  return `${Math.round((value / 3600) * 10) / 10} giờ`
}

function readinessTone(report?: AnalyticsProductionReadinessReport | null) {
  const status = String(report?.stage_status || report?.readiness || '').toUpperCase()
  if (status.includes('READY') && !status.includes('WARNING') && report?.ready_for_production) return 'success'
  if (status.includes('BLOCKED') || (!report?.ready_for_production && (report?.blocker_count || 0) > 0)) return 'danger'
  return 'warning'
}

function readinessLabel(report?: AnalyticsProductionReadinessReport | null) {
  if (!report) return 'Chưa kiểm tra'
  if (report.summary_label) return report.summary_label
  if (report.ready_for_production && (report.warning_count || 0) <= 0) return 'Sẵn sàng production'
  if (report.ready_for_production) return 'Có thể pilot, còn cảnh báo'
  return 'Chưa sẵn sàng production'
}

function readinessIssueLabel(issue: AnalyticsDataQualityIssue) {
  return issue.code || issue.message || 'UNKNOWN_CHECK'
}

function readinessSeverityLabel(severity?: string | null) {
  const value = String(severity || '').toUpperCase()
  if (value === 'BLOCKER' || value === 'ERROR') return 'Blocker'
  if (value === 'WARNING') return 'Cảnh báo'
  return 'Thông tin'
}

function campusLabel(campus: string, campuses: AcademicCampus[]) {
  if (!campus) return 'Tất cả cơ sở'
  const found = campuses.find((item) => item.campus_code === campus)
  return found ? `${found.campus_code?.toUpperCase()} · ${found.campus_name}` : campus.toUpperCase()
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

  return <AccessibleDialog
    open={Boolean(row)}
    title="Lý do ra kết quả"
    description={`${row.username} · ${row.class_id || 'Lớp N/A'}`}
    onClose={onClose}
    placement="right"
    size="large"
    className="analytics-result-drawer"
    bodyClassName="analytics-result-drawer-body"
  >

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

        {!!sessions.length && <EnterpriseDataTable<AnalyticsStudentSessionProgress>
          tableId="analytics-student-session-detail"
          caption="Tiến độ theo bài"
          rows={sessions.slice(0, 12)}
          columns={[
            { key: 'stt', header: 'STT', kind: 'index', width: 52, hideable: false, render: (_item, index) => index + 1 },
            { key: 'session', header: 'Bài', kind: 'identity', minWidth: 190, hideable: false, render: (item, index) => <b>{item.session_title || `Bài ${item.session_index || index + 1}`}</b> },
            { key: 'video', header: 'Video', kind: 'progress', width: 110, hideable: true, render: (item) => `${item.videos_completed || 0}/${item.total_videos || 0}` },
            { key: 'quiz', header: 'Quiz', kind: 'status', width: 108, hideable: true, render: (item) => item.quiz_attempted ? 'Đã làm' : 'Chưa thấy' },
            { key: 'deadline', header: 'Deadline', kind: 'status', minWidth: 130, hideable: true, render: (item) => item.completed_before_deadline ? 'Đúng hạn' : item.completed_late ? 'Trễ hạn' : 'Chưa đủ dữ liệu' },
          ]}
          rowKey={(item) => String(item.session_index)}
          density="compact"
          label="bài"
          showSummary={false}
        />}
      </>}
  </AccessibleDialog>
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

  const { authHeaders, can } = useAppContext()
  const headers = useMemo(() => authHeaders(), [authHeaders])
  const [terms, setTerms] = useState<AcademicTerm[]>([])
  const [campuses, setCampuses] = useState<AcademicCampus[]>([])
  const [subjects, setSubjects] = useState<AcademicSubjectManagement[]>([])
  const [subjectPage, setSubjectPage] = useState(1)
  const [subjectTotal, setSubjectTotal] = useState(0)
  const [subjectTotalPages, setSubjectTotalPages] = useState(0)
  const [subjectSummary, setSubjectSummary] = useState(EMPTY_SUBJECT_SUMMARY)
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
  const debouncedSubjectSearch = useDebouncedValue(subjectSearch, 400)
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
  const [productionReadiness, setProductionReadiness] = useState<AnalyticsProductionReadinessReport | null>(null)
  const [slaReport, setSlaReport] = useState<AnalyticsSlaReport | null>(null)
  const [pilotAcceptance, setPilotAcceptance] = useState<AnalyticsPilotAcceptanceReport | null>(null)
  const [evidencePack, setEvidencePack] = useState<AnalyticsEvidencePackReport | null>(null)
  const [mappingReliability, setMappingReliability] = useState<AnalyticsCourseClassMappingReport | null>(null)
  const [performanceReadiness, setPerformanceReadiness] = useState<PerformanceReadinessReport | null>(null)
  const [securityReadiness, setSecurityReadiness] = useState<SecurityReadinessReport | null>(null)
  const [releaseCandidate, setReleaseCandidate] = useState<ReleaseCandidateReport | null>(null)
  const [pilotOperations, setPilotOperations] = useState<PilotOperationsReport | null>(null)
  const [pilotLoading, setPilotLoading] = useState(false)
  const [showOperations, setShowOperations] = useState(false)
  const [classDoctor, setClassDoctor] = useState<AnalyticsClassResultDoctor | null>(null)
  const [doctorLoading, setDoctorLoading] = useState(false)
  const [recalculateLoading, setRecalculateLoading] = useState(false)

  const selectedTerm = useMemo(() => terms.find((item) => item.id === termId) || null, [terms, termId])
  const selectedSubject = useMemo(() => subjects.find((item) => item.id === subjectId) || null, [subjects, subjectId])
  const selectedClassOverview = useMemo(() => classOverview.find((item) => item.class_id === classId) || null, [classOverview, classId])
  const effectiveCourseId = selectedClassOverview?.openedx_course_id || null
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
      setClassDoctor(null)
    }
    if (nextStep === 'classes') {
      setRows([])
      setSummary(EMPTY_SUMMARY)
      setClassDoctor(null)
      setClassOverviewPage(1)
    }
    updateUrl({ step: nextStep, subjectId: nextSubjectId, classId: nextClassId })
  }

  useEffect(() => {
    if (!showOperations || !can('view_ops_readiness')) {
      setProductionReadiness(null)
      setSlaReport(null)
      setPerformanceReadiness(null)
      setSecurityReadiness(null)
      return
    }
    let cancelled = false
    getAnalyticsProductionReadiness(headers)
      .then((report) => { if (!cancelled) setProductionReadiness(report) })
      .catch(() => { if (!cancelled) setProductionReadiness(null) })
    getAnalyticsSlaReport(headers, 20)
      .then((report) => { if (!cancelled) setSlaReport(report) })
      .catch(() => { if (!cancelled) setSlaReport(null) })
    getPerformanceReadiness(headers)
      .then((report) => { if (!cancelled) setPerformanceReadiness(report) })
      .catch(() => { if (!cancelled) setPerformanceReadiness(null) })
    getSecurityReadiness(headers)
      .then((report) => { if (!cancelled) setSecurityReadiness(report) })
      .catch(() => { if (!cancelled) setSecurityReadiness(null) })
    return () => { cancelled = true }
  }, [headers, showOperations, can])

  useEffect(() => {
    if (!showOperations || !can('view_ops_readiness')) {
      setPilotAcceptance(null)
      setEvidencePack(null)
      setReleaseCandidate(null)
      setPilotOperations(null)
      setMappingReliability(null)
      setPilotLoading(false)
      return
    }
    let cancelled = false
    setPilotLoading(true)
    getAnalyticsPilotAcceptance(headers, {
      branch,
      campus,
      classId: classId || undefined,
      courseId: effectiveCourseId || undefined,
      sampleLimit: 5,
    })
      .then((report) => { if (!cancelled) setPilotAcceptance(report) })
      .catch(() => { if (!cancelled) setPilotAcceptance(null) })
    getAnalyticsEvidencePack(headers, {
      branch,
      campus,
      classId: classId || undefined,
      courseId: effectiveCourseId || undefined,
      sampleLimit: 5,
    })
      .then((report) => { if (!cancelled) setEvidencePack(report) })
      .catch(() => { if (!cancelled) setEvidencePack(null) })
      .finally(() => { if (!cancelled) setPilotLoading(false) })
    getReleaseCandidateReadiness(headers, {
      branch,
      campus,
      classId: classId || undefined,
      courseId: effectiveCourseId || undefined,
      sampleLimit: 5,
    })
      .then((report) => { if (!cancelled) setReleaseCandidate(report) })
      .catch(() => { if (!cancelled) setReleaseCandidate(null) })
    getPilotOperationsReadiness(headers, {
      branch,
      campus,
      classId: classId || undefined,
      courseId: effectiveCourseId || undefined,
      sampleLimit: 5,
    })
      .then((report) => { if (!cancelled) setPilotOperations(report) })
      .catch(() => { if (!cancelled) setPilotOperations(null) })
    getAnalyticsCourseClassMappingReport(headers, {
      branch,
      campus,
      termId: termId || undefined,
      subjectId: subjectId || undefined,
      classId: classId || undefined,
      courseId: effectiveCourseId || undefined,
      limit: 50,
    })
      .then((report) => { if (!cancelled) setMappingReliability(report) })
      .catch(() => { if (!cancelled) setMappingReliability(null) })
    return () => { cancelled = true }
  }, [headers, branch, campus, termId, subjectId, classId, effectiveCourseId, showOperations, can])

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
      .catch((error) => { if (!cancelled) setMessage(analyticsErrorMessage(error, 'Không tải được học kỳ')) })
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
      setSubjectTotal(0)
      setSubjectTotalPages(0)
      setSubjectSummary(EMPTY_SUBJECT_SUMMARY)
      setSubjectId('')
      return
    }
    let cancelled = false
    setLoadingSubjects(true)
    setMessage('')
    getAcademicTeacherSubjects(headers, { termId, branch, campus, search: debouncedSubjectSearch, learningStatus: 'all', page: subjectPage, pageSize: SUBJECT_PAGE_SIZE })
      .then((result) => {
        if (cancelled) return
        const items = result.items || []
        setSubjects(items)
        setSubjectTotal(result.total || 0)
        setSubjectTotalPages(result.total_pages || 0)
        setSubjectSummary(result.summary || EMPTY_SUBJECT_SUMMARY)
        setSubjectId((current) => items.some((item) => item.id === current) ? current : '')
      })
      .catch((error) => { if (!cancelled) setMessage(analyticsErrorMessage(error, 'Không tải được môn')) })
      .finally(() => { if (!cancelled) setLoadingSubjects(false) })
    return () => { cancelled = true }
  }, [headers, termId, campus, branch, debouncedSubjectSearch, subjectPage])

  useEffect(() => {
    setSubjectPage(1)
  }, [termId, campus, branch, debouncedSubjectSearch])

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
          setMessage(analyticsErrorMessage(error, 'Không tải được danh sách lớp theo quyền'))
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
      setClassDoctor(null)
      return
    }
    let cancelled = false
    setLoadingResults(true)
    setMessage('')
    setDoctorLoading(true)
    getAnalyticsClassWorkspace(headers, classId, {
      courseId: effectiveCourseId,
      classification,
      limit: PAGE_SIZE,
      offset: 0,
    })
      .then((workspace) => {
        if (cancelled) return
        const nextSummary = workspace.summary || EMPTY_SUMMARY
        const result = workspace.rows || { items: [], total: 0 }
        setSummary(nextSummary)
        setRows(result.items || [])
        setTotalRows(result.total || nextSummary.roster_count || result.items?.length || 0)
        setClassDoctor(workspace.doctor || nextSummary.diagnostics || result.diagnostics || null)
        if (workspace.permission_scope) setPermissionScope(workspace.permission_scope as Record<string, unknown>)
      })
      .catch((error) => {
        if (!cancelled) {
          setSummary(EMPTY_SUMMARY)
          setRows([])
          setTotalRows(0)
          setClassDoctor(null)
          setMessage(analyticsErrorMessage(error, 'Không tải được kết quả học online'))
        }
      })
      .finally(() => { if (!cancelled) { setLoadingResults(false); setDoctorLoading(false) } })
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

  useEffect(() => {
    if (step !== 'subjects') return
    updateUrl({ search: debouncedSubjectSearch })
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [debouncedSubjectSearch])

  const openReason = async (row: AnalyticsLearningBehaviorRow) => {
    setSelectedRow(row)
    setDetail(null)
    setDetailLoading(true)
    try {
      const next = await getAnalyticsStudentLearningBehaviorDetail(headers, classId, row.username, effectiveCourseId)
      setDetail(next)
    } catch (error) {
      setMessage(analyticsErrorMessage(error, 'Không tải được lý do chi tiết'))
    } finally {
      setDetailLoading(false)
    }
  }

  const refreshClassDoctor = async () => {
    if (!classId) return
    setDoctorLoading(true)
    setMessage('')
    try {
      const doctor = await getAnalyticsClassResultDoctor(headers, classId, effectiveCourseId)
      setClassDoctor(doctor)
    } catch (error) {
      setMessage(analyticsErrorMessage(error, 'Không kiểm tra được trạng thái dữ liệu lớp'))
    } finally {
      setDoctorLoading(false)
    }
  }

  const enqueueClassRecalculate = async () => {
    if (!classId) return
    const courseForJob = classDoctor?.recalculate?.course_id || classDoctor?.resolved_course_id || effectiveCourseId
    if (!courseForJob) {
      setMessage('Lớp chưa có Course CMS/Open edX rõ ràng nên chưa thể tính lại.')
      return
    }
    setRecalculateLoading(true)
    setMessage('')
    try {
      const job = await enqueueAnalyticsClassDoctorRecalculate(headers, classId, courseForJob, { force: true, limit: 500 })
      setMessage(`Đã đưa tác vụ tính lại lớp vào hàng đợi: #${job.id || 'job'}. Theo dõi ở /jobs.`)
      await refreshClassDoctor()
    } catch (error) {
      setMessage(analyticsErrorMessage(error, 'Không đưa được tác vụ tính lại vào hàng đợi'))
    } finally {
      setRecalculateLoading(false)
    }
  }

  const scopeMode = String(permissionScope?.['mode'] || '')
  const permissionText = scopeMode === 'all'
    ? 'Quyền xem: toàn hệ thống.'
    : 'Quyền xem: hệ thống đã lọc theo phân quyền cơ sở, môn hoặc lớp AP được phân công.'

  const workflowSteps = [
    { key: 'subjects', label: 'Chọn môn', description: 'Tìm môn trong phạm vi' },
    { key: 'classes', label: 'Chọn lớp', description: 'Xem lớp và mức dữ liệu', disabled: !subjectId },
    { key: 'results', label: 'Xem kết quả', description: 'Phân tích sinh viên', disabled: !classId },
  ]

  const subjectColumns = useMemo<EnterpriseTableColumn<AcademicSubjectManagement>[]>(() => [
    { key: 'stt', header: 'STT', kind: 'index', width: 52, hideable: false, render: (_item, index) => (subjectPage - 1) * SUBJECT_PAGE_SIZE + index + 1 },
    { key: 'subject', header: 'Môn', kind: 'identity', minWidth: 250, priority: 'required', hideable: false, render: (item) => <><b>{compactSubjectLabel(item)}</b><small>{item.branch?.toUpperCase() || branch.toUpperCase()}</small></> },
    { key: 'classes', header: 'Lớp', kind: 'number', width: 76, priority: 'important', hideable: true, render: (item) => item.class_count || 0 },
    { key: 'students', header: 'Sinh viên', kind: 'number', width: 88, priority: 'important', hideable: true, render: (item) => item.student_count || 0 },
    { key: 'course', header: 'Course CMS', kind: 'status', minWidth: 128, priority: 'important', hideable: true, render: (item) => <span className={item.openedx_course_id ? 'status-pill success' : 'status-pill warning'}>{item.openedx_course_id ? 'Đã ghép' : 'Chưa ghép'}</span> },
    { key: 'actions', header: 'Thao tác', kind: 'actions', width: 112, hideable: false, render: (item) => <button className="btn small primary" type="button" onClick={() => setFlowStep('classes', { subjectId: item.id, classId: '' })}>Xem lớp</button> },
  ], [branch, subjectPage])

  const classColumns = useMemo<EnterpriseTableColumn<AnalyticsClassBehaviorOverviewItem>[]>(() => [
    { key: 'stt', header: 'STT', kind: 'index', width: 52, hideable: false, render: (_item, index) => (classOverviewPage - 1) * CLASS_OVERVIEW_PAGE_SIZE + index + 1 },
    { key: 'class', header: 'Lớp', kind: 'identity', minWidth: 220, priority: 'required', hideable: false, render: (item) => <><b>{item.class_code || item.class_name || item.class_id}</b><small>{item.campus?.toUpperCase() || 'N/A'} · {classDataStatusLabel(item)}</small></> },
    { key: 'result', header: 'Kết quả lớp', kind: 'status', minWidth: 160, priority: 'important', hideable: true, render: (item) => <span className={resultClass(item.dominant_classification)}>{item.data_status === 'not_calculated' ? 'Chưa có kết quả' : resultLabel(item.dominant_classification, item.dominant_label)}</span> },
    { key: 'real', header: 'Học thật', kind: 'number', width: 82, priority: 'important', hideable: true, render: (item) => item.likely_real_learning_count || 0 },
    { key: 'review', header: 'Cần xem', kind: 'number', width: 86, priority: 'important', hideable: true, render: (item) => (item.possible_idle_count || 0) + (item.possible_suspicious_count || 0) },
    { key: 'insufficient', header: 'Thiếu dữ liệu', kind: 'number', width: 98, priority: 'optional', hideable: true, render: (item) => item.insufficient_data_count || 0 },
    { key: 'course', header: 'Course CMS', kind: 'status', minWidth: 135, priority: 'optional', defaultVisible: false, hideable: true, render: (item) => item.openedx_course_id ? <span className="status-pill success">Đã ghép</span> : <span className="status-pill warning">Chưa ghép</span> },
    { key: 'actions', header: 'Thao tác', kind: 'actions', width: 120, hideable: false, render: (item) => <button className="btn small primary" type="button" onClick={() => setFlowStep('results', { classId: item.class_id })}>Xem kết quả</button> },
  ], [classOverviewPage])

  const resultColumns = useMemo<EnterpriseTableColumn<AnalyticsLearningBehaviorRow>[]>(() => [
    { key: 'stt', header: 'STT', kind: 'index', width: 52, sticky: 'left', hideable: false, render: (_row, index) => index + 1 },
    { key: 'student', header: 'Sinh viên', kind: 'identity', minWidth: 245, sticky: 'left', priority: 'required', hideable: false, render: (row) => <><b>{row.student_code || row.username}</b><small>{row.full_name || row.username}</small></> },
    { key: 'result', header: 'Kết quả', kind: 'status', minWidth: 185, priority: 'important', hideable: false, render: (row) => <button className="analytics-result-button" type="button" onClick={() => openReason(row)} aria-label={`Xem lý do kết quả của ${row.username}`}><span className={resultClass(row.classification)}>{resultLabel(row.classification, row.display_label)}</span></button> },
    { key: 'confidence', header: 'Tin cậy', kind: 'number', width: 86, priority: 'important', hideable: true, render: (row) => percent(row.confidence_score) },
    { key: 'activity', header: 'Hoạt động cuối', kind: 'date', width: 150, priority: 'optional', hideable: true, render: (row) => row.last_activity_at ? formatVNDateTime(row.last_activity_at) : 'N/A' },
    { key: 'course', header: 'Course CMS', kind: 'text', minWidth: 175, priority: 'optional', defaultVisible: false, hideable: true, truncateLines: 1, render: (row) => row.course_id || effectiveCourseId || 'N/A' },
    { key: 'actions', header: 'Thao tác', kind: 'actions', width: 106, hideable: false, render: (row) => <button className="btn small secondary" type="button" onClick={() => openReason(row)}>Chi tiết</button> },
  ], [effectiveCourseId])

  return <PageRoot className="page-stack enterprise-standard-page analytics-learning-page analytics-learning-result-only-page analytics-three-step-flow-page">
    <EnterpriseScreenHeader
      eyebrow="Vận hành đào tạo"
      title="Phân tích học tập"
      description="Phân tích tiến độ, video, quiz và tín hiệu hành vi học theo lớp; dữ liệu chỉ hỗ trợ xác minh, không tự kết luận vi phạm."
      icon="analytics"
      tone="blue"
      breadcrumbs={[{ label: 'Vận hành đào tạo' }, { label: 'Phân tích học tập' }]}
      secondaryActions={SHOW_DIAGNOSTICS_UI && can('view_ops_readiness') ? <button className="btn secondary" type="button" aria-expanded={showOperations} onClick={() => setShowOperations((value) => !value)}>{showOperations ? 'Ẩn kiểm tra vận hành' : 'Mở kiểm tra vận hành'}</button> : undefined}
    />
    <section className="card academic-unified-card">
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

      <TrainingWorkflowSteps
        steps={workflowSteps}
        activeKey={step}
        ariaLabel="Luồng phân tích học tập"
        onChange={(key) => {
          if (key === 'subjects') setFlowStep('subjects', { subjectId: '', classId: '' })
          else if (key === 'classes') setFlowStep('classes', { classId: '' })
          else setFlowStep('results')
        }}
      />
      <TrainingContextChips items={[selectedTerm?.term_name || 'Chưa chọn kỳ', campusLabel(campus, campuses), selectedSubject?.subject_code || 'Chưa chọn môn', selectedClassOverview?.class_code || 'Chưa chọn lớp']} />

      {SHOW_DIAGNOSTICS_UI && showOperations && can('view_ops_readiness') && <>
      {productionReadiness && <div className={`analytics-production-readiness-panel ${readinessTone(productionReadiness)}`}>
        <div className="analytics-readiness-head">
          <div>
            <b>Production readiness</b>
            <span>{readinessLabel(productionReadiness)}</span>
          </div>
          <div className="analytics-readiness-counters">
            <span className={(productionReadiness.blocker_count || 0) > 0 ? 'status-pill danger' : 'status-pill success'}>{productionReadiness.blocker_count || 0} blocker</span>
            <span className={(productionReadiness.warning_count || 0) > 0 ? 'status-pill warning' : 'status-pill neutral'}>{productionReadiness.warning_count || 0} cảnh báo</span>
          </div>
        </div>
        {productionReadiness.message && <p className="analytics-readiness-message">Cần xử lý trước production theo checklist bên dưới. {productionReadiness.message}</p>}
        {productionReadiness.primary_blocker && <div className="analytics-primary-blocker">
          <b>Blocker chính:</b> {readinessIssueLabel(productionReadiness.primary_blocker)} · {productionReadiness.primary_blocker.message}
          {productionReadiness.primary_blocker.action && <span> · Cách xử lý: {productionReadiness.primary_blocker.action}</span>}
        </div>}
        {Array.isArray(productionReadiness.issues) && productionReadiness.issues.length > 0 && <div className="analytics-readiness-issue-list">
          {productionReadiness.issues.slice(0, 5).map((item, index) => <div key={`${item.code || item.message || 'issue'}-${index}`} className="analytics-readiness-issue">
            <span className={String(item.severity || '').toUpperCase() === 'BLOCKER' || String(item.severity || '').toUpperCase() === 'ERROR' ? 'status-pill danger' : 'status-pill warning'}>{readinessSeverityLabel(item.severity)}</span>
            <div><b>{item.category || readinessIssueLabel(item)}</b><small>{readinessIssueLabel(item)} · {item.message}</small>{item.action && <small>Cách xử lý: {item.action}</small>}</div>
          </div>)}
        </div>}
      </div>}

      {slaReport && <div className={`analytics-sla-panel ${slaTone(slaReport)}`}>
        <div className="analytics-sla-head">
          <div>
            <b>SLA vận hành analytics</b>
            <span>{slaReport.summary_label || 'Đang theo dõi ingest → tính lại → snapshot'}</span>
          </div>
          <div className="analytics-sla-counters">
            <span className={slaTone(slaReport) === 'success' ? 'status-pill success' : slaTone(slaReport) === 'danger' ? 'status-pill danger' : 'status-pill warning'}>{slaReport.sla_status || 'UNKNOWN'}</span>
            <span className="status-pill neutral">{slaReport.counters?.events_last_hour || 0} event/giờ</span>
            <span className="status-pill neutral">{slaReport.counters?.recalculate_active_jobs || 0} job active</span>
            <span className={(slaReport.counters?.classes_with_roster_gap || 0) > 0 ? 'status-pill warning' : 'status-pill success'}>{slaReport.counters?.classes_with_roster_gap || 0} lớp thiếu snapshot</span>
          </div>
        </div>
        <div className="analytics-sla-grid">
          <div><span>Ingest gần nhất</span><b>{formatDurationSeconds(slaReport.latency?.seconds_since_last_ingest)}</b><small>Mục tiêu {formatDurationSeconds(slaReport.targets?.ingest_target_seconds)}</small></div>
          <div><span>Snapshot gần nhất</span><b>{formatDurationSeconds(slaReport.latency?.seconds_since_latest_snapshot)}</b><small>Mục tiêu {formatDurationSeconds(slaReport.targets?.snapshot_target_seconds)}</small></div>
          <div><span>Recalculate thành công/giờ</span><b>{slaReport.counters?.recalculate_completed_last_hour || 0}</b><small>Lỗi {slaReport.counters?.recalculate_failed_last_hour || 0}</small></div>
          <div><span>Snapshot mới/giờ</span><b>{slaReport.counters?.snapshots_last_hour || 0}</b><small>Tổng {slaReport.counters?.behavior_snapshot_count || 0}</small></div>
        </div>
        {Array.isArray(slaReport.sections) && slaReport.sections.length > 0 && <div className="analytics-sla-sections">
          {slaReport.sections.slice(0, 4).map((section) => <div key={section.key} className="analytics-sla-section">
            <span className={slaSectionTone(section.status)}>{section.status}</span>
            <div><b>{section.title}</b>{typeof section.actual_seconds === 'number' && <small>Độ trễ: {formatDurationSeconds(section.actual_seconds)}</small>}</div>
          </div>)}
        </div>}
        {Array.isArray(slaReport.classes_needing_snapshot) && slaReport.classes_needing_snapshot.length > 0 && <div className="analytics-sla-gap-list">
          <b>Lớp cần ưu tiên tính lại</b>
          <div>
            {slaReport.classes_needing_snapshot.slice(0, 5).map((item) => <span key={item.class_id} className="status-pill warning">{item.class_code || item.class_id}: {item.snapshot_count}/{item.student_count}</span>)}
          </div>
        </div>}
        {Array.isArray(slaReport.issues) && slaReport.issues.length > 0 && <div className="analytics-readiness-issue-list analytics-sla-issues">
          {slaReport.issues.slice(0, 3).map((item, index) => <div key={`${item.code || item.message || 'sla'}-${index}`} className="analytics-readiness-issue">
            <span className={String(item.severity || '').toUpperCase() === 'BLOCKER' ? 'status-pill danger' : 'status-pill warning'}>{readinessSeverityLabel(item.severity)}</span>
            <div><b>{item.code || item.category || 'SLA'}</b><small>{item.message}</small>{item.action && <small>Cách xử lý: {item.action}</small>}</div>
          </div>)}
        </div>}
      </div>}

      {performanceReadiness && <div className={`analytics-performance-readiness-panel ${performanceReadinessTone(performanceReadiness)}`}>
        <div className="analytics-pilot-head">
          <div>
            <b>Hiệu năng vận hành</b>
            <span>{performanceReadinessLabel(performanceReadiness)}</span>
          </div>
          <div className="analytics-pilot-counters">
            <span className={performanceReadinessTone(performanceReadiness) === 'success' ? 'status-pill success' : performanceReadinessTone(performanceReadiness) === 'danger' ? 'status-pill danger' : 'status-pill warning'}>{performanceReadiness.status || 'UNKNOWN'}</span>
            <span className={(performanceReadiness.blocker_count || 0) > 0 ? 'status-pill danger' : 'status-pill success'}>{performanceReadiness.blocker_count || 0} blocker</span>
            <span className={(performanceReadiness.warning_count || 0) > 0 ? 'status-pill warning' : 'status-pill neutral'}>{performanceReadiness.warning_count || 0} cảnh báo</span>
          </div>
        </div>
        <div className="analytics-pilot-grid">
          <div><span>DB pool</span><b>{performanceReadiness.limits?.db_pool_size ?? 'N/A'}</b><small>Overflow {performanceReadiness.limits?.db_max_overflow ?? 'N/A'}</small></div>
          <div><span>Statement timeout</span><b>{performanceReadiness.limits?.db_statement_timeout_ms ?? 'N/A'}ms</b><small>Chống query runaway</small></div>
          <div><span>Active jobs</span><b>{performanceReadiness.queue_pressure?.active_total ?? 0}</b><small>Lỗi/giờ {performanceReadiness.queue_pressure?.failed_last_hour_total ?? 0}</small></div>
          <div><span>Page analytics</span><b>{performanceReadiness.limits?.analytics_dashboard_max_page_size ?? 'N/A'}</b><small>Giới hạn response</small></div>
          <div><span>Batch connector</span><b>{performanceReadiness.limits?.openedx_connector_max_batch_size ?? 'N/A'}</b><small>CMS/Open edX</small></div>
        </div>
        {Array.isArray(performanceReadiness.sections) && performanceReadiness.sections.length > 0 && <div className="analytics-sla-sections">
          {performanceReadiness.sections.slice(0, 5).map((section) => <div key={section.key} className="analytics-sla-section">
            <span className={performanceSectionClass(section.status)}>{section.status}</span>
            <div><b>{section.title || section.key}</b><small>{section.check_count || 0} check · {section.blocker_count || 0} blocker · {section.warning_count || 0} cảnh báo</small></div>
          </div>)}
        </div>}
        {Array.isArray(performanceReadiness.checks) && performanceReadiness.checks.length > 0 && <div className="analytics-readiness-issue-list analytics-sla-issues">
          {performanceReadiness.checks.filter((item) => item.severity === 'BLOCKER' || item.severity === 'WARNING').slice(0, 4).map((item, index) => <div key={`${item.code || item.message || 'perf'}-${index}`} className="analytics-readiness-issue">
            <span className={String(item.severity || '').toUpperCase() === 'BLOCKER' ? 'status-pill danger' : 'status-pill warning'}>{readinessSeverityLabel(item.severity)}</span>
            <div><b>{item.code || item.category || 'Performance'}</b><small>{item.message}</small>{item.action && <small>Cách xử lý: {item.action}</small>}</div>
          </div>)}
        </div>}
        {Array.isArray(performanceReadiness.next_actions) && performanceReadiness.next_actions.length > 0 && <div className="analytics-pilot-next-actions">
          <b>Việc tiếp theo cho hiệu năng</b>
          <ul>{performanceReadiness.next_actions.slice(0, 4).map((action, index) => <li key={`${action}-${index}`}>{action}</li>)}</ul>
        </div>}
        {Array.isArray(performanceReadiness.read_only_guarantees) && performanceReadiness.read_only_guarantees.length > 0 && <p className="analytics-pilot-disclaimer">Read-only: {performanceReadiness.read_only_guarantees.slice(0, 3).join(' · ')}</p>}
      </div>}


      {securityReadiness && <div className={`analytics-security-readiness-panel ${securityReadinessTone(securityReadiness)}`}>
        <div className="analytics-pilot-head">
          <div>
            <b>Security production gate</b>
            <span>{securityReadinessLabel(securityReadiness)}</span>
          </div>
          <div className="analytics-pilot-counters">
            <span className={securityReadinessTone(securityReadiness) === 'success' ? 'status-pill success' : securityReadinessTone(securityReadiness) === 'danger' ? 'status-pill danger' : 'status-pill warning'}>{securityReadiness.status || 'UNKNOWN'}</span>
            <span className={(securityReadiness.blocker_count || 0) > 0 ? 'status-pill danger' : 'status-pill success'}>{securityReadiness.blocker_count || 0} blocker</span>
            <span className={(securityReadiness.warning_count || 0) > 0 ? 'status-pill warning' : 'status-pill neutral'}>{securityReadiness.warning_count || 0} cảnh báo</span>
            <span className={securityReadiness.can_pilot ? 'status-pill success' : 'status-pill danger'}>{securityReadiness.can_pilot ? 'Có thể pilot' : 'Chưa pilot'}</span>
          </div>
        </div>
        <div className="analytics-pilot-grid">
          <div><span>Môi trường</span><b>{securityReadiness.app_env || 'N/A'}</b><small>Không trả secret</small></div>
          <div><span>Auth/Cookie</span><b>{securityReadiness.sections?.find((item) => item.key === 'auth')?.status || 'N/A'}</b><small>SSO/JWT + cookie</small></div>
          <div><span>CORS/Network</span><b>{securityReadiness.sections?.find((item) => item.key === 'network')?.status || 'N/A'}</b><small>Whitelist origin</small></div>
          <div><span>Connector</span><b>{securityReadiness.sections?.find((item) => item.key === 'integration')?.status || 'N/A'}</b><small>Open edX/AP HMAC</small></div>
          <div><span>Data safety</span><b>{securityReadiness.sections?.find((item) => item.key === 'data_safety')?.status || 'N/A'}</b><small>Cleanup/destructive guard</small></div>
        </div>
        {Array.isArray(securityReadiness.sections) && securityReadiness.sections.length > 0 && <div className="analytics-sla-sections">
          {securityReadiness.sections.slice(0, 6).map((section) => <div key={section.key} className="analytics-sla-section">
            <span className={securitySectionClass(section.status)}>{section.status}</span>
            <div><b>{section.title || section.key}</b><small>{section.check_count || 0} check · {section.blocker_count || 0} blocker · {section.warning_count || 0} cảnh báo</small></div>
          </div>)}
        </div>}
        {securityReadiness.primary_blocker && <div className="analytics-primary-blocker">
          <b>Blocker security chính:</b> {securityReadiness.primary_blocker.code || securityReadiness.primary_blocker.category} · {securityReadiness.primary_blocker.message}
          {securityReadiness.primary_blocker.action && <span> · Cách xử lý: {securityReadiness.primary_blocker.action}</span>}
        </div>}
        {Array.isArray(securityReadiness.checks) && securityReadiness.checks.length > 0 && <div className="analytics-readiness-issue-list analytics-sla-issues">
          {securityReadiness.checks.filter((item) => item.severity === 'BLOCKER' || item.severity === 'WARNING').slice(0, 5).map((item, index) => <div key={`${item.code || item.message || 'security'}-${index}`} className="analytics-readiness-issue">
            <span className={String(item.severity || '').toUpperCase() === 'BLOCKER' ? 'status-pill danger' : 'status-pill warning'}>{readinessSeverityLabel(item.severity)}</span>
            <div><b>{item.code || item.category || 'Security'}</b><small>{item.message}</small>{item.action && <small>Cách xử lý: {item.action}</small>}</div>
          </div>)}
        </div>}
        {Array.isArray(securityReadiness.next_actions) && securityReadiness.next_actions.length > 0 && <div className="analytics-pilot-next-actions">
          <b>Việc tiếp theo cho security</b>
          <ul>{securityReadiness.next_actions.slice(0, 5).map((action, index) => <li key={`${action}-${index}`}>{action}</li>)}</ul>
        </div>}
        {Array.isArray(securityReadiness.read_only_guarantees) && securityReadiness.read_only_guarantees.length > 0 && <p className="analytics-pilot-disclaimer">Read-only: {securityReadiness.read_only_guarantees.slice(0, 3).join(' · ')}</p>}
      </div>}

      {releaseCandidate && <div className={`analytics-release-candidate-panel ${releaseCandidateTone(releaseCandidate)}`}>
        <div className="analytics-pilot-head">
          <div>
            <b>Pilot Release Candidate</b>
            <span>{releaseCandidateLabel(releaseCandidate)}</span>
          </div>
          <div className="analytics-pilot-counters">
            <span className={releaseCandidateTone(releaseCandidate) === 'success' ? 'status-pill success' : releaseCandidateTone(releaseCandidate) === 'danger' ? 'status-pill danger' : 'status-pill warning'}>{releaseCandidate.status || 'UNKNOWN'}</span>
            <span className={releaseCandidate.go_no_go === 'HOLD' ? 'status-pill danger' : 'status-pill success'}>{releaseCandidate.go_no_go || 'GO/NO-GO'}</span>
            <span className={(releaseCandidate.blocker_count || 0) > 0 ? 'status-pill danger' : 'status-pill success'}>{releaseCandidate.blocker_count || 0} blocker</span>
            <span className={(releaseCandidate.warning_count || 0) > 0 ? 'status-pill warning' : 'status-pill neutral'}>{releaseCandidate.warning_count || 0} cảnh báo</span>
          </div>
        </div>
        <div className="analytics-pilot-grid">
          <div><span>Ready pilot</span><b>{releaseCandidate.ready_for_pilot ? 'Có' : 'Chưa'}</b><small>Go/no-go UAT</small></div>
          <div><span>Ready mở rộng</span><b>{releaseCandidate.ready_for_broad_production ? 'Có' : 'Chưa'}</b><small>Broad rollout</small></div>
          <div><span>RC</span><b>{releaseCandidate.release_candidate || 'v25.9.16.7.2.64.13'}</b><small>Ứng viên pilot</small></div>
          <div><span>Gate</span><b>{releaseCandidate.gates?.length || 0}</b><small>Readiness/security/performance/evidence</small></div>
          <div><span>Policy</span><b>Read-only</b><small>Không mutate dữ liệu</small></div>
        </div>
        {Array.isArray(releaseCandidate.gates) && releaseCandidate.gates.length > 0 && <div className="analytics-sla-sections">
          {releaseCandidate.gates.map((gate) => <div key={gate.key} className="analytics-sla-section">
            <span className={releaseGateClass(gate.status)}>{gate.status}</span>
            <div><b>{gate.title || gate.key}</b><small>{gate.blocker_count || 0} blocker · {gate.warning_count || 0} cảnh báo · {gate.report_endpoint}</small>{gate.message && <small>{gate.message}</small>}</div>
          </div>)}
        </div>}
        {Array.isArray(releaseCandidate.blockers) && releaseCandidate.blockers.length > 0 && <div className="analytics-readiness-issue-list analytics-sla-issues">
          {releaseCandidate.blockers.slice(0, 4).map((item, index) => <div key={`${item.source || 'rc'}-${item.code || index}`} className="analytics-readiness-issue">
            <span className="status-pill danger">Blocker</span>
            <div><b>{item.source || 'release_candidate'} · {item.code || 'BLOCKER'}</b><small>{item.message}</small>{item.action && <small>Cách xử lý: {item.action}</small>}</div>
          </div>)}
        </div>}
        {Array.isArray(releaseCandidate.next_actions) && releaseCandidate.next_actions.length > 0 && <div className="analytics-pilot-next-actions">
          <b>Việc cần làm trước pilot</b>
          <ul>{releaseCandidate.next_actions.slice(0, 5).map((action, index) => <li key={`${action}-${index}`}>{action}</li>)}</ul>
        </div>}
        {Array.isArray(releaseCandidate.read_only_guarantees) && releaseCandidate.read_only_guarantees.length > 0 && <p className="analytics-pilot-disclaimer">Read-only: {releaseCandidate.read_only_guarantees.slice(0, 3).join(' · ')}</p>}
      </div>}



      {pilotOperations && <div className={`analytics-pilot-operations-panel ${pilotOperationsTone(pilotOperations)}`}>
        <div className="analytics-pilot-head">
          <div>
            <b>Pilot operations runbook</b>
            <span>{pilotOperationsLabel(pilotOperations)}</span>
          </div>
          <div className="analytics-pilot-counters">
            <span className={pilotOperationsTone(pilotOperations) === 'success' ? 'status-pill success' : pilotOperationsTone(pilotOperations) === 'danger' ? 'status-pill danger' : 'status-pill warning'}>{pilotOperations.status || 'UNKNOWN'}</span>
            <span className={pilotOperations.decision === 'NO_GO' ? 'status-pill danger' : 'status-pill success'}>{pilotOperations.decision || 'GO/NO-GO'}</span>
            <span className={(pilotOperations.blocker_count || 0) > 0 ? 'status-pill danger' : 'status-pill success'}>{pilotOperations.blocker_count || 0} blocker</span>
            <span className={(pilotOperations.warning_count || 0) > 0 ? 'status-pill warning' : 'status-pill neutral'}>{pilotOperations.warning_count || 0} cảnh báo</span>
          </div>
        </div>
        <div className="analytics-pilot-grid">
          <div><span>Ready pilot</span><b>{pilotOperations.ready_for_pilot ? 'Có' : 'Chưa'}</b><small>Điều kiện mở pilot</small></div>
          <div><span>Ready mở rộng</span><b>{pilotOperations.ready_for_broad_production ? 'Có' : 'Chưa'}</b><small>Broad production</small></div>
          <div><span>RC status</span><b>{pilotOperations.release_candidate_summary?.status || 'N/A'}</b><small>{pilotOperations.release_candidate_summary?.go_no_go || 'GO/NO-GO'}</small></div>
          <div><span>Phase</span><b>{pilotOperations.phases?.length || 0}</b><small>Preflight → sign-off</small></div>
          <div><span>Rollback trigger</span><b>{pilotOperations.rollback_triggers?.length || 0}</b><small>Điều kiện dừng/rollback</small></div>
        </div>
        {Array.isArray(pilotOperations.phases) && pilotOperations.phases.length > 0 && <div className="analytics-sla-sections">
          {pilotOperations.phases.slice(0, 5).map((phase) => <div key={phase.key} className="analytics-sla-section">
            <span className={pilotPhaseClass(phase.status)}>{phase.status}</span>
            <div><b>{phase.title || phase.key}</b><small>{(phase.checks || []).slice(0, 2).join(' · ')}</small></div>
          </div>)}
        </div>}
        {Array.isArray(pilotOperations.rollback_triggers) && pilotOperations.rollback_triggers.length > 0 && <div className="analytics-readiness-issue-list analytics-sla-issues">
          {pilotOperations.rollback_triggers.slice(0, 4).map((item, index) => <div key={`${item.code || 'rollback'}-${index}`} className="analytics-readiness-issue">
            <span className={String(item.severity || '').toUpperCase() === 'BLOCKER' ? 'status-pill danger' : 'status-pill warning'}>{readinessSeverityLabel(item.severity)}</span>
            <div><b>{item.code || 'ROLLBACK_TRIGGER'}</b><small>{item.condition}</small>{item.action && <small>Cách xử lý: {item.action}</small>}</div>
          </div>)}
        </div>}
        {Array.isArray(pilotOperations.next_actions) && pilotOperations.next_actions.length > 0 && <div className="analytics-pilot-next-actions">
          <b>Việc tiếp theo để chạy pilot</b>
          <ul>{pilotOperations.next_actions.slice(0, 5).map((action, index) => <li key={`${action}-${index}`}>{action}</li>)}</ul>
        </div>}
        {Array.isArray(pilotOperations.read_only_guarantees) && pilotOperations.read_only_guarantees.length > 0 && <p className="analytics-pilot-disclaimer">Read-only: {pilotOperations.read_only_guarantees.slice(0, 3).join(' · ')}</p>}
      </div>}

      {(pilotAcceptance || pilotLoading) && <div className={`analytics-pilot-acceptance-panel ${pilotTone(pilotAcceptance)}`}>
        <div className="analytics-pilot-head">
          <div>
            <b>Kiểm thử pilot UAT</b>
            <span>{pilotLoading ? 'Đang kiểm tra readiness + SLA + sample lớp...' : pilotLabel(pilotAcceptance)}</span>
          </div>
          <div className="analytics-pilot-counters">
            {pilotAcceptance && <span className={pilotTone(pilotAcceptance) === 'success' ? 'status-pill success' : pilotTone(pilotAcceptance) === 'danger' ? 'status-pill danger' : 'status-pill warning'}>{pilotAcceptance.pilot_status || 'UNKNOWN'}</span>}
            {pilotAcceptance && <span className={pilotAcceptance.ready_for_pilot ? 'status-pill success' : 'status-pill danger'}>{pilotAcceptance.ready_for_pilot ? 'Có thể pilot' : 'Chưa pilot'}</span>}
            {pilotAcceptance && <span className={pilotAcceptance.ready_for_broad_production ? 'status-pill success' : 'status-pill warning'}>{pilotAcceptance.ready_for_broad_production ? 'Có thể mở rộng' : 'Chưa mở rộng'}</span>}
          </div>
        </div>
        {pilotAcceptance && <div className="analytics-pilot-grid">
          <div><span>Checklist</span><b>{pilotChecklistCount(pilotAcceptance).passed}/{pilotChecklistCount(pilotAcceptance).total || 0}</b><small>Điều kiện kỹ thuật</small></div>
          <div><span>Blocker</span><b>{pilotAcceptance.blocker_count || 0}</b><small>{(pilotAcceptance.blocker_codes || []).slice(0, 2).join(', ') || 'Không có'}</small></div>
          <div><span>Cảnh báo</span><b>{pilotAcceptance.warning_count || 0}</b><small>{(pilotAcceptance.warning_codes || []).slice(0, 2).join(', ') || 'Không có'}</small></div>
          <div><span>Lớp mẫu</span><b>{pilotAcceptance.classes?.length || 0}</b><small>Sample kiểm thử</small></div>
          <div><span>Sinh viên mẫu</span><b>{pilotAcceptance.sample_students?.length || 0}</b><small>Tín hiệu mềm</small></div>
        </div>}
        {Array.isArray(pilotAcceptance?.checklist) && pilotAcceptance!.checklist!.length > 0 && <div className="analytics-pilot-checklist">
          {pilotAcceptance!.checklist!.slice(0, 6).map((item) => <div key={item.key} className="analytics-pilot-check-item">
            <span className={item.passed ? 'status-pill success' : 'status-pill danger'}>{item.passed ? 'Đạt' : 'Chưa đạt'}</span>
            <b>{item.label}</b>
          </div>)}
        </div>}
        {Array.isArray(pilotAcceptance?.classes) && pilotAcceptance!.classes!.length > 0 && <div className="analytics-pilot-class-list">
          <b>Lớp pilot cần chú ý</b>
          <div>{pilotAcceptance!.classes!.slice(0, 5).map((item) => <span key={item.class_id} className={pilotAcceptanceStatusClass(item.acceptance_status)}>{item.class_code || item.class_id}: {item.behavior_snapshot_count}/{item.student_count}</span>)}</div>
        </div>}
        {Array.isArray(pilotAcceptance?.next_actions) && pilotAcceptance!.next_actions!.length > 0 && <div className="analytics-pilot-next-actions">
          <b>Việc tiếp theo</b>
          <ul>{pilotAcceptance!.next_actions!.slice(0, 4).map((action, index) => <li key={`${action}-${index}`}>{action}</li>)}</ul>
        </div>}
        <p className="analytics-pilot-disclaimer">Pilot chỉ xác nhận pipeline ingest/recalculate/snapshot và sample dữ liệu; không kết luận vi phạm cá nhân.</p>
      </div>}
      {evidencePack && <div className={`analytics-evidence-pack-panel ${evidenceTone(evidencePack)}`}>
        <div className="analytics-pilot-head">
          <div>
            <b>Gói bằng chứng UAT</b>
            <span>{evidenceLabel(evidencePack)}</span>
          </div>
          <div className="analytics-pilot-counters">
            <span className={evidenceTone(evidencePack) === 'success' ? 'status-pill success' : evidenceTone(evidencePack) === 'danger' ? 'status-pill danger' : 'status-pill warning'}>{evidencePack.evidence_status || 'UNKNOWN'}</span>
            <span className={(evidencePack.summary?.blocker_count || 0) > 0 ? 'status-pill danger' : 'status-pill success'}>{evidencePack.summary?.blocker_count || 0} blocker</span>
            <span className={(evidencePack.summary?.warning_count || 0) > 0 ? 'status-pill warning' : 'status-pill neutral'}>{evidencePack.summary?.warning_count || 0} cảnh báo</span>
          </div>
        </div>
        <div className="analytics-pilot-grid">
          <div><span>Ready pilot</span><b>{evidencePack.summary?.ready_for_pilot ? 'Có' : 'Chưa'}</b><small>Acceptance gate</small></div>
          <div><span>Ready mở rộng</span><b>{evidencePack.summary?.ready_for_broad_production ? 'Có' : 'Chưa'}</b><small>Broad rollout</small></div>
          <div><span>SLA</span><b>{evidencePack.summary?.sla_status || 'UNKNOWN'}</b><small>Ingest → snapshot</small></div>
          <div><span>Lớp mẫu</span><b>{evidencePack.summary?.pilot_class_count || 0}</b><small>Trong gói bằng chứng</small></div>
          <div><span>Sinh viên mẫu</span><b>{evidencePack.summary?.sample_student_count || 0}</b><small>Tín hiệu mềm</small></div>
        </div>
        {Array.isArray(evidencePack.next_actions) && evidencePack.next_actions.length > 0 && <div className="analytics-pilot-next-actions">
          <b>Action còn lại trong evidence pack</b>
          <ul>{evidencePack.next_actions.slice(0, 4).map((action, index) => <li key={`${action}-${index}`}>{action}</li>)}</ul>
        </div>}
        {Array.isArray(evidencePack.read_only_guarantees) && evidencePack.read_only_guarantees.length > 0 && <p className="analytics-pilot-disclaimer">Read-only: {evidencePack.read_only_guarantees.slice(0, 3).join(' · ')}</p>}
      </div>}
      {mappingReliability && <div className={`analytics-mapping-reliability-panel ${mappingReliabilityTone(mappingReliability)}`}>
        <div className="analytics-pilot-head">
          <div>
            <b>Độ tin cậy mapping Course/Lớp</b>
            <span>{mappingReliabilityLabel(mappingReliability)}</span>
          </div>
          <div className="analytics-pilot-counters">
            <span className={mappingReliabilityTone(mappingReliability) === 'success' ? 'status-pill success' : mappingReliabilityTone(mappingReliability) === 'danger' ? 'status-pill danger' : 'status-pill warning'}>{mappingReliability.status || 'UNKNOWN'}</span>
            <span className={(mappingReliability.blocker_count || 0) > 0 ? 'status-pill danger' : 'status-pill success'}>{mappingReliability.blocker_count || 0} blocker</span>
            <span className={(mappingReliability.warning_count || 0) > 0 ? 'status-pill warning' : 'status-pill neutral'}>{mappingReliability.warning_count || 0} cảnh báo</span>
          </div>
        </div>
        <div className="analytics-pilot-grid">
          <div><span>Lớp trong scope</span><b>{mappingReliability.total_scope_classes || 0}</b><small>Trả về {mappingReliability.returned_classes || 0}</small></div>
          <div><span>Course resolved</span><b>{mappingReliability.resolved_course_count || 0}</b><small>Mapping rõ</small></div>
          <div><span>Course có event chưa map</span><b>{mappingReliability.courses_with_events_without_class_mapping_count || 0}</b><small>Cần xử lý trước pilot rộng</small></div>
          <div><span>Thiếu mapping</span><b>{mappingReliability.counts?.NO_COURSE_MAPPING || 0}</b><small>Ghép Course CMS</small></div>
          <div><span>Ambiguous</span><b>{mappingReliability.counts?.AMBIGUOUS_MAPPING || 0}</b><small>Cần class override</small></div>
        </div>
        {Array.isArray(mappingReliability.items) && mappingReliability.items.length > 0 && <div className="analytics-pilot-class-list">
          <b>Lớp cần chú ý mapping</b>
          <div>{mappingReliability.items.filter((item) => item.reliability_status !== 'READY').slice(0, 5).map((item) => <span key={item.class_id} className={mappingReliabilityStatusClass(item.reliability_status)}>{item.class_code || item.class_id}: {item.reliability_status}</span>)}</div>
        </div>}
        {Array.isArray(mappingReliability.courses_with_events_without_class_mapping) && mappingReliability.courses_with_events_without_class_mapping.length > 0 && <div className="analytics-pilot-class-list">
          <b>Course có event nhưng chưa resolve class</b>
          <div>{mappingReliability.courses_with_events_without_class_mapping.slice(0, 5).map((item) => <span key={item.course_id} className="status-pill danger">{item.course_id}: {item.event_count} event</span>)}</div>
        </div>}
        {Array.isArray(mappingReliability.next_actions) && mappingReliability.next_actions.length > 0 && <div className="analytics-pilot-next-actions">
          <b>Việc tiếp theo cho mapping</b>
          <ul>{mappingReliability.next_actions.slice(0, 4).map((action, index) => <li key={`${action}-${index}`}>{action}</li>)}</ul>
        </div>}
        {Array.isArray(mappingReliability.read_only_guarantees) && mappingReliability.read_only_guarantees.length > 0 && <p className="analytics-pilot-disclaimer">Read-only: {mappingReliability.read_only_guarantees.slice(0, 3).join(' · ')}</p>}
      </div>}
      </>}
      <div className="alert info compact-alert">{permissionText}</div>
      {message && <div className="academic-inline-error"><b>Cần kiểm tra</b><span>{message}</span></div>}
    </section>

    {step === 'subjects' && <section className="card academic-unified-card analytics-subject-picker-card analytics-workspace-section">
      <div className="analytics-results-head">
        <div>
          <h3>Chọn môn</h3>
          <p>Chỉ hiển thị môn nằm trong phạm vi cơ sở, bộ môn hoặc lớp AP được phân công.</p>
        </div>
        <span className="status-pill neutral">{subjectTotal.toLocaleString('vi-VN')} môn</span>
      </div>
      <div className="training-compact-filter">
        <label className="is-wide">Tìm môn
          <input className="input" value={subjectSearch} onChange={(event) => { setSubjectSearch(event.target.value); setSubjectPage(1); setStep('subjects') }} placeholder="COM1071, Tin học..." />
        </label>
      </div>
      <TrainingKpiStrip compact items={[
        { key: 'subjects', label: 'Môn', value: subjectSummary.subject_count },
        { key: 'classes', label: 'Lớp', value: subjectSummary.class_count },
        { key: 'students', label: 'Sinh viên', value: subjectSummary.student_count },
        { key: 'course', label: 'Course CMS', value: `${subjectSummary.course_mapped_count}/${subjectSummary.subject_count}`, tone: subjectSummary.course_mapped_count < subjectSummary.subject_count ? 'warning' : 'success' },
        { key: 'enrolled', label: 'Ghi danh', value: subjectSummary.learning_enrolled_count },
      ]} />
      <EnterpriseDataTable
        tableId="analytics-subjects"
        caption="Danh sách môn"
        rows={subjects}
        columns={subjectColumns}
        rowKey={(item) => item.id}
        density="compact"
        loading={loadingSubjects}
        emptyTitle="Không có môn trong phạm vi hiện tại"
        emptyDescription="Đổi học kỳ, cơ sở hoặc từ khóa tìm kiếm."
        label="môn"
      />
      {subjectTotal > SUBJECT_PAGE_SIZE && <div className="pagination-row">
        <button className="btn secondary" type="button" disabled={subjectPage <= 1 || loadingSubjects} onClick={() => setSubjectPage((value) => Math.max(1, value - 1))}>Trang trước</button>
        <span>Trang {subjectPage}/{Math.max(1, subjectTotalPages || Math.ceil(subjectTotal / SUBJECT_PAGE_SIZE))}</span>
        <button className="btn secondary" type="button" disabled={subjectPage >= Math.max(1, subjectTotalPages || Math.ceil(subjectTotal / SUBJECT_PAGE_SIZE)) || loadingSubjects} onClick={() => setSubjectPage((value) => value + 1)}>Trang sau</button>
      </div>}
    </section>}

    {step === 'classes' && <section className="card academic-unified-card analytics-class-overview-card analytics-workspace-section">
      <div className="analytics-results-head">
        <div>
          <h3>Lớp của môn {selectedSubject?.subject_code || ''}</h3>
          <p>{selectedSubject ? compactSubjectLabel(selectedSubject) : 'Chọn môn để xem lớp.'}</p>
        </div>
        <button className="btn secondary small" type="button" onClick={() => setFlowStep('subjects', { subjectId: '', classId: '' })}>Quay lại môn</button>
      </div>
      <TrainingKpiStrip compact items={[
        { key: 'classes', label: 'Lớp', value: classOverviewSummary.total_classes || 0 },
        { key: 'students', label: 'Sinh viên', value: classOverviewSummary.total_students || 0 },
        { key: 'real', label: 'Có dấu hiệu học thật', value: classOverviewSummary.likely_real_learning_count || 0, tone: 'success' },
        { key: 'review', label: 'Cần giáo viên xem', value: (classOverviewSummary.possible_idle_count || 0) + (classOverviewSummary.possible_suspicious_count || 0), tone: 'warning' },
        { key: 'insufficient', label: 'Chưa đủ dữ liệu', value: classOverviewSummary.insufficient_data_count || 0 },
      ]} />
      <EnterpriseDataTable
        tableId="analytics-classes"
        caption="Danh sách lớp"
        rows={classOverview}
        columns={classColumns}
        rowKey={(item) => item.class_id}
        density="compact"
        loading={loadingClassOverview}
        emptyTitle={subjectId ? 'Không có lớp phù hợp' : 'Chưa chọn môn'}
        emptyDescription={subjectId ? 'Không có lớp trong phân quyền hoặc bộ lọc kết quả hiện tại.' : 'Chọn môn ở bước đầu tiên.'}
        label="lớp"
      />
      {classOverviewTotal > CLASS_OVERVIEW_PAGE_SIZE && <div className="pagination-row">
        <button className="btn secondary" type="button" disabled={classOverviewPage <= 1 || loadingClassOverview} onClick={() => setClassOverviewPage((value) => Math.max(1, value - 1))}>Trang trước</button>
        <span>Trang {classOverviewPage}/{Math.max(1, Math.ceil(classOverviewTotal / CLASS_OVERVIEW_PAGE_SIZE))}</span>
        <button className="btn secondary" type="button" disabled={classOverviewPage >= Math.ceil(classOverviewTotal / CLASS_OVERVIEW_PAGE_SIZE) || loadingClassOverview} onClick={() => setClassOverviewPage((value) => value + 1)}>Trang sau</button>
      </div>}
    </section>}

    {step === 'results' && <section className="card academic-unified-card analytics-workspace-section">
      <div className="analytics-results-head">
        <div>
          <h3>Kết quả lớp {selectedClassOverview?.class_code || ''}</h3>
          <p>{selectedClassOverview ? `${selectedSubject?.subject_code || ''} · ${selectedClassOverview.campus?.toUpperCase() || campusLabel(campus, campuses)} · ${selectedClassOverview.snapshot_count}/${selectedClassOverview.student_count} sinh viên có snapshot` : 'Đang tải lớp đã chọn.'}</p>
        </div>
        <div className="teacher-compact-actions">
          <button className="btn secondary small" type="button" onClick={() => setFlowStep('classes', { classId: '' })}>Quay lại lớp</button>
          <button className="btn secondary small" type="button" onClick={() => setFlowStep('subjects', { subjectId: '', classId: '' })}>Chọn môn khác</button>
        </div>
      </div>

      {!effectiveCourseId && classId ? <TrainingMappingEmptyState
        description="Lớp chưa ghép Course CMS nên hệ thống chỉ có thể hiển thị roster và trạng thái Chưa đủ dữ liệu. Hoàn tất mapping để nhận kết quả học online."
        action={<a className="btn secondary small" href={`/student-management/classes/${encodeURIComponent(classId)}`}>Mở chi tiết lớp</a>}
      /> : null}

      {SHOW_DIAGNOSTICS_UI && <div className="analytics-class-doctor-panel">
        <div className="section-head list-card-head compact-head">
          <div>
            <h4>Trạng thái dữ liệu lớp</h4>
            <p>{doctorLoading ? 'Đang kiểm tra roster, mapping, event và snapshot...' : (classDoctor?.message || 'Kiểm tra nhanh để biết vì sao lớp có thể đang thiếu snapshot.')}</p>
          </div>
          <div className="teacher-compact-actions">
            {classDoctor && <span className={doctorStatusClass(classDoctor.status)}>{doctorGapLabel(classDoctor.data_gap)}</span>}
            <button className="btn secondary small" type="button" onClick={refreshClassDoctor} disabled={doctorLoading}>Kiểm tra dữ liệu lớp</button>
            <button className="btn primary small" type="button" onClick={enqueueClassRecalculate} disabled={recalculateLoading || doctorLoading || !classDoctor?.recalculate?.can_enqueue}>{recalculateLoading ? 'Đang đưa job...' : 'Tính lại lớp này'}</button>
          </div>
        </div>
      </div>}

      <TrainingKpiStrip compact items={[
        { key: 'students', label: 'Sinh viên', value: summary.roster_count ?? summary.total_students ?? 0 },
        { key: 'snapshots', label: 'Có snapshot', value: summary.snapshot_count ?? rows.length },
        { key: 'missing', label: 'Thiếu snapshot', value: summary.missing_snapshot_count ?? Math.max(0, (summary.roster_count ?? summary.total_students ?? 0) - (summary.snapshot_count ?? rows.length)), tone: (summary.missing_snapshot_count || 0) > 0 ? 'warning' : 'success' },
        { key: 'real', label: 'Có dấu hiệu học thật', value: summary.likely_real_learning_count || 0, tone: 'success' },
        { key: 'review', label: 'Cần giáo viên xem', value: (summary.possible_idle_count || 0) + (summary.possible_suspicious_count || 0), tone: 'warning' },
        { key: 'insufficient', label: 'Chưa đủ dữ liệu', value: summary.insufficient_data_count || 0 },
      ]} />

      <EnterpriseDataTable
        tableId="analytics-results"
        caption="Kết quả sinh viên"
        rows={rows}
        columns={resultColumns}
        rowKey={(row) => `${row.class_id}-${row.course_id}-${row.username}`}
        density="compact"
        loading={loadingResults}
        emptyTitle={classId ? 'Chưa có kết quả cho lớp này' : 'Chưa chọn lớp'}
        emptyDescription={classId ? 'Roster vẫn được giữ; các sinh viên chưa có snapshot sẽ hiển thị Chưa đủ dữ liệu khi backend trả kết quả.' : 'Chọn một lớp ở bước trước.'}
        label="sinh viên"
      />
    </section>}

    <DetailDrawer row={selectedRow} detail={detail} loading={detailLoading} onClose={() => { setSelectedRow(null); setDetail(null) }} />
  </PageRoot>
}
