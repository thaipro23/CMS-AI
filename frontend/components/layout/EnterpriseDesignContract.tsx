'use client'

import type { ReactNode } from 'react'
import type { AppIconName } from '../icons/AppIcon'
import type { VisualTone } from '../ui/VisualIcon'
import { VisualIcon } from '../ui/VisualIcon'
import { SectionHeader } from './SectionHeader'
import { PageHeader } from './PageHeader'
import type { PageBreadcrumb } from './PageShellContext'

export function EnterprisePageIdentity({
  title,
  description,
  icon = 'dashboard',
  tone = 'blue',
  actions,
  meta,
  className = '',
}: {
  title: string
  description: ReactNode
  icon?: AppIconName
  tone?: VisualTone
  actions?: ReactNode
  meta?: ReactNode
  className?: string
}) {
  return <header className={`enterprise-page-identity ${className}`.trim()}>
    <div className="enterprise-page-identity__main">
      <VisualIcon icon={icon} tone={tone} label={title} size={22} className="enterprise-page-identity__icon" />
      <div className="enterprise-page-identity__copy">
        <div className="enterprise-page-identity__title-row">
          <h1>{title}</h1>
          {meta ? <div className="enterprise-page-identity__meta">{meta}</div> : null}
        </div>
        <p>{description}</p>
      </div>
    </div>
    {actions ? <div className="enterprise-page-identity__actions">{actions}</div> : null}
  </header>
}

export function EnterpriseScreenHeader({
  title,
  description,
  eyebrow,
  icon = 'dashboard',
  tone = 'blue',
  breadcrumbs,
  primaryAction,
  secondaryActions,
  meta,
  className = '',
}: {
  title: string
  description: ReactNode
  eyebrow?: string
  icon?: AppIconName
  tone?: VisualTone
  breadcrumbs?: PageBreadcrumb[]
  primaryAction?: ReactNode
  secondaryActions?: ReactNode
  meta?: ReactNode
  className?: string
}) {
  const actions = primaryAction || secondaryActions
    ? <>{secondaryActions}{primaryAction}</>
    : undefined

  return <>
    <PageHeader title={title} eyebrow={eyebrow} icon={icon} tone={tone} breadcrumbs={breadcrumbs} />
    <EnterprisePageIdentity
      title={title}
      description={description}
      icon={icon}
      tone={tone}
      actions={actions}
      meta={meta}
      className={className}
    />
  </>
}

export function EnterpriseSection({
  title,
  description,
  icon,
  tone = 'blue',
  meta,
  actions,
  children,
  className = '',
  bodyClassName = '',
}: {
  title: string
  description?: ReactNode
  icon?: AppIconName
  tone?: VisualTone
  meta?: ReactNode
  actions?: ReactNode
  children: ReactNode
  className?: string
  bodyClassName?: string
}) {
  return <section className={`enterprise-contract-section ${className}`.trim()}>
    <SectionHeader title={title} description={description} icon={icon} tone={tone} meta={meta} actions={actions} className="enterprise-contract-section__header" />
    <div className={`enterprise-contract-section__body ${bodyClassName}`.trim()}>{children}</div>
  </section>
}
