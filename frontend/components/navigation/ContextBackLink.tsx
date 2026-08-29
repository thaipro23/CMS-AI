import Link from 'next/link'
import { AppIcon } from '../icons/AppIcon'

export function ContextBackLink({ href, label, className = '' }: { href: string; label: string; className?: string }) {
  return <Link className={`context-back-link ${className}`.trim()} href={href}>
    <AppIcon name="chevron-right" size={16} className="context-back-link-icon" />
    <span>{label}</span>
  </Link>
}
