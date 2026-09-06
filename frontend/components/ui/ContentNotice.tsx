import type { HTMLAttributes, ReactNode } from 'react'
import { VisualIcon } from './VisualIcon'
import { userFacingError } from '../../lib/userFacingError'
import styles from './FeedbackMessage.module.css'

type Tone = 'info' | 'success' | 'warning' | 'error' | 'danger'

/** Keeps rich notice content in one column, separate from its decorative icon. */
export function ContentNotice({ tone = 'info', children, className = '', ...props }: {
  tone?: Tone
  children: ReactNode
} & HTMLAttributes<HTMLDivElement>) {
  const kind = tone === 'danger' ? 'error' : tone
  return <div role={kind === 'error' ? 'alert' : 'status'} aria-live="polite" {...props} className={`${styles.message} ${styles.contentMessage} ${styles[kind]} ${className}`}>
    <VisualIcon icon={kind === 'success' ? 'check' : kind === 'info' ? 'info' : 'alert'} tone={kind === 'success' ? 'green' : kind === 'warning' ? 'amber' : kind === 'error' ? 'red' : 'blue'} className={styles.icon} />
    <div className={styles.content}>{kind === 'error' && typeof children === 'string' ? userFacingError(children) : children}</div>
  </div>
}
