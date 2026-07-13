import type { ReactNode } from 'react'

export function PageHeader({
  title,
  description,
  eyebrow,
  primaryAction,
  secondaryActions,
  className = '',
}: {
  title: string
  description?: ReactNode
  eyebrow?: string
  primaryAction?: ReactNode
  secondaryActions?: ReactNode
  className?: string
}) {
  return <header className={`enterprise-page-header ${className}`.trim()}>
    <div className="enterprise-page-header-copy">
      {eyebrow && <span className="enterprise-page-eyebrow">{eyebrow}</span>}
      <h1>{title}</h1>
      {description && <div className="enterprise-page-description">{description}</div>}
    </div>
    {(primaryAction || secondaryActions) && <div className="enterprise-page-actions">
      {secondaryActions}
      {primaryAction}
    </div>}
  </header>
}
