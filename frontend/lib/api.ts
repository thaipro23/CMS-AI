import {
  CourseChunk,
  Job,
  Question,
  QuestionFilters,
  QuestionStats,
  AnalyticsOverview,
  EditQuestionForm,
  CourseTreeNode,
  CourseNodeOption,
  CourseOption,
  RuntimeSettings,
  RuntimeSettingsUpdate,
  PricingResponse,
  PaginatedResponse,
  CursorPaginatedResponse,
  CoursePolicy,
  CoursePolicyUpdate,
  AuditLogRow,
  CourseCleanResyncResponse,
  PublishResult,
  PublishBatchSummary,
  SourceTrace,
  Concept,
  ConceptExtractResponse,
  ConceptListResponse,
  BankSummary,
  Department,
  Subject,
  SubjectOffering,
  SubjectChapter,
  BankVersion,
  BankRelease,
  BankReleasePublishResult,
  EdxCourseMapping,
  MappingValidation,
  EdxCourseChapterMapping,
  QuizBlueprint,
  MaterialChunk,
  MaterialVersion,
  MaterialUploadResult,
  BankGeneratePreview,
  BankGenerateResult,
  BankVersionQuestion,
  BankQuestionListItem,
  BankVersionDiffPreview,
  BankCarryOverResult,
  BankRetireResult,
  BankReleaseQuizPlan,
  BankReleaseQuizCreateResult,
  BankReleaseReadiness,
  BankQuestionReviewResult,
  BankQuestionBulkReviewResult,
  BankDocumentDiffResolveResult,
  CourseQuizInstance,
  CourseQuizRollbackResult,
  QuizAutoMapResult,
  BankDashboardOverview,
  DashboardAnalytics,
  BankSearchResult,
  BankSearchGroupedResponse,
  BankDashboardDrilldownResponse,
  DepartmentSummary,
  SubjectSummary,
  SubjectVersionSummary,
  ChapterSummary,
  RBACRole,
  RBACPermission,
  RoleAssignment,
  RoleAssignmentCreate,
  RoleAssignmentImportResponse,
  RoleAssignmentListResponse,
  EffectiveRBAC,
  BankOperationJob,
  BankOperationJobQueued,
} from "../types";

const rawApiBase =
  process.env.NEXT_PUBLIC_API_BASE_URL ||
  process.env.NEXT_PUBLIC_API_URL ||
  "http://localhost:8000";
const normalizedApiBase = rawApiBase.replace(/\/+$/, "");
export const API = normalizedApiBase.endsWith("/api")
  ? normalizedApiBase
  : `${normalizedApiBase}/api`;


function withIdempotency(headers: HeadersInit, idempotencyKey?: string): HeadersInit {
  if (!idempotencyKey) return headers;
  const next = new Headers(headers);
  next.set("Idempotency-Key", idempotencyKey);
  return next;
}

function withoutContentType(headers: HeadersInit): HeadersInit {
  const next = new Headers(headers);
  next.delete('Content-Type');
  next.delete('content-type');
  return next;
}

async function parseResponse<T>(response: Response): Promise<T> {
  const text = await response.text();
  const data = text ? JSON.parse(text) : null;
  if (!response.ok) {
    const errorEnvelope = data?.error;
    const message = errorEnvelope?.message || data?.detail || data?.message || response.statusText;
    if (typeof message === "string") {
      const detail = errorEnvelope?.code ? ` [${errorEnvelope.code}]` : "";
      throw new Error(`${message}${detail}`);
    }
    if (Array.isArray(message))
      throw new Error(
        message
          .map((item) => item?.msg || item?.message || "Dữ liệu không hợp lệ")
          .join("; "),
      );
    throw new Error(
      "Backend trả về lỗi không hợp lệ. Mở Docker logs/backend để xem chi tiết kỹ thuật.",
    );
  }
  return data as T;
}



const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

export async function getBankOperationJob(headers: HeadersInit, jobId: string) {
  return parseResponse<BankOperationJob>(
    await fetch(`${API}/question-bank-v2/operation-jobs/${encodeURIComponent(jobId)}`, { headers }),
  );
}

export async function waitForBankOperationJob(headers: HeadersInit, jobId: string, options: { timeoutMs?: number; intervalMs?: number } = {}) {
  const timeoutMs = options.timeoutMs ?? 10 * 60 * 1000;
  const intervalMs = options.intervalMs ?? 1200;
  const start = Date.now();
  let last: BankOperationJob | null = null;
  while (Date.now() - start < timeoutMs) {
    last = await getBankOperationJob(headers, jobId);
    if (['completed', 'failed', 'canceled'].includes(last.status)) {
      if (last.status === 'completed') return last;
      throw new Error(last.error_message || last.progress_label || `Job ${last.status}`);
    }
    await sleep(intervalMs);
  }
  throw new Error(last?.progress_label ? `Job vẫn đang chạy: ${last.progress_label}` : 'Job quá thời gian chờ. Vào Tiến trình job để kiểm tra tiếp.');
}

async function enqueueAndWait<T>(headers: HeadersInit, queued: BankOperationJobQueued, timeoutMs?: number): Promise<T> {
  const job = await waitForBankOperationJob(headers, queued.job.id, { timeoutMs });
  return (job.result || {}) as T;
}


function unwrapPage<T>(data: T[] | PaginatedResponse<T>): T[] {
  if (Array.isArray(data)) return data;
  return data?.items || [];
}

function unwrapCursorPage<T>(data: T[] | CursorPaginatedResponse<T>): T[] {
  if (Array.isArray(data)) return data;
  return data?.items || [];
}

async function parsePageItems<T>(response: Response): Promise<T[]> {
  return unwrapPage<T>(await parseResponse<T[] | PaginatedResponse<T>>(response));
}

async function parseCursorPageItems<T>(response: Response): Promise<T[]> {
  return unwrapCursorPage<T>(await parseResponse<T[] | CursorPaginatedResponse<T>>(response));
}

export async function getAnalytics(
  courseId: string,
  headers: HeadersInit,
): Promise<AnalyticsOverview> {
  return parseResponse(
    await fetch(
      `${API}/analytics/overview?course_id=${encodeURIComponent(courseId)}`,
      { headers },
    ),
  );
}

export async function getQuestionStats(
  courseId: string,
  headers: HeadersInit,
): Promise<QuestionStats> {
  return parseResponse(
    await fetch(
      `${API}/question-bank/stats?course_id=${encodeURIComponent(courseId)}`,
      { headers },
    ),
  );
}

export async function getJobs(
  courseId: string,
  headers: HeadersInit,
): Promise<Job[]> {
  return parseResponse(
    await fetch(`${API}/jobs?course_id=${encodeURIComponent(courseId)}`, {
      headers,
    }),
  );
}

function buildQuestionParams(courseId: string, filters: QuestionFilters) {
  const params = new URLSearchParams();
  params.set("course_id", courseId);
  if (filters.status !== "all") params.set("status", filters.status);
  if (filters.difficulty !== "all")
    params.set("difficulty", filters.difficulty);
  if (filters.nodeId && filters.nodeId !== "all")
    params.set("node_id", filters.nodeId);
  if (filters.sourceType && filters.sourceType !== "all")
    params.set("source_type", filters.sourceType);
  if (filters.search.trim()) params.set("search", filters.search.trim());
  params.set("sort_by", filters.sortBy);
  params.set("sort_dir", filters.sortDir);
  return params;
}

