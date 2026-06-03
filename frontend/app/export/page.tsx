'use client'

import { useEffect, useState } from 'react'
import { downloadApprovedOlx, exportApprovedOlx, getPublishHistory, publishApprovedToOpenEdx, rollbackPublishBatch } from '../../lib/api'
import { useAppContext } from '../../context/AppContext'
import { ActionMessage, ActionMessageData, toUserError } from '../../components/ui/ActionMessage'
import { LoadingButton } from '../../components/ui/LoadingButton'
import { PublishBatchSummary, PublishLibrarySummary, PublishResult } from '../../types'

type PublishMode = 'publish_new' | 'replace' | 'delete_reimport'

function statusLabel(status: string) {
  if (status === 'published' || status === 'verified' || status === 'success' || status === 'published_ok_stale_verify' || status === 'published_with_tag_warning') return 'Published'
  if (status === 'published_with_pending_changes' || status === 'warning') return 'Published with pending changes'
  if (status === 'imported_needs_manual_publish') return 'Imported but needs manual publish'
  if (status === 'imported_needs_manual_verify') return 'Imported but needs manual verify'
  if (status === 'failed') return 'Failed'
  return status || '—'
}

function statusClass(status: string) {
  const value = (status || '').toLowerCase()
  if (value.includes('failed')) return 'status danger'
  if (value.includes('pending') || value.includes('manual') || value.includes('warning')) return 'status warning'
  return 'status success'
}

function LibrarySummaryTable({ rows }: { rows: PublishLibrarySummary[] }) {
  if (!rows.length) return <div className="empty-state">Chưa có kết quả publish theo Library.</div>
  return <div className="table-wrap"><table className="data-table compact-table">
    <thead><tr><th>Difficulty</th><th>Library</th><th>Số câu</th><th>Trạng thái</th><th>Studio</th></tr></thead>
    <tbody>{rows.map((row) => <tr key={`${row.library_key}-${row.difficulty}`}>
      <td><b>{row.difficulty}</b></td>
      <td className="text-clip"><b>{row.library_display_name || row.library_key}</b><small>{row.library_key}</small></td>
      <td>{row.component_count} components<br /><small>{row.verified_count || 0} verified · {row.pending_count || 0} pending</small></td>
      <td><span className={statusClass(row.status)}>{statusLabel(row.status)}</span></td>
      <td>{row.studio_url ? <a className="btn small secondary" href={row.studio_url} target="_blank" rel="noreferrer">Mở</a> : <span className="muted">Không có link</span>}</td>
    </tr>)}</tbody>
  </table></div>
}

