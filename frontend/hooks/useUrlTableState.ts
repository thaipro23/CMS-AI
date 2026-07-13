'use client'

import { useCallback, useMemo } from 'react'
import { usePathname, useRouter, useSearchParams } from 'next/navigation'

export type TableDensity = 'compact' | 'standard' | 'comfortable'

export type UrlTableState = {
  q: string
  status: string
  page: number
  pageSize: number
  sort: string
  density: TableDensity
}

const PAGE_SIZES = new Set([20, 50, 100])
const DENSITIES = new Set<TableDensity>(['compact', 'standard', 'comfortable'])

function positiveInt(value: string | null, fallback: number) {
  const parsed = Number(value)
  return Number.isFinite(parsed) && parsed > 0 ? Math.floor(parsed) : fallback
}

export function useUrlTableState(defaults: Partial<UrlTableState> = {}) {
  const router = useRouter()
  const pathname = usePathname()
  const searchParams = useSearchParams()

  const state = useMemo<UrlTableState>(() => {
    const pageSize = positiveInt(searchParams.get('page_size'), defaults.pageSize || 20)
    const density = (searchParams.get('density') || defaults.density || 'compact') as TableDensity
    return {
      q: searchParams.get('q') ?? defaults.q ?? '',
      status: searchParams.get('status') ?? defaults.status ?? 'all',
      page: positiveInt(searchParams.get('page'), defaults.page || 1),
      pageSize: PAGE_SIZES.has(pageSize) ? pageSize : (defaults.pageSize || 20),
      sort: searchParams.get('sort') ?? defaults.sort ?? '',
      density: DENSITIES.has(density) ? density : (defaults.density || 'compact'),
    }
  }, [defaults.density, defaults.page, defaults.pageSize, defaults.q, defaults.sort, defaults.status, searchParams])

  const update = useCallback((patch: Partial<UrlTableState>, options: { replace?: boolean; resetPage?: boolean } = {}) => {
    const next = new URLSearchParams(searchParams.toString())
    const merged = { ...state, ...patch }
    if (options.resetPage !== false && !Object.prototype.hasOwnProperty.call(patch, 'page')) merged.page = 1
    const pairs: Array<[keyof UrlTableState, string]> = [
      ['q', merged.q], ['status', merged.status], ['page', String(merged.page)], ['pageSize', String(merged.pageSize)], ['sort', merged.sort], ['density', merged.density],
    ]
    const queryKeys: Record<keyof UrlTableState, string> = { q: 'q', status: 'status', page: 'page', pageSize: 'page_size', sort: 'sort', density: 'density' }
    for (const [key, value] of pairs) {
      const queryKey = queryKeys[key]
      const defaultValue = key === 'page' ? '1' : key === 'status' ? 'all' : key === 'density' ? 'compact' : ''
      if (!value || value === defaultValue) next.delete(queryKey)
      else next.set(queryKey, value)
    }
    const href = next.toString() ? `${pathname}?${next.toString()}` : pathname
    if (options.replace === false) router.push(href, { scroll: false })
    else router.replace(href, { scroll: false })
  }, [pathname, router, searchParams, state])

  return { state, update }
}
