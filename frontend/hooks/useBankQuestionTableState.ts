'use client'

import { useCallback, useMemo } from 'react'
import { usePathname, useRouter, useSearchParams } from 'next/navigation'
import type { TableDensity } from './useUrlTableState'

const PAGE_SIZES = new Set([20, 50, 100])
const DENSITIES = new Set<TableDensity>(['compact', 'standard', 'comfortable'])

export type BankQuestionTableState = {
  q: string
  status: string
  difficulty: string
  sort: string
  page: number
  pageSize: number
  density: TableDensity
}

function positiveInt(value: string | null, fallback: number) {
  const parsed = Number(value)
  return Number.isFinite(parsed) && parsed > 0 ? Math.floor(parsed) : fallback
}

export function useBankQuestionTableState() {
  const router = useRouter()
  const pathname = usePathname()
  const searchParams = useSearchParams()
  const state = useMemo<BankQuestionTableState>(() => {
    const pageSize = positiveInt(searchParams.get('page_size'), 20)
    const density = (searchParams.get('density') || 'compact') as TableDensity
    return {
      q: searchParams.get('q') || '',
      status: searchParams.get('status') || 'all',
      difficulty: searchParams.get('difficulty') || 'all',
      sort: searchParams.get('sort') || 'needs_review',
      page: positiveInt(searchParams.get('page'), 1),
      pageSize: PAGE_SIZES.has(pageSize) ? pageSize : 20,
      density: DENSITIES.has(density) ? density : 'compact',
    }
  }, [searchParams])

  const update = useCallback((patch: Partial<BankQuestionTableState>, options: { replace?: boolean; resetPage?: boolean } = {}) => {
    const merged = { ...state, ...patch }
    if (options.resetPage !== false && patch.page === undefined) merged.page = 1
    const params = new URLSearchParams(searchParams.toString())
    const values: Record<string, string> = {
      q: merged.q,
      status: merged.status,
      difficulty: merged.difficulty,
      sort: merged.sort,
      page: String(merged.page),
      page_size: String(merged.pageSize),
      density: merged.density,
    }
    const defaults: Record<string, string> = { q: '', status: 'all', difficulty: 'all', sort: 'needs_review', page: '1', page_size: '20', density: 'compact' }
    for (const [key, value] of Object.entries(values)) {
      if (!value || value === defaults[key]) params.delete(key)
      else params.set(key, value)
    }
    const href = params.toString() ? `${pathname}?${params.toString()}` : pathname
    if (options.replace === false) router.push(href, { scroll: false })
    else router.replace(href, { scroll: false })
  }, [pathname, router, searchParams, state])

  return { state, update }
}
