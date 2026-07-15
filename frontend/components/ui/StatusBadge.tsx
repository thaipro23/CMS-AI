import type { ReactNode } from 'react'
import { AppIcon, type AppIconName } from '../icons/AppIcon'

const LABELS: Record<string, string> = {
  pending_review: 'Chờ duyệt', needs_review: 'Cần review', approved: 'Đã duyệt', rejected: 'Từ chối', published: 'Đã publish', draft_error: 'Cần sửa',
  completed: 'Hoàn tất', partial_completed: 'Hoàn tất một phần', model_parse_failed: 'Lỗi đọc kết quả AI', partial_failed: 'Lỗi một phần', failed: 'Thất bại',
  queued: 'Đang chờ', running: 'Đang chạy', success: 'Thành công', canceled: 'Đã hủy', warning: 'Cảnh báo', info: 'Thông tin', neutral: 'Chưa xác định',
  active: 'Đang hiệu lực', inactive: 'Không hoạt động', revoked: 'Đã thu hồi',
  ready: 'Sẵn sàng chốt', needs_fix: 'Cần sửa câu hỏi', not_ready: 'Cần hoàn thiện', empty: 'Chưa có dữ liệu',
  created: 'Đã tạo', rolled_back: 'Đã khôi phục', draft: 'Bản nháp',
}

function tone(status: string) {
  if (['approved', 'published', 'completed', 'success', 'active', 'ready', 'created'].includes(status)) return 'success'
  if (['rejected', 'draft_error', 'failed', 'model_parse_failed', 'partial_failed', 'revoked', 'needs_fix'].includes(status)) return 'danger'
  if (['partial_completed', 'queued', 'running', 'pending_review', 'needs_review', 'warning', 'not_ready', 'draft'].includes(status)) return 'warning'
  return 'neutral'
}

const ICONS: Record<string, AppIconName> = { success: 'check', danger: 'alert', warning: 'clock', neutral: 'info' }

export function StatusBadge({ status, label }: { status: string; label?: ReactNode }) {
  const normalized = String(status || 'neutral').toLowerCase()
  const semanticTone = tone(normalized)
  return <span className={`status ${semanticTone}`} data-status={normalized}>
    <span className="status-icon" aria-hidden="true"><AppIcon name={ICONS[semanticTone]} size={13} /></span>
    <span>{label ?? LABELS[normalized] ?? status ?? 'Chưa xác định'}</span>
  </span>
}