export async function getQuestions(
  courseId: string,
  filters: QuestionFilters,
  headers: HeadersInit,
): Promise<Question[]> {
  return parseResponse(
    await fetch(
      `${API}/question-bank?${buildQuestionParams(courseId, filters).toString()}`,
      { headers },
    ),
  );
}

export async function getQuestionsPage(
  courseId: string,
  filters: QuestionFilters,
  headers: HeadersInit,
  page = 1,
  pageSize = 20,
): Promise<PaginatedResponse<Question>> {
  const params = buildQuestionParams(courseId, filters);
  params.set("page", String(page));
  params.set("page_size", String(pageSize));
  return parseResponse(
    await fetch(`${API}/question-bank/page?${params.toString()}`, { headers }),
  );
}

export async function getSyncedCourses(
  headers: HeadersInit,
  search = "",
  limit = 1000,
): Promise<CourseOption[]> {
  const params = new URLSearchParams();
  if (search.trim()) params.set("search", search.trim());
  params.set("limit", String(limit));
  return parseResponse(
    await fetch(`${API}/courses?${params.toString()}`, { headers }),
  );
}


export async function getCourseConcepts(
  courseId: string,
  headers: HeadersInit,
  nodeId?: string,
): Promise<ConceptListResponse> {
  const params = new URLSearchParams();
  if (nodeId && nodeId !== "all") params.set("node_id", nodeId);
  return parseResponse(
    await fetch(`${API}/courses/${encodeURIComponent(courseId)}/concepts?${params.toString()}`, { headers }),
  );
}

export async function extractCourseConcepts(
  courseId: string,
  headers: HeadersInit,
  nodeId?: string,
  force = false,
  maxConcepts = 20,
): Promise<ConceptExtractResponse> {
  return parseResponse(
    await fetch(`${API}/courses/${encodeURIComponent(courseId)}/concepts/extract`, {
      method: "POST",
      headers,
      body: JSON.stringify({ node_id: nodeId && nodeId !== "all" ? nodeId : null, force, max_concepts: maxConcepts }),
    }),
  );
}

export async function syncCourse(courseId: string, headers: HeadersInit) {
  return parseResponse(
    await fetch(`${API}/courses/sync`, {
      method: "POST",
      headers,
      body: JSON.stringify({ course_id: courseId, force: false }),
    }),
  );
}

export async function cleanResyncCourse(
  courseId: string,
  headers: HeadersInit,
  confirm = "RESET_COURSE_SYNC",
): Promise<CourseCleanResyncResponse> {
  const params = new URLSearchParams();
  params.set("confirm", confirm);
  return parseResponse(
    await fetch(
      `${API}/courses/${encodeURIComponent(courseId)}/clean-resync?${params.toString()}`,
      {
        method: "POST",
        headers,
      },
    ),
  );
}

export async function uploadFileToNode(
  courseId: string,
  nodeId: string,
  file: File,
  headers: HeadersInit,
  replaceExisting = true,
) {
  const form = new FormData();
  form.append("file", file);
  form.append("replace_existing", String(replaceExisting));
  return parseResponse(
    await fetch(
      `${API}/courses/${encodeURIComponent(courseId)}/nodes/${encodeURIComponent(nodeId)}/files`,
      {
        method: "POST",
        headers,
        body: form,
      },
    ),
  );
}

export async function deleteCourseNode(
  courseId: string,
  nodeId: string,
  headers: HeadersInit,
  confirm = "DELETE_NODE",
) {
  const params = new URLSearchParams();
  params.set("confirm", confirm);
  return parseResponse(
    await fetch(
      `${API}/courses/${encodeURIComponent(courseId)}/nodes/${encodeURIComponent(nodeId)}?${params.toString()}`,
      {
        method: "DELETE",
        headers,
      },
    ),
  );
}

export async function getCourseTree(
  courseId: string,
  headers: HeadersInit,
): Promise<CourseTreeNode[]> {
  return parseResponse(
    await fetch(`${API}/courses/${encodeURIComponent(courseId)}/tree`, {
      headers,
    }),
  );
}

export async function getCourseNodes(
  courseId: string,
  headers: HeadersInit,
): Promise<CourseNodeOption[]> {
  return parseResponse(
    await fetch(`${API}/courses/${encodeURIComponent(courseId)}/nodes`, {
      headers,
    }),
  );
}

function buildChunkParams(sourceType: string, search: string, nodeId = "all") {
  const params = new URLSearchParams();
  if (sourceType !== "all") params.set("source_type", sourceType);
  if (search.trim()) params.set("search", search.trim());
  if (nodeId !== "all") params.set("node_id", nodeId);
  return params;
}

export async function getChunks(
  courseId: string,
  sourceType: string,
  search: string,
  headers: HeadersInit,
  nodeId = "all",
): Promise<CourseChunk[]> {
  const params = buildChunkParams(sourceType, search, nodeId);
  params.set("limit", "200");
  return parseResponse(
    await fetch(
      `${API}/courses/${encodeURIComponent(courseId)}/chunks?${params.toString()}`,
      { headers },
    ),
  );
}

export async function getChunksPage(
  courseId: string,
  sourceType: string,
  search: string,
  headers: HeadersInit,
  nodeId = "all",
  page = 1,
  pageSize = 20,
): Promise<PaginatedResponse<CourseChunk>> {
  const params = buildChunkParams(sourceType, search, nodeId);
  params.set("page", String(page));
  params.set("page_size", String(pageSize));
  return parseResponse(
    await fetch(
      `${API}/courses/${encodeURIComponent(courseId)}/chunks/page?${params.toString()}`,
      { headers },
    ),
  );
}

export async function estimateCost(
  payload: {
    course_id: string;
    question_count: number;
    content_tokens?: number;
    content?: string;
    chunk_ids?: string[];
    node_ids?: string[];
    batch_size?: number;
    use_node_coverage?: boolean;
    refresh_pricing?: boolean;
    difficulty_percentages?: { easy: number; medium: number; hard: number };
  },
  headers: HeadersInit,
  idempotencyKey?: string,
) {
  return parseResponse(
    await fetch(`${API}/cost/estimate`, {
      method: "POST",
      headers: withIdempotency(headers, idempotencyKey),
      body: JSON.stringify(payload),
    }),
  );
}

export async function generateQuestions(
  payload: {
    course_id: string;
    question_count: number;
    batch_size: number;
    content?: string;
    chunk_ids?: string[];
    node_ids?: string[];
    use_node_coverage?: boolean;
    difficulty_percentages?: { easy: number; medium: number; hard: number };
  },
  headers: HeadersInit,
  idempotencyKey?: string,
) {
  return parseResponse(
    await fetch(`${API}/questions/generate`, {
      method: "POST",
      headers: withIdempotency(headers, idempotencyKey),
      body: JSON.stringify(payload),
    }),
  );
}

export async function updateQuestion(
  id: string,
  form: EditQuestionForm,
  headers: HeadersInit,
): Promise<Question> {
  const body = {
    ...form,
    topic: form.node_title || form.topic,
    note: "Teacher edited question",
    source_page: form.source_page ? Number(form.source_page) : null,
    variant_no: form.variant_no ? Number(form.variant_no) : null,
    tags: form.tags_text
      .split(",")
      .map((tag) => tag.trim())
      .filter(Boolean),
  };
  return parseResponse(
    await fetch(`${API}/question-bank/${id}`, {
      method: "PATCH",
      headers,
      body: JSON.stringify(body),
    }),
  );
}

export async function transitionQuestion(
  id: string,
  action: "approve" | "reject" | "publish" | string,
  headers: HeadersInit,
): Promise<Question> {
  return parseResponse(
    await fetch(`${API}/question-bank/${id}/${action}`, {
      method: "POST",
      headers,
      body: JSON.stringify({ note: `Manual transition ${action}` }),
    }),
  );
}