export default function ExportPage() {
  const { courseId, authHeaders, can } = useAppContext()
  const [olxPreview, setOlxPreview] = useState('')
  const [message, setMessage] = useState<ActionMessageData | null>(null)
  const [loadingAction, setLoadingAction] = useState<string | null>(null)
  const [publishMode, setPublishMode] = useState<PublishMode>('publish_new')
  const [result, setResult] = useState<PublishResult | null>(null)
  const [history, setHistory] = useState<PublishBatchSummary[]>([])

  useEffect(() => {
    const saved = window.localStorage.getItem('ai_openedx_olx_preview')
    if (saved) setOlxPreview(saved)
  }, [])

  useEffect(() => { loadHistory() }, [courseId])

  async function loadHistory() {
    try {
      const data = await getPublishHistory(courseId, authHeaders())
      setHistory(data.batches || [])
    } catch {
      setHistory([])
    }
  }

  async function preview() {
    setLoadingAction('preview')
    try {
      const data = await exportApprovedOlx(courseId, authHeaders())
      setOlxPreview(data.olx)
      window.localStorage.setItem('ai_openedx_olx_preview', data.olx)
      setMessage({ type: 'success', body: `Đã preview ${data.question_count} câu hỏi approved.` })
    } catch (error) {
      setMessage(toUserError(error))
    } finally {
      setLoadingAction(null)
    }
  }

  async function publishToOpenEdx() {
    setLoadingAction('publish')
    try {
      const data = await publishApprovedToOpenEdx(courseId, authHeaders(true), publishMode)
      setResult(data)
      await loadHistory()
      const published = data?.published ?? 0
      const failed = data?.failed ?? 0
      const warnings = data?.warnings ?? 0
      if (failed > 0) {
        const firstError = data?.errors?.[0]?.error ? ` Lỗi đầu tiên: ${data.errors[0].error}` : ''
        setMessage({ type: 'warning', title: 'Publish chưa hoàn tất', body: `Đã publish/import ${published} câu, warning ${warnings}, lỗi ${failed}.${firstError}` })
      } else if (warnings > 0) {
        setMessage({ type: 'warning', title: 'Đã import nhưng cần kiểm tra Studio', body: `Đã import ${published} câu. Có ${warnings} câu/library còn pending/manual verify. Xem bảng verify bên dưới.` })
      } else {
        setMessage({ type: 'success', title: 'Publish thành công', body: `Đã publish ${published} câu approved sang Open edX và verify xong.` })
      }
    } catch (error) {
      setMessage(toUserError(error, 'Publish thất bại. Kiểm tra USE_MOCK_OPENEDX, connector production và backend logs.'))
    } finally {
      setLoadingAction(null)
    }
  }

  async function download() {
    setLoadingAction('download')
    try {
      await downloadApprovedOlx(courseId, authHeaders())
      setMessage({ type: 'success', body: 'Đã tạo file XML để tải xuống.' })
    } catch (error) {
      setMessage(toUserError(error))
    } finally {
      setLoadingAction(null)
    }
  }

  async function rollback(batch: PublishBatchSummary, level: 'ai_server' | 'openedx') {
    if (!window.confirm(`Rollback batch ${batch.id.slice(0, 8)} ở mức ${level}?`)) return
    setLoadingAction(`rollback:${batch.id}:${level}`)
    try {
      const data: any = await rollbackPublishBatch(batch.id, level, authHeaders(true))
      const manual = data.manual_delete_required || 0
      const failed = data.failed_delete_count || 0
      const title = manual || failed ? 'Rollback một phần' : 'Đã rollback'
      const type = manual || failed ? 'warning' : 'success'
      setMessage({
        type,
        title,
        body: `Reset ${data.reset_questions || 0} câu. Đã xóa Open edX: ${data.deleted_openedx_components || 0}. Cần xóa tay: ${manual}. Lỗi xóa: ${failed}.`,
      })
      await loadHistory()
    } catch (error) {
      setMessage(toUserError(error))
    } finally {
      setLoadingAction(null)
    }
  }

  const latestRows = result?.libraries || history[0]?.summary?.libraries || []

  return <div className="page-stack">
    <section className="card page-intro export-hero">
      <div>
        <h2>Xuất Open edX Library</h2>
        <p className="helper">Workflow: chọn course → preview OLX → publish vào Library → verify Open edX → cấu hình Problem Bank trong Unit.</p>
      </div>
      <div className="export-mode-box">
        <label>Chế độ publish</label>
        <select className="input" value={publishMode} onChange={(event) => setPublishMode(event.target.value as PublishMode)}>
          <option value="publish_new">Publish mới</option>
          <option value="replace">Replace component cũ</option>
          <option value="delete_reimport">Xóa component cũ rồi import lại</option>
        </select>
      </div>
    </section>

    <ActionMessage message={message} onClose={() => setMessage(null)} />

    <section className="workflow-steps compact-steps">
      <div className="step-card"><b>1</b><span>Course</span><small>{courseId}</small></div>
      <div className="step-card"><b>2</b><span>Approved questions</span><small>Preview trước khi publish</small></div>
      <div className="step-card"><b>3</b><span>OLX</span><small>Problem XML gọn cho LMS</small></div>
      <div className="step-card"><b>4</b><span>Publish</span><small>Chapter + Difficulty Library</small></div>
      <div className="step-card"><b>5</b><span>Verify</span><small>Library/Problem/Tag/Pending</small></div>
      <div className="step-card"><b>6</b><span>Problem Bank</span><small>Dùng gợi ý ở bảng dưới</small></div>
    </section>

    <section className="card action-strip">
      <LoadingButton className="btn" loading={loadingAction === 'preview'} disabled={!can('export_questions') || Boolean(loadingAction)} onClick={preview}>Xem trước OLX</LoadingButton>
      <LoadingButton className="btn secondary" loading={loadingAction === 'download'} disabled={!can('export_questions') || Boolean(loadingAction)} onClick={download}>Tải XML</LoadingButton>
      <LoadingButton className="btn danger" loading={loadingAction === 'publish'} disabled={!can('publish_to_openedx') || Boolean(loadingAction)} onClick={publishToOpenEdx}>Publish to Library</LoadingButton>
    </section>

    <section className="card">
      <div className="section-head"><div><h2>Kết quả publish / Problem Bank friendly</h2><p className="helper">Sau publish, dùng từng Library EASY/MEDIUM/HARD trong Problem Bank của Unit.</p></div></div>
      {result && <div className="summary-grid">
        <div><span>Batch</span><b>{result.batch_id?.slice(0, 8) || '—'}</b></div>
        <div><span>Published/imported</span><b>{result.published}</b></div>
        <div><span>Warnings</span><b>{result.warnings || 0}</b></div>
        <div><span>Failed</span><b>{result.failed}</b></div>
      </div>}
      <LibrarySummaryTable rows={latestRows} />
    </section>

    <section className="card">
      <h2>Xem trước OLX</h2>
      <pre className="xml-preview">{olxPreview || 'Chưa có OLX preview. Hãy bấm Xem trước OLX hoặc preview từng câu từ Ngân hàng câu hỏi.'}</pre>
    </section>

    <section className="card">
      <div className="section-head"><div><h2>Lịch sử publish</h2><p className="helper">Rollback mức AI Server sẽ đưa câu về approved. Rollback Open edX sẽ cố gắng xóa component nếu connector hỗ trợ.</p></div><button className="btn secondary" onClick={loadHistory}>Tải lại</button></div>
      {!history.length ? <div className="empty-state">Chưa có lịch sử publish.</div> : <div className="table-wrap"><table className="data-table compact-table">
        <thead><tr><th>Batch</th><th>Mode</th><th>Kết quả</th><th>Thời gian</th><th>Rollback</th></tr></thead>
        <tbody>{history.map((batch) => <tr key={batch.id}>
          <td><b>{batch.id.slice(0, 8)}</b><small>{batch.actor_id}</small></td>
          <td>{batch.mode}</td>
          <td><span className={statusClass(batch.status)}>{batch.status}</span><br /><small>{batch.published_count} ok · {batch.warning_count} warning · {batch.failed_count} lỗi</small></td>
          <td>{batch.created_at ? new Date(batch.created_at).toLocaleString('vi-VN') : '—'}</td>
          <td className="button-row compact">
            <button className="btn small secondary" disabled={Boolean(loadingAction)} onClick={() => rollback(batch, 'ai_server')}>AI Server</button>
            <button className="btn small danger" disabled={Boolean(loadingAction)} onClick={() => rollback(batch, 'openedx')}>Open edX</button>
          </td>
        </tr>)}</tbody>
      </table></div>}
    </section>
  </div>
}
