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
import { BankPageIdentity, BankWorkflowStepper } from '../bank/_components/BankDesignContract'
import { useBankData } from '../bank/_components/shared'

const TERMINAL_JOB_STATUSES = new Set(['completed', 'failed', 'canceled'])
type LegacyImportError = LegacyQuizCmsOldImportPreview['errors'][number]

const ERROR_LABELS: Record<string, string> = {
  MISSING_IMAGE: 'Thiếu ảnh câu hỏi',
  SUBJECT_NOT_FOUND: 'Không tìm thấy môn đích',
  SUBJECT_AMBIGUOUS: 'Mã môn không duy nhất',
  INVALID_QUESTION: 'Câu hỏi không hợp lệ',
  BANK_PREFLIGHT_FAILED: 'Câu chưa đạt kiểm tra kho đề/CMS',
  INVALID_TYPE: 'TYPE không hợp lệ',
  INVALID_DIFFICULTY: 'NGƯỠNG không hợp lệ',
  INVALID_WORKBOOK: 'File Excel không hợp lệ',
  INVALID_SHEET: 'Sheet không hợp lệ',
}

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
  const errorGroups = useMemo(() => {
    const groups = new Map<string, LegacyImportError[]>()
    for (const item of preview?.errors || []) {
      const code = item.code || 'INVALID_DATA'
      groups.set(code, [...(groups.get(code) || []), item])
    }
    return Array.from(groups, ([code, items]) => ({ code, items }))
      .sort((left, right) => right.items.length - left.items.length)
  }, [preview])

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
  const currentStep = job || preview?.can_commit ? 3 : preview ? 2 : 1
  const readyQuestionCount = preview
    ? Math.max(0, preview.question_count - preview.invalid_question_count)
    : 0
  const unclassifiedDifficultyCount = Number(preview?.difficulty_counts.unclassified || 0)
  const targetSubjects = preview?.workbooks
    .filter((workbook) => workbook.subject_code)
    .map((workbook) => `${workbook.subject_code} · ${workbook.subject_name}`)
    .join(', ')

  return <PageRoot className="page-stack bank-multipage bank-contract-page legacy-quiz-import-page">
    <PageHeader
      eyebrow="Ngân hàng đề"
      title="Import Quiz CMS cũ"
      icon="upload"
      tone="blue"
      breadcrumbs={[{ label: 'Ngân hàng đề', href: '/bank/departments' }, { label: 'Import Quiz CMS cũ' }]}
    />

    <BankPageIdentity
      title="Import Quiz CMS cũ"
      description="Kiểm tra Excel, xử lý ảnh còn thiếu rồi đưa câu hỏi vào đúng môn, đúng bài của phiên bản SU26."
      icon="upload"
      tone="blue"
      meta={<span className="legacy-import-term">Đích cố định · SU26</span>}
      actions={<div className="legacy-import-rules">
        <div><b>TYPE</b><span>0 Một đáp án · 1 Nhiều đáp án · 2 Điền ô trống</span></div>
        <div><b>NGƯỠNG</b><span>1 Dễ · 2 Trung bình · 3 Khó</span></div>
      </div>}
    />

    <BankWorkflowStepper
      currentStep={currentStep}
      steps={[
        { title: 'Chọn tệp', description: 'Excel và ảnh đi kèm', icon: 'upload' },
        { title: 'Kiểm tra & xử lý', description: 'Môn, sheet, đáp án, ảnh', icon: 'search' },
        { title: 'Xác nhận import', description: 'Tạo câu Chờ duyệt', icon: 'check' },
      ]}
    />

    {!preview ? <section className="legacy-import-source-panel">
      <div className="legacy-import-source-heading">
        <div><span>Nguồn dữ liệu</span><h2>Chọn file cần import</h2></div>
        <p>Tên file phải bắt đầu bằng mã môn. Mỗi sheet tương ứng một bài trong SU26.</p>
      </div>
      <div className="legacy-import-upload-grid">
        <div className="legacy-import-upload-card">
          <div className="legacy-import-upload-copy"><span className="legacy-import-upload-index">01</span><div><h3>File Excel câu hỏi</h3><p>Tối đa 20 file <code>.xlsx</code>.</p></div></div>
          <label className="legacy-import-dropzone">+ Chọn file Excel<input hidden type="file" accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" multiple disabled={busy} onChange={(event) => { setWorkbooks(Array.from(event.target.files || [])); resetResult(); event.currentTarget.value = '' }} /></label>
          <FileList files={workbooks} onRemove={(index) => { setWorkbooks((current) => current.filter((_, itemIndex) => itemIndex !== index)); resetResult() }} />
          <small>{workbooks.length ? `${workbooks.length} file · ${fileSize(workbookBytes)}` : 'Ví dụ: MEC229 - Đồ gá.xlsx'}</small>
        </div>
        <div className="legacy-import-upload-card">
          <div className="legacy-import-upload-copy"><span className="legacy-import-upload-index">02</span><div><h3>Ảnh đi kèm <em>Không bắt buộc</em></h3><p>Chọn ảnh trực tiếp hoặc một file ZIP.</p></div></div>
          <label className="legacy-import-dropzone secondary">+ Chọn ảnh hoặc ZIP<input hidden type="file" accept=".png,.jpg,.jpeg,.webp,.zip,image/png,image/jpeg,image/webp,application/zip" multiple disabled={busy} onChange={(event) => { addAssets(Array.from(event.target.files || [])); event.currentTarget.value = '' }} /></label>
          <FileList files={assets} onRemove={(index) => { setAssets((current) => current.filter((_, itemIndex) => itemIndex !== index)); resetResult() }} />
          <small>{assets.length ? `${assets.length} file · ${fileSize(assetBytes)}` : 'Có thể bổ sung sau khi hệ thống báo thiếu ảnh'}</small>
        </div>
      </div>
      <div className="legacy-import-action-bar">
        <div><b>Kiểm tra trước, chưa ghi dữ liệu</b><span>Hệ thống chỉ tạo dữ liệu sau khi bạn xác nhận ở bước cuối.</span></div>
        <button className="btn" type="button" disabled={busy || !workbooks.length} onClick={() => void runPreview()}>{busyAction === 'preview' ? 'Đang kiểm tra...' : preview ? 'Kiểm tra lại file' : 'Kiểm tra file'}</button>
      </div>
    </section> : null}

    {error ? <div className="alert error"><b>Không thể hoàn tất</b><span>{error}</span></div> : null}

    {preview ? <>
      <section className="legacy-import-preview-heading">
        <div><span>Kết quả kiểm tra</span><h2>{preview.workbook_count === 1 ? preview.workbooks[0]?.filename : `${preview.workbook_count} file Excel`}</h2><p>{targetSubjects || 'Chưa xác định được môn đích'} · {preview.sheet_count} sheet</p></div>
        <div className="legacy-import-preview-actions">
          <StatusBadge status={preview.can_commit ? 'ready' : 'failed'} label={preview.can_commit ? 'Sẵn sàng import' : 'Cần xử lý'} />
          <button className="btn secondary small" type="button" disabled={busy} onClick={resetResult}>Đổi tệp</button>
        </div>
      </section>

      <section className="legacy-import-summary" aria-label="Tổng quan kết quả kiểm tra">
        <div><span>Tổng câu trong nguồn</span><b>{preview.original_question_count}</b><small>{preview.workbook_count} file · {preview.sheet_count} sheet</small></div>
        <div className="is-ready"><span>Câu hợp lệ</span><b>{readyQuestionCount}</b><small>Sẽ đưa vào Chờ duyệt</small></div>
        <div className={preview.invalid_question_count ? 'has-errors' : ''}><span>Câu cần xử lý</span><b>{preview.invalid_question_count}</b><small>{preview.missing_image_question_count ? `${preview.missing_image_question_count} câu thiếu ảnh` : 'Không còn lỗi cấp câu'}</small></div>
        <div className={unclassifiedDifficultyCount ? 'is-warning' : ''}><span>Chưa có độ khó</span><b>{unclassifiedDifficultyCount}</b><small>Được xếp quota linh hoạt</small></div>
      </section>

      <div className="legacy-import-review-grid">
        <section className="legacy-import-workbooks legacy-import-review-main">
          <div className="section-head"><div><span>Đối chiếu dữ liệu</span><h2>Môn và sheet sẽ được tạo</h2><p>Mỗi sheet tạo hoặc dùng lại đúng Bài tương ứng trong phiên bản SU26.</p></div></div>
          {preview.workbooks.map((workbook) => <details key={workbook.filename} open={preview.workbooks.length === 1}>
            <summary><span><b>{workbook.filename}</b><small>{workbook.subject_code ? `${workbook.subject_code} · ${workbook.subject_name}` : 'Chưa khớp môn'}</small></span><span>{workbook.sheet_count} sheet · {workbook.question_count} câu</span><StatusBadge status={workbook.error_count ? 'failed' : 'ready'} label={workbook.error_count ? `${workbook.error_count} lỗi` : 'Hợp lệ'} /></summary>
            <div className="legacy-import-sheet-table"><div className="legacy-import-sheet-head"><span>Sheet</span><span>Bài</span><span>Câu</span><span>Loại câu</span><span>Độ khó</span><span>Kiểm tra</span></div>{workbook.sheets.map((sheet) => <div key={sheet.sheet_name}><span><b>{sheet.sheet_name}</b></span><span>Bài {sheet.chapter_no}</span><span>{sheet.question_count}</span><span>{Object.entries(sheet.type_counts).map(([key, count]) => `${typeLabel(key)}: ${count}`).join(' · ')}</span><span>{Object.entries(sheet.difficulty_counts).map(([key, count]) => `${difficultyLabel(key)}: ${count}`).join(' · ')}</span><span className={sheet.error_count ? 'legacy-import-cell-error' : ''}>{sheet.error_count ? `${sheet.error_count} lỗi` : sheet.warning_count ? `${sheet.warning_count} cảnh báo` : 'Hợp lệ'}</span></div>)}</div>
          </details>)}

          <div className="legacy-import-breakdown">
            <div><h3>Loại câu hỏi</h3>{Object.entries(preview.type_counts).map(([key, count]) => <p key={key}><span>{typeLabel(key)}</span><b>{count}</b></p>)}</div>
            <div><h3>Độ khó</h3>{['easy', 'medium', 'hard', 'unclassified'].map((key) => <p key={key}><span>{difficultyLabel(key)}</span><b>{preview.difficulty_counts[key] || 0}</b></p>)}</div>
          </div>
        </section>

        <aside className="legacy-import-review-sidebar" aria-label="Lỗi và cảnh báo import">
          {preview.can_skip_invalid_questions ? <section className="legacy-import-resolution">
            <div><span>Cần quyết định</span><h2>{preview.missing_image_question_count ? `${preview.missing_image_question_count} câu thiếu ảnh` : `${preview.invalid_question_count} câu đang lỗi`}</h2><p>Bổ sung ảnh để kiểm tra lại, hoặc bỏ qua để loại đúng các câu lỗi khỏi lần import này.</p></div>
            <div className="legacy-import-resolution-actions">
              {preview.missing_image_question_count ? <label className="btn secondary file-button">Bổ sung ảnh và kiểm tra lại<input hidden type="file" accept=".png,.jpg,.jpeg,.webp,.zip,image/png,image/jpeg,image/webp,application/zip" multiple disabled={busy} onChange={(event) => { addAssets(Array.from(event.target.files || []), true); event.currentTarget.value = '' }} /></label> : null}
              <button className="btn danger" type="button" disabled={busy} onClick={skipInvalidQuestions}>{busyAction === 'skip' ? 'Đang loại câu lỗi...' : `Bỏ qua ${preview.invalid_question_count} câu lỗi`}</button>
            </div>
            <small>Chỉ câu lỗi bị xóa. File gốc vẫn được lưu làm tài liệu; lỗi cấp môn, file hoặc sheet vẫn phải sửa.</small>
          </section> : null}

          {errorGroups.length ? <section className="legacy-import-error-groups">
            <div className="legacy-import-sidebar-heading"><div><span>Kiểm tra dữ liệu</span><h2>{preview.errors.length} lỗi chặn import</h2></div></div>
            {errorGroups.map(({ code, items }, groupIndex) => <details key={code} open={groupIndex === 0} data-error-group={code}>
              <summary><span><b>{ERROR_LABELS[code] || code}</b><small>{code}</small></span><strong>{items.length}</strong></summary>
              <div className="legacy-import-error-items">
                {items.slice(0, 12).map((item, index) => <div key={`${code}-${item.workbook}-${item.sheet}-${item.row}-${index}`}><span>{[item.workbook, item.sheet, item.row ? `dòng ${item.row}` : '', item.field].filter(Boolean).join(' · ')}</span><p>{item.message}</p></div>)}
                {items.length > 12 ? <small>Còn {items.length - 12} lỗi cùng nhóm. Sửa theo hướng dẫn trên rồi kiểm tra lại file.</small> : null}
              </div>
              {code === 'MISSING_IMAGE' ? <label className="legacy-import-inline-file-action">+ Thêm ảnh/ZIP cho nhóm này<input hidden type="file" accept=".png,.jpg,.jpeg,.webp,.zip,image/png,image/jpeg,image/webp,application/zip" multiple disabled={busy} onChange={(event) => { addAssets(Array.from(event.target.files || []), true); event.currentTarget.value = '' }} /></label> : null}
            </details>)}
          </section> : <section className="legacy-import-ready-card"><span aria-hidden="true">✓</span><div><h2>Không còn lỗi chặn</h2><p>Bạn có thể xác nhận import ở thanh bên dưới.</p></div></section>}

          {preview.skipped_invalid_questions.length ? <details className="legacy-import-skipped" open>
            <summary><span><b>Câu đã bỏ qua</b><small>Không được tạo trong ngân hàng đề</small></span><strong>{preview.skipped_invalid_question_count}</strong></summary>
            <div>{preview.skipped_invalid_questions.slice(0, 12).map((item, index) => <p key={`${item.workbook}-${item.sheet}-${item.row}-${index}`}><b>{item.error_codes?.join(', ') || 'INVALID_QUESTION'}</b><span>{[item.sheet, item.row ? `dòng ${item.row}` : ''].filter(Boolean).join(' · ')}</span></p>)}</div>
          </details> : null}

          {preview.warnings.length ? <details className="legacy-import-warning-box">
            <summary><span><b>Cảnh báo</b><small>Không chặn import</small></span><strong>{preview.warnings.length}</strong></summary>
            <div>{preview.warnings.slice(0, 20).map((warning, index) => <p key={`${warning}-${index}`}>{warning}</p>)}</div>
          </details> : null}
        </aside>
      </div>

      {!job ? <section className={`legacy-import-confirm${preview.can_commit ? ' is-ready' : ''}`}>
        <div><span>Bước 3 · Xác nhận</span><h2>{preview.can_commit ? `Import ${preview.question_count} câu vào SU26` : 'Hoàn tất xử lý lỗi để import'}</h2><p>{preview.message} Câu thiếu concept/độ khó vẫn được nhận và xếp linh hoạt khi tạo Quiz; mọi câu mới đều ghi người import và bắt buộc duyệt.</p></div>
        <button className="btn" type="button" disabled={busy || !preview.can_commit} onClick={startImport}>{busyAction === 'enqueue' ? 'Đang tạo tác vụ...' : 'Import vào SU26'}</button>
      </section> : null}
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
