import { API } from './api';

export type LatestAcademicScoreRefreshPayload = {
  termId: string;
  branch: string;
  campus?: string;
  search?: string;
  learningStatus?: string;
  force?: boolean;
  limit?: number;
  maxClasses?: number;
  mode?: string;
};

export type LatestAcademicScoreRefreshResult = {
  ok: boolean;
  job_id: string;
  status: string;
  class_total: number;
  scope_class_total?: number;
  skipped_unmapped_count?: number;
  reused?: boolean;
  message?: string;
};

function errorMessage(payload: unknown, fallback: string): string {
  if (payload && typeof payload === 'object') {
    const detail = (payload as { detail?: unknown }).detail;
    if (typeof detail === 'string' && detail.trim()) return detail;
    if (detail && typeof detail === 'object') {
      const message = (detail as { message?: unknown }).message;
      if (typeof message === 'string' && message.trim()) return message;
    }
    const message = (payload as { message?: unknown }).message;
    if (typeof message === 'string' && message.trim()) return message;
  }
  return fallback;
}

export async function refreshLatestAcademicScores(
  headers: HeadersInit,
  payload: LatestAcademicScoreRefreshPayload,
): Promise<LatestAcademicScoreRefreshResult> {
  const response = await fetch(`${API}/academic/subjects/learning/refresh/jobs`, {
    method: 'POST',
    headers,
    body: JSON.stringify({
      term_id: payload.termId,
      branch: payload.branch,
      campus: payload.campus || null,
      search: payload.search || null,
      learning_status: payload.learningStatus || null,
      force: payload.force !== false,
      limit: payload.limit || 500,
      max_classes: payload.maxClasses || 3000,
      mode: payload.mode || null,
    }),
  });

  let data: unknown = null;
  try {
    data = await response.json();
  } catch {
    data = null;
  }
  if (!response.ok) {
    throw new Error(errorMessage(data, `Không tạo được tác vụ lấy điểm mới nhất (HTTP ${response.status}).`));
  }
  return data as LatestAcademicScoreRefreshResult;
}
