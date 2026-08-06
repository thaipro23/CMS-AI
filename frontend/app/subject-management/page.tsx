'use client'

import Link from 'next/link'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { useAppContext } from '../../context/AppContext'
import {
  bulkUpdateAcademicSubjectDeliveryPlatform,
  createAcademicSubjectCatalogRefreshJob,
  getAcademicBlocks,
  getAcademicBulkOperationJob,
  getAcademicBulkOperationJobs,
  getAcademicSubjectDeliveries,
  getAcademicTerms,
  updateAcademicSubjectDeliveryPlatform,
} from '../../lib/api'
import type {
  AcademicBlock,
  AcademicBulkOperationJob,
  AcademicLearningPlatform,
  AcademicSubjectDelivery,
  AcademicSubjectDeliveryListResponse,
  AcademicTerm,
} from '../../types'
import { PageRoot } from '../../components/layout/PageHeader'
import { EnterpriseScreenHeader } from '../../components/layout/EnterpriseDesignContract'
import { EnterpriseDataTable, type EnterpriseTableColumn } from '../../components/table/EnterpriseDataTable'
import { CompactFilterBar, OperationsKpiStrip, WorkspaceSection } from '../../components/operations/OperationsWorkspace'
import { InlineNotice, noticeError, noticeSuccess } from '../../components/ui/InlineNotice'
import { PersistentJobNotice } from '../../components/ui/PersistentJobNotice'
import { StatusBadge } from '../../components/ui/StatusBadge'
import { UdemyPlanImportDialog } from '../../components/subject-management/UdemyPlanImportDialog'
import { UdemyProgressImportDialog } from '../../components/subject-management/UdemyProgressImportDialog'


type Branch = 'poly' | 'ptcd'
type PlatformFilter = 'all' | 'unassigned' | 'cms' | 'udemy'

const EMPTY_RESULT: AcademicSubjectDeliveryListResponse = {
  items: [],
  total: 0,
  page: 1,
  page_size: 50,
  total_pages: 0,
  has_next: false,
  summary: { total: 0, cms_count: 0, udemy_count: 0, unassigned_count: 0, class_count: 0, scope_label: 'Toàn bộ bộ lọc' },
}

function branchLabel(value?: string | null) { return String(value || '').toLowerCase() === 'ptcd' ? 'PTCĐ' : 'Poly' }
function platformLabel(value?: AcademicLearningPlatform) { return value === 'cms' ? 'CMS' : value === 'udemy' ? 'Udemy' : 'Chưa chọn' }
function formatDateTime(value?: string | null) {
  if (!value) return 'Chưa có'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : new Intl.DateTimeFormat('vi-VN', { dateStyle: 'short', timeStyle: 'short' }).format(date)
}
function matchingProgressJob(job: AcademicBulkOperationJob, termId: string, blockId: string, branch: string) {
  const request = job.request_json || {}
  return job.job_type === 'udemy_progress_import'
    && job.term_id === termId
    && String(job.branch || '').toLowerCase() === branch.toLowerCase()
    && String(request.block_id || '') === blockId
    && ['queued', 'running'].includes(job.status)
}

function matchingCatalogJob(job: AcademicBulkOperationJob, termId: string, blockId: string, branch: string) {
  const request = job.request_json || {}
  return job.job_type === 'subject_catalog_refresh'
    && job.term_id === termId
    && String(job.branch || '').toLowerCase() === branch.toLowerCase()
    && String(request.block_id || '') === blockId
    && ['queued', 'running'].includes(job.status)
}

function PlatformSelector({ value, disabled, onChange }: { value: AcademicLearningPlatform; disabled?: boolean; onChange: (value: AcademicLearningPlatform) => void }) {
  const options: Array<{ value: AcademicLearningPlatform; label: string }> = [
    { value: null, label: 'Chưa chọn' },
    { value: 'cms', label: 'CMS' },
    { value: 'udemy', label: 'Udemy' },
  ]
  return <div className="subject-platform-segment" role="radiogroup" aria-label="Nền tảng môn học">
    {options.map((option) => <button
      key={option.label}
      type="button"
      role="radio"
      aria-checked={value === option.value}
      className={`subject-platform-option ${value === option.value ? 'is-active' : ''} ${option.value || 'unassigned'}`}
      disabled={disabled}
      onClick={() => onChange(option.value)}
    >{option.label}</button>)}
  </div>
}

