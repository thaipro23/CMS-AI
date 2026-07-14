'use client'

import { useEffect, useMemo, useState } from 'react'
import { useAppContext } from '../../context/AppContext'
import { deleteAcademicTerm, getAcademicTermWithBlocks, getAcademicTerms, saveAcademicTerm } from '../../lib/api'
import { AcademicBlock, AcademicTerm } from '../../types'
import { PageHeader } from '../../components/layout/PageHeader'
import { EnterpriseDataTable, type EnterpriseTableColumn } from '../../components/table/EnterpriseDataTable'
import { OperationsKpiStrip, WorkspaceSection } from '../../components/operations/OperationsWorkspace'
import { StatusBadge } from '../../components/ui/StatusBadge'
import { addDaysToVNDateInput, formatVNDate, normalizeVNDateInput, vnDateInputToISODate, vnDateInputToISODateTime } from '../../lib/time'

type Branch = 'poly' | 'ptcd'
type TermRow = AcademicTerm & { blocks?: AcademicBlock[] }
type LearningWeekForm = { week_number: number; start_date: string; end_date: string; note?: string }
type BlockForm = { id?: string | null; block_code: string; block_name: string; start_date: string; end_date: string; active: boolean; learning_weeks: LearningWeekForm[] }
type TermForm = { id?: string | null; term_code: string; term_name: string; branch: Branch; active: boolean; blocks: BlockForm[] }

function branchLabel(branch?: string | null) { return (branch || '').toLowerCase() === 'ptcd' ? 'PTCĐ' : 'Poly' }
function formatDate(value?: string | null) { return formatVNDate(value) }
function toDateInput(value?: string | null) { return vnDateInputToISODate(value) }
function normalizeDateInput(value: string) { return vnDateInputToISODate(value) }
function toIsoDate(value: string) { return vnDateInputToISODateTime(value) }
function addDays(value: string, days: number) { return vnDateInputToISODate(addDaysToVNDateInput(value, days)) }
function defaultLearningWeeks(startDate = ''): LearningWeekForm[] {
  return Array.from({ length: 6 }, (_, index) => ({
    week_number: index + 1,
    start_date: startDate ? addDays(startDate, index * 7) : '',
    end_date: startDate ? addDays(startDate, index * 7 + 5) : '',
    note: '',
  }))
}

function blockNoHint(block?: AcademicBlock | null) {
  const raw = `${block?.sort_order ?? ''} ${block?.block_code || ''} ${block?.block_name || ''}`.toLowerCase()
  const explicit = raw.match(/(?:^|\D)([12])(?:\D|$)/)
  if (explicit) return Number(explicit[1])
  return null
}
function pickBlocksForTermForm(blocks?: AcademicBlock[] | null): Array<AcademicBlock | null> {
  const source = (blocks || []).slice().filter(Boolean)
  const ranked = source.sort((a, b) => {
    const activeDelta = Number(b.active !== false) - Number(a.active !== false)
    if (activeDelta) return activeDelta
    const aHint = blockNoHint(a) || Number(a.sort_order || 0) || 99
    const bHint = blockNoHint(b) || Number(b.sort_order || 0) || 99
    if (aHint !== bHint) return aHint - bHint
    return String(a.block_name || a.block_code || '').localeCompare(String(b.block_name || b.block_code || ''), 'vi')
  })
  const used = new Set<string>()
  return [1, 2].map((wanted) => {
    const exact = ranked.find((block) => !used.has(block.id) && (Number(block.sort_order || 0) === wanted || blockNoHint(block) === wanted))
    const fallback = exact || ranked.find((block) => !used.has(block.id)) || null
    if (fallback?.id) used.add(fallback.id)
    return fallback
  })
}

type LearningWeekMetadata = {
  week_number?: number | string | null
  start_date?: string | null
  from_date?: string | null
  from?: string | null
  end_date?: string | null
  to_date?: string | null
  to?: string | null
  deadline_date?: string | null
  note?: string | null
}