export async function changeQuestionStatus(
  id: string,
  status: string,
  note: string,
  headers: HeadersInit,
): Promise<Question> {
  return parseResponse(
    await fetch(`${API}/question-bank/${id}/status`, {
      method: "POST",
      headers,
      body: JSON.stringify({ target_status: status, note }),
    }),
  );
}

export async function deleteQuestion(
  id: string,
  headers: HeadersInit,
): Promise<{ deleted: boolean; question_id: string }> {
  return parseResponse(
    await fetch(`${API}/question-bank/${id}`, {
      method: "DELETE",
      headers,
    }),
  );
}

export async function repairDraftError(
  id: string,
  headers: HeadersInit,
): Promise<Question> {
  return parseResponse(
    await fetch(`${API}/question-bank/${id}/repair`, {
      method: "POST",
      headers,
      body: JSON.stringify({ note: "Repair draft_error from UI" }),
    }),
  );
}

export async function keepDraftErrorAnyway(
  id: string,
  headers: HeadersInit,
): Promise<Question> {
  return parseResponse(
    await fetch(`${API}/question-bank/${id}/keep-anyway`, {
      method: "POST",
      headers,
      body: JSON.stringify({ note: "Teacher reviewed and kept anyway" }),
    }),
  );
}

export async function getQuestionDiversityReport(
  courseId: string,
  headers: HeadersInit,
) {
  return parseResponse(
    await fetch(
      `${API}/question-bank/diversity/report?course_id=${encodeURIComponent(courseId)}`,
      { headers },
    ),
  );
}

export async function dryRunQuestionPublish(
  questionId: string,
  headers: HeadersInit,
) {
  return parseResponse(
    await fetch(
      `${API}/publish/questions/${encodeURIComponent(questionId)}/openedx/dry-run`,
      {
        method: "POST",
        headers,
      },
    ),
  );
}

export async function testOpenEdxConnection(
  courseId: string | null,
  headers: HeadersInit,
) {
  const suffix = courseId ? `?course_id=${encodeURIComponent(courseId)}` : "";
  return parseResponse(
    await fetch(`${API}/settings/openedx/test${suffix}`, {
      method: "POST",
      headers,
    }),
  );
}

export async function bulkApprove(
  payload: {
    note?: string;
    question_ids?: string[];
    course_id?: string;
    approve_all_pending?: boolean;
  },
  headers: HeadersInit,
) {
  return parseResponse(
    await fetch(`${API}/question-bank/bulk/approve`, {
      method: "POST",
      headers,
      body: JSON.stringify(payload),
    }),
  );
}

export async function getQuestionOlx(id: string, headers: HeadersInit) {
  return parseResponse<{ question_id: string; olx: string }>(
    await fetch(`${API}/question-bank/${id}/openedx-olx`, { headers }),
  );
}

export async function exportApprovedOlx(
  courseId: string,
  headers: HeadersInit,
  status = "approved",
) {
  const data = await parseResponse<{
    course_id?: string;
    status?: string;
    question_count: number;
    olx?: string;
    olx_xml?: string;
  }>(
    await fetch(
      `${API}/question-bank/export/openedx-olx?course_id=${encodeURIComponent(courseId)}&status=${status}`,
      { headers },
    ),
  );
  const olx = data.olx || data.olx_xml || "";
  return { ...data, olx };
}

export async function downloadApprovedOlx(
  courseId: string,
  headers: HeadersInit,
  status = "approved",
) {
  const response = await fetch(
    `${API}/question-bank/export/openedx-olx.xml?course_id=${encodeURIComponent(courseId)}&status=${status}`,
    { headers },
  );
  if (!response.ok) throw new Error(response.statusText);
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `${courseId.replace(/[^a-zA-Z0-9_-]/g, "_")}_approved_questions.xml`;
  a.click();
  URL.revokeObjectURL(url);
}

export async function publishApprovedToOpenEdx(
  courseId: string,
  headers: HeadersInit,
  mode: "publish_new" | "replace" | "delete_reimport" = "publish_new",
  idempotencyKey?: string,
): Promise<PublishResult> {
  const params = new URLSearchParams();
  params.set("mode", mode);
  return parseResponse(
    await fetch(
      `${API}/publish/courses/${encodeURIComponent(courseId)}/openedx?${params.toString()}`,
      {
        method: "POST",
        headers: withIdempotency(headers, idempotencyKey),
      },
    ),
  );
}

export async function publishQuestionToOpenEdx(
  questionId: string,
  headers: HeadersInit,
  mode: "publish_new" | "replace" | "delete_reimport" = "publish_new",
  idempotencyKey?: string,
): Promise<Question> {
  const params = new URLSearchParams();
  params.set("mode", mode);
  return parseResponse(
    await fetch(
      `${API}/publish/questions/${encodeURIComponent(questionId)}/openedx?${params.toString()}`,
      {
        method: "POST",
        headers: withIdempotency(headers, idempotencyKey),
      },
    ),
  );
}

export async function getPublishHistory(
  courseId: string,
  headers: HeadersInit,
): Promise<{ course_id: string; batches: PublishBatchSummary[] }> {
  return parseResponse(
    await fetch(`${API}/publish/courses/${encodeURIComponent(courseId)}/openedx/history`, { headers }),
  );
}

export async function rollbackPublishBatch(
  batchId: string,
  level: "ai_server" | "openedx",
  headers: HeadersInit,
  idempotencyKey?: string,
) {
  const params = new URLSearchParams();
  params.set("level", level);
  return parseResponse(
    await fetch(`${API}/publish/batches/${encodeURIComponent(batchId)}/rollback?${params.toString()}`, {
      method: "POST",
      headers: withIdempotency(headers, idempotencyKey),
    }),
  );
}

export async function getQuestionSourceTrace(
  questionId: string,
  headers: HeadersInit,
): Promise<SourceTrace> {
  return parseResponse(
    await fetch(`${API}/question-bank/${encodeURIComponent(questionId)}/source-trace`, { headers }),
  );
}

// New v20 names kept for newer code paths.
export const exportOlx = exportApprovedOlx;
export const publishApproved = publishApprovedToOpenEdx;
export const downloadOlxUrl = (courseId: string, status = "approved") =>
  `${API}/question-bank/export/openedx-olx.xml?course_id=${encodeURIComponent(courseId)}&status=${status}`;

export async function getUserAnalytics(
  courseId: string,
  query: { search?: string; sortBy?: string; sortDir?: string },
  headers: HeadersInit,
) {
  const params = new URLSearchParams();
  if (courseId) params.set("course_id", courseId);
  if (query.search?.trim()) params.set("search", query.search.trim());
  params.set("sort_by", query.sortBy || "cost_usd");
  params.set("sort_dir", query.sortDir || "desc");
  return parseResponse(
    await fetch(`${API}/users/analytics?${params.toString()}`, { headers }),
  );
}

export async function getRuntimeSettings(
  headers: HeadersInit,
): Promise<RuntimeSettings> {
  return parseResponse(await fetch(`${API}/settings/runtime`, { headers }));
}

export async function updateRuntimeSettings(
  payload: RuntimeSettingsUpdate,
  headers: HeadersInit,
): Promise<RuntimeSettings> {
  return parseResponse(
    await fetch(`${API}/settings/runtime`, {
      method: "PATCH",
      headers,
      body: JSON.stringify(payload),
    }),
  );
}

