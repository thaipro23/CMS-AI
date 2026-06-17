'use client'

import { useEffect, useMemo, useState } from 'react'
import { useAppContext } from '../../context/AppContext'
import { deleteAcademicTerm, getAcademicTermWithBlocks, getAcademicTerms, saveAcademicTerm } from '../../lib/api'
import { AcademicBlock, AcademicTerm } from '../../types'

type Branch = 'poly' | 'ptcd'
type TermRow = AcademicTerm & { blocks?: AcademicBlock[] }
type BlockForm = { id?: string | null; block_code: string; block_name: string; start_date: string; end_date: string; active: boolean }
type TermForm = { id?: string | null; term_code: string; term_name: string; branch: Branch; active: boolean; blocks: BlockForm[] }

function branchLabel(branch?: string | null) { return (branch || '').toLowerCase() === 'ptcd' ? 'PTCĐ' : 'Poly' }
function formatDate(value?: string | null) { if (!value) return '—'; try { return new Date(value).toLocaleDateString('vi-VN') } catch { return '—' } }
function toDateInput(value?: string | null) { if (!value) return ''; try { return new Date(value).toISOString().slice(0, 10) } catch { return '' } }
function toIsoDate(value: string) { return value ? `${value}T00:00:00` : null }
function defaultBlocks(): BlockForm[] { return [{ block_code: 'Block 1', block_name: 'Block 1', start_date: '', end_date: '', active: true }, { block_code: 'Block 2', block_name: 'Block 2', start_date: '', end_date: '', active: true }] }
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
      const sourceBlocks = (full.blocks || []).slice(0, 2)
      const nextBlocks = [0, 1].map((index) => {
        const block = sourceBlocks[index]
        return block ? { id: block.id, block_code: block.block_code || `Block ${index + 1}`, block_name: block.block_name || `Block ${index + 1}`, start_date: toDateInput(block.start_date), end_date: toDateInput(block.end_date), active: block.active } : defaultBlocks()[index]
      })
      setForm({ id: full.id, term_code: full.term_code, term_name: full.term_name, branch: (full.branch || 'poly') as Branch, active: full.active, blocks: nextBlocks })
      setModalOpen(true)
    } catch (error) { setMessage(error instanceof Error ? error.message : 'Không tải được học kỳ') }
    finally { setSaving(false) }
  }
  const updateBlock = (index: number, patch: Partial<BlockForm>) => setForm((value) => ({ ...value, blocks: value.blocks.map((block, idx) => idx === index ? { ...block, ...patch } : block) }))
  const save = async () => {
    if (!form.term_code.trim()) { setMessage('Thiếu mã học kỳ'); return }
    if (!form.term_name.trim()) { setMessage('Thiếu tên học kỳ'); return }
    if (form.blocks.length !== 2) { setMessage('Một kỳ phải có đúng 2 block'); return }
    setSaving(true); setMessage('')
    try {
      await saveAcademicTerm(jsonHeaders, { id: form.id, term_code: form.term_code.trim(), term_name: form.term_name.trim(), branch: form.branch, start_date: null, end_date: null, active: form.active, blocks: form.blocks.map((block, index) => ({ id: block.id, block_code: block.block_code.trim() || `Block ${index + 1}`, block_name: block.block_name.trim() || `Block ${index + 1}`, start_date: toIsoDate(block.start_date), end_date: toIsoDate(block.end_date), sort_order: index + 1, active: block.active })) })
      setMessage(`Đã lưu học kỳ ${form.term_code}`)
      setModalOpen(false)
      await load()
    } catch (error) { setMessage(error instanceof Error ? error.message : 'Lưu học kỳ thất bại') }
    finally { setSaving(false) }
  }
  const remove = async (item: TermRow) => {
    if (!window.confirm(`Xóa học kỳ ${item.term_name}?\n\nCác block của kỳ này cũng sẽ bị ẩn khỏi dropdown đồng bộ AP. Dữ liệu lịch sử lớp/sinh viên không bị xóa.`)) return
    setSaving(true); setMessage('')
    try {
      await deleteAcademicTerm(jsonHeaders, item.id)
      setMessage(`Đã xóa học kỳ ${item.term_name}`)
      await load()
    } catch (error) { setMessage(error instanceof Error ? error.message : 'Xóa học kỳ thất bại') }
    finally { setSaving(false) }
  }

  if (!can('manage_settings')) return <div className="page-stack"><section className="hero-card compact-hero"><div><div className="eyebrow">Semesters</div><h1>Học kỳ</h1><p>Bạn không có quyền quản trị học kỳ.</p></div></section></div>

  return <div className="page-stack semesters-page">
    <section className="hero-card compact-hero"><div><div className="eyebrow">AP master data</div><h1>Học kỳ & Block</h1><p>Quản lý kỳ học và 2 block/kế hoạch học dùng cho đồng bộ AP. Thêm mới/chỉnh sửa bằng popup.</p></div><div className="hero-actions"><button className="btn secondary" disabled={loading} onClick={load}>Làm mới</button><button className="btn" onClick={openCreate}>Thêm học kỳ</button></div></section>
    {message ? <div className="alert">{message}</div> : null}
    <section className="card"><div className="section-head"><div><h2>Danh sách học kỳ</h2><p>{loading ? 'Đang tải...' : `${items.length} học kỳ`}</p></div></div>
      <div className="table-wrap" style={{ marginTop: 16 }}><table className="data-table compact-table"><thead><tr><th>Hệ</th><th>Mã học kỳ</th><th>Tên học kỳ</th><th>Block 1</th><th>Block 2</th><th>Trạng thái</th><th>Thao tác</th></tr></thead><tbody>{items.map((item) => {
        const activeBlocks = (item.blocks || []).slice(0, 2)
        const b1 = activeBlocks[0]
        const b2 = activeBlocks[1]
        return <tr key={item.id}><td><b>{branchLabel(item.branch)}</b></td><td><b>{item.term_code}</b></td><td>{item.term_name}</td><td>{b1 ? <><b>{b1.block_name}</b><small>{formatDate(b1.start_date)} → {formatDate(b1.end_date)}</small></> : '—'}</td><td>{b2 ? <><b>{b2.block_name}</b><small>{formatDate(b2.start_date)} → {formatDate(b2.end_date)}</small></> : '—'}</td><td><span className={item.active ? 'status-pill success' : 'status-pill danger'}>{item.active ? 'Đang dùng' : 'Đã xóa'}</span></td><td><div className="row-actions"><button className="btn small secondary" onClick={() => openEdit(item)}>Sửa</button><button className="btn small danger" disabled={saving} onClick={() => remove(item)}>Xóa</button></div></td></tr>
      })}{!items.length ? <tr><td colSpan={7}><div className="empty-state">Chưa có học kỳ.</div></td></tr> : null}</tbody></table></div>
    </section>
    {modalOpen ? <div className="modal-backdrop" onClick={() => !saving && setModalOpen(false)}><div className="card bank-modal bank-modal-wide" onClick={(event) => event.stopPropagation()}><div className="bank-modal-head"><div><div className="eyebrow">{form.id ? 'Sửa học kỳ' : 'Thêm mới học kỳ'}</div><h2>{form.id ? form.term_code : 'Học kỳ mới'}</h2></div><button className="btn small secondary" disabled={saving} onClick={() => setModalOpen(false)}>Đóng</button></div><div className="bank-modal-body"><div className="filter-grid academic-filter-grid"><label>Hệ<select className="input" value={form.branch} onChange={(event) => setForm((value) => ({ ...value, branch: event.target.value as Branch }))}><option value="poly">Poly</option><option value="ptcd">PTCĐ</option></select></label><label>Mã học kỳ<input className="input" value={form.term_code} onChange={(event) => setForm((value) => ({ ...value, term_code: event.target.value, term_name: value.term_name || event.target.value }))} placeholder="Summer 2026" /></label><label>Tên học kỳ<input className="input" value={form.term_name} onChange={(event) => setForm((value) => ({ ...value, term_name: event.target.value }))} placeholder="Summer 2026" /></label><label>Trạng thái<select className="input" value={form.active ? 'true' : 'false'} onChange={(event) => setForm((value) => ({ ...value, active: event.target.value === 'true' }))}><option value="true">Đang dùng</option><option value="false">Đã xóa</option></select></label></div><div className="section-head" style={{ marginTop: 18 }}><div><h3>Block/kế hoạch học</h3><p>Mỗi kỳ có đúng 2 block.</p></div></div><div className="table-wrap"><table className="data-table compact-table"><thead><tr><th>Mã block</th><th>Tên block</th><th>Bắt đầu</th><th>Kết thúc</th><th>Trạng thái</th></tr></thead><tbody>{form.blocks.map((block, index) => <tr key={`${block.id || 'new'}-${index}`}><td><input className="input" value={block.block_code} onChange={(event) => updateBlock(index, { block_code: event.target.value })} /></td><td><input className="input" value={block.block_name} onChange={(event) => updateBlock(index, { block_name: event.target.value })} /></td><td><input className="input" type="date" value={block.start_date} onChange={(event) => updateBlock(index, { start_date: event.target.value })} /></td><td><input className="input" type="date" value={block.end_date} onChange={(event) => updateBlock(index, { end_date: event.target.value })} /></td><td><select className="input" value={block.active ? 'true' : 'false'} onChange={(event) => updateBlock(index, { active: event.target.value === 'true' })}><option value="true">Đang dùng</option><option value="false">Đã xóa</option></select></td></tr>)}</tbody></table></div><div className="modal-actions"><button className="btn" disabled={saving} onClick={save}>{saving ? 'Đang lưu...' : 'Lưu học kỳ'}</button><button className="btn secondary" disabled={saving} onClick={() => setModalOpen(false)}>Hủy</button></div></div></div></div> : null}
  </div>
}
