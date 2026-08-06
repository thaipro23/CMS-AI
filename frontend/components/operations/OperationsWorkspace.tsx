'use client'

import type { KeyboardEvent as ReactKeyboardEvent, ReactNode } from 'react'
import type { AppIconName } from '../icons/AppIcon'
import type { VisualTone } from '../ui/VisualIcon'
import { VisualIcon } from '../ui/VisualIcon'
import { AccessibleDialog } from '../ui/AccessibleDialog'

export type OperationsMetric = {
  label: string
  value: ReactNode
  hint?: ReactNode
  tone?: 'neutral' | 'success' | 'warning' | 'danger' | 'info'
  icon?: AppIconName
}

export function OperationsKpiStrip({ items, ariaLabel = 'Tổng quan vận hành' }: { items: OperationsMetric[]; ariaLabel?: string }) {
  return <section className="operations-kpi-strip" aria-label={ariaLabel}>
    {items.map((item) => <div className={`operations-kpi visual-card tone-${item.tone || 'neutral'}`} key={item.label}>
      <VisualIcon label={item.label} icon={item.icon} tone={toneFromOperation(item.tone)} />
      <div className="operations-kpi-copy"><span>{item.label}</span><b>{item.value}</b>{item.hint ? <small>{item.hint}</small> : null}</div>
    </div>)}
  </section>
}

export function CompactFilterBar({ children, actions, ariaLabel = 'Bộ lọc' }: { children: ReactNode; actions?: ReactNode; ariaLabel?: string }) {
  return <section className="operations-filter-bar visual-filter-card" aria-label={ariaLabel}>
    <VisualIcon label={ariaLabel} icon="filter" tone="blue" className="visual-filter-icon" />
    <div className="operations-filter-fields">{children}</div>
    {actions ? <div className="operations-filter-actions">{actions}</div> : null}
  </section>
}

export type WorkspaceTab = { key: string; label: string; count?: number; icon?: AppIconName }
export function WorkspaceTabs({ tabs, active, onChange, ariaLabel = 'Nhóm cấu hình', idPrefix }: { tabs: WorkspaceTab[]; active: string; onChange: (key: string) => void; ariaLabel?: string; idPrefix?: string }) {
  function handleKey(event: ReactKeyboardEvent<HTMLButtonElement>, index: number) {
    if (!['ArrowDown', 'ArrowRight', 'ArrowUp', 'ArrowLeft', 'Home', 'End'].includes(event.key)) return
    event.preventDefault()
    let nextIndex = index
    if (event.key === 'Home') nextIndex = 0
    else if (event.key === 'End') nextIndex = tabs.length - 1
    else if (event.key === 'ArrowDown' || event.key === 'ArrowRight') nextIndex = (index + 1) % tabs.length
    else nextIndex = (index - 1 + tabs.length) % tabs.length
    const next = tabs[nextIndex]
    if (!next) return
    onChange(next.key)
    const parent = event.currentTarget.parentElement
    window.requestAnimationFrame(() => (parent?.querySelectorAll<HTMLButtonElement>('[role="tab"]')[nextIndex])?.focus())
  }

  return <div className="workspace-tabs" role="tablist" aria-label={ariaLabel}>
    {tabs.map((tab, index) => <button
      key={tab.key}
      type="button"
      role="tab"
      id={idPrefix ? `${idPrefix}-tab-${tab.key}` : undefined}
      aria-controls={idPrefix ? `${idPrefix}-panel-${tab.key}` : undefined}
      aria-selected={active === tab.key}
      tabIndex={active === tab.key ? 0 : -1}
      className={active === tab.key ? 'active' : ''}
      onKeyDown={(event) => handleKey(event, index)}
      onClick={() => onChange(tab.key)}
    >
      <VisualIcon label={tab.label} icon={tab.icon} size={14} className="workspace-tab-icon" /><span>{tab.label}</span>{typeof tab.count === 'number' ? <small>{tab.count}</small> : null}
    </button>)}
  </div>
}

export function WorkspaceSection({ title, description, actions, children, className = '', icon, tone }: { title: string; description?: string; actions?: ReactNode; children: ReactNode; className?: string; icon?: AppIconName; tone?: VisualTone }) {
  return <section className={`card workspace-section visual-section-card ${className}`.trim()}>
    <div className="workspace-section-head">
      <div className="visual-section-heading"><VisualIcon label={title} icon={icon} tone={tone} /><div><h2>{title}</h2>{description ? <p>{description}</p> : null}</div></div>
      {actions ? <div className="workspace-section-actions">{actions}</div> : null}
    </div>
    <div className="workspace-section-body">{children}</div>
  </section>
}

export function SideDrawer({ open, title, description, children, footer, onClose, width = 'large' }: { open: boolean; title: string; description?: string; children: ReactNode; footer?: ReactNode; onClose: () => void; width?: 'medium' | 'large' }) {
  return <AccessibleDialog
    open={open}
    title={title}
    description={description}
    onClose={onClose}
    placement="right"
    size={width === 'large' ? 'large' : 'medium'}
    className={`side-drawer side-drawer-${width}`}
    bodyClassName="side-drawer-body"
    footer={footer}
  >
    {children}
  </AccessibleDialog>
}

export function InfoPairGrid({ items }: { items: Array<{ label: string; value: ReactNode; wide?: boolean }> }) {
  return <dl className="info-pair-grid">
    {items.map((item) => <div className={item.wide ? 'wide' : ''} key={item.label}><dt>{item.label}</dt><dd>{item.value}</dd></div>)}
  </dl>
}

function toneFromOperation(tone?: OperationsMetric['tone']): VisualTone {
  if (tone === 'success') return 'green'
  if (tone === 'warning') return 'amber'
  if (tone === 'danger') return 'red'
  if (tone === 'info') return 'blue'
  return 'slate'
}
