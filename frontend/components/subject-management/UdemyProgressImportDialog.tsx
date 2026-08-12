'use client'

import { useEffect, useMemo, useState } from 'react'
import { EnterpriseDataTable, type EnterpriseTableColumn } from '../table/EnterpriseDataTable'
import { AccessibleDialog } from '../ui/AccessibleDialog'
import { InlineNotice, noticeError, noticeInfo, noticeSuccess, noticeWarning } from '../ui/InlineNotice'
import { StatusBadge } from '../ui/StatusBadge'
import {
  createUdemyProgressImportJob,
  downloadUdemyProgressImportErrors,
  getUdemyProgressImportBatches,
  retryUdemyProgressImportBatch,
} from '../../lib/api'
import type { AcademicSubjectDelivery, UdemyProgressImportBatch, UdemyProgressImportJobResult } from '../../types'

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

function derivedJobStatus(batches: UdemyProgressImportBatch[]): string {
  if (batches.some((batch) => ['queued', 'running'].includes(batch.status))) return 'running'
  const completed = batches.filter((batch) => ['completed', 'skipped'].includes(batch.status)).length
  const failed = batches.filter((batch) => batch.status === 'failed').length
  if (failed && !completed) return 'failed'
  return 'completed'
}

function statusLabel(status: string) {
  if (status === 'queued') return 'Đang chờ'
  if (status === 'running') return 'Đang xử lý'
  if (status === 'completed') return 'Hoàn tất'
  if (status === 'failed') return 'Thất bại'
  if (status === 'skipped') return 'Bỏ qua file trùng'
  return status
}

