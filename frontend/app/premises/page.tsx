'use client'

import { useEffect, useMemo, useState } from 'react'
import { useAppContext } from '../../context/AppContext'
import { getAcademicCampuses, saveAcademicCampus } from '../../lib/api'
import { AcademicCampus } from '../../types'

const EMPTY_FORM = { campus_code: '', campus_name: '', branch: 'poly', active: true, sort_order: 0 }
type CampusForm = typeof EMPTY_FORM
type ActiveFilter = 'active' | 'inactive' | 'all'

function codeLabel(code?: string | null) { return (code || '').toUpperCase() }
function branchLabel(branch?: string | null) { return (branch || '').toLowerCase() === 'ptcd' ? 'PTCĐ' : 'Poly' }
function sourceLabel(item: AcademicCampus) {
  const source = item.metadata_json?.source
  if (source === 'acms_html_premises') return 'Import từ ACMS'
  if (source === 'manual_ui') return 'Nhập tay'
  if (source === 'env.ACADEMIC_AP_CAMPUSES') return 'Seed từ env'
  return source || '—'
}

export default function PremisesPage() {
  const { authHeaders, can } = useAppContext()
  const headers = useMemo(() => authHeaders(), [authHeaders])
  const jsonHeaders = useMemo(() => authHeaders(true), [authHeaders])
  const [items, setItems] = useState<AcademicCampus[]>([])
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState('')
  const [branch, setBranch] = useState('poly')
  const [activeFilter, setActiveFilter] = useState<ActiveFilter>('active')
  const [search, setSearch] = useState('')
  const [form, setForm] = useState<CampusForm>({ ...EMPTY_FORM })
  const [editingId, setEditingId] = useState<string | null>(null)
  const [modalOpen, setModalOpen] = useState(false)

  const load = async () => {
    setLoading(true); setMessage('')
    try {
      const active = activeFilter === 'all' ? null : activeFilter === 'active'
      setItems(await getAcademicCampuses(headers, { branch, active }))
    } catch (error) { setMessage(error instanceof Error ? error.message : 'Không tải được danh sách cơ sở') }
    finally { setLoading(false) }
  }
  useEffect(() => { load() }, [headers, branch, activeFilter])

  const filtered = items.filter((item) => {
    const q = search.trim().toLowerCase(); if (!q) return true
    return [item.campus_code, item.campus_name, item.branch, sourceLabel(item)].some((value) => String(value || '').toLowerCase().includes(q))
  })
  const openCreate = () => { setForm({ ...EMPTY_FORM, branch }); setEditingId(null); setModalOpen(true) }
  const edit = (item: AcademicCampus) => {
    setEditingId(item.id)
    setForm({ campus_code: codeLabel(item.campus_code), campus_name: item.campus_name || '', branch: item.branch || 'poly', active: item.active, sort_order: item.sort_order || 0 })
    setModalOpen(true)
  }
  const save = async () => {
    const code = form.campus_code.trim(); const name = form.campus_name.trim()
    if (!code) { setMessage('Thiếu mã cơ sở'); return }
    if (!name) { setMessage('Thiếu tên cơ sở'); return }
    setSaving(true); setMessage('')
    try {
      const saved = await saveAcademicCampus(jsonHeaders, { campus_code: code, campus_name: name, branch: form.branch, active: form.active, sort_order: Number(form.sort_order || 0) })
      setMessage(`Đã lưu cơ sở ${codeLabel(saved.campus_code)} · ${saved.campus_name}`)
      setModalOpen(false); setEditingId(null); setForm({ ...EMPTY_FORM, branch: saved.branch || form.branch }); setBranch(saved.branch || form.branch)
      await load()
    } catch (error) { setMessage(error instanceof Error ? error.message : 'Lưu cơ sở thất bại') }
    finally { setSaving(false) }
  }
  const toggleActive = async (item: AcademicCampus) => {
    setSaving(true); setMessage('')
    try {
      await saveAcademicCampus(jsonHeaders, { campus_code: item.campus_code, campus_name: item.campus_name || codeLabel(item.campus_code), branch: item.branch || branch, active: !item.active, sort_order: item.sort_order || 0 })
      setMessage(`${!item.active ? 'Đã bật lại' : 'Đã ẩn'} cơ sở ${codeLabel(item.campus_code)}`)
      await load()
    } catch (error) { setMessage(error instanceof Error ? error.message : 'Cập nhật trạng thái thất bại') }
    finally { setSaving(false) }
  }

  if (!can('manage_settings')) return <div className="page-stack"><section className="hero-card compact-hero"><div><div className="eyebrow">Premises</div><h1>Cơ sở</h1><p>Bạn không có quyền quản trị cơ sở.</p></div></section></div>

  return <div className="page-stack premises-page">
    <section className="hero-card compact-hero"><div><div className="eyebrow">AP master data</div><h1>Cơ sở</h1><p>Quản lý danh mục cơ sở dùng cho đồng bộ AP. Thêm/sửa bằng popup để không rời trang.</p></div><div className="hero-actions"><button className="btn secondary" disabled={loading} onClick={load}>Làm mới</button><button className="btn" onClick={openCreate}>Thêm cơ sở</button></div></section>
    {message ? <div className="alert">{message}</div> : null}
    <section className="card"><div className="section-head"><div><h2>Danh sách cơ sở</h2><p>{loading ? 'Đang tải...' : `${filtered.length} / ${items.length} cơ sở`}</p></div></div>
      <div className="filter-grid academic-filter-grid"><label>Hệ<select className="input" value={branch} onChange={(event) => setBranch(event.target.value)}><option value="poly">Poly</option><option value="ptcd">PTCĐ</option></select></label><label>Trạng thái<select className="input" value={activeFilter} onChange={(event) => setActiveFilter(event.target.value as ActiveFilter)}><option value="active">Đang dùng</option><option value="inactive">Đã ẩn</option><option value="all">Tất cả</option></select></label><label>Tìm kiếm<input className="input" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="PT, Thái Nguyên, TP. HCM..." /></label></div>
      <div className="table-wrap" style={{ marginTop: 16 }}><table className="data-table compact-table"><thead><tr><th>Hệ</th><th>Mã cơ sở</th><th>Tên cơ sở</th><th>Nguồn</th><th>Trạng thái</th><th>Thao tác</th></tr></thead><tbody>{filtered.map((item) => <tr key={item.id}><td><b>{branchLabel(item.branch)}</b><small>{item.branch || 'poly'}</small></td><td><b>{codeLabel(item.campus_code)}</b><small>AP header campus: {(item.campus_code || '').toLowerCase()}</small></td><td>{item.campus_name || '—'}</td><td><span className="status-pill neutral">{sourceLabel(item)}</span></td><td><span className={item.active ? 'status-pill success' : 'status-pill warning'}>{item.active ? 'Đang dùng' : 'Đã ẩn'}</span></td><td><div className="row-actions"><button className="btn small secondary" onClick={() => edit(item)}>Sửa</button><button className="btn small secondary" disabled={saving} onClick={() => toggleActive(item)}>{item.active ? 'Ẩn' : 'Bật lại'}</button></div></td></tr>)}{!filtered.length ? <tr><td colSpan={6}><div className="empty-state">Chưa có cơ sở phù hợp.</div></td></tr> : null}</tbody></table></div>
    </section>
    {modalOpen ? <div className="modal-backdrop" onClick={() => !saving && setModalOpen(false)}><div className="card bank-modal" onClick={(event) => event.stopPropagation()}><div className="bank-modal-head"><div><div className="eyebrow">{editingId ? 'Sửa cơ sở' : 'Thêm mới cơ sở'}</div><h2>{editingId ? codeLabel(form.campus_code) : 'Cơ sở mới'}</h2></div><button className="btn small secondary" disabled={saving} onClick={() => setModalOpen(false)}>Đóng</button></div><div className="bank-modal-body"><div className="filter-grid academic-filter-grid"><label>Mã cơ sở<input className="input" value={form.campus_code} onChange={(event) => setForm((value) => ({ ...value, campus_code: event.target.value.toUpperCase() }))} placeholder="PT" /></label><label>Tên cơ sở<input className="input" value={form.campus_name} onChange={(event) => setForm((value) => ({ ...value, campus_name: event.target.value }))} placeholder="Thái Nguyên" /></label><label>Hệ<select className="input" value={form.branch} onChange={(event) => setForm((value) => ({ ...value, branch: event.target.value }))}><option value="poly">Poly</option><option value="ptcd">PTCĐ</option></select></label><label>Thứ tự<input className="input" type="number" value={form.sort_order} onChange={(event) => setForm((value) => ({ ...value, sort_order: Number(event.target.value || 0) }))} /></label><label>Trạng thái<select className="input" value={form.active ? 'true' : 'false'} onChange={(event) => setForm((value) => ({ ...value, active: event.target.value === 'true' }))}><option value="true">Đang dùng</option><option value="false">Ẩn</option></select></label></div><div className="modal-actions"><button className="btn" disabled={saving} onClick={save}>{saving ? 'Đang lưu...' : 'Lưu cơ sở'}</button><button className="btn secondary" disabled={saving} onClick={() => setModalOpen(false)}>Hủy</button></div></div></div></div> : null}
  </div>
}
