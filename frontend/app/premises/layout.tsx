'use client'

import { useState } from 'react'
import type { ReactNode } from 'react'

import { getAcademicApSyncOptions, saveAcademicCampus } from '../../lib/api'
import { useAppContext } from '../../context/AppContext'
import { toUserError } from '../../components/ui/ActionMessage'

const CAMPUS_BRANCHES = ['poly', 'ptcd'] as const

export default function PremisesLayout({ children }: { children: ReactNode }) {
  const { authHeaders, isSystemAdmin, businessPermissions } = useAppContext()
  const canRefresh = isSystemAdmin || businessPermissions.includes('campus_owner.assign')
  const [refreshing, setRefreshing] = useState(false)
  const [status, setStatus] = useState('')
  const [error, setError] = useState('')

  async function refreshCampusCatalog() {
    if (refreshing) return
    setRefreshing(true)
    setStatus('')
    setError('')
    try {
      const headers = authHeaders()
      const counts: Record<string, number> = { poly: 0, ptcd: 0 }

      for (const branch of CAMPUS_BRANCHES) {
        const options = await getAcademicApSyncOptions(headers, {
          branch,
          includeSubjects: false,
        })
        const uniqueCampuses = Array.from(
          new Map(
            (options.campuses || [])
              .filter((item) => String(item.value || '').trim())
              .map((item) => [String(item.value).trim().toLowerCase(), item]),
          ).values(),
        )
        await Promise.all(
          uniqueCampuses.map((campus, index) => saveAcademicCampus(headers, {
            campus_code: String(campus.value).trim(),
            campus_name: String(campus.label || campus.value).trim(),
            branch,
            active: true,
            sort_order: index + 1,
          })),
        )
        counts[branch] = uniqueCampuses.length
      }

      setStatus(`Đã cập nhật cơ sở từ FU API: Poly ${counts.poly}, PTCĐ ${counts.ptcd}. Không đồng bộ môn tại bước này.`)
      window.setTimeout(() => window.location.reload(), 700)
    } catch (caught) {
      const detail = toUserError(caught, 'Không cập nhật được danh sách cơ sở từ FU API.')
      setError(detail.body)
    } finally {
      setRefreshing(false)
    }
  }

  return <>
    {canRefresh ? <div className="premises-catalog-refresh">
      <div className="premises-catalog-refresh__message" aria-live="polite">
        {status ? <small>{status}</small> : null}
        {error ? <small role="alert">{error}</small> : null}
      </div>
      <button className="btn secondary" type="button" onClick={() => void refreshCampusCatalog()} disabled={refreshing}>
        {refreshing ? 'Đang cập nhật cơ sở...' : 'Cập nhật cơ sở'}
      </button>
    </div> : null}
    {children}
  </>
}
