export const VIETNAM_TIME_ZONE = 'Asia/Ho_Chi_Minh'

function isDateOnlyISO(value: string) {
  return /^\d{4}-\d{2}-\d{2}$/.test(value.trim())
}

function parseISODateOnly(value: string) {
  const match = value.trim().match(/^(\d{4})-(\d{2})-(\d{2})$/)
  if (!match) return null
  return { yyyy: Number(match[1]), mm: Number(match[2]), dd: Number(match[3]) }
}

function parseVNDateParts(value: string) {
  const match = value.trim().match(/^(\d{1,2})[\/\-.](\d{1,2})[\/\-.](\d{4})$/)
  if (!match) return null
  const dd = Number(match[1])
  const mm = Number(match[2])
  const yyyy = Number(match[3])
  if (!Number.isInteger(dd) || !Number.isInteger(mm) || !Number.isInteger(yyyy)) return null
  if (yyyy < 1900 || yyyy > 2200 || mm < 1 || mm > 12 || dd < 1 || dd > 31) return null
  const daysInMonth = new Date(Date.UTC(yyyy, mm, 0)).getUTCDate()
  if (dd > daysInMonth) return null
  return { yyyy, mm, dd }
}

export function normalizeVNDateInput(value?: string | null): string {
  const raw = String(value || '').trim()
  if (!raw) return ''
  const vn = parseVNDateParts(raw)
  if (vn) return `${String(vn.dd).padStart(2, '0')}/${String(vn.mm).padStart(2, '0')}/${vn.yyyy}`
  const isoDate = parseISODateOnly(raw)
  if (isoDate) return `${String(isoDate.dd).padStart(2, '0')}/${String(isoDate.mm).padStart(2, '0')}/${isoDate.yyyy}`
  return formatVNDate(raw)
}

export function vnDateInputToISODate(value?: string | null): string {
  const raw = String(value || '').trim()
  if (!raw) return ''
  const vn = parseVNDateParts(raw)
  if (vn) return `${vn.yyyy}-${String(vn.mm).padStart(2, '0')}-${String(vn.dd).padStart(2, '0')}`
  const iso = parseISODateOnly(raw)
  if (iso) return raw
  const formatted = formatVNDate(raw)
  const fallback = parseVNDateParts(formatted)
  return fallback ? `${fallback.yyyy}-${String(fallback.mm).padStart(2, '0')}-${String(fallback.dd).padStart(2, '0')}` : ''
}

export function vnDateInputToISODateTime(value?: string | null): string | null {
  const isoDate = vnDateInputToISODate(value)
  return isoDate ? `${isoDate}T00:00:00+07:00` : null
}

export function addDaysToVNDateInput(value: string, days: number): string {
  const isoDate = vnDateInputToISODate(value)
  if (!isoDate) return ''
  const [yyyy, mm, dd] = isoDate.split('-').map(Number)
  const date = new Date(Date.UTC(yyyy, mm - 1, dd))
  date.setUTCDate(date.getUTCDate() + days)
  return `${String(date.getUTCDate()).padStart(2, '0')}/${String(date.getUTCMonth() + 1).padStart(2, '0')}/${date.getUTCFullYear()}`
}

export function todayVNISODate(): string {
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: VIETNAM_TIME_ZONE,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).formatToParts(new Date())
  const get = (type: string) => parts.find((part) => part.type === type)?.value || ''
  return `${get('year')}-${get('month')}-${get('day')}`
}

export function daysAgoVNISODate(days: number): string {
  const today = todayVNISODate()
  const [yyyy, mm, dd] = today.split('-').map(Number)
  const date = new Date(Date.UTC(yyyy, mm - 1, dd))
  date.setUTCDate(date.getUTCDate() - Math.max(0, days))
  return `${date.getUTCFullYear()}-${String(date.getUTCMonth() + 1).padStart(2, '0')}-${String(date.getUTCDate()).padStart(2, '0')}`
}

export function formatVNDateTime(value?: string | number | Date | null): string {
  if (!value) return '—'
  try {
    const raw = typeof value === 'string' ? value.trim() : value
    if (typeof raw === 'string' && isDateOnlyISO(raw)) return normalizeVNDateInput(raw)
    return new Date(raw).toLocaleString('vi-VN', {
      timeZone: VIETNAM_TIME_ZONE,
      hour12: false,
      year: 'numeric',
      day: '2-digit',
      month: '2-digit',
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
    const raw = typeof value === 'string' ? value.trim() : value
    if (typeof raw === 'string') {
      const normalized = parseVNDateParts(raw)
      if (normalized) return `${String(normalized.dd).padStart(2, '0')}/${String(normalized.mm).padStart(2, '0')}/${normalized.yyyy}`
      const isoDate = parseISODateOnly(raw)
      if (isoDate) return `${String(isoDate.dd).padStart(2, '0')}/${String(isoDate.mm).padStart(2, '0')}/${isoDate.yyyy}`
    }
    return new Date(raw).toLocaleDateString('vi-VN', { timeZone: VIETNAM_TIME_ZONE, day: '2-digit', month: '2-digit', year: 'numeric' })
  } catch {
    return String(value || '—')
  }
}
