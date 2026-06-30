'use client'

import { useEffect, useMemo, useState } from 'react'
import { useAppContext } from '../../context/AppContext'
import { enqueueAcademicApSyncJob, getAcademicApSyncJob, getAcademicApSyncJobs, getAcademicApSyncOptions, syncAcademicCampusesFromAp } from '../../lib/api'
import { AcademicAPOption, AcademicAPSyncOptions, AcademicSyncResult, AcademicSyncRun } from '../../types'

type BranchCode = 'poly' | 'ptcd'
type BranchState = Record<BranchCode, AcademicAPSyncOptions>
type SyncConfirm = { branches: BranchCode[]; runnable: BranchCode[]; label: string; campusCount: number } | null

const BRANCHES: Array<{ value: BranchCode; label: string }> = [
  { value: 'poly', label: 'Poly' },
  { value: 'ptcd', label: 'PTCĐ' },
]

const EMPTY_OPTIONS: AcademicAPSyncOptions = { branches: [], campuses: [], terms: [], subjects: [], warnings: [] }

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
  const [termName, setTermName] = useState('Summer 2026')
  const [selectedBranch, setSelectedBranch] = useState<BranchCode>('poly')
  const [optionsByBranch, setOptionsByBranch] = useState<BranchState>({ poly: EMPTY_OPTIONS, ptcd: EMPTY_OPTIONS })
  const [loadingOptions, setLoadingOptions] = useState(false)
  const [syncingCampuses, setSyncingCampuses] = useState(false)
  const [running, setRunning] = useState(false)
  const [dryRun, setDryRun] = useState(false)
  const [message, setMessage] = useState('')
  const [lastResults, setLastResults] = useState<Array<{ branch: BranchCode; result: AcademicSyncResult }>>([])
  const [activeRuns, setActiveRuns] = useState<Array<{ branch: BranchCode; run: AcademicSyncRun }>>([])
  const [syncConfirm, setSyncConfirm] = useState<SyncConfirm>(null)

  const termOptions = useMemo(() => uniqueTermOptions(optionsByBranch), [optionsByBranch])
  const currentBranchOptions = optionsByBranch[selectedBranch] || EMPTY_OPTIONS
  const totalCampuses = BRANCHES.reduce((sum, branch) => sum + (optionsByBranch[branch.value].campuses?.length || 0), 0)
  const canManageAcademicOps = can('manage_training_deadlines') || can('manage_settings')

  const loadOptions = async () => {
    setLoadingOptions(true)
    setMessage('')
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
      setMessage(error instanceof Error ? error.message : 'Không tải được dữ liệu học kỳ/hệ/cơ sở')
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

  const syncCampusesFromAp = async () => {
    if (!canManageAcademicOps) {
      setMessage('Bạn không có quyền đồng bộ danh sách cơ sở AP.')
      return
    }
    setSyncingCampuses(true)
    setMessage('')
    try {
      const results = await Promise.all(BRANCHES.map(async (branch) => ({
        branch: branch.value,
        campuses: await syncAcademicCampusesFromAp(jsonHeaders, branch.value),
      })))
      await loadOptions()
      const summary = results.map((item) => `${BRANCHES.find((branch) => branch.value === item.branch)?.label || item.branch}: ${item.campuses.length} cơ sở`).join(' · ')
      setMessage(`Đã đồng bộ danh sách cơ sở từ AP và lưu vào /premises. ${summary}`)
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Không đồng bộ được danh sách cơ sở từ AP')
    } finally {
      setSyncingCampuses(false)
    }
  }

  useEffect(() => {
    loadOptions()
    refreshActiveRuns().catch(() => null)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [headers, termName])

  useEffect(() => {
    if (!activeRuns.length) return
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
            setMessage('Có job đồng bộ AP thất bại. Xem chi tiết trong bảng kết quả gần nhất.')
          } else {
            setMessage(dryRun ? 'Đã kiểm tra kế hoạch đồng bộ AP.' : 'Đã chạy xong đồng bộ AP.')
            await loadOptions()
          }
        }
        if (next.some((item) => isRunActive(item.run))) timer = setTimeout(poll, 2000)
      } catch (error) {
        if (!canceled) {
          setMessage(error instanceof Error ? error.message : 'Không kiểm tra được trạng thái job đồng bộ AP')
          timer = setTimeout(poll, 4000)
        }
      }
    }
    timer = setTimeout(poll, 1000)
    return () => { canceled = true; if (timer) clearTimeout(timer) }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeRuns.map((item) => item.run.id).join(','), headers])

  const requestRunForBranches = (branches: BranchCode[]) => {
    if (!canManageAcademicOps) {
      setMessage('Bạn không có quyền đồng bộ AP.')
      return
    }
    const normalizedTerm = termName.trim()
    if (!normalizedTerm) {
      setMessage('Vui lòng chọn kỳ trước khi đồng bộ.')
      return
    }
    const runnable = branches.filter((branch) => optionValues(optionsByBranch[branch].campuses).length > 0)
    if (!runnable.length) {
      setMessage('Chưa có cơ sở để đồng bộ. Vào trang Cơ sở để thêm hoặc bật lại cơ sở trước.')
      return
    }
    const label = branches.length > 1 ? 'toàn bộ Poly và PTCĐ' : `hệ ${BRANCHES.find((item) => item.value === branches[0])?.label || branches[0]}`
    const campusCount = runnable.reduce((sum, branch) => sum + optionValues(optionsByBranch[branch].campuses).length, 0)
    setSyncConfirm({ branches, runnable, label, campusCount })
  }

  const executeConfirmedSync = async () => {
    if (!syncConfirm) return
    const normalizedTerm = termName.trim()
    const runnable = syncConfirm.runnable
    setRunning(true)
    setMessage('')
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
          subject_codes: [],
          max_subjects: 0,
          dry_run: dryRun,
        })
        queuedRuns.push({ branch, run: result.sync_run })
      }
      setActiveRuns((current) => {
        const seen = new Set(current.map((item) => item.run.id))
        return [...queuedRuns, ...current.filter((item) => !seen.has(item.run.id))]
      })
      setMessage(dryRun ? 'Đã đưa job kiểm tra kế hoạch AP vào hàng đợi.' : 'Đã đưa job đồng bộ AP vào hàng đợi. Bạn có thể F5 hoặc mở máy khác để theo dõi tiếp.')
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Không đưa được job đồng bộ AP vào hàng đợi')
    } finally {
      setRunning(false)
    }
  }

  return <div className="page-stack ap-sync-page">
    <section className="hero-card compact-hero">
      <div>
        <div className="eyebrow">AP → AI Server</div>
        <h1>Đồng bộ AP</h1>
        <p>Trang này dùng để đồng bộ dữ liệu phân công từ AP theo kỳ. Không chia nhỏ theo cơ sở hoặc theo môn trên giao diện nữa.</p>
      </div>
      <div className="hero-actions">
        <button className="btn secondary" disabled={loadingOptions || running || syncingCampuses} onClick={loadOptions}>{loadingOptions ? 'Đang tải...' : 'Làm mới'}</button>
        {canManageAcademicOps && <button className="btn secondary" disabled={loadingOptions || running || syncingCampuses || Boolean(activeRuns.length)} onClick={syncCampusesFromAp}>{syncingCampuses ? 'Đang đồng bộ cơ sở...' : 'Đồng bộ danh sách cơ sở'}</button>}
      </div>
    </section>

    {message ? <div className="alert">{message}</div> : null}

    {activeRuns.length ? <section className="card sync-job-status persistent-sync-job-status" role="status" aria-live="polite" aria-busy="true">
      <div className="section-head">
        <div>
          <h2>Hệ thống đang đồng bộ AP</h2>
          <p>Job chạy ở nền. F5 hoặc mở máy khác vẫn đọc lại trạng thái từ backend.</p>
        </div>
        <button className="btn secondary small" type="button" onClick={() => refreshActiveRuns().catch((error) => setMessage(error instanceof Error ? error.message : 'Không tải được trạng thái job'))}>Làm mới tiến trình</button>
      </div>
      <div className="operation-stack">
        {activeRuns.map(({ branch, run }) => {
          const progress = runProgress(run)
          return <div className="operation-row" key={run.id}>
            <div>
              <b>{BRANCHES.find((item) => item.value === branch)?.label || branch}</b>
              <p>{progress.label}</p>
              <small>Run ID {run.id.slice(0, 8)} · {run.status}</small>
            </div>
            <div className="operation-progress">
              <span>{progress.percent}%</span>
              <progress value={progress.current} max={progress.total} aria-label="Tiến độ đồng bộ AP" />
            </div>
          </div>
        })}
      </div>
    </section> : null}

    <section className="card">
      <div className="section-head">
        <div>
          <h2>Thiết lập kỳ đồng bộ</h2>
          <p>Thông thường mỗi kỳ chỉ cần chạy một vài lần: đồng bộ toàn bộ hoặc đồng bộ riêng từng hệ.</p>
        </div>
      </div>
      <div className="filter-grid academic-filter-grid">
        <label>Kỳ
          <select className="input" value={termName} onChange={(event) => setTermName(event.target.value)} disabled={!termOptions.length}>
            {termOptions.length ? termOptions.map((item) => <option key={item.value} value={item.value}>{item.label}</option>) : <option value="">Chưa có học kỳ. Tạo ở trang Học kỳ trước.</option>}
          </select>
        </label>
        <label>Hệ cần đồng bộ riêng
          <select className="input" value={selectedBranch} onChange={(event) => setSelectedBranch(event.target.value as BranchCode)}>
            {BRANCHES.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
          </select>
        </label>
        <label className="check-row align-end">
          <input type="checkbox" checked={dryRun} onChange={(event) => setDryRun(event.target.checked)} />
          Chỉ kiểm tra kế hoạch, chưa ghi dữ liệu
        </label>
      </div>
      {canManageAcademicOps && <div className="toolbar-actions ap-sync-actions ap-sync-actions-primary">
        <button className="btn" disabled={running || loadingOptions || syncingCampuses || Boolean(activeRuns.length) || totalCampuses === 0 || !termName.trim()} onClick={() => requestRunForBranches(['poly', 'ptcd'])}>
          {running ? 'Đang chạy...' : 'Đồng bộ tất cả'}
        </button>
        <button className="btn secondary" disabled={running || loadingOptions || syncingCampuses || Boolean(activeRuns.length) || !currentBranchOptions.campuses.length || !termName.trim()} onClick={() => requestRunForBranches([selectedBranch])}>
          {running ? 'Đang chạy...' : `Đồng bộ theo hệ ${BRANCHES.find((item) => item.value === selectedBranch)?.label || ''}`}
        </button>
      </div>}
      {!totalCampuses ? <div className="alert soft-alert">Chưa có cơ sở đang bật. Bấm Đồng bộ danh sách cơ sở để lấy từ AP CMS get-campus và lưu vào /premises, hoặc vào trang Cơ sở để thêm thủ công.</div> : null}
    </section>

    {lastResults.length ? <section className="card">
      <div className="section-head">
        <div>
          <h2>Kết quả gần nhất</h2>
          <p>{lastResults.length} hệ đã xử lý</p>
        </div>
      </div>
      <div className="table-wrap">
        <table className="data-table compact-table">
          <thead><tr><th>Hệ</th><th>Trạng thái</th><th>Kết quả</th><th>Run ID</th></tr></thead>
          <tbody>{lastResults.map(({ branch, result }) => <tr key={`${branch}-${result.sync_run?.id}`}>
            <td><b>{BRANCHES.find((item) => item.value === branch)?.label || branch}</b></td>
            <td><span className={result.sync_run?.status === 'completed' ? 'status-pill success' : 'status-pill danger'}>{result.sync_run?.status || 'unknown'}</span></td>
            <td>{summarizeCounters(result)}{result.sync_run?.error_message ? <small>{result.sync_run.error_message}</small> : null}</td>
            <td><small>{result.sync_run?.id || '—'}</small></td>
          </tr>)}</tbody>
        </table>
      </div>
    </section> : null}

    {syncConfirm ? <div className="modal-backdrop bank-popup-backdrop" onMouseDown={() => !running && setSyncConfirm(null)}><div className="card bank-modal academic-confirm-modal" onMouseDown={(event) => event.stopPropagation()}><div className="bank-modal-head"><div><div className="eyebrow">Xác nhận đồng bộ</div><h2>{dryRun ? 'Kiểm tra kế hoạch AP' : 'Chạy đồng bộ AP'}</h2></div><button className="btn small secondary" disabled={running} onClick={() => setSyncConfirm(null)}>Đóng</button></div><div className="bank-modal-body academic-confirm-body"><p>{dryRun ? 'Hệ thống sẽ chỉ kiểm tra kế hoạch, chưa ghi dữ liệu vào AI Server.' : 'Hệ thống sẽ gọi AP và ghi dữ liệu lớp, giảng viên, sinh viên vào AI Server.'}</p><div className="academic-confirm-summary"><span>Kỳ</span><b>{termName}</b><span>Phạm vi</span><b>{syncConfirm.label}</b><span>Số hệ</span><b>{syncConfirm.runnable.length}</b><span>Số cơ sở</span><b>{syncConfirm.campusCount}</b></div><div className="modal-actions"><button className="btn" disabled={running} onClick={executeConfirmedSync}>{dryRun ? 'Xác nhận kiểm tra' : 'Xác nhận đồng bộ'}</button><button className="btn secondary" disabled={running} onClick={() => setSyncConfirm(null)}>Hủy</button></div></div></div></div> : null}
  </div>
}
