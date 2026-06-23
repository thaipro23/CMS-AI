'use client'

import { useEffect, useMemo, useState } from 'react'
import { getAuditLogs } from '../../lib/api'
import { useAppContext } from '../../context/AppContext'
import { AuditLogRow } from '../../types'
import { ActionMessage, ActionMessageData, toUserError } from '../../components/ui/ActionMessage'
import { PaginationControls } from '../../components/ui/PaginationControls'
import { StatusBadge } from '../../components/ui/StatusBadge'
import { formatVNDateTime } from '../../lib/time'

const actionLabel: Record<string, string> = {
  'question_bank.material.upload.async': 'Tách tài liệu',
  'question_bank.material.upload.job': 'Tạo job upload tài liệu',
  'question_bank.bank_version.generate.async': 'Tạo câu hỏi bằng AI',
  'question_bank.bank_version.generate.job': 'Tạo job generate',
  'question_bank.release.publish_openedx': 'Publish release',
  'question_bank.release.quiz.create': 'Tạo Quiz Open edX',
  'question_bank.version.question.review': 'Duyệt/Từ chối câu hỏi',
  'question_bank.version.question.update': 'Sửa câu hỏi',
  'rbac.assignment.create': 'Gán quyền',
  'rbac.assignment.revoke': 'Thu hồi quyền',
}
function actionText(value: string) { return actionLabel[value] || value.replace('question_bank.', 'Bank · ').replace('rbac.', 'Phân quyền · ') }
function errorText(v?: string | null) {
  return v === 'USER_ERROR' ? 'Do người dùng/cấu hình' : v === 'SYSTEM_ERROR' ? 'Do hệ thống' : v === 'EXTERNAL_SERVICE_ERROR' ? 'Dịch vụ ngoài' : v === 'VALIDATION_ERROR' ? 'Dữ liệu đầu vào' : v === 'AUTH_ERROR' ? 'Phân quyền' : '—'
}
function formatDate(value?: string | null) { return formatVNDateTime(value) }
function actorLabel(row: AuditLogRow) { return row.actor_id === 'system' ? 'Hệ thống' : row.actor_id || '—' }
function targetLabel(row: AuditLogRow) { return [row.target_type, row.target_id].filter(Boolean).join(' ') || '—' }

export default function AuditPage() {
  const { authHeaders, can } = useAppContext()
  const [rows, setRows] = useState<AuditLogRow[]>([])
  const [status, setStatus] = useState('all')
  const [errorType, setErrorType] = useState('all')
  const [actorId, setActorId] = useState('')
  const [query, setQuery] = useState('')
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [total, setTotal] = useState(0)
  const [totalPages, setTotalPages] = useState(1)
  const [loading, setLoading] = useState(false)
  const [message, setMessage] = useState<ActionMessageData | null>(null)

  async function load(nextPage = page, nextPageSize = pageSize) {
    setLoading(true)
    try {
      const d = await getAuditLogs('', { status, errorType, actorId, page: nextPage, pageSize: nextPageSize }, authHeaders())
      setRows(d.items || [])
      setTotal(d.total || 0)
      setPage(d.page || nextPage)
      setPageSize(d.page_size || nextPageSize)
      setTotalPages(d.total_pages || 1)
      setMessage(null)
    } catch (e) { setMessage(toUserError(e)) } finally { setLoading(false) }
  }
  useEffect(() => { setPage(1) }, [status, errorType, actorId])
  useEffect(() => { const t = window.setTimeout(() => load(page, pageSize), 250); return () => window.clearTimeout(t) }, [status, errorType, actorId, page, pageSize]) // eslint-disable-line react-hooks/exhaustive-deps

  const filteredRows = useMemo(() => {
    const needle = query.trim().toLowerCase()
    if (!needle) return rows
    return rows.filter((row) => [row.action, row.actor_id, row.actor_role, row.target_type, row.target_id, row.message, row.error_type, row.status].filter(Boolean).some((v) => String(v).toLowerCase().includes(needle)))
  }, [query, rows])
  const failedCount = rows.filter((r) => r.status === 'failed').length
  const successCount = rows.filter((r) => r.status === 'success').length

  if (!can('view_jobs')) return <div className="card empty-state">Bạn không có quyền xem nhật ký hoạt động.</div>
  return <div className="page-stack ops-console audit-console">
    <section className="ops-hero card">
      <div><span className="eyebrow">Audit scope</span><h1>Nhật ký hoạt động</h1><p>Nhật ký được trình bày dạng bảng để dễ lọc, dễ đọc và dễ đối soát. Backend đã lọc dữ liệu theo quyền.</p></div>
      <button className="btn secondary" onClick={() => load(1, pageSize)} disabled={loading}>{loading ? 'Đang tải...' : 'Làm mới'}</button>
    </section>
    <ActionMessage message={message} onClose={() => setMessage(null)} />
    <section className="ops-kpi-grid"><div><span>Tổng log trang này</span><b>{rows.length}</b></div><div><span>Thành công</span><b>{successCount}</b></div><div><span>Thất bại</span><b>{failedCount}</b></div><div><span>Đang xem</span><b>{total}</b></div></section>
    <section className="card ops-filter-card"><div className="grid grid-4"><label>Tìm nhanh<input className="input" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="hành động, người, nội dung..." /></label><label>Trạng thái<select className="input" value={status} onChange={(e) => setStatus(e.target.value)}><option value="all">Tất cả</option><option value="success">Thành công</option><option value="failed">Thất bại</option></select></label><label>Nguồn lỗi<select className="input" value={errorType} onChange={(e) => setErrorType(e.target.value)}><option value="all">Tất cả</option><option value="USER_ERROR">Do người dùng/cấu hình</option><option value="SYSTEM_ERROR">Do hệ thống</option><option value="EXTERNAL_SERVICE_ERROR">Dịch vụ ngoài</option><option value="VALIDATION_ERROR">Dữ liệu đầu vào</option><option value="AUTH_ERROR">Phân quyền</option></select></label><label>Người thực hiện<input className="input" value={actorId} onChange={(e) => setActorId(e.target.value)} placeholder="admin, system..." /></label></div></section>
    <section className="card"><PaginationControls page={page} pageSize={pageSize} total={total} totalPages={totalPages} onPageChange={setPage} onPageSizeChange={(s) => { setPageSize(s); setPage(1) }} loading={loading} label="log" />
      <div className="responsive-table-wrap"><table className="ops-data-table audit-data-table"><thead><tr><th>Thời điểm</th><th>Người thực hiện</th><th>Hành động</th><th>Kết quả</th><th>Nguồn lỗi</th><th>Đối tượng</th><th>Nội dung</th></tr></thead><tbody>{filteredRows.length ? filteredRows.map((row) => <tr key={row.id} className={`row-${row.status}`}><td><small>{formatDate(row.created_at)}</small></td><td><b>{actorLabel(row)}</b><small>{row.actor_role || '—'}</small></td><td><b>{actionText(row.action)}</b><small>{row.action}</small></td><td><StatusBadge status={row.status} /></td><td>{errorText(row.error_type)}</td><td><small>{targetLabel(row)}</small></td><td><span className={row.status === 'failed' ? 'table-error-text' : ''}>{row.message || 'Không có nội dung mô tả.'}</span></td></tr>) : <tr><td colSpan={7}><div className="empty-state">Không có log phù hợp với bộ lọc.</div></td></tr>}</tbody></table></div>
    </section>
  </div>
}