export async function getRealtimePricing(
  model: string,
  headers: HeadersInit,
  refresh = true,
): Promise<PricingResponse> {
  const params = new URLSearchParams();
  if (model.trim()) params.set("model", model.trim());
  params.set("refresh", refresh ? "true" : "false");
  return parseResponse(
    await fetch(`${API}/cost/pricing/realtime?${params.toString()}`, {
      headers,
    }),
  );
}

export async function testModelGateway(
  headers: HeadersInit,
): Promise<{
  ok: boolean;
  provider: string;
  model: string;
  api_mode?: string;
  input_tokens: number;
  cached_input_tokens?: number;
  output_tokens: number;
  question_count: number;
  first_question?: string | null;
}> {
  return parseResponse(
    await fetch(`${API}/settings/runtime/test-model`, {
      method: "POST",
      headers,
    }),
  );
}

export async function getCoursePolicy(
  courseId: string,
  headers: HeadersInit,
): Promise<CoursePolicy> {
  return parseResponse(
    await fetch(
      `${API}/cost/policy?course_id=${encodeURIComponent(courseId)}`,
      { headers },
    ),
  );
}

export async function updateCoursePolicy(
  payload: CoursePolicyUpdate,
  headers: HeadersInit,
): Promise<CoursePolicy> {
  return parseResponse(
    await fetch(`${API}/cost/policy`, {
      method: "PATCH",
      headers,
      body: JSON.stringify(payload),
    }),
  );
}

export async function getAuditLogs(
  courseId: string,
  query: {
    status?: string;
    errorType?: string;
    actorId?: string;
    page?: number;
    pageSize?: number;
  },
  headers: HeadersInit,
): Promise<PaginatedResponse<AuditLogRow>> {
  const params = new URLSearchParams();
  if (courseId) params.set("course_id", courseId);
  if (query.status && query.status !== "all")
    params.set("status", query.status);
  if (query.errorType && query.errorType !== "all")
    params.set("error_type", query.errorType);
  if (query.actorId?.trim()) params.set("actor_id", query.actorId.trim());
  params.set("page", String(query.page || 1));
  params.set("page_size", String(query.pageSize || 20));
  return parseResponse(
    await fetch(`${API}/audit?${params.toString()}`, { headers }),
  );
}

export type OpenEdxSessionExchangeResponse = {
  access_token: string;
  token_type: string;
  expires_in: number;
  user_id: string;
  email?: string | null;
  role: "admin" | "teacher" | "reviewer" | "viewer";
  course_ids: string[];
  username?: string | null;
  name?: string | null;
};

export async function exchangeOpenEdxSessionTicket(ticket: string): Promise<OpenEdxSessionExchangeResponse> {
  return parseResponse(
    await fetch(`${API}/auth/openedx-session/exchange`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify({ ticket }),
    }),
  );
}

export function buildCmsSessionBridgeUrl(courseId?: string) {
  const cmsBase = (process.env.NEXT_PUBLIC_OPENEDX_CMS_BASE_URL || process.env.NEXT_PUBLIC_CMS_BASE_URL || "").replace(/\/+$/, "");
  if (!cmsBase) throw new Error("NEXT_PUBLIC_OPENEDX_CMS_BASE_URL chưa được cấu hình cho frontend.");
  const returnTo = `${window.location.origin}/auth/cms-callback`;
  const params = new URLSearchParams();
  params.set("return_to", returnTo);
  if (courseId) params.set("course_id", courseId);
  params.set("state", Math.random().toString(36).slice(2));
  return `${cmsBase}/api/ai-connector/v1/session/bridge?${params.toString()}`;
}

export async function previewFamilyBankPlan(
  courseId: string,
  payload: {
    chapter_node_id?: string | null;
    total_questions: number;
    difficulty_distribution?: { easy?: number; medium?: number; hard?: number; EASY?: number; MEDIUM?: number; HARD?: number };
    require_all_approved?: boolean;
    shortage_policy?: string;
    max_families_per_bank?: number;
  },
  headers: HeadersInit,
) {
  return parseResponse(
    await fetch(`${API}/publish/courses/${encodeURIComponent(courseId)}/family-bank-plan/preview`, {
      method: "POST",
      headers,
      body: JSON.stringify(payload),
    }),
  );
}

export async function publishFamilyBankPlan(
  courseId: string,
  plan: any,
  headers: HeadersInit,
  mode: "publish_new" | "replace" | "delete_reimport" = "publish_new",
  idempotencyKey?: string,
) {
  return parseResponse(
    await fetch(`${API}/publish/courses/${encodeURIComponent(courseId)}/family-bank-plan/publish`, {
      method: "POST",
      headers: withIdempotency(headers, idempotencyKey),
      body: JSON.stringify({ plan, mode }),
    }),
  );
}

export async function createCmsQuizNode(
  courseId: string,
  payload: { parent_node_id: string; quiz_title: string; unit_title: string; plan?: any },
  headers: HeadersInit,
  idempotencyKey?: string,
) {
  return parseResponse(
    await fetch(`${API}/publish/courses/${encodeURIComponent(courseId)}/cms-quiz-node/create`, {
      method: "POST",
      headers: withIdempotency(headers, idempotencyKey),
      body: JSON.stringify(payload),
    }),
  );
}

export async function insertCmsProblemBanks(
  courseId: string,
  payload: { unit_node_id: string; plan: any; strict_component_selection?: boolean },
  headers: HeadersInit,
  idempotencyKey?: string,
) {
  return parseResponse(
    await fetch(`${API}/publish/courses/${encodeURIComponent(courseId)}/cms-problem-banks/insert`, {
      method: "POST",
      headers: withIdempotency(headers, idempotencyKey),
      body: JSON.stringify(payload),
    }),
  );
}



export async function getBankDashboardAnalytics(headers: HeadersInit, filters: { dateRange?: string; fromDate?: string; toDate?: string } = {}) {
  const params = new URLSearchParams();
  params.set('date_range', filters.dateRange || '30d');
  if (filters.fromDate) params.set('from_date', filters.fromDate);
  if (filters.toDate) params.set('to_date', filters.toDate);
  return parseResponse<DashboardAnalytics>(
    await fetch(`${API}/question-bank-v2/dashboard/analytics?${params.toString()}`, { headers }),
  );
}


export async function getBankDashboardDrilldown(
  headers: HeadersInit,
  filters: {
    entity?: string
    q?: string
    status?: string
    difficulty?: string
    questionType?: string
    createdFrom?: string
    createdTo?: string
    questionId?: string
    chapterId?: string
    subjectId?: string
    limit?: number
  } = {},
) {
  const params = new URLSearchParams();
  params.set('entity', filters.entity || 'questions');
  if (filters.q) params.set('q', filters.q);
  if (filters.status) params.set('status', filters.status);
  if (filters.difficulty) params.set('difficulty', filters.difficulty);
  if (filters.questionType) params.set('question_type', filters.questionType);
  if (filters.createdFrom) params.set('created_from', filters.createdFrom);
  if (filters.createdTo) params.set('created_to', filters.createdTo);
  if (filters.questionId) params.set('question_id', filters.questionId);
  if (filters.chapterId) params.set('chapter_id', filters.chapterId);
  if (filters.subjectId) params.set('subject_id', filters.subjectId);
  params.set('limit', String(filters.limit || 100));
  return parseResponse<BankDashboardDrilldownResponse>(
    await fetch(`${API}/question-bank-v2/dashboard/drilldown?${params.toString()}`, { headers }),
  );
}

export async function getBankDashboardOverview(headers: HeadersInit) {
  return parseResponse<BankDashboardOverview>(
    await fetch(`${API}/question-bank-v2/dashboard/overview`, { headers }),
  );
}

