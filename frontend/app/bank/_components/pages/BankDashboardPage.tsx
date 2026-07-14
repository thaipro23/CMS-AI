'use client'

import { daysAgoVNISODate, formatVNDateTime, todayVNISODate } from '../../../../lib/time'
import Link from 'next/link'
import { useRouter, useSearchParams } from 'next/navigation'
import { useEffect, useMemo, useState } from 'react'
import { useBankData, Breadcrumb, QuickSearchBox, Modal } from '../shared'
import { getBankDashboardAnalytics } from '../../../../lib/api'
import { PageHeader } from '../../../../components/layout/PageHeader'
import type { DashboardAnalytics, DashboardChart, DashboardChartItem, DashboardDrilldown, DashboardKpi } from '../../../../types'

const STATUS_COLORS: Record<string, string> = {
  draft: '#64748b',
  pending_review: '#f59e0b',
  approved: '#10b981',
  rejected: '#ef4444',
  draft_error: '#dc2626',
  easy: '#22c55e',
  medium: '#f59e0b',
  hard: '#ef4444',
  single_choice: '#2563eb',
  multiple_choice: '#0891b2',
  essay: '#7c3aed',
  short_answer: '#0f766e',
  unknown: '#64748b',
}

function formatNumber(value?: number | null) {
  return new Intl.NumberFormat('vi-VN').format(Number(value || 0))
}

function todayIso() {
  return todayVNISODate()
}

function buildDateRange(days: number) {
  return { fromDate: daysAgoVNISODate(Math.max(0, days - 1)), toDate: todayVNISODate() }
}

function drilldownUrl(drilldown?: DashboardDrilldown | null) {
  if (!drilldown?.route) return '/bank'
  const params = new URLSearchParams()
  Object.entries(drilldown.query || {}).forEach(([key, value]) => {
    if (value === null || value === undefined || value === '') return
    params.set(key, String(value))
  })
  const qs = params.toString()
  return qs ? `${drilldown.route}?${qs}` : drilldown.route
}

function SkeletonBlock({ height = 120 }: { height?: number }) {
  return <div className="dashboard-skeleton" style={{ minHeight: height }} />
}

function DashboardEmptyState({ role }: { role?: string }) {
  return <div className="dashboard-empty-state">
    <b>Chưa có dữ liệu trong phạm vi này.</b>
    <p>{role === 'QUESTION_REVIEWER' ? 'Bạn chưa được giao câu hỏi hoặc chapter nào để duyệt, hoặc chapter được giao chưa có dữ liệu.' : 'Hãy upload tài liệu hoặc tạo câu hỏi đầu tiên trong phạm vi được phân quyền.'}</p>
    <Link className="btn secondary small" href="/bank/departments">Đi tới Ngân hàng câu hỏi</Link>
  </div>
}

function DashboardErrorState({ message, onRetry }: { message: string; onRetry: () => void }) {
  return <div className="dashboard-error-state">
    <b>Không tải được dashboard.</b>
    <p>{message || 'API trả về lỗi. Vui lòng thử lại hoặc kiểm tra backend logs.'}</p>
    <button className="btn small" type="button" onClick={onRetry}>Thử lại</button>
  </div>
}

function KpiCard({ item, tone }: { item: DashboardKpi; tone?: string }) {
  return <Link className={`dashboard-kpi-card ${tone || ''}`} href={drilldownUrl(item.drilldown)}>
    <span>{item.label}</span>
    <b>{formatNumber(item.value)}</b>
    <small>{item.overdue ? `${formatNumber(item.overdue)} quá hạn · ` : ''}{item.percent !== undefined ? `${item.percent}% trong tổng số` : item.delta_label}</small>
  </Link>
}

function ChartCard({ title, children, empty }: { title: string; children: React.ReactNode; empty?: boolean }) {
  return <section className="card dashboard-chart-card">
    <div className="section-head compact-section-head"><div><h2>{title}</h2></div></div>
    {empty ? <div className="dashboard-chart-empty">Chưa có dữ liệu phù hợp.</div> : children}
  </section>
}

