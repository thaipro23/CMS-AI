'use client'

import { InlineNotice, type InlineNoticeData } from '../../components/ui/InlineNotice'

import { useEffect, useMemo, useState } from 'react'
import { useAppContext } from '../../context/AppContext'
import { enqueueAcademicApSyncJob, getAcademicApSyncJob, getAcademicApSyncJobs, getAcademicApSyncOptions } from '../../lib/api'
import { PageRoot } from '../../components/layout/PageHeader'
import { EnterpriseScreenHeader } from '../../components/layout/EnterpriseDesignContract'
import { OperationsKpiStrip, WorkspaceSection } from '../../components/operations/OperationsWorkspace'
import { StatusBadge } from '../../components/ui/StatusBadge'
import { AccessibleDialog } from '../../components/ui/AccessibleDialog'
import { AcademicAPOption, AcademicAPSyncOptions, AcademicSyncResult, AcademicSyncRun } from '../../types'
import { ContentNotice } from '../../components/ui/ContentNotice'

type BranchCode = 'poly' | 'ptcd'
type BranchState = Record<BranchCode, AcademicAPSyncOptions>
type SyncConfirm = { branches: BranchCode[]; runnable: BranchCode[]; label: string; campusCount: number; subjectCount: number } | null

const BRANCHES: Array<{ value: BranchCode; label: string }> = [
  { value: 'poly', label: 'Poly' },
  { value: 'ptcd', label: 'PTCĐ' },
]

const EMPTY_OPTIONS: AcademicAPSyncOptions = { branches: [], campuses: [], terms: [], subjects: [], warnings: [], selected_subject_codes: [], selected_subject_count: 0, cms_subject_count: 0, udemy_subject_count: 0 }

function optionValues(items: AcademicAPOption[] = []) {
  return items.map((item) => String(item.value || '').trim().toLowerCase()).filter(Boolean)
}

function uniqueTermOptions(optionsByBranch: BranchState) {
  const seen = new Set<string>()
  const out: AcademicAPOption[] = []
  for (const branch of BRANCHES) {
    for (const item of optionsByBranch[branch.value].terms || []) {
      const value = String(item.value || '').trim()
      if (value && !seen.has(value)) {
        seen.add(value)
        out.push(item)
      }
    }
  }
  return out
}

function summarizeCounters(result: AcademicSyncResult) {
  const counters = result.counters || {}
  const parts = [
    `lớp ${counters.classes || 0}`,
    `sinh viên ${counters.students || 0}`,
    `GV ${counters.teachers || 0}`,
    `môn ${counters.subjects || 0}`,
    `lỗi ${counters.errors || 0}`,
  ]
  return parts.join(' · ')
}

function countersFromRun(run: AcademicSyncRun): Record<string, number> {
  const data = run.counters_json || {}
  return {
    terms: Number(data.terms || 0),
    blocks: Number(data.blocks || 0),
    subjects: Number(data.subjects || 0),
    classes: Number(data.classes || 0),
    teachers: Number(data.teachers || 0),
    students: Number(data.students || 0),
    teacher_assignments: Number(data.teacher_assignments || 0),
    class_students: Number(data.class_students || 0),
    skipped_empty_classes: Number(data.skipped_empty_classes || 0),
    errors: Number(data.errors || 0),
  }
}

function resultFromRun(run: AcademicSyncRun): AcademicSyncResult {
  return {
    ok: run.status === 'completed',
    message: run.status === 'completed' ? 'Đã đồng bộ dữ liệu AP' : (run.error_message || 'Đồng bộ AP đang xử lý'),
    sync_run: run,
    counters: countersFromRun(run),
  }
}

function runProgress(run: AcademicSyncRun) {
  const progress = run.counters_json?.progress || {}
  const current = Number(progress.current || 0)
  const total = Math.max(1, Number(progress.total || 1))
  const percent = Math.max(0, Math.min(100, Math.round((current / total) * 100)))
  return { current, total, percent, label: String(progress.label || run.error_message || 'Đang chờ xử lý') }
}

function isRunActive(run?: AcademicSyncRun | null) {
  return Boolean(run && ['queued', 'running'].includes(run.status))
}