export async function searchBankDashboard(headers: HeadersInit, q: string, limit = 20) {
  const params = new URLSearchParams();
  params.set('q', q);
  params.set('limit', String(limit));
  params.set('include_questions', 'true');
  const payload = await parseResponse<BankSearchResult[] | BankSearchGroupedResponse>(
    await fetch(`${API}/question-bank-v2/search?${params.toString()}`, { headers }),
  );
  if (Array.isArray(payload)) return payload;
  if (Array.isArray(payload.items) && payload.items.length) return payload.items;
  const groups = payload.groups || {};
  return [
    ...(groups.departments || []),
    ...(groups.subjects || []),
    ...(groups.subject_versions || []),
    ...(groups.chapters || []),
    ...(groups.questions || []),
  ].slice(0, limit);
}

export async function getDepartmentSummaries(headers: HeadersInit) {
  return parseResponse<DepartmentSummary[]>(
    await fetch(`${API}/question-bank-v2/departments/summary`, { headers }),
  );
}

export async function getSubjectSummaries(headers: HeadersInit, departmentId: string) {
  return parseResponse<SubjectSummary[]>(
    await fetch(`${API}/question-bank-v2/departments/${encodeURIComponent(departmentId)}/subjects/summary`, { headers }),
  );
}

export async function getSubjectVersionSummaries(headers: HeadersInit, subjectId: string) {
  return parseResponse<SubjectVersionSummary[]>(
    await fetch(`${API}/question-bank-v2/subjects/${encodeURIComponent(subjectId)}/versions/summary`, { headers }),
  );
}

export async function getChapterSummaries(headers: HeadersInit, subjectOfferingId: string) {
  return parseResponse<ChapterSummary[]>(
    await fetch(`${API}/question-bank-v2/subject-versions/${encodeURIComponent(subjectOfferingId)}/chapters/summary`, { headers }),
  );
}

export async function getBankSummary(headers: HeadersInit) {
  return parseResponse<BankSummary>(
    await fetch(`${API}/question-bank-v2/summary`, { headers }),
  );
}

export async function getDepartments(headers: HeadersInit) {
  return parsePageItems<Department>(
    await fetch(`${API}/question-bank-v2/departments?page_size=50`, { headers }),
  );
}

export async function createDepartment(headers: HeadersInit, payload: { code: string; name: string; description?: string }) {
  return parseResponse<Department>(
    await fetch(`${API}/question-bank-v2/departments`, { method: 'POST', headers, body: JSON.stringify(payload) }),
  );
}


export async function updateDepartment(headers: HeadersInit, id: string, payload: { code?: string; name?: string; description?: string }) {
  return parseResponse<Department>(
    await fetch(`${API}/question-bank-v2/departments/${encodeURIComponent(id)}`, { method: 'PATCH', headers, body: JSON.stringify(payload) }),
  );
}

export async function deleteDepartment(headers: HeadersInit, id: string) {
  return parseResponse<{ ok: boolean; deleted: boolean; message: string }>(
    await fetch(`${API}/question-bank-v2/departments/${encodeURIComponent(id)}`, { method: 'DELETE', headers }),
  );
}

export async function getSubjects(headers: HeadersInit, departmentId?: string) {
  const params = new URLSearchParams();
  if (departmentId) params.set('department_id', departmentId);
  params.set('page_size', '100');
  return parsePageItems<Subject>(
    await fetch(`${API}/question-bank-v2/subjects?${params.toString()}`, { headers }),
  );
}

export async function createSubject(headers: HeadersInit, payload: { department_id: string; code: string; name: string; description?: string }) {
  return parseResponse<Subject>(
    await fetch(`${API}/question-bank-v2/subjects`, { method: 'POST', headers, body: JSON.stringify(payload) }),
  );
}


export async function updateSubject(headers: HeadersInit, id: string, payload: { code?: string; name?: string; description?: string }) {
  return parseResponse<Subject>(
    await fetch(`${API}/question-bank-v2/subjects/${encodeURIComponent(id)}`, { method: 'PATCH', headers, body: JSON.stringify(payload) }),
  );
}

export async function deleteSubject(headers: HeadersInit, id: string) {
  return parseResponse<{ ok: boolean; deleted: boolean; message: string }>(
    await fetch(`${API}/question-bank-v2/subjects/${encodeURIComponent(id)}`, { method: 'DELETE', headers }),
  );
}

export async function getSubjectOfferings(headers: HeadersInit, subjectId?: string) {
  const params = new URLSearchParams();
  if (subjectId) params.set('subject_id', subjectId);
  params.set('page_size', '100');
  return parsePageItems<SubjectOffering>(
    await fetch(`${API}/question-bank-v2/subject-versions?${params.toString()}`, { headers }),
  );
}

export async function createSubjectOffering(headers: HeadersInit, payload: { subject_id: string; code?: string; name?: string; term?: string | null; season?: string | null; year?: number | string | null; version_code?: string; based_on_offering_id?: string | null; clone_from_offering_id?: string | null; clone_chapters?: boolean; clone_materials?: boolean; clone_questions?: boolean; description?: string }) {
  return parseResponse<SubjectOffering>(
    await fetch(`${API}/question-bank-v2/subject-versions`, { method: 'POST', headers, body: JSON.stringify(payload) }),
  );
}


export async function updateSubjectOffering(headers: HeadersInit, id: string, payload: { code?: string; name?: string; term?: string | null; version_code?: string; description?: string }) {
  return parseResponse<SubjectOffering>(
    await fetch(`${API}/question-bank-v2/subject-versions/${encodeURIComponent(id)}`, { method: 'PATCH', headers, body: JSON.stringify(payload) }),
  );
}

export async function deleteSubjectOffering(headers: HeadersInit, id: string) {
  return parseResponse<{ ok: boolean; deleted: boolean; message: string }>(
    await fetch(`${API}/question-bank-v2/subject-versions/${encodeURIComponent(id)}`, { method: 'DELETE', headers }),
  );
}

export async function getSubjectChapters(headers: HeadersInit, subjectId?: string, subjectOfferingId?: string) {
  const params = new URLSearchParams();
  if (subjectId) params.set('subject_id', subjectId);
  if (subjectOfferingId) params.set('subject_offering_id', subjectOfferingId);
  params.set('page_size', '100');
  return parsePageItems<SubjectChapter>(
    await fetch(`${API}/question-bank-v2/chapters?${params.toString()}`, { headers }),
  );
}

export async function createSubjectChapter(headers: HeadersInit, payload: { subject_id: string; subject_offering_id?: string | null; chapter_no?: number; title: string; description?: string; sort_order?: number }) {
  return parseResponse<SubjectChapter>(
    await fetch(`${API}/question-bank-v2/chapters`, { method: 'POST', headers, body: JSON.stringify(payload) }),
  );
}


export async function updateSubjectChapter(headers: HeadersInit, id: string, payload: { title?: string; description?: string; sort_order?: number }) {
  return parseResponse<SubjectChapter>(
    await fetch(`${API}/question-bank-v2/chapters/${encodeURIComponent(id)}`, { method: 'PATCH', headers, body: JSON.stringify(payload) }),
  );
}

export async function deleteSubjectChapter(headers: HeadersInit, id: string) {
  return parseResponse<{ ok: boolean; deleted: boolean; message: string }>(
    await fetch(`${API}/question-bank-v2/chapters/${encodeURIComponent(id)}`, { method: 'DELETE', headers }),
  );
}

