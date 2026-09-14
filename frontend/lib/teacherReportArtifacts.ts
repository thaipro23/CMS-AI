import { API, ApiRequestError, apiFetch } from './api'

export type LatestTeacherReportArtifact = {
  available: boolean
  job_id?: string
  term_id: string
  branch: string
  campus?: string | null
  scope: string
  file_name?: string | null
  generated_at?: string | null
  source_synced_at?: string | null
  timezone: 'Asia/Ho_Chi_Minh' | string
  is_current_day: boolean
  warning?: string | null
  today_run?: {
    id?: string
    status?: string
    progress_current?: number
    progress_total?: number
    progress_label?: string
    failed_class_count?: number
    updated_at?: string
  } | null
}

function queryString(params: { termId: string; branch: string; campus?: string | null }) {
  const query = new URLSearchParams()
  query.set('term_id', params.termId)
  query.set('branch', params.branch || 'poly')
  if (params.campus) query.set('campus', params.campus)
  return query.toString()
}

async function errorMessage(response: Response, fallback: string) {
  try {
    const body = await response.json()
    const detail = body?.detail
    if (typeof detail === 'string' && detail.trim()) return detail
    if (typeof detail?.message === 'string' && detail.message.trim()) return detail.message
    if (typeof body?.message === 'string' && body.message.trim()) return body.message
  } catch {
    // Ignore malformed error payload and use the safe fallback.
  }
  return fallback
}

export async function getLatestTeacherReportArtifact(
  headers: HeadersInit,
  params: { termId: string; branch: string; campus?: string | null },
  signal?: AbortSignal,
): Promise<LatestTeacherReportArtifact> {
  const response = await apiFetch(
    `${API}/academic/training/teacher-reports/latest?${queryString(params)}`,
    {
      headers,
      method: 'GET',
      cache: 'no-store',
      timeoutMs: 20_000,
      retries: 1,
      signal,
    },
  )
  if (!response.ok) {
    throw new ApiRequestError(
      await errorMessage(response, 'Không đọc được thông tin file báo cáo 05:00.'),
      { code: 'TEACHER_REPORT_ARTIFACT_LOOKUP_FAILED', status: response.status },
    )
  }
  return await response.json() as LatestTeacherReportArtifact
}

export async function downloadLatestTeacherReportArtifact(
  headers: HeadersInit,
  params: { termId: string; branch: string; campus?: string | null },
): Promise<{ blob: Blob; filename: string }> {
  const response = await apiFetch(
    `${API}/academic/training/teacher-reports/latest/download?${queryString(params)}`,
    {
      headers,
      method: 'GET',
      timeoutMs: 60_000,
      retries: 1,
    },
  )
  if (!response.ok) {
    throw new ApiRequestError(
      await errorMessage(response, 'Không tải được file báo cáo 05:00.'),
      { code: 'TEACHER_REPORT_ARTIFACT_DOWNLOAD_FAILED', status: response.status },
    )
  }
  const disposition = response.headers.get('Content-Disposition') || ''
  const utf8 = disposition.match(/filename\*=UTF-8''([^;]+)/i)?.[1]
  let filename = 'teacher-report.xlsx'
  if (utf8) {
    try { filename = decodeURIComponent(utf8) } catch { filename = 'teacher-report.xlsx' }
  }
  return { blob: await response.blob(), filename }
}
