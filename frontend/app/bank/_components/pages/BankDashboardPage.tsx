'use client'

import Link from 'next/link'
import { useRouter, useSearchParams } from 'next/navigation'
import { useEffect, useMemo, useState } from 'react'

import { EnterpriseDataTable, type EnterpriseTableColumn } from '../../../../components/table/EnterpriseDataTable'
import { PageHeader, PageRoot } from '../../../../components/layout/PageHeader'
import { InlineNotice, noticeError, noticeInfo } from '../../../../components/ui/InlineNotice'
import { VisualIcon } from '../../../../components/ui/VisualIcon'
import { useUrlTableState } from '../../../../hooks/useUrlTableState'
import { getBankCostAnalytics } from '../../../../lib/api'
import { daysAgoVNISODate, formatVNDateTime, todayVNISODate } from '../../../../lib/time'
import type { BankCostAnalytics, BankCostAnalyticsRow } from '../../../../types'
import { BankPageIdentity, BankSection } from '../BankDesignContract'
import { useBankData } from '../shared'

function formatNumber(value?: number | null) {
  return new Intl.NumberFormat('vi-VN').format(Number(value || 0))
}

function formatVnd(value?: number | null) {
  return `${new Intl.NumberFormat('vi-VN', { maximumFractionDigits: 0 }).format(Number(value || 0))} ₫`
}

function formatUsd(value?: number | null) {
  return `$${new Intl.NumberFormat('en-US', { minimumFractionDigits: 4, maximumFractionDigits: 4 }).format(Number(value || 0))}`
}

function buildDateRange(days: number) {
  return { fromDate: daysAgoVNISODate(Math.max(0, days - 1)), toDate: todayVNISODate() }
}

function deltaLabel(value?: number | null) {
  if (value === null || value === undefined) return 'Chưa có kỳ trước để so sánh'
  if (value === 0) return 'Không đổi so với kỳ trước'
  return `${value > 0 ? '+' : ''}${value}% so với kỳ trước`
}

function CostMetricCard({
  label,
  value,
  helper,
  icon,
  tone,
  emphasis,
}: {
  label: string
  value: string
  helper: string
  icon: 'money' | 'database' | 'sparkles' | 'sync'
  tone: 'blue' | 'green' | 'amber' | 'violet'
  emphasis?: string
}) {
  return <article className={`bank-cost-metric is-${tone}`}>
    <VisualIcon label={label} icon={icon} tone={tone} size={22} className="bank-cost-metric__icon" />
    <div className="bank-cost-metric__copy">
      <span>{label}</span>
      <b>{value}</b>
      <small>{helper}</small>
      {emphasis ? <em>{emphasis}</em> : null}
    </div>
  </article>
}

function CostTrendChart({ items }: { items: BankCostAnalytics['daily'] }) {
  const width = 760
  const height = 230
  const padX = 48
  const padY = 28
  const max = Math.max(1, ...items.map((item) => Number(item.cost_vnd || 0)))
  const points = items.map((item, index) => ({
    item,
    x: items.length <= 1 ? width / 2 : padX + (index * (width - padX * 2)) / (items.length - 1),
    y: height - padY - (Number(item.cost_vnd || 0) / max) * (height - padY * 2),
  }))
  const path = points.map((point, index) => `${index === 0 ? 'M' : 'L'} ${point.x} ${point.y}`).join(' ')
  const area = points.length ? `${path} L ${points[points.length - 1].x} ${height - padY} L ${points[0].x} ${height - padY} Z` : ''
  const visibleLabels = items.length <= 10 ? items : items.filter((_, index) => index === 0 || index === items.length - 1 || index % Math.ceil(items.length / 6) === 0)

  return <div className="bank-cost-trend">
    <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Chi phí thực tế theo ngày">
      {[0, .25, .5, .75, 1].map((ratio) => {
        const y = padY + ratio * (height - padY * 2)
        const value = Math.round(max * (1 - ratio))
        return <g key={ratio}>
          <line x1={padX} x2={width - padX} y1={y} y2={y} className="bank-cost-grid-line" />
          <text x={padX - 8} y={y + 4} textAnchor="end" className="bank-cost-axis-label">{formatNumber(value)}</text>
        </g>
      })}
      {area ? <path d={area} className="bank-cost-area" /> : null}
      {path ? <path d={path} className="bank-cost-line" /> : null}
      {points.map((point) => <g key={point.item.date}>
        <circle cx={point.x} cy={point.y} r="4.5" className="bank-cost-point" />
        <title>{point.item.label}: {formatVnd(point.item.cost_vnd)} · {formatNumber(point.item.total_tokens)} token</title>
      </g>)}
      {visibleLabels.map((item) => {
        const point = points.find((candidate) => candidate.item.date === item.date)
        return point ? <text key={item.date} x={point.x} y={height - 5} textAnchor="middle" className="bank-cost-axis-label">{item.label}</text> : null
      })}
    </svg>
  </div>
}

