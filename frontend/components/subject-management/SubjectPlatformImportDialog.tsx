'use client'
import { useState } from 'react'
import { applyAcademicSubjectPlatformImport, previewAcademicSubjectPlatformImport } from '../../lib/api'
import type { AcademicSubjectPlatformImportPreview } from '../../types'

export function SubjectPlatformImportDialog({ open, headers, termId, branch, onClose, onApplied }: { open: boolean; headers: HeadersInit; termId: string; branch: string; onClose: () => void; onApplied: (message: string) => void }) {
  const [file, setFile] = useState<File | null>(null)
  const [preview, setPreview] = useState<AcademicSubjectPlatformImportPreview | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  if (!open) return null
  const runPreview = async () => { if (!file || !termId) return; setBusy(true); setError(''); try { setPreview(await previewAcademicSubjectPlatformImport(headers, file, termId, branch)) } catch (e) { setError(e instanceof Error ? e.message : 'Không đọc được file.') } finally { setBusy(false) } }
  const apply = async () => { if (!preview?.can_apply) return; setBusy(true); setError(''); try { const result = await applyAcademicSubjectPlatformImport(headers, preview.preview_token); onApplied(result.message); setPreview(null); setFile(null); onClose() } catch (e) { setError(e instanceof Error ? e.message : 'Áp dụng kế hoạch thất bại.') } finally { setBusy(false) } }
  return <div className="dialog-backdrop" role="presentation"><section className="card dialog" role="dialog" aria-modal="true" aria-labelledby="subject-platform-import-title"><h2 id="subject-platform-import-title">Import kế hoạch nền tảng</h2><p>Excel chỉ gồm hai cột theo đúng thứ tự: <b>Mã môn</b> và <b>Nền tảng</b>. Hệ và học kỳ lấy từ bộ lọc hiện tại.</p><input type="file" aria-label="File kế hoạch Excel" accept=".xlsx" onChange={(e) => { setFile(e.target.files?.[0] || null); setPreview(null) }} />{preview ? <div className="import-preview"><p>{preview.can_apply ? 'Có thể áp dụng' : 'Có dòng lỗi, chưa thể áp dụng'}</p><p>Khớp: {preview.matched_count} · Thiếu: {preview.missing_count} · Trùng: {preview.duplicate_count} · Lỗi: {preview.invalid_count}</p><ul>{preview.rows.slice(0, 20).map((row) => <li key={row.row_no}>Dòng {row.row_no}: {row.subject_code} · {row.message}</li>)}</ul></div> : null}{error ? <p role="alert" className="danger-text">{error}</p> : null}<footer><button className="btn secondary" type="button" onClick={onClose}>Đóng</button>{!preview ? <button className="btn" type="button" disabled={!file || busy} onClick={() => void runPreview()}>{busy ? 'Đang kiểm tra...' : 'Xem trước'}</button> : <button className="btn" type="button" disabled={!preview.can_apply || busy} onClick={() => void apply()}>{busy ? 'Đang áp dụng...' : 'Áp dụng kế hoạch'}</button>}</footer></section></div>
}
