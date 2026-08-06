'use client'

import type { ReactNode } from 'react'
import type { AcademicBulkOperationJob } from '../../types'
import { VisualIcon } from './VisualIcon'

export function PersistentJobNotice({
  job,
  title,
  description,
  action,
  tone,
}: {
  job: AcademicBulkOperationJob
  title: string
  description?: string
  action?: ReactNode
  tone?: 'info' | 'success' | 'warning' | 'error'
}) {
  const statusTone = tone || (job.status === 'failed' ? 'error' : job.status === 'completed' ? 'success' : 'info')
  const total = Math.max(1, Number(job.progress_total || 100))
  const current = Math.max(0, Math.min(total, Number(job.progress_current || 0)))
  const percent = Math.round((current / total) * 100)
  const active = ['queued', 'running'].includes(job.status)
  const body = description || job.error_message || job.progress_label || 'Hệ thống đang xử lý tác vụ nền.'

  return <section
    className={`academic-inline-notice enterprise-inline-notice persistent-job-notice ${statusTone}`}
    role={statusTone === 'error' ? 'alert' : 'status'}
    aria-live="polite"
    aria-busy={active}
  >
    <VisualIcon
      label={title}
      icon={statusTone === 'error' || statusTone === 'warning' ? 'alert' : statusTone === 'success' ? 'check' : 'clock'}
      tone={statusTone === 'error' ? 'red' : statusTone === 'warning' ? 'amber' : statusTone === 'success' ? 'green' : 'blue'}
      className="notice-visual-icon"
    />
    <div className="notice-copy persistent-job-copy">
      <b>{title}</b>
      <span>{body}</span>
      <div className="persistent-job-progress-row">
        <progress max={total} value={current} aria-label={`${title}: ${percent}%`} />
        <small>{percent}%</small>
      </div>
    </div>
    {action ? <div className="persistent-job-action">{action}</div> : null}
  </section>
}