function CostTrendSummary({ items }: { items: BankCostAnalytics['daily'] }) {
  const total = items.reduce((sum, item) => sum + Number(item.cost_vnd || 0), 0)
  const average = items.length ? total / items.length : 0
  const peak = items.reduce((max, item) => Math.max(max, Number(item.cost_vnd || 0)), 0)
  return <div className="bank-cost-trend-summary">
    <div className="bank-cost-trend-legend"><i /> Chi phí thực tế (VND)</div>
    <div className="bank-cost-trend-stats">
      <span>Tổng kỳ hiện tại: <b>{formatVnd(total)}</b></span>
      <span>Trung bình/ngày: <b>{formatVnd(average)}</b></span>
      <span>Cao nhất trong kỳ: <b>{formatVnd(peak)}</b></span>
    </div>
  </div>
}

function TokenComposition({ totals }: { totals: BankCostAnalytics['totals'] }) {
  const input = Number(totals.uncached_input_tokens || 0)
  const cached = Number(totals.cached_input_tokens || 0)
  const output = Number(totals.output_tokens || 0)
  const actualTotal = input + cached + output
  const safeTotal = Math.max(1, actualTotal)
  const inputPercent = input * 100 / safeTotal
  const cachedPercent = cached * 100 / safeTotal
  const outputPercent = output * 100 / safeTotal
  const gradient = actualTotal
    ? `conic-gradient(var(--bank-cost-blue) 0 ${inputPercent}%, var(--bank-cost-violet) ${inputPercent}% ${inputPercent + cachedPercent}%, var(--bank-cost-green) ${inputPercent + cachedPercent}% 100%)`
    : 'conic-gradient(#dfe5ed 0 100%)'
  const parts = [
    { label: 'Input chưa cache', value: input, percent: inputPercent, className: 'is-input' },
    { label: 'Input cache', value: cached, percent: cachedPercent, className: 'is-cached' },
    { label: 'Output', value: output, percent: outputPercent, className: 'is-output' },
  ]
  return <div className="bank-token-composition">
    <div className="bank-token-donut-area">
      <div className="bank-token-donut" style={{ background: gradient }} aria-label={`Tổng ${formatNumber(actualTotal)} token`}>
        <div className="bank-token-donut__center">{actualTotal ? <><b>{formatNumber(actualTotal)}</b><small>token</small></> : null}</div>
      </div>
      {!actualTotal ? <div className="bank-token-empty-copy"><b>Chưa có dữ liệu token trong khoảng thời gian đã chọn.</b><span>Hãy thử mở rộng khoảng thời gian để xem dữ liệu.</span></div> : null}
    </div>
    <div className="bank-token-legend">
      {parts.map((part) => <div key={part.label}><i className={part.className} /><span>{part.label}</span><b>{formatNumber(part.value)}</b><small>{part.percent.toFixed(1)}%</small></div>)}
    </div>
    <div className="bank-token-total"><span>Tổng token</span><b>{formatNumber(actualTotal)}</b></div>
  </div>
}

