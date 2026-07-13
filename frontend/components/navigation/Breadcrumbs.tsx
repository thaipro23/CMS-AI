'use client'

import Link from 'next/link'

export type BreadcrumbItem = {
  label: string
  href?: string
}

export function Breadcrumbs({ items, ariaLabel = 'Điều hướng phân cấp', compact = false }: { items: BreadcrumbItem[]; ariaLabel?: string; compact?: boolean }) {
  const safeItems = items.filter((item) => item.label?.trim())
  if (!safeItems.length) return null
  return <nav className={compact ? 'enterprise-breadcrumbs compact' : 'enterprise-breadcrumbs'} aria-label={ariaLabel}>
    <ol>
      {safeItems.map((item, index) => {
        const current = index === safeItems.length - 1
        return <li key={`${item.label}-${index}`} aria-current={current ? 'page' : undefined}>
          {index > 0 && <span className="enterprise-breadcrumb-separator" aria-hidden="true">›</span>}
          {!current && item.href ? <Link href={item.href}>{item.label}</Link> : <span className={current ? 'current' : undefined}>{item.label}</span>}
        </li>
      })}
    </ol>
  </nav>
}
