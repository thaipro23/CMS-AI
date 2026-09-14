'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'

import { useAppContext } from '../../context/AppContext'
import { useAcademicTableState } from '../../hooks/useAcademicTableState'
import {
  downloadLatestTeacherReportArtifact,
  getLatestTeacherReportArtifact,
  type LatestTeacherReportArtifact,
} from '../../lib/teacherReportArtifacts'


function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  window.setTimeout(() => URL.revokeObjectURL(url), 1000)
}

function vnDateTime(value?: string | null) {
  if (!value) return 'Chưa có'
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return 'Chưa có'
  return new Intl.DateTimeFormat('vi-VN', {
    timeZone: 'Asia/Ho_Chi_Minh',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour12: false,
  }).format(parsed)
}

export function CmsTeacherReportArtifactBar() {
  const { authHeaders } = useAppContext()
  const headers = useMemo(() => authHeaders(), [authHeaders])
  const { state } = useAcademicTableState({ branch: 'poly', status: 'all', pageSize: 50 })
  const { termId, branch, campus } = state
  const [artifact, setArtifact] = useState<LatestTeacherReportArtifact | null>(null)
  const [loading, setLoading] = useState(false)
  const [downloading, setDownloading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async (signal?: AbortSignal) => {
    if (!termId) {
      setArtifact(null)
      setError(null)
      return
    }
    setLoading(true)
    try {
      const value = await getLatestTeacherReportArtifact(
        headers,
        { termId, branch, campus: campus || null },
        signal,
      )
      if (signal?.aborted) return
      setArtifact(value)
      setError(null)
    } catch (exc) {
      if (signal?.aborted) return
      setArtifact(null)
      setError(exc instanceof Error ? exc.message : 'Không đọc được file báo cáo 05:00.')
    } finally {
      if (!signal?.aborted) setLoading(false)
    }
  }, [branch, campus, headers, termId])

  useEffect(() => {
    const controller = new AbortController()
    void load(controller.signal)
    const timer = window.setInterval(() => void load(controller.signal), 60_000)
    return () => {
      window.clearInterval(timer)
      controller.abort()
    }
  }, [load])

  const download = useCallback(async () => {
    if (!termId || !artifact?.available) return
    setDownloading(true)
    setError(null)
    try {
      const result = await downloadLatestTeacherReportArtifact(
        headers,
        { termId, branch, campus: campus || null },
      )
      downloadBlob(result.blob, result.filename)
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : 'Không tải được file báo cáo.')
    } finally {
      setDownloading(false)
    }
  }, [artifact?.available, branch, campus, headers, termId])

  const scopeLabel = campus ? `Cơ sở ${campus.toUpperCase()}` : 'HO · toàn hệ thống trong hệ đã chọn'
  const run = artifact?.today_run
  const runPercent = run?.progress_total
    ? Math.round((Number(run.progress_current || 0) / Math.max(1, Number(run.progress_total))) * 100)
    : null

  return (
    <section className="card cms-teacher-artifact-bar" aria-label="Báo cáo Excel quản lý giảng viên đã tạo sẵn">
      <div className="cms-teacher-artifact-bar__copy">
        <div className="cms-teacher-artifact-bar__title">Báo cáo quản lý giảng viên · {scopeLabel}</div>
        <div className="cms-teacher-artifact-bar__meta">
          <span>Dữ liệu điểm: {vnDateTime(artifact?.source_synced_at)}</span>
          <span>File Excel: {vnDateTime(artifact?.generated_at)}</span>
          <span>Múi giờ: GMT+7</span>
        </div>
        {artifact?.warning ? <div className="cms-teacher-artifact-bar__warning">⚠ {artifact.warning}</div> : null}
        {!artifact?.available && run && ['queued', 'running'].includes(String(run.status || '')) ? (
          <div className="cms-teacher-artifact-bar__status">
            Đợt 05:00 đang xử lý{runPercent !== null ? ` · ${runPercent}%` : ''}{run.progress_label ? ` · ${run.progress_label}` : ''}
          </div>
        ) : null}
        {error ? <div className="cms-teacher-artifact-bar__error">{error}</div> : null}
      </div>
      <div className="cms-teacher-artifact-bar__actions">
        <button
          className="btn secondary"
          type="button"
          onClick={() => void load()}
          disabled={!termId || loading}
        >
          {loading ? 'Đang kiểm tra…' : 'Kiểm tra file'}
        </button>
        <button
          className="btn"
          type="button"
          onClick={() => void download()}
          disabled={!termId || !artifact?.available || downloading}
        >
          {downloading ? 'Đang tải…' : 'Tải Excel'}
        </button>
      </div>
      <style jsx>{`
        .cms-teacher-artifact-bar {
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 18px;
          margin: 0 0 14px;
          padding: 14px 16px;
        }
        .cms-teacher-artifact-bar__copy { display: grid; gap: 6px; min-width: 0; }
        .cms-teacher-artifact-bar__title { font-weight: 800; }
        .cms-teacher-artifact-bar__meta { display: flex; flex-wrap: wrap; gap: 8px 18px; font-size: 13px; opacity: .82; }
        .cms-teacher-artifact-bar__warning { color: #9a6700; font-size: 13px; font-weight: 650; }
        .cms-teacher-artifact-bar__status { font-size: 13px; color: #1d4ed8; }
        .cms-teacher-artifact-bar__error { font-size: 13px; color: #b91c1c; }
        .cms-teacher-artifact-bar__actions { display: flex; align-items: center; gap: 8px; flex: 0 0 auto; }
        @media (max-width: 760px) {
          .cms-teacher-artifact-bar { align-items: stretch; flex-direction: column; }
          .cms-teacher-artifact-bar__actions { width: 100%; }
          .cms-teacher-artifact-bar__actions :global(.btn) { flex: 1; }
        }
      `}</style>
    </section>
  )
}
