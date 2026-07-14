'use client'

import { useEffect, useMemo, useState } from 'react'
import { useAppContext } from '../../context/AppContext'
import { deleteAcademicCampus, getAcademicCampuses, saveAcademicCampus } from '../../lib/api'
import { AcademicCampus } from '../../types'
import { PageHeader, PageRoot } from '../../components/layout/PageHeader'
import { EnterpriseDataTable, type EnterpriseTableColumn } from '../../components/table/EnterpriseDataTable'
import { CompactFilterBar, OperationsKpiStrip, WorkspaceSection } from '../../components/operations/OperationsWorkspace'
import { StatusBadge } from '../../components/ui/StatusBadge'

const EMPTY_FORM = { campus_code: '', campus_name: '', branch: 'poly', active: true }
type CampusForm = typeof EMPTY_FORM
type ActiveFilter = 'active' | 'inactive' | 'all'

function codeLabel(code?: string | null) { return (code || '').toUpperCase() }
function branchLabel(branch?: string | null) { return (branch || '').toLowerCase() === 'ptcd' ? 'PTCĐ' : 'Poly' }

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
  const [deleteTarget, setDeleteTarget] = useState<AcademicCampus | null>(null)

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
    return [item.campus_code, item.campus_name, item.branch].some((value) => String(value || '').toLowerCase().includes(q))
  })
  const openCreate = () => { setForm({ ...EMPTY_FORM, branch }); setEditingId(null); setModalOpen(true) }
  const edit = (item: AcademicCampus) => {
    setEditingId(item.id)
    setForm({ campus_code: codeLabel(item.campus_code), campus_name: item.campus_name || '', branch: item.branch || 'poly', active: item.active })
    setModalOpen(true)
  }
  const save = async () => {
    const code = form.campus_code.trim(); const name = form.campus_name.trim()
    if (!code) { setMessage('Thiếu mã cơ sở'); return }
    if (!name) { setMessage('Thiếu tên cơ sở'); return }
    setSaving(true); setMessage('')
    try {
      const saved = await saveAcademicCampus(jsonHeaders, { campus_code: code, campus_name: name, branch: form.branch, active: form.active })
      setMessage(`Đã lưu cơ sở ${codeLabel(saved.campus_code)} · ${saved.campus_name}`)
      setModalOpen(false); setEditingId(null); setForm({ ...EMPTY_FORM, branch: saved.branch || form.branch }); setBranch(saved.branch || form.branch)
      await load()
    } catch (error) { setMessage(error instanceof Error ? error.message : 'Lưu cơ sở thất bại') }
    finally { setSaving(false) }
  }
  const confirmDelete = async () => {
    if (!deleteTarget) return
    setSaving(true); setMessage('')
    try {
      await deleteAcademicCampus(jsonHeaders, deleteTarget.id)
      setMessage(`Đã xóa cơ sở ${codeLabel(deleteTarget.campus_code)}`)
      setDeleteTarget(null)
      await load()
    } catch (error) { setMessage(error instanceof Error ? error.message : 'Xóa cơ sở thất bại') }
    finally { setSaving(false) }
  }

  const columns: EnterpriseTableColumn<AcademicCampus>[] = [
    { key: 'stt', header: 'STT', kind: 'index', width: 52, hideable: false, render: (_item, index) => index + 1 },
    { key: 'campus', header: 'Cơ sở', kind: 'identity', minWidth: 240, hideable: false, render: (item) => <div><b>{codeLabel(item.campus_code)} · {item.campus_name || 'Chưa có tên'}</b><small>{branchLabel(item.branch)}</small></div> },
    { key: 'branch', header: 'Hệ', kind: 'status', width: 90, priority: 'optional', hideable: true, defaultVisible: false, render: (item) => branchLabel(item.branch) },
    { key: 'status', header: 'Trạng thái', kind: 'status', width: 112, hideable: true, render: (item) => <StatusBadge status={item.active ? 'active' : 'inactive'} label={item.active ? 'Đang dùng' : 'Đã xóa'} /> },
    { key: 'actions', header: 'Thao tác', kind: 'actions', width: 112, sticky: 'right', hideable: false, render: (item) => <div className="row-actions"><button className="btn small secondary" type="button" onClick={() => edit(item)}>Sửa</button><button className="btn small danger secondary-danger" type="button" disabled={saving} onClick={() => setDeleteTarget(item)}>Xóa</button></div> },
  ]

  if (!(can('manage_training_deadlines') || can('manage_settings'))) return null

  return <PageRoot className="page-stack premises-page">
    <PageHeader eyebrow="Danh mục" title="Cơ sở" secondaryActions={<button className="btn secondary" type="button" disabled={loading} onClick={load}>Làm mới</button>} primaryAction={<button className="btn" type="button" onClick={openCreate}>Thêm cơ sở</button>} />
    {message ? <div className="alert">{message}</div> : null}
    <OperationsKpiStrip items={[
      { label: 'Đang hiển thị', value: filtered.length, hint: `${items.length} cơ sở đã tải` },
      { label: 'Hệ', value: branchLabel(branch), hint: 'Phạm vi danh mục hiện tại' },
      { label: 'Trạng thái', value: activeFilter === 'all' ? 'Tất cả' : activeFilter === 'active' ? 'Đang dùng' : 'Đã xóa', hint: 'Bộ lọc hiện tại' },
    ]} />
    <CompactFilterBar actions={<button className="btn secondary" type="button" onClick={() => { setBranch('poly'); setActiveFilter('active'); setSearch('') }} disabled={branch === 'poly' && activeFilter === 'active' && !search}>Xóa lọc</button>}>
      <label>Hệ<select className="input" value={branch} onChange={(event) => setBranch(event.target.value)}><option value="poly">Poly</option><option value="ptcd">PTCĐ</option></select></label>
      <label>Trạng thái<select className="input" value={activeFilter} onChange={(event) => setActiveFilter(event.target.value as ActiveFilter)}><option value="active">Đang dùng</option><option value="inactive">Đã xóa</option><option value="all">Tất cả</option></select></label>
      <label>Tìm kiếm<input className="input" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Mã hoặc tên cơ sở..." /></label>
    </CompactFilterBar>
    <WorkspaceSection title="Danh sách cơ sở" description="Danh mục dùng cho đồng bộ AP và scope Chủ cơ sở.">
      <EnterpriseDataTable tableId="premises-v2" caption="Danh sách cơ sở" rows={filtered} columns={columns} rowKey={(item) => item.id} density="compact" loading={loading} label="cơ sở" emptyTitle="Chưa có cơ sở phù hợp" emptyDescription="Thay đổi bộ lọc hoặc thêm cơ sở mới." />
    </WorkspaceSection>
    {modalOpen ? <div className="modal-backdrop bank-popup-backdrop" onMouseDown={() => !saving && setModalOpen(false)}><div className="card bank-modal" onMouseDown={(event) => event.stopPropagation()}><div className="bank-modal-head"><div><div className="eyebrow">{editingId ? 'Sửa cơ sở' : 'Thêm mới cơ sở'}</div><h2>{editingId ? codeLabel(form.campus_code) : 'Cơ sở mới'}</h2></div><button className="btn small secondary" disabled={saving} onClick={() => setModalOpen(false)}>Đóng</button></div><div className="bank-modal-body"><div className="academic-modal-form"><label>Mã cơ sở<input className="input" value={form.campus_code} onChange={(event) => setForm((value) => ({ ...value, campus_code: event.target.value.toUpperCase() }))} placeholder="PT" /></label><label>Tên cơ sở<input className="input" value={form.campus_name} onChange={(event) => setForm((value) => ({ ...value, campus_name: event.target.value }))} placeholder="Thái Nguyên" /></label><label>Hệ<select className="input" value={form.branch} onChange={(event) => setForm((value) => ({ ...value, branch: event.target.value }))}><option value="poly">Poly</option><option value="ptcd">PTCĐ</option></select></label><label>Trạng thái<select className="input" value={form.active ? 'true' : 'false'} onChange={(event) => setForm((value) => ({ ...value, active: event.target.value === 'true' }))}><option value="true">Đang dùng</option><option value="false">Đã xóa</option></select></label></div><div className="modal-actions"><button className="btn" disabled={saving} onClick={save}>{saving ? 'Đang lưu...' : 'Lưu cơ sở'}</button><button className="btn secondary" disabled={saving} onClick={() => setModalOpen(false)}>Hủy</button></div></div></div></div> : null}
    {deleteTarget ? <div className="modal-backdrop bank-popup-backdrop" onMouseDown={() => !saving && setDeleteTarget(null)}><div className="card bank-modal academic-confirm-modal" onMouseDown={(event) => event.stopPropagation()}><div className="bank-modal-head"><div><div className="eyebrow danger-text">Xác nhận xóa</div><h2>Xóa cơ sở {codeLabel(deleteTarget.campus_code)}?</h2></div><button className="btn small secondary" disabled={saving} onClick={() => setDeleteTarget(null)}>Đóng</button></div><div className="bank-modal-body academic-confirm-body"><p>Cơ sở <b>{codeLabel(deleteTarget.campus_code)} · {deleteTarget.campus_name || 'Không có tên'}</b> sẽ bị chuyển sang trạng thái đã xóa và không còn xuất hiện trong dropdown đồng bộ AP.</p><div className="academic-confirm-summary"><span>Hệ</span><b>{branchLabel(deleteTarget.branch)}</b><span>Mã cơ sở</span><b>{codeLabel(deleteTarget.campus_code)}</b></div><div className="modal-actions"><button className="btn danger" disabled={saving} onClick={confirmDelete}>{saving ? 'Đang xóa...' : 'Xác nhận xóa'}</button><button className="btn secondary" disabled={saving} onClick={() => setDeleteTarget(null)}>Hủy</button></div></div></div></div> : null}
  </PageRoot>
}
