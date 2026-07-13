'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import Link from 'next/link'
import { useAppContext } from '../../../context/AppContext'
import { OperationalGatePanel, type OperationalGateTone } from '../../../components/readiness/OperationalGatePanel'
import {
  getMaintainabilityContract,
  getPerformanceReadiness,
  getPilotOperationsReadiness,
  getProductionPilotFinal,
  getQueryHotspots,
  getReleaseCandidateReadiness,
  getSecurityReadiness,
  getSecurityAttackSimulation,
  getUxAcceptance,
} from '../../../lib/api/readiness'
import type {
  MaintainabilityContractReport,
  PerformanceReadinessReport,
  PilotOperationsReport,
  QueryHotspotReport,
  ProductionPilotFinalReport,
  ReleaseCandidateReport,
  SecurityReadinessReport,
  SecurityAttackSimulationReport,
  UxAcceptanceReport,
} from '../../../types/readiness'

type ReportState = {
  security?: SecurityReadinessReport | null
  performance?: PerformanceReadinessReport | null
  releaseCandidate?: ReleaseCandidateReport | null
  pilotOperations?: PilotOperationsReport | null
  maintainability?: MaintainabilityContractReport | null
  queryHotspots?: QueryHotspotReport | null
  productionPilotFinal?: ProductionPilotFinalReport | null
  securityAttackSimulation?: SecurityAttackSimulationReport | null
  uxAcceptance?: UxAcceptanceReport | null
}

function toneFromStatus(status?: string | null): OperationalGateTone {
  const value = String(status || '').toUpperCase()
  if (['READY', 'PASS', 'OK', 'PILOT_READY'].includes(value)) return 'success'
  if (['BLOCKED', 'FAIL', 'HOLD'].includes(value)) return 'danger'
  if (!value || value === 'UNKNOWN') return 'neutral'
  return 'warning'
}

function issueCounter(report?: { blocker_count?: number; warning_count?: number } | null) {
  return [
    { label: 'blocker', value: report?.blocker_count || 0, tone: (report?.blocker_count || 0) > 0 ? 'danger' as const : 'success' as const },
    { label: 'cảnh báo', value: report?.warning_count || 0, tone: (report?.warning_count || 0) > 0 ? 'warning' as const : 'neutral' as const },
  ]
}

function nextActions(actions?: string[]) {
  if (!Array.isArray(actions) || actions.length === 0) return null
  return <ul className="ops-readiness-list">{actions.slice(0, 5).map((action, index) => <li key={`${action}-${index}`}>{action}</li>)}</ul>
}