export async function getBankVersions(headers: HeadersInit, chapterId?: string, subjectId?: string, subjectOfferingId?: string) {
  const params = new URLSearchParams();
  if (chapterId) params.set('chapter_id', chapterId);
  if (subjectId) params.set('subject_id', subjectId);
  if (subjectOfferingId) params.set('subject_offering_id', subjectOfferingId);
  params.set('page_size', '100');
  return parsePageItems<BankVersion>(
    await fetch(`${API}/question-bank-v2/bank-versions?${params.toString()}`, { headers }),
  );
}

export async function createBankVersion(headers: HeadersInit, payload: { subject_id: string; chapter_id: string; subject_offering_id?: string | null; version_code: string; title?: string; change_note?: string; based_on_version_id?: string | null }) {
  return parseResponse<BankVersion>(
    await fetch(`${API}/question-bank-v2/bank-versions`, { method: 'POST', headers, body: JSON.stringify(payload) }),
  );
}

export async function getBankReleases(headers: HeadersInit, bankVersionId?: string, chapterId?: string) {
  const params = new URLSearchParams();
  if (bankVersionId) params.set('bank_version_id', bankVersionId);
  if (chapterId) params.set('chapter_id', chapterId);
  params.set('page_size', '100');
  return parsePageItems<BankRelease>(
    await fetch(`${API}/question-bank-v2/releases?${params.toString()}`, { headers }),
  );
}

export async function createBankRelease(headers: HeadersInit, payload: { bank_version_id: string; release_code?: string; title?: string; include_approved_questions?: boolean }) {
  return parseResponse<BankRelease>(
    await fetch(`${API}/question-bank-v2/releases`, { method: 'POST', headers, body: JSON.stringify(payload) }),
  );
}

export async function publishBankRelease(headers: HeadersInit, releaseId: string, payload: { openedx_course_id_for_org?: string | null; force_reimport?: boolean } = {}) {
  const queued = await parseResponse<BankOperationJobQueued>(
    await fetch(`${API}/question-bank-v2/releases/${encodeURIComponent(releaseId)}/publish-openedx-job`, { method: 'POST', headers, body: JSON.stringify(payload) }),
  );
  return enqueueAndWait<BankReleasePublishResult>(headers, queued, 20 * 60 * 1000);
}

export async function getCourseMappings(headers: HeadersInit, subjectId?: string) {
  const params = new URLSearchParams();
  if (subjectId) params.set('subject_id', subjectId);
  params.set('page_size', '100');
  return parsePageItems<EdxCourseMapping>(
    await fetch(`${API}/question-bank-v2/course-mappings?${params.toString()}`, { headers }),
  );
}

export async function validateCourseMapping(headers: HeadersInit, payload: { openedx_course_id: string; subject_id: string; department_id?: string | null; term?: string | null; openedx_course_title?: string | null }) {
  return parseResponse<MappingValidation>(
    await fetch(`${API}/question-bank-v2/course-mappings/validate`, { method: 'POST', headers, body: JSON.stringify(payload) }),
  );
}

export async function createCourseMapping(headers: HeadersInit, payload: { openedx_course_id: string; subject_id: string; department_id?: string | null; term?: string | null; openedx_course_title?: string | null; allow_warnings?: boolean }) {
  return parseResponse<EdxCourseMapping>(
    await fetch(`${API}/question-bank-v2/course-mappings`, { method: 'POST', headers, body: JSON.stringify(payload) }),
  );
}

export async function validateCourseChapterMapping(headers: HeadersInit, payload: { course_mapping_id: string; subject_chapter_id: string; bank_release_id: string; openedx_parent_node_id: string; openedx_node_title?: string | null }) {
  return parseResponse<MappingValidation>(
    await fetch(`${API}/question-bank-v2/course-chapter-mappings/validate`, { method: 'POST', headers, body: JSON.stringify(payload) }),
  );
}

export async function createCourseChapterMapping(headers: HeadersInit, payload: { course_mapping_id: string; subject_chapter_id: string; bank_release_id?: string | null; openedx_parent_node_id?: string | null; openedx_node_title?: string | null; enabled?: boolean; allow_warnings?: boolean }) {
  return parseResponse<EdxCourseChapterMapping>(
    await fetch(`${API}/question-bank-v2/course-chapter-mappings`, { method: 'POST', headers, body: JSON.stringify(payload) }),
  );
}

export async function getQuizBlueprints(headers: HeadersInit, chapterId?: string) {
  const params = new URLSearchParams();
  if (chapterId) params.set('chapter_id', chapterId);
  params.set('page_size', '100');
  return parsePageItems<QuizBlueprint>(
    await fetch(`${API}/question-bank-v2/quiz-blueprints?${params.toString()}`, { headers }),
  );
}

export async function createQuizBlueprint(headers: HeadersInit, payload: { subject_id: string; chapter_id: string; title: string; total_questions: number; difficulty_easy: number; difficulty_medium: number; difficulty_hard: number; max_families_per_bank?: number; pick_count_per_slot?: number }) {
  return parseResponse<QuizBlueprint>(
    await fetch(`${API}/question-bank-v2/quiz-blueprints`, { method: 'POST', headers, body: JSON.stringify(payload) }),
  );
}



export async function getMaterialVersions(headers: HeadersInit, bankVersionId?: string) {
  const params = new URLSearchParams();
  if (bankVersionId) params.set('bank_version_id', bankVersionId);
  params.set('page_size', '100');
  return parsePageItems<MaterialVersion>(
    await fetch(`${API}/question-bank-v2/material-versions?${params.toString()}`, { headers }),
  );
}


export async function deleteMaterialVersion(headers: HeadersInit, materialVersionId: string) {
  return parseResponse<{ ok: boolean; material_version_id: string; bank_version_id: string; chunks_deleted: number; detached_question_count: number; message: string }>(
    await fetch(`${API}/question-bank-v2/material-versions/${encodeURIComponent(materialVersionId)}`, {
      method: 'DELETE',
      headers,
    }),
  );
}

export async function uploadBankMaterial(
  headers: HeadersInit,
  bankVersionId: string,
  file: File,
  payload: { title?: string; change_type?: string; replace_existing?: boolean } = {},
) {
  const form = new FormData();
  form.append('file', file);
  form.append('title', payload.title || file.name);
  form.append('change_type', payload.change_type || 'initial');
  form.append('replace_existing', String(Boolean(payload.replace_existing)));
  const queued = await parseResponse<BankOperationJobQueued>(
    await fetch(`${API}/question-bank-v2/bank-versions/${encodeURIComponent(bankVersionId)}/materials/upload-job`, {
      method: 'POST',
      headers: withoutContentType(headers),
      body: form,
    }),
  );
  return enqueueAndWait<MaterialUploadResult>(headers, queued, 10 * 60 * 1000);
}

export async function getBankMaterialChunks(headers: HeadersInit, bankVersionId: string, materialVersionId?: string) {
  const params = new URLSearchParams();
  if (materialVersionId) params.set('material_version_id', materialVersionId);
  params.set('page_size', '100');
  return parsePageItems<MaterialChunk>(
    await fetch(`${API}/question-bank-v2/bank-versions/${encodeURIComponent(bankVersionId)}/material-chunks?${params.toString()}`, { headers }),
  );
}

export async function previewGenerateFromBankVersion(
  headers: HeadersInit,
  bankVersionId: string,
  payload: {
    question_count: number;
    target_question_count?: number;
    difficulty_easy?: number;
    difficulty_medium?: number;
    difficulty_hard?: number;
    material_version_ids?: string[] | null;
  },
) {
  return parseResponse<BankGeneratePreview>(
    await fetch(`${API}/question-bank-v2/bank-versions/${encodeURIComponent(bankVersionId)}/generate/preview`, {
      method: 'POST',
      headers,
      body: JSON.stringify(payload),
    }),
  );
}

