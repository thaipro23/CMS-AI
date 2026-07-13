const LABELS: Record<string, string> = {
  pending_review: 'Chờ duyệt', needs_review: 'Cần review', approved: 'Đã duyệt', rejected: 'Từ chối', published: 'Đã publish', draft_error: 'Cần sửa',
  completed: 'Hoàn tất', partial_completed: 'Hoàn tất một phần', model_parse_failed: 'Lỗi đọc kết quả AI', partial_failed: 'Lỗi một phần', failed: 'Thất bại',
  queued: 'Đang chờ', running: 'Đang chạy', success: 'Thành công', canceled: 'Đã hủy', warning: 'Cảnh báo', info: 'Thông tin', neutral: 'Chưa xác định',
}

function tone(status: string) {
  if (['approved', 'published', 'completed', 'success'].includes(status)) return 'success'
  if (['rejected', 'draft_error', 'failed', 'model_parse_failed', 'partial_failed'].includes(status)) return 'danger'
  if (['partial_completed', 'queued', 'running', 'pending_review', 'needs_review', 'warning'].includes(status)) return 'warning'
  return 'neutral'
}

const ICONS: Record<string, string> = { success: '✓', danger: '!', warning: '•', neutral: '–' }

export function StatusBadge({ status }: { status: string }) {
  const normalized = String(status || 'neutral').toLowerCase()
  const semanticTone = tone(normalized)
  return <span className={`status ${semanticTone}`} data-status={normalized}>
    <span className="status-icon" aria-hidden="true">{ICONS[semanticTone]}</span>
    <span>{LABELS[normalized] || status || 'Chưa xác định'}</span>
  </span>
}
