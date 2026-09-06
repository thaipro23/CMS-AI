'use client'

import { useEffect, useMemo, useState } from 'react'
import { EnterpriseDataTable, type EnterpriseTableColumn } from '../table/EnterpriseDataTable'
import { AccessibleDialog } from '../ui/AccessibleDialog'
import { InlineNotice, noticeError, noticeInfo, noticeSuccess, noticeWarning } from '../ui/InlineNotice'
import { StatusBadge } from '../ui/StatusBadge'
import {
  createUdemyProgressImportJob,
  downloadUdemyProgressImportErrors,
  getAcademicBlocks,
  getUdemyProgressImportBatches,
  retryUdemyProgressImportBatch,
} from '../../lib/api'
import type {
  AcademicBlock,
  AcademicSubjectDelivery,
  UdemyProgressImportBatch,
  UdemyProgressImportJobResult,
  UdemyProgressImportRejectedFile,
} from '../../types'

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

function rejectionLabel(code: string) {
  if (code === 'SUBJECT_CODE_MISMATCH') return 'Sai mã môn'
  if (code === 'TERM_MISMATCH') return 'Sai học kỳ'
  if (code === 'BRANCH_MISMATCH') return 'Sai hệ'
  if (code === 'DELIVERY_NOT_FOUND') return 'Không có môn trong Block'
  if (code === 'NOT_UDEMY') return 'Môn không dùng Udemy'
  if (code === 'FILE_TOO_LARGE') return 'File quá lớn'
  if (code === 'UNSUPPORTED_FILE') return 'Không hỗ trợ'
  return 'Không hợp lệ'
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
  const [blocks, setBlocks] = useState<AcademicBlock[]>([])
  const [selectedBlockId, setSelectedBlockId] = useState(blockId)
  const effectiveBlockId = delivery?.block_id || blockId || selectedBlockId

  useEffect(() => {
    if (!open) return
    setFiles([])
    setForce(false)
    setBusy(false)
    setBusyBatchId('')
    setError('')
    setResult(null)
    setSelectedBlockId(blockId)
  }, [open, delivery?.id, blockId])

  useEffect(() => {
    if (!open || delivery || !termId) return
    let cancelled = false
    getAcademicBlocks(headers, termId)
      .then((items) => {
        if (cancelled) return
        const active = items.filter((item) => item.active !== false)
        setBlocks(active)
        setSelectedBlockId((current) => active.some((item) => item.id === current) ? current : active[0]?.id || '')
      })
      .catch((err) => {
        if (!cancelled) {
          setBlocks([])
          setSelectedBlockId('')
          setError(err instanceof Error ? err.message : 'Không tải được danh sách Block.')
        }
      })
    return () => { cancelled = true }
  }, [delivery, headers, open, termId])

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
        // Dashboard/Jobs continues tracking the parent job. A transient modal poll error must not stop import.
      }
    }
    void refresh()
    const timer = window.setInterval(refresh, 2000)
    return () => { cancelled = true; window.clearInterval(timer) }
  }, [headers, open, result?.job_id, result?.status])

  const close = () => { if (!busy && !busyBatchId) onClose() }

  const submit = async () => {
    if (!files.length || !termId || !effectiveBlockId) return
    setBusy(true)
    setError('')
    try {
      const response = await createUdemyProgressImportJob(headers, {
        files,
        termId,
        blockId: effectiveBlockId,
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

  const rejectedColumns = useMemo<EnterpriseTableColumn<UdemyProgressImportRejectedFile>[]>(() => [
    { key: 'stt', header: 'STT', kind: 'index', width: 54, render: (_row, index) => index + 1 },
    { key: 'file', header: 'File bị loại', kind: 'identity', minWidth: 280, render: (item) => <div><b>{item.file_name}</b><small>{item.source_archive ? `Trong ${item.source_archive}` : ''}</small></div> },
    { key: 'reason', header: 'Lý do', kind: 'status', minWidth: 150, render: (item) => <StatusBadge status="warning" label={rejectionLabel(item.reason_code)} /> },
    { key: 'detected', header: 'Nhận diện', kind: 'text', minWidth: 160, render: (item) => <div><b>{item.detected_subject_code || '—'}</b><small>{item.detected_term_code || ''}</small></div> },
    { key: 'message', header: 'Chi tiết', kind: 'text', minWidth: 380, render: (item) => item.message },
  ], [])

  const resultNotice = result
    ? result.status === 'failed'
      ? noticeError(result.message, 'Import Udemy thất bại.')
      : result.status === 'completed'
        ? noticeSuccess(result.message, 'Import đã hoàn tất')
        : noticeInfo(result.message, 'Đã xếp hàng import')
    : null

  return <AccessibleDialog
    open={open}
    title={delivery ? `Import tiến độ ${delivery.subject_code}` : 'Import hàng loạt Udemy'}
    description={delivery
      ? `${delivery.subject_name} · ${delivery.term_name} · ${delivery.block_name}`
      : 'Chọn nhiều CSV/XLSX hoặc tải một ZIP chứa nhiều báo cáo. Hệ thống tự map theo mã môn và vẫn giữ phạm vi học kỳ + Block.'}
    onClose={close}
    busy={busy || Boolean(busyBatchId)}
    size="xlarge"
    className="udemy-progress-import-dialog"
    bodyClassName="udemy-progress-import-body"
    footer={<div className="modal-actions">
      <button className="btn secondary" type="button" disabled={busy || Boolean(busyBatchId)} onClick={close}>{result ? 'Đóng' : 'Hủy'}</button>
      {!result ? <button className="btn" type="button" disabled={busy || !files.length || !termId || !effectiveBlockId} onClick={() => void submit()}>{busy ? 'Đang tải file...' : 'Bắt đầu import hàng loạt'}</button> : null}
    </div>}
  >
    <InlineNotice notice={noticeInfo(delivery
      ? `File được gắn trực tiếp với môn ${delivery.subject_code}. Bạn có thể xem tiến trình tại Tác vụ nền.`
      : 'Có thể chọn nhiều file cùng lúc hoặc một ZIP. File sai học kỳ, sai hệ, sai mã môn hoặc không thuộc Udemy sẽ bị loại riêng; các file hợp lệ vẫn tiếp tục.', 'Phạm vi nhập dữ liệu')} />
    <div className="udemy-progress-upload-panel">
      {!delivery ? <label><b>Block vận hành</b><small>Chọn Block cần cập nhật tiến độ.</small>
        <select className="input" value={effectiveBlockId} disabled={busy || Boolean(result)} onChange={(event) => setSelectedBlockId(event.target.value)}>
          {!blocks.length ? <option value="">Chưa có Block</option> : null}
          {blocks.map((item) => <option key={item.id} value={item.id}>{item.block_name}</option>)}
        </select>
      </label> : null}
      <label><b>File tiến độ Udemy</b><small>Hỗ trợ .xlsx/.csv, .zip và file tổng hợp tiến độ 7 cột. ZIP có thể chứa tối đa 50 báo cáo; mỗi báo cáo tối đa 20 MB. File mới có cột “ID bên ngoài” được hỗ trợ.</small>
        <input className="input" type="file" accept=".xlsx,.csv,.zip,application/zip,application/x-zip-compressed,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,text/csv" multiple={!delivery} disabled={busy || Boolean(result)} onChange={(event) => { setFiles(Array.from(event.target.files || [])); setResult(null); setError('') }} />
      </label>
      <label className="udemy-progress-force"><input type="checkbox" checked={force} disabled={busy || Boolean(result)} onChange={(event) => setForce(event.target.checked)} /><span><b>Import lại có chủ đích</b><small>Cho phép xử lý lại cùng file SHA-256. Mặc định hệ thống bỏ qua file trùng.</small></span></label>
    </div>
    {files.length ? <div className="udemy-progress-file-list" aria-label="File đã chọn">{files.map((file) => <div key={`${file.name}-${file.size}`}><b>{file.name}</b><span>{(file.size / 1024 / 1024).toFixed(2)} MB</span></div>)}</div> : null}
    <InlineNotice notice={error ? noticeError(error) : null} />
    <InlineNotice notice={resultNotice} />
    {result ? <>
      <div className="summary-grid compact-summary" aria-label="Tổng kết import"><div><span>Xếp hàng</span><b>{result.queued_count}</b></div><div><span>File trùng</span><b>{result.duplicate_count}</b></div><div><span>Bị loại</span><b>{result.rejected_count || 0}</b></div><div><span>Trạng thái</span><b>{statusLabel(result.status)}</b></div></div>
      {(result.rejected_count || 0) > 0 ? <>
        <InlineNotice notice={noticeWarning(`${result.rejected_count} file không được đưa vào hàng đợi. Các file hợp lệ vẫn được xử lý bình thường.`, 'Có file bị loại')} />
        <EnterpriseDataTable
          tableId="udemy-import-rejected-batch35-3-3"
          caption="Các file bị loại trước khi import"
          rows={result.rejected_files || []}
          columns={rejectedColumns}
          rowKey={(item) => `${item.source_archive || 'direct'}-${item.file_name}-${item.reason_code}`}
          density="compact"
          emptyTitle="Không có file bị loại"
          label="file"
          stickyHorizontalScroll
        />
      </> : null}
      {result.status === 'completed' && result.batches.some((batch) => batch.failed_rows || batch.unmatched_rows || batch.ambiguous_rows || batch.outside_roster_rows) ? <InlineNotice notice={noticeWarning('Một số dòng cần đối chiếu. Tải file lỗi ở cột Thao tác để xem chi tiết.', 'Có dữ liệu cần kiểm tra')} /> : null}
      <EnterpriseDataTable
        tableId="udemy-import-result-batch35-3-3"
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