function isLearningWeekMetadata(value: unknown): value is LearningWeekMetadata {
  return typeof value === 'object' && value !== null
}

function learningWeeksFromMetadata(block?: AcademicBlock | null, startDate = ''): LearningWeekForm[] {
  const rawValue = block?.metadata_json?.learning_weeks
  const raw = Array.isArray(rawValue) ? rawValue.filter(isLearningWeekMetadata) : []
  const rows = raw.map((item, index): LearningWeekForm => ({
    week_number: Number(item.week_number || index + 1),
    start_date: toDateInput(item.start_date || item.from_date || item.from),
    end_date: toDateInput(item.end_date || item.to_date || item.to || item.deadline_date),
    note: String(item.note || ''),
  })).filter((item) => item.start_date || item.end_date)
  return rows.length ? rows : defaultLearningWeeks(startDate)
}
function normalizeLearningWeeks(weeks: LearningWeekForm[]) {
  return weeks.map((week, index) => ({
    week_number: Number(week.week_number || index + 1),
    start_date: toIsoDate(week.start_date),
    end_date: toIsoDate(week.end_date),
    note: String(week.note || '').trim(),
  })).filter((week) => week.start_date && week.end_date)
}
function defaultBlocks(): BlockForm[] { return [{ block_code: 'Block 1', block_name: 'Block 1', start_date: '', end_date: '', active: true, learning_weeks: defaultLearningWeeks() }, { block_code: 'Block 2', block_name: 'Block 2', start_date: '', end_date: '', active: true, learning_weeks: defaultLearningWeeks() }] }
function emptyForm(branch: Branch = 'poly'): TermForm { return { term_code: 'Summer 2026', term_name: 'Summer 2026', branch, active: true, blocks: defaultBlocks() } }

