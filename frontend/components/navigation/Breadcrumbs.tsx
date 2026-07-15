'use client'

export type BreadcrumbItem = { label: string; href?: string }

/**
 * Breadcrumbs were intentionally removed from main content in v25.9.16.7.2.64.16.5.7.2.2.
 * Route context and the single page title are rendered in the application top bar.
 * Keep this compatibility component temporarily so legacy route modules do not break while
 * their markup is incrementally simplified.
 */
export function Breadcrumbs(_props: { items: BreadcrumbItem[]; ariaLabel?: string; compact?: boolean }) {
  return null
}
