'use client'

import { useState } from 'react'
import type { ReactNode } from 'react'

import { getAcademicApSyncOptions, saveAcademicCampus } from '../../lib/api'
import { useAppContext } from '../../context/AppContext'
import { toUserError } from '../../components/ui/ActionMessage'

const CATALOG_TERM_NAME = 'Fall 2026'
const CATALOG_BRANCH = 'poly'

export default function UsersLayout({ children }: { children: ReactNode }) {
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
      const options = await getAcademicApSyncOptions(headers, {
        branch: CATALOG_BRANCH,
        termName: CATALOG_TERM_NAME,
        includeSubjects: true,
      })
      const uniqueCampuses = Array.from(
        new Map(
          (options.campuses || [])
            .filter((item) => String(item.value || '').trim())
            .map((item) => [String(item.value).trim().toLowerCase(), item]),
        ).values(),
      )
      if (!uniqueCampuses.length) {
        throw new Error('FU API không trả danh sách cơ sở POLY.')
      }
      await Promise.all(
        uniqueCampuses.map((campus, index) => saveAcademicCampus(headers, {
          campus_code: String(campus.value).trim(),
          campus_name: String(campus.label || campus.value).trim(),
          branch: CATALOG_BRANCH,
          active: true,
          sort_order: index + 1,
        })),
      )
      const subjectCount = (options.subjects || []).length
      const warningText = (options.warnings || []).filter(Boolean).join(' · ')
      setStatus(
        `Đã cập nhật ${uniqueCampuses.length} cơ sở từ FU API và đọc ${subjectCount} môn cho ${CATALOG_TERM_NAME}.` +
        (warningText ? ` Cảnh báo: ${warningText}` : ''),
      )
      window.setTimeout(() => window.location.reload(), 700)
    } catch (caught) {
      const detail = toUserError(caught, 'Không cập nhật được danh sách cơ sở từ FU API.')
      setError(detail.body)
    } finally {
      setRefreshing(false)
    }
  }

  return <>
    {canRefresh ? <div style={{ display: 'flex', justifyContent: 'flex-end', alignItems: 'center', gap: 12, padding: '14px 24px 0' }}>
      {status ? <small style={{ maxWidth: 720 }}>{status}</small> : null}
      {error ? <small role="alert" style={{ maxWidth: 720 }}>{error}</small> : null}
      <button className="btn secondary" type="button" onClick={() => void refreshCampusCatalog()} disabled={refreshing}>
        {refreshing ? 'Đang cập nhật cơ sở...' : 'Cập nhật cơ sở'}
      </button>
    </div> : null}
    {children}
  </>
}
