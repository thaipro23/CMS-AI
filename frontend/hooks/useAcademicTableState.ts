'use client'

import { useCallback, useMemo } from 'react'
import { usePathname, useRouter, useSearchParams } from 'next/navigation'
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
}

const PAGE_SIZES = new Set([20, 50, 100])
const DENSITIES = new Set<TableDensity>(['compact', 'standard', 'comfortable'])

function positiveInt(value: string | null, fallback: number) {
  const parsed = Number(value)
  return Number.isFinite(parsed) && parsed > 0 ? Math.floor(parsed) : fallback
}

export function useAcademicTableState(defaults: Partial<AcademicTableState> = {}) {
  const router = useRouter()
  const pathname = usePathname()
  const searchParams = useSearchParams()

  const state = useMemo<AcademicTableState>(() => {
    const pageSize = positiveInt(searchParams.get('page_size'), defaults.pageSize || 50)
    const density = (searchParams.get('density') || defaults.density || 'compact') as TableDensity
    const rawCampus = searchParams.get('campus') ?? defaults.campus ?? ''
    return {
      q: searchParams.get('q') ?? searchParams.get('search') ?? defaults.q ?? '',
      status: searchParams.get('status') ?? defaults.status ?? 'all',
      page: positiveInt(searchParams.get('page'), defaults.page || 1),
      pageSize: PAGE_SIZES.has(pageSize) ? pageSize : (defaults.pageSize || 50),
      density: DENSITIES.has(density) ? density : (defaults.density || 'compact'),
      termId: searchParams.get('term_id') ?? defaults.termId ?? '',
      branch: searchParams.get('branch') ?? defaults.branch ?? 'poly',
      campus: rawCampus === 'all' ? '' : rawCampus,
    }
  }, [defaults.branch, defaults.campus, defaults.density, defaults.page, defaults.pageSize, defaults.q, defaults.status, defaults.termId, searchParams])

  const update = useCallback((patch: Partial<AcademicTableState>, options: { replace?: boolean; resetPage?: boolean } = {}) => {
    const next = new URLSearchParams(searchParams.toString())
    const merged = { ...state, ...patch }
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
    ]
    next.delete('search')
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
