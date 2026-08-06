'use client'

import Link from 'next/link'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { useParams } from 'next/navigation'
import { useAppContext } from '../../../../context/AppContext'
import { createUdemyPlanVersion, getUdemyPlanDetail, getUdemyPlanHistory } from '../../../../lib/api'
import type { UdemyPlanDetail, UdemyPlanMilestone, UdemySubjectPlan } from '../../../../types'
import { PageRoot } from '../../../../components/layout/PageHeader'
import { EnterpriseScreenHeader } from '../../../../components/layout/EnterpriseDesignContract'
import { OperationsKpiStrip, WorkspaceSection } from '../../../../components/operations/OperationsWorkspace'
import { EnterpriseDataTable, type EnterpriseTableColumn } from '../../../../components/table/EnterpriseDataTable'
import { InlineNotice, noticeError, noticeSuccess, noticeWarning } from '../../../../components/ui/InlineNotice'
import { StatusBadge } from '../../../../components/ui/StatusBadge'

function formatDate(value?: string | null) {
  if (!value) return '—'
  const date = new Date(`${value}T00:00:00`)
  return Number.isNaN(date.getTime()) ? value : new Intl.DateTimeFormat('vi-VN').format(date)
}
function formatDateTime(value?: string | null) {
  if (!value) return '—'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : new Intl.DateTimeFormat('vi-VN', { dateStyle: 'short', timeStyle: 'short' }).format(date)
}
function blankMilestone(week: number): UdemyPlanMilestone {
  return { week_number: week, deadline_date: '', required_progress_percent: 0 }
}

