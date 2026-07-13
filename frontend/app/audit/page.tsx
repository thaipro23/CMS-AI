'use client'

import { Suspense, useCallback, useEffect, useMemo, useState } from 'react'
import { downloadAuditLogsCsv, getAuditLogs } from '../../lib/api'
import { useAppContext } from '../../context/AppContext'
import { AuditLogRow } from '../../types'
import { ActionMessage, ActionMessageData, toUserError } from '../../components/ui/ActionMessage'
import { StatusBadge } from '../../components/ui/StatusBadge'
import { PageHeader } from '../../components/layout/PageHeader'
import { EnterpriseDataTable, EnterpriseTableColumn } from '../../components/table/EnterpriseDataTable'
import { useOpsTableState } from '../../hooks/useOpsTableState'
import { useDebouncedValue } from '../../lib/useDebouncedValue'
import { formatVNDateTime } from '../../lib/time'

const actionLabel: Record<string, string> = {
  'question_bank.material.upload.async': 'Tách tài liệu',
  'question_bank.material.upload.job': 'Đưa tài liệu vào hàng đợi xử lý',
  'question_bank.bank_version.generate.async': 'Tạo câu hỏi bằng AI',
  'question_bank.bank_version.generate.job': 'Đưa việc tạo câu hỏi vào hàng đợi',
  'question_bank.release.publish_openedx': 'Đưa bộ đề lên CMS',
  'question_bank.release.quiz.create': 'Tạo Quiz trên CMS',
  'academic.sync.ap.job': 'Đưa đồng bộ AP vào hàng đợi',
  'academic.sync.ap.run': 'Chạy đồng bộ AP',
  'academic.class_sync.async': 'Đồng bộ lớp/CMS',
  'academic.class_sync.job': 'Đưa đồng bộ lớp vào hàng đợi',
  'academic.learning_sync.job': 'Đưa cập nhật điểm vào hàng đợi',
  'analytics.ingest.job': 'Đưa ingest học online vào hàng đợi',
  'analytics.learning_behavior.job': 'Đưa tính lại học online vào hàng đợi',
  'analytics.learning_behavior.recalculate': 'Tính lại học online',
  'question_bank.version.question.review': 'Duyệt/Từ chối câu hỏi',
  'question_bank.version.question.update': 'Sửa câu hỏi',
  'rbac.assignment.create': 'Gán quyền',
  'rbac.assignment.revoke': 'Thu hồi quyền',
}
function actionText(value: string) { return actionLabel[value] || value.replace('question_bank.', 'Bank · ').replace('academic.', 'Đào tạo · ').replace('analytics.', 'Học online · ').replace('rbac.', 'Phân quyền · ') }
function errorText(value?: string | null) {
  return value === 'USER_ERROR' ? 'Do người dùng/cấu hình' : value === 'SYSTEM_ERROR' ? 'Do hệ thống' : value === 'EXTERNAL_SERVICE_ERROR' ? 'Dịch vụ ngoài' : value === 'VALIDATION_ERROR' ? 'Dữ liệu đầu vào' : value === 'AUTH_ERROR' ? 'Phân quyền' : '—'
}
function actorLabel(row: AuditLogRow) { return row.actor_id === 'system' ? 'Hệ thống' : row.actor_id || '—' }
function targetLabel(row: AuditLogRow) { return [row.target_type, row.target_id].filter(Boolean).join(' ') || '—' }
function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  window.setTimeout(() => URL.revokeObjectURL(url), 1000)
}

