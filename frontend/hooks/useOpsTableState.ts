'use client'

import { useCallback, useMemo } from 'react'
import { usePathname, useRouter, useSearchParams } from 'next/navigation'
import type { TableDensity } from './useUrlTableState'

export type OpsTableState = {
  q: string
  status: string
  group: string
  errorType: string
  actorId: string
  page: number
  pageSize: number
  density: TableDensity
}

const PAGE_SIZES = new Set([20, 50, 100])
const DENSITIES = new Set<TableDensity>(['compact', 'standard', 'comfortable'])
function positiveInt(value: string | null, fallback: number) {
  const parsed = Number(value)
  return Number.isFinite(parsed) && parsed > 0 ? Math.floor(parsed) : fallback
}

export function useOpsTableState(defaults: Partial<OpsTableState> = {}) {
  const router = useRouter()
  const pathname = usePathname()
  const searchParams = useSearchParams()
  const state = useMemo<OpsTableState>(() => {
    const pageSize = positiveInt(searchParams.get('page_size'), defaults.pageSize || 20)
    const density = (searchParams.get('density') || defaults.density || 'compact') as TableDensity
    return {
      q: searchParams.get('q') ?? defaults.q ?? '',
      status: searchParams.get('status') ?? defaults.status ?? 'all',
      group: searchParams.get('group') ?? defaults.group ?? 'all',
      errorType: searchParams.get('error_type') ?? defaults.errorType ?? 'all',
      actorId: searchParams.get('actor_id') ?? defaults.actorId ?? '',
      page: positiveInt(searchParams.get('page'), defaults.page || 1),
      pageSize: PAGE_SIZES.has(pageSize) ? pageSize : (defaults.pageSize || 20),
      density: DENSITIES.has(density) ? density : (defaults.density || 'compact'),
    }
  }, [defaults.actorId, defaults.density, defaults.errorType, defaults.group, defaults.page, defaults.pageSize, defaults.q, defaults.status, searchParams])

  const update = useCallback((patch: Partial<OpsTableState>, options: { replace?: boolean; resetPage?: boolean } = {}) => {
    const next = new URLSearchParams(searchParams.toString())
    const merged = { ...state, ...patch }
    if (options.resetPage !== false && !Object.prototype.hasOwnProperty.call(patch, 'page')) merged.page = 1
    const values: Array<[string, string, string]> = [
      ['q', merged.q, ''], ['status', merged.status, 'all'], ['group', merged.group, 'all'],
      ['error_type', merged.errorType, 'all'], ['actor_id', merged.actorId, ''],
      ['page', String(merged.page), '1'], ['page_size', String(merged.pageSize), '20'], ['density', merged.density, 'compact'],
    ]
    for (const [key, value, defaultValue] of values) {
      if (!value || value === defaultValue) next.delete(key)
      else next.set(key, value)
    }
    const href = next.toString() ? `${pathname}?${next.toString()}` : pathname
    if (options.replace === false) router.push(href, { scroll: false })
    else router.replace(href, { scroll: false })
  }, [pathname, router, searchParams, state])
  return { state, update }
}