export async function generateFromBankVersion(
  headers: HeadersInit,
  bankVersionId: string,
  payload: {
    question_count: number;
    target_question_count?: number;
    difficulty_easy?: number;
    difficulty_medium?: number;
    difficulty_hard?: number;
    material_version_ids?: string[] | null;
    provider?: string;
    approve_after_generate?: boolean;
  },
) {
  const queued = await parseResponse<BankOperationJobQueued>(
    await fetch(`${API}/question-bank-v2/bank-versions/${encodeURIComponent(bankVersionId)}/generate-job`, {
      method: 'POST',
      headers,
      body: JSON.stringify(payload),
    }),
  );
  return enqueueAndWait<BankGenerateResult>(headers, queued, 20 * 60 * 1000);
}

function bankQuestionListItemToQuestion(item: BankQuestionListItem): BankVersionQuestion {
  return {
    id: item.id,
    bank_version_id: item.bank_version_id,
    subject_id: item.subject_id,
    subject_chapter_id: item.subject_chapter_id,
    concept_title: item.concept_title,
    question_family_id: item.question_family_id,
    variant_no: item.variant_no,
    difficulty: item.difficulty,
    question_text: item.question_text_preview || '',
    option_a: item.option_a_preview || '',
    option_b: item.option_b_preview || '',
    option_c: item.option_c_preview || '',
    option_d: item.option_d_preview || '',
    correct_answer: item.correct_answer,
    status: item.status,
    quality_score: Number(item.quality_score || 0),
    draft_error_reason: item.draft_error_reason,
    is_duplicate: item.is_duplicate,
    previous_question_id: item.previous_question_id,
    lineage_root_question_id: item.lineage_root_question_id,
    question_revision_no: item.question_revision_no ?? undefined,
    is_carry_over: Boolean(item.is_carry_over),
    is_retired: Boolean(item.is_retired),
    created_at: item.created_at,
  };
}

export async function getBankVersionQuestionPage(
  headers: HeadersInit,
  bankVersionId: string,
  options: { statusFilter?: string; difficulty?: string; search?: string; limit?: number; cursorCreatedAt?: string | null; cursorId?: string | null; includeTotal?: boolean } = {},
) {
  const params = new URLSearchParams();
  if (options.statusFilter) params.set('status_filter', options.statusFilter);
  if (options.difficulty) params.set('difficulty', options.difficulty);
  if (options.search) params.set('search', options.search);
  params.set('limit', String(Math.max(1, Math.min(Number(options.limit || 100), 100))));
  if (options.cursorCreatedAt && options.cursorId) {
    params.set('cursor_created_at', options.cursorCreatedAt);
    params.set('cursor_id', options.cursorId);
  }
  if (options.includeTotal) params.set('include_total', 'true');
  const page = await parseResponse<CursorPaginatedResponse<BankQuestionListItem>>(
    await fetch(`${API}/question-bank-v2/bank-versions/${encodeURIComponent(bankVersionId)}/questions?${params.toString()}`, { headers }),
  );
  return {
    ...page,
    items: (page.items || []).map(bankQuestionListItemToQuestion),
  } as CursorPaginatedResponse<BankVersionQuestion>;
}

export async function getBankVersionQuestions(headers: HeadersInit, bankVersionId: string, statusFilter?: string, limit = 100) {
  const requestedLimit = Math.max(1, Math.min(Number(limit || 100), 1000));
  const items: BankVersionQuestion[] = [];
  let cursorCreatedAt: string | null | undefined;
  let cursorId: string | null | undefined;
  while (items.length < requestedLimit) {
    const page = await getBankVersionQuestionPage(headers, bankVersionId, {
      statusFilter,
      limit: Math.min(100, requestedLimit - items.length),
      cursorCreatedAt,
      cursorId,
    });
    items.push(...(page.items || []));
    if (!page.has_next || !page.next_cursor?.created_at || !page.next_cursor?.id) break;
    cursorCreatedAt = page.next_cursor.created_at;
    cursorId = page.next_cursor.id;
  }
  return items;
}

export async function getBankVersionQuestion(headers: HeadersInit, bankVersionId: string, questionId: string) {
  return parseResponse<BankVersionQuestion>(
    await fetch(`${API}/question-bank-v2/bank-versions/${encodeURIComponent(bankVersionId)}/questions/${encodeURIComponent(questionId)}`, { headers }),
  );
}

export async function previewBankVersionDiff(
  headers: HeadersInit,
  bankVersionId: string,
  payload: { base_bank_version_id?: string | null; persist?: boolean } = {},
) {
  return parseResponse<BankVersionDiffPreview>(
    await fetch(`${API}/question-bank-v2/bank-versions/${encodeURIComponent(bankVersionId)}/diff/preview`, {
      method: 'POST',
      headers,
      body: JSON.stringify(payload),
    }),
  );
}

export async function carryOverBankQuestions(
  headers: HeadersInit,
  bankVersionId: string,
  payload: { base_bank_version_id: string; question_ids?: string[] | null; require_review?: boolean; diff_id?: string | null },
) {
  return parseResponse<BankCarryOverResult>(
    await fetch(`${API}/question-bank-v2/bank-versions/${encodeURIComponent(bankVersionId)}/carry-over`, {
      method: 'POST',
      headers,
      body: JSON.stringify(payload),
    }),
  );
}

export async function retireBankQuestions(
  headers: HeadersInit,
  bankVersionId: string,
  payload: { question_ids: string[]; reason?: string },
) {
  return parseResponse<BankRetireResult>(
    await fetch(`${API}/question-bank-v2/bank-versions/${encodeURIComponent(bankVersionId)}/questions/retire`, {
      method: 'POST',
      headers,
      body: JSON.stringify(payload),
    }),
  );
}




export async function previewQuizAutoMap(
  headers: HeadersInit,
  payload: { openedx_course_id: string; selected_subject_offering_id?: string | null; total_questions?: number; difficulty_easy?: number; difficulty_medium?: number; difficulty_hard?: number; max_families_per_bank?: number },
) {
  return parseResponse<QuizAutoMapResult>(
    await fetch(`${API}/question-bank-v2/quiz/auto-map/preview`, {
      method: 'POST',
      headers,
      body: JSON.stringify(payload),
    }),
  );
}

export async function applyQuizAutoMap(
  headers: HeadersInit,
  payload: { openedx_course_id: string; selected_subject_offering_id?: string | null; total_questions?: number; difficulty_easy?: number; difficulty_medium?: number; difficulty_hard?: number; max_families_per_bank?: number },
) {
  return parseResponse<QuizAutoMapResult>(
    await fetch(`${API}/question-bank-v2/quiz/auto-map/apply`, {
      method: 'POST',
      headers,
      body: JSON.stringify(payload),
    }),
  );
}

export async function previewQuizFromBankRelease(
  headers: HeadersInit,
  releaseId: string,
  payload: { total_questions: number; difficulty_easy: number; difficulty_medium: number; difficulty_hard: number; max_families_per_bank?: number },
) {
  return parseResponse<BankReleaseQuizPlan>(
    await fetch(`${API}/question-bank-v2/releases/${encodeURIComponent(releaseId)}/quiz/preview`, {
      method: 'POST',
      headers,
      body: JSON.stringify(payload),
    }),
  );
}

