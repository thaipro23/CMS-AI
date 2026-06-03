'use client'

import { useEffect, useState } from 'react'
import { useAppContext } from '../../context/AppContext'
import { ActionMessage, ActionMessageData, toUserError } from '../../components/ui/ActionMessage'
import { getAnalytics } from '../../lib/api'
import { AnalyticsOverview } from '../../types'
import { MetricCard } from '../../components/ui/MetricCard'
import { StatPanel } from '../../components/ui/StatPanel'

export default function DashboardPage() {
  const { courseId, authHeaders, can } = useAppContext()
  const [overview, setOverview] = useState<AnalyticsOverview | null>(null)
  const [message, setMessage] = useState<ActionMessageData | null>(null)

  async function load() {
    try {
      setMessage(null)
      setOverview(await getAnalytics(courseId, authHeaders()))
    } catch (error) {
      setMessage(toUserError(error))
    }
  }

  useEffect(() => { load() }, [courseId])

  if (!can('view_dashboard')) return <div className="card empty-state">Role hiện tại không có quyền xem dashboard.</div>

  return <div className="page-stack">
    <section className="card page-intro">
      <div><h2>Dashboard thống kê & quản trị</h2><p className="helper">Tổng hợp ngân hàng câu hỏi, review, job, chi phí, đồng bộ và quota theo khóa học hiện tại.</p></div>
      <button className="btn secondary" onClick={load}>Tải lại dashboard</button>
    </section>
    <ActionMessage message={message} onClose={() => setMessage(null)} />
    {overview ? <>
      <section className="dashboard-grid">
        <MetricCard title="Tổng số câu hỏi" value={overview.questions.total} hint={`Điểm chất lượng TB: ${overview.questions.quality_average}`} />
        <MetricCard title="Tỷ lệ duyệt" value={`${overview.questions.approve_rate_percent}%`} hint="Đã duyệt + đã publish / đã review" />
        <MetricCard title="Job tạo câu hỏi" value={overview.jobs.total} hint={`Lỗi: ${overview.jobs.failed_jobs} · Thử lại: ${overview.jobs.retry_total}`} />
        <MetricCard title="Chi phí đã dùng" value={`${overview.cost.total_usage_cost_vnd.toLocaleString('vi-VN')} VND`} hint={`${overview.cost.budget_used_percent}% của $${overview.cost.monthly_budget_usd}`} />
        <MetricCard title="Độ chính xác chi phí" value={`${overview.jobs.estimate_accuracy_percent}%`} hint={`Delta $${overview.jobs.cost_delta_usd}`} />
        <MetricCard title="Độ chính xác output" value={`${overview.jobs.output_accuracy_percent || 0}%`} hint={`Est ${Number(overview.jobs.estimated_output_tokens_per_question || 0).toLocaleString('vi-VN')} / Actual ${Number(overview.jobs.actual_output_tokens_per_question || 0).toLocaleString('vi-VN')} tokens/câu`} />
        <MetricCard title="Token thực tế" value={overview.jobs.actual_input_tokens.toLocaleString('vi-VN')} hint={`Đã cache ${overview.jobs.actual_cached_input_tokens.toLocaleString('vi-VN')} · Output ${overview.jobs.actual_output_tokens.toLocaleString('vi-VN')}`} />
        <MetricCard title="Chunk học liệu" value={overview.course_sync.chunks} hint={`${overview.course_sync.tokens_indexed.toLocaleString('vi-VN')} token đã index`} />
        <MetricCard title="Quota đã dùng" value={`${overview.governance.quota_used_percent}%`} hint={`Tối đa ${overview.governance.quota_max_questions_per_course} câu/course`} />
      </section>
      <section className="grid grid-3">
        <StatPanel title="Câu hỏi theo trạng thái" rows={overview.questions.by_status} />
        <StatPanel title="Câu hỏi theo độ khó" rows={overview.questions.by_difficulty} />
        <StatPanel title="Job theo trạng thái" rows={overview.jobs.by_status} />
        <StatPanel title="Node/phạm vi nhiều câu nhất" rows={overview.questions.top_scopes.map((row) => ({ label: row.scope, value: row.count }))} />
        <StatPanel title="Chi phí theo tính năng" rows={overview.cost.by_feature} empty="Chưa có usage log." />
        <StatPanel title="Chi phí theo model" rows={overview.cost.by_model} empty="Chưa có usage log." />
        <StatPanel title="Học liệu sync theo nguồn" rows={overview.course_sync.by_source_type} empty="Chưa sync chunk." />
      </section>
    </> : <div className="empty-state">Chưa tải được dashboard.</div>}
  </div>
}
