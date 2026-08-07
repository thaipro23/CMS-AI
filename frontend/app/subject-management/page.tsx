'use client'

import Link from 'next/link'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { useAppContext } from '../../context/AppContext'
import {
  bulkUpdateAcademicSubjectDeliveryPlatform,
  createAcademicSubjectCatalogRefreshJob,
  getAcademicBulkOperationJob,
  getAcademicBulkOperationJobs,
  getAcademicSubjectDeliveries,
  getAcademicTerms,
} from '../../lib/api'
import type {
  AcademicBulkOperationJob,
  AcademicLearningPlatform,
  AcademicSubjectDelivery,
  AcademicSubjectDeliveryBlock,
  AcademicSubjectDeliveryListResponse,
  AcademicTerm,
} from '../../types'
import { PageRoot } from '../../components/layout/PageHeader'
import { EnterpriseScreenHeader } from '../../components/layout/EnterpriseDesignContract'
import { EnterpriseDataTable, type EnterpriseTableColumn } from '../../components/table/EnterpriseDataTable'
import { CompactFilterBar, OperationsKpiStrip, WorkspaceSection } from '../../components/operations/OperationsWorkspace'
import { InlineNotice, noticeError, noticeInfo, noticeSuccess } from '../../components/ui/InlineNotice'
import { PersistentJobNotice } from '../../components/ui/PersistentJobNotice'
import { StatusBadge } from '../../components/ui/StatusBadge'
import { UdemyPlanImportDialog } from '../../components/subject-management/UdemyPlanImportDialog'
import { UdemyProgressImportDialog } from '../../components/subject-management/UdemyProgressImportDialog'


type Branch = 'poly' | 'ptcd'
type PlatformFilter = 'all' | 'unassigned' | 'cms' | 'udemy' | 'mixed'

const EMPTY_RESULT: AcademicSubjectDeliveryListResponse = {
  items: [],
  total: 0,
  page: 1,
  page_size: 50,
  total_pages: 0,
  has_next: false,
  summary: { total: 0, cms_count: 0, udemy_count: 0, unassigned_count: 0, mixed_count: 0, class_count: 0, scope_label: 'Theo học kỳ' },
}

function branchLabel(value?: string | null) { return String(value || '').toLowerCase() === 'ptcd' ? 'PTCĐ' : 'Poly' }
function platformLabel(value?: AcademicLearningPlatform) { return value === 'cms' ? 'CMS' : value === 'udemy' ? 'Udemy' : 'Chưa chọn' }
function formatDateTime(value?: string | null) {
  if (!value) return 'Chưa có'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : new Intl.DateTimeFormat('vi-VN', { dateStyle: 'short', timeStyle: 'short' }).format(date)
}

function matchingProgressJob(job: AcademicBulkOperationJob, termId: string, branch: string) {
  return job.job_type === 'udemy_progress_import'
    && job.term_id === termId
    && String(job.branch || '').toLowerCase() === branch.toLowerCase()
    && ['queued', 'running'].includes(job.status)
}

function matchingCatalogJob(job: AcademicBulkOperationJob, termId: string, branch: string) {
  const request = job.request_json || {}
  return job.job_type === 'subject_catalog_refresh'
    && job.term_id === termId
    && String(job.branch || '').toLowerCase() === branch.toLowerCase()
    && !request.block_id
    && ['queued', 'running'].includes(job.status)
}

function PlatformSelector({
  value,
  mixed,
  disabled,
  onChange,
}: {
  value: AcademicLearningPlatform
  mixed?: boolean
  disabled?: boolean
  onChange: (value: AcademicLearningPlatform) => void
}) {
  const options: Array<{ value: AcademicLearningPlatform; label: string }> = [
    { value: null, label: 'Chưa chọn' },
    { value: 'cms', label: 'CMS' },
    { value: 'udemy', label: 'Udemy' },
  ]
  return <div className="subject-platform-control">
    {mixed ? <StatusBadge status="warning" label="Khác nhau giữa các Block" /> : null}
    <div className="subject-platform-segment" role="radiogroup" aria-label="Nền tảng môn học trong học kỳ">
      {options.map((option) => <button
        key={option.label}
        type="button"
        role="radio"
        aria-checked={!mixed && value === option.value}
        className={`subject-platform-option ${!mixed && value === option.value ? 'is-active' : ''} ${option.value || 'unassigned'}`}
        disabled={disabled}
        onClick={() => onChange(option.value)}
      >{option.label}</button>)}
    </div>
  </div>
}

