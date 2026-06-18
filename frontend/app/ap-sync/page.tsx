'use client'

import { useEffect, useMemo, useState } from 'react'
import { useAppContext } from '../../context/AppContext'
import { getAcademicApSyncOptions, syncAcademicFromAp } from '../../lib/api'
import { AcademicAPOption, AcademicAPSyncOptions, AcademicSyncResult } from '../../types'

type BranchCode = 'poly' | 'ptcd'

type BranchState = Record<BranchCode, AcademicAPSyncOptions>

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

export default function ApSyncPage() {
  const { authHeaders, can } = useAppContext()
  const headers = useMemo(() => authHeaders(), [authHeaders])
  const jsonHeaders = useMemo(() => authHeaders(true), [authHeaders])
  const [termName, setTermName] = useState('Summer 2026')
  const [selectedBranch, setSelectedBranch] = useState<BranchCode>('poly')
  const [optionsByBranch, setOptionsByBranch] = useState<BranchState>({ poly: EMPTY_OPTIONS, ptcd: EMPTY_OPTIONS })
  const [loadingOptions, setLoadingOptions] = useState(false)
  const [running, setRunning] = useState(false)
  const [dryRun, setDryRun] = useState(false)
  const [message, setMessage] = useState('')
  const [lastResults, setLastResults] = useState<Array<{ branch: BranchCode; result: AcademicSyncResult }>>([])

  const termOptions = useMemo(() => uniqueTermOptions(optionsByBranch), [optionsByBranch])
  const currentBranchOptions = optionsByBranch[selectedBranch] || EMPTY_OPTIONS
  const totalCampuses = BRANCHES.reduce((sum, branch) => sum + (optionsByBranch[branch.value].campuses?.length || 0), 0)

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

  useEffect(() => {
    loadOptions()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [headers, termName])

  const runForBranches = async (branches: BranchCode[]) => {
    if (!can('manage_settings')) {
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
    const ok = window.confirm(`${dryRun ? 'Kiểm tra kế hoạch' : 'Đồng bộ thật'} ${label} cho kỳ ${normalizedTerm}?\n\nSố hệ sẽ chạy: ${runnable.length}\nSố cơ sở: ${campusCount}\n\nDanh sách môn sẽ lấy tự động từ AP theo từng hệ/kỳ.`)
    if (!ok) return

    setRunning(true)
    setMessage('')
    setLastResults([])
    try {
      const results: Array<{ branch: BranchCode; result: AcademicSyncResult }> = []
      for (const branch of runnable) {
        const campuses = optionValues(optionsByBranch[branch].campuses)
        const result = await syncAcademicFromAp(jsonHeaders, {
          term_name: normalizedTerm,
          sync_scope: 'all',
          branch,
          campuses,
          subject_codes: [],
          max_subjects: 0,
          dry_run: dryRun,
        })
        results.push({ branch, result })
        setLastResults([...results])
      }
      setMessage(dryRun ? 'Đã kiểm tra kế hoạch đồng bộ AP.' : 'Đã chạy đồng bộ AP.')
      await loadOptions()
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Đồng bộ AP thất bại')
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
        <button className="btn secondary" disabled={loadingOptions || running} onClick={loadOptions}>{loadingOptions ? 'Đang tải...' : 'Làm mới'}</button>
      </div>
    </section>

    {message ? <div className="alert">{message}</div> : null}

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
      <div className="toolbar-actions ap-sync-actions ap-sync-actions-primary">
        <button className="btn" disabled={running || loadingOptions || totalCampuses === 0 || !termName.trim()} onClick={() => runForBranches(['poly', 'ptcd'])}>
          {running ? 'Đang chạy...' : 'Đồng bộ tất cả'}
        </button>
        <button className="btn secondary" disabled={running || loadingOptions || !currentBranchOptions.campuses.length || !termName.trim()} onClick={() => runForBranches([selectedBranch])}>
          {running ? 'Đang chạy...' : `Đồng bộ theo hệ ${BRANCHES.find((item) => item.value === selectedBranch)?.label || ''}`}
        </button>
      </div>
      {!totalCampuses ? <div className="alert soft-alert">Chưa có cơ sở đang bật. Vào trang Cơ sở để thêm hoặc bật lại cơ sở trước.</div> : null}
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
  </div>
}
