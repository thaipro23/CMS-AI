// v25.9.16.7.2.64.13 — split readiness API facade.
// The legacy frontend/lib/api.ts exports remain intact. New readiness/ops code
// should import from this facade so the monolithic API client stops growing.
export {
  getSecurityReadiness,
  getPerformanceReadiness,
  getReleaseCandidateReadiness,
  getPilotOperationsReadiness,
} from '../api'

import { API, apiFetch, parseResponse } from '../api'
import type { MaintainabilityContractReport, QueryHotspotReport, ProductionPilotFinalReport, SecurityAttackSimulationReport } from '../../types/readiness'

export async function getMaintainabilityContract(
  headers: HeadersInit,
): Promise<MaintainabilityContractReport> {
  return parseResponse(
    await apiFetch(`${API}/health/maintainability-contract`, {
      credentials: 'include',
      headers,
    }),
  )
}


export async function getQueryHotspots(
  headers: HeadersInit,
  filters: { maxItems?: number } = {},
): Promise<QueryHotspotReport> {
  const params = new URLSearchParams();
  params.set('max_items', String(Math.max(1, Math.min(500, filters.maxItems || 120))));
  return parseResponse(
    await apiFetch(`${API}/health/query-hotspots?${params.toString()}`, {
      credentials: 'include',
      headers,
    }),
  )
}


export async function getProductionPilotFinal(
  headers: HeadersInit,
  filters: { classId?: string; courseId?: string; branch?: string; campus?: string; sampleLimit?: number; includeStaticScans?: boolean } = {},
): Promise<ProductionPilotFinalReport> {
  const params = new URLSearchParams();
  if (filters.classId?.trim()) params.set('class_id', filters.classId.trim());
  if (filters.courseId?.trim()) params.set('course_id', filters.courseId.trim());
  if (filters.branch?.trim()) params.set('branch', filters.branch.trim());
  if (filters.campus?.trim()) params.set('campus', filters.campus.trim());
  params.set('sample_limit', String(filters.sampleLimit || 5));
  params.set('include_static_scans', String(filters.includeStaticScans ?? true));
  return parseResponse(
    await apiFetch(`${API}/health/production-pilot-final?${params.toString()}`, {
      credentials: 'include',
      headers,
    }),
  )
}


export async function getSecurityAttackSimulation(
  headers: HeadersInit,
): Promise<SecurityAttackSimulationReport> {
  return parseResponse(
    await apiFetch(`${API}/health/security-attack-simulation`, {
      credentials: 'include',
      headers,
    }),
  )
}
