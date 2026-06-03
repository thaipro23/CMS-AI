'use client'

import { ButtonHTMLAttributes, ReactNode } from 'react'

type Props = ButtonHTMLAttributes<HTMLButtonElement> & {
  loading?: boolean
  loadingLabel?: string
  children: ReactNode
}

export function LoadingButton({ loading = false, loadingLabel = 'Đang xử lý...', children, disabled, className = 'btn', ...props }: Props) {
  return <button {...props} className={className} disabled={disabled || loading}>
    {loading && <span className="spinner" aria-hidden="true" />}
    {loading ? loadingLabel : children}
  </button>
}
