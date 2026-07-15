'use client'

import { useId, useLayoutEffect, type ReactNode } from 'react'
import type { AppIconName } from '../icons/AppIcon'
import type { VisualTone } from '../ui/VisualIcon'
import { usePageShellRegistration, type PageBreadcrumb } from './PageShellContext'

export function PageHeader({
  title,
  eyebrow,
  primaryAction,
  secondaryActions,
  className = '',
  icon,
  tone,
  breadcrumbs,
}: {
  title: string
  eyebrow?: string
  primaryAction?: ReactNode
  secondaryActions?: ReactNode
  className?: string
  icon?: AppIconName
  tone?: VisualTone
  breadcrumbs?: PageBreadcrumb[]
}) {
  const registration = usePageShellRegistration()
  const registrationId = useId()

  useLayoutEffect(() => {
    if (!registration) return undefined
    return registration.registerChrome({ registrationId, eyebrow, title, icon, tone, breadcrumbs })
  }, [breadcrumbs, eyebrow, icon, registration, registrationId, title, tone])

  if (!primaryAction && !secondaryActions) return null

  return <header className={`enterprise-page-header enterprise-page-header-actions-only ${className}`.trim()}>
    <div className="enterprise-page-actions">
      {secondaryActions}
      {primaryAction}
    </div>
  </header>
}
export { PageRoot } from './PageShellContext'
