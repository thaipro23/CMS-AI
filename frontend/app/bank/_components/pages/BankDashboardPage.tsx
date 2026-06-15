'use client'

import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { useEffect, useMemo, useRef, useState } from 'react'
import { useAppContext } from '../../../../context/AppContext'
import {
  BankRelease,
  BankDashboardOverview,
  BankSearchResult,
  DepartmentSummary,
  SubjectSummary,
  SubjectVersionSummary,
  ChapterSummary,
  BankGeneratePreview,
  BankReleaseReadiness,
  BankVersion,
  BankVersionDiffPreview,
  BankVersionQuestion,
  CourseQuizInstance,
  AuditLogRow,
  Job,
  Department,
  MaterialChunk,
  MaterialVersion,
  Subject,
  SubjectChapter,
  SubjectOffering,
} from '../../../../types'
import {
  bulkReviewBankQuestions,
  createBankRelease,
  createBankVersion,
  createDepartment,
  createSubject,
  createSubjectChapter,
  createSubjectOffering,
  deleteDepartment,
  deleteSubject,
  deleteSubjectChapter,
  deleteSubjectOffering,
  deleteMaterialVersion,
  generateFromBankVersion,
  getBankDashboardOverview,
  getAuditLogs,
  getJobs,
  searchBankDashboard,
  getDepartmentSummaries,
  getSubjectSummaries,
  getSubjectVersionSummaries,
  getChapterSummaries,
  getBankMaterialChunks,
  getBankReleaseReadiness,
  getBankReleases,
  getBankVersionQuestion,
  getBankVersionQuestionPage,
  getBankVersions,
  getCourseQuizInstances,
  getDepartments,
  getMaterialVersions,
  getSubjectChapters,
  getSubjectOfferings,
  getSubjects,
  markBankDiffResolved,
  previewBankVersionDiff,
  previewGenerateFromBankVersion,
  publishBankRelease,
  reviewBankQuestion,
  rollbackCourseQuizInstance,
  uploadBankMaterial,
  updateBankQuestion,
  updateDepartment,
  updateSubject,
  updateSubjectChapter,
  updateSubjectOffering,
} from '../../../../lib/api'
import {
  TERMS,
  chapterDisplayName,
  normalizeLessonInput,
  buildChapterTitle,
  statusLabel,
  statusClass,
  useBankData,
  useAsyncMessage,
  Breadcrumb,
  Toolbar,
  SearchActionBar,
  Modal,
  EntityActions,
  promptText,
  matchesSearch,
  reviewStatusText,
  reviewStatusClass,
  StatLine,
  QuickSearchBox,
  questionStats,
  nextReleaseText,
  bankAnswerRows,
  bankQuestionErrorMessage,
  isQuestionWaitingForReview,
  BankQuestionEditForm,
  BankChartRow,
  toBankQuestionEditForm,
  BankBarChart,
  BankStackedChart,
  countRows,
  auditActionText,
} from '../shared'

