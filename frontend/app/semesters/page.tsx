'use client'

import { useEffect, useMemo, useState } from 'react'
import { useAppContext } from '../../context/AppContext'
import { getAcademicBlocks, getAcademicTerms, saveAcademicTerm } from '../../lib/api'
import { AcademicBlock, AcademicTerm } from '../../types'

type Branch = 'poly' | 'ptcd'
type ActiveFilter = 'active' | 'inactive' | 'all'

type BlockForm = {
  id?: string | null
  block_code: string
  block_name: string
  start_date: string
  end_date: string
  sort_order: number
  active: boolean
}

type TermForm = {
  id?: string | null
  term_code: string
  term_name: string
  branch: Branch
  start_date: string
  end_date: string
  active: boolean
  blocks: BlockForm[]
}

const DEFAULT_BLOCKS: BlockForm[] = [
  { block_code: 'Block 1', block_name: 'Block 1', start_date: '', end_date: '', sort_order: 1, active: true },
  { block_code: 'Block 2', block_name: 'Block 2', start_date: '', end_date: '', sort_order: 2, active: true },
]

const EMPTY_FORM: TermForm = {
  term_code: 'Summer 2026',
  term_name: 'Summer 2026',
  branch: 'poly',
  start_date: '',
  end_date: '',
  active: true,
  blocks: DEFAULT_BLOCKS,
}

function branchLabel(branch?: string | null) {
  return (branch || '').toLowerCase() === 'ptcd' ? 'PTCĐ' : 'Poly'
}

function dateInput(value?: string | null) {
  if (!value) return ''
  return String(value).slice(0, 10)
}

function toIsoDate(value: string) {
  return value ? `${value}T00:00:00` : null
}

function formatDate(value?: string | null) {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return String(value).slice(0, 10)
  return date.toLocaleDateString('vi-VN')
}

function sourceLabel(item: AcademicTerm) {
  const source = item.metadata_json?.source
  if (source === 'acms_html_semester') return 'Import từ ACMS'
  if (source === 'manual_ui') return 'Nhập tay'
  if (source === 'ap') return 'AP sync'
  return source || '—'
}

