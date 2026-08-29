import type { ReactNode } from 'react'
import type { AppIconName } from '../icons/AppIcon'
import { VisualIcon, type VisualTone } from '../ui/VisualIcon'

export type SectionHeaderProps = {
  title: string
  description?: ReactNode
  icon?: AppIconName
  tone?: VisualTone
  meta?: ReactNode
  actions?: ReactNode
  className?: string
}

export function SectionHeader({
  title,
  description,
  icon,
  tone = 'blue',
  meta,
  actions,
  className = '',
}: SectionHeaderProps) {
  return <header className={`enterprise-section-header ${className}`.trim()}>
    <div className="enterprise-section-heading">
      {icon ? <VisualIcon icon={icon} tone={tone} label={title} size={17} className="enterprise-section-icon" /> : null}
      <div className="enterprise-section-copy">
        <div className="enterprise-section-title-row">
          <h2>{title}</h2>
          {meta ? <div className="enterprise-section-meta">{meta}</div> : null}
        </div>
        {description ? <div className="enterprise-section-description">{description}</div> : null}
      </div>
    </div>
    {actions ? <div className="enterprise-section-actions">{actions}</div> : null}
  </header>
}
