'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import { usePathname, useRouter, useSearchParams } from 'next/navigation'
import { useAppContext } from '../context/AppContext'
import { API, apiFetch } from '../lib/api'
import type { TableDensity } from './useUrlTableState'

export type AcademicTableState = {
  q: string
  status: string
  page: number
  pageSize: number
  density: TableDensity
  termId: string
  branch: string
  campus: string
  blockId: string
}

type TrainingScope = {
  campus_scoped?: boolean
  campus_codes?: string[]
  branches?: string[]
  campuses?: Array<{ campus_code?: string; branch?: string }>
  preferred_branch?: string | null
  preferred_campus?: string | null
}

const PAGE_SIZES = new Set([20, 50, 100])
const DENSITIES = new Set<TableDensity>(['compact', 'standard', 'comfortable'])

function positiveInt(value: string | null, fallback: number) {
  const parsed = Number(value)
  return Number.isFinite(parsed) && parsed > 0 ? Math.floor(parsed) : fallback
}

function normalized(value?: string | null) {
  return String(value || '').trim().toLowerCase()
}

function applyTrainingScope(branch: string, campus: string, scope: TrainingScope | null) {
  if (!scope?.campus_scoped) return { branch, campus }
  const campusCodes = new Set((scope.campus_codes || []).map(normalized).filter(Boolean))
  const branches = (scope.branches || []).map(normalized).filter(Boolean)
  const preferredBranch = normalized(scope.preferred_branch)
  const preferredCampus = normalized(scope.preferred_campus)
  let nextBranch = normalized(branch)
  if (branches.length && !branches.includes(nextBranch)) nextBranch = preferredBranch || branches[0]

  const branchCampusCodes = (scope.campuses || [])
    .filter((item) => !nextBranch || normalized(item.branch) === nextBranch)
    .map((item) => normalized(item.campus_code))
    .filter((code) => code && campusCodes.has(code))

  let nextCampus = normalized(campus)
  if (nextCampus && (!campusCodes.has(nextCampus) || (branchCampusCodes.length && !branchCampusCodes.includes(nextCampus)))) {
    nextCampus = ''
  }
  if (!nextCampus && preferredCampus && campusCodes.has(preferredCampus) && (!branchCampusCodes.length || branchCampusCodes.includes(preferredCampus))) {
    nextCampus = preferredCampus
  }
  if (!nextCampus && branchCampusCodes.length === 1) nextCampus = branchCampusCodes[0]
  return { branch: nextBranch || branch, campus: nextCampus }
}

export function useAcademicTableState(defaults: Partial<AcademicTableState> = {}) {
  const router = useRouter()
  const pathname = usePathname()
  const searchParams = useSearchParams()
  const { authReady, isAuthenticated, authHeaders, userId } = useAppContext()
  const [trainingScope, setTrainingScope] = useState<TrainingScope | null>(null)
  const [trainingScopeReady, setTrainingScopeReady] = useState(false)

  useEffect(() => {
    if (!authReady) {
      setTrainingScope(null)
      setTrainingScopeReady(false)
      return
    }
    if (!isAuthenticated) {
      setTrainingScope(null)
      setTrainingScopeReady(false)
      return
    }
    const controller = new AbortController()
    setTrainingScopeReady(false)
    apiFetch(`${API}/academic/training-scope`, {
      headers: authHeaders(),
      credentials: 'include',
      cache: 'no-store',
      timeoutMs: 15_000,
      retries: 1,
      signal: controller.signal,
    })
      .then(async (response) => response.ok ? await response.json() as TrainingScope : null)
      .then((scope) => {
        if (controller.signal.aborted) return
        setTrainingScope(scope)
        setTrainingScopeReady(true)
      })
      .catch(() => {
        if (controller.signal.aborted) return
        setTrainingScope(null)
        setTrainingScopeReady(true)
      })
    return () => controller.abort()
  }, [authHeaders, authReady, isAuthenticated, userId])

  const state = useMemo<AcademicTableState>(() => {
    const pageSize = positiveInt(searchParams.get('page_size'), defaults.pageSize || 50)
    const density = (searchParams.get('density') || defaults.density || 'compact') as TableDensity
    const rawCampus = searchParams.get('campus') ?? defaults.campus ?? ''
    const requestedBranch = searchParams.get('branch') ?? defaults.branch ?? 'poly'
    const requestedCampus = rawCampus === 'all' ? '' : rawCampus
    const scoped = applyTrainingScope(requestedBranch, requestedCampus, trainingScope)
    return {
      q: searchParams.get('q') ?? searchParams.get('search') ?? defaults.q ?? '',
      status: searchParams.get('status') ?? defaults.status ?? 'all',
      page: positiveInt(searchParams.get('page'), defaults.page || 1),
      pageSize: PAGE_SIZES.has(pageSize) ? pageSize : (defaults.pageSize || 50),
      density: DENSITIES.has(density) ? density : (defaults.density || 'compact'),
      termId: searchParams.get('term_id') ?? defaults.termId ?? '',
      branch: scoped.branch,
      campus: scoped.campus,
      blockId: searchParams.get('block_id') ?? defaults.blockId ?? '',
    }
  }, [defaults.branch, defaults.campus, defaults.density, defaults.page, defaults.pageSize, defaults.q, defaults.status, defaults.termId, defaults.blockId, searchParams, trainingScope])

  const update = useCallback((patch: Partial<AcademicTableState>, options: { replace?: boolean; resetPage?: boolean } = {}) => {
    const next = new URLSearchParams(searchParams.toString())
    let merged = { ...state, ...patch }
    const scoped = applyTrainingScope(merged.branch, merged.campus, trainingScope)
    merged = { ...merged, ...scoped }
    if (options.resetPage !== false && !Object.prototype.hasOwnProperty.call(patch, 'page')) merged.page = 1

    const values: Array<[string, string, string]> = [
      ['q', merged.q, ''],
      ['status', merged.status, 'all'],
      ['page', String(merged.page), '1'],
      ['page_size', String(merged.pageSize), '50'],
      ['density', merged.density, 'compact'],
      ['term_id', merged.termId, ''],
      ['branch', merged.branch, 'poly'],
      ['campus', merged.campus, ''],
      ['block_id', merged.blockId, ''],
    ]
    next.delete('search')
    for (const [key, value, defaultValue] of values) {
      if (!value || value === defaultValue) next.delete(key)
      else next.set(key, value)
    }
    const href = next.toString() ? `${pathname}?${next.toString()}` : pathname
    if (options.replace === false) router.push(href, { scroll: false })
    else router.replace(href, { scroll: false })
  }, [pathname, router, searchParams, state, trainingScope])

  return { state, update, scopeReady: authReady && isAuthenticated && trainingScopeReady }
}
