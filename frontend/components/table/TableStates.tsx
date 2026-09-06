'use client'

import type { ReactNode } from 'react'
import { VisualIcon } from '../ui/VisualIcon'
import { userFacingError } from '../../lib/userFacingError'

export function TableLoadingState({ label = 'Đang tải dữ liệu...' }: { label?: string }) {
  return <div className="enterprise-table-state loading visual-state" role="status" aria-live="polite"><VisualIcon label="Đang tải dữ liệu" icon="database" tone="blue" /><span className="spinner" aria-hidden="true" /><div><b>{label}</b></div></div>
}

export function TableEmptyState({ title = 'Chưa có dữ liệu', description, action }: { title?: string; description?: string; action?: ReactNode }) {
  return <div className="enterprise-table-state empty visual-state" role="status"><VisualIcon label={title} icon="database" tone="slate" /><div><b>{title}</b>{description && <small>{description}</small>}</div>{action && <div>{action}</div>}</div>
}

export function TableErrorState({ title = 'Không thể tải dữ liệu', message, onRetry }: { title?: string; message?: string; code?: string; onRetry?: () => void }) {
  return <div className="enterprise-table-state error visual-state" role="alert"><VisualIcon label="Có lỗi" icon="alert" tone="red" /><div><b>{title}</b>{message && <small>{userFacingError(message)}</small>}</div>{onRetry && <button className="btn small secondary" type="button" onClick={onRetry}>Thử lại</button>}</div>
}