export default function SubjectManagementPage() {
  const { authHeaders, can } = useAppContext()
  const headers = useMemo(() => authHeaders(), [authHeaders])
  const jsonHeaders = useMemo(() => authHeaders(true), [authHeaders])
  const canManage = can('manage_settings')

  const [branch, setBranch] = useState<Branch>('poly')
  const [terms, setTerms] = useState<AcademicTerm[]>([])
  const [blocks, setBlocks] = useState<AcademicBlock[]>([])
  const [termId, setTermId] = useState('')
  const [blockId, setBlockId] = useState('')
  const [platformFilter, setPlatformFilter] = useState<PlatformFilter>('all')
  const [search, setSearch] = useState('')
  const [appliedSearch, setAppliedSearch] = useState('')
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(50)
  const [result, setResult] = useState<AcademicSubjectDeliveryListResponse>(EMPTY_RESULT)
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [loading, setLoading] = useState(false)
  const [savingIds, setSavingIds] = useState<Set<string>>(new Set())
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [catalogJob, setCatalogJob] = useState<AcademicBulkOperationJob | null>(null)
  const [planImportOpen, setPlanImportOpen] = useState(false)
  const [progressImportOpen, setProgressImportOpen] = useState(false)
  const [progressDelivery, setProgressDelivery] = useState<AcademicSubjectDelivery | null>(null)
  const [progressJob, setProgressJob] = useState<AcademicBulkOperationJob | null>(null)

  const selectedTerm = useMemo(() => terms.find((item) => item.id === termId) || null, [terms, termId])
  const selectedBlock = useMemo(() => blocks.find((item) => item.id === blockId) || null, [blocks, blockId])

  const loadTerms = useCallback(async () => {
    if (!canManage) return
    setError('')
    try {
      const rows = (await getAcademicTerms(headers, { branch, active: true })).filter((item) => String(item.branch || branch).toLowerCase() === branch)
      setTerms(rows)
      setTermId((current) => rows.some((item) => item.id === current) ? current : rows[0]?.id || '')
    } catch (err) {
      setTerms([]); setTermId('')
      setError(err instanceof Error ? err.message : 'Không tải được danh sách học kỳ.')
    }
  }, [branch, canManage, headers])

  const loadBlocks = useCallback(async () => {
    if (!termId) { setBlocks([]); setBlockId(''); return }
    try {
      const rows = (await getAcademicBlocks(headers, termId)).filter((item) => item.active !== false)
      setBlocks(rows)
      setBlockId((current) => rows.some((item) => item.id === current) ? current : rows[0]?.id || '')
    } catch (err) {
      setBlocks([]); setBlockId('')
      setError(err instanceof Error ? err.message : 'Không tải được danh sách Block.')
    }
  }, [headers, termId])

  const loadDeliveries = useCallback(async () => {
    if (!canManage || !termId || !blockId) { setResult(EMPTY_RESULT); return }
    setLoading(true); setError('')
    try {
      const response = await getAcademicSubjectDeliveries(headers, {
        termId,
        blockId,
        branch,
        platform: platformFilter === 'unassigned' ? null : platformFilter,
        search: appliedSearch,
        page,
        pageSize,
      })
      setResult(response)
      setSelected((current) => new Set([...current].filter((id) => response.items.some((item) => item.id === id))))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Không tải được danh sách môn học.')
    } finally { setLoading(false) }
  }, [appliedSearch, blockId, branch, canManage, headers, page, pageSize, platformFilter, termId])

  const findActiveCatalogJob = useCallback(async () => {
    if (!termId || !blockId) { setCatalogJob(null); return }
    try {
      const jobs = await getAcademicBulkOperationJobs(headers, { status: 'active', limit: 100 })
      setCatalogJob(jobs.find((job) => matchingCatalogJob(job, termId, blockId, branch)) || null)
      setProgressJob(jobs.find((job) => matchingProgressJob(job, termId, blockId, branch)) || null)
    } catch {
      // The catalog list remains usable even if the shared jobs endpoint is temporarily unavailable.
    }
  }, [blockId, branch, headers, termId])

  useEffect(() => { loadTerms() }, [loadTerms])
  useEffect(() => { loadBlocks() }, [loadBlocks])
  useEffect(() => { setPage(1); setSelected(new Set()); findActiveCatalogJob() }, [branch, termId, blockId, platformFilter, appliedSearch, findActiveCatalogJob])
  useEffect(() => { loadDeliveries() }, [loadDeliveries])

  useEffect(() => {
    if (!catalogJob || !['queued', 'running'].includes(catalogJob.status)) return
    const timer = window.setInterval(async () => {
      try {
        const next = await getAcademicBulkOperationJob(headers, catalogJob.id)
        setCatalogJob(next)
        if (next.status === 'completed') {
          const text = String(next.result_json?.message || next.progress_label || 'Đã lấy danh sách môn từ AP.')
          setMessage(text); setError('')
          await loadDeliveries()
        } else if (next.status === 'failed') {
          setError(next.error_message || next.progress_label || 'Lấy danh sách môn từ AP thất bại.')
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Không đọc được trạng thái tác vụ AP.')
      }
    }, 2000)
    return () => window.clearInterval(timer)
  }, [catalogJob?.id, catalogJob?.status, headers, loadDeliveries])

  useEffect(() => {
    if (!progressJob || !['queued', 'running'].includes(progressJob.status)) return
    const timer = window.setInterval(async () => {
      try {
        const next = await getAcademicBulkOperationJob(headers, progressJob.id)
        setProgressJob(next)
        if (next.status === 'completed') {
          setMessage(String(next.progress_label || 'Đã import tiến độ Udemy.')); setError('')
          await loadDeliveries()
        } else if (next.status === 'failed') {
          setError(next.error_message || next.progress_label || 'Import tiến độ Udemy thất bại.')
        }
      } catch (err) { setError(err instanceof Error ? err.message : 'Không đọc được trạng thái import Udemy.') }
    }, 2000)
    return () => window.clearInterval(timer)
  }, [progressJob?.id, progressJob?.status, headers, loadDeliveries])

  const refreshCatalog = async () => {
    if (!termId || !blockId) { setError('Hãy chọn học kỳ và Block trước khi lấy danh sách môn.'); return }
    setMessage(''); setError('')
    try {
      const response = await createAcademicSubjectCatalogRefreshJob(jsonHeaders, { termId, blockId, branch })
      const job = await getAcademicBulkOperationJob(headers, response.job_id)
      setCatalogJob(job)
      setMessage(response.message)
    } catch (err) { setError(err instanceof Error ? err.message : 'Không tạo được tác vụ lấy danh sách môn.') }
  }

  const changePlatform = async (item: AcademicSubjectDelivery, platform: AcademicLearningPlatform) => {
    setSavingIds((current) => new Set(current).add(item.id)); setError(''); setMessage('')
    try {
      const response = await updateAcademicSubjectDeliveryPlatform(jsonHeaders, item.id, platform)
      setMessage(response.message)
      setResult((current) => ({
        ...current,
        items: current.items.map((row) => row.id === item.id ? { ...row, learning_platform: platform, configured_at: new Date().toISOString() } : row),
        summary: {
          ...current.summary,
          cms_count: current.items.filter((row) => (row.id === item.id ? platform : row.learning_platform) === 'cms').length,
          udemy_count: current.items.filter((row) => (row.id === item.id ? platform : row.learning_platform) === 'udemy').length,
          unassigned_count: current.items.filter((row) => (row.id === item.id ? platform : row.learning_platform) === null).length,
        },
      }))
      await loadDeliveries()
    } catch (err) { setError(err instanceof Error ? err.message : 'Cập nhật nền tảng thất bại.') }
    finally { setSavingIds((current) => { const next = new Set(current); next.delete(item.id); return next }) }
  }

  const bulkChangePlatform = async (platform: AcademicLearningPlatform) => {
    const ids = [...selected]
    if (!ids.length) { setError('Chưa chọn môn cần cập nhật.'); return }
    setSavingIds(new Set(ids)); setError(''); setMessage('')
    try {
      const response = await bulkUpdateAcademicSubjectDeliveryPlatform(jsonHeaders, ids, platform)
      setMessage(response.message); setSelected(new Set())
      await loadDeliveries()
    } catch (err) { setError(err instanceof Error ? err.message : 'Cập nhật hàng loạt thất bại.') }
    finally { setSavingIds(new Set()) }
  }

  const columns: EnterpriseTableColumn<AcademicSubjectDelivery>[] = [
    { key: 'stt', header: 'STT', kind: 'index', width: 54, hideable: false, render: (_item, index) => (page - 1) * pageSize + index + 1 },
    { key: 'subject', header: 'Môn học', kind: 'identity', minWidth: 270, sticky: 'left', hideable: false, render: (item) => <div className="subject-delivery-identity"><b>{item.subject_code}</b><span>{item.subject_name}</span>{item.skill_code ? <small>Skill: {item.skill_code}</small> : null}</div> },
    { key: 'branch', header: 'Hệ', kind: 'status', width: 88, render: (item) => branchLabel(item.branch) },
    { key: 'term', header: 'Học kỳ', kind: 'text', minWidth: 150, render: (item) => item.term_name },
    { key: 'block', header: 'Block', kind: 'text', width: 116, render: (item) => item.block_name },
    { key: 'platform', header: 'Nền tảng', kind: 'actions', minWidth: 292, hideable: false, render: (item) => <PlatformSelector value={item.learning_platform} disabled={savingIds.has(item.id) || Boolean(catalogJob && ['queued', 'running'].includes(catalogJob.status))} onChange={(value) => changePlatform(item, value)} /> },
    { key: 'classes', header: 'Số lớp', kind: 'number', width: 84, render: (item) => item.class_count },
    { key: 'udemyPlan', header: 'Kế hoạch Udemy', kind: 'actions', minWidth: 190, render: (item) => item.learning_platform === 'udemy' ? <div className="udemy-plan-cell"><StatusBadge status={item.has_udemy_plan ? 'active' : 'warning'} label={item.has_udemy_plan ? `v${item.udemy_plan_version || 1} · ${item.udemy_milestone_count || 0} mốc` : 'Chưa có'} /><Link className="btn small secondary" href={`/subject-management/${encodeURIComponent(item.id)}/udemy-plan`}>{item.has_udemy_plan ? 'Xem / sửa' : 'Tạo kế hoạch'}</Link></div> : <span className="muted">Không áp dụng</span> },
    { key: 'udemyProgress', header: 'Tiến độ Udemy', kind: 'actions', minWidth: 292, render: (item) => item.learning_platform === 'udemy' ? <div className="udemy-progress-cell"><div><b>{item.udemy_progress_student_count || 0} sinh viên</b><small>{item.udemy_progress_late_count || 0} chậm · {item.udemy_progress_unmatched_count || 0} cần đối chiếu</small><small>Cập nhật: {formatDateTime(item.last_udemy_import_at)}</small></div><div className="udemy-progress-row-actions"><Link className="btn small secondary" href={`/subject-management/${encodeURIComponent(item.id)}/udemy`}>Xem tiến độ</Link><button className="btn small secondary" type="button" disabled={Boolean(progressJob && ['queued', 'running'].includes(progressJob.status))} onClick={() => { setProgressDelivery(item); setProgressImportOpen(true) }}>Import điểm</button></div></div> : <span className="muted">Không áp dụng</span> },
    { key: 'updated', header: 'Catalog gần nhất', kind: 'date', minWidth: 150, render: (item) => <div><span>{formatDateTime(item.catalog_refreshed_at)}</span>{item.configured_at ? <small>Chọn nền tảng: {formatDateTime(item.configured_at)}</small> : null}</div> },
  ]

  if (!canManage) return <PageRoot className="page-stack enterprise-standard-page subject-management-page"><EnterpriseScreenHeader eyebrow="Danh mục" title="Quản lý môn học" description="Chọn nền tảng CMS hoặc Udemy theo học kỳ và Block." icon="book" tone="blue" breadcrumbs={[{ label: 'Danh mục' }, { label: 'Quản lý môn học' }]} /><section className="card empty-state">Bạn không có quyền quản lý danh mục môn học.</section></PageRoot>

  const jobActive = Boolean(catalogJob && ['queued', 'running'].includes(catalogJob.status))
  return <PageRoot className="page-stack enterprise-standard-page subject-management-page">
    <EnterpriseScreenHeader
      eyebrow="Danh mục"
      title="Quản lý môn học"
      description="Lấy danh sách môn từ AP và chọn nền tảng triển khai theo từng học kỳ, Block: CMS hoặc Udemy."
      icon="book"
      tone="blue"
      breadcrumbs={[{ label: 'Danh mục' }, { label: 'Quản lý môn học' }]}
      secondaryActions={<div className="subject-header-actions"><button className="btn secondary" type="button" onClick={() => setPlanImportOpen(true)}>Import kế hoạch Udemy</button><button className="btn secondary" type="button" disabled={!termId || !blockId || Boolean(progressJob && ['queued', 'running'].includes(progressJob.status))} onClick={() => { setProgressDelivery(null); setProgressImportOpen(true) }}>Import điểm Udemy</button><button className="btn secondary" type="button" disabled={loading} onClick={() => { loadDeliveries(); findActiveCatalogJob() }}>Làm mới</button></div>}
      primaryAction={<button className="btn" type="button" disabled={!termId || !blockId || jobActive} onClick={refreshCatalog}>{jobActive ? 'Đang lấy môn từ AP...' : 'Lấy danh sách tất cả môn'}</button>}
    />

    <InlineNotice notice={message ? noticeSuccess(message) : null} />
    <InlineNotice notice={error ? noticeError(error) : null} />
    {catalogJob ? <PersistentJobNotice job={catalogJob} title="Đồng bộ danh mục môn từ AP" /> : null}
    {progressJob ? <PersistentJobNotice job={progressJob} title="Import tiến độ Udemy" description={progressJob.status === 'completed' ? 'Dữ liệu danh sách môn đã được cập nhật.' : 'Job chạy nền và tiếp tục khi F5 hoặc chuyển trang.'} /> : null}

    <OperationsKpiStrip items={[
      { label: 'Tổng môn', value: result.summary.total, hint: `${branchLabel(branch)} · ${selectedTerm?.term_name || 'Chưa chọn kỳ'} · ${selectedBlock?.block_name || 'Chưa chọn Block'}` },
      { label: 'CMS', value: result.summary.cms_count, hint: 'Có thể dùng map Course và Full CMS', tone: 'info' },
      { label: 'Udemy', value: result.summary.udemy_count, hint: 'Dùng kế hoạch và import điểm Udemy', tone: 'success' },
      { label: 'Chưa chọn', value: result.summary.unassigned_count, hint: 'Cần phân loại trước khi vận hành', tone: 'warning' },
      { label: 'Số lớp AP', value: result.summary.class_count, hint: 'Lớp đã đồng bộ trong phạm vi hiện tại' },
    ]} />

    <CompactFilterBar actions={<div className="subject-filter-actions"><button className="btn secondary" type="button" onClick={() => { setAppliedSearch(search.trim()); setPage(1) }}>Áp dụng</button><button className="btn secondary" type="button" disabled={!search && platformFilter === 'all'} onClick={() => { setSearch(''); setAppliedSearch(''); setPlatformFilter('all'); setPage(1) }}>Xóa lọc</button></div>}>
      <label>Hệ<select className="input" value={branch} onChange={(event) => { setBranch(event.target.value as Branch); setTermId(''); setBlockId(''); setPage(1) }}><option value="poly">Poly</option><option value="ptcd">PTCĐ</option></select></label>
      <label>Học kỳ<select className="input" value={termId} onChange={(event) => { setTermId(event.target.value); setBlockId(''); setPage(1) }}><option value="">Chọn học kỳ</option>{terms.map((item) => <option value={item.id} key={item.id}>{item.term_name}</option>)}</select></label>
      <label>Block<select className="input" value={blockId} onChange={(event) => { setBlockId(event.target.value); setPage(1) }}><option value="">Chọn Block</option>{blocks.map((item) => <option value={item.id} key={item.id}>{item.block_name}</option>)}</select></label>
      <label>Nền tảng<select className="input" value={platformFilter} onChange={(event) => { setPlatformFilter(event.target.value as PlatformFilter); setPage(1) }}><option value="all">Tất cả</option><option value="unassigned">Chưa chọn</option><option value="cms">CMS</option><option value="udemy">Udemy</option></select></label>
      <label>Tìm kiếm<input className="input" value={search} onChange={(event) => setSearch(event.target.value)} onKeyDown={(event) => { if (event.key === 'Enter') { setAppliedSearch(search.trim()); setPage(1) } }} placeholder="Mã hoặc tên môn..." /></label>
    </CompactFilterBar>

    <WorkspaceSection
      title="Danh sách môn theo học kỳ và Block"
      description="Mỗi môn chỉ có một lựa chọn trong phạm vi hiện tại. Đổi CMS/Udemy không xóa dữ liệu lịch sử."
      actions={<div className="subject-bulk-actions"><span>Đã chọn <b>{selected.size}</b></span><button className="btn small secondary" disabled={!selected.size || savingIds.size > 0} onClick={() => bulkChangePlatform('cms')}>Chọn CMS</button><button className="btn small secondary" disabled={!selected.size || savingIds.size > 0} onClick={() => bulkChangePlatform('udemy')}>Chọn Udemy</button><button className="btn small secondary" disabled={!selected.size || savingIds.size > 0} onClick={() => bulkChangePlatform(null)}>Bỏ lựa chọn</button></div>}
    >
      <EnterpriseDataTable
        tableId="subject-deliveries-batch33"
        caption="Danh sách môn học CMS và Udemy"
        rows={result.items}
        columns={columns}
        rowKey={(item) => item.id}
        density="compact"
        loading={loading}
        error={error || undefined}
        onRetry={loadDeliveries}
        emptyTitle={termId && blockId ? 'Chưa có danh sách môn' : 'Hãy chọn học kỳ và Block'}
        emptyDescription={termId && blockId ? 'Bấm “Lấy danh sách tất cả môn” để đồng bộ catalog từ AP.' : 'Danh sách môn được quản lý riêng theo học kỳ và Block.'}
        selection={{
          selectedKeys: selected,
          onToggle: (item) => setSelected((current) => { const next = new Set(current); if (next.has(item.id)) next.delete(item.id); else next.add(item.id); return next }),
          onTogglePage: (rows, checked) => setSelected((current) => { const next = new Set(current); rows.forEach((item) => checked ? next.add(item.id) : next.delete(item.id)); return next }),
        }}
        page={result.page}
        pageSize={result.page_size}
        total={result.total}
        totalPages={result.total_pages}
        onPageChange={setPage}
        onPageSizeChange={(value) => { setPageSize(value); setPage(1) }}
        label="môn"
        stickyHorizontalScroll
      />
    </WorkspaceSection>
    <UdemyPlanImportDialog
      open={planImportOpen}
      branch={branch}
      headers={headers}
      jsonHeaders={jsonHeaders}
      onClose={() => setPlanImportOpen(false)}
      onCommitted={(text) => { setMessage(text); setError(''); loadDeliveries() }}
    />
    <UdemyProgressImportDialog
      open={progressImportOpen}
      branch={branch}
      termId={termId}
      blockId={blockId}
      delivery={progressDelivery}
      headers={headers}
      onClose={() => { setProgressImportOpen(false); setProgressDelivery(null) }}
      onQueued={async (response) => {
        setMessage(response.message); setError('')
        try { setProgressJob(await getAcademicBulkOperationJob(headers, response.job_id)) } catch { /* job will be rediscovered on refresh */ }
        if (response.status === 'completed') loadDeliveries()
      }}
    />
  </PageRoot>
}
