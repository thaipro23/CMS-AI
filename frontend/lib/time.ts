export const VIETNAM_TIME_ZONE = 'Asia/Ho_Chi_Minh'

export function formatVNDateTime(value?: string | number | Date | null): string {
  if (!value) return '—'
  try {
    return new Date(value).toLocaleString('vi-VN', {
      timeZone: VIETNAM_TIME_ZONE,
      hour12: false,
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    })
  } catch {
    return String(value || '—')
  }
}

export function formatVNDate(value?: string | number | Date | null): string {
  if (!value) return '—'
  try {
    return new Date(value).toLocaleDateString('vi-VN', { timeZone: VIETNAM_TIME_ZONE })
  } catch {
    return String(value || '—')
  }
}
