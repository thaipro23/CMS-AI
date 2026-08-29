'use client'

import { useEffect, useMemo, useState } from 'react'
import type { BankOpenEdxImportPreview } from '../../../types'
import { importBankOpenEdxQuestions, previewBankOpenEdxImport } from '../../../lib/api'
import { Modal } from './shared'

function questionTypeLabel(value: string) {
  if (value === 'single_select') return 'Một đáp án'
  if (value === 'multi_select') return 'Nhiều đáp án'
  if (value === 'text_input') return 'Trả lời ngắn'
  if (value === 'numerical_input') return 'Trả lời số'
  return value || 'Không xác định'
}

export function BankOpenEdxImportModal({
  open,
  headers,
  bankVersionId,
  disabled = false,
  onClose,
  onImported,
}: {
  open: boolean
  headers: HeadersInit
  bankVersionId: string
  disabled?: boolean
  onClose: () => void
  onImported: (message: string) => void | Promise<void>
}) {
  const [olx, setOlx] = useState('')
  const [sourceRef, setSourceRef] = useState('openedx-olx-import')
  const [preview, setPreview] = useState<BankOpenEdxImportPreview | null>(null)
  const [busy, setBusy] = useState<'preview' | 'import' | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!open) {
      setPreview(null)
      setBusy(null)
      setError('')
    }
  }, [open])

  const typeCounts = useMemo(() => {
    const counts: Record<string, number> = {}
    for (const row of preview?.questions || []) {
      const type = String(row.question_type || 'unknown')
      counts[type] = (counts[type] || 0) + 1
    }
    return counts
  }, [preview])

  async function runPreview() {
    if (!olx.trim() || busy || disabled) return
    setBusy('preview')
    setError('')
    setPreview(null)
    try {
      const result = await previewBankOpenEdxImport(headers, bankVersionId, olx, sourceRef.trim() || 'openedx-olx-import')
      setPreview(result)
      if (!result.ok && result.errors.length) setError('OLX còn response không hợp lệ hoặc chưa được hỗ trợ. Hệ thống chưa ghi dữ liệu.')
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Không đọc được Open edX OLX.')
    } finally {
      setBusy(null)
    }
  }

  async function commitImport() {
    if (!preview?.ok || preview.invalid_count > 0 || busy || disabled) return
    setBusy('import')
    setError('')
    try {
      const result = await importBankOpenEdxQuestions(headers, bankVersionId, olx, sourceRef.trim() || 'openedx-olx-import')
      await onImported(result.message || `Đã import ${result.created_count} câu Open edX.`)
      setOlx('')
      setPreview(null)
      onClose()
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Import Open edX OLX thất bại. Không có dữ liệu lỗi nào được xác nhận là đã ghi.')
    } finally {
      setBusy(null)
    }
  }

  return <Modal open={open} title="Import câu hỏi từ Open edX OLX" onClose={() => { if (!busy) onClose() }} wide>
    <div className="bank-openedx-import-form">
      <div className="alert info"><b>Giữ nguyên semantics chấm điểm.</b> Hệ thống nhận Một đáp án, Nhiều đáp án, Trả lời ngắn và Trả lời số. Response Open edX chưa hỗ trợ sẽ bị chặn thay vì âm thầm đổi cách chấm.</div>
      <label>Nguồn tham chiếu<input className="input" disabled={Boolean(busy) || disabled} value={sourceRef} onChange={(event) => { setSourceRef(event.target.value); setPreview(null) }} placeholder="Ví dụ: course-v1:FPL+WEB107+SU26 / problem ..." /></label>
      <label>Problem OLX<textarea className="input openedx-olx-input" rows={13} disabled={Boolean(busy) || disabled} value={olx} onChange={(event) => { setOlx(event.target.value); setPreview(null); setError('') }} placeholder={'<problem>\n  <multiplechoiceresponse>...\n</problem>'} /></label>
      <p className="helper">Nếu OLX tham chiếu ảnh/static asset của Course cũ, response type vẫn được đọc nhưng ảnh không được sao chép mù. Hãy upload lại ảnh trong editor ACMS để asset thuộc đúng Question/Library mới.</p>

      {error ? <div className="alert danger" role="alert">{error}</div> : null}
      {preview ? <div className="openedx-import-preview">
        <div className="summary-grid compact-summary">
          <div><span>Đọc được</span><b>{preview.total_parsed}</b></div>
          <div><span>Hợp lệ</span><b>{preview.valid_count}</b></div>
          <div><span>Bị chặn</span><b>{preview.invalid_count}</b></div>
          <div><span>Một đáp án</span><b>{typeCounts.single_select || 0}</b></div>
          <div><span>Nhiều đáp án</span><b>{typeCounts.multi_select || 0}</b></div>
          <div><span>Text / Số</span><b>{(typeCounts.text_input || 0) + (typeCounts.numerical_input || 0)}</b></div>
        </div>
        {preview.warnings?.map((warning, index) => <div className="alert warning" key={`warning-${index}`}>{warning}</div>)}
        {preview.errors?.length ? <div className="alert danger"><b>Không thể import khi còn lỗi:</b><ul>{preview.errors.slice(0, 12).map((row, index) => <li key={`error-${index}`}>Câu {String(row.index ?? index + 1)} · {String(row.question_type || 'unknown')} · {String(row.error || 'Không hợp lệ')}</li>)}</ul></div> : null}
        {preview.questions?.length ? <div className="openedx-import-question-list">{preview.questions.slice(0, 20).map((row, index) => <div key={`${row.index || index}-${row.question_text || ''}`}><span className="soft-tag">{questionTypeLabel(String(row.question_type || ''))}</span><b>{String(row.question_text || `Câu ${index + 1}`)}</b></div>)}</div> : null}
        {preview.questions.length > 20 ? <p className="helper">Chỉ hiển thị 20 câu đầu trong preview để popup không quá nặng.</p> : null}
      </div> : null}

      <div className="modal-actions">
        <button className="btn secondary" type="button" disabled={Boolean(busy)} onClick={onClose}>Đóng</button>
        <button className="btn secondary" type="button" disabled={!olx.trim() || Boolean(busy) || disabled} onClick={runPreview}>{busy === 'preview' ? 'Đang đọc...' : 'Kiểm tra OLX'}</button>
        <button className="btn" type="button" disabled={!preview?.ok || preview.invalid_count > 0 || Boolean(busy) || disabled} onClick={commitImport}>{busy === 'import' ? 'Đang import...' : `Import ${preview?.valid_count || 0} câu & chờ duyệt`}</button>
      </div>
    </div>
  </Modal>
}