export function BankDashboardPage() {
  const { headers, authReady } = useBankData()
  const [overview, setOverview] = useState<BankDashboardOverview | null>(null)
  const [quizInstances, setQuizInstances] = useState<CourseQuizInstance[]>([])
  const [auditRows, setAuditRows] = useState<AuditLogRow[]>([])
  const [jobs, setJobs] = useState<Job[]>([])
  const overviewLoadKey = useRef('')

  const load = async () => {
    const [nextOverview, nextQuizInstances, nextAudit, nextJobs] = await Promise.all([
      getBankDashboardOverview(headers),
      getCourseQuizInstances(headers, { limit: 50 }),
      getAuditLogs('', { page: 1, pageSize: 10 }, headers),
      getJobs('', headers),
    ])
    setOverview(nextOverview)
    setQuizInstances(nextQuizInstances)
    setAuditRows(nextAudit.items || [])
    setJobs(nextJobs)
  }

  useEffect(() => {
    if (!authReady) return
    const key = JSON.stringify(headers)
    if (overviewLoadKey.current === key) return
    overviewLoadKey.current = key
    let cancelled = false
    load().catch(() => { if (!cancelled) overviewLoadKey.current = '' })
    return () => { cancelled = true }
  }, [authReady, headers]) // eslint-disable-line react-hooks/exhaustive-deps

  const totalQuestions = overview?.total_questions || 0
  const approvedQuestions = overview?.approved_count || 0
  const pendingQuestions = overview?.pending_review_count || 0
  const errorQuestions = overview?.draft_error_count || 0
  const readyChapters = overview?.chapters_ready_to_release || 0
  const reviewProgress = totalQuestions > 0 ? Math.round((approvedQuestions / totalQuestions) * 100) : 0
  const failedQuizCount = quizInstances.filter((item) => item.status === 'failed').length
  const createdQuizCount = quizInstances.filter((item) => item.status === 'created').length
  const failedJobCount = jobs.filter((item) => item.status === 'failed').length
  const activeJobCount = jobs.filter((item) => ['queued', 'running', 'processing'].includes(item.status)).length
  const needsAttention = pendingQuestions + errorQuestions + readyChapters + failedQuizCount + failedJobCount

  const questionRows: BankChartRow[] = [
    { label: 'Đã duyệt', value: approvedQuestions, tone: 'green' },
    { label: 'Chờ duyệt', value: pendingQuestions, tone: 'amber' },
    { label: 'Câu lỗi', value: errorQuestions, tone: 'red' },
  ]
  const hierarchyRows: BankChartRow[] = [
    { label: 'Bộ môn', value: overview?.departments_total || 0, tone: 'blue' },
    { label: 'Môn', value: overview?.subjects_total || 0, tone: 'green' },
    { label: 'Version', value: overview?.subject_versions_total || 0, tone: 'amber' },
    { label: 'Bài', value: overview?.chapters_total || 0, tone: 'slate' },
  ]
  const quizRows = countRows(quizInstances, (row) => row.status, { created: 'green', failed: 'red', rolled_back: 'amber' })
  const jobRows = countRows(jobs, (row) => row.status, { completed: 'green', failed: 'red', running: 'blue', queued: 'amber' })
  const recentQuizzes = quizInstances.slice(0, 6)
  const recentJobs = jobs.slice(0, 6)
  const nextActions = overview?.next_actions || []

  return <div className="page-stack bank-multipage bank-dashboard-modern">
    <Breadcrumb items={[{ label: 'Ngân hàng đề' }]} />

    <section className="bank-command-center card">
      <div className="bank-command-copy">
        <span className="eyebrow">Trung tâm vận hành ngân hàng đề</span>
        <h1>Dashboard Bank</h1>
        <p>Nhìn nhanh việc cần làm, chất lượng câu hỏi, Quiz Open edX, job và hoạt động gần đây. Trang này thay cho dashboard course-first cũ.</p>
        <div className="button-row no-margin">
          <button className="btn secondary" type="button" onClick={load}>Tải lại</button>
          <Link className="btn secondary" href="/bank/departments">Quản lý bộ môn</Link>
          <Link className="btn" href="/bank/quiz">Tạo Quiz Open edX</Link>
        </div>
      </div>
      <div className="bank-command-score">
        <span>Tiến độ duyệt câu hỏi</span>
        <b>{reviewProgress}%</b>
        <small>{approvedQuestions}/{totalQuestions} câu đã duyệt</small>
        <div className="bank-progress"><i style={{ width: `${Math.min(100, reviewProgress)}%` }} /></div>
      </div>
    </section>

    <section className="bank-kpi-grid">
      <div className={needsAttention > 0 ? 'bank-kpi-card danger' : 'bank-kpi-card success'}><span>Cần xử lý</span><b>{needsAttention}</b><small>{pendingQuestions} chờ duyệt · {errorQuestions} lỗi · {readyChapters} bài sẵn sàng</small></div>
      <div className="bank-kpi-card"><span>Tổng câu hỏi</span><b>{totalQuestions}</b><small>{approvedQuestions} đã duyệt · {pendingQuestions} chờ duyệt</small></div>
      <div className="bank-kpi-card"><span>Quiz Open edX</span><b>{quizInstances.length}</b><small>{createdQuizCount} đã tạo · {failedQuizCount} lỗi</small></div>
      <div className="bank-kpi-card"><span>Job</span><b>{jobs.length}</b><small>{activeJobCount} đang chạy · {failedJobCount} lỗi</small></div>
    </section>

    <section className="card bank-search-card">
      <div className="section-head"><div><h2>Tìm nhanh</h2><p className="helper">Gõ mã môn, version, bài hoặc keyword câu hỏi để đi thẳng tới nơi cần xử lý.</p></div></div>
      <QuickSearchBox />
    </section>

    <section className="bank-dashboard-layout">
      <div className="bank-dashboard-main">
        <section className="card bank-focus-card">
          <div className="section-head"><div><h2>Việc cần làm ngay</h2><p className="helper">Ưu tiên xử lý câu lỗi, câu chờ duyệt và bài đã đủ điều kiện chốt release.</p></div></div>
          <div className="dashboard-task-list modern-task-list">
            {nextActions.slice(0, 6).map((item) => <Link href={item.href} className={`task-row ${item.type === 'fix_errors' ? 'danger' : item.type === 'review_questions' ? 'warning' : 'success'}`} key={`${item.type}-${item.href}`}>
              <span>{item.type === 'create_release' ? '✅' : item.type === 'fix_errors' ? '⚠️' : '📝'}</span>
              <div><b>{item.title}</b><small>{item.message}</small></div>
              <em>{item.type === 'create_release' ? 'Chốt' : item.type === 'fix_errors' ? 'Sửa lỗi' : 'Duyệt'}</em>
            </Link>)}
            {overview && !nextActions.length ? <div className="empty-state">Chưa có việc gấp. Có thể tạo thêm câu hỏi hoặc tạo Quiz Open edX.</div> : null}
            {!overview ? <div className="empty-state">Đang tải tổng quan...</div> : null}
          </div>
        </section>

        <section className="bank-chart-grid strong-chart-grid">
          <BankStackedChart title="Tình trạng câu hỏi" helper="Chất lượng bank theo trạng thái review." rows={questionRows} />
          <BankBarChart title="Quy mô ngân hàng" helper="Bộ môn, môn, version và bài trong hệ thống." rows={hierarchyRows} />
          <BankBarChart title="Quiz Open edX" helper="Theo dõi trạng thái các Quiz đã tạo." rows={quizRows} empty="Chưa có Quiz Open edX." />
          <BankBarChart title="Job generate" helper="Generate/publish/quiz jobs gần đây." rows={jobRows} empty="Chưa có job." />
        </section>
      </div>

      <aside className="bank-dashboard-side">
        <section className="card mini-feed-card">
          <div className="section-head compact-section-head"><div><h2>Quiz gần đây</h2><p className="helper">Theo dõi tạo Quiz và lỗi tạo Quiz.</p></div><Link href="/bank/history" className="btn secondary small">Xem tất cả</Link></div>
          <div className="mini-feed-list">
            {recentQuizzes.length ? recentQuizzes.map((row) => <div className="mini-feed-row" key={row.id}>
              <div><b>{row.openedx_course_id}</b><small>{row.id.slice(0, 8)} · {row.created_at ? new Date(row.created_at).toLocaleString('vi-VN') : '—'}</small></div>
              <span className={row.status === 'failed' ? 'status danger' : row.status === 'created' ? 'status success' : 'status warning'}>{statusLabel(row.status)}</span>
            </div>) : <div className="empty-state small-empty">Chưa có Quiz.</div>}
          </div>
        </section>

        <section className="card mini-feed-card">
          <div className="section-head compact-section-head"><div><h2>Job gần đây</h2><p className="helper">Generate, publish và tạo quiz.</p></div><Link href="/jobs" className="btn secondary small">Mở job</Link></div>
          <div className="mini-feed-list">
            {recentJobs.length ? recentJobs.map((row) => <div className="mini-feed-row" key={row.id}>
              <div><b>{row.course_id || 'Bank job'}</b><small>{row.question_count || 0} câu · {row.error_message || 'Không có lỗi'}</small></div>
              <span className={row.status === 'failed' ? 'status danger' : row.status === 'completed' ? 'status success' : 'status warning'}>{statusLabel(row.status)}</span>
            </div>) : <div className="empty-state small-empty">Chưa có job.</div>}
          </div>
        </section>
      </aside>
    </section>

    <section className="card">
      <div className="section-head"><div><h2>Nhật ký gần đây</h2><p className="helper">Ai làm gì, lỗi gì, thao tác nào vừa xảy ra trong luồng Bank/Quiz.</p></div><Link className="btn secondary" href="/audit">Xem nhật ký</Link></div>
      <div className="table-wrap"><table className="table"><thead><tr><th>Thời điểm</th><th>Người</th><th>Hành động</th><th>Kết quả</th><th>Nội dung</th></tr></thead><tbody>{auditRows.length ? auditRows.map((row) => <tr key={row.id}><td>{row.created_at ? new Date(row.created_at).toLocaleString('vi-VN') : '—'}</td><td><b>{row.actor_id}</b><br /><span className="helper">{row.actor_role || '—'}</span></td><td>{auditActionText(row.action)}</td><td><span className={row.status === 'failed' ? 'status danger' : 'status success'}>{row.status}</span></td><td>{row.message || '—'}</td></tr>) : <tr><td colSpan={5}><div className="empty-state">Chưa có hoạt động.</div></td></tr>}</tbody></table></div>
    </section>
  </div>
}

