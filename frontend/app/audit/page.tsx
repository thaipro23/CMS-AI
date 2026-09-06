'use client'

import { Suspense, useCallback, useEffect, useMemo, useState } from 'react'
import { downloadAuditLogsCsv, getAuditLogs } from '../../lib/api'
import { useAppContext } from '../../context/AppContext'
import { AuditLogRow } from '../../types'
import { ActionMessage, ActionMessageData, toUserError } from '../../components/ui/ActionMessage'
import { StatusBadge } from '../../components/ui/StatusBadge'
import { PageRoot } from '../../components/layout/PageHeader'
import { EnterpriseScreenHeader } from '../../components/layout/EnterpriseDesignContract'
import { EnterpriseDataTable, EnterpriseTableColumn } from '../../components/table/EnterpriseDataTable'
import { useOpsTableState } from '../../hooks/useOpsTableState'
import { useDebouncedValue } from '../../lib/useDebouncedValue'
import { formatVNDateTime } from '../../lib/time'
import { userFacingError } from '../../lib/userFacingError'
import { CompactFilterBar, InfoPairGrid, OperationsKpiStrip, SideDrawer } from '../../components/operations/OperationsWorkspace'

const actionLabel: Record<string, string> = {
  'question_bank.material.upload.async': 'Tách tài liệu',
  'question_bank.material.upload.job': 'Đưa tài liệu vào hàng đợi xử lý',
  'question_bank.bank_version.generate.async': 'Tạo câu hỏi bằng AI',
  'question_bank.bank_version.generate.job': 'Đưa việc tạo câu hỏi vào hàng đợi',
  'question_bank.release.publish_openedx': 'Đưa bộ đề lên CMS',
  'question_bank.release.quiz.create': 'Tạo Quiz trên CMS',
  'question_bank.release.quiz.create.async': 'Tạo Quiz / Final test trên CMS',
  'question_bank.release.quiz.create.job': 'Đưa việc tạo bài kiểm tra vào hàng đợi',
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
function logMessage(row: AuditLogRow) {
  return row.status === 'failed'
    ? userFacingError(row.message, 'Tác vụ thất bại nhưng nhật ký cũ chưa lưu nguyên nhân. Mở Lịch sử Quiz để xem chi tiết bài kiểm tra.')
    : row.message || '—'
}
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
  const [selectedLog, setSelectedLog] = useState<AuditLogRow | null>(null)
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
    { key: 'stt', header: 'STT', kind: 'index', width: 52, sticky: 'left', hideable: false, render: (_row, index) => (page - 1) * pageSize + index + 1 },
    { key: 'actor', header: 'Người thực hiện', kind: 'identity', minWidth: 170, priority: 'required', hideable: false, render: (row) => <><b>{actorLabel(row)}</b><small>{row.actor_role || 'Không có vai trò'}</small></> },
    { key: 'action', header: 'Hành động', kind: 'identity', minWidth: 240, priority: 'required', hideable: false, render: (row) => <><b>{actionText(row.action)}</b>{debugMode ? <small>{row.action}</small> : <small>{row.target_type || 'Hệ thống'}</small>}</> },
    { key: 'status', header: 'Kết quả', kind: 'status', width: 110, priority: 'required', hideable: false, render: (row) => <StatusBadge status={row.status} /> },
    { key: 'created_at', header: 'Thời điểm', kind: 'date', width: 142, priority: 'important', hideable: true, render: (row) => <small>{formatVNDateTime(row.created_at)}</small> },
    { key: 'message', header: 'Nội dung', kind: 'text', minWidth: 240, priority: 'optional', hideable: true, defaultVisible: false, truncateLines: 2, render: (row) => <span className={row.status === 'failed' ? 'table-error-text' : ''}>{logMessage(row)}</span> },
    { key: 'error_type', header: 'Nguồn lỗi', kind: 'status', width: 130, priority: 'optional', hideable: true, defaultVisible: false, render: (row) => errorText(row.error_type) },
    { key: 'target', header: 'Đối tượng', kind: 'text', minWidth: 150, priority: 'optional', hideable: true, defaultVisible: false, render: (row) => <small>{targetLabel(row)}</small> },
    { key: 'actions', header: 'Thao tác', kind: 'actions', width: 92, sticky: 'right', hideable: false, render: (row) => <button className="btn small secondary" type="button" onClick={() => setSelectedLog(row)}>Chi tiết</button> },
  ], [debugMode, page, pageSize])

  if (!can('view_jobs')) return <PageRoot className="page-stack enterprise-standard-page ops-console audit-console"><EnterpriseScreenHeader eyebrow="Vận hành hệ thống" title="Nhật ký hoạt động" description="Tra cứu thao tác, kết quả, nguồn lỗi và người thực hiện để phục vụ audit và xử lý sự cố." icon="audit" tone="blue" breadcrumbs={[{ label: 'Vận hành hệ thống' }, { label: 'Nhật ký hoạt động' }]} /><section className="card empty-state">Bạn không có quyền xem nhật ký hoạt động.</section></PageRoot>
  const failedCount = rows.filter((row) => row.status === 'failed').length
  const successCount = rows.filter((row) => row.status === 'success').length
  const resetFilters = () => update({ q: '', status: 'all', errorType: 'all', actorId: '', page: 1 }, { resetPage: false })

  return <PageRoot className="page-stack enterprise-standard-page ops-console audit-console ux-enterprise-page">
    <EnterpriseScreenHeader
      eyebrow="Vận hành hệ thống"
      title="Nhật ký hoạt động"
      description="Tra cứu thao tác, kết quả, nguồn lỗi và người thực hiện để phục vụ audit và xử lý sự cố."
      icon="audit"
      tone="blue"
      breadcrumbs={[{ label: 'Vận hành hệ thống' }, { label: 'Nhật ký hoạt động' }]}
      secondaryActions={<button className="btn secondary" type="button" onClick={load} disabled={loading}>{loading ? 'Đang tải...' : 'Tải lại'}</button>}
      primaryAction={<button className="btn" type="button" onClick={exportCurrentFilter} disabled={exporting || loading}>{exporting ? 'Đang xuất...' : 'Xuất CSV'}</button>}
    />
    <ActionMessage message={message} onClose={() => setMessage(null)} />
    <OperationsKpiStrip items={[
      { label: 'Tổng theo bộ lọc', value: total, hint: `${totalPages} trang` },
      { label: 'Thành công', value: successCount, hint: 'Trên trang hiện tại', tone: 'success' },
      { label: 'Thất bại', value: failedCount, hint: failedCount ? 'Cần kiểm tra chi tiết' : 'Không có lỗi trên trang', tone: failedCount ? 'danger' : 'neutral' },
    ]} />
    <CompactFilterBar actions={<button className="btn secondary" type="button" onClick={resetFilters} disabled={!q && status === 'all' && errorType === 'all' && !actorId}>Xóa lọc</button>}>
      <label>Tìm nhanh<input className="input" value={q} onChange={(event) => update({ q: event.target.value })} placeholder="Hành động, nội dung, đối tượng..." /></label>
      <label>Trạng thái<select className="input" value={status} onChange={(event) => update({ status: event.target.value })}><option value="all">Tất cả</option><option value="success">Thành công</option><option value="failed">Thất bại</option></select></label>
      <label>Nguồn lỗi<select className="input" value={errorType} onChange={(event) => update({ errorType: event.target.value })}><option value="all">Tất cả</option><option value="USER_ERROR">Người dùng/cấu hình</option><option value="SYSTEM_ERROR">Hệ thống</option><option value="EXTERNAL_SERVICE_ERROR">Dịch vụ ngoài</option><option value="VALIDATION_ERROR">Dữ liệu đầu vào</option><option value="AUTH_ERROR">Phân quyền</option></select></label>
      <label>Người thực hiện<input className="input" value={actorId} onChange={(event) => update({ actorId: event.target.value })} placeholder="admin, system..." /></label>
    </CompactFilterBar>
    <EnterpriseDataTable tableId="ops-audit-v2" caption="Nhật ký hoạt động" rows={rows} columns={columns} rowKey={(row) => row.id} density={density} onDensityChange={(value) => update({ density: value }, { resetPage: false })} loading={loading} error={error} onRetry={load} emptyTitle="Không có log phù hợp" emptyDescription="Thử thay đổi từ khóa, trạng thái, nguồn lỗi hoặc người thực hiện." page={page} pageSize={pageSize} total={total} totalPages={totalPages} onPageChange={(value) => update({ page: value }, { resetPage: false })} onPageSizeChange={(value) => update({ pageSize: value, page: 1 }, { resetPage: false })} label="log" getRowClassName={(row) => `row-${row.status}`} />

    <SideDrawer open={Boolean(selectedLog)} title={selectedLog ? actionText(selectedLog.action) : 'Chi tiết nhật ký'} description={selectedLog ? formatVNDateTime(selectedLog.created_at) : undefined} onClose={() => setSelectedLog(null)}>
      {selectedLog ? <div className="page-stack compact-stack"><StatusBadge status={selectedLog.status} /><InfoPairGrid items={[
        { label: 'Người thực hiện', value: actorLabel(selectedLog) },
        { label: 'Vai trò', value: selectedLog.actor_role || '—' },
        { label: 'Nguồn lỗi', value: errorText(selectedLog.error_type) },
        { label: 'Đối tượng', value: targetLabel(selectedLog) },
        { label: 'Mã hành động', value: <code>{selectedLog.action}</code>, wide: true },
        { label: 'Nội dung', value: logMessage(selectedLog), wide: true },
      ]} /></div> : null}
    </SideDrawer>
  </PageRoot>
}

export default function AuditPage() {
  return <Suspense fallback={<div className="card">Đang tải nhật ký...</div>}><AuditContent /></Suspense>
}