function DonutChart({ chart }: { chart: DashboardChart }) {
  const router = useRouter()
  const items = (chart.items || []).filter((item) => Number(item.value || 0) > 0)
  const total = items.reduce((sum, item) => sum + Number(item.value || 0), 0)
  let offset = (2 * Math.PI * 34) * 0.25
  const radius = 34
  const circumference = 2 * Math.PI * radius
  return <ChartCard title={chart.title} empty={!items.length}>
    <div className="dashboard-donut-layout">
      <svg className="dashboard-donut" viewBox="0 0 100 100" role="img" aria-label={chart.title}>
        <circle cx="50" cy="50" r={radius} fill="none" stroke="#e5e7eb" strokeWidth="14" />
        {items.map((item, index) => {
          const value = Number(item.value || 0)
          const dash = total ? (value / total) * circumference : 0
          const segmentOffset = offset
          offset -= dash
          return <circle
            key={`${item.key || item.label}-${index}`}
            cx="50"
            cy="50"
            r={radius}
            fill="none"
            stroke={STATUS_COLORS[String(item.key)] || `hsl(${(index * 67) % 360} 70% 45%)`}
            strokeWidth="14"
            strokeDasharray={`${dash} ${circumference - dash}`}
            strokeDashoffset={segmentOffset}
            className="dashboard-clickable-segment"
            onClick={() => item.drilldown && router.push(drilldownUrl(item.drilldown))}
          />
        })}
        <text x="50" y="49" textAnchor="middle" className="dashboard-donut-value">{formatNumber(total)}</text>
        <text x="50" y="61" textAnchor="middle" className="dashboard-donut-label">tổng</text>
      </svg>
      <div className="dashboard-legend-list">
        {items.map((item, index) => <button key={`${item.key || item.label}-${index}`} type="button" className="dashboard-legend-row" onClick={() => item.drilldown && router.push(drilldownUrl(item.drilldown))} title={`${item.label}: ${formatNumber(item.value)} (${item.percent || 0}%)`}>
          <i style={{ background: STATUS_COLORS[String(item.key)] || `hsl(${(index * 67) % 360} 70% 45%)` }} />
          <span>{item.label}</span>
          <b>{formatNumber(item.value)}</b>
          <em>{item.percent || 0}%</em>
        </button>)}
      </div>
    </div>
  </ChartCard>
}

function LineChart({ chart }: { chart: DashboardChart }) {
  const router = useRouter()
  const items = chart.items || []
  const max = Math.max(1, ...items.map((item) => Number(item.value || 0)))
  const width = 520
  const height = 190
  const padX = 28
  const padY = 24
  const points = items.map((item, index) => {
    const x = items.length <= 1 ? width / 2 : padX + (index * (width - padX * 2)) / (items.length - 1)
    const y = height - padY - (Number(item.value || 0) / max) * (height - padY * 2)
    return { x, y, item }
  })
  const path = points.map((p, index) => `${index === 0 ? 'M' : 'L'} ${p.x} ${p.y}`).join(' ')
  return <ChartCard title={chart.title} empty={!items.length}>
    <div className="dashboard-line-wrap">
      <svg className="dashboard-line" viewBox={`0 0 ${width} ${height}`} role="img" aria-label={chart.title}>
        {[0, .25, .5, .75, 1].map((ratio) => {
          const y = padY + ratio * (height - padY * 2)
          const value = Math.round(max * (1 - ratio))
          return <g key={ratio}>
            <line x1={padX + 20} x2={width - padX} y1={y} y2={y} stroke="#e5e7eb" strokeWidth="1" />
            <text x={padX + 14} y={y + 4} textAnchor="end" className="dashboard-y-axis-label">{formatNumber(value)}</text>
          </g>
        })}
        <path d={path} fill="none" stroke="#2563eb" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
        {points.map((point, index) => <g key={`${point.item.date || index}-${index}`} className="dashboard-line-point" onClick={() => point.item.drilldown && router.push(drilldownUrl(point.item.drilldown))}>
          <circle cx={point.x} cy={point.y} r="5" fill="#2563eb" />
          <title>{point.item.label || point.item.date}: {formatNumber(point.item.value)}</title>
        </g>)}
      </svg>
      <div className="dashboard-line-axis"><span>{items[0]?.label || items[0]?.date}</span><span>{items[items.length - 1]?.label || items[items.length - 1]?.date}</span></div>
    </div>
  </ChartCard>
}