function AuditContent() {
  const { authHeaders, can } = useAppContext()
  const headers = useMemo(() => authHeaders(), [authHeaders])
  const { state, update } = useOpsTableState({ pageSize: 20 })
  const { q, status, errorType, actorId, page, pageSize, density } = state
  const debouncedQuery = useDebouncedValue(q, 350)
  const [rows, setRows] = useState<AuditLogRow[]>([])
  const [total, setTotal] = useState(0)
  const [totalPages, setTotalPages] = useState(1)
  const [loading, setLoading] = useState(false)
  const [exporting, setExporting] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState<ActionMessageData | null>(null)
  const debugMode = typeof window !== 'undefined' && new URLSearchParams(window.location.search).get('debug') === '1'

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const data = await getAuditLogs('', { status, errorType, actorId, search: debouncedQuery, page, pageSize }, headers)
      const nextTotalPages = Math.max(1, data.total_pages || 1)
      setRows(data.items || [])
      setTotal(data.total || 0)
      setTotalPages(nextTotalPages)
      if (page > nextTotalPages) update({ page: nextTotalPages }, { resetPage: false })
      else if (data.page && data.page !== page) update({ page: data.page }, { resetPage: false })
      setMessage(null)
    } catch (err) {
      const userError = toUserError(err)
      setError(userError.body || userError.title || "Không tải được nhật ký.")
      setMessage(userError)
    } finally {
      setLoading(false)
    }
  }, [actorId, debouncedQuery, errorType, headers, page, pageSize, status, update])

  useEffect(() => { load() }, [load])

  const exportCurrentFilter = async () => {
    setExporting(true)
    try {
      const blob = await downloadAuditLogsCsv({ status, errorType, actorId, search: debouncedQuery }, headers)
      downloadBlob(blob, 'audit-current-filter.csv')
    } catch (err) {
      setMessage(toUserError(err))
    } finally {
      setExporting(false)
    }
  }

  const columns = useMemo<EnterpriseTableColumn<AuditLogRow>[]>(() => [
    { key: 'stt', header: 'STT', width: 72, sticky: 'left', stickyOffset: 0, hideable: false, render: (_row, index) => (page - 1) * pageSize + index + 1 },
    { key: 'created_at', header: 'Thời điểm', minWidth: 150, render: (row) => <small>{formatVNDateTime(row.created_at)}</small> },
    { key: 'actor', header: 'Người thực hiện', minWidth: 170, render: (row) => <><b>{actorLabel(row)}</b><small>{row.actor_role || '—'}</small></> },
    { key: 'action', header: 'Hành động', minWidth: 220, render: (row) => <><b>{actionText(row.action)}</b>{debugMode ? <small>{row.action}</small> : null}</> },
    { key: 'status', header: 'Kết quả', minWidth: 120, render: (row) => <StatusBadge status={row.status} /> },
    { key: 'error_type', header: 'Nguồn lỗi', minWidth: 150, hideable: true, render: (row) => errorText(row.error_type) },
    { key: 'target', header: 'Đối tượng', minWidth: 170, hideable: true, render: (row) => <small>{debugMode ? targetLabel(row) : (row.target_type || '—')}</small> },
    { key: 'message', header: 'Nội dung', minWidth: 300, render: (row) => <span className={row.status === 'failed' ? 'table-error-text' : ''}>{row.message || 'Không có nội dung mô tả.'}</span> },
  ], [debugMode, page, pageSize])

  if (!can('view_jobs')) return <div className="card empty-state">Bạn không có quyền xem nhật ký hoạt động.</div>
  const failedCount = rows.filter((row) => row.status === 'failed').length
  const successCount = rows.filter((row) => row.status === 'success').length

  return <div className="page-stack ops-console audit-console ux-enterprise-page">
    <PageHeader
      eyebrow="Vận hành hệ thống"
      title="Nhật ký hoạt động"
      description="Tra cứu lịch sử thao tác theo đúng phạm vi RBAC. Bộ lọc, phân trang và mật độ bảng được lưu trong URL."
      secondaryActions={<button className="btn secondary" type="button" onClick={load} disabled={loading}>{loading ? 'Đang tải...' : 'Tải lại'}</button>}
      primaryAction={<button className="btn" type="button" onClick={exportCurrentFilter} disabled={exporting || loading}>{exporting ? 'Đang xuất...' : 'Xuất CSV'}</button>}
    />
    <ActionMessage message={message} onClose={() => setMessage(null)} />
    <section className="ops-kpi-grid"><div><span>Tổng theo bộ lọc</span><b>{total}</b></div><div><span>Thành công trên trang</span><b>{successCount}</b></div><div><span>Thất bại trên trang</span><b>{failedCount}</b></div><div><span>Trang hiện tại</span><b>{page}/{totalPages}</b></div></section>
    <section className="card ops-filter-card"><div className="grid grid-4">
      <label>Tìm nhanh<input className="input" value={q} onChange={(event) => update({ q: event.target.value })} placeholder="hành động, người, nội dung..." /></label>
      <label>Trạng thái<select className="input" value={status} onChange={(event) => update({ status: event.target.value })}><option value="all">Tất cả</option><option value="success">Thành công</option><option value="failed">Thất bại</option></select></label>
      <label>Nguồn lỗi<select className="input" value={errorType} onChange={(event) => update({ errorType: event.target.value })}><option value="all">Tất cả</option><option value="USER_ERROR">Do người dùng/cấu hình</option><option value="SYSTEM_ERROR">Do hệ thống</option><option value="EXTERNAL_SERVICE_ERROR">Dịch vụ ngoài</option><option value="VALIDATION_ERROR">Dữ liệu đầu vào</option><option value="AUTH_ERROR">Phân quyền</option></select></label>
      <label>Người thực hiện<input className="input" value={actorId} onChange={(event) => update({ actorId: event.target.value })} placeholder="admin, system..." /></label>
    </div></section>
    <EnterpriseDataTable tableId="ops-audit" caption="Nhật ký hoạt động" rows={rows} columns={columns} rowKey={(row) => row.id} density={density} onDensityChange={(value) => update({ density: value }, { resetPage: false })} loading={loading} error={error} onRetry={load} emptyTitle="Không có log phù hợp" emptyDescription="Thử thay đổi từ khóa, trạng thái, nguồn lỗi hoặc người thực hiện." page={page} pageSize={pageSize} total={total} totalPages={totalPages} onPageChange={(value) => update({ page: value }, { resetPage: false })} onPageSizeChange={(value) => update({ pageSize: value, page: 1 }, { resetPage: false })} label="log" getRowClassName={(row) => `row-${row.status}`} />
  </div>
}

export default function AuditPage() {
  return <Suspense fallback={<div className="card">Đang tải nhật ký...</div>}><AuditContent /></Suspense>
}