export function UdemyProgressImportDialog({
  open,
  branch,
  termId,
  blockId,
  delivery,
  headers,
  onClose,
  onQueued,
}: {
  open: boolean
  branch: 'poly' | 'ptcd'
  termId: string
  blockId: string
  delivery?: AcademicSubjectDelivery | null
  headers: HeadersInit
  onClose: () => void
  onQueued: (result: UdemyProgressImportJobResult) => void
}) {
  const [files, setFiles] = useState<File[]>([])
  const [force, setForce] = useState(false)
  const [busy, setBusy] = useState(false)
  const [busyBatchId, setBusyBatchId] = useState('')
  const [error, setError] = useState('')
  const [result, setResult] = useState<UdemyProgressImportJobResult | null>(null)

  useEffect(() => {
    if (!open) return
    setFiles([])
    setForce(false)
    setBusy(false)
    setBusyBatchId('')
    setError('')
    setResult(null)
  }, [open, delivery?.id])

  useEffect(() => {
    if (!open || !result?.job_id || !['queued', 'running'].includes(result.status)) return
    let cancelled = false
    const refresh = async () => {
      try {
        const batches = await getUdemyProgressImportBatches(headers, { parentJobId: result.job_id, limit: 200 })
        if (cancelled || !batches.length) return
        setResult((current) => current && current.job_id === result.job_id
          ? { ...current, batches, status: derivedJobStatus(batches) }
          : current)
      } catch {
        // Dashboard continues tracking the parent job. A transient modal polling error must not stop import.
      }
    }
    void refresh()
    const timer = window.setInterval(refresh, 2000)
    return () => { cancelled = true; window.clearInterval(timer) }
  }, [headers, open, result?.job_id, result?.status])

  const close = () => { if (!busy && !busyBatchId) onClose() }

  const submit = async () => {
    if (!files.length || !termId || !blockId) return
    setBusy(true)
    setError('')
    try {
      const response = await createUdemyProgressImportJob(headers, {
        files,
        termId,
        blockId,
        branch,
        deliveryId: delivery?.id || null,
        forceReimport: force,
      })
      setResult(response)
      onQueued(response)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Không tạo được tác vụ import tiến độ Udemy.')
    } finally {
      setBusy(false)
    }
  }

  const retryBatch = async (batch: UdemyProgressImportBatch) => {
    setBusyBatchId(batch.id)
    setError('')
    try {
      const response = await retryUdemyProgressImportBatch(headers, batch.id)
      setResult(response)
      onQueued(response)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Không thể thử lại file Udemy.')
    } finally {
      setBusyBatchId('')
    }
  }

  const columns = useMemo<EnterpriseTableColumn<UdemyProgressImportBatch>[]>(() => [
    { key: 'stt', header: 'STT', kind: 'index', width: 54, render: (_row, index) => index + 1 },
    { key: 'subject', header: 'Môn', kind: 'identity', minWidth: 155, render: (batch) => <div><b>{batch.subject_code || '—'}</b><small>{batch.subject_name || ''}</small></div> },
    { key: 'file', header: 'File', kind: 'identity', minWidth: 250, render: (batch) => batch.file_name },
    { key: 'status', header: 'Trạng thái', kind: 'status', minWidth: 145, render: (batch) => <StatusBadge status={batch.status} label={statusLabel(batch.status)} /> },
    { key: 'matched', header: 'Đối chiếu AP', kind: 'number', minWidth: 120, render: (batch) => `${batch.matched_rows}/${batch.processed_rows}` },
    { key: 'issues', header: 'Cần kiểm tra', kind: 'number', width: 120, render: (batch) => batch.unmatched_rows + batch.ambiguous_rows + batch.outside_roster_rows + batch.failed_rows },
    { key: 'actions', header: 'Thao tác', kind: 'actions', minWidth: 170, sticky: 'right', render: (batch) => <div className="udemy-progress-row-actions">{batch.error_report_available ? <button className="btn small secondary" type="button" onClick={async () => { try { saveBlob(await downloadUdemyProgressImportErrors(headers, batch.id), `udemy-progress-errors-${batch.subject_code || batch.id}.xlsx`) } catch (err) { setError(err instanceof Error ? err.message : 'Không tải được file lỗi.') } }}>Tải file lỗi</button> : null}{batch.status === 'failed' ? <button className="btn small secondary" type="button" disabled={Boolean(busyBatchId)} onClick={() => void retryBatch(batch)}>{busyBatchId === batch.id ? 'Đang thử lại...' : 'Thử lại'}</button> : null}</div> },
  ], [busyBatchId, headers])

  const resultNotice = result
    ? result.status === 'failed'
      ? noticeError(result.message, 'Import Udemy thất bại.')
      : result.status === 'completed'
        ? noticeSuccess(result.message, 'Import đã hoàn tất')
        : noticeInfo(result.message, 'Đã xếp hàng import')
    : null

  return <AccessibleDialog
    open={open}
    title={delivery ? `Import tiến độ ${delivery.subject_code}` : 'Import điểm và tiến độ Udemy'}
    description={delivery ? `${delivery.subject_name} · ${delivery.term_name} · ${delivery.block_name}` : 'Import nhiều file theo tên MAMON_*.xlsx hoặc MAMON_*.csv trong đúng học kỳ và Block'}
    onClose={close}
    busy={busy || Boolean(busyBatchId)}
    size="xlarge"
    className="udemy-progress-import-dialog"
    bodyClassName="udemy-progress-import-body"
    footer={<div className="modal-actions">
      <button className="btn secondary" type="button" disabled={busy || Boolean(busyBatchId)} onClick={close}>{result ? 'Đóng' : 'Hủy'}</button>
      {!result ? <button className="btn" type="button" disabled={busy || !files.length || !termId || !blockId} onClick={() => void submit()}>{busy ? 'Đang tải file...' : 'Bắt đầu import'}</button> : null}
    </div>}
  >
    <InlineNotice notice={noticeInfo(delivery
      ? `File được gắn trực tiếp với môn ${delivery.subject_code}. Tác vụ chạy nền; F5 hoặc chuyển trang không làm mất tiến trình.`
      : 'Tên file phải bắt đầu bằng mã môn, ví dụ SOF3032_report.xlsx hoặc SOF3032_report.csv. Mỗi lần tối đa 50 file. Tác vụ tiếp tục chạy khi F5 hoặc chuyển trang.', 'Quy tắc import')} />
    <div className="udemy-progress-upload-panel">
      <label><b>File tiến độ Udemy</b><small>Hỗ trợ .xlsx/.csv export gốc Udemy theo header, kể cả file mới có cột “ID bên ngoài”, và file tổng hợp tiến độ 7 cột. Tối đa 20 MB/file.</small>
        <input className="input" type="file" accept=".xlsx,.csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,text/csv" multiple={!delivery} disabled={busy || Boolean(result)} onChange={(event) => { setFiles(Array.from(event.target.files || [])); setResult(null); setError('') }} />
      </label>
      <label className="udemy-progress-force"><input type="checkbox" checked={force} disabled={busy || Boolean(result)} onChange={(event) => setForce(event.target.checked)} /><span><b>Import lại có chủ đích</b><small>Cho phép xử lý lại cùng file SHA-256. Mặc định hệ thống bỏ qua file trùng.</small></span></label>
    </div>
    {files.length ? <div className="udemy-progress-file-list" aria-label="File đã chọn">{files.map((file) => <div key={`${file.name}-${file.size}`}><b>{file.name}</b><span>{(file.size / 1024 / 1024).toFixed(2)} MB</span></div>)}</div> : null}
    <InlineNotice notice={error ? noticeError(error) : null} />
    <InlineNotice notice={resultNotice} />
    {result ? <>
      <div className="summary-grid compact-summary" aria-label="Tổng kết import"><div><span>Xếp hàng</span><b>{result.queued_count}</b></div><div><span>File trùng</span><b>{result.duplicate_count}</b></div><div><span>Trạng thái</span><b>{statusLabel(result.status)}</b></div></div>
      {result.status === 'completed' && result.batches.some((batch) => batch.failed_rows || batch.unmatched_rows || batch.ambiguous_rows || batch.outside_roster_rows) ? <InlineNotice notice={noticeWarning('Một số dòng cần đối chiếu. Tải file lỗi ở cột Thao tác để xem chi tiết.', 'Có dữ liệu cần kiểm tra')} /> : null}
      <EnterpriseDataTable
        tableId="udemy-import-result-batch35-1"
        caption="Kết quả xử lý các file tiến độ Udemy"
        rows={result.batches}
        columns={columns}
        rowKey={(batch) => batch.id}
        density="compact"
        emptyTitle="Chưa có file được xử lý"
        label="file"
        stickyHorizontalScroll
      />
    </> : null}
  </AccessibleDialog>
}