function HorizontalBarChart({ chart }: { chart: DashboardChart }) {
  const router = useRouter()
  const items = chart.items || []
  const max = Math.max(1, ...items.map((item) => Number(item.value || 0)))
  return <ChartCard title={chart.title} empty={!items.length}>
    <div className="dashboard-bar-list">
      {items.map((item, index) => <button key={`${item.subject_id || item.label}-${index}`} type="button" className="dashboard-horizontal-bar" onClick={() => item.drilldown && router.push(drilldownUrl(item.drilldown))} title={`${item.label}: ${formatNumber(item.value)}`}>
        <span>{item.label}</span>
        <div><i style={{ width: `${Math.max(4, (Number(item.value || 0) / max) * 100)}%` }} /></div>
        <b>{formatNumber(item.value)}</b>
      </button>)}
    </div>
  </ChartCard>
}

function GroupedBarChart({ chart }: { chart: DashboardChart }) {
  const router = useRouter()
  const items = chart.items || []
  const max = Math.max(1, ...items.flatMap((item) => [Number(item.current || 0), Number(item.previous || 0)]))
  return <ChartCard title={chart.title} empty={!items.length}>
    <div className="dashboard-grouped-legend"><span><i className="current" />{chart.current_term || 'Kỳ này'}</span><span><i className="previous" />{chart.previous_term || 'Kỳ trước'}</span></div>
    <div className="dashboard-grouped-list">
      {items.map((item, index) => <button key={`${item.subject_id || item.label}-${index}`} type="button" className="dashboard-grouped-row" onClick={() => item.drilldown && router.push(drilldownUrl(item.drilldown))}>
        <span>{item.label}</span>
        <div className="dashboard-group-pair">
          <i className="current" style={{ width: `${Math.max(3, (Number(item.current || 0) / max) * 100)}%` }} />
          <i className="previous" style={{ width: `${Math.max(3, (Number(item.previous || 0) / max) * 100)}%` }} />
        </div>
        <b>{formatNumber(item.current)} / {formatNumber(item.previous)}</b>
      </button>)}
    </div>
  </ChartCard>
}

function AlertPanel({ alerts }: { alerts: DashboardAnalytics['alerts'] }) {
  const router = useRouter()
  return <section className="card dashboard-alert-panel">
    <div className="section-head compact-section-head"><div><h2>Cảnh báo cần xử lý</h2><p className="helper">Ưu tiên các việc đang chậm hoặc có nguy cơ thiếu dữ liệu.</p></div></div>
    <div className="dashboard-alert-list">
      {alerts.length ? alerts.map((alert) => <button key={alert.id} type="button" className={`dashboard-alert-item ${alert.severity}`} onClick={() => alert.drilldown && router.push(drilldownUrl(alert.drilldown))}>
        <span>{alert.severity === 'critical' ? '🔴' : alert.severity === 'warning' ? '🟡' : '🔵'}</span>
        <div><b>{alert.title}</b>{alert.description ? <small>{alert.description}</small> : null}</div>
      </button>) : <div className="dashboard-chart-empty">Chưa có cảnh báo trong phạm vi này.</div>}
    </div>
  </section>
}

