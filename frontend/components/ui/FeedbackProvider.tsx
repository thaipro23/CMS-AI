'use client'

import { createContext, useCallback, useContext, useMemo, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { AccessibleDialog } from './AccessibleDialog'
import { VisualIcon } from './VisualIcon'
import { userFacingError } from '../../lib/userFacingError'

export type FeedbackTone = 'success' | 'info' | 'warning' | 'danger'

type Toast = {
  id: number
  tone: FeedbackTone
  title: string
  message?: string
}

type ConfirmOptions = {
  title: string
  description: ReactNode
  confirmLabel?: string
  cancelLabel?: string
  danger?: boolean
}

type ConfirmState = ConfirmOptions & {
  resolve: (value: boolean) => void
}

type FeedbackContextValue = {
  notify: (toast: Omit<Toast, 'id'>) => void
  confirmAction: (options: ConfirmOptions) => Promise<boolean>
}

const FeedbackContext = createContext<FeedbackContextValue | null>(null)

function toneIcon(tone: FeedbackTone) {
  if (tone === 'success') return 'check' as const
  if (tone === 'warning') return 'alert' as const
  if (tone === 'danger') return 'alert' as const
  return 'info' as const
}

export function FeedbackProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([])
  const [confirmState, setConfirmState] = useState<ConfirmState | null>(null)
  const counter = useRef(0)

  const notify = useCallback((toast: Omit<Toast, 'id'>) => {
    counter.current += 1
    const id = counter.current
    const message = toast.tone === 'danger' && toast.message ? userFacingError(toast.message) : toast.message
    setToasts((current) => [...current.slice(-3), { ...toast, message, id }])
    // Errors and warnings remain readable until dismissed. Success/info can
    // disappear automatically; the corresponding inline result stays on page.
    if (toast.tone === 'success' || toast.tone === 'info') {
      window.setTimeout(() => setToasts((current) => current.filter((item) => item.id !== id)), 7000)
    }
  }, [])

  const confirmAction = useCallback((options: ConfirmOptions) => new Promise<boolean>((resolve) => {
    setConfirmState({ ...options, resolve })
  }), [])

  const settleConfirm = useCallback((result: boolean) => {
    setConfirmState((current) => {
      current?.resolve(result)
      return null
    })
  }, [])

  const value = useMemo(() => ({ notify, confirmAction }), [confirmAction, notify])

  return <FeedbackContext.Provider value={value}>
    {children}
    <div className="feedback-toast-region" role="region" aria-label="Thông báo hệ thống" aria-live="polite">
      {toasts.map((toast) => <article className={`feedback-toast tone-${toast.tone}`} key={toast.id} role={toast.tone === 'danger' ? 'alert' : 'status'}>
        <VisualIcon label={toast.title} icon={toneIcon(toast.tone)} tone={toast.tone === 'success' ? 'green' : toast.tone === 'warning' ? 'amber' : toast.tone === 'danger' ? 'red' : 'blue'} />
        <div><b>{toast.title}</b>{toast.message ? <p>{toast.message}</p> : null}</div>
        <button type="button" aria-label={`Đóng thông báo ${toast.title}`} onClick={() => setToasts((current) => current.filter((item) => item.id !== toast.id))}>×</button>
      </article>)}
    </div>
    <AccessibleDialog
      open={Boolean(confirmState)}
      title={confirmState?.title || 'Xác nhận thao tác'}
      onClose={() => settleConfirm(false)}
      size="small"
      footer={<div className="dialog-action-row">
        <button type="button" className="btn secondary" onClick={() => settleConfirm(false)}>{confirmState?.cancelLabel || 'Hủy'}</button>
        <button type="button" className={`btn${confirmState?.danger ? ' danger' : ''}`} data-dialog-autofocus onClick={() => settleConfirm(true)}>{confirmState?.confirmLabel || 'Xác nhận'}</button>
      </div>}
    >
      <div className="confirm-dialog-copy">{confirmState?.description}</div>
    </AccessibleDialog>
  </FeedbackContext.Provider>
}

export function useFeedback() {
  const value = useContext(FeedbackContext)
  if (!value) throw new Error('useFeedback must be used inside FeedbackProvider')
  return value
}