export default function UdemyPlanPage() {
  const params = useParams<{ deliveryId: string }>()
  const deliveryId = String(params?.deliveryId || '')
  const { authHeaders, can } = useAppContext()
  const headers = useMemo(() => authHeaders(), [authHeaders])
  const jsonHeaders = useMemo(() => authHeaders(true), [authHeaders])
  const canManage = can('manage_settings')

  const [detail, setDetail] = useState<UdemyPlanDetail | null>(null)
  const [history, setHistory] = useState<UdemySubjectPlan[]>([])
  const [itemCount, setItemCount] = useState(1)
  const [milestones, setMilestones] = useState<UdemyPlanMilestone[]>([blankMilestone(1)])
  const [note, setNote] = useState('')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')

  const load = useCallback(async () => {
    if (!deliveryId || !canManage) return
    setLoading(true)
    setError('')
    try {
      const [nextDetail, nextHistory] = await Promise.all([
        getUdemyPlanDetail(headers, deliveryId),
        getUdemyPlanHistory(headers, deliveryId),
      ])
      setDetail(nextDetail)
      setHistory(nextHistory)
      if (nextDetail.active_plan) {
        setItemCount(nextDetail.active_plan.item_count)
        setMilestones(nextDetail.active_plan.milestones.map((item) => ({ ...item, deadline_date: String(item.deadline_date).slice(0, 10) })))
        setNote(nextDetail.active_plan.note || '')
      } else {
        setItemCount(1)
        setMilestones([blankMilestone(1)])
        setNote('')
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Không tải được kế hoạch Udemy.')
    } finally { setLoading(false) }
  }, [canManage, deliveryId, headers])

  useEffect(() => { void load() }, [load])

  const sortedMilestones = useMemo(() => [...milestones].sort((a, b) => a.week_number - b.week_number), [milestones])
  const finalProgress = sortedMilestones.at(-1)?.required_progress_percent || 0
  const nextVersion = (detail?.active_plan?.version || 0) + 1

  const historyColumns = useMemo<EnterpriseTableColumn<UdemySubjectPlan>[]>(() => [
    { key: 'stt', header: 'STT', kind: 'index', width: 54, render: (_row, index) => index + 1 },
    { key: 'version', header: 'Phiên bản', kind: 'identity', width: 105, render: (plan) => <b>v{plan.version}</b> },
    { key: 'status', header: 'Trạng thái', kind: 'status', minWidth: 125, render: (plan) => <StatusBadge status={plan.active ? 'active' : 'inactive'} label={plan.active ? 'Đang dùng' : 'Lịch sử'} /> },
    { key: 'items', header: 'Item', kind: 'number', width: 80, render: (plan) => plan.item_count },
    { key: 'milestones', header: 'Các mốc', kind: 'text', minWidth: 310, render: (plan) => <div className="udemy-history-milestones">{plan.milestones.map((item) => <span key={item.week_number}>W{item.week_number}: {formatDate(item.deadline_date)} · {item.required_progress_percent}%</span>)}</div> },
    { key: 'source', header: 'Nguồn', kind: 'text', minWidth: 150, render: (plan) => <div>{plan.source === 'excel_import' ? 'Excel' : 'Thủ công'}{plan.source_file_name ? <small>{plan.source_file_name}</small> : null}</div> },
    { key: 'actor', header: 'Người thực hiện', kind: 'identity', minWidth: 170, render: (plan) => plan.imported_by || 'Hệ thống' },
    { key: 'time', header: 'Thời gian', kind: 'date', minWidth: 145, render: (plan) => formatDateTime(plan.imported_at) },
    { key: 'note', header: 'Ghi chú', kind: 'text', minWidth: 230, render: (plan) => plan.note || '—' },
  ], [])

  const updateMilestone = (index: number, patch: Partial<UdemyPlanMilestone>) => {
    setMilestones((current) => current.map((item, currentIndex) => currentIndex === index ? { ...item, ...patch } : item))
  }
  const addMilestone = () => {
    const used = new Set(milestones.map((item) => item.week_number))
    let week = 1
    while (used.has(week) && week <= 52) week += 1
    if (week <= 52) setMilestones((current) => [...current, blankMilestone(week)].sort((a, b) => a.week_number - b.week_number))
  }
  const removeMilestone = (index: number) => {
    setMilestones((current) => current.length <= 1 ? current : current.filter((_, currentIndex) => currentIndex !== index))
  }

  const save = async () => {
    setError('')
    setMessage('')
    if (!Number.isInteger(Number(itemCount)) || Number(itemCount) <= 0) { setError('Số lượng Item phải là số nguyên lớn hơn 0.'); return }
    if (milestones.some((item) => !item.deadline_date)) { setError('Hãy nhập đầy đủ deadline cho tất cả các mốc.'); return }
    const normalized = [...milestones].sort((a, b) => Number(a.week_number) - Number(b.week_number))
    const usedWeeks = new Set<number>()
    for (let index = 0; index < normalized.length; index += 1) {
      const current = normalized[index]
      const week = Number(current.week_number)
      const progress = Number(current.required_progress_percent)
      if (!Number.isInteger(week) || week < 1 || week > 52 || usedWeeks.has(week)) { setError('Số tuần phải duy nhất và nằm trong khoảng 1–52.'); return }
      usedWeeks.add(week)
      if (!Number.isFinite(progress) || progress < 0 || progress > 100) { setError(`Week ${week}: tiến độ phải từ 0 đến 100.`); return }
      if (index > 0) {
        const previous = normalized[index - 1]
        if (String(current.deadline_date) <= String(previous.deadline_date)) { setError(`Week ${week}: deadline phải sau Week ${previous.week_number}.`); return }
        if (progress < Number(previous.required_progress_percent)) { setError(`Week ${week}: tiến độ không được giảm so với Week ${previous.week_number}.`); return }
      }
    }
    setMilestones(normalized)
    setSaving(true)
    try {
      const result = await createUdemyPlanVersion(jsonHeaders, deliveryId, {
        item_count: Number(itemCount),
        milestones: normalized.map((item) => ({
          week_number: Number(item.week_number),
          deadline_date: item.deadline_date,
          required_progress_percent: Number(item.required_progress_percent),
        })),
        note: note.trim() || null,
      })
      setMessage(result.message)
      await load()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Không lưu được kế hoạch Udemy.')
    } finally { setSaving(false) }
  }

  if (!canManage) return <PageRoot className="page-stack enterprise-standard-page udemy-plan-page"><EnterpriseScreenHeader eyebrow="Danh mục" title="Kế hoạch Udemy" description="Bạn không có quyền quản lý kế hoạch môn học." icon="book" tone="blue" breadcrumbs={[{ label: 'Danh mục', href: '/subject-management' }, { label: 'Kế hoạch Udemy' }]} /><section className="card empty-state">Bạn không có quyền quản lý kế hoạch Udemy.</section></PageRoot>

  return <PageRoot className="page-stack enterprise-standard-page udemy-plan-page">
    <EnterpriseScreenHeader
      eyebrow="Quản lý môn học"
      title={detail ? `${detail.delivery.subject_code} · Kế hoạch Udemy` : 'Kế hoạch Udemy'}
      description={detail ? `${detail.delivery.subject_name} · ${detail.delivery.term_name} · ${detail.delivery.block_name}` : 'Tạo và quản lý kế hoạch tiến độ theo phiên bản.'}
      icon="book"
      tone="blue"
      breadcrumbs={[{ label: 'Danh mục' }, { label: 'Quản lý môn học', href: '/subject-management' }, { label: detail?.delivery.subject_code || 'Kế hoạch Udemy' }]}
      secondaryActions={<Link className="btn secondary" href="/subject-management">Quay lại danh sách</Link>}
      primaryAction={<button className="btn" type="button" disabled={loading || saving || detail?.delivery.learning_platform !== 'udemy'} onClick={() => void save()}>{saving ? 'Đang lưu...' : `Lưu phiên bản v${nextVersion}`}</button>}
    />

    <InlineNotice notice={message ? noticeSuccess(message) : null} />
    <InlineNotice notice={error ? noticeError(error) : null} />
    <InlineNotice notice={detail?.delivery.learning_platform !== 'udemy' ? noticeWarning('Hãy quay lại Quản lý môn học và chọn Udemy trước khi tạo kế hoạch.', 'Môn hiện không vận hành trên Udemy') : null} />

    <OperationsKpiStrip items={[
      { label: 'Phiên bản hiện tại', value: detail?.active_plan ? `v${detail.active_plan.version}` : 'Chưa có', hint: detail?.active_plan ? `Cập nhật ${formatDateTime(detail.active_plan.updated_at || detail.active_plan.imported_at)}` : 'Lưu lần đầu để tạo v1' },
      { label: 'Số lượng Item', value: detail?.active_plan?.item_count || 0, hint: 'Tổng item của môn Udemy', tone: 'info' },
      { label: 'Số mốc', value: detail?.active_plan?.milestones.length || 0, hint: 'Deadline và tiến độ bắt buộc', tone: 'success' },
      { label: 'Tiến độ mốc cuối', value: `${detail?.active_plan?.milestones.at(-1)?.required_progress_percent || 0}%`, hint: 'Khuyến nghị mốc cuối đạt 100%', tone: finalProgress < 100 ? 'warning' : 'success' },
    ]} />

    <WorkspaceSection title={`Soạn phiên bản v${nextVersion}`} description="Mỗi lần lưu tạo phiên bản mới; dữ liệu cũ không bị ghi đè." icon="calendar" tone="green">
      {loading ? <div className="card empty-state">Đang tải kế hoạch...</div> : <div className="udemy-plan-editor">
        <div className="udemy-plan-editor-meta">
          <label>Số lượng Item<input className="input" type="number" min={1} step={1} value={itemCount} onChange={(event) => setItemCount(Number(event.target.value))} /></label>
          <label>Ghi chú phiên bản<textarea className="input" rows={3} value={note} onChange={(event) => setNote(event.target.value)} placeholder="Ví dụ: Điều chỉnh deadline theo lịch học mới..." /></label>
        </div>
        <div className="udemy-plan-editor-heading"><div><h3>Các mốc tiến độ</h3><p>Deadline phải tăng dần; tiến độ từ 0–100 và không được giảm.</p></div><button className="btn small secondary" type="button" onClick={addMilestone} disabled={milestones.length >= 52}>Thêm mốc</button></div>
        <div className="responsive-table-wrap" role="region" aria-label="Bảng soạn các mốc tiến độ Udemy" tabIndex={0}><table className="ops-data-table udemy-plan-milestone-table"><caption className="sr-only">Các mốc tiến độ của phiên bản kế hoạch mới</caption><thead><tr><th>STT</th><th>Tuần</th><th>Deadline</th><th>Tiến độ yêu cầu</th><th>Thao tác</th></tr></thead><tbody>{milestones.map((item, index) => <tr key={`${item.week_number}-${index}`}><td>{index + 1}</td><td><label className="sr-only" htmlFor={`milestone-week-${index}`}>Tuần của mốc {index + 1}</label><input id={`milestone-week-${index}`} className="input compact-input" type="number" min={1} max={52} value={item.week_number} onChange={(event) => updateMilestone(index, { week_number: Number(event.target.value) })} /></td><td><label className="sr-only" htmlFor={`milestone-date-${index}`}>Deadline của mốc {index + 1}</label><input id={`milestone-date-${index}`} className="input" type="date" value={item.deadline_date || ''} onChange={(event) => updateMilestone(index, { deadline_date: event.target.value })} /></td><td><div className="udemy-progress-input"><label className="sr-only" htmlFor={`milestone-progress-${index}`}>Tiến độ yêu cầu của mốc {index + 1}</label><input id={`milestone-progress-${index}`} className="input" type="number" min={0} max={100} step={0.01} value={item.required_progress_percent} onChange={(event) => updateMilestone(index, { required_progress_percent: Number(event.target.value) })} /><span aria-hidden="true">%</span></div></td><td><button className="btn small danger" type="button" disabled={milestones.length <= 1} onClick={() => removeMilestone(index)}>Xóa</button></td></tr>)}</tbody></table></div>
        <InlineNotice notice={finalProgress < 100 ? noticeWarning(`Mốc cuối hiện là ${finalProgress}%. Hệ thống vẫn cho lưu, nhưng kế hoạch hoàn chỉnh thường kết thúc ở 100%.`, 'Kế hoạch chưa đạt 100%') : null} />
      </div>}
    </WorkspaceSection>

    <WorkspaceSection title="Lịch sử phiên bản" description="Phiên bản đang dùng là nguồn đánh giá tiến độ hiện tại." icon="clock" tone="slate">
      <EnterpriseDataTable
        tableId="udemy-plan-history-batch35-1"
        caption="Lịch sử phiên bản kế hoạch Udemy"
        rows={history}
        columns={historyColumns}
        rowKey={(plan) => plan.id}
        loading={loading}
        emptyTitle="Chưa có phiên bản kế hoạch"
        emptyDescription="Lưu phiên bản đầu tiên để bắt đầu theo dõi kế hoạch theo lịch sử."
        label="phiên bản"
        stickyHorizontalScroll
      />
    </WorkspaceSection>
  </PageRoot>
}