function ActivityFeed({ items }: { items: DashboardAnalytics['activity_feed'] }) {
  const router = useRouter()
  return <section className="card dashboard-activity-panel">
    <div className="section-head compact-section-head"><div><h2>Hoạt động gần đây</h2><p className="helper">10 thao tác mới nhất trong phạm vi bạn được xem.</p></div></div>
    <div className="dashboard-activity-list">
      {items.length ? items.map((item) => <button key={item.id} type="button" className="dashboard-activity-item" onClick={() => item.drilldown && router.push(drilldownUrl(item.drilldown))}>
        <span>{item.status === 'failed' ? '⚠️' : '•'}</span>
        <div><b>{item.message}</b><small>{item.relative_time || item.created_at || ''}</small></div>
      </button>) : <div className="dashboard-chart-empty">Chưa có hoạt động gần đây.</div>}
    </div>
  </section>
}

function DateFilters({ dateRange, fromDate, toDate, onPreset, onCustom }: { dateRange: string; fromDate: string; toDate: string; onPreset: (preset: string) => void; onCustom: (from: string, to: string) => void }) {
  const [from, setFrom] = useState(fromDate)
  const [to, setTo] = useState(toDate)
  useEffect(() => { setFrom(fromDate); setTo(toDate) }, [fromDate, toDate])
  return <div className="dashboard-filter-row">
    {['today', '7d', '30d'].map((preset) => <button key={preset} className={`btn small ${dateRange === preset ? '' : 'secondary'}`} type="button" onClick={() => onPreset(preset)}>{preset === 'today' ? 'Hôm nay' : preset === '7d' ? '7 ngày' : '30 ngày'}</button>)}
    <input className="input dashboard-date-input" type="date" value={from} onChange={(event) => setFrom(event.target.value)} />
    <input className="input dashboard-date-input" type="date" value={to} onChange={(event) => setTo(event.target.value)} />
    <button className={`btn small ${dateRange === 'custom' ? '' : 'secondary'}`} type="button" onClick={() => onCustom(from, to)}>Áp dụng</button>
  </div>
}

