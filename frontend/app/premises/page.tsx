'use client'

import { useEffect, useMemo, useState } from 'react'
import { useAppContext } from '../../context/AppContext'
import { deleteAcademicCampus, getAcademicCampuses, saveAcademicCampus, updateAcademicCampus } from '../../lib/api'
import { AcademicCampus } from '../../types'
import { PageRoot } from '../../components/layout/PageHeader'
import { EnterpriseScreenHeader } from '../../components/layout/EnterpriseDesignContract'
import { EnterpriseDataTable, type EnterpriseTableColumn } from '../../components/table/EnterpriseDataTable'
import { CompactFilterBar, OperationsKpiStrip, WorkspaceSection } from '../../components/operations/OperationsWorkspace'
import { StatusBadge } from '../../components/ui/StatusBadge'
import { AccessibleDialog } from '../../components/ui/AccessibleDialog'

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
  const canManageCampusCatalog = can('manage_settings')

  const load = async () => {
    setLoading(true); setMessage('')
    try {
      const active = activeFilter === 'all' ? null : activeFilter === 'active'
      setItems(await getAcademicCampuses(headers, { branch, active }))
    } catch (error) { setMessage(error instanceof Error ? error.message : 'Không tải được danh sách cơ sở') }
    finally { setLoading(false) }
  }
  useEffect(() => { if (canManageCampusCatalog) load() }, [canManageCampusCatalog, headers, branch, activeFilter])

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
      const payload = { campus_code: code, campus_name: name, branch: form.branch, active: form.active }
      const saved = editingId
        ? await updateAcademicCampus(jsonHeaders, editingId, payload)
        : await saveAcademicCampus(jsonHeaders, payload)
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

  if (!canManageCampusCatalog) return <PageRoot className="page-stack enterprise-standard-page premises-page"><EnterpriseScreenHeader eyebrow="Danh mục" title="Cơ sở" description="Danh mục cơ sở được nhập và chỉnh sửa thủ công tại đây." icon="campus" tone="blue" breadcrumbs={[{ label: 'Danh mục' }, { label: 'Cơ sở' }]} /><section className="card empty-state">Bạn không có quyền quản lý danh mục cơ sở.</section></PageRoot>

  return <PageRoot className="page-stack enterprise-standard-page premises-page">
    <EnterpriseScreenHeader eyebrow="Danh mục" title="Cơ sở" description="Nhập và chỉnh sửa thủ công danh mục cơ sở dùng cho đồng bộ AP và phạm vi vận hành đào tạo." icon="campus" tone="blue" breadcrumbs={[{ label: 'Danh mục' }, { label: 'Cơ sở' }]} secondaryActions={<button className="btn secondary" type="button" disabled={loading} onClick={load}>Làm mới</button>} primaryAction={<button className="btn" type="button" onClick={openCreate}>Thêm cơ sở thủ công</button>} />
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
    <WorkspaceSection title="Danh sách cơ sở" description="Danh mục được quản trị thủ công; hệ thống không lấy cơ sở từ AP.">
      <EnterpriseDataTable tableId="premises-v2" caption="Danh sách cơ sở" rows={filtered} columns={columns} rowKey={(item) => item.id} density="compact" loading={loading} label="cơ sở" emptyTitle="Chưa có cơ sở phù hợp" emptyDescription="Thay đổi bộ lọc hoặc thêm cơ sở mới." />
    </WorkspaceSection>
    <AccessibleDialog
      open={modalOpen}
      title={editingId ? `Sửa cơ sở ${codeLabel(form.campus_code)}` : 'Thêm cơ sở'}
      description="Nhập thủ công mã, tên và hệ của cơ sở. Cơ sở được dùng cho đồng bộ AP và phạm vi quản lý đào tạo."
      onClose={() => !saving && setModalOpen(false)}
      busy={saving}
      size="medium"
      footer={<div className="dialog-action-row"><button className="btn secondary" disabled={saving} onClick={() => setModalOpen(false)}>Hủy</button><button className="btn" data-dialog-autofocus disabled={saving} onClick={save}>{saving ? 'Đang lưu...' : 'Lưu cơ sở'}</button></div>}
    >
      <div className="academic-modal-form">
        <label>Mã cơ sở<input className="input" value={form.campus_code} onChange={(event) => setForm((value) => ({ ...value, campus_code: event.target.value.toUpperCase() }))} placeholder="PT" /></label>
        <label>Tên cơ sở<input className="input" value={form.campus_name} onChange={(event) => setForm((value) => ({ ...value, campus_name: event.target.value }))} placeholder="Thái Nguyên" /></label>
        <label>Hệ<select className="input" value={form.branch} onChange={(event) => setForm((value) => ({ ...value, branch: event.target.value }))}><option value="poly">Poly</option><option value="ptcd">PTCĐ</option></select></label>
        <label>Trạng thái<select className="input" value={form.active ? 'true' : 'false'} onChange={(event) => setForm((value) => ({ ...value, active: event.target.value === 'true' }))}><option value="true">Đang dùng</option><option value="false">Đã xóa</option></select></label>
      </div>
    </AccessibleDialog>
    <AccessibleDialog
      open={Boolean(deleteTarget)}
      title={`Xóa cơ sở ${deleteTarget ? codeLabel(deleteTarget.campus_code) : ''}?`}
      description="Thao tác này chỉ chuyển cơ sở sang trạng thái đã xóa; dữ liệu lịch sử được giữ nguyên."
      onClose={() => !saving && setDeleteTarget(null)}
      busy={saving}
      size="small"
      footer={<div className="dialog-action-row"><button className="btn secondary" disabled={saving} onClick={() => setDeleteTarget(null)}>Hủy</button><button className="btn danger" data-dialog-autofocus disabled={saving} onClick={confirmDelete}>{saving ? 'Đang xóa...' : 'Xác nhận xóa'}</button></div>}
    >
      {deleteTarget ? <div className="academic-confirm-body"><p>Cơ sở <b>{codeLabel(deleteTarget.campus_code)} · {deleteTarget.campus_name || 'Không có tên'}</b> sẽ không còn xuất hiện trong dropdown đồng bộ AP.</p><div className="academic-confirm-summary"><span>Hệ</span><b>{branchLabel(deleteTarget.branch)}</b><span>Mã cơ sở</span><b>{codeLabel(deleteTarget.campus_code)}</b></div></div> : null}
    </AccessibleDialog>
  </PageRoot>
}
