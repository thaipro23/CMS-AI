import type { ReactNode } from 'react'

export function FilterToolbar({
  children,
  actions,
  ariaLabel = 'Bộ lọc dữ liệu',
  className = '',
}: {
  children: ReactNode
  actions?: ReactNode
  ariaLabel?: string
  className?: string
}) {
  return <div className={`enterprise-filter-toolbar ${className}`.trim()} role="search" aria-label={ariaLabel}>
    <div className="enterprise-filter-fields">{children}</div>
    {actions ? <div className="enterprise-filter-actions">{actions}</div> : null}
  </div>
}