export default function SemestersPage() {
  const { authHeaders, can } = useAppContext()
  const headers = useMemo(() => authHeaders(), [authHeaders])
  const jsonHeaders = useMemo(() => authHeaders(true), [authHeaders])

  const [items, setItems] = useState<Array<AcademicTerm & { blocks?: AcademicBlock[] }>>([])
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState('')
  const [branch, setBranch] = useState<Branch>('poly')
  const [activeFilter, setActiveFilter] = useState<ActiveFilter>('active')
  const [search, setSearch] = useState('')
  const [modalOpen, setModalOpen] = useState(false)
  const [form, setForm] = useState<TermForm>({ ...EMPTY_FORM })

  const load = async () => {
    setLoading(true)
    setMessage('')
    try {
      const active = activeFilter === 'all' ? null : activeFilter === 'active'
      const terms = await getAcademicTerms(headers, { branch, active })
      const enriched = await Promise.all(terms.map(async (term) => {
        try {
          const blocks = await getAcademicBlocks(headers, term.id)
          return { ...term, blocks }
        } catch {
          return { ...term, blocks: [] }
        }
      }))
      setItems(enriched)
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Không tải được danh sách học kỳ')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [headers, branch, activeFilter])

  const filtered = items.filter((item) => {
    const q = search.trim().toLowerCase()
    if (!q) return true
    return [item.term_code, item.term_name, item.branch, sourceLabel(item)]
      .some((value) => String(value || '').toLowerCase().includes(q))
  })

  const openCreate = () => {
    setForm({ ...EMPTY_FORM, branch, blocks: DEFAULT_BLOCKS.map((item) => ({ ...item })) })
    setModalOpen(true)
  }

  const openEdit = (term: AcademicTerm & { blocks?: AcademicBlock[] }) => {
    const blocks = (term.blocks?.length ? term.blocks : []).map((block) => ({
      id: block.id,
      block_code: block.block_code,
      block_name: block.block_name,
      start_date: dateInput(block.start_date),
      end_date: dateInput(block.end_date),
      sort_order: block.sort_order || 0,
      active: block.active,
    }))
    setForm({
      id: term.id,
      term_code: term.term_code,
      term_name: term.term_name,
      branch: (term.branch || 'poly') as Branch,
      start_date: dateInput(term.start_date),
      end_date: dateInput(term.end_date),
      active: term.active,
      blocks: blocks.length ? blocks : DEFAULT_BLOCKS.map((item) => ({ ...item })),
    })
    setModalOpen(true)
  }

  const updateBlock = (index: number, patch: Partial<BlockForm>) => {
    setForm((value) => ({ ...value, blocks: value.blocks.map((block, i) => i === index ? { ...block, ...patch } : block) }))
  }

  const addBlock = () => {
    setForm((value) => ({ ...value, blocks: [...value.blocks, { block_code: `Block ${value.blocks.length + 1}`, block_name: `Block ${value.blocks.length + 1}`, start_date: '', end_date: '', sort_order: value.blocks.length + 1, active: true }] }))
  }

  const save = async () => {
    if (!form.term_code.trim()) { setMessage('Thiếu mã học kỳ'); return }
    if (!form.term_name.trim()) { setMessage('Thiếu tên học kỳ'); return }
    if (!form.blocks.length) { setMessage('Cần ít nhất 1 block'); return }
    setSaving(true)
    setMessage('')
    try {
      await saveAcademicTerm(jsonHeaders, {
        id: form.id,
        term_code: form.term_code.trim(),
        term_name: form.term_name.trim(),
        branch: form.branch,
        start_date: toIsoDate(form.start_date),
        end_date: toIsoDate(form.end_date),
        active: form.active,
        blocks: form.blocks.map((block, index) => ({
          id: block.id,
          block_code: block.block_code.trim(),
          block_name: block.block_name.trim() || block.block_code.trim(),
          start_date: toIsoDate(block.start_date),
          end_date: toIsoDate(block.end_date),
          sort_order: Number(block.sort_order || index + 1),
          active: block.active,
        })),
      })
      setMessage(`Đã lưu học kỳ ${form.term_code}`)
      setModalOpen(false)
      setBranch(form.branch)
      await load()
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Lưu học kỳ thất bại')
    } finally {
      setSaving(false)
    }
  }

  const toggleActive = async (item: AcademicTerm & { blocks?: AcademicBlock[] }) => {
    setSaving(true)
    setMessage('')
    try {
      await saveAcademicTerm(jsonHeaders, {
        id: item.id,
        term_code: item.term_code,
        term_name: item.term_name,
        branch: item.branch || branch,
        start_date: item.start_date,
        end_date: item.end_date,
        active: !item.active,
        blocks: (item.blocks || []).map((block) => ({
          id: block.id,
          block_code: block.block_code,
          block_name: block.block_name,
          start_date: block.start_date,
          end_date: block.end_date,
          sort_order: block.sort_order,
          active: block.active,
        })),
      })
      setMessage(`${!item.active ? 'Đã bật lại' : 'Đã ẩn'} học kỳ ${item.term_code}`)
      await load()
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Cập nhật trạng thái thất bại')
    } finally {
      setSaving(false)
    }
  }

  if (!can('manage_settings')) {
    return <div className="page-stack"><section className="hero-card compact-hero"><div><div className="eyebrow">Semesters</div><h1>Học kỳ</h1><p>Bạn không có quyền quản trị học kỳ.</p></div></section></div>
  }

  return <div className="page-stack semesters-page">
    <section className="hero-card compact-hero">
      <div>
        <div className="eyebrow">AP master data</div>
        <h1>Học kỳ & Block</h1>
        <p>Quản lý kỳ học và block kế hoạch học dùng cho đồng bộ AP. Thêm mới/chỉnh sửa bằng popup để thao tác nhanh như ACMS nhưng không rời trang.</p>
      </div>
      <div className="hero-actions">
        <button className="btn secondary" disabled={loading} onClick={load}>Làm mới</button>
        <button className="btn" onClick={openCreate}>Thêm học kỳ</button>
      </div>
    </section>

    {message ? <div className="alert">{message}</div> : null}

    <section className="card">
      <div className="section-head">
        <div><h2>Danh sách học kỳ</h2><p>{loading ? 'Đang tải...' : `${filtered.length} / ${items.length} học kỳ`}</p></div>
      </div>
      <div className="filter-grid academic-filter-grid">
        <label>Hệ
          <select className="input" value={branch} onChange={(event) => setBranch(event.target.value as Branch)}>
            <option value="poly">Poly</option>
            <option value="ptcd">PTCĐ</option>
          </select>
        </label>
        <label>Trạng thái
          <select className="input" value={activeFilter} onChange={(event) => setActiveFilter(event.target.value as ActiveFilter)}>
            <option value="active">Đang dùng</option>
            <option value="inactive">Đã ẩn</option>
            <option value="all">Tất cả</option>
          </select>
        </label>
        <label>Tìm kiếm
          <input className="input" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Summer 2026, Block 1..." />
        </label>
      </div>
      <div className="table-wrap" style={{ marginTop: 16 }}>
        <table className="data-table compact-table">
          <thead><tr><th>Hệ</th><th>Mã học kỳ</th><th>Tên học kỳ</th><th>Block</th><th>Nguồn</th><th>Trạng thái</th><th>Thao tác</th></tr></thead>
          <tbody>
            {filtered.map((item) => <tr key={item.id}>
              <td><b>{branchLabel(item.branch)}</b><small>{item.branch || 'poly'}</small></td>
              <td><b>{item.term_code}</b><small>{formatDate(item.start_date)} → {formatDate(item.end_date)}</small></td>
              <td>{item.term_name}</td>
              <td>{(item.blocks || []).filter((block) => block.active).map((block) => <div key={block.id} className="mini-row"><b>{block.block_name}</b><small>{formatDate(block.start_date)} → {formatDate(block.end_date)}</small></div>)}</td>
              <td><span className="status-pill neutral">{sourceLabel(item)}</span></td>
              <td><span className={item.active ? 'status-pill success' : 'status-pill warning'}>{item.active ? 'Đang dùng' : 'Đã ẩn'}</span></td>
              <td><div className="row-actions"><button className="btn small secondary" onClick={() => openEdit(item)}>Sửa</button><button className="btn small secondary" disabled={saving} onClick={() => toggleActive(item)}>{item.active ? 'Ẩn' : 'Bật lại'}</button></div></td>
            </tr>)}
            {!filtered.length ? <tr><td colSpan={7}><div className="empty-state">Chưa có học kỳ phù hợp.</div></td></tr> : null}
          </tbody>
        </table>
      </div>
    </section>

    {modalOpen ? <div className="modal-backdrop" onClick={() => !saving && setModalOpen(false)}>
      <div className="card bank-modal bank-modal-wide" onClick={(event) => event.stopPropagation()}>
        <div className="bank-modal-head">
          <div><div className="eyebrow">{form.id ? 'Sửa học kỳ' : 'Thêm mới học kỳ'}</div><h2>{form.id ? form.term_code : 'Học kỳ mới'}</h2></div>
          <button className="btn small secondary" disabled={saving} onClick={() => setModalOpen(false)}>Đóng</button>
        </div>
        <div className="bank-modal-body">
          <div className="filter-grid academic-filter-grid">
            <label>Hệ
              <select className="input" value={form.branch} onChange={(event) => setForm((value) => ({ ...value, branch: event.target.value as Branch }))}>
                <option value="poly">Poly</option>
                <option value="ptcd">PTCĐ</option>
              </select>
            </label>
            <label>Mã học kỳ
              <input className="input" value={form.term_code} onChange={(event) => setForm((value) => ({ ...value, term_code: event.target.value, term_name: value.term_name || event.target.value }))} placeholder="Summer 2026" />
            </label>
            <label>Tên học kỳ
              <input className="input" value={form.term_name} onChange={(event) => setForm((value) => ({ ...value, term_name: event.target.value }))} placeholder="Summer 2026" />
            </label>
            <label>Ngày bắt đầu kỳ
              <input className="input" type="date" value={form.start_date} onChange={(event) => setForm((value) => ({ ...value, start_date: event.target.value }))} />
            </label>
            <label>Ngày kết thúc kỳ
              <input className="input" type="date" value={form.end_date} onChange={(event) => setForm((value) => ({ ...value, end_date: event.target.value }))} />
            </label>
            <label>Trạng thái
              <select className="input" value={form.active ? 'true' : 'false'} onChange={(event) => setForm((value) => ({ ...value, active: event.target.value === 'true' }))}>
                <option value="true">Đang dùng</option>
                <option value="false">Ẩn</option>
              </select>
            </label>
          </div>
          <div className="section-head" style={{ marginTop: 18 }}><div><h3>Block/kế hoạch học</h3><p>ACMS cũ có Block 1 và Block 2; có thể thêm block nếu AP mở rộng.</p></div><button className="btn small secondary" onClick={addBlock}>Thêm block</button></div>
          <div className="table-wrap">
            <table className="data-table compact-table">
              <thead><tr><th>Mã block</th><th>Tên block</th><th>Bắt đầu</th><th>Kết thúc</th><th>Thứ tự</th><th>Trạng thái</th></tr></thead>
              <tbody>{form.blocks.map((block, index) => <tr key={`${block.id || 'new'}-${index}`}>
                <td><input className="input" value={block.block_code} onChange={(event) => updateBlock(index, { block_code: event.target.value })} /></td>
                <td><input className="input" value={block.block_name} onChange={(event) => updateBlock(index, { block_name: event.target.value })} /></td>
                <td><input className="input" type="date" value={block.start_date} onChange={(event) => updateBlock(index, { start_date: event.target.value })} /></td>
                <td><input className="input" type="date" value={block.end_date} onChange={(event) => updateBlock(index, { end_date: event.target.value })} /></td>
                <td><input className="input" type="number" value={block.sort_order} onChange={(event) => updateBlock(index, { sort_order: Number(event.target.value || index + 1) })} /></td>
                <td><select className="input" value={block.active ? 'true' : 'false'} onChange={(event) => updateBlock(index, { active: event.target.value === 'true' })}><option value="true">Đang dùng</option><option value="false">Ẩn</option></select></td>
              </tr>)}</tbody>
            </table>
          </div>
          <div className="modal-actions"><button className="btn" disabled={saving} onClick={save}>{saving ? 'Đang lưu...' : 'Lưu học kỳ'}</button><button className="btn secondary" disabled={saving} onClick={() => setModalOpen(false)}>Hủy</button></div>
        </div>
      </div>
    </div> : null}
  </div>
}