function blockDelivery(item: AcademicSubjectDelivery, block: AcademicSubjectDeliveryBlock): AcademicSubjectDelivery {
  return {
    ...item,
    id: block.id,
    block_id: block.block_id,
    block_name: block.block_name,
    learning_platform: block.learning_platform,
    class_count: block.class_count,
    campus_count: block.campus_count,
    has_udemy_plan: block.has_udemy_plan,
    udemy_plan_version: block.udemy_plan_version,
    udemy_milestone_count: block.udemy_milestone_count,
    udemy_progress_student_count: block.udemy_progress_student_count,
    udemy_progress_late_count: block.udemy_progress_late_count,
    udemy_progress_unmatched_count: block.udemy_progress_unmatched_count,
    last_udemy_import_at: block.last_udemy_import_at,
    delivery_ids: [block.id],
    block_count: 1,
    block_names: [block.block_name],
    platform_consistent: true,
    platform_values: [block.learning_platform],
    management_scope: 'delivery',
    block_deliveries: [],
  }
}

export default function SubjectManagementPage() {
  const { authHeaders, can } = useAppContext()
  const headers = useMemo(() => authHeaders(), [authHeaders])
  const jsonHeaders = useMemo(() => authHeaders(true), [authHeaders])
  const canManage = can('manage_settings')

  const [branch, setBranch] = useState<Branch>('poly')
  const [terms, setTerms] = useState<AcademicTerm[]>([])
  const [termId, setTermId] = useState('')
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

  const loadDeliveries = useCallback(async () => {
    if (!canManage || !termId) { setResult(EMPTY_RESULT); return }
    setLoading(true); setError('')
    try {
      const response = await getAcademicSubjectDeliveries(headers, {
        termId,
        branch,
        platform: platformFilter === 'unassigned' ? null : platformFilter,
        managementScope: 'term',
        search: appliedSearch,
        page,
        pageSize,
      })
      setResult(response)
      setSelected((current) => new Set([...current].filter((id) => response.items.some((item) => item.id === id))))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Không tải được danh sách môn học.')
    } finally { setLoading(false) }
  }, [appliedSearch, branch, canManage, headers, page, pageSize, platformFilter, termId])

  const findActiveCatalogJob = useCallback(async () => {
    if (!termId) { setCatalogJob(null); setProgressJob(null); return }
    try {
      const jobs = await getAcademicBulkOperationJobs(headers, { status: 'active', limit: 100 })
      setCatalogJob(jobs.find((job) => matchingCatalogJob(job, termId, branch)) || null)
      setProgressJob(jobs.find((job) => matchingProgressJob(job, termId, branch)) || null)
    } catch {
      // Danh sách môn vẫn dùng được nếu endpoint job tạm thời không phản hồi.
    }
  }, [branch, headers, termId])

  useEffect(() => { loadTerms() }, [loadTerms])
  useEffect(() => { setPage(1); setSelected(new Set()); findActiveCatalogJob() }, [branch, termId, platformFilter, appliedSearch, findActiveCatalogJob])
  useEffect(() => { loadDeliveries() }, [loadDeliveries])

  useEffect(() => {
    if (!catalogJob || !['queued', 'running'].includes(catalogJob.status)) return
    const timer = window.setInterval(async () => {
      try {
        const next = await getAcademicBulkOperationJob(headers, catalogJob.id)
        setCatalogJob(next)
        if (next.status === 'completed') {
          setMessage(String(next.result_json?.message || next.progress_label || 'Đã lấy danh sách môn từ AP.'))
          setError('')
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
          setMessage(String(next.progress_label || 'Đã import tiến độ Udemy.'))
          setError('')
          await loadDeliveries()
        } else if (next.status === 'failed') {
          setError(next.error_message || next.progress_label || 'Import tiến độ Udemy thất bại.')
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Không đọc được trạng thái import Udemy.')
      }
    }, 2000)
    return () => window.clearInterval(timer)
  }, [progressJob?.id, progressJob?.status, headers, loadDeliveries])

  const refreshCatalog = async () => {
    if (!termId) { setError('Hãy chọn học kỳ trước khi lấy danh sách môn.'); return }
    setMessage(''); setError('')
    try {
      const response = await createAcademicSubjectCatalogRefreshJob(jsonHeaders, { termId, blockId: null, branch })
      const job = await getAcademicBulkOperationJob(headers, response.job_id)
      setCatalogJob(job)
      setMessage(response.message)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Không tạo được tác vụ lấy danh sách môn.')
    }
  }

  const changePlatform = async (item: AcademicSubjectDelivery, platform: AcademicLearningPlatform) => {
    const ids = item.delivery_ids?.length ? item.delivery_ids : [item.id]
    setSavingIds((current) => new Set(current).add(item.id)); setError(''); setMessage('')
    try {
      await bulkUpdateAcademicSubjectDeliveryPlatform(jsonHeaders, ids, platform)
      setMessage(`Đã đặt ${item.subject_code} thành ${platformLabel(platform)} cho toàn bộ ${ids.length} Block trong ${item.term_name}.`)
      await loadDeliveries()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Cập nhật nền tảng thất bại.')
    } finally {
      setSavingIds((current) => { const next = new Set(current); next.delete(item.id); return next })
    }
  }

  const bulkChangePlatform = async (platform: AcademicLearningPlatform) => {
    const rows = result.items.filter((item) => selected.has(item.id))
    const ids = [...new Set(rows.flatMap((item) => item.delivery_ids?.length ? item.delivery_ids : [item.id]))]
    if (!rows.length || !ids.length) { setError('Chưa chọn môn cần cập nhật.'); return }
    setSavingIds(new Set(rows.map((item) => item.id))); setError(''); setMessage('')
    try {
      await bulkUpdateAcademicSubjectDeliveryPlatform(jsonHeaders, ids, platform)
      setMessage(`Đã đặt ${rows.length} môn thành ${platformLabel(platform)} trên toàn bộ ${ids.length} phạm vi Block của học kỳ.`)
      setSelected(new Set())
      await loadDeliveries()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Cập nhật hàng loạt thất bại.')
    } finally { setSavingIds(new Set()) }
  }

  const openProgressImport = (item: AcademicSubjectDelivery, block: AcademicSubjectDeliveryBlock) => {
    setProgressDelivery(blockDelivery(item, block))
    setProgressImportOpen(true)
  }

  const columns: EnterpriseTableColumn<AcademicSubjectDelivery>[] = [
    { key: 'stt', header: 'STT', kind: 'index', width: 54, hideable: false, render: (_item, index) => (page - 1) * pageSize + index + 1 },
    { key: 'subject', header: 'Môn học', kind: 'identity', minWidth: 280, sticky: 'left', hideable: false, render: (item) => <div className="subject-delivery-identity"><b>{item.subject_code}</b><span>{item.subject_name}</span>{item.skill_code ? <small>Skill: {item.skill_code}</small> : null}</div> },
    { key: 'branch', header: 'Hệ', kind: 'status', width: 88, render: (item) => branchLabel(item.branch) },
    { key: 'term', header: 'Học kỳ', kind: 'text', minWidth: 150, render: (item) => item.term_name },
    { key: 'blocks', header: 'Phạm vi Block', kind: 'text', minWidth: 170, render: (item) => <div><b>{item.block_count || item.block_deliveries?.length || 1} Block</b><small>{item.block_names?.join(' · ') || item.block_name}</small></div> },
    { key: 'platform', header: 'Nền tảng học kỳ', kind: 'actions', minWidth: 310, hideable: false, render: (item) => <PlatformSelector value={item.learning_platform} mixed={item.platform_consistent === false} disabled={savingIds.has(item.id) || Boolean(catalogJob && ['queued', 'running'].includes(catalogJob.status))} onChange={(value) => void changePlatform(item, value)} /> },
    { key: 'classes', header: 'Số lớp', kind: 'number', width: 84, render: (item) => item.class_count },
    { key: 'blockOperations', header: 'Vận hành theo Block', kind: 'actions', minWidth: 300, render: (item) => <details className="subject-block-operations"><summary>{item.block_deliveries?.length || 0} Block · mở chi tiết</summary><div className="subject-block-operation-list">{(item.block_deliveries || []).map((block) => <div className="subject-block-operation-row" key={block.id}><div><b>{block.block_name}</b><small>{block.class_count} lớp · {platformLabel(block.learning_platform)}</small></div>{block.learning_platform === 'udemy' ? <div className="subject-block-operation-actions"><Link className="btn small secondary" href={`/subject-management/${encodeURIComponent(block.id)}/udemy`}>Xem tiến độ</Link><Link className="btn small secondary" href={`/subject-management/${encodeURIComponent(block.id)}/udemy-plan`}>{block.has_udemy_plan ? 'Kế hoạch' : 'Tạo kế hoạch'}</Link><button className="btn small secondary" type="button" disabled={Boolean(progressJob && ['queued', 'running'].includes(progressJob.status))} onClick={() => openProgressImport(item, block)}>Import điểm Udemy</button></div> : <StatusBadge status={block.learning_platform === 'cms' ? 'info' : 'warning'} label={platformLabel(block.learning_platform)} />}</div>)}</div></details> },
    { key: 'updated', header: 'Cập nhật gần nhất', kind: 'date', minWidth: 165, render: (item) => <div><span>{formatDateTime(item.catalog_refreshed_at)}</span>{item.configured_at ? <small>Chọn nền tảng: {formatDateTime(item.configured_at)}</small> : null}</div> },
  ]

  if (!canManage) return <PageRoot className="page-stack enterprise-standard-page subject-management-page"><EnterpriseScreenHeader eyebrow="Danh mục" title="Quản lý môn học" description="Chọn nền tảng CMS hoặc Udemy theo học kỳ." icon="book" tone="blue" breadcrumbs={[{ label: 'Danh mục' }, { label: 'Quản lý môn học' }]} /><section className="card empty-state">Bạn không có quyền quản lý danh mục môn học.</section></PageRoot>

  const jobActive = Boolean(catalogJob && ['queued', 'running'].includes(catalogJob.status))
  return <PageRoot className="page-stack enterprise-standard-page subject-management-page">
    <EnterpriseScreenHeader
      eyebrow="Danh mục"
      title="Quản lý môn học"
      description="Mỗi môn được chọn CMS hoặc Udemy một lần cho cả học kỳ. Các nghiệp vụ lớp, kế hoạch và tiến độ vẫn vận hành riêng theo từng Block."
      icon="book"
      tone="blue"
      breadcrumbs={[{ label: 'Danh mục' }, { label: 'Quản lý môn học' }]}
      secondaryActions={<div className="subject-header-actions"><button className="btn secondary" type="button" onClick={() => setPlanImportOpen(true)}>Import kế hoạch Udemy</button><button className="btn secondary" type="button" disabled={loading} onClick={() => { loadDeliveries(); findActiveCatalogJob() }}>Làm mới</button></div>}
      primaryAction={<button className="btn" type="button" disabled={!termId || jobActive} onClick={() => void refreshCatalog()}>{jobActive ? 'Đang lấy môn từ AP...' : 'Lấy danh sách tất cả môn'}</button>}
    />

    <InlineNotice notice={noticeInfo('Kỳ mới kế thừa lựa chọn CMS/Udemy nhất quán từ kỳ gần nhất để không phải tích lại từ đầu. Bạn có thể thêm, đổi hoặc bỏ chọn; thay đổi sẽ áp dụng đồng thời cho mọi Block của môn trong học kỳ đang chọn.', 'Quy tắc quản lý theo học kỳ')} />
    <InlineNotice notice={message ? noticeSuccess(message) : null} />
    <InlineNotice notice={error ? noticeError(error) : null} />
    {catalogJob ? <PersistentJobNotice job={catalogJob} title="Đồng bộ danh mục môn từ AP" /> : null}
    {progressJob ? <PersistentJobNotice job={progressJob} title="Import tiến độ Udemy" description={progressJob.status === 'completed' ? 'Dữ liệu danh sách môn đã được cập nhật.' : 'Job chạy nền và tiếp tục khi F5 hoặc chuyển trang.'} /> : null}

    <OperationsKpiStrip items={[
      { label: 'Tổng môn', value: result.summary.total, hint: `${branchLabel(branch)} · ${selectedTerm?.term_name || 'Chưa chọn kỳ'}` },
      { label: 'CMS', value: result.summary.cms_count, hint: 'Áp dụng cho toàn bộ Block trong kỳ', tone: 'info' },
      { label: 'Udemy', value: result.summary.udemy_count, hint: 'Vận hành chi tiết theo từng Block', tone: 'success' },
      { label: 'Chưa chọn', value: result.summary.unassigned_count, hint: 'Môn mới hoặc kỳ trước chưa có lựa chọn nhất quán', tone: 'warning' },
      { label: 'Chưa đồng nhất', value: result.summary.mixed_count || 0, hint: 'Dữ liệu cũ khác nhau giữa các Block', tone: 'warning' },
      { label: 'Số lớp AP', value: result.summary.class_count, hint: 'Tổng số lớp của mọi Block trong kỳ' },
    ]} />

    <CompactFilterBar actions={<div className="subject-filter-actions"><button className="btn secondary" type="button" onClick={() => { setAppliedSearch(search.trim()); setPage(1) }}>Áp dụng</button><button className="btn secondary" type="button" disabled={!search && platformFilter === 'all'} onClick={() => { setSearch(''); setAppliedSearch(''); setPlatformFilter('all'); setPage(1) }}>Xóa lọc</button></div>}>
      <label>Hệ<select className="input" value={branch} onChange={(event) => { setBranch(event.target.value as Branch); setTermId(''); setPage(1) }}><option value="poly">Poly</option><option value="ptcd">PTCĐ</option></select></label>
      <label>Học kỳ<select className="input" value={termId} onChange={(event) => { setTermId(event.target.value); setPage(1) }}><option value="">Chọn học kỳ</option>{terms.map((item) => <option value={item.id} key={item.id}>{item.term_name}</option>)}</select></label>
      <label>Nền tảng<select className="input" value={platformFilter} onChange={(event) => { setPlatformFilter(event.target.value as PlatformFilter); setPage(1) }}><option value="all">Tất cả</option><option value="unassigned">Chưa chọn</option><option value="cms">CMS</option><option value="udemy">Udemy</option><option value="mixed">Chưa đồng nhất giữa Block</option></select></label>
      <label>Tìm kiếm<input className="input" value={search} onChange={(event) => setSearch(event.target.value)} onKeyDown={(event) => { if (event.key === 'Enter') { setAppliedSearch(search.trim()); setPage(1) } }} placeholder="Mã hoặc tên môn..." /></label>
    </CompactFilterBar>

    <WorkspaceSection
      title="Danh sách môn theo học kỳ"
      description="Mỗi môn chỉ có một lựa chọn nền tảng cho cả học kỳ. Mở cột Vận hành theo Block để vào kế hoạch, tiến độ hoặc import của Block cụ thể."
      actions={<div className="subject-bulk-actions"><span>Đã chọn <b>{selected.size}</b></span><button className="btn small secondary" disabled={!selected.size || savingIds.size > 0} onClick={() => void bulkChangePlatform('cms')}>Chọn CMS</button><button className="btn small secondary" disabled={!selected.size || savingIds.size > 0} onClick={() => void bulkChangePlatform('udemy')}>Chọn Udemy</button><button className="btn small secondary" disabled={!selected.size || savingIds.size > 0} onClick={() => void bulkChangePlatform(null)}>Bỏ lựa chọn</button></div>}
    >
      <EnterpriseDataTable
        tableId="subject-deliveries-term-management-batch35-2"
        caption="Danh sách môn học CMS và Udemy theo học kỳ"
        rows={result.items}
        columns={columns}
        rowKey={(item) => item.id}
        density="compact"
        loading={loading}
        error={error || undefined}
        onRetry={loadDeliveries}
        emptyTitle={termId ? 'Chưa có danh sách môn' : 'Hãy chọn học kỳ'}
        emptyDescription={termId ? 'Bấm “Lấy danh sách tất cả môn” để đồng bộ catalog từ AP cho toàn bộ Block của học kỳ.' : 'Màn Quản lý môn học chỉ phân loại theo học kỳ; các nghiệp vụ phía sau vẫn theo Block.'}
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
      termId={progressDelivery?.term_id || termId}
      blockId={progressDelivery?.block_id || ''}
      delivery={progressDelivery}
      headers={headers}
      onClose={() => { setProgressImportOpen(false); setProgressDelivery(null) }}
      onQueued={async (response) => {
        setMessage(response.message); setError('')
        try { setProgressJob(await getAcademicBulkOperationJob(headers, response.job_id)) } catch { /* job sẽ được tìm lại khi làm mới */ }
        if (response.status === 'completed') loadDeliveries()
      }}
    />
  </PageRoot>
}
