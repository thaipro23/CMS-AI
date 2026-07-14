import type { ReactNode } from 'react'
import type { AppIconName } from '../icons/AppIcon'
import type { VisualTone } from '../ui/VisualIcon'
import { VisualIcon } from '../ui/VisualIcon'

export function PageHeader({
  title,
  description,
  eyebrow,
  primaryAction,
  secondaryActions,
  className = '',
  icon,
  tone,
}: {
  title: string
  description?: ReactNode
  eyebrow?: string
  primaryAction?: ReactNode
  secondaryActions?: ReactNode
  className?: string
  icon?: AppIconName
  tone?: VisualTone
}) {
  return <header className={`enterprise-page-header ${className}`.trim()}>
    <div className="enterprise-page-header-leading">
      <VisualIcon label={`${eyebrow || ''} ${title}`} icon={icon} tone={tone} size={21} className="enterprise-page-header-icon" />
      <div className="enterprise-page-header-copy">
      {eyebrow && <span className="enterprise-page-eyebrow">{eyebrow}</span>}
      <h1>{title}</h1>
      {description && <div className="enterprise-page-description">{description}</div>}
      </div>
    </div>
    {(primaryAction || secondaryActions) && <div className="enterprise-page-actions">
      {secondaryActions}
      {primaryAction}
    </div>}
  </header>
}