export async function createQuizFromBankRelease(
  headers: HeadersInit,
  releaseId: string,
  payload: { course_chapter_mapping_id: string; quiz_title?: string; unit_title?: string; total_questions: number; difficulty_easy: number; difficulty_medium: number; difficulty_hard: number; max_families_per_bank?: number; custom_timer_enabled?: boolean; time_limit_minutes?: number; retake_cooldown_minutes?: number; auto_submit_on_timeout?: boolean; lock_after_timeout?: boolean; native_timed_exam?: boolean },
) {
  const queued = await parseResponse<BankOperationJobQueued>(
    await fetch(`${API}/question-bank-v2/releases/${encodeURIComponent(releaseId)}/quiz/create-job`, {
      method: 'POST',
      headers,
      body: JSON.stringify(payload),
    }),
  );
  return enqueueAndWait<BankReleaseQuizCreateResult>(headers, queued, 20 * 60 * 1000);
}


export async function updateBankQuestion(
  headers: HeadersInit,
  bankVersionId: string,
  questionId: string,
  payload: {
    difficulty?: string;
    cognitive_level?: string;
    learning_objective?: string;
    question_text?: string;
    option_a?: string;
    option_b?: string;
    option_c?: string;
    option_d?: string;
    correct_answer?: string;
    explanation?: string;
    concept_title?: string;
    question_family_id?: string;
    source_ref?: string;
    source_type?: string;
    source_excerpt?: string;
    source_evidence?: string;
    target_status?: string;
    note?: string;
  },
) {
  return parseResponse<BankVersionQuestion>(
    await fetch(`${API}/question-bank-v2/bank-versions/${encodeURIComponent(bankVersionId)}/questions/${encodeURIComponent(questionId)}`, {
      method: 'PATCH',
      headers,
      body: JSON.stringify(payload),
    }),
  );
}


export async function reviewBankQuestion(
  headers: HeadersInit,
  bankVersionId: string,
  questionId: string,
  payload: { action: 'approve' | 'reject' | 'back_to_review'; note?: string },
) {
  return parseResponse<BankQuestionReviewResult>(
    await fetch(`${API}/question-bank-v2/bank-versions/${encodeURIComponent(bankVersionId)}/questions/${encodeURIComponent(questionId)}/review`, {
      method: 'POST',
      headers,
      body: JSON.stringify(payload),
    }),
  );
}

export async function bulkReviewBankQuestions(
  headers: HeadersInit,
  bankVersionId: string,
  payload: { action: 'approve' | 'reject' | 'back_to_review'; question_ids?: string[]; approve_all_pending?: boolean; note?: string },
) {
  return parseResponse<BankQuestionBulkReviewResult>(
    await fetch(`${API}/question-bank-v2/bank-versions/${encodeURIComponent(bankVersionId)}/questions/bulk-review`, {
      method: 'POST',
      headers,
      body: JSON.stringify(payload),
    }),
  );
}

export async function markBankDiffResolved(
  headers: HeadersInit,
  bankVersionId: string,
  payload: { note?: string } = {},
) {
  return parseResponse<BankDocumentDiffResolveResult>(
    await fetch(`${API}/question-bank-v2/bank-versions/${encodeURIComponent(bankVersionId)}/diff/mark-resolved`, {
      method: 'POST',
      headers,
      body: JSON.stringify(payload),
    }),
  );
}

export async function getBankReleaseReadiness(headers: HeadersInit, bankVersionId: string) {
  return parseResponse<BankReleaseReadiness>(
    await fetch(`${API}/question-bank-v2/bank-versions/${encodeURIComponent(bankVersionId)}/release/readiness`, { headers }),
  );
}

export async function getCourseQuizInstances(
  headers: HeadersInit,
  params: { openedx_course_id?: string; bank_release_id?: string; limit?: number } = {},
) {
  const search = new URLSearchParams();
  if (params.openedx_course_id) search.set('openedx_course_id', params.openedx_course_id);
  if (params.bank_release_id) search.set('bank_release_id', params.bank_release_id);
  if (params.limit) search.set('limit', String(params.limit));
  const suffix = search.toString() ? `?${search.toString()}` : '';
  return parsePageItems<CourseQuizInstance>(
    await fetch(`${API}/question-bank-v2/course-quiz-instances${suffix}`, { headers }),
  );
}

export async function rollbackCourseQuizInstance(
  headers: HeadersInit,
  instanceId: string,
  payload: { mode?: 'safe' | 'manual'; note?: string } = {},
) {
  return parseResponse<CourseQuizRollbackResult>(
    await fetch(`${API}/question-bank-v2/course-quiz-instances/${encodeURIComponent(instanceId)}/rollback`, {
      method: 'POST',
      headers,
      body: JSON.stringify(payload),
    }),
  );
}


export async function getEffectiveRBAC(headers: HeadersInit): Promise<EffectiveRBAC> {
  return parseResponse<EffectiveRBAC>(await fetch(`${API}/rbac/me`, { headers }))
}

export async function getRBACRoles(headers: HeadersInit): Promise<RBACRole[]> {
  return parseResponse<RBACRole[]>(await fetch(`${API}/rbac/roles`, { headers }))
}

export async function getRBACPermissions(headers: HeadersInit): Promise<RBACPermission[]> {
  return parseResponse<RBACPermission[]>(await fetch(`${API}/rbac/permissions`, { headers }))
}

export async function getRoleAssignments(
  headers: HeadersInit,
  filters: { userId?: string; roleCode?: string; scopeType?: string; scopeId?: string; includeRevoked?: boolean } = {},
): Promise<RoleAssignmentListResponse> {
  const params = new URLSearchParams()
  if (filters.userId) params.set('user_id', filters.userId)
  if (filters.roleCode) params.set('role_code', filters.roleCode)
  if (filters.scopeType) params.set('scope_type', filters.scopeType)
  if (filters.scopeId) params.set('scope_id', filters.scopeId)
  if (filters.includeRevoked) params.set('include_revoked', 'true')
  const suffix = params.toString() ? `?${params.toString()}` : ''
  return parseResponse<RoleAssignmentListResponse>(await fetch(`${API}/rbac/assignments${suffix}`, { headers }))
}

export async function createRoleAssignment(payload: RoleAssignmentCreate, headers: HeadersInit): Promise<RoleAssignment> {
  return parseResponse<RoleAssignment>(await fetch(`${API}/rbac/assignments`, { method: 'POST', headers, body: JSON.stringify(payload) }))
}



export async function downloadRBACImportTemplate(headers: HeadersInit): Promise<Blob> {
  const response = await fetch(`${API}/rbac/assignments/import-template`, { headers });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || response.statusText);
  }
  return response.blob();
}

export async function importRoleAssignmentsFromExcel(headers: HeadersInit, file: File, dryRun = false): Promise<RoleAssignmentImportResponse> {
  const form = new FormData();
  form.append('file', file);
  const cleanHeaders = withoutContentType(headers);
  return parseResponse<RoleAssignmentImportResponse>(await fetch(`${API}/rbac/assignments/import?dry_run=${dryRun ? 'true' : 'false'}`, {
    method: 'POST',
    headers: cleanHeaders,
    body: form,
  }));
}

export async function revokeRoleAssignment(assignmentId: string, headers: HeadersInit, revokeReason = ''): Promise<RoleAssignment> {
  return parseResponse<RoleAssignment>(await fetch(`${API}/rbac/assignments/${encodeURIComponent(assignmentId)}`, {
    method: 'DELETE',
    headers,
    body: JSON.stringify({ revoke_reason: revokeReason }),
  }))
}
