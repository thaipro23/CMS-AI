'use client'

import Link from 'next/link'
import { useEffect, useMemo, useState } from 'react'
import { PageHeader, PageRoot } from '../../components/layout/PageHeader'
import { StatusBadge } from '../../components/ui/StatusBadge'
import {
  enqueueLegacyQuizCmsOldImport,
  getBankOperationJob,
  previewLegacyQuizCmsOldImport,
  skipInvalidLegacyQuizCmsOldQuestions,
} from '../../lib/api'
import type { BankOperationJob, LegacyQuizCmsOldImportPreview } from '../../types'
import { useBankData } from '../bank/_components/shared'

const TERMINAL_JOB_STATUSES = new Set(['completed', 'failed', 'canceled'])

function fileSize(value: number) {
  if (value < 1024 * 1024) return `${Math.max(1, Math.round(value / 1024))} KB`
  return `${(value / 1024 / 1024).toFixed(1)} MB`
}

function typeLabel(value: string) {
  return ({
    single_select: 'Chọn một đáp án đúng',
    multi_select: 'Chọn nhiều đáp án đúng',
    dropdown_fill: 'Chọn và điền vào ô trống',
  } as Record<string, string>)[value] || value
}

function difficultyLabel(value: string) {
  return ({
    easy: 'Dễ',
    medium: 'Trung bình',
    hard: 'Khó',
    unclassified: 'Chưa phân loại',
  } as Record<string, string>)[value] || value
}

function mergeFiles(current: File[], incoming: File[]) {
  const files = new Map(current.map((file) => [`${file.name}:${file.size}:${file.lastModified}`, file]))
  incoming.forEach((file) => files.set(`${file.name}:${file.size}:${file.lastModified}`, file))
  return Array.from(files.values())
}

function FileList({ files, onRemove }: { files: File[]; onRemove: (index: number) => void }) {
  if (!files.length) return null
  return <div className="legacy-import-file-list">{files.map((file, index) => <div key={`${file.name}-${file.lastModified}-${index}`}>
    <span aria-hidden="true">▧</span><span><b>{file.name}</b><small>{fileSize(file.size)}</small></span><button type="button" className="icon-button danger" aria-label={`Bỏ ${file.name}`} onClick={() => onRemove(index)}>×</button>
  </div>)}</div>
}