export default function OpsReadinessPage() {
  const { authHeaders, authReady, isAuthenticated, can } = useAppContext()
  const headers = useMemo(() => authHeaders(), [authHeaders])
  const [branch, setBranch] = useState('poly')
  const [campus, setCampus] = useState('')
  const [classId, setClassId] = useState('')
  const [courseId, setCourseId] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [reports, setReports] = useState<ReportState>({})

  const filters = useMemo(() => ({
    branch,
    campus: campus || undefined,
    classId: classId || undefined,
    courseId: courseId || undefined,
    sampleLimit: 5,
  }), [branch, campus, classId, courseId])

  const load = useCallback(async () => {
    if (!authReady || !isAuthenticated || !can('view_jobs')) return
    setLoading(true)
    setError(null)
    try {
      const [security, attackSimulation, performance, releaseCandidate, pilotOperations, maintainability, queryHotspots, productionPilotFinal, uxAcceptance] = await Promise.all([
        getSecurityReadiness(headers).catch(() => null),
        getSecurityAttackSimulation(headers).catch(() => null),
        getPerformanceReadiness(headers).catch(() => null),
        getReleaseCandidateReadiness(headers, filters).catch(() => null),
        getPilotOperationsReadiness(headers, filters).catch(() => null),
        getMaintainabilityContract(headers).catch(() => null),
        getQueryHotspots(headers, { maxItems: 120 }).catch(() => null),
        getProductionPilotFinal(headers, { ...filters, includeStaticScans: true }).catch(() => null),
        getUxAcceptance(headers).catch(() => null),
      ])
      setReports({ security, securityAttackSimulation: attackSimulation, performance, releaseCandidate, pilotOperations, maintainability, queryHotspots, productionPilotFinal, uxAcceptance })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Không tải được readiness reports')
    } finally {
      setLoading(false)
    }
  }, [authReady, isAuthenticated, can, headers, filters])

  useEffect(() => { load() }, [load])

  if (!authReady) return <main className="ops-readiness-page"><p>Đang kiểm tra phiên đăng nhập...</p></main>
  if (!isAuthenticated) return <main className="ops-readiness-page"><p>Vui lòng đăng nhập để xem trạng thái vận hành.</p></main>
  if (!can('view_jobs')) return <main className="ops-readiness-page"><p>Bạn chưa có quyền xem trạng thái vận hành.</p></main>

  return <main className="ops-readiness-page">
    <section className="ops-readiness-header">
      <div>
        <p className="eyebrow">Operations</p>
        <h1>Readiness & Pilot Gates</h1>
        <p>Tách các gate vận hành khỏi màn nghiệp vụ để `/analytics/learning` không tiếp tục phình. Trang này chỉ đọc, không enqueue job và không mutate dữ liệu.</p>
      </div>
      <div className="ops-readiness-actions">
        <button className="primary-action" type="button" onClick={load} disabled={loading}>{loading ? 'Đang tải...' : 'Tải lại'}</button>
        <Link className="secondary-action" href="/analytics/learning">Quay lại Học online</Link>
      </div>
    </section>

    <section className="ops-readiness-filters" aria-label="Bộ lọc readiness">
      <label>Hệ <input value={branch} onChange={(event) => setBranch(event.target.value)} placeholder="poly" /></label>
      <label>Cơ sở <input value={campus} onChange={(event) => setCampus(event.target.value)} placeholder="ph" /></label>
      <label>Class ID <input value={classId} onChange={(event) => setClassId(event.target.value)} placeholder="optional" /></label>
      <label>Course ID <input value={courseId} onChange={(event) => setCourseId(event.target.value)} placeholder="course-v1:..." /></label>
    </section>

    {error && <div className="ops-readiness-error">{error}</div>}

    <section className="ops-compact-summary" aria-label="Tóm tắt readiness">
      <div><span>Final gate</span><b>{reports.productionPilotFinal?.decision || reports.productionPilotFinal?.status || 'UNKNOWN'}</b><small>{reports.productionPilotFinal?.blocker_count || 0} blocker</small></div>
      <div><span>UX acceptance</span><b>{reports.uxAcceptance?.status || 'UNKNOWN'}</b><small>{reports.uxAcceptance?.passed_count || 0}/{reports.uxAcceptance?.check_count || 0} checks</small></div>
      <div><span>Security</span><b>{reports.security?.status || 'UNKNOWN'}</b><small>{reports.security?.warning_count || 0} cảnh báo</small></div>
      <div><span>Performance</span><b>{reports.performance?.status || 'UNKNOWN'}</b><small>{reports.performance?.warning_count || 0} cảnh báo</small></div>
    </section>

    <div className="ops-readiness-grid">

      <OperationalGatePanel
        title="Production pilot final"
        subtitle={reports.productionPilotFinal?.summary_label || 'Final QA, load-test plan, rollback drill và sign-off'}
        tone={toneFromStatus(reports.productionPilotFinal?.status)}
        status={reports.productionPilotFinal?.decision || reports.productionPilotFinal?.status || 'UNKNOWN'}
        counters={issueCounter(reports.productionPilotFinal)}
      >
        {Array.isArray(reports.productionPilotFinal?.final_checks) && reports.productionPilotFinal.final_checks.length ? <ul className="ops-readiness-list">{reports.productionPilotFinal.final_checks.slice(0, 5).map((item, index) => <li key={`${item.code || 'final'}-${index}`}><b>{item.code}</b>: {item.message}</li>)}</ul> : nextActions(reports.productionPilotFinal?.next_actions)}
      </OperationalGatePanel>

      <OperationalGatePanel
        title="UAT UX acceptance"
        subtitle={reports.uxAcceptance?.summary_label || 'Enterprise table, URL state, accessibility và Audit export contract'}
        tone={toneFromStatus(reports.uxAcceptance?.status)}
        status={reports.uxAcceptance?.status || 'UNKNOWN'}
        counters={[
          ...issueCounter(reports.uxAcceptance),
          { label: 'passed', value: reports.uxAcceptance?.passed_count || 0, tone: 'success' as const },
        ]}
      >
        {Array.isArray(reports.uxAcceptance?.browser_uat_checklist) && reports.uxAcceptance.browser_uat_checklist.length ? <ul className="ops-readiness-list">{reports.uxAcceptance.browser_uat_checklist.slice(0, 5).map((item, index) => <li key={`${item}-${index}`}>{item}</li>)}</ul> : nextActions(reports.uxAcceptance?.next_actions)}
      </OperationalGatePanel>

      <OperationalGatePanel
        title="Security readiness"
        subtitle={reports.security?.summary_label || 'Auth, cookie, CORS, connector, secret posture'}
        tone={toneFromStatus(reports.security?.status)}
        status={reports.security?.status || 'UNKNOWN'}
        counters={issueCounter(reports.security)}
      >
        {nextActions(reports.security?.next_actions)}
      </OperationalGatePanel>



      <OperationalGatePanel
        title="Security attack simulation"
        subtitle={reports.securityAttackSimulation?.summary_label || 'Mô phỏng tĩnh 20 nhóm tấn công phổ biến'}
        tone={toneFromStatus(reports.securityAttackSimulation?.status)}
        status={reports.securityAttackSimulation?.status || 'UNKNOWN'}
        counters={[
          ...(issueCounter(reports.securityAttackSimulation)),
          { label: 'attack', value: reports.securityAttackSimulation?.attack_count || 0, tone: 'neutral' as const },
          { label: 'protected', value: reports.securityAttackSimulation?.protected_count || 0, tone: 'success' as const },
        ]}
      >
        {Array.isArray(reports.securityAttackSimulation?.attacks) && reports.securityAttackSimulation.attacks.length ? <ul className="ops-readiness-list">{reports.securityAttackSimulation.attacks.filter((item) => item.status !== 'PROTECTED').slice(0, 5).map((item) => <li key={item.id}><b>{item.attack}</b>: {item.fix}</li>)}</ul> : nextActions(reports.securityAttackSimulation?.next_actions)}
      </OperationalGatePanel>

      <OperationalGatePanel
        title="Performance readiness"
        subtitle={reports.performance?.summary_label || 'DB pool, query/index contract, job pressure'}
        tone={toneFromStatus(reports.performance?.status)}
        status={reports.performance?.status || 'UNKNOWN'}
        counters={issueCounter(reports.performance)}
      >
        {nextActions(reports.performance?.next_actions)}
      </OperationalGatePanel>

      <OperationalGatePanel
        title="Release candidate"
        subtitle={reports.releaseCandidate?.summary_label || 'Go/no-go tổng hợp trước pilot'}
        tone={toneFromStatus(reports.releaseCandidate?.status)}
        status={reports.releaseCandidate?.go_no_go || reports.releaseCandidate?.status || 'UNKNOWN'}
        counters={issueCounter(reports.releaseCandidate)}
      >
        {nextActions(reports.releaseCandidate?.next_actions)}
      </OperationalGatePanel>

      <OperationalGatePanel
        title="Pilot operations"
        subtitle={reports.pilotOperations?.summary_label || 'Runbook, rollback triggers, evidence, sign-off'}
        tone={toneFromStatus(reports.pilotOperations?.status)}
        status={reports.pilotOperations?.decision || reports.pilotOperations?.status || 'UNKNOWN'}
        counters={issueCounter(reports.pilotOperations)}
      >
        {Array.isArray(reports.pilotOperations?.rollback_triggers) && reports.pilotOperations?.rollback_triggers?.length ? <ul className="ops-readiness-list">{reports.pilotOperations.rollback_triggers.slice(0, 4).map((item, index) => <li key={`${item.code || 'rollback'}-${index}`}><b>{item.code}</b>: {item.condition}</li>)}</ul> : nextActions(reports.pilotOperations?.next_actions)}
      </OperationalGatePanel>

      <OperationalGatePanel
        title="Maintainability contract"
        subtitle={reports.maintainability?.summary_label || 'Large-file debt và split contract modules'}
        tone={toneFromStatus(reports.maintainability?.status)}
        status={reports.maintainability?.status || 'UNKNOWN'}
        counters={issueCounter(reports.maintainability)}
      >
        {Array.isArray(reports.maintainability?.file_metrics) && <ul className="ops-readiness-list">{reports.maintainability.file_metrics.filter((item) => item.severity === 'WARNING' || item.severity === 'BLOCKER').slice(0, 5).map((item) => <li key={item.path}>{item.path}: {item.lines}/{item.threshold} dòng</li>)}</ul>}
      </OperationalGatePanel>

      <OperationalGatePanel
        title="Query hotspots"
        subtitle={reports.queryHotspots?.summary_label || 'Static scan cho unbounded query và endpoint nóng'}
        tone={toneFromStatus(reports.queryHotspots?.status)}
        status={reports.queryHotspots?.status || 'UNKNOWN'}
        counters={issueCounter(reports.queryHotspots)}
      >
        {nextActions(reports.queryHotspots?.next_actions)}
      </OperationalGatePanel>
    </div>
  </main>
}
