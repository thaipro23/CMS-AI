// v25.9.16.7.2.64.14 — split readiness contract types.
// Keep these re-exports backward compatible while new code imports from this file
// instead of adding more operational report types to frontend/types/index.ts.
export type {
  SecurityReadinessReport,
  PerformanceReadinessReport,
  ReleaseCandidateReport,
  PilotOperationsReport,
  ReleaseCandidateGate,
  ReleaseCandidateIssue,
  SecurityReadinessCheck,
  PerformanceReadinessCheck,
  PilotOperationsPhase,
  PilotOperationsTrigger,
} from './index'

export type MaintainabilityFileMetric = {
  path: string
  lines: number
  threshold: number
  severity: 'BLOCKER' | 'WARNING' | 'INFO' | string
  reason?: string
}

export type MaintainabilityContractReport = {
  version?: string
  report_type?: 'maintainability_contract' | string
  status: 'READY' | 'READY_WITH_WARNINGS' | 'BLOCKED' | string
  summary_label?: string
  blocker_count?: number
  warning_count?: number
  file_metrics?: MaintainabilityFileMetric[]
  contract_modules?: Array<{ path: string; exists: boolean }>
  checks?: Array<Record<string, any>>
  sections?: Array<Record<string, any>>
  summary?: Record<string, any>
  next_actions?: string[]
  safe_policy?: string
  read_only_guarantees?: string[]
}


export type QueryHotspotReport = {
  version?: string
  report_type?: string
  status: 'READY' | 'READY_WITH_WARNINGS' | 'BLOCKED' | string
  summary_label?: string
  blocker_count?: number
  warning_count?: number
  checks?: Array<Record<string, any>>
  sections?: Array<Record<string, any>>
  hotspots?: Array<Record<string, any>>
  summary?: Record<string, any>
  next_actions?: string[]
  read_only_guarantees?: string[]
}


export type ProductionPilotFinalReport = {
  version?: string
  report_type?: 'production_pilot_final_gate' | string
  status: 'GO' | 'GO_WITH_MONITORING' | 'HOLD' | string
  decision?: 'GO_PILOT' | 'GO_CONTROLLED_PILOT' | 'NO_GO' | string
  summary_label?: string
  ready_for_pilot?: boolean
  ready_for_broad_production?: boolean
  blocker_count?: number
  warning_count?: number
  gates?: Array<Record<string, any>>
  final_checks?: Array<Record<string, any>>
  evidence_required?: string[]
  load_test_plan?: Array<Record<string, any>>
  rollback_drill?: Record<string, any>
  signoff?: Record<string, any>
  reports?: Record<string, any>
  next_actions?: string[]
  read_only_guarantees?: string[]
}


export type SecurityAttackSimulationReport = {
  version?: string
  report_type?: 'security_attack_simulation_v1' | string
  status: 'READY' | 'READY_WITH_WARNINGS' | 'BLOCKED' | string
  summary_label?: string
  blocker_count?: number
  warning_count?: number
  attack_count?: number
  protected_count?: number
  needs_review_count?: number
  attacks?: Array<{ id?: number; category?: string; attack?: string; control?: string; status?: string; severity?: string; evidence?: string; fix?: string }>
  sections?: Array<Record<string, any>>
  next_actions?: string[]
  read_only_guarantees?: string[]
}

export type UxAcceptanceReport = {
  version?: string
  report_type?: 'uat_ux_acceptance_v1' | string
  status: 'READY' | 'READY_WITH_WARNINGS' | 'BLOCKED' | string
  summary_label?: string
  message?: string
  blocker_count?: number
  warning_count?: number
  check_count?: number
  passed_count?: number
  checks?: Array<{ category?: string; code?: string; severity?: string; ok?: boolean; message?: string; action?: string; path?: string }>
  sections?: Array<Record<string, any>>
  browser_uat_checklist?: string[]
  next_actions?: string[]
  read_only_guarantees?: string[]
  disclaimer?: string
}