export default function ImportQuizCmsOldPage() {
  const { headers } = useBankData()
  const [workbooks, setWorkbooks] = useState<File[]>([])
  const [assets, setAssets] = useState<File[]>([])
  const [preview, setPreview] = useState<LegacyQuizCmsOldImportPreview | null>(null)
  const [job, setJob] = useState<BankOperationJob | null>(null)
  const [busyAction, setBusyAction] = useState<'preview' | 'skip' | 'enqueue' | null>(null)
  const [error, setError] = useState('')
  const busy = Boolean(busyAction)

  const resetResult = () => {
    setPreview(null)
    setJob(null)
    setError('')
  }
  const workbookBytes = useMemo(() => workbooks.reduce((sum, file) => sum + file.size, 0), [workbooks])
  const assetBytes = useMemo(() => assets.reduce((sum, file) => sum + file.size, 0), [assets])

  useEffect(() => {
    if (!job || TERMINAL_JOB_STATUSES.has(job.status)) return
    const timer = window.setInterval(() => {
      getBankOperationJob(headers, job.id)
        .then(setJob)
        .catch(() => null)
    }, 2_000)
    return () => window.clearInterval(timer)
  }, [headers, job])

  const runPreview = async (selectedAssets: File[] = assets) => {
    if (!workbooks.length) return
    setBusyAction('preview')
    setError('')
    setPreview(null)
    setJob(null)
    try {
      setPreview(await previewLegacyQuizCmsOldImport(headers, workbooks, selectedAssets))
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Không thể kiểm tra file import.')
    } finally {
      setBusyAction(null)
    }
  }

  const startImport = async () => {
    if (!preview?.can_commit) return
    setBusyAction('enqueue')
    setError('')
    try {
      const queued = await enqueueLegacyQuizCmsOldImport(headers, preview.preview_token)
      setJob(queued.job)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Không thể tạo tác vụ import.')
    } finally {
      setBusyAction(null)
    }
  }

  const skipInvalidQuestions = async () => {
    if (!preview?.can_skip_invalid_questions) return
    setBusyAction('skip')
    setError('')
    try {
      setPreview(await skipInvalidLegacyQuizCmsOldQuestions(headers, preview.preview_token))
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Không thể bỏ qua các câu lỗi.')
    } finally {
      setBusyAction(null)
    }
  }

  const addAssets = (incoming: File[], recheck = false) => {
    if (!incoming.length) return
    const nextAssets = mergeFiles(assets, incoming)
    setAssets(nextAssets)
    resetResult()
    if (recheck && workbooks.length) void runPreview(nextAssets)
  }

  const result = (job?.result || {}) as Record<string, any>

  return <PageRoot className="page-stack enterprise-standard-page legacy-quiz-import-page">
    <PageHeader
      eyebrow="Ngân hàng đề"
      title="Import Quiz CMS cũ"
      icon="upload"
      tone="blue"
      breadcrumbs={[{ label: 'Ngân hàng đề', href: '/bank/departments' }, { label: 'Import Quiz CMS cũ' }]}
    />

    <section className="legacy-import-intro">
      <div><span className="legacy-import-term">Đích cố định · SU26</span><h2>Đưa ngân hàng câu hỏi Excel cũ vào đúng môn và bài</h2><p>Mã môn phải nằm chính xác ở đầu tên file. Mỗi sheet được ánh xạ thành một bài; hệ thống tạo phiên bản SU26, bài và bản nháp ngân hàng câu hỏi nếu chưa có.</p></div>
      <div className="legacy-import-rules">
        <div><b>TYPE</b><span>0 · Một đáp án</span><span>1 · Nhiều đáp án</span><span>2 · Chọn/điền ô trống</span></div>
        <div><b>NGƯỠNG</b><span>1 · Dễ</span><span>2 · Trung bình</span><span>3 · Khó</span></div>
      </div>
    </section>

    <section className="legacy-import-upload-grid">
      <div className="legacy-import-upload-card">
        <div><span>Bước 1</span><h3>File Excel câu hỏi</h3><p>Chọn tối đa 20 file .xlsx. Tên file bắt đầu bằng mã môn, ví dụ <code>MEC229 - Đồ gá.xlsx</code>.</p></div>
        <label className="legacy-import-dropzone">Chọn file Excel<input hidden type="file" accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" multiple disabled={busy} onChange={(event) => { setWorkbooks(Array.from(event.target.files || [])); resetResult(); event.currentTarget.value = '' }} /></label>
        <FileList files={workbooks} onRemove={(index) => { setWorkbooks((current) => current.filter((_, itemIndex) => itemIndex !== index)); resetResult() }} />
        {workbooks.length ? <small>{workbooks.length} file · {fileSize(workbookBytes)}</small> : null}
      </div>
      <div className="legacy-import-upload-card">
        <div><span>Bước 2 · Khi có ảnh</span><h3>Ảnh đi kèm</h3><p>Nếu câu hỏi chứa <code>[ten-anh.png]</code>, phải tải đủ ảnh trực tiếp hoặc trong ZIP. Ảnh nhúng sẵn trong Excel cũng được nhận diện.</p></div>
        <label className="legacy-import-dropzone secondary">Chọn ảnh hoặc ZIP<input hidden type="file" accept=".png,.jpg,.jpeg,.webp,.zip,image/png,image/jpeg,image/webp,application/zip" multiple disabled={busy} onChange={(event) => { addAssets(Array.from(event.target.files || [])); event.currentTarget.value = '' }} /></label>
        <FileList files={assets} onRemove={(index) => { setAssets((current) => current.filter((_, itemIndex) => itemIndex !== index)); resetResult() }} />
        {assets.length ? <small>{assets.length} file · {fileSize(assetBytes)}</small> : null}
      </div>
    </section>

    <section className="legacy-import-action-bar">
      <div><b>Preview không ghi dữ liệu môn học</b><span>Hệ thống kiểm tra loại câu, độ khó, đáp án, ảnh và môn đích trước khi cho phép import.</span></div>
      <button className="btn" type="button" disabled={busy || !workbooks.length} onClick={() => void runPreview()}>{busyAction === 'preview' ? 'Đang kiểm tra...' : 'Kiểm tra file'}</button>
    </section>

    {error ? <div className="alert error"><b>Không thể hoàn tất</b><span>{error}</span></div> : null}

    {preview ? <>
      <section className="legacy-import-summary">
        <div><span>File Excel</span><b>{preview.workbook_count}</b></div><div><span>Sheet / bài</span><b>{preview.sheet_count}</b></div><div><span>Câu sẽ import</span><b>{preview.question_count}</b></div><div><span>Ảnh gắn câu hỏi</span><b>{preview.image_count}</b></div><div className={preview.invalid_question_count ? 'has-errors' : preview.skipped_invalid_question_count ? 'is-warning' : ''}><span>{preview.skipped_invalid_question_count ? 'Câu đã bỏ qua' : 'Câu lỗi'}</span><b>{preview.skipped_invalid_question_count || preview.invalid_question_count}</b></div><div className={preview.can_commit ? 'is-ready' : 'has-errors'}><span>Trạng thái</span><b>{preview.can_commit ? 'Sẵn sàng' : 'Cần xử lý'}</b></div>
      </section>

      <section className="legacy-import-breakdown">
        <div><h3>Loại câu hỏi</h3>{Object.entries(preview.type_counts).map(([key, count]) => <p key={key}><span>{typeLabel(key)}</span><b>{count}</b></p>)}</div>
        <div><h3>Độ khó</h3>{['easy', 'medium', 'hard', 'unclassified'].map((key) => <p key={key}><span>{difficultyLabel(key)}</span><b>{preview.difficulty_counts[key] || 0}</b></p>)}</div>
      </section>

      <section className="legacy-import-workbooks">
        <div className="section-head"><div><h2>Đối chiếu môn và sheet</h2><p>Mỗi dòng dưới đây sẽ tạo hoặc dùng lại Bài tương ứng trong phiên bản SU26.</p></div></div>
        {preview.workbooks.map((workbook) => <details key={workbook.filename} open={preview.workbooks.length === 1}>
          <summary><span><b>{workbook.filename}</b><small>{workbook.subject_code ? `${workbook.subject_code} · ${workbook.subject_name}` : 'Chưa khớp môn'}</small></span><span>{workbook.sheet_count} sheet · {workbook.question_count} câu</span><StatusBadge status={workbook.error_count ? 'failed' : 'ready'} label={workbook.error_count ? `${workbook.error_count} lỗi` : 'Hợp lệ'} /></summary>
          <div className="legacy-import-sheet-table"><div className="legacy-import-sheet-head"><span>Sheet</span><span>Bài</span><span>Câu</span><span>Loại câu</span><span>Độ khó</span><span>Kiểm tra</span></div>{workbook.sheets.map((sheet) => <div key={sheet.sheet_name}><span><b>{sheet.sheet_name}</b></span><span>Bài {sheet.chapter_no}</span><span>{sheet.question_count}</span><span>{Object.entries(sheet.type_counts).map(([key, count]) => `${typeLabel(key)}: ${count}`).join(' · ')}</span><span>{Object.entries(sheet.difficulty_counts).map(([key, count]) => `${difficultyLabel(key)}: ${count}`).join(' · ')}</span><span>{sheet.error_count ? `${sheet.error_count} lỗi` : sheet.warning_count ? `${sheet.warning_count} cảnh báo` : 'Hợp lệ'}</span></div>)}</div>
        </details>)}
      </section>

      {preview.can_skip_invalid_questions ? <section className="legacy-import-resolution">
        <div>
          <span>Cần quyết định</span>
          <h2>{preview.missing_image_question_count ? `${preview.missing_image_question_count} câu đang thiếu ảnh` : `${preview.invalid_question_count} câu đang lỗi`}</h2>
          <p>Bổ sung đủ ảnh rồi hệ thống sẽ tự kiểm tra lại, hoặc bỏ qua để loại toàn bộ {preview.invalid_question_count} câu lỗi khỏi lần import này. Lỗi cấp môn, file hoặc sheet vẫn phải sửa.</p>
          <small>File Excel gốc vẫn được lưu làm tài liệu đối chiếu; câu bị bỏ qua sẽ không được tạo trong ngân hàng đề.</small>
        </div>
        <div className="button-row">
          {preview.missing_image_question_count ? <label className="btn secondary file-button">Bổ sung ảnh và kiểm tra lại<input hidden type="file" accept=".png,.jpg,.jpeg,.webp,.zip,image/png,image/jpeg,image/webp,application/zip" multiple disabled={busy} onChange={(event) => { addAssets(Array.from(event.target.files || []), true); event.currentTarget.value = '' }} /></label> : null}
          <button className="btn danger" type="button" disabled={busy} onClick={skipInvalidQuestions}>{busyAction === 'skip' ? 'Đang loại câu lỗi...' : `Bỏ qua ${preview.invalid_question_count} câu lỗi`}</button>
        </div>
      </section> : null}

      {preview.errors.length ? <section className="legacy-import-issues error-list"><h2>Lỗi chặn import ({preview.errors.length})</h2>{preview.errors.slice(0, 100).map((item, index) => <div key={`${item.code}-${index}`}><b>{item.code || 'INVALID_DATA'}</b><span>{[item.workbook, item.sheet, item.row ? `dòng ${item.row}` : '', item.field].filter(Boolean).join(' · ')}</span><p>{item.message}</p></div>)}</section> : null}
      {preview.skipped_invalid_questions.length ? <section className="legacy-import-issues skipped-list"><h2>Câu đã bỏ qua ({preview.skipped_invalid_question_count})</h2>{preview.skipped_invalid_questions.slice(0, 100).map((item, index) => <div key={`${item.workbook}-${item.sheet}-${item.row}-${index}`}><b>{item.error_codes?.join(', ') || 'INVALID_QUESTION'}</b><span>{[item.workbook, item.sheet, item.row ? `dòng ${item.row}` : ''].filter(Boolean).join(' · ')}</span><p>{item.image_refs?.length ? `Ảnh tham chiếu: ${item.image_refs.join(', ')}` : 'Câu này sẽ không được tạo trong ngân hàng đề.'}</p></div>)}</section> : null}
      {preview.warnings.length ? <section className="legacy-import-issues warning-list"><h2>Cảnh báo ({preview.warnings.length})</h2>{preview.warnings.slice(0, 100).map((warning, index) => <p key={`${warning}-${index}`}>{warning}</p>)}</section> : null}

      <section className="legacy-import-confirm">
        <div><h2>{preview.can_commit ? 'Sẵn sàng import vào SU26' : 'Chưa thể import'}</h2><p>{preview.message} Câu thiếu concept hoặc độ khó vẫn được nhận và sẽ được tạo Quiz theo chế độ linh hoạt; tất cả câu mới đều ghi nhận người import và bắt buộc duyệt.</p></div>
        <button className="btn" type="button" disabled={busy || !preview.can_commit || Boolean(job)} onClick={startImport}>{busyAction === 'enqueue' ? 'Đang tạo tác vụ...' : 'Import vào SU26'}</button>
      </section>
    </> : null}

    {job ? <section className={`legacy-import-job ${job.status}`}>
      <div className="section-head"><div><span>Tác vụ nền</span><h2>{job.progress_label || 'Đang xử lý'}</h2></div><StatusBadge status={job.status} label={job.status === 'completed' ? 'Hoàn tất' : job.status === 'failed' ? 'Thất bại' : job.status === 'running' ? 'Đang chạy' : 'Đang chờ'} /></div>
      <div className="legacy-import-progress"><span style={{ width: `${Math.max(0, Math.min(100, job.progress_percent || 0))}%` }} /></div><p>{Math.round(job.progress_percent || 0)}% · {job.progress_current}/{job.progress_total} sheet</p>
      {job.error_message ? <div className="alert error">{job.error_message}</div> : null}
      {job.status === 'completed' ? <div className="alert success"><b>{String(result.message || 'Import hoàn tất.')}</b><span>{Number(result.created_question_count || 0)} câu mới đang Chờ duyệt; đã loại {Number(result.skipped_invalid_question_count || 0)} câu lỗi; bỏ qua {Number(result.skipped_question_count || 0)} câu đã có do retry.</span></div> : null}
      <div className="button-row"><Link className="btn secondary" href="/bank/departments">Mở Ngân hàng đề</Link><Link className="btn secondary" href="/jobs">Xem tác vụ nền</Link></div>
    </section> : null}
  </PageRoot>
}
