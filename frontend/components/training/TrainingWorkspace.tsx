'use client'

import type { ReactNode } from 'react'
import { AppIcon, type AppIconName } from '../icons/AppIcon'
import { VisualIcon } from '../ui/VisualIcon'

export type TrainingWorkflowStep = {
  key: string
  label: string
  description?: string
  disabled?: boolean
}

export function TrainingWorkflowSteps({
  steps,
  activeKey,
  onChange,
  ariaLabel = 'Các bước xử lý',
}: {
  steps: TrainingWorkflowStep[]
  activeKey: string
  onChange: (key: string) => void
  ariaLabel?: string
}) {
  return <nav className="training-workflow-steps" aria-label={ariaLabel}>
    {steps.map((step, index) => {
      const active = step.key === activeKey
      const activeIndex = steps.findIndex((item) => item.key === activeKey)
      const completed = activeIndex > index
      return <button
        key={step.key}
        type="button"
        className={active ? 'is-active' : completed ? 'is-complete' : ''}
        disabled={step.disabled}
        aria-current={active ? 'step' : undefined}
        onClick={() => onChange(step.key)}
      >
        <span className="training-workflow-index" aria-hidden="true">{completed ? <AppIcon name="check" size={15} /> : index + 1}</span>
        <span className="training-workflow-copy">
          <b>{step.label}</b>
          {step.description ? <small>{step.description}</small> : null}
        </span>
      </button>
    })}
  </nav>
}

export function TrainingContextChips({ items }: { items: Array<string | null | undefined> }) {
  const values = items.filter((item): item is string => Boolean(item))
  if (!values.length) return null
  return <div className="training-context-chips" aria-label="Phạm vi hiện tại">
    {values.map((item, index) => <span key={`${item}-${index}`}>{item}</span>)}
  </div>
}

export type TrainingKpi = {
  key: string
  label: string
  value: ReactNode
  hint?: ReactNode
  tone?: 'neutral' | 'success' | 'warning' | 'danger'
  icon?: AppIconName
}

export function TrainingKpiStrip({ items, compact = false }: { items: TrainingKpi[]; compact?: boolean }) {
  return <div className={`training-kpi-strip${compact ? ' is-compact' : ''}`}>
    {items.map((item) => <div key={item.key} className={`training-kpi visual-card training-kpi-${item.tone || 'neutral'}`}>
      <VisualIcon label={item.label} icon={item.icon} tone={item.tone === 'success' ? 'green' : item.tone === 'warning' ? 'amber' : item.tone === 'danger' ? 'red' : undefined} />
      <div className="training-kpi-copy"><span>{item.label}</span><b>{item.value}</b>{item.hint ? <small>{item.hint}</small> : null}</div>
    </div>)}
  </div>
}

export function TrainingMappingEmptyState({
  title = 'Chưa ghép Course CMS',
  description = 'Dữ liệu học tập chưa thể tổng hợp đầy đủ cho đến khi lớp được ghép đúng Course CMS.',
  action,
}: {
  title?: string
  description?: string
  action?: ReactNode
}) {
  return <div className="training-mapping-empty-state" role="status">
    <VisualIcon label={title} icon="link" tone="amber" className="training-mapping-empty-icon" />
    <div>
      <b>{title}</b>
      <p>{description}</p>
      {action ? <div className="training-mapping-empty-action">{action}</div> : null}
    </div>
  </div>
}
