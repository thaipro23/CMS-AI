'use client'

import { useState } from 'react'
import type { BankQuestionImportPreview } from '../../../types'
import { downloadBankQuestionImportErrors, downloadBankQuestionImportTemplate, enqueueBankQuestionImport, previewBankQuestionImport } from '../../../lib/api'
import { Modal } from './shared'
import { ContentNotice } from '../../../components/ui/ContentNotice'

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

export function BankQuestionImportModal({ open, headers, bankVersionId, onClose, onQueued }: { open: boolean; headers: HeadersInit; bankVersionId: string; onClose: () => void; onQueued: (message: string) => void }) {
  const [file, setFile] = useState<File | null>(null)
  const [preview, setPreview] = useState<BankQuestionImportPreview | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const reset = () => { setFile(null); setPreview(null); setError(''); setBusy(false); onClose() }
  return <Modal open={open} title="Import câu hỏi từ Excel" onClose={reset} wide>
    <div className="bank-import-flow">
      <div className="bank-import-steps"><span className={!preview ? 'active' : 'done'}>1. Chọn file</span><span className={preview ? 'active' : ''}>2. Kiểm tra</span><span>3. Import nền</span></div>
      <p className="helper">Import không ghi dữ liệu ngay khi chọn file. Hệ thống kiểm tra toàn bộ dòng trước; câu hợp lệ được tạo ở trạng thái <b>Chờ duyệt</b>.</p>
      <div className="button-row"><button className="btn secondary" disabled={busy} onClick={async () => { try { setBusy(true); saveBlob(await downloadBankQuestionImportTemplate(headers, bankVersionId), 'bank-question-import-template.xlsx') } catch (e) { setError(e instanceof Error ? e.message : 'Không tải được file mẫu') } finally { setBusy(false) } }}>Tải file mẫu</button></div>
      <input className="input" type="file" accept=".xlsx" onChange={(event) => { setFile(event.target.files?.[0] || null); setPreview(null); setError('') }} />
      {error && <ContentNotice tone="danger">{error}</ContentNotice>}
      {!preview && <div className="modal-actions"><button className="btn secondary" onClick={reset}>Hủy</button><button className="btn" disabled={busy || !file} onClick={async () => { if (!file) return; try { setBusy(true); setError(''); setPreview(await previewBankQuestionImport(headers, bankVersionId, file)) } catch (e) { setError(e instanceof Error ? e.message : 'Không kiểm tra được file') } finally { setBusy(false) } }}>{busy ? 'Đang kiểm tra...' : 'Kiểm tra dữ liệu'}</button></div>}
      {preview && <>
        <div className="summary-grid compact-summary"><div><span>Tổng dòng</span><b>{preview.total_rows}</b></div><div><span>Hợp lệ</span><b>{preview.valid_count}</b></div><div><span>Dòng lỗi</span><b>{preview.error_count}</b></div></div>
        <ContentNotice tone={preview.can_commit ? "success" : "warning"}>{preview.message}</ContentNotice>
        {preview.errors.length > 0 && <>
          <div className="button-row no-margin"><button className="btn secondary" disabled={busy} onClick={async () => { try { setBusy(true); saveBlob(await downloadBankQuestionImportErrors(headers, bankVersionId, preview.preview_token), 'bank-question-import-errors.xlsx') } catch (e) { setError(e instanceof Error ? e.message : 'Không tải được file lỗi') } finally { setBusy(false) } }}>Tải file lỗi Excel</button></div>
          <div className="responsive-table-wrap"><table className="ops-data-table"><thead><tr><th>Dòng</th><th>Cột</th><th>Mã lỗi</th><th>Nội dung</th></tr></thead><tbody>{preview.errors.slice(0, 100).map((item, index) => <tr key={`${item.row}-${item.field}-${index}`}><td>{item.row || '—'}</td><td>{item.field || '—'}</td><td><code>{item.code || 'INVALID'}</code></td><td>{item.message || 'Dữ liệu không hợp lệ'}</td></tr>)}</tbody></table></div>
        </>}
        {preview.preview_rows.length > 0 && <details><summary>Xem trước tối đa 20 dòng</summary><div className="responsive-table-wrap"><table className="ops-data-table"><thead><tr><th>Dòng</th><th>Câu hỏi</th><th>Độ khó</th><th>Đáp án</th></tr></thead><tbody>{preview.preview_rows.map((row) => <tr key={String(row.row_no)}><td>{row.row_no}</td><td>{String(row.question_text || '')}</td><td>{String(row.difficulty || '')}</td><td>{String(row.correct_answer || '')}</td></tr>)}</tbody></table></div></details>}
        <div className="modal-actions"><button className="btn secondary" disabled={busy} onClick={() => { setPreview(null); setError('') }}>Chọn lại file</button><button className="btn" disabled={busy || !preview.can_commit} onClick={async () => { try { setBusy(true); const queued = await enqueueBankQuestionImport(headers, bankVersionId, preview.preview_token); onQueued(queued.message || 'Đã tạo tác vụ nền import câu hỏi.'); reset() } catch (e) { setError(e instanceof Error ? e.message : 'Không tạo được job import') } finally { setBusy(false) } }}>{busy ? 'Đang tạo job...' : 'Xác nhận import'}</button></div>
      </>}
    </div>
  </Modal>
}
