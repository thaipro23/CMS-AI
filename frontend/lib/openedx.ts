const COURSE_KEY_PATTERN = /course-v1:([^+/\s?#]+)\+([^+/\s?#]+)\+([^+/\s?#]+)/i

export function normalizeOpenEdxCourseId(value: string | null | undefined): string {
  let raw = String(value || '').trim()
  if (!raw) return ''
  try { raw = decodeURIComponent(raw) } catch { /* keep operator input */ }
  const match = raw.match(COURSE_KEY_PATTERN)
  if (!match) return ''
  return `course-v1:${match[1]}+${match[2]}+${match[3]}`
}

export function isOpenEdxCourseId(value: string | null | undefined): boolean {
  return Boolean(normalizeOpenEdxCourseId(value))
}
