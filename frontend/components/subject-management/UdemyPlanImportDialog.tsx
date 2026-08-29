'use client'

import { useMemo, useState } from 'react'
import { EnterpriseDataTable, type EnterpriseTableColumn } from '../table/EnterpriseDataTable'
import { AccessibleDialog } from '../ui/AccessibleDialog'
import { InlineNotice, noticeError, noticeInfo, noticeSuccess, noticeWarning } from '../ui/InlineNotice'
import { StatusBadge } from '../ui/StatusBadge'
import {
  commitUdemyPlanImport,
  downloadUdemyPlanImportErrors,
  downloadUdemyPlanImportTemplate,
  previewUdemyPlanImport,
} from '../../lib/api'
import type { UdemyPlanImportIssue, UdemyPlanImportPreview, UdemyPlanImportPreviewRow } from '../../types'

function saveBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  URL.revokeObjectURL(url)
}

export function UdemyPlanImportDialog({
  open,
  branch,
  headers,
  jsonHeaders,
  onClose,
  onCommitted,
}: {
  open: boolean
  branch: 'poly' | 'ptcd'
  headers: HeadersInit
  jsonHeaders: HeadersInit
  onClose: () => void
  onCommitted: (message: string) => void
}) {
  const [file, setFile] = useState<File | null>(null)
  const [preview, setPreview] = useState<UdemyPlanImportPreview | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const reset = () => {
    if (busy) return
    setFile(null)
    setPreview(null)
    setError('')
    onClose()
  }

  const inspectFile = async () => {
    if (!file) return
    setBusy(true)
    setError('')
    try {
      setPreview(await previewUdemyPlanImport(headers, file, branch))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Không kiểm tra được file kế hoạch Udemy.')
    } finally { setBusy(false) }
  }

  const commit = async () => {
    if (!preview?.can_commit) return
    setBusy(true)
    setError('')
    try {
      const result = await commitUdemyPlanImport(jsonHeaders, preview.preview_token)
      onCommitted(result.message)
      setFile(null)
      setPreview(null)
      onClose()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Không import được kế hoạch Udemy.')
    } finally { setBusy(false) }
  }

  const issueColumns = useMemo<EnterpriseTableColumn<UdemyPlanImportIssue>[]>(() => [
    { key: 'stt', header: 'STT', kind: 'index', width: 54, render: (_row, index) => index + 1 },
    { key: 'row', header: 'Dòng', kind: 'number', width: 80, render: (item) => item.row || '—' },
    { key: 'subject', header: 'Môn', kind: 'identity', minWidth: 130, render: (item) => item.subject_code || '—' },
    { key: 'code', header: 'Mã lỗi', kind: 'status', minWidth: 150, render: (item) => <code>{item.code}</code> },
    { key: 'message', header: 'Nội dung', kind: 'text', minWidth: 320, render: (item) => item.message },
  ], [])

  const warningColumns = useMemo<EnterpriseTableColumn<UdemyPlanImportIssue>[]>(() => [
    { key: 'stt', header: 'STT', kind: 'index', width: 54, render: (_row, index) => index + 1 },
    { key: 'row', header: 'Dòng', kind: 'number', width: 80, render: (item) => item.row || '—' },
    { key: 'subject', header: 'Môn', kind: 'identity', minWidth: 130, render: (item) => item.subject_code || '—' },
    { key: 'message', header: 'Nội dung', kind: 'text', minWidth: 360, render: (item) => item.message },
  ], [])

  const previewColumns = useMemo<EnterpriseTableColumn<UdemyPlanImportPreviewRow>[]>(() => [
    { key: 'stt', header: 'STT', kind: 'index', width: 54, render: (_row, index) => index + 1 },
    { key: 'row', header: 'Dòng', kind: 'number', width: 75, render: (row) => row.row_no },
    { key: 'subject', header: 'Môn', kind: 'identity', minWidth: 200, render: (row) => <div><b>{row.subject_code}</b><small>{row.subject_name || ''}</small></div> },
    { key: 'scope', header: 'Học kỳ · Block', kind: 'text', minWidth: 185, render: (row) => <div>{row.term_name}<small>{row.block_name}</small></div> },
    { key: 'items', header: 'Item', kind: 'number', width: 80, render: (row) => row.item_count || '—' },
    { key: 'version', header: 'Phiên bản', kind: 'text', minWidth: 145, render: (row) => row.current_version ? `v${row.current_version} → v${row.next_version}` : `Tạo v${row.next_version}` },
    { key: 'milestones', header: 'Các mốc', kind: 'text', minWidth: 300, render: (row) => row.milestones.map((item) => `W${item.week_number}: ${item.required_progress_percent}%`).join(' · ') || '—' },
    { key: 'status', header: 'Trạng thái', kind: 'status', minWidth: 120, render: (row) => row.errors.length ? <StatusBadge status="failed" label="Có lỗi" /> : <StatusBadge status="success" label="Hợp lệ" /> },
  ], [])

  return <AccessibleDialog
    open={open}
    title="Import kế hoạch Udemy"
    description={`Hệ ${branch === 'ptcd' ? 'PTCĐ' : 'Poly'} · kiểm tra toàn bộ file trước khi ghi dữ liệu`}
    onClose={reset}
    busy={busy}
    size="xlarge"
    className="udemy-plan-import-dialog"
    bodyClassName="udemy-plan-import-body"
    footer={<div className="modal-actions">
      <button className="btn secondary" type="button" disabled={busy} onClick={preview ? () => { setPreview(null); setError('') } : reset}>{preview ? 'Chọn lại file' : 'Hủy'}</button>
      {!preview
        ? <button className="btn" type="button" disabled={busy || !file} onClick={() => void inspectFile()}>{busy ? 'Đang kiểm tra...' : 'Kiểm tra dữ liệu'}</button>
        : <button className="btn" type="button" disabled={busy || !preview.can_commit} onClick={() => void commit()}>{busy ? 'Đang import...' : 'Xác nhận import'}</button>}
    </div>}
  >
    <div className="udemy-plan-import-steps" aria-label="Các bước import"><span className={!preview ? 'active' : 'done'}>1. Chọn file</span><span className={preview ? 'active' : ''}>2. Kiểm tra</span><span>3. Tạo phiên bản</span></div>
    <InlineNotice notice={noticeInfo('Import lại sẽ tạo phiên bản kế hoạch mới; phiên bản cũ vẫn được giữ trong lịch sử. Chỉ môn đã chọn nền tảng Udemy mới được nhận.', 'Nguyên tắc tạo phiên bản')} />
    <div className="udemy-plan-upload-panel">
      <div><b>File Excel kế hoạch</b><small>Hỗ trợ .xlsx, tối đa 10 MB và 2.000 dòng.</small></div>
      <input className="input" type="file" accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" disabled={busy} aria-label="Chọn file Excel kế hoạch Udemy" onChange={(event) => { setFile(event.target.files?.[0] || null); setPreview(null); setError('') }} />
      <button className="btn secondary" type="button" disabled={busy} onClick={async () => {
        try { setBusy(true); saveBlob(await downloadUdemyPlanImportTemplate(headers), 'udemy-plan-import-template.xlsx') }
        catch (err) { setError(err instanceof Error ? err.message : 'Không tải được file mẫu.') }
        finally { setBusy(false) }
      }}>Tải file mẫu</button>
    </div>
    {file ? <div className="udemy-plan-selected-file"><b>{file.name}</b><span>{(file.size / 1024).toFixed(1)} KB</span></div> : null}
    <InlineNotice notice={error ? noticeError(error) : null} />

    {preview ? <>
      <div className="summary-grid compact-summary udemy-plan-preview-summary" aria-label="Kết quả kiểm tra file">
        <div><span>Tổng dòng</span><b>{preview.total_rows}</b></div>
        <div><span>Hợp lệ</span><b>{preview.valid_count}</b></div>
        <div><span>Lỗi</span><b>{preview.error_count}</b></div>
        <div><span>Cảnh báo</span><b>{preview.warning_count}</b></div>
      </div>
      <InlineNotice notice={preview.can_commit ? noticeSuccess(preview.message, 'File đủ điều kiện import') : noticeWarning(preview.message, 'File chưa thể import')} />
      {preview.errors.length ? <section className="udemy-plan-preview-section">
        <div className="workspace-section-heading"><div><h3>Lỗi cần sửa</h3><p>File chỉ được xác nhận khi không còn lỗi.</p></div><button className="btn small secondary" type="button" disabled={busy} onClick={async () => {
          try { setBusy(true); saveBlob(await downloadUdemyPlanImportErrors(headers, preview.preview_token), 'udemy-plan-import-errors.xlsx') }
          catch (err) { setError(err instanceof Error ? err.message : 'Không tải được file lỗi.') }
          finally { setBusy(false) }
        }}>Tải file lỗi</button></div>
        <EnterpriseDataTable tableId="udemy-plan-import-errors-batch35-1" caption="Lỗi trong file kế hoạch Udemy" rows={preview.errors.slice(0, 200)} columns={issueColumns} rowKey={(item) => `${item.row || 0}-${item.subject_code || ''}-${item.code}-${item.message}`} density="compact" label="lỗi" stickyHorizontalScroll />
      </section> : null}
      {preview.warnings.length ? <section className="udemy-plan-preview-section"><h3>Cảnh báo</h3><EnterpriseDataTable tableId="udemy-plan-import-warnings-batch35-1" caption="Cảnh báo trong file kế hoạch Udemy" rows={preview.warnings.slice(0, 100)} columns={warningColumns} rowKey={(item) => `${item.row || 0}-${item.subject_code || ''}-${item.code}-${item.message}`} density="compact" label="cảnh báo" stickyHorizontalScroll /></section> : null}
      <section className="udemy-plan-preview-section"><div className="workspace-section-heading"><div><h3>Xem trước kế hoạch</h3><p>Hiển thị tối đa 200 dòng đầu; toàn bộ dữ liệu hợp lệ vẫn được import.</p></div></div><EnterpriseDataTable tableId="udemy-plan-import-preview-batch35-1" caption="Xem trước kế hoạch Udemy" rows={preview.rows.slice(0, 200)} columns={previewColumns} rowKey={(row) => String(row.row_no)} density="compact" getRowClassName={(row) => row.errors.length ? 'row-invalid' : ''} label="dòng" stickyHorizontalScroll /></section>
    </> : null}
  </AccessibleDialog>
}