export default function SemestersPage() {
  const { authHeaders, can } = useAppContext()
  const headers = useMemo(() => authHeaders(), [authHeaders])
  const jsonHeaders = useMemo(() => authHeaders(true), [authHeaders])
  const [items, setItems] = useState<TermRow[]>([])
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState('')
  const [modalOpen, setModalOpen] = useState(false)
  const [form, setForm] = useState<TermForm>(emptyForm())
  const [deleteTarget, setDeleteTarget] = useState<TermRow | null>(null)

  const load = async () => {
    setLoading(true); setMessage('')
    try {
      const terms = await getAcademicTerms(headers, { active: null })
      const withBlocks = await Promise.all(terms.map(async (term) => {
        try { return await getAcademicTermWithBlocks(headers, term.id) as TermRow } catch { return { ...term, blocks: [] } }
      }))
      setItems(withBlocks)
    } catch (error) { setMessage(error instanceof Error ? error.message : 'Không tải được danh sách học kỳ') }
    finally { setLoading(false) }
  }
  useEffect(() => { load() }, [headers])

  const openCreate = () => { setForm(emptyForm()); setModalOpen(true) }
  const openEdit = async (item: TermRow) => {
    setSaving(true); setMessage('')
    try {
      const full = await getAcademicTermWithBlocks(headers, item.id) as TermRow
      const sourceBlocks = pickBlocksForTermForm(full.blocks || [])
      const nextBlocks = [0, 1].map((index) => {
        const block = sourceBlocks[index]
        return block ? { id: block.id, block_code: block.block_code || `Block ${index + 1}`, block_name: block.block_name || `Block ${index + 1}`, start_date: toDateInput(block.start_date), end_date: toDateInput(block.end_date), active: block.active, learning_weeks: learningWeeksFromMetadata(block, toDateInput(block.start_date)) } : defaultBlocks()[index]
      })
      setForm({ id: full.id, term_code: full.term_code, term_name: full.term_name, branch: (full.branch || 'poly') as Branch, active: full.active, blocks: nextBlocks })
      setModalOpen(true)
    } catch (error) { setMessage(error instanceof Error ? error.message : 'Không tải được học kỳ') }
    finally { setSaving(false) }
  }
  const updateBlock = (index: number, patch: Partial<BlockForm>) => setForm((value) => ({ ...value, blocks: value.blocks.map((block, idx) => idx === index ? { ...block, ...patch } : block) }))
  const updateLearningWeek = (blockIndex: number, weekIndex: number, patch: Partial<LearningWeekForm>) => setForm((value) => ({ ...value, blocks: value.blocks.map((block, idx) => idx === blockIndex ? { ...block, learning_weeks: block.learning_weeks.map((week, widx) => widx === weekIndex ? { ...week, ...patch } : week) } : block) }))
  const rebuildLearningWeeks = (blockIndex: number) => setForm((value) => ({ ...value, blocks: value.blocks.map((block, idx) => idx === blockIndex ? { ...block, learning_weeks: defaultLearningWeeks(block.start_date) } : block) }))
  const save = async () => {
    if (!form.term_code.trim()) { setMessage('Thiếu mã học kỳ'); return }
    if (!form.term_name.trim()) { setMessage('Thiếu tên học kỳ'); return }
    if (form.blocks.length !== 2) { setMessage('Một kỳ phải có đúng 2 block'); return }
    const invalidDateBlock = form.blocks.find((block) => (block.start_date && !normalizeDateInput(block.start_date)) || (block.end_date && !normalizeDateInput(block.end_date)) || block.learning_weeks.some((week) => (week.start_date && !normalizeDateInput(week.start_date)) || (week.end_date && !normalizeDateInput(week.end_date))))
    if (invalidDateBlock) { setMessage('Ngày block/tuần học phải chọn bằng date picker; hệ thống hiển thị theo dd/mm/yyyy và lưu theo giờ Việt Nam'); return }
    setSaving(true); setMessage('')
    try {
      await saveAcademicTerm(jsonHeaders, { id: form.id, term_code: form.term_code.trim(), term_name: form.term_name.trim(), branch: form.branch, start_date: null, end_date: null, active: form.active, blocks: form.blocks.map((block, index) => ({ id: block.id, block_code: block.block_code.trim() || `Block ${index + 1}`, block_name: block.block_name.trim() || `Block ${index + 1}`, start_date: toIsoDate(block.start_date), end_date: toIsoDate(block.end_date), sort_order: index + 1, active: block.active, metadata_json: { learning_weeks: normalizeLearningWeeks(block.learning_weeks), learning_week_source: 'semesters_page' } })) })
      setMessage(`Đã lưu học kỳ ${form.term_code}`)
      setModalOpen(false)
      await load()
    } catch (error) { setMessage(error instanceof Error ? error.message : 'Lưu học kỳ thất bại') }
    finally { setSaving(false) }
  }
  const confirmDelete = async () => {
    if (!deleteTarget) return
    setSaving(true); setMessage('')
    try {
      await deleteAcademicTerm(jsonHeaders, deleteTarget.id)
      setMessage(`Đã xóa học kỳ ${deleteTarget.term_name}`)
      setDeleteTarget(null)
      await load()
    } catch (error) { setMessage(error instanceof Error ? error.message : 'Xóa học kỳ thất bại') }
    finally { setSaving(false) }
  }

  const columns: EnterpriseTableColumn<TermRow>[] = [
    { key: 'stt', header: 'STT', kind: 'index', width: 52, hideable: false, render: (_item, index) => index + 1 },
    { key: 'term', header: 'Học kỳ', kind: 'identity', minWidth: 220, hideable: false, render: (item) => <div><b>{item.term_code}</b><small>{item.term_name} · {branchLabel(item.branch)}</small></div> },
    { key: 'blocks', header: 'Lịch 2 block', kind: 'text', minWidth: 330, priority: 'important', hideable: true, render: (item) => <div className="term-block-summary">{(item.blocks || []).slice(0, 2).map((block, index) => <span key={block.id || index}><b>{block.block_name || `Block ${index + 1}`}</b><small>{formatDate(block.start_date)} → {formatDate(block.end_date)}</small></span>)}{!(item.blocks || []).length ? <span>Chưa cấu hình</span> : null}</div> },
    { key: 'status', header: 'Trạng thái', kind: 'status', width: 112, hideable: true, render: (item) => <StatusBadge status={item.active ? 'active' : 'inactive'} label={item.active ? 'Đang dùng' : 'Đã xóa'} /> },
    { key: 'actions', header: 'Thao tác', kind: 'actions', width: 112, sticky: 'right', hideable: false, render: (item) => <div className="row-actions"><button className="btn small secondary" type="button" onClick={() => openEdit(item)}>Sửa</button><details className="row-action-menu"><summary className="btn small ghost" aria-label="Mở thêm thao tác">•••</summary><div className="row-action-popover"><button type="button" className="danger-text" disabled={saving} onClick={() => setDeleteTarget(item)}>Xóa học kỳ</button></div></details></div> },
  ]

  if (!can('manage_settings')) return <div className="page-stack"><PageHeader eyebrow="Danh mục" title="Học kỳ" description="Bạn không có quyền quản trị học kỳ." /></div>

  return <div className="page-stack semesters-page">
    <PageHeader eyebrow="Danh mục" title="Học kỳ & Cấu hình tuần học" description="Quản lý kỳ, block và lịch tuần học dùng để xác định deadline Quiz." secondaryActions={<button className="btn secondary" type="button" disabled={loading} onClick={load}>Làm mới</button>} primaryAction={<button className="btn" type="button" onClick={openCreate}>Thêm học kỳ</button>} />
    {message ? <div className="alert">{message}</div> : null}
    <OperationsKpiStrip items={[
      { label: 'Tổng học kỳ', value: items.length, hint: 'Poly và PTCĐ' },
      { label: 'Đang dùng', value: items.filter((item) => item.active).length, hint: 'Có thể chọn trong vận hành', tone: 'success' },
      { label: 'Đã khóa/xóa', value: items.length - items.filter((item) => item.active).length, hint: 'Giữ lại dữ liệu lịch sử' },
    ]} />
    <WorkspaceSection title="Danh sách học kỳ" description="Mỗi học kỳ có đúng 2 block; lịch tuần học được chỉnh trong màn Sửa.">
      <EnterpriseDataTable tableId="semesters-v2" caption="Danh sách học kỳ" rows={items} columns={columns} rowKey={(item) => item.id} density="compact" loading={loading} label="học kỳ" emptyTitle="Chưa có học kỳ" emptyDescription="Tạo học kỳ mới để cấu hình block và tuần học." />
    </WorkspaceSection>
    {modalOpen ? <div className="modal-backdrop bank-popup-backdrop" onMouseDown={() => !saving && setModalOpen(false)}><div className="card bank-modal bank-modal-wide" onMouseDown={(event) => event.stopPropagation()}><div className="bank-modal-head"><div><div className="eyebrow">{form.id ? 'Sửa học kỳ' : 'Thêm mới học kỳ'}</div><h2>{form.id ? form.term_code : 'Học kỳ mới'}</h2></div><button className="btn small secondary" disabled={saving} onClick={() => setModalOpen(false)}>Đóng</button></div><div className="bank-modal-body"><div className="academic-modal-form"><label>Hệ<select className="input" value={form.branch} onChange={(event) => setForm((value) => ({ ...value, branch: event.target.value as Branch }))}><option value="poly">Poly</option><option value="ptcd">PTCĐ</option></select></label><label>Mã học kỳ<input className="input" value={form.term_code} onChange={(event) => setForm((value) => ({ ...value, term_code: event.target.value, term_name: value.term_name || event.target.value }))} placeholder="Summer 2026" /></label><label>Tên học kỳ<input className="input" value={form.term_name} onChange={(event) => setForm((value) => ({ ...value, term_name: event.target.value }))} placeholder="Summer 2026" /></label><label>Trạng thái<select className="input" value={form.active ? 'true' : 'false'} onChange={(event) => setForm((value) => ({ ...value, active: event.target.value === 'true' }))}><option value="true">Đang dùng</option><option value="false">Đã xóa</option></select></label></div><div className="section-head" style={{ marginTop: 18 }}><div><h3>Block & Cấu hình tuần học</h3><p>Mỗi kỳ có đúng 2 block. Chỉnh tuần học khi có nghỉ/lễ để deadline Quiz bám đúng lịch.</p></div></div><div className="term-block-editor">{form.blocks.map((block, index) => <section className="term-block-card" key={`${block.id || 'new'}-${index}`}><header><div><span>Block {index + 1}</span><b>{block.block_name || block.block_code}</b></div><button className="btn small secondary" type="button" onClick={() => rebuildLearningWeeks(index)}>Tự chia 6 tuần</button></header><div className="settings-form-grid"><label>Mã block<input className="input" value={block.block_code} onChange={(event) => updateBlock(index, { block_code: event.target.value })} /></label><label>Tên block<input className="input" value={block.block_name} onChange={(event) => updateBlock(index, { block_name: event.target.value })} /></label><label>Bắt đầu<input className="input" type="date" lang="vi-VN" value={block.start_date} onChange={(event) => updateBlock(index, { start_date: event.target.value })} /></label><label>Kết thúc<input className="input" type="date" lang="vi-VN" value={block.end_date} onChange={(event) => updateBlock(index, { end_date: event.target.value })} /></label></div><label className="check-row"><input type="checkbox" checked={block.active} onChange={(event) => updateBlock(index, { active: event.target.checked })} /> Block đang dùng</label><div className="learning-weeks-editor"><div className="learning-weeks-head"><b>6 tuần học</b><small>Định dạng ngày hiển thị dd/mm/yyyy.</small></div><div className="learning-weeks-grid">{block.learning_weeks.map((week, weekIndex) => <label className="learning-week-card" key={`${index}-${weekIndex}`}><span>Tuần {week.week_number}</span><input className="input" type="date" lang="vi-VN" value={week.start_date} onChange={(event) => updateLearningWeek(index, weekIndex, { start_date: event.target.value })} /><input className="input" type="date" lang="vi-VN" value={week.end_date} onChange={(event) => updateLearningWeek(index, weekIndex, { end_date: event.target.value })} /></label>)}</div></div></section>)}</div><div className="modal-actions"><button className="btn" disabled={saving} onClick={save}>{saving ? 'Đang lưu...' : 'Lưu học kỳ'}</button><button className="btn secondary" disabled={saving} onClick={() => setModalOpen(false)}>Hủy</button></div></div></div></div> : null}
    {deleteTarget ? <div className="modal-backdrop bank-popup-backdrop" onMouseDown={() => !saving && setDeleteTarget(null)}><div className="card bank-modal academic-confirm-modal" onMouseDown={(event) => event.stopPropagation()}><div className="bank-modal-head"><div><div className="eyebrow danger-text">Xác nhận xóa</div><h2>Xóa học kỳ {deleteTarget.term_name}?</h2></div><button className="btn small secondary" disabled={saving} onClick={() => setDeleteTarget(null)}>Đóng</button></div><div className="bank-modal-body academic-confirm-body"><p>Học kỳ <b>{deleteTarget.term_name}</b> và 2 block/kế hoạch học của kỳ này sẽ bị chuyển sang trạng thái đã xóa. Dữ liệu lớp/sinh viên lịch sử không bị xóa.</p><div className="academic-confirm-summary"><span>Hệ</span><b>{branchLabel(deleteTarget.branch)}</b><span>Mã học kỳ</span><b>{deleteTarget.term_code}</b></div><div className="modal-actions"><button className="btn danger" disabled={saving} onClick={confirmDelete}>{saving ? 'Đang xóa...' : 'Xác nhận xóa'}</button><button className="btn secondary" disabled={saving} onClick={() => setDeleteTarget(null)}>Hủy</button></div></div></div></div> : null}
  </div>
}
