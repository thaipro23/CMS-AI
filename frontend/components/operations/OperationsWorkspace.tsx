'use client'

import { useEffect, useId, useRef } from 'react'
import type { KeyboardEvent as ReactKeyboardEvent, ReactNode } from 'react'
import type { AppIconName } from '../icons/AppIcon'
import type { VisualTone } from '../ui/VisualIcon'
import { VisualIcon } from '../ui/VisualIcon'

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
export function WorkspaceTabs({ tabs, active, onChange, ariaLabel = 'Nhóm cấu hình' }: { tabs: WorkspaceTab[]; active: string; onChange: (key: string) => void; ariaLabel?: string }) {
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

const FOCUSABLE = 'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'

export function SideDrawer({ open, title, description, children, footer, onClose, width = 'large' }: { open: boolean; title: string; description?: string; children: ReactNode; footer?: ReactNode; onClose: () => void; width?: 'medium' | 'large' }) {
  const titleId = useId()
  const descriptionId = useId()
  const closeRef = useRef<HTMLButtonElement | null>(null)
  const panelRef = useRef<HTMLElement | null>(null)

  useEffect(() => {
    if (!open) return undefined
    const previous = document.activeElement as HTMLElement | null
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault()
        onClose()
        return
      }
      if (event.key !== 'Tab') return
      const focusable = Array.from(panelRef.current?.querySelectorAll<HTMLElement>(FOCUSABLE) || []).filter((item) => item.offsetParent !== null)
      if (!focusable.length) return
      const first = focusable[0]
      const last = focusable[focusable.length - 1]
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault()
        last.focus()
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault()
        first.focus()
      }
    }
    document.addEventListener('keydown', onKey)
    window.setTimeout(() => closeRef.current?.focus(), 0)
    return () => {
      document.removeEventListener('keydown', onKey)
      document.body.style.overflow = previousOverflow
      previous?.focus?.()
    }
  }, [open, onClose])

  if (!open) return null
  return <div className="side-drawer-backdrop" onMouseDown={onClose}>
    <aside ref={panelRef} className={`side-drawer side-drawer-${width}`} role="dialog" aria-modal="true" aria-labelledby={titleId} aria-describedby={description ? descriptionId : undefined} onMouseDown={(event) => event.stopPropagation()}>
      <header><div><h2 id={titleId}>{title}</h2>{description ? <p id={descriptionId}>{description}</p> : null}</div><button ref={closeRef} type="button" className="btn small secondary" aria-label={`Đóng ${title}`} onClick={onClose}>Đóng</button></header>
      <div className="side-drawer-body">{children}</div>
      {footer ? <footer>{footer}</footer> : null}
    </aside>
  </div>
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
