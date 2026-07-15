'use client'

import { createPortal } from 'react-dom'
import { useEffect, useId, useMemo, useRef, useState } from 'react'
import type { ReactNode, RefObject } from 'react'
import { AppIcon } from '../icons/AppIcon'

const FOCUSABLE_SELECTOR = [
  'a[href]',
  'button:not([disabled])',
  'input:not([disabled]):not([type="hidden"])',
  'select:not([disabled])',
  'textarea:not([disabled])',
  '[tabindex]:not([tabindex="-1"])',
].join(',')

const dialogStack: symbol[] = []
let bodyLockCount = 0
let originalBodyOverflow = ''
let originalBodyPaddingRight = ''

function lockBodyScroll() {
  if (bodyLockCount === 0) {
    originalBodyOverflow = document.body.style.overflow
    originalBodyPaddingRight = document.body.style.paddingRight
    const scrollbarWidth = Math.max(0, window.innerWidth - document.documentElement.clientWidth)
    document.body.style.overflow = 'hidden'
    if (scrollbarWidth > 0) document.body.style.paddingRight = `${scrollbarWidth}px`
  }
  bodyLockCount += 1
}

function unlockBodyScroll() {
  bodyLockCount = Math.max(0, bodyLockCount - 1)
  if (bodyLockCount === 0) {
    document.body.style.overflow = originalBodyOverflow
    document.body.style.paddingRight = originalBodyPaddingRight
  }
}

function visibleFocusable(panel: HTMLElement | null) {
  if (!panel) return []
  return Array.from(panel.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR)).filter((element) => {
    if (element.hasAttribute('disabled') || element.getAttribute('aria-hidden') === 'true') return false
    const style = window.getComputedStyle(element)
    return style.visibility !== 'hidden' && style.display !== 'none'
  })
}

export type AccessibleDialogProps = {
  open: boolean
  title: string
  description?: ReactNode
  children: ReactNode
  footer?: ReactNode
  onClose: () => void
  size?: 'small' | 'medium' | 'large' | 'xlarge' | 'viewport'
  placement?: 'center' | 'right'
  closeLabel?: string
  closeOnBackdrop?: boolean
  busy?: boolean
  className?: string
  bodyClassName?: string
  initialFocusRef?: RefObject<HTMLElement | null>
}

export function AccessibleDialog({
  open,
  title,
  description,
  children,
  footer,
  onClose,
  size = 'medium',
  placement = 'center',
  closeLabel = 'Đóng',
  closeOnBackdrop = true,
  busy = false,
  className = '',
  bodyClassName = '',
  initialFocusRef,
}: AccessibleDialogProps) {
  const titleId = useId()
  const descriptionId = useId()
  const panelRef = useRef<HTMLDivElement | null>(null)
  const closeRef = useRef<HTMLButtonElement | null>(null)
  const token = useMemo(() => Symbol('accessible-dialog'), [])
  const [mounted, setMounted] = useState(false)

  useEffect(() => setMounted(true), [])

  useEffect(() => {
    if (!open || !mounted) return undefined
    const previousActive = document.activeElement instanceof HTMLElement ? document.activeElement : null
    dialogStack.push(token)
    lockBodyScroll()

    const isTopmost = () => dialogStack[dialogStack.length - 1] === token
    const focusInitial = () => {
      const explicit = initialFocusRef?.current
      const autofocus = panelRef.current?.querySelector<HTMLElement>('[data-dialog-autofocus]')
      const first = visibleFocusable(panelRef.current)[0]
      ;(explicit || autofocus || first || panelRef.current)?.focus({ preventScroll: true })
    }
    const focusTimer = window.setTimeout(focusInitial, 0)

    const onKeyDown = (event: KeyboardEvent) => {
      if (!isTopmost()) return
      if (event.key === 'Escape') {
        if (busy) return
        event.preventDefault()
        onClose()
        return
      }
      if (event.key !== 'Tab') return
      const focusable = visibleFocusable(panelRef.current)
      if (!focusable.length) {
        event.preventDefault()
        panelRef.current?.focus()
        return
      }
      const first = focusable[0]
      const last = focusable[focusable.length - 1]
      const current = document.activeElement
      if (event.shiftKey && (current === first || !panelRef.current?.contains(current))) {
        event.preventDefault()
        last.focus()
      } else if (!event.shiftKey && current === last) {
        event.preventDefault()
        first.focus()
      }
    }

    document.addEventListener('keydown', onKeyDown, true)
    return () => {
      window.clearTimeout(focusTimer)
      document.removeEventListener('keydown', onKeyDown, true)
      const index = dialogStack.lastIndexOf(token)
      if (index >= 0) dialogStack.splice(index, 1)
      unlockBodyScroll()
      window.requestAnimationFrame(() => previousActive?.focus?.({ preventScroll: true }))
    }
  }, [busy, initialFocusRef, mounted, onClose, open, token])

  if (!open || !mounted) return null

  const dialog = <div
    className={`accessible-dialog-backdrop placement-${placement}`}
    data-dialog-backdrop
    onMouseDown={(event) => {
      if (!closeOnBackdrop || busy || event.target !== event.currentTarget) return
      onClose()
    }}
  >
    <div
      ref={panelRef}
      className={`accessible-dialog-surface size-${size} placement-${placement} ${className}`.trim()}
      role="dialog"
      aria-modal="true"
      aria-labelledby={titleId}
      aria-describedby={description ? descriptionId : undefined}
      tabIndex={-1}
    >
      <header className="accessible-dialog-header">
        <div className="accessible-dialog-heading">
          <h2 id={titleId}>{title}</h2>
          {description ? <div id={descriptionId} className="accessible-dialog-description">{description}</div> : null}
        </div>
        <button ref={closeRef} type="button" className="accessible-dialog-close" aria-label={`${closeLabel}: ${title}`} disabled={busy} onClick={onClose}>
          <AppIcon name="close" size={18} />
        </button>
      </header>
      <div className={`accessible-dialog-body ${bodyClassName}`.trim()}>{children}</div>
      {footer ? <footer className="accessible-dialog-footer">{footer}</footer> : null}
    </div>
  </div>

  return createPortal(dialog, document.body)
}
