const LABELS: Record<string, string> = {
  pending_review: 'Chờ duyệt', needs_review: 'Cần review', approved: 'Đã duyệt', rejected: 'Từ chối', published: 'Đã publish', draft_error: 'Cần sửa', completed: 'Hoàn tất', partial_completed: 'Hoàn tất một phần', model_parse_failed: 'Lỗi đọc kết quả AI', partial_failed: 'Lỗi một phần', failed: 'Thất bại', queued: 'Đang chờ', running: 'Đang chạy', success: 'Thành công'
}
function statusClass(status: string) {
  if (['approved', 'published', 'completed', 'success'].includes(status)) return 'status success'
  if (['rejected', 'draft_error', 'failed', 'model_parse_failed', 'partial_failed'].includes(status)) return 'status danger'
  if (['partial_completed', 'queued', 'running', 'needs_review'].includes(status)) return 'status warning'
  return 'status'
}
export function StatusBadge({ status }: { status: string }) { return <span className={statusClass(status)}>{LABELS[status] || status}</span> }