export default function ApSyncPage() {
  const { authHeaders, can } = useAppContext()
  const headers = useMemo(() => authHeaders(), [authHeaders])
  const jsonHeaders = useMemo(() => authHeaders(true), [authHeaders])
  const [termName, setTermName] = useState('')
  const [selectedBranch, setSelectedBranch] = useState<BranchCode>('poly')
  const [optionsByBranch, setOptionsByBranch] = useState<BranchState>({ poly: EMPTY_OPTIONS, ptcd: EMPTY_OPTIONS })
  const [loadingOptions, setLoadingOptions] = useState(false)
  const [running, setRunning] = useState(false)
  const [dryRun, setDryRun] = useState(false)
  const [message, setMessage] = useState<InlineNoticeData | null>(null)
  const notify = (body: string, type: InlineNoticeData['type'] = 'error') => setMessage({ type, body })
  const [lastResults, setLastResults] = useState<Array<{ branch: BranchCode; result: AcademicSyncResult }>>([])
  const [activeRuns, setActiveRuns] = useState<Array<{ branch: BranchCode; run: AcademicSyncRun }>>([])
  const [syncConfirm, setSyncConfirm] = useState<SyncConfirm>(null)

  const termOptions = useMemo(() => uniqueTermOptions(optionsByBranch), [optionsByBranch])
  const currentBranchOptions = optionsByBranch[selectedBranch] || EMPTY_OPTIONS
  const totalCampuses = BRANCHES.reduce((sum, branch) => sum + (optionsByBranch[branch.value].campuses?.length || 0), 0)
  const totalSelectedSubjects = BRANCHES.reduce((sum, branch) => sum + Number(optionsByBranch[branch.value].selected_subject_count || 0), 0)
  const canManageAcademicOps = can('academic.catalog.manage')

  const loadOptions = async (clearMessage = true) => {
    setLoadingOptions(true)
    if (clearMessage) setMessage(null)
    try {
      const [poly, ptcd] = await Promise.all([
        getAcademicApSyncOptions(headers, { termName, branch: 'poly', includeSubjects: false }),
        getAcademicApSyncOptions(headers, { termName, branch: 'ptcd', includeSubjects: false }),
      ])
      setOptionsByBranch({ poly, ptcd })
      const availableTerms = uniqueTermOptions({ poly, ptcd })
      const availableValues = new Set(availableTerms.map((item) => String(item.value || '').trim()))
      if (availableTerms.length && !availableValues.has(termName.trim())) {
        setTermName(String(availableTerms[0].value || ''))
      }
    } catch (error) {
      notify(error instanceof Error ? error.message : 'Không tải được dữ liệu học kỳ/hệ/cơ sở')
    } finally {
      setLoadingOptions(false)
    }
  }

  const refreshActiveRuns = async () => {
    const jobs = await Promise.all(BRANCHES.map(async (branch) => {
      const runs = await getAcademicApSyncJobs(headers, { termName, branch: branch.value, status: 'active', limit: 5 })
      return runs.map((run) => ({ branch: branch.value, run }))
    }))
    const flattened = jobs.flat().filter((item) => isRunActive(item.run))
    setActiveRuns(flattened)
    return flattened
  }

  useEffect(() => {
    if (!canManageAcademicOps) return
    loadOptions()
    refreshActiveRuns().catch(() => null)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [canManageAcademicOps, headers, termName])

  useEffect(() => {
    if (!canManageAcademicOps || !activeRuns.length) return
    let canceled = false
    let timer: ReturnType<typeof setTimeout> | null = null
    const poll = async () => {
      try {
        const next = await Promise.all(activeRuns.map(async (item) => ({ branch: item.branch, run: await getAcademicApSyncJob(headers, item.run.id) })))
        if (canceled) return
        setActiveRuns(next.filter((item) => isRunActive(item.run)))
        const finished = next.filter((item) => !isRunActive(item.run))
        if (finished.length) {
          setLastResults((current) => {
            const mapped = finished.map((item) => ({ branch: item.branch, result: resultFromRun(item.run) }))
            const seen = new Set(mapped.map((item) => item.result.sync_run.id))
            return [...mapped, ...current.filter((item) => !seen.has(item.result.sync_run.id))].slice(0, 10)
          })
          if (finished.some((item) => item.run.status === 'failed')) {
            notify('Có tác vụ đồng bộ AP thất bại. Xem chi tiết trong bảng kết quả gần nhất.')
          } else {
            const onlyDryRun = finished.every((item) => String(item.run.mode || '').includes('dry_run'))
            notify(onlyDryRun ? 'Đã kiểm tra kế hoạch đồng bộ AP.' : 'Đã chạy xong đồng bộ AP.', 'success')
            await loadOptions(false)
          }
        }
        if (next.some((item) => isRunActive(item.run))) timer = setTimeout(poll, 2000)
      } catch (error) {
        if (!canceled) {
          notify(error instanceof Error ? error.message : 'Không kiểm tra được trạng thái tác vụ đồng bộ AP')
          timer = setTimeout(poll, 4000)
        }
      }
    }
    timer = setTimeout(poll, 1000)
    return () => { canceled = true; if (timer) clearTimeout(timer) }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeRuns.map((item) => item.run.id).join(','), canManageAcademicOps, headers])

  const requestRunForBranches = (branches: BranchCode[]) => {
    if (!canManageAcademicOps) {
      notify('Bạn không có quyền đồng bộ AP.')
      return
    }
    const normalizedTerm = termName.trim()
    if (!normalizedTerm) {
      notify('Vui lòng chọn kỳ trước khi đồng bộ.')
      return
    }
    const runnable = branches.filter((branch) => optionValues(optionsByBranch[branch].campuses).length > 0 && Number(optionsByBranch[branch].selected_subject_count || 0) > 0)
    if (!runnable.length) {
      notify('Chưa có phạm vi AP hợp lệ. Hãy bảo đảm có cơ sở đang bật và đã chọn CMS/Udemy cho ít nhất một môn trong Quản lý môn học.')
      return
    }
    const label = branches.length > 1 ? 'các hệ có môn đã chọn CMS/Udemy' : `hệ ${BRANCHES.find((item) => item.value === branches[0])?.label || branches[0]}`
    const campusCount = runnable.reduce((sum, branch) => sum + optionValues(optionsByBranch[branch].campuses).length, 0)
    const subjectCount = runnable.reduce((sum, branch) => sum + Number(optionsByBranch[branch].selected_subject_count || 0), 0)
    setSyncConfirm({ branches, runnable, label, campusCount, subjectCount })
  }

  const executeConfirmedSync = async () => {
    if (!syncConfirm) return
    const normalizedTerm = termName.trim()
    const runnable = syncConfirm.runnable
    setRunning(true)
    setMessage(null)
    setLastResults([])
    try {
      const queuedRuns: Array<{ branch: BranchCode; run: AcademicSyncRun }> = []
      setSyncConfirm(null)
      for (const branch of runnable) {
        const campuses = optionValues(optionsByBranch[branch].campuses)
        const result = await enqueueAcademicApSyncJob(jsonHeaders, {
          term_name: normalizedTerm,
          sync_scope: 'all',
          branch,
          campuses,
          subject_codes: optionsByBranch[branch].selected_subject_codes || [],
          max_subjects: 0,
          dry_run: dryRun,
        })
        queuedRuns.push({ branch, run: result.sync_run })
      }
      setActiveRuns((current) => {
        const seen = new Set(current.map((item) => item.run.id))
        return [...queuedRuns, ...current.filter((item) => !seen.has(item.run.id))]
      })
      notify(dryRun ? 'Đã xếp hàng kiểm tra kế hoạch AP.' : 'Đã xếp hàng đồng bộ AP. Bạn có thể xem tiến trình tại Tác vụ nền.', 'info')
    } catch (error) {
      notify(error instanceof Error ? error.message : 'Không đưa được job đồng bộ AP vào hàng đợi')
    } finally {
      setRunning(false)
    }
  }

  return <PageRoot className="page-stack enterprise-standard-page training-operations-page ap-sync-page">
    <EnterpriseScreenHeader
      eyebrow="Vận hành hệ thống"
      title="Đồng bộ AP"
      description="Đồng bộ lớp, giảng viên và sinh viên cho các môn đã chọn CMS hoặc Udemy."
      icon="sync"
      tone="blue"
      breadcrumbs={[{ label: 'Vận hành hệ thống' }, { label: 'Đồng bộ AP' }]}
      secondaryActions={<button className="btn secondary" type="button" disabled={loadingOptions || running} onClick={() => void loadOptions()}>{loadingOptions ? 'Đang cập nhật...' : 'Cập nhật cơ sở'}</button>}
    />

    <InlineNotice notice={message} />

    <OperationsKpiStrip items={[
      { label: 'Học kỳ', value: termName || 'Chưa chọn', hint: 'Phạm vi đồng bộ hiện tại' },
      { label: 'Cơ sở khả dụng', value: totalCampuses, hint: 'Lấy từ API theo hệ POLY/PTCD', tone: totalCampuses ? 'success' : 'warning' },
      { label: 'Môn được đồng bộ', value: totalSelectedSubjects, hint: `CMS ${optionsByBranch.poly.cms_subject_count + optionsByBranch.ptcd.cms_subject_count} · Udemy ${optionsByBranch.poly.udemy_subject_count + optionsByBranch.ptcd.udemy_subject_count}`, tone: totalSelectedSubjects ? 'success' : 'warning' },
      { label: 'Tác vụ đang chạy', value: activeRuns.length, hint: activeRuns.length ? 'Đang xử lý' : 'Sẵn sàng chạy', tone: activeRuns.length ? 'info' : 'neutral' },
      { label: 'Kết quả gần nhất', value: lastResults.length, hint: dryRun ? 'Chế độ kiểm tra kế hoạch' : 'Chế độ ghi dữ liệu' },
    ]} />

    <div className="ap-sync-workspace">
      <WorkspaceSection title="Kế hoạch đồng bộ" description="Chọn học kỳ và kiểm tra phạm vi trước khi đồng bộ." className="ap-sync-plan">
        <div className="settings-form-grid">
          <label>Học kỳ<select className="input" value={termName} onChange={(event) => setTermName(event.target.value)} disabled={!termOptions.length}>{termOptions.length ? termOptions.map((item) => <option key={item.value} value={item.value}>{item.label}</option>) : <option value="">Chưa có học kỳ</option>}</select></label>
          <label>Hệ khi chạy riêng<select className="input" value={selectedBranch} onChange={(event) => setSelectedBranch(event.target.value as BranchCode)}>{BRANCHES.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}</select></label>
        </div>
        <label className="check-row"><input type="checkbox" checked={dryRun} onChange={(event) => setDryRun(event.target.checked)} /> Chỉ kiểm tra kế hoạch, chưa ghi dữ liệu</label>
        <div className="ap-sync-summary">
          <div><span>Poly</span><b>{optionsByBranch.poly.campuses?.length || 0}</b><small>cơ sở khả dụng</small></div>
          <div><span>PTCĐ</span><b>{optionsByBranch.ptcd.campuses?.length || 0}</b><small>cơ sở khả dụng</small></div>
          <div><span>Phạm vi riêng</span><b>{BRANCHES.find((item) => item.value === selectedBranch)?.label}</b><small>{currentBranchOptions.campuses?.length || 0} cơ sở</small></div>
          <div><span>Môn đã chọn</span><b>{currentBranchOptions.selected_subject_count || 0}</b><small>CMS {currentBranchOptions.cms_subject_count || 0} · Udemy {currentBranchOptions.udemy_subject_count || 0}</small></div>
        </div>
        {!totalCampuses ? <ContentNotice tone="warning">Chưa có cơ sở đang bật. Vào trang Cơ sở để thêm thủ công trước khi đồng bộ.</ContentNotice> : null}
        {termName.trim() && totalSelectedSubjects === 0 ? <ContentNotice tone="warning">Học kỳ này chưa có môn nào được chọn CMS/Udemy. Vào Quản lý môn học để chọn nền tảng; Các môn chưa chọn nền tảng được bỏ qua.</ContentNotice> : null}
        {canManageAcademicOps ? <div className="ap-sync-actions">
          <button className="btn" type="button" disabled={running || loadingOptions || Boolean(activeRuns.length) || totalCampuses === 0 || totalSelectedSubjects === 0 || !termName.trim()} onClick={() => requestRunForBranches(['poly', 'ptcd'])}>{dryRun ? 'Kiểm tra toàn bộ' : 'Đồng bộ toàn bộ'}</button>
          <button className="btn secondary" type="button" disabled={running || loadingOptions || Boolean(activeRuns.length) || !currentBranchOptions.campuses.length || !currentBranchOptions.selected_subject_count || !termName.trim()} onClick={() => requestRunForBranches([selectedBranch])}>{dryRun ? `Kiểm tra hệ ${BRANCHES.find((item) => item.value === selectedBranch)?.label}` : `Đồng bộ hệ ${BRANCHES.find((item) => item.value === selectedBranch)?.label}`}</button>
        </div> : <ContentNotice tone="warning">Bạn không có quyền chạy đồng bộ AP.</ContentNotice>}
      </WorkspaceSection>

      <WorkspaceSection title="Tiến trình & kết quả" description="Theo dõi tiến trình và kết quả theo hệ." actions={activeRuns.length ? <button className="btn small secondary" type="button" onClick={() => refreshActiveRuns().catch((error) => notify(error instanceof Error ? error.message : 'Không tải được trạng thái tác vụ'))}>Làm mới</button> : undefined} className="ap-sync-recent">
        <div className="operation-compact-list" aria-live="polite">
          {activeRuns.map(({ branch, run }) => { const progress = runProgress(run); return <div className="operation-compact-item" key={run.id}><header><b>{BRANCHES.find((item) => item.value === branch)?.label || branch}</b><StatusBadge status={run.status} /></header><div className="job-progress table-progress" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={progress.percent}><i style={{ width: `${progress.percent}%` }} /></div><p>{progress.percent}% · {progress.label}</p><small>Run {run.id.slice(0, 8)}</small></div> })}
          {lastResults.map(({ branch, result }) => <div className="operation-compact-item" key={`${branch}-${result.sync_run?.id}`}><header><b>{BRANCHES.find((item) => item.value === branch)?.label || branch}</b><StatusBadge status={result.sync_run?.status || 'unknown'} /></header><p>{summarizeCounters(result)}</p>{result.sync_run?.error_message ? <small className="table-error-text">{result.sync_run.error_message}</small> : <small>Run {result.sync_run?.id?.slice(0, 8) || '—'}</small>}</div>)}
          {!activeRuns.length && !lastResults.length ? <div className="empty-state small-empty">Chưa có job trong phiên này. Sau khi bắt đầu, tiến trình sẽ xuất hiện tại đây và trong Tác vụ nền.</div> : null}
        </div>
      </WorkspaceSection>
    </div>

    <AccessibleDialog
      open={Boolean(syncConfirm)}
      title={dryRun ? 'Kiểm tra kế hoạch AP' : 'Chạy đồng bộ AP'}
      description={dryRun ? 'Hệ thống chỉ kiểm tra kế hoạch và không ghi dữ liệu.' : 'Hệ thống chỉ gọi AP cho các môn đã chọn CMS/Udemy rồi ghi dữ liệu lớp, giảng viên và sinh viên vào AI Server.'}
      onClose={() => !running && setSyncConfirm(null)}
      busy={running}
      size="small"
      footer={<div className="dialog-action-row"><button className="btn secondary" disabled={running} onClick={() => setSyncConfirm(null)}>Hủy</button><button className="btn" data-dialog-autofocus disabled={running} onClick={executeConfirmedSync}>{dryRun ? 'Xác nhận kiểm tra' : 'Xác nhận đồng bộ'}</button></div>}
    >
      {syncConfirm ? <div className="academic-confirm-summary"><span>Học kỳ</span><b>{termName}</b><span>Phạm vi</span><b>{syncConfirm.label}</b><span>Số hệ</span><b>{syncConfirm.runnable.length}</b><span>Số cơ sở</span><b>{syncConfirm.campusCount}</b><span>Số môn CMS/Udemy</span><b>{syncConfirm.subjectCount}</b></div> : null}
    </AccessibleDialog>
  </PageRoot>
}
