'use client'

import type { ReactNode } from 'react'

export function TableLoadingState({ label = 'Đang tải dữ liệu...' }: { label?: string }) {
  return <div className="enterprise-table-state loading" role="status" aria-live="polite"><span className="spinner" aria-hidden="true" /><div><b>{label}</b><small>Vui lòng chờ, dữ liệu hiện có sẽ không bị thay đổi.</small></div></div>
}

export function TableEmptyState({ title = 'Chưa có dữ liệu', description, action }: { title?: string; description?: string; action?: ReactNode }) {
  return <div className="enterprise-table-state empty"><div><b>{title}</b>{description && <small>{description}</small>}</div>{action && <div>{action}</div>}</div>
}

export function TableErrorState({ title = 'Không thể tải dữ liệu', message, code, onRetry }: { title?: string; message?: string; code?: string; onRetry?: () => void }) {
  return <div className="enterprise-table-state error" role="alert"><div><b>{title}</b>{message && <small>{message}</small>}{code && <code>{code}</code>}</div>{onRetry && <button className="btn small secondary" type="button" onClick={onRetry}>Thử lại</button>}</div>
}
