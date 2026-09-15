export function maskEmailForDisplay(value?: string | null): string {
  const email = String(value || '').trim().toLowerCase()
  if (!email) return ''
  const at = email.lastIndexOf('@')
  if (at <= 0 || at === email.length - 1) return '***'
  const local = email.slice(0, at)
  const domain = email.slice(at + 1)
  if (local.includes('***')) return `${local}@${domain}`
  const maskedLocal = local.length <= 1
    ? `${local.slice(0, 1)}***`
    : `${local.slice(0, 1)}***${local.slice(-1)}`
  return `${maskedLocal}@${domain}`
}