function SubjectCostBars({ items }: { items: BankCostAnalytics['subjects'] }) {
  const max = Math.max(1, ...items.map((item) => Number(item.cost_vnd || 0)))
  if (!items.length) return <div className="bank-cost-empty">Chưa có chi phí thực tế theo môn trong khoảng thời gian này.</div>
  return <div className="bank-subject-cost-list">
    {items.map((item) => <div className="bank-subject-cost-row" key={item.subject_id}>
      <div><b>{item.subject_code}</b><small>{item.subject_name}</small></div>
      <div className="bank-subject-cost-track"><i style={{ width: `${Math.max(3, Number(item.cost_vnd || 0) * 100 / max)}%` }} /></div>
      <div><b>{formatVnd(item.cost_vnd)}</b><small>{formatNumber(item.questions_generated)} câu · {formatNumber(item.total_tokens)} token</small></div>
    </div>)}
  </div>
}

export function BankDashboardPage() {
  const { headers, authReady } = useBankData()
  const router = useRouter()
  const searchParams = useSearchParams()
  const { state: tableState, update: updateTableState } = useUrlTableState({ pageSize: 20, density: 'compact', sort: 'cost_vnd:desc' })
  const initialRange = searchParams.get('range') || '30d'
  const initialFrom = searchParams.get('from') || buildDateRange(30).fromDate
  const initialTo = searchParams.get('to') || todayVNISODate()
  const [appliedFilter, setAppliedFilter] = useState({ dateRange: initialRange, fromDate: initialFrom, toDate: initialTo })
  const [draftFromDate, setDraftFromDate] = useState(initialFrom)
  const [draftToDate, setDraftToDate] = useState(initialTo)
  const [searchDraft, setSearchDraft] = useState(tableState.q)
  const [data, setData] = useState<BankCostAnalytics | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [filterError, setFilterError] = useState('')
  const [showUsageNotice, setShowUsageNotice] = useState(true)

  const [sortKey, sortDirection] = useMemo(() => {
    const [key, direction] = (tableState.sort || 'cost_vnd:desc').split(':')
    return [key || 'cost_vnd', direction === 'asc' ? 'asc' : 'desc'] as const
  }, [tableState.sort])

  const updateDateUrl = (range: string, from: string, to: string) => {
    const params = new URLSearchParams(searchParams.toString())
    params.set('range', range)
    params.set('from', from)
    params.set('to', to)
    params.delete('page')
    router.replace(`/bank?${params.toString()}`, { scroll: false })
  }

  const load = async () => {
    if (!authReady) return
    setLoading(true)
    setError('')
    try {
      const payload = await getBankCostAnalytics(headers, {
        dateRange: appliedFilter.dateRange,
        fromDate: appliedFilter.fromDate,
        toDate: appliedFilter.toDate,
        q: tableState.q,
        page: tableState.page,
        pageSize: tableState.pageSize,
        sortBy: sortKey,
        sortDir: sortDirection,
      })
      setData(payload)
    } catch (err: any) {
      setError(err?.message || 'Không tải được thống kê chi phí và token')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [authReady, headers, appliedFilter.dateRange, appliedFilter.fromDate, appliedFilter.toDate, tableState.q, tableState.page, tableState.pageSize, sortKey, sortDirection]) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { setSearchDraft(tableState.q) }, [tableState.q])

  const applyPreset = (preset: string) => {
    const range = preset === 'today' ? { fromDate: todayVNISODate(), toDate: todayVNISODate() } : preset === '7d' ? buildDateRange(7) : buildDateRange(30)
    setDraftFromDate(range.fromDate)
    setDraftToDate(range.toDate)
    setAppliedFilter({ dateRange: preset, fromDate: range.fromDate, toDate: range.toDate })
    setFilterError('')
    updateDateUrl(preset, range.fromDate, range.toDate)
  }

  const applyCustom = () => {
    if (!draftFromDate || !draftToDate) {
      setFilterError('Vui lòng chọn đầy đủ Từ ngày và Đến ngày.')
      return
    }
    if (draftFromDate > draftToDate) {
      setFilterError('Từ ngày không được lớn hơn Đến ngày.')
      return
    }
    setFilterError('')
    setAppliedFilter({ dateRange: 'custom', fromDate: draftFromDate, toDate: draftToDate })
    updateDateUrl('custom', draftFromDate, draftToDate)
  }

  const emptyTotals = useMemo<BankCostAnalytics['totals']>(() => ({
    cost_usd: 0,
    cost_vnd: 0,
    input_tokens: 0,
    cached_input_tokens: 0,
    uncached_input_tokens: 0,
    output_tokens: 0,
    total_tokens: 0,
    calls: 0,
    questions_generated: 0,
    avg_cost_per_question_vnd: 0,
    cache_ratio_percent: 0,
  }), [])

  const columns = useMemo<EnterpriseTableColumn<BankCostAnalyticsRow>[]>(() => [
    { key: 'stt', header: 'STT', kind: 'index', width: 58, hideable: false, render: (_row, index) => (data?.rows.page ? (data.rows.page - 1) * data.rows.page_size : 0) + index + 1 },
    { key: 'subject_code', header: 'Môn / phiên bản / bài', kind: 'identity', minWidth: 310, sticky: 'left', hideable: false, sortable: true, render: (row) => <Link href={row.href} className="bank-cost-identity"><b>{row.subject_code} · {row.chapter_title}</b><span>{row.subject_name}</span><small>{row.subject_offering_code || row.version_code}{row.term ? ` · ${row.term}` : ''}</small></Link> },
    { key: 'calls', header: 'Lượt gọi', kind: 'number', width: 88, sortable: true, render: (row) => formatNumber(row.calls) },
    { key: 'questions_generated', header: 'Câu AI tạo', kind: 'number', width: 104, sortable: true, render: (row) => formatNumber(row.questions_generated) },
    { key: 'input_tokens', header: 'Input token', kind: 'number', width: 118, sortable: true, render: (row) => formatNumber(row.input_tokens) },
    { key: 'cached_input_tokens', header: 'Token cache', kind: 'number', width: 118, sortable: true, render: (row) => <div className="bank-cost-token-cell"><b>{formatNumber(row.cached_input_tokens)}</b><small>{row.cache_ratio_percent}% input</small></div> },
    { key: 'output_tokens', header: 'Output token', kind: 'number', width: 120, sortable: true, render: (row) => formatNumber(row.output_tokens) },
    { key: 'cost_vnd', header: 'Chi phí thực tế', kind: 'number', width: 150, sortable: true, render: (row) => <div className="bank-cost-money-cell"><b>{formatVnd(row.cost_vnd)}</b><small>{formatUsd(row.cost_usd)}</small></div> },
    { key: 'avg_cost_per_question_vnd', header: 'Bình quân/câu', kind: 'number', width: 128, sortable: true, defaultVisible: false, render: (row) => row.questions_generated ? formatVnd(row.avg_cost_per_question_vnd) : '—' },
    { key: 'latest_at', header: 'Gần nhất', kind: 'date', width: 148, sortable: true, defaultVisible: false, render: (row) => row.latest_at ? formatVNDateTime(row.latest_at) : '—' },
    { key: 'actions', header: 'Thao tác', kind: 'actions', width: 98, sticky: 'right', hideable: false, render: (row) => <Link className="btn small secondary" href={row.href}>Mở bài</Link> },
  ], [data?.rows.page, data?.rows.page_size])

  return <PageRoot className="page-stack bank-multipage bank-contract-page bank-cost-dashboard-page">
    <PageHeader eyebrow="Ngân hàng đề" title="Chi phí & Token" icon="money" breadcrumbs={[{ label: 'Ngân hàng đề', href: '/bank/departments' }, { label: 'Chi phí & Token' }]} />
    <BankPageIdentity
      title="Chi phí & Token ngân hàng đề"
      description="Theo dõi chi phí GPT thực tế, lượng token và hiệu suất tạo câu hỏi theo môn, phiên bản môn và bài học trong phạm vi được phân quyền."
      icon="money"
      tone="amber"
    />

    <section className="dashboard-control-bar bank-cost-filter-bar" aria-label="Bộ lọc thời gian và phạm vi">
      <div className="bank-cost-presets">
        {['today', '7d', '30d'].map((preset) => <button key={preset} type="button" className={`btn small ${appliedFilter.dateRange === preset ? '' : 'secondary'}`} onClick={() => applyPreset(preset)}>{preset === 'today' ? 'Hôm nay' : preset === '7d' ? '7 ngày' : '30 ngày'}</button>)}
      </div>
      <label><span>Từ ngày</span><input className="input" type="date" value={draftFromDate} onChange={(event) => { setDraftFromDate(event.target.value); setFilterError('') }} /></label>
      <label><span>Đến ngày</span><input className="input" type="date" value={draftToDate} onChange={(event) => { setDraftToDate(event.target.value); setFilterError('') }} /></label>
      <button className="btn small" type="button" onClick={applyCustom}>Áp dụng</button>
      <div className="bank-cost-filter-meta">
        {data?.scope?.label ? <span>Phạm vi <b>{data.scope.label}</b></span> : null}
        <span>Nguồn <b>Usage thực tế</b></span>
        {data?.generated_at ? <span>Cập nhật <b>{formatVNDateTime(data.generated_at)}</b></span> : null}
        <button type="button" className="bank-cost-refresh-button" onClick={load} aria-label="Tải lại thống kê" disabled={loading}>
          <VisualIcon icon="sync" tone="blue" label="Tải lại thống kê" size={15} />
        </button>
      </div>
    </section>

    {filterError ? <InlineNotice notice={noticeError(filterError, 'Khoảng thời gian chưa hợp lệ')} /> : null}

    {showUsageNotice ? <div className="bank-cost-notice-wrap">
      <button type="button" className="bank-cost-notice-close" aria-label="Đóng thông báo" onClick={() => setShowUsageNotice(false)}>×</button>
    </div> : null}

    {error ? <InlineNotice notice={{ ...noticeError(error, 'Không tải được thống kê chi phí và token.'), title: 'Không tải được thống kê', onRetry: load }} /> : null}

    <section className="bank-cost-metric-grid" aria-label="Chỉ số chi phí và token">
      <CostMetricCard label="Chi phí thực tế" value={loading ? '…' : formatVnd(data?.totals.cost_vnd)} helper={loading ? 'Đang tải dữ liệu' : formatUsd(data?.totals.cost_usd)} emphasis={loading ? undefined : deltaLabel(data?.deltas.cost_percent)} icon="money" tone="amber" />
      <CostMetricCard label="Tổng token" value={loading ? '…' : formatNumber(data?.totals.total_tokens)} helper={loading ? 'Đang tải dữ liệu' : `${formatNumber(data?.totals.input_tokens)} input · ${formatNumber(data?.totals.output_tokens)} output`} emphasis={loading ? undefined : deltaLabel(data?.deltas.tokens_percent)} icon="database" tone="blue" />
      <CostMetricCard label="Câu hỏi AI đã tạo" value={loading ? '…' : formatNumber(data?.totals.questions_generated)} helper={loading ? 'Đang tải dữ liệu' : `${formatVnd(data?.totals.avg_cost_per_question_vnd)} / câu`} emphasis={loading ? undefined : `${formatNumber(data?.totals.calls)} lượt gọi model`} icon="sparkles" tone="green" />
      <CostMetricCard label="Token dùng cache" value={loading ? '…' : formatNumber(data?.totals.cached_input_tokens)} helper={loading ? 'Đang tải dữ liệu' : `${data?.totals.cache_ratio_percent || 0}% tổng input token`} emphasis={loading ? undefined : `${formatNumber(data?.totals.uncached_input_tokens)} input chưa cache`} icon="sync" tone="violet" />
    </section>

    <section className="bank-cost-insight-grid">
      <BankSection
        title="Chi phí theo ngày"
        description="Chi phí VND thực tế phát sinh từ các lượt tạo câu hỏi AI."
        icon="analytics"
        tone="blue"
        className="bank-cost-trend-section"
        actions={<select className="bank-cost-currency-select" aria-label="Đơn vị chi phí" defaultValue="VND"><option>VND</option></select>}
      >
        {loading ? <div className="bank-cost-loading" /> : <><CostTrendChart items={data?.daily || []} /><CostTrendSummary items={data?.daily || []} /></>}
      </BankSection>
      <BankSection title="Cơ cấu token" description="Tách input chưa cache, input cache và output token." icon="database" tone="blue">
        {loading ? <div className="bank-cost-loading" /> : <TokenComposition totals={data?.totals || emptyTotals} />}
      </BankSection>
    </section>

    <BankSection title="Môn học sử dụng chi phí nhiều nhất" description="Xếp theo chi phí thực tế trong khoảng thời gian đang chọn." icon="book" tone="amber">
      {loading ? <div className="bank-cost-loading is-short" /> : <SubjectCostBars items={data?.subjects || []} />}
    </BankSection>

    <BankSection
      title="Chi tiết chi phí theo bộ đề"
      description="Mỗi dòng là một Bank Version gắn với môn, phiên bản môn và bài học."
      icon="money"
      tone="amber"
      meta={<span className="soft-tag">{formatNumber(data?.rows.total)} bộ đề có usage</span>}
      actions={<form className="bank-cost-search" onSubmit={(event) => { event.preventDefault(); updateTableState({ q: searchDraft }, { resetPage: true }) }}><input className="input" value={searchDraft} onChange={(event) => setSearchDraft(event.target.value)} placeholder="Tìm mã môn, phiên bản hoặc bài..." /><button className="btn small secondary" type="submit">Tìm</button>{tableState.q ? <button className="btn small ghost" type="button" onClick={() => { setSearchDraft(''); updateTableState({ q: '' }, { resetPage: true }) }}>Xóa lọc</button> : null}</form>}
      bodyClassName="bank-cost-table-section"
    >
      <EnterpriseDataTable
        tableId="bank-cost-analytics"
        caption="Chi tiết chi phí và token theo bộ đề"
        rows={data?.rows.items || []}
        columns={columns}
        rowKey={(row) => row.bank_version_id}
        density={tableState.density}
        onDensityChange={(density) => updateTableState({ density }, { resetPage: false })}
        loading={loading}
        error={error}
        onRetry={load}
        emptyTitle="Chưa có chi phí thực tế"
        emptyDescription="Chưa có lượt tạo câu hỏi AI được ghi nhận trong thời gian hoặc phạm vi đang chọn."
        page={data?.rows.page || tableState.page}
        pageSize={data?.rows.page_size || tableState.pageSize}
        total={data?.rows.total || 0}
        totalPages={data?.rows.total_pages || 0}
        onPageChange={(page) => updateTableState({ page }, { resetPage: false })}
        onPageSizeChange={(pageSize) => updateTableState({ pageSize, page: 1 }, { resetPage: false })}
        sortKey={sortKey}
        sortDirection={sortDirection}
        onSortChange={(key, direction) => updateTableState({ sort: `${key}:${direction}`, page: 1 }, { resetPage: false })}
        label="bộ đề"
        showSummary={false}
      />
    </BankSection>
  </PageRoot>
}