export function BankDashboardPage() {
  const { headers, authReady } = useBankData()
  const router = useRouter()
  const searchParams = useSearchParams()
  const initialRange = searchParams.get('range') || '30d'
  const initialFrom = searchParams.get('from') || buildDateRange(30).fromDate
  const initialTo = searchParams.get('to') || todayIso()
  const [dateRange, setDateRange] = useState(initialRange)
  const [fromDate, setFromDate] = useState(initialFrom)
  const [toDate, setToDate] = useState(initialTo)
  const [data, setData] = useState<DashboardAnalytics | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [alertsOpen, setAlertsOpen] = useState(false)
  const [activityOpen, setActivityOpen] = useState(false)

  const updateUrl = (range: string, from?: string, to?: string) => {
    const params = new URLSearchParams()
    params.set('range', range)
    if (from) params.set('from', from)
    if (to) params.set('to', to)
    router.replace(`/bank?${params.toString()}`, { scroll: false })
  }

  const load = async () => {
    if (!authReady) return
    setLoading(true)
    setError('')
    try {
      const payload = await getBankDashboardAnalytics(headers, { dateRange, fromDate, toDate })
      setData(payload)
    } catch (err: any) {
      setError(err?.message || 'Không tải được dashboard')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [authReady, headers, dateRange, fromDate, toDate]) // eslint-disable-line react-hooks/exhaustive-deps

  const hasData = useMemo(() => data ? Object.values(data.kpis || {}).some((item) => Number(item.value || 0) > 0) : false, [data])

  const onPreset = (preset: string) => {
    const range = preset === 'today' ? { fromDate: todayIso(), toDate: todayIso() } : preset === '7d' ? buildDateRange(7) : buildDateRange(30)
    setDateRange(preset)
    setFromDate(range.fromDate)
    setToDate(range.toDate)
    updateUrl(preset, range.fromDate, range.toDate)
  }
  const onCustom = (from: string, to: string) => {
    setDateRange('custom')
    setFromDate(from)
    setToDate(to)
    updateUrl('custom', from, to)
  }

  return <div className="page-stack bank-multipage dashboard-analytics-page">
    <Breadcrumb items={[{ label: 'Ngân hàng câu hỏi' }]} />

    <PageHeader
      eyebrow="Ngân hàng đề"
      title="Tổng quan Ngân hàng câu hỏi"
      description="Theo dõi khối lượng câu hỏi, hàng chờ duyệt và hoạt động trong phạm vi được giao."
      secondaryActions={<DateFilters dateRange={dateRange} fromDate={fromDate} toDate={toDate} onPreset={onPreset} onCustom={onCustom} />}
    />
    <div className="dashboard-scope-strip dashboard-scope-strip-compact">
      <span className="dashboard-scope-chip">Phạm vi: <b>{data?.scope?.label || 'Đang xác định...'}</b></span>
      {data?.cache ? <span className="dashboard-scope-chip subtle">Dữ liệu: {data.cache.hit ? 'đã lưu tạm' : 'mới cập nhật'}</span> : null}
      {data?.generated_at ? <span className="dashboard-scope-chip subtle">Cập nhật: {formatVNDateTime(data.generated_at)}</span> : null}
    </div>

    {loading ? <>
      <section className="dashboard-kpi-grid"><SkeletonBlock height={112} /><SkeletonBlock height={112} /><SkeletonBlock height={112} /><SkeletonBlock height={112} /></section>
      <section className="dashboard-chart-grid"><SkeletonBlock height={260} /><SkeletonBlock height={260} /><SkeletonBlock height={260} /><SkeletonBlock height={260} /></section>
    </> : error ? <DashboardErrorState message={error} onRetry={load} /> : data ? <>
      {!hasData ? <DashboardEmptyState role={data.scope?.role} /> : null}

      <section className="dashboard-kpi-grid">
        <KpiCard item={data.kpis.total_questions} />
        <KpiCard item={data.kpis.pending_review} tone={Number(data.kpis.pending_review.value || 0) > 0 ? 'warning' : 'success'} />
        <KpiCard item={data.kpis.approved} tone="success" />
        <KpiCard item={data.kpis.rejected} tone={Number(data.kpis.rejected.value || 0) > 0 ? 'danger' : ''} />
      </section>

      <section className="dashboard-tech-strip">
        <span><b>{formatNumber(Number(data.meta?.departments_total || 0))}</b> bộ môn</span>
        <span><b>{formatNumber(Number(data.meta?.subjects_total || 0))}</b> môn</span>
        <span><b>{formatNumber(Number(data.meta?.subject_versions_total || 0))}</b> phiên bản môn</span>
        <span><b>{formatNumber(Number(data.meta?.chapters_total || 0))}</b> bài</span>
      </section>

      <section className="card bank-search-card">
        <div className="section-head">
          <div><h2>Tìm nhanh</h2><p className="helper">Tìm bộ môn, môn, phiên bản, bài hoặc câu hỏi trong phạm vi được giao.</p></div>
          <div className="button-row compact">
            <button className="btn small secondary" type="button" onClick={() => setAlertsOpen(true)}>Cảnh báo ({formatNumber((data.alerts || []).length)})</button>
            <button className="btn small secondary" type="button" onClick={() => setActivityOpen(true)}>Hoạt động ({formatNumber((data.activity_feed || []).length)})</button>
          </div>
        </div>
        <QuickSearchBox />
      </section>

      <section className="dashboard-chart-grid">
        <DonutChart chart={data.charts.question_status} />
        <LineChart chart={data.charts.new_questions_by_day} />
        <HorizontalBarChart chart={data.charts.questions_by_subject} />
        <DonutChart chart={data.charts.difficulty_distribution} />
        <DonutChart chart={data.charts.question_type_distribution} />
        <GroupedBarChart chart={data.charts.term_comparison} />
      </section>

      <Modal open={alertsOpen} title="Cảnh báo cần xử lý" wide onClose={() => setAlertsOpen(false)}>
        <AlertPanel alerts={data.alerts || []} />
      </Modal>
      <Modal open={activityOpen} title="Hoạt động gần đây" wide onClose={() => setActivityOpen(false)}>
        <ActivityFeed items={data.activity_feed || []} />
      </Modal>
    </> : null}
  </div>
}
