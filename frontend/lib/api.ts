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
  BankReleasePublishAudit,
  BankReleasePreview,
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
  BankQuestionMedia,
  BankQuestionContent,
  BankOpenEdxImportPreview,
  BankOpenEdxImportResult,
  BankQuestionListItem,
  BankQuestionImportPreview,
  LegacyQuizCmsOldImportPreview,
  BankVersionDiffPreview,
  BankMaterialRecheckResult,
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
  BankCostAnalytics,
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
  RoleAssignmentBatchCreate,
  RoleAssignmentBatchResponse,
  RoleAssignmentCreate,
  RoleAssignmentImportResponse,
  RoleAssignmentListResponse,
  EffectiveRBAC,
  BankOperationJob,
  BankOperationJobQueued,
  AcademicTerm,
  AcademicBlock,
  AcademicSubject,
  AcademicLearningPlatform,
  AcademicSubjectDeliveryListResponse,
  AcademicSubjectCatalogRefreshResult,
  AcademicSubjectPlatformMutationResult,
  UdemyPlanDetail,
  UdemyPlanImportPreview,
  UdemyPlanMutationResult,
  UdemyPlanMilestone,
  UdemySubjectPlan,
  UdemyProgressImportBatch,
  UdemyProgressImportJobResult,
  UdemyProgressSummary,
  UdemyProgressDashboard,
  UdemyProgressStudentList,
  AcademicSubjectManagementListResponse,
  AcademicSubjectCourseAutoMapResult,
  AcademicSubjectAutoMapAllSyncResult,
  AcademicCampus,
  AcademicClass,
  AcademicClassListResponse,
  AcademicClassSyncJob,
  AcademicBulkOperationJob,
  AcademicStudentListResponse,
  AcademicSyncResult,
  AcademicSyncRun,
  AcademicAPSyncOptions,
  AcademicMappingSummary,
  AcademicLearningSummary,
  AcademicIdentityCleanupResult,
  AcademicIdentityReconciliationReport,
  AcademicEnrollmentSyncResult,
  AcademicLearningSyncResult,
  AcademicMappingResolveResult,
  AcademicManualMappingImportResult,
  AcademicCourseMappingValidation,
  AcademicCourseMapping,
  AcademicClassCourseMapping,
  AcademicClassCourseMappingProposal,
  AcademicCourseMappingListResponse,
  AcademicTrainingTeacherReportResponse,
  AcademicTeacherReportJob,
  AcademicQuizDeadlineOverride,
  AcademicAssignmentDefenseScore,
  AnalyticsLearningBehaviorSummary,
  AnalyticsLearningBehaviorListResponse,
  AnalyticsClassWorkspaceResponse,
  AnalyticsClassResultDoctor,
  AnalyticsClassBehaviorOverviewResponse,
  AnalyticsStudentLearningBehaviorDetail,
  AnalyticsLearningDashboardResponse,
  AnalyticsClassVideoSummary,
  AnalyticsClassSessionProgressResponse,
  AnalyticsDataQualityReport,
  AnalyticsBackfillPlanResponse,
  AnalyticsBackfillJobsResponse,
  AnalyticsProductionReadinessReport,
  AnalyticsSlaReport,
  AnalyticsPilotAcceptanceReport,
  AnalyticsEvidencePackReport,
  AnalyticsCourseClassMappingReport,
  PerformanceReadinessReport,
  SecurityReadinessReport,
  ReleaseCandidateReport,
  PilotOperationsReport,
  AnalyticsRolloutControlReport,
  AnalyticsMonitoringReport,
  AnalyticsOpsStatus,
  AnalyticsIngestJobResponse,
  JsonObject,
  JsonValue,
} from "../types";

const rawApiBase =
  process.env.NEXT_PUBLIC_API_BASE_URL ||
  process.env.NEXT_PUBLIC_API_URL ||
  "http://localhost:8000";
const normalizedApiBase = rawApiBase.replace(/\/+$/, "");
export const API = normalizedApiBase.endsWith("/api")
  ? normalizedApiBase
  : `${normalizedApiBase}/api`;

export class ApiRequestError extends Error {
  code: string;
  status?: number;
  requestId?: string;
  details?: unknown;

  constructor(
    message: string,
    options: {
      code: string;
      status?: number;
      requestId?: string;
      details?: unknown;
      cause?: unknown;
    },
  ) {
    super(message, { cause: options.cause });
    this.name = "ApiRequestError";
    this.code = options.code;
    this.status = options.status;
    this.requestId = options.requestId;
    this.details = options.details;
  }
}

export type ApiFetchInit = RequestInit & {
  timeoutMs?: number;
  retries?: number;
  retryDelayMs?: number;
  skipAuthExpiredEvent?: boolean;
};

const DEFAULT_GET_TIMEOUT_MS = Math.max(5_000, Number(process.env.NEXT_PUBLIC_API_GET_TIMEOUT_MS || 45_000));
const DEFAULT_WRITE_TIMEOUT_MS = Math.max(10_000, Number(process.env.NEXT_PUBLIC_API_WRITE_TIMEOUT_MS || 120_000));
const RETRYABLE_STATUS_CODES = new Set([408, 425, 429, 502, 503, 504]);

function requestIdValue(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") return crypto.randomUUID();
  return `web-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}

function retryAfterMs(response: Response, fallbackMs: number): number {
  const value = response.headers.get("Retry-After");
  if (!value) return fallbackMs;
  const seconds = Number(value);
  if (Number.isFinite(seconds)) return Math.min(10_000, Math.max(fallbackMs, seconds * 1_000));
  const date = Date.parse(value);
  return Number.isFinite(date) ? Math.min(10_000, Math.max(fallbackMs, date - Date.now())) : fallbackMs;
}

function dispatchAuthExpired(input: RequestInfo | URL, skip: boolean): void {
  if (skip || typeof window === "undefined") return;
  const url = String(input);
  if (/\/auth\/(exchange|session|logout|cms-callback)/.test(url)) return;
  window.dispatchEvent(new CustomEvent("ai:auth-expired"));
}

function isLikelyJsonRequestBody(body: BodyInit | null | undefined): body is string {
  if (typeof body !== "string") return false;
  const trimmed = body.trim();
  return trimmed.startsWith("{") || trimmed.startsWith("[") || trimmed === "null";
}

function prepareRequestHeaders(init: RequestInit): Headers {
  const headers = new Headers(init.headers);
  if (!headers.has("Content-Type") && isLikelyJsonRequestBody(init.body)) {
    headers.set("Content-Type", "application/json");
  }
  if (!headers.has("X-Request-ID")) headers.set("X-Request-ID", requestIdValue());
  return headers;
}

function sleepWithSignal(ms: number, signal?: AbortSignal): Promise<void> {
  if (signal?.aborted) return Promise.reject(signal.reason || new DOMException("Aborted", "AbortError"));
  return new Promise((resolve, reject) => {
    const finish = () => {
      signal?.removeEventListener("abort", abort);
      resolve();
    };
    const timer = setTimeout(finish, ms);
    const abort = () => {
      clearTimeout(timer);
      signal?.removeEventListener("abort", abort);
      reject(signal?.reason || new DOMException("Aborted", "AbortError"));
    };
    signal?.addEventListener("abort", abort, { once: true });
  });
}

export async function apiFetch(
  input: RequestInfo | URL,
  init: ApiFetchInit = {},
): Promise<Response> {
  const {
    timeoutMs,
    retries,
    retryDelayMs = 750,
    skipAuthExpiredEvent = false,
    signal: rawCallerSignal,
    ...requestInit
  } = init;
  const callerSignal = rawCallerSignal || undefined;
  const method = String(requestInit.method || "GET").toUpperCase();
  const safeToRetry = method === "GET" || method === "HEAD";
  const maxRetries = Math.max(0, retries ?? (safeToRetry ? 1 : 0));
  const effectiveTimeout = Math.max(1_000, timeoutMs ?? (safeToRetry ? DEFAULT_GET_TIMEOUT_MS : DEFAULT_WRITE_TIMEOUT_MS));
  const headers = prepareRequestHeaders(requestInit);
  const requestId = headers.get("X-Request-ID") || undefined;

  for (let attempt = 0; attempt <= maxRetries; attempt += 1) {
    const controller = new AbortController();
    const abortFromCaller = () => controller.abort(callerSignal?.reason);
    if (callerSignal?.aborted) controller.abort(callerSignal.reason);
    else callerSignal?.addEventListener("abort", abortFromCaller, { once: true });
    const timeout = setTimeout(() => controller.abort(new DOMException("Request timeout", "TimeoutError")), effectiveTimeout);
    try {
      const response = await fetch(input, {
        credentials: "include",
        ...requestInit,
        headers,
        signal: controller.signal,
      });
      if (response.status === 401) dispatchAuthExpired(input, skipAuthExpiredEvent);
      if (attempt < maxRetries && RETRYABLE_STATUS_CODES.has(response.status)) {
        await response.body?.cancel().catch(() => undefined);
        await sleepWithSignal(retryAfterMs(response, retryDelayMs * 2 ** attempt), callerSignal);
        continue;
      }
      return response;
    } catch (error) {
      if (callerSignal?.aborted) throw error;
      const timedOut = controller.signal.aborted;
      if (attempt < maxRetries && safeToRetry) {
        await sleepWithSignal(Math.min(5_000, retryDelayMs * 2 ** attempt), callerSignal);
        continue;
      }
      throw new ApiRequestError(
        timedOut
          ? "Yêu cầu quá thời gian chờ. Vui lòng thử lại hoặc kiểm tra trạng thái hệ thống."
          : "Không kết nối được máy chủ. Vui lòng kiểm tra mạng và thử lại.",
        { code: timedOut ? "REQUEST_TIMEOUT" : "NETWORK_ERROR", requestId, cause: error },
      );
    } finally {
      clearTimeout(timeout);
      callerSignal?.removeEventListener("abort", abortFromCaller);
    }
  }
  throw new ApiRequestError("Không thể hoàn tất yêu cầu.", { code: "REQUEST_FAILED", requestId });
}

function withIdempotency(
  headers: HeadersInit,
  idempotencyKey?: string,
): HeadersInit {
  if (!idempotencyKey) return headers;
  const next = new Headers(headers);
  next.set("Idempotency-Key", idempotencyKey);
  return next;
}

function withoutContentType(headers: HeadersInit): HeadersInit {
  const next = new Headers(headers);
  next.delete("Content-Type");
  next.delete("content-type");
  return next;
}

function isJsonObject(value: unknown): value is JsonObject {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function stringFromJson(value: JsonValue | undefined): string | undefined {
  return typeof value === "string" ? value : undefined;
}

function apiErrorEnvelope(data: unknown): JsonObject {
  const root = isJsonObject(data) ? data : {};
  return isJsonObject(root.error) ? root.error : root;
}

function apiErrorCode(data: unknown, fallback: string): string {
  const root = isJsonObject(data) ? data : {};
  const detail = isJsonObject(root.detail) ? root.detail : undefined;
  const envelope = apiErrorEnvelope(data);
  return (
    stringFromJson(envelope.code) ||
    stringFromJson(detail?.code) ||
    stringFromJson(root.code) ||
    fallback
  );
}

function apiErrorDetails(data: unknown): unknown {
  const root = isJsonObject(data) ? data : {};
  const detail = isJsonObject(root.detail) ? root.detail : undefined;
  const envelope = apiErrorEnvelope(data);
  return envelope.details ?? detail?.details ?? root.details;
}

function validationDetailsMessage(details: unknown): string {
  if (!Array.isArray(details)) return "";
  const messages = details
    .map((entry) => {
      if (!isJsonObject(entry)) return "";
      const loc = Array.isArray(entry.loc)
        ? entry.loc.filter((part) => part !== "body" && part !== "query").map(String).join(".")
        : "";
      const msg = stringFromJson(entry.msg) || stringFromJson(entry.message) || "Dữ liệu không hợp lệ";
      return loc ? `${loc}: ${msg}` : msg;
    })
    .filter(Boolean);
  return messages.join("; ");
}

function normalizeApiErrorMessage(response: Response, data: unknown): string {
  const root = isJsonObject(data) ? data : {};
  const detail = isJsonObject(root.detail) ? root.detail : undefined;
  const errorEnvelope = isJsonObject(root.error) ? root.error : undefined;
  const details = errorEnvelope?.details ?? detail?.details ?? root.details;
  const rawMessage =
    detail?.message ||
    errorEnvelope?.message ||
    root.detail ||
    root.message ||
    response.statusText;
  const code =
    stringFromJson(errorEnvelope?.code) ||
    stringFromJson(detail?.code) ||
    stringFromJson(root.code) ||
    "";
  const mapOne = (item: JsonValue | undefined): string => {
    if (!item) return "Dữ liệu không hợp lệ";
    if (typeof item === "string") return item;
    if (isJsonObject(item))
      return (
        stringFromJson(item.msg) ||
        stringFromJson(item.message) ||
        stringFromJson(item.detail) ||
        "Dữ liệu không hợp lệ"
      );
    return "Dữ liệu không hợp lệ";
  };
  let message = "";
  if (typeof rawMessage === "string") message = rawMessage;
  else if (Array.isArray(rawMessage))
    message = rawMessage.map((item) => mapOne(item)).join("; ");
  else if (isJsonObject(rawMessage)) message = mapOne(rawMessage);
  else message = "Có lỗi xảy ra từ máy chủ. Vui lòng thử lại.";

  const validationMessage = validationDetailsMessage(details);
  if (validationMessage && (response.status === 400 || response.status === 422)) {
    message = message && message !== "Request validation failed"
      ? `${message}: ${validationMessage}`
      : validationMessage;
  }

  const lower = message.toLowerCase();
  if (response.status === 413 || lower.includes("file quá lớn")) {
    return "File quá lớn. Vui lòng giảm dung lượng file hoặc chia nhỏ tài liệu rồi upload lại.";
  }
  if (
    lower.includes("office cũ") ||
    lower.includes("legacy") ||
    lower.includes(".doc") ||
    lower.includes(".xls")
  ) {
    return message;
  }
  if (
    lower.includes("unsupported") ||
    lower.includes("not supported") ||
    lower.includes("không hỗ trợ") ||
    lower.includes("chưa được hỗ trợ")
  ) {
    return message.startsWith("Định dạng file")
      ? message
      : `Định dạng file không hỗ trợ. ${message}`;
  }
  return code ? `${message} [${code}]` : message;
}

export async function parseResponse<T>(response: Response): Promise<T> {
  const requestId = response.headers.get("X-Request-ID") || undefined;
  const text = await response.text();
  let data: unknown = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch (error) {
    throw new ApiRequestError(
      response.ok
        ? "Phản hồi máy chủ không đúng định dạng JSON."
        : `Máy chủ trả lỗi ${response.status}. Vui lòng thử lại hoặc kiểm tra backend/proxy.`,
      { code: "INVALID_API_RESPONSE", status: response.status, requestId, cause: error },
    );
  }
  if (!response.ok) {
    throw new ApiRequestError(normalizeApiErrorMessage(response, data), {
      code: apiErrorCode(data, `HTTP_${response.status}`),
      status: response.status,
      requestId,
      details: apiErrorDetails(data),
    });
  }
  return data as T;
}

export async function getBankOperationJobs(
  headers: HeadersInit,
  filters: {
    status?: string;
    operationType?: string;
    targetType?: string;
    targetId?: string;
    page?: number;
    pageSize?: number;
  } = {},
): Promise<PaginatedResponse<BankOperationJob>> {
  const params = new URLSearchParams();
  if (filters.status && filters.status !== "all")
    params.set("status_filter", filters.status);
  if (filters.operationType && filters.operationType !== "all")
    params.set("operation_type", filters.operationType);
  if (filters.targetType && filters.targetType !== "all")
    params.set("target_type", filters.targetType);
  if (filters.targetId) params.set("target_id", filters.targetId);
  params.set("page", String(filters.page || 1));
  params.set("page_size", String(filters.pageSize || 30));
  return parseResponse<PaginatedResponse<BankOperationJob>>(
    await apiFetch(
      `${API}/question-bank-v2/operation-jobs?${params.toString()}`,
      { credentials: "include", headers },
    ),
  );
}

export async function getBankOperationJob(headers: HeadersInit, jobId: string) {
  return parseResponse<BankOperationJob>(
    await apiFetch(
      `${API}/question-bank-v2/operation-jobs/${encodeURIComponent(jobId)}`,
      { credentials: "include", headers },
    ),
  );
}

export async function retryBankOperationJob(
  headers: HeadersInit,
  jobId: string,
): Promise<BankOperationJob> {
  return parseResponse<BankOperationJob>(
    await apiFetch(
      `${API}/question-bank-v2/operation-jobs/${encodeURIComponent(jobId)}/retry`,
      { method: "POST", credentials: "include", headers },
    ),
  );
}

export async function waitForBankOperationJob(
  headers: HeadersInit,
  jobId: string,
  options: {
    timeoutMs?: number;
    initialIntervalMs?: number;
    maxIntervalMs?: number;
    backoffMultiplier?: number;
    signal?: AbortSignal;
  } = {},
) {
  const timeoutMs = options.timeoutMs ?? 10 * 60 * 1000;
  const initialIntervalMs = Math.max(750, options.initialIntervalMs ?? 1_500);
  const maxIntervalMs = Math.max(initialIntervalMs, options.maxIntervalMs ?? 10_000);
  const multiplier = Math.max(1.1, options.backoffMultiplier ?? 1.7);
  const start = Date.now();
  let intervalMs = initialIntervalMs;
  let last: BankOperationJob | null = null;
  while (Date.now() - start < timeoutMs) {
    if (options.signal?.aborted) throw options.signal.reason || new DOMException("Aborted", "AbortError");
    last = await parseResponse<BankOperationJob>(
      await apiFetch(
        `${API}/question-bank-v2/operation-jobs/${encodeURIComponent(jobId)}`,
        { credentials: "include", headers, signal: options.signal, retries: 1 },
      ),
    );
    if (["completed", "failed", "canceled"].includes(last.status)) {
      if (last.status === "completed") return last;
      const result = (last.result || {}) as Record<string, unknown>;
      const userMessage = typeof result.user_message === "string" ? result.user_message : "";
      const suggestion = typeof result.suggestion === "string" ? result.suggestion : "";
      const baseMessage = userMessage || last.error_message || last.progress_label || `Job ${last.status}`;
      throw new Error(suggestion ? `${baseMessage} ${suggestion}` : baseMessage);
    }
    await sleepWithSignal(intervalMs, options.signal);
    intervalMs = Math.min(maxIntervalMs, Math.round(intervalMs * multiplier));
  }
  throw new Error(
    last?.progress_label
      ? `Job vẫn đang chạy: ${last.progress_label}`
      : "Job quá thời gian chờ. Vào Tiến trình job để kiểm tra tiếp.",
  );
}

async function enqueueAndWait<T>(
  headers: HeadersInit,
  queued: BankOperationJobQueued,
  timeoutMs?: number,
): Promise<T> {
  const job = await waitForBankOperationJob(headers, queued.job.id, {
    timeoutMs,
  });
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

async function parsePage<T>(response: Response): Promise<PaginatedResponse<T>> {
  const data = await parseResponse<T[] | PaginatedResponse<T>>(response);
  if (Array.isArray(data)) {
    return {
      items: data,
      total: data.length,
      page: 1,
      page_size: data.length,
      total_pages: 1,
      has_next: false,
    };
  }
  return data;
}

async function parsePageItems<T>(response: Response): Promise<T[]> {
  return unwrapPage<T>(
    await parseResponse<T[] | PaginatedResponse<T>>(response),
  );
}

async function fetchAllPageItems<T>(
  buildUrl: (page: number) => string,
  init: ApiFetchInit,
  options: { maxPages?: number; maxItems?: number; concurrency?: number } = {},
): Promise<T[]> {
  const maxPages = Math.max(1, options.maxPages || 50);
  const maxItems = Math.max(100, options.maxItems || 5_000);
  const concurrency = Math.max(1, Math.min(6, options.concurrency || 4));
  const first = await parsePage<T>(await apiFetch(buildUrl(1), init));
  const totalPages = Math.min(maxPages, Math.max(1, first.total_pages || 1));
  if ((first.total || 0) > maxItems || totalPages > maxPages) {
    throw new ApiRequestError(
      `Danh mục có ${first.total || 0} bản ghi, vượt giới hạn tải toàn bộ ${maxItems}. Hãy dùng tìm kiếm phía máy chủ.`,
      { code: "CATALOG_REQUIRES_SERVER_SEARCH" },
    );
  }
  const pages = new Map<number, T[]>();
  pages.set(1, first.items || []);
  for (let start = 2; start <= totalPages; start += concurrency) {
    const batch = Array.from(
      { length: Math.min(concurrency, totalPages - start + 1) },
      (_, index) => start + index,
    );
    const results = await Promise.all(
      batch.map(async (page) => ({
        page,
        data: await parsePage<T>(await apiFetch(buildUrl(page), init)),
      })),
    );
    results.forEach(({ page, data }) => pages.set(page, data.items || []));
  }
  return Array.from({ length: totalPages }, (_, index) => pages.get(index + 1) || []).flat();
}

async function parseCursorPageItems<T>(response: Response): Promise<T[]> {
  return unwrapCursorPage<T>(
    await parseResponse<T[] | CursorPaginatedResponse<T>>(response),
  );
}

export async function getAnalytics(
  courseId: string,
  headers: HeadersInit,
): Promise<AnalyticsOverview> {
  return parseResponse(
    await apiFetch(
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
    await apiFetch(
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
    await apiFetch(`${API}/jobs?course_id=${encodeURIComponent(courseId)}`, {
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
    await apiFetch(
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
    await apiFetch(`${API}/question-bank/page?${params.toString()}`, {
      credentials: "include",
      headers,
    }),
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
    await apiFetch(`${API}/courses?${params.toString()}`, {
      credentials: "include",
      headers,
    }),
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
    await apiFetch(
      `${API}/courses/${encodeURIComponent(courseId)}/concepts?${params.toString()}`,
      { credentials: "include", headers },
    ),
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
    await apiFetch(
      `${API}/courses/${encodeURIComponent(courseId)}/concepts/extract`,
      {
        method: "POST",
        headers,
        body: JSON.stringify({
          node_id: nodeId && nodeId !== "all" ? nodeId : null,
          force,
          max_concepts: maxConcepts,
        }),
      },
    ),
  );
}

export async function syncCourse(courseId: string, headers: HeadersInit) {
  return parseResponse(
    await apiFetch(`${API}/courses/sync`, {
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
    await apiFetch(
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
    await apiFetch(
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
    await apiFetch(
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
    await apiFetch(`${API}/courses/${encodeURIComponent(courseId)}/tree`, {
      headers,
    }),
  );
}

export async function getCourseNodes(
  courseId: string,
  headers: HeadersInit,
): Promise<CourseNodeOption[]> {
  return parseResponse(
    await apiFetch(`${API}/courses/${encodeURIComponent(courseId)}/nodes`, {
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
    await apiFetch(
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
    await apiFetch(
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
    await apiFetch(`${API}/cost/estimate`, {
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
    await apiFetch(`${API}/questions/generate`, {
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
    await apiFetch(`${API}/question-bank/${id}`, {
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
    await apiFetch(`${API}/question-bank/${id}/${action}`, {
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
    await apiFetch(`${API}/question-bank/${id}/status`, {
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
    await apiFetch(`${API}/question-bank/${id}`, {
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
    await apiFetch(`${API}/question-bank/${id}/repair`, {
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
    await apiFetch(`${API}/question-bank/${id}/keep-anyway`, {
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
    await apiFetch(
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
    await apiFetch(
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
    await apiFetch(`${API}/settings/openedx/test${suffix}`, {
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
    await apiFetch(`${API}/question-bank/bulk/approve`, {
      method: "POST",
      headers,
      body: JSON.stringify(payload),
    }),
  );
}

export async function getQuestionOlx(id: string, headers: HeadersInit) {
  return parseResponse<{ question_id: string; olx: string }>(
    await apiFetch(`${API}/question-bank/${id}/openedx-olx`, {
      credentials: "include",
      headers,
    }),
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
    await apiFetch(
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
  const response = await apiFetch(
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
    await apiFetch(
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
    await apiFetch(
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
    await apiFetch(
      `${API}/publish/courses/${encodeURIComponent(courseId)}/openedx/history`,
      { credentials: "include", headers },
    ),
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
    await apiFetch(
      `${API}/publish/batches/${encodeURIComponent(batchId)}/rollback?${params.toString()}`,
      {
        method: "POST",
        headers: withIdempotency(headers, idempotencyKey),
      },
    ),
  );
}

export async function getQuestionSourceTrace(
  questionId: string,
  headers: HeadersInit,
): Promise<SourceTrace> {
  return parseResponse(
    await apiFetch(
      `${API}/question-bank/${encodeURIComponent(questionId)}/source-trace`,
      { credentials: "include", headers },
    ),
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
    await apiFetch(`${API}/users/analytics?${params.toString()}`, {
      credentials: "include",
      headers,
    }),
  );
}

export async function getRuntimeSettings(
  headers: HeadersInit,
): Promise<RuntimeSettings> {
  return parseResponse(
    await apiFetch(`${API}/settings/runtime`, {
      credentials: "include",
      headers,
    }),
  );
}

export async function updateRuntimeSettings(
  payload: RuntimeSettingsUpdate,
  headers: HeadersInit,
): Promise<RuntimeSettings> {
  return parseResponse(
    await apiFetch(`${API}/settings/runtime`, {
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
    await apiFetch(`${API}/cost/pricing/realtime?${params.toString()}`, {
      headers,
    }),
  );
}

export async function testModelGateway(headers: HeadersInit): Promise<{
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
    await apiFetch(`${API}/settings/runtime/test-model`, {
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
    await apiFetch(
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
    await apiFetch(`${API}/cost/policy`, {
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
    search?: string;
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
  if (query.search?.trim()) params.set("search", query.search.trim());
  params.set("page", String(query.page || 1));
  params.set("page_size", String(query.pageSize || 20));
  return parseResponse(
    await apiFetch(`${API}/audit?${params.toString()}`, {
      credentials: "include",
      headers,
    }),
  );
}

export async function downloadAuditLogsCsv(
  query: { status?: string; errorType?: string; actorId?: string; search?: string } = {},
  headers: HeadersInit,
): Promise<Blob> {
  const params = new URLSearchParams();
  if (query.status && query.status !== "all") params.set("status", query.status);
  if (query.errorType && query.errorType !== "all") params.set("error_type", query.errorType);
  if (query.actorId?.trim()) params.set("actor_id", query.actorId.trim());
  if (query.search?.trim()) params.set("search", query.search.trim());
  const response = await apiFetch(`${API}/audit/export.csv?${params.toString()}`, { credentials: "include", headers });
  if (!response.ok) throw new Error(await response.text() || response.statusText);
  return response.blob();
}

export type OpenEdxSessionExchangeResponse = {
  access_token?: string;
  token_type: string;
  expires_in: number;
  user_id: string;
  email?: string | null;
  role: "admin" | "teacher" | "reviewer" | "viewer";
  course_ids: string[];
  username?: string | null;
  name?: string | null;
};

export async function exchangeOpenEdxSessionTicket(
  ticket: string,
): Promise<OpenEdxSessionExchangeResponse> {
  return parseResponse(
    await apiFetch(`${API}/auth/openedx-session/exchange`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify({ ticket }),
    }),
  );
}


export async function logoutAuthSession() {
  return parseResponse(
    await apiFetch(`${API}/auth/logout`, {
      method: "POST",
      credentials: "include",
    }),
  );
}

const CMS_BRIDGE_STARTED_AT_KEY = "ai_openedx_cms_bridge_started_at";
const CMS_POST_AUTH_RETURN_TO_KEY = "ai_openedx_post_auth_return_to";

export function normalizeInternalReturnPath(value?: string | null, fallback = "/bank"): string {
  const candidate = String(value || "").trim();
  if (!candidate.startsWith("/") || candidate.startsWith("//") || candidate.startsWith("/auth/")) return fallback;
  return candidate;
}

export function rememberCmsPostAuthReturnPath(value?: string | null): string {
  const target = normalizeInternalReturnPath(value);
  if (typeof window !== "undefined") window.sessionStorage.setItem(CMS_POST_AUTH_RETURN_TO_KEY, target);
  return target;
}

export function consumeCmsPostAuthReturnPath(fallback = "/bank"): string {
  if (typeof window === "undefined") return fallback;
  const target = normalizeInternalReturnPath(window.sessionStorage.getItem(CMS_POST_AUTH_RETURN_TO_KEY), fallback);
  window.sessionStorage.removeItem(CMS_POST_AUTH_RETURN_TO_KEY);
  return target;
}

export function markCmsSessionBridgeStarted(): void {
  if (typeof window !== "undefined") window.sessionStorage.setItem(CMS_BRIDGE_STARTED_AT_KEY, String(Date.now()));
}

export function clearCmsSessionBridgeAttempt(): void {
  if (typeof window === "undefined") return;
  window.sessionStorage.removeItem(CMS_BRIDGE_STARTED_AT_KEY);
}

export function buildCmsSessionBridgeUrl(courseId?: string, returnPath?: string) {
  const cmsBase = (
    process.env.NEXT_PUBLIC_OPENEDX_CMS_BASE_URL ||
    process.env.NEXT_PUBLIC_CMS_BASE_URL ||
    ""
  ).replace(/\/+$/, "");
  if (!cmsBase)
    throw new Error(
      "NEXT_PUBLIC_OPENEDX_CMS_BASE_URL chưa được cấu hình cho frontend.",
    );

  const target = rememberCmsPostAuthReturnPath(returnPath || `${window.location.pathname}${window.location.search}`);
  const callback = new URL("/auth/cms-callback", window.location.origin);
  callback.searchParams.set("next", target);

  const params = new URLSearchParams();
  params.set("return_to", callback.toString());
  if (courseId) params.set("course_id", courseId);
  params.set("state", Math.random().toString(36).slice(2));
  return `${cmsBase}/api/ai-connector/v1/session/bridge?${params.toString()}`;
}

export async function previewFamilyBankPlan(
  courseId: string,
  payload: {
    chapter_node_id?: string | null;
    total_questions: number;
    difficulty_distribution?: {
      easy?: number;
      medium?: number;
      hard?: number;
      EASY?: number;
      MEDIUM?: number;
      HARD?: number;
    };
    require_all_approved?: boolean;
    shortage_policy?: string;
    max_families_per_bank?: number;
  },
  headers: HeadersInit,
) {
  return parseResponse(
    await apiFetch(
      `${API}/publish/courses/${encodeURIComponent(courseId)}/family-bank-plan/preview`,
      {
        method: "POST",
        headers,
        body: JSON.stringify(payload),
      },
    ),
  );
}

export async function publishFamilyBankPlan(
  courseId: string,
  plan: JsonObject,
  headers: HeadersInit,
  mode: "publish_new" | "replace" | "delete_reimport" = "publish_new",
  idempotencyKey?: string,
) {
  return parseResponse(
    await apiFetch(
      `${API}/publish/courses/${encodeURIComponent(courseId)}/family-bank-plan/publish`,
      {
        method: "POST",
        headers: withIdempotency(headers, idempotencyKey),
        body: JSON.stringify({ plan, mode }),
      },
    ),
  );
}

export async function createCmsQuizNode(
  courseId: string,
  payload: {
    parent_node_id: string;
    quiz_title: string;
    unit_title: string;
    plan?: JsonObject;
  },
  headers: HeadersInit,
  idempotencyKey?: string,
) {
  return parseResponse(
    await apiFetch(
      `${API}/publish/courses/${encodeURIComponent(courseId)}/cms-quiz-node/create`,
      {
        method: "POST",
        headers: withIdempotency(headers, idempotencyKey),
        body: JSON.stringify(payload),
      },
    ),
  );
}

export async function insertCmsProblemBanks(
  courseId: string,
  payload: {
    unit_node_id: string;
    plan: JsonObject;
    strict_component_selection?: boolean;
  },
  headers: HeadersInit,
  idempotencyKey?: string,
) {
  return parseResponse(
    await apiFetch(
      `${API}/publish/courses/${encodeURIComponent(courseId)}/cms-problem-banks/insert`,
      {
        method: "POST",
        headers: withIdempotency(headers, idempotencyKey),
        body: JSON.stringify(payload),
      },
    ),
  );
}


export async function getBankCostAnalytics(
  headers: HeadersInit,
  filters: {
    dateRange?: string;
    fromDate?: string;
    toDate?: string;
    q?: string;
    page?: number;
    pageSize?: number;
    sortBy?: string;
    sortDir?: 'asc' | 'desc';
  } = {},
) {
  const params = new URLSearchParams();
  params.set('date_range', filters.dateRange || '30d');
  if (filters.fromDate) params.set('from_date', filters.fromDate);
  if (filters.toDate) params.set('to_date', filters.toDate);
  if (filters.q?.trim()) params.set('q', filters.q.trim());
  params.set('page', String(filters.page || 1));
  params.set('page_size', String(filters.pageSize || 20));
  params.set('sort_by', filters.sortBy || 'cost_vnd');
  params.set('sort_dir', filters.sortDir || 'desc');
  return parseResponse<BankCostAnalytics>(
    await apiFetch(`${API}/question-bank-v2/dashboard/cost-analytics?${params.toString()}`, {
      credentials: 'include',
      headers,
    }),
  );
}

export async function getBankDashboardAnalytics(
  headers: HeadersInit,
  filters: { dateRange?: string; fromDate?: string; toDate?: string } = {},
) {
  const params = new URLSearchParams();
  params.set("date_range", filters.dateRange || "30d");
  if (filters.fromDate) params.set("from_date", filters.fromDate);
  if (filters.toDate) params.set("to_date", filters.toDate);
  return parseResponse<DashboardAnalytics>(
    await apiFetch(
      `${API}/question-bank-v2/dashboard/analytics?${params.toString()}`,
      { credentials: "include", headers },
    ),
  );
}

export async function getBankDashboardDrilldown(
  headers: HeadersInit,
  filters: {
    entity?: string;
    q?: string;
    status?: string;
    difficulty?: string;
    questionType?: string;
    createdFrom?: string;
    createdTo?: string;
    questionId?: string;
    chapterId?: string;
    subjectId?: string;
    limit?: number;
  } = {},
) {
  const params = new URLSearchParams();
  params.set("entity", filters.entity || "questions");
  if (filters.q) params.set("q", filters.q);
  if (filters.status) params.set("status", filters.status);
  if (filters.difficulty) params.set("difficulty", filters.difficulty);
  if (filters.questionType) params.set("question_type", filters.questionType);
  if (filters.createdFrom) params.set("created_from", filters.createdFrom);
  if (filters.createdTo) params.set("created_to", filters.createdTo);
  if (filters.questionId) params.set("question_id", filters.questionId);
  if (filters.chapterId) params.set("chapter_id", filters.chapterId);
  if (filters.subjectId) params.set("subject_id", filters.subjectId);
  params.set("limit", String(filters.limit || 100));
  return parseResponse<BankDashboardDrilldownResponse>(
    await apiFetch(
      `${API}/question-bank-v2/dashboard/drilldown?${params.toString()}`,
      { credentials: "include", headers },
    ),
  );
}

export async function getBankDashboardOverview(headers: HeadersInit) {
  return parseResponse<BankDashboardOverview>(
    await apiFetch(`${API}/question-bank-v2/dashboard/overview`, {
      credentials: "include",
      headers,
    }),
  );
}

export async function searchBankDashboard(
  headers: HeadersInit,
  q: string,
  limit = 20,
) {
  const params = new URLSearchParams();
  params.set("q", q);
  params.set("limit", String(limit));
  params.set("include_questions", "true");
  const payload = await parseResponse<
    BankSearchResult[] | BankSearchGroupedResponse
  >(
    await apiFetch(`${API}/question-bank-v2/search?${params.toString()}`, {
      credentials: "include",
      headers,
    }),
  );
  if (Array.isArray(payload)) return payload;
  if (Array.isArray(payload.items) && payload.items.length)
    return payload.items;
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
    await apiFetch(
      `${API}/question-bank-v2/departments/summary?_=${Date.now()}`,
      { credentials: "include", headers, cache: "no-store" },
    ),
  );
}

export async function getSubjectSummaries(
  headers: HeadersInit,
  departmentId: string,
) {
  return parseResponse<SubjectSummary[]>(
    await apiFetch(
      `${API}/question-bank-v2/departments/${encodeURIComponent(departmentId)}/subjects/summary?_=${Date.now()}`,
      { credentials: "include", headers, cache: "no-store" },
    ),
  );
}

export async function getSubjectVersionSummaries(
  headers: HeadersInit,
  subjectId: string,
) {
  return parseResponse<SubjectVersionSummary[]>(
    await apiFetch(
      `${API}/question-bank-v2/subjects/${encodeURIComponent(subjectId)}/versions/summary?_=${Date.now()}`,
      { credentials: "include", headers, cache: "no-store" },
    ),
  );
}

export async function getChapterSummaries(
  headers: HeadersInit,
  subjectOfferingId: string,
) {
  return parseResponse<ChapterSummary[]>(
    await apiFetch(
      `${API}/question-bank-v2/subject-versions/${encodeURIComponent(subjectOfferingId)}/chapters/summary?_=${Date.now()}`,
      { credentials: "include", headers, cache: "no-store" },
    ),
  );
}

export async function getBankSummary(headers: HeadersInit) {
  return parseResponse<BankSummary>(
    await apiFetch(`${API}/question-bank-v2/summary`, {
      credentials: "include",
      headers,
    }),
  );
}

export async function searchDepartments(
  headers: HeadersInit,
  query = "",
  signal?: AbortSignal,
): Promise<Department[]> {
  const params = new URLSearchParams({ page: "1", page_size: "50" });
  if (query.trim()) params.set("q", query.trim());
  return parsePageItems<Department>(
    await apiFetch(`${API}/question-bank-v2/departments?${params.toString()}`, {
      credentials: "include", headers, signal, retries: 1,
    }),
  );
}

export async function previewLegacyQuizCmsOldImport(
  headers: HeadersInit,
  workbooks: File[],
  assets: File[] = [],
): Promise<LegacyQuizCmsOldImportPreview> {
  const body = new FormData();
  workbooks.forEach((file) => body.append("workbooks", file));
  assets.forEach((file) => body.append("assets", file));
  return parseResponse<LegacyQuizCmsOldImportPreview>(
    await apiFetch(`${API}/question-bank-v2/import-quiz-cms-old/preview`, {
      method: "POST",
      credentials: "include",
      headers: withoutContentType(headers),
      body,
      timeoutMs: 180_000,
    }),
  );
}

export async function enqueueLegacyQuizCmsOldImport(
  headers: HeadersInit,
  previewToken: string,
): Promise<BankOperationJobQueued> {
  return parseResponse<BankOperationJobQueued>(
    await apiFetch(`${API}/question-bank-v2/import-quiz-cms-old/jobs`, {
      method: "POST",
      credentials: "include",
      headers: { ...headers, "Content-Type": "application/json" },
      body: JSON.stringify({ preview_token: previewToken }),
      timeoutMs: 60_000,
    }),
  );
}

export async function searchSubjects(
  headers: HeadersInit,
  options: { query?: string; departmentId?: string; signal?: AbortSignal } = {},
): Promise<Subject[]> {
  const params = new URLSearchParams({ page: "1", page_size: "100" });
  if (options.query?.trim()) params.set("q", options.query.trim());
  if (options.departmentId) params.set("department_id", options.departmentId);
  return parsePageItems<Subject>(
    await apiFetch(`${API}/question-bank-v2/subjects?${params.toString()}`, {
      credentials: "include", headers, signal: options.signal, retries: 1,
    }),
  );
}

export async function searchSubjectOfferings(
  headers: HeadersInit,
  options: { query?: string; subjectId?: string; signal?: AbortSignal } = {},
): Promise<SubjectOffering[]> {
  const params = new URLSearchParams({ page: "1", page_size: "100" });
  if (options.query?.trim()) params.set("q", options.query.trim());
  if (options.subjectId) params.set("subject_id", options.subjectId);
  return parsePageItems<SubjectOffering>(
    await apiFetch(`${API}/question-bank-v2/subject-versions?${params.toString()}`, {
      credentials: "include", headers, signal: options.signal, retries: 1,
    }),
  );
}

export async function searchSubjectChapters(
  headers: HeadersInit,
  options: { query?: string; subjectId?: string; subjectOfferingId?: string; signal?: AbortSignal } = {},
): Promise<SubjectChapter[]> {
  const params = new URLSearchParams({ page: "1", page_size: "100" });
  if (options.query?.trim()) params.set("q", options.query.trim());
  if (options.subjectId) params.set("subject_id", options.subjectId);
  if (options.subjectOfferingId) params.set("subject_offering_id", options.subjectOfferingId);
  return parsePageItems<SubjectChapter>(
    await apiFetch(`${API}/question-bank-v2/chapters?${params.toString()}`, {
      credentials: "include", headers, signal: options.signal, retries: 1,
    }),
  );
}

export async function getDepartments(headers: HeadersInit) {
  return fetchAllPageItems<Department>(
    (page) => `${API}/question-bank-v2/departments?page=${page}&page_size=50`,
    { credentials: "include", headers },
    { maxPages: 20 },
  );
}

export async function getDepartment(headers: HeadersInit, id: string) {
  return parseResponse<Department>(
    await apiFetch(
      `${API}/question-bank-v2/departments/${encodeURIComponent(id)}`,
      { credentials: "include", headers },
    ),
  );
}

export async function createDepartment(
  headers: HeadersInit,
  payload: { code: string; name: string; description?: string },
) {
  return parseResponse<Department>(
    await apiFetch(`${API}/question-bank-v2/departments`, {
      method: "POST",
      headers,
      body: JSON.stringify(payload),
    }),
  );
}

export async function updateDepartment(
  headers: HeadersInit,
  id: string,
  payload: { code?: string; name?: string; description?: string },
) {
  return parseResponse<Department>(
    await apiFetch(
      `${API}/question-bank-v2/departments/${encodeURIComponent(id)}`,
      { method: "PATCH", headers, body: JSON.stringify(payload) },
    ),
  );
}

export async function deleteDepartment(headers: HeadersInit, id: string) {
  return parseResponse<{ ok: boolean; deleted: boolean; message: string }>(
    await apiFetch(
      `${API}/question-bank-v2/departments/${encodeURIComponent(id)}`,
      { method: "DELETE", headers },
    ),
  );
}

export async function getSubjects(headers: HeadersInit, departmentId?: string) {
  return fetchAllPageItems<Subject>(
    (page) => {
      const params = new URLSearchParams();
      if (departmentId) params.set("department_id", departmentId);
      params.set("page", String(page));
      params.set("page_size", "100");
      return `${API}/question-bank-v2/subjects?${params.toString()}`;
    },
    { credentials: "include", headers },
    { maxPages: departmentId ? 50 : 20 },
  );
}

export async function getSubject(headers: HeadersInit, id: string) {
  return parseResponse<Subject>(
    await apiFetch(
      `${API}/question-bank-v2/subjects/${encodeURIComponent(id)}`,
      { credentials: "include", headers },
    ),
  );
}

export async function createSubject(
  headers: HeadersInit,
  payload: {
    department_id: string;
    code: string;
    name: string;
    description?: string;
  },
) {
  return parseResponse<Subject>(
    await apiFetch(`${API}/question-bank-v2/subjects`, {
      method: "POST",
      headers,
      body: JSON.stringify(payload),
    }),
  );
}

export async function updateSubject(
  headers: HeadersInit,
  id: string,
  payload: { code?: string; name?: string; description?: string },
) {
  return parseResponse<Subject>(
    await apiFetch(
      `${API}/question-bank-v2/subjects/${encodeURIComponent(id)}`,
      { method: "PATCH", headers, body: JSON.stringify(payload) },
    ),
  );
}

export async function deleteSubject(headers: HeadersInit, id: string) {
  return parseResponse<{ ok: boolean; deleted: boolean; message: string }>(
    await apiFetch(
      `${API}/question-bank-v2/subjects/${encodeURIComponent(id)}`,
      { method: "DELETE", headers },
    ),
  );
}

export async function getSubjectOfferings(
  headers: HeadersInit,
  subjectId?: string,
) {
  return fetchAllPageItems<SubjectOffering>(
    (page) => {
      const params = new URLSearchParams();
      if (subjectId) params.set("subject_id", subjectId);
      params.set("page", String(page));
      params.set("page_size", "100");
      return `${API}/question-bank-v2/subject-versions?${params.toString()}`;
    },
    { credentials: "include", headers },
    { maxPages: subjectId ? 50 : 30 },
  );
}

export async function getSubjectOffering(headers: HeadersInit, id: string) {
  return parseResponse<SubjectOffering>(
    await apiFetch(
      `${API}/question-bank-v2/subject-versions/${encodeURIComponent(id)}`,
      { credentials: "include", headers },
    ),
  );
}

export async function createSubjectOffering(
  headers: HeadersInit,
  payload: {
    subject_id: string;
    code?: string;
    name?: string;
    term?: string | null;
    season?: string | null;
    year?: number | string | null;
    version_code?: string;
    based_on_offering_id?: string | null;
    clone_from_offering_id?: string | null;
    clone_chapters?: boolean;
    clone_materials?: boolean;
    clone_questions?: boolean;
    description?: string;
  },
) {
  return parseResponse<SubjectOffering>(
    await apiFetch(`${API}/question-bank-v2/subject-versions`, {
      method: "POST",
      headers,
      body: JSON.stringify(payload),
    }),
  );
}

export async function updateSubjectOffering(
  headers: HeadersInit,
  id: string,
  payload: {
    code?: string;
    name?: string;
    term?: string | null;
    version_code?: string;
    description?: string;
  },
) {
  return parseResponse<SubjectOffering>(
    await apiFetch(
      `${API}/question-bank-v2/subject-versions/${encodeURIComponent(id)}`,
      { method: "PATCH", headers, body: JSON.stringify(payload) },
    ),
  );
}

export async function deleteSubjectOffering(headers: HeadersInit, id: string) {
  return parseResponse<{ ok: boolean; deleted: boolean; message: string }>(
    await apiFetch(
      `${API}/question-bank-v2/subject-versions/${encodeURIComponent(id)}`,
      { method: "DELETE", headers },
    ),
  );
}

export async function getSubjectChapters(
  headers: HeadersInit,
  subjectId?: string,
  subjectOfferingId?: string,
) {
  return fetchAllPageItems<SubjectChapter>(
    (page) => {
      const params = new URLSearchParams();
      if (subjectId) params.set("subject_id", subjectId);
      if (subjectOfferingId)
        params.set("subject_offering_id", subjectOfferingId);
      params.set("page", String(page));
      params.set("page_size", "100");
      return `${API}/question-bank-v2/chapters?${params.toString()}`;
    },
    { credentials: "include", headers },
    { maxPages: subjectOfferingId ? 50 : 250 },
  );
}

export async function getSubjectChapter(headers: HeadersInit, id: string) {
  return parseResponse<SubjectChapter>(
    await apiFetch(
      `${API}/question-bank-v2/chapters/${encodeURIComponent(id)}`,
      { credentials: "include", headers },
    ),
  );
}

export async function createSubjectChapter(
  headers: HeadersInit,
  payload: {
    subject_id: string;
    subject_offering_id?: string | null;
    chapter_no?: number;
    title: string;
    description?: string;
    sort_order?: number;
  },
) {
  return parseResponse<SubjectChapter>(
    await apiFetch(`${API}/question-bank-v2/chapters`, {
      method: "POST",
      headers,
      body: JSON.stringify(payload),
    }),
  );
}

export async function updateSubjectChapter(
  headers: HeadersInit,
  id: string,
  payload: { title?: string; description?: string; sort_order?: number },
) {
  return parseResponse<SubjectChapter>(
    await apiFetch(
      `${API}/question-bank-v2/chapters/${encodeURIComponent(id)}`,
      { method: "PATCH", headers, body: JSON.stringify(payload) },
    ),
  );
}

export async function deleteSubjectChapter(headers: HeadersInit, id: string) {
  return parseResponse<{ ok: boolean; deleted: boolean; message: string }>(
    await apiFetch(
      `${API}/question-bank-v2/chapters/${encodeURIComponent(id)}`,
      { method: "DELETE", headers },
    ),
  );
}

export async function getBankVersions(
  headers: HeadersInit,
  chapterId?: string,
  subjectId?: string,
  subjectOfferingId?: string,
) {
  const params = new URLSearchParams();
  if (chapterId) params.set("chapter_id", chapterId);
  if (subjectId) params.set("subject_id", subjectId);
  if (subjectOfferingId) params.set("subject_offering_id", subjectOfferingId);
  params.set("page_size", "100");
  return parsePageItems<BankVersion>(
    await apiFetch(
      `${API}/question-bank-v2/bank-versions?${params.toString()}`,
      { credentials: "include", headers },
    ),
  );
}

export async function createBankVersion(
  headers: HeadersInit,
  payload: {
    subject_id: string;
    chapter_id: string;
    subject_offering_id?: string | null;
    version_code: string;
    title?: string;
    change_note?: string;
    based_on_version_id?: string | null;
  },
) {
  return parseResponse<BankVersion>(
    await apiFetch(`${API}/question-bank-v2/bank-versions`, {
      method: "POST",
      headers,
      body: JSON.stringify(payload),
    }),
  );
}

export async function getBankReleases(
  headers: HeadersInit,
  bankVersionId?: string,
  chapterId?: string,
) {
  const params = new URLSearchParams();
  if (bankVersionId) params.set("bank_version_id", bankVersionId);
  if (chapterId) params.set("chapter_id", chapterId);
  params.set("page_size", "100");
  return parsePageItems<BankRelease>(
    await apiFetch(`${API}/question-bank-v2/releases?${params.toString()}`, {
      credentials: "include",
      headers,
    }),
  );
}

export async function createBankRelease(
  headers: HeadersInit,
  payload: {
    bank_version_id: string;
    release_code?: string;
    title?: string;
    include_approved_questions?: boolean;
  },
) {
  return parseResponse<BankRelease>(
    await apiFetch(`${API}/question-bank-v2/releases`, {
      method: "POST",
      headers,
      body: JSON.stringify(payload),
    }),
  );
}


export async function getBankReleasePreview(headers: HeadersInit, releaseId: string): Promise<BankReleasePreview> {
  return parseResponse<BankReleasePreview>(
    await apiFetch(`${API}/question-bank-v2/releases/${encodeURIComponent(releaseId)}/preview`, { credentials: "include", headers }),
  );
}

export async function getBankReleasePublishAudit(
  headers: HeadersInit,
  releaseId: string,
) {
  return parseResponse<BankReleasePublishAudit>(
    await apiFetch(
      `${API}/question-bank-v2/releases/${encodeURIComponent(releaseId)}/publish-audit`,
      { credentials: "include", headers },
    ),
  );
}

export async function enqueueBankReleasePublish(
  headers: HeadersInit,
  releaseId: string,
  payload: {
    openedx_course_id_for_org?: string | null;
    force_reimport?: boolean;
  } = {},
): Promise<BankOperationJobQueued> {
  return parseResponse<BankOperationJobQueued>(
    await apiFetch(
      `${API}/question-bank-v2/releases/${encodeURIComponent(releaseId)}/publish-openedx-job`,
      { method: "POST", headers, body: JSON.stringify(payload) },
    ),
  );
}

// Backward-compatible name: publishing is worker-only and never waits in the browser request.
export const publishBankRelease = enqueueBankReleasePublish;

export async function getCourseMappings(
  headers: HeadersInit,
  subjectId?: string,
) {
  const params = new URLSearchParams();
  if (subjectId) params.set("subject_id", subjectId);
  params.set("page_size", "100");
  return parsePageItems<EdxCourseMapping>(
    await apiFetch(
      `${API}/question-bank-v2/course-mappings?${params.toString()}`,
      { credentials: "include", headers },
    ),
  );
}

export async function validateCourseMapping(
  headers: HeadersInit,
  payload: {
    openedx_course_id: string;
    subject_id: string;
    department_id?: string | null;
    term?: string | null;
    openedx_course_title?: string | null;
  },
) {
  return parseResponse<MappingValidation>(
    await apiFetch(`${API}/question-bank-v2/course-mappings/validate`, {
      method: "POST",
      headers,
      body: JSON.stringify(payload),
    }),
  );
}

export async function createCourseMapping(
  headers: HeadersInit,
  payload: {
    openedx_course_id: string;
    subject_id: string;
    department_id?: string | null;
    term?: string | null;
    openedx_course_title?: string | null;
    allow_warnings?: boolean;
  },
) {
  return parseResponse<EdxCourseMapping>(
    await apiFetch(`${API}/question-bank-v2/course-mappings`, {
      method: "POST",
      headers,
      body: JSON.stringify(payload),
    }),
  );
}

export async function validateCourseChapterMapping(
  headers: HeadersInit,
  payload: {
    course_mapping_id: string;
    subject_chapter_id: string;
    bank_release_id: string;
    openedx_parent_node_id: string;
    openedx_node_title?: string | null;
  },
) {
  return parseResponse<MappingValidation>(
    await apiFetch(`${API}/question-bank-v2/course-chapter-mappings/validate`, {
      method: "POST",
      headers,
      body: JSON.stringify(payload),
    }),
  );
}

export async function createCourseChapterMapping(
  headers: HeadersInit,
  payload: {
    course_mapping_id: string;
    subject_chapter_id: string;
    bank_release_id?: string | null;
    openedx_parent_node_id?: string | null;
    openedx_node_title?: string | null;
    enabled?: boolean;
    allow_warnings?: boolean;
  },
) {
  return parseResponse<EdxCourseChapterMapping>(
    await apiFetch(`${API}/question-bank-v2/course-chapter-mappings`, {
      method: "POST",
      headers,
      body: JSON.stringify(payload),
    }),
  );
}

export async function getQuizBlueprints(
  headers: HeadersInit,
  chapterId?: string,
) {
  const params = new URLSearchParams();
  if (chapterId) params.set("chapter_id", chapterId);
  params.set("page_size", "100");
  return parsePageItems<QuizBlueprint>(
    await apiFetch(
      `${API}/question-bank-v2/quiz-blueprints?${params.toString()}`,
      { credentials: "include", headers },
    ),
  );
}

export async function createQuizBlueprint(
  headers: HeadersInit,
  payload: {
    subject_id: string;
    chapter_id: string;
    subject_offering_id?: string | null;
    title: string;
    total_questions: number;
    difficulty_easy: number;
    difficulty_medium: number;
    difficulty_hard: number;
    single_select_count?: number | null;
    multi_select_count?: number | null;
    text_input_count?: number | null;
    numerical_input_count?: number | null;
    max_families_per_bank?: number;
    pick_count_per_slot?: number;
  },
) {
  return parseResponse<QuizBlueprint>(
    await apiFetch(`${API}/question-bank-v2/quiz-blueprints`, {
      method: "POST",
      headers,
      body: JSON.stringify(payload),
    }),
  );
}

export async function getMaterialVersions(
  headers: HeadersInit,
  bankVersionId?: string,
) {
  const params = new URLSearchParams();
  if (bankVersionId) params.set("bank_version_id", bankVersionId);
  params.set("page_size", "100");
  return parsePageItems<MaterialVersion>(
    await apiFetch(
      `${API}/question-bank-v2/material-versions?${params.toString()}`,
      { credentials: "include", headers },
    ),
  );
}

export async function deleteMaterialVersion(
  headers: HeadersInit,
  materialVersionId: string,
) {
  return parseResponse<{
    ok: boolean;
    material_version_id: string;
    bank_version_id: string;
    chunks_deleted: number;
    detached_question_count: number;
    message: string;
  }>(
    await apiFetch(
      `${API}/question-bank-v2/material-versions/${encodeURIComponent(materialVersionId)}`,
      {
        method: "DELETE",
        headers,
      },
    ),
  );
}

function assertSupportedBankMaterialFile(file: File) {
  const name = (file.name || "").toLowerCase();
  const ext = name.includes(".") ? name.split(".").pop() || "" : "";
  const supported = new Set([
    "pdf",
    "docx",
    "pptx",
    "xlsx",
    "xlsm",
    "csv",
    "tsv",
    "txt",
    "md",
    "markdown",
    "html",
    "htm",
    "xml",
    "json",
    "srt",
    "vtt",
  ]);
  const legacy = new Set(["doc", "xls", "ppt"]);
  if (legacy.has(ext)) {
    throw new Error(
      `Định dạng file .${ext} là Office cũ. Vui lòng chuyển sang DOCX/XLSX/PPTX hoặc PDF rồi upload lại.`,
    );
  }
  if (ext && !supported.has(ext)) {
    throw new Error(
      `Định dạng file .${ext} chưa được hỗ trợ. Hệ thống hiện hỗ trợ: PDF, DOCX, PPTX, XLSX, CSV/TSV, TXT/MD, HTML, JSON/XML, SRT/VTT.`,
    );
  }
  if (!ext && !(file.type || "").toLowerCase().startsWith("text/")) {
    throw new Error(
      "Không xác định được định dạng file. Vui lòng upload tài liệu có đuôi file rõ ràng như PDF, DOCX, PPTX, XLSX, CSV hoặc TXT.",
    );
  }
}

export async function enqueueBankMaterialUpload(
  headers: HeadersInit,
  bankVersionId: string,
  file: File,
  payload: {
    title?: string;
    change_type?: string;
    replace_existing?: boolean;
  } = {},
) {
  assertSupportedBankMaterialFile(file);
  const form = new FormData();
  form.append("file", file);
  form.append("title", payload.title || file.name);
  form.append("change_type", payload.change_type || "initial");
  form.append("replace_existing", String(Boolean(payload.replace_existing)));
  return parseResponse<BankOperationJobQueued>(
    await apiFetch(
      `${API}/question-bank-v2/bank-versions/${encodeURIComponent(bankVersionId)}/materials/upload-job`,
      {
        method: "POST",
        headers: withoutContentType(headers),
        body: form,
      },
    ),
  );
}

export async function uploadBankMaterial(
  headers: HeadersInit,
  bankVersionId: string,
  file: File,
  payload: {
    title?: string;
    change_type?: string;
    replace_existing?: boolean;
  } = {},
) {
  const queued = await enqueueBankMaterialUpload(
    headers,
    bankVersionId,
    file,
    payload,
  );
  return enqueueAndWait<MaterialUploadResult>(headers, queued, 10 * 60 * 1000);
}

export async function getBankMaterialChunks(
  headers: HeadersInit,
  bankVersionId: string,
  materialVersionId?: string,
) {
  const params = new URLSearchParams();
  if (materialVersionId) params.set("material_version_id", materialVersionId);
  params.set("page_size", "100");
  return parsePageItems<MaterialChunk>(
    await apiFetch(
      `${API}/question-bank-v2/bank-versions/${encodeURIComponent(bankVersionId)}/material-chunks?${params.toString()}`,
      { credentials: "include", headers },
    ),
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
    question_type_single_select?: number;
    question_type_multi_select?: number;
    material_version_ids?: string[] | null;
  },
) {
  return parseResponse<BankGeneratePreview>(
    await apiFetch(
      `${API}/question-bank-v2/bank-versions/${encodeURIComponent(bankVersionId)}/generate/preview`,
      {
        method: "POST",
        headers,
        body: JSON.stringify(payload),
      },
    ),
  );
}

export async function enqueueGenerateFromBankVersion(
  headers: HeadersInit,
  bankVersionId: string,
  payload: {
    question_count: number;
    target_question_count?: number;
    difficulty_easy?: number;
    difficulty_medium?: number;
    difficulty_hard?: number;
    question_type_single_select?: number;
    question_type_multi_select?: number;
    material_version_ids?: string[] | null;
    provider?: string;
    approve_after_generate?: boolean;
  },
) {
  return parseResponse<BankOperationJobQueued>(
    await apiFetch(
      `${API}/question-bank-v2/bank-versions/${encodeURIComponent(bankVersionId)}/generate-job`,
      {
        method: "POST",
        headers,
        body: JSON.stringify(payload),
      },
    ),
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
    question_type_single_select?: number;
    question_type_multi_select?: number;
    material_version_ids?: string[] | null;
    provider?: string;
    approve_after_generate?: boolean;
  },
) {
  const queued = await enqueueGenerateFromBankVersion(
    headers,
    bankVersionId,
    payload,
  );
  return enqueueAndWait<BankGenerateResult>(headers, queued, 20 * 60 * 1000);
}

function bankQuestionListItemToQuestion(
  item: BankQuestionListItem,
): BankVersionQuestion {
  return {
    id: item.id,
    bank_version_id: item.bank_version_id,
    subject_id: item.subject_id,
    subject_chapter_id: item.subject_chapter_id,
    concept_title: item.concept_title,
    question_family_id: item.question_family_id,
    variant_no: item.variant_no,
    difficulty: item.difficulty,
    question_type: item.question_type,
    authoring_mode: item.authoring_mode,
    question_schema_version: item.question_schema_version,
    media_count: item.media_count,
    question_text: item.question_text_preview || "",
    option_a: item.option_a_preview || "",
    option_b: item.option_b_preview || "",
    option_c: item.option_c_preview || "",
    option_d: item.option_d_preview || "",
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


export async function getBankVersionQuestionOffsetPage(
  headers: HeadersInit,
  bankVersionId: string,
  options: {
    statusFilter?: string;
    difficulty?: string;
    search?: string;
    sort?: string;
    page?: number;
    pageSize?: number;
  } = {},
): Promise<PaginatedResponse<BankVersionQuestion>> {
  const params = new URLSearchParams();
  if (options.statusFilter && options.statusFilter !== "all") params.set("status_filter", options.statusFilter);
  if (options.difficulty && options.difficulty !== "all") params.set("difficulty", options.difficulty);
  if (options.search?.trim()) params.set("search", options.search.trim());
  if (options.sort?.trim()) params.set("sort", options.sort.trim());
  params.set("page", String(Math.max(1, Number(options.page || 1))));
  params.set("page_size", String(Math.max(1, Math.min(Number(options.pageSize || 20), 100))));
  const page = await parseResponse<PaginatedResponse<BankQuestionListItem>>(
    await apiFetch(`${API}/question-bank-v2/bank-versions/${encodeURIComponent(bankVersionId)}/questions/page?${params.toString()}`, {
      credentials: "include",
      headers,
    }),
  );
  return { ...page, items: (page.items || []).map(bankQuestionListItemToQuestion) };
}

export async function exportBankVersionQuestions(
  headers: HeadersInit,
  bankVersionId: string,
  options: { statusFilter?: string; difficulty?: string; search?: string; questionIds?: string[] } = {},
): Promise<Blob> {
  const params = new URLSearchParams();
  if (options.statusFilter && options.statusFilter !== "all") params.set("status_filter", options.statusFilter);
  if (options.difficulty && options.difficulty !== "all") params.set("difficulty", options.difficulty);
  if (options.search?.trim()) params.set("search", options.search.trim());
  if (options.questionIds?.length) params.set("question_ids", options.questionIds.join(","));
  const response = await apiFetch(`${API}/question-bank-v2/bank-versions/${encodeURIComponent(bankVersionId)}/questions/export.csv?${params.toString()}`, { credentials: "include", headers });
  if (!response.ok) throw new Error((await response.text()) || response.statusText);
  return response.blob();
}

export async function downloadBankQuestionImportTemplate(headers: HeadersInit, bankVersionId: string): Promise<Blob> {
  const response = await apiFetch(`${API}/question-bank-v2/bank-versions/${encodeURIComponent(bankVersionId)}/questions/import-template.xlsx`, { credentials: "include", headers });
  if (!response.ok) throw new Error((await response.text()) || response.statusText);
  return response.blob();
}

export async function previewBankQuestionImport(headers: HeadersInit, bankVersionId: string, file: File): Promise<BankQuestionImportPreview> {
  const form = new FormData();
  form.append("file", file);
  return parseResponse<BankQuestionImportPreview>(
    await apiFetch(`${API}/question-bank-v2/bank-versions/${encodeURIComponent(bankVersionId)}/questions/import-preview`, {
      method: "POST",
      headers: withoutContentType(headers),
      body: form,
    }),
  );
}

export async function downloadBankQuestionImportErrors(headers: HeadersInit, bankVersionId: string, previewToken: string): Promise<Blob> {
  const response = await apiFetch(`${API}/question-bank-v2/bank-versions/${encodeURIComponent(bankVersionId)}/questions/import-errors/${encodeURIComponent(previewToken)}.xlsx`, { credentials: "include", headers });
  if (!response.ok) throw new Error((await response.text()) || response.statusText);
  return response.blob();
}

export async function enqueueBankQuestionImport(headers: HeadersInit, bankVersionId: string, previewToken: string): Promise<BankOperationJobQueued> {
  return parseResponse<BankOperationJobQueued>(
    await apiFetch(`${API}/question-bank-v2/bank-versions/${encodeURIComponent(bankVersionId)}/questions/import-job`, {
      method: "POST",
      headers,
      body: JSON.stringify({ preview_token: previewToken }),
    }),
  );
}

export async function getBankVersionQuestionPage(
  headers: HeadersInit,
  bankVersionId: string,
  options: {
    statusFilter?: string;
    difficulty?: string;
    search?: string;
    limit?: number;
    cursorCreatedAt?: string | null;
    cursorId?: string | null;
    includeTotal?: boolean;
  } = {},
) {
  const params = new URLSearchParams();
  if (options.statusFilter) params.set("status_filter", options.statusFilter);
  if (options.difficulty) params.set("difficulty", options.difficulty);
  if (options.search) params.set("search", options.search);
  params.set(
    "limit",
    String(Math.max(1, Math.min(Number(options.limit || 100), 100))),
  );
  if (options.cursorCreatedAt && options.cursorId) {
    params.set("cursor_created_at", options.cursorCreatedAt);
    params.set("cursor_id", options.cursorId);
  }
  if (options.includeTotal) params.set("include_total", "true");
  const page = await parseResponse<
    CursorPaginatedResponse<BankQuestionListItem>
  >(
    await apiFetch(
      `${API}/question-bank-v2/bank-versions/${encodeURIComponent(bankVersionId)}/questions?${params.toString()}`,
      { credentials: "include", headers },
    ),
  );
  return {
    ...page,
    items: (page.items || []).map(bankQuestionListItemToQuestion),
  } as CursorPaginatedResponse<BankVersionQuestion>;
}

export async function getBankVersionQuestions(
  headers: HeadersInit,
  bankVersionId: string,
  statusFilter?: string,
  limit = 100,
) {
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
    if (
      !page.has_next ||
      !page.next_cursor?.created_at ||
      !page.next_cursor?.id
    )
      break;
    cursorCreatedAt = page.next_cursor.created_at;
    cursorId = page.next_cursor.id;
  }
  return items;
}

export async function getBankVersionQuestion(
  headers: HeadersInit,
  bankVersionId: string,
  questionId: string,
) {
  return parseResponse<BankVersionQuestion>(
    await apiFetch(
      `${API}/question-bank-v2/bank-versions/${encodeURIComponent(bankVersionId)}/questions/${encodeURIComponent(questionId)}`,
      { credentials: "include", headers },
    ),
  );
}

export async function previewBankVersionDiff(
  headers: HeadersInit,
  bankVersionId: string,
  payload: { base_bank_version_id?: string | null; persist?: boolean } = {},
) {
  return parseResponse<BankVersionDiffPreview>(
    await apiFetch(
      `${API}/question-bank-v2/bank-versions/${encodeURIComponent(bankVersionId)}/diff/preview`,
      {
        method: "POST",
        headers,
        body: JSON.stringify(payload),
      },
    ),
  );
}

export async function recheckBankMaterialCarryOver(
  headers: HeadersInit,
  bankVersionId: string,
) {
  return parseResponse<BankMaterialRecheckResult>(
    await apiFetch(
      `${API}/question-bank-v2/bank-versions/${encodeURIComponent(bankVersionId)}/materials/recheck-carry-over`,
      {
        method: "POST",
        headers,
      },
    ),
  );
}

export async function carryOverBankQuestions(
  headers: HeadersInit,
  bankVersionId: string,
  payload: {
    base_bank_version_id: string;
    question_ids?: string[] | null;
    require_review?: boolean;
    diff_id?: string | null;
  },
) {
  return parseResponse<BankCarryOverResult>(
    await apiFetch(
      `${API}/question-bank-v2/bank-versions/${encodeURIComponent(bankVersionId)}/carry-over`,
      {
        method: "POST",
        headers,
        body: JSON.stringify(payload),
      },
    ),
  );
}

export async function retireBankQuestions(
  headers: HeadersInit,
  bankVersionId: string,
  payload: { question_ids: string[]; reason?: string },
) {
  return parseResponse<BankRetireResult>(
    await apiFetch(
      `${API}/question-bank-v2/bank-versions/${encodeURIComponent(bankVersionId)}/questions/retire`,
      {
        method: "POST",
        headers,
        body: JSON.stringify(payload),
      },
    ),
  );
}

export async function previewQuizAutoMap(
  headers: HeadersInit,
  payload: {
    openedx_course_id: string;
    selected_subject_offering_id?: string | null;
    total_questions?: number;
    difficulty_easy?: number;
    difficulty_medium?: number;
    difficulty_hard?: number;
    max_families_per_bank?: number;
    single_select_count?: number | null;
    multi_select_count?: number | null;
    text_input_count?: number | null;
    numerical_input_count?: number | null;
    chapter_plan?: Array<{
      chapter_id: string;
      action: "quiz" | "skip" | "assignment" | "final_test";
    }>;
  },
) {
  return parseResponse<QuizAutoMapResult>(
    await apiFetch(`${API}/question-bank-v2/quiz/auto-map/preview`, {
      method: "POST",
      headers,
      body: JSON.stringify(payload),
    }),
  );
}

export async function applyQuizAutoMap(
  headers: HeadersInit,
  payload: {
    openedx_course_id: string;
    selected_subject_offering_id?: string | null;
    total_questions?: number;
    difficulty_easy?: number;
    difficulty_medium?: number;
    difficulty_hard?: number;
    max_families_per_bank?: number;
    single_select_count?: number | null;
    multi_select_count?: number | null;
    text_input_count?: number | null;
    numerical_input_count?: number | null;
    chapter_plan?: Array<{
      chapter_id: string;
      action: "quiz" | "skip" | "assignment" | "final_test";
    }>;
  },
) {
  return parseResponse<QuizAutoMapResult>(
    await apiFetch(`${API}/question-bank-v2/quiz/auto-map/apply`, {
      method: "POST",
      headers,
      body: JSON.stringify(payload),
    }),
  );
}

export async function previewQuizFromBankRelease(
  headers: HeadersInit,
  releaseId: string,
  payload: {
    total_questions: number;
    difficulty_easy: number;
    difficulty_medium: number;
    difficulty_hard: number;
    max_families_per_bank?: number;
    quiz_blueprint_id?: string | null;
    single_select_count?: number | null;
    multi_select_count?: number | null;
    text_input_count?: number | null;
    numerical_input_count?: number | null;
  },
) {
  return parseResponse<BankReleaseQuizPlan>(
    await apiFetch(
      `${API}/question-bank-v2/releases/${encodeURIComponent(releaseId)}/quiz/preview`,
      {
        method: "POST",
        headers,
        body: JSON.stringify(payload),
      },
    ),
  );
}

export async function createQuizFromBankRelease(
  headers: HeadersInit,
  releaseId: string,
  payload: {
    course_chapter_mapping_id: string;
    quiz_title?: string;
    unit_title?: string;
    assessment_type?: "quiz" | "final_test";
    total_questions: number;
    difficulty_easy: number;
    difficulty_medium: number;
    difficulty_hard: number;
    max_families_per_bank?: number;
    quiz_blueprint_id?: string | null;
    single_select_count?: number | null;
    multi_select_count?: number | null;
    text_input_count?: number | null;
    numerical_input_count?: number | null;
    custom_timer_enabled?: boolean;
    time_limit_minutes?: number;
    retake_cooldown_minutes?: number;
    auto_submit_on_timeout?: boolean;
    lock_after_timeout?: boolean;
    native_timed_exam?: boolean;
  },
) {
  const queued = await parseResponse<BankOperationJobQueued>(
    await apiFetch(
      `${API}/question-bank-v2/releases/${encodeURIComponent(releaseId)}/quiz/create-job`,
      {
        method: "POST",
        headers,
        body: JSON.stringify(payload),
      },
    ),
  );
  return enqueueAndWait<BankReleaseQuizCreateResult>(
    headers,
    queued,
    20 * 60 * 1000,
  );
}

export async function createManualBankQuestion(
  headers: HeadersInit,
  bankVersionId: string,
  payload: {
    question_type: string; question_text: string; question_content_json: BankQuestionContent | Record<string, any>;
    difficulty?: string; cognitive_level?: string; learning_objective?: string; explanation?: string; concept_title?: string;
    question_family_id?: string | null; source_ref?: string; source_excerpt?: string; source_evidence?: string;
  },
) {
  return parseResponse<BankVersionQuestion>(await apiFetch(`${API}/question-bank-v2/bank-versions/${encodeURIComponent(bankVersionId)}/questions`, { method: 'POST', headers, body: JSON.stringify(payload) }));
}

export async function uploadBankQuestionMedia(headers: HeadersInit, bankVersionId: string, questionId: string, file: File, altText: string) {
  const form = new FormData(); form.append('file', file); form.append('alt_text', altText);
  return parseResponse<BankQuestionMedia>(await apiFetch(`${API}/question-bank-v2/bank-versions/${encodeURIComponent(bankVersionId)}/questions/${encodeURIComponent(questionId)}/media`, { method: 'POST', headers: withoutContentType(headers), body: form }));
}

export async function deleteBankQuestionMedia(headers: HeadersInit, bankVersionId: string, questionId: string, mediaId: string) {
  return parseResponse<{ok:boolean;media_id:string;question_id:string;file_deleted:boolean;message:string}>(await apiFetch(`${API}/question-bank-v2/bank-versions/${encodeURIComponent(bankVersionId)}/questions/${encodeURIComponent(questionId)}/media/${encodeURIComponent(mediaId)}`, { method: 'DELETE', headers }));
}

export function bankQuestionMediaContentUrl(bankVersionId: string, questionId: string, mediaId: string) {
  return `${API}/question-bank-v2/bank-versions/${encodeURIComponent(bankVersionId)}/questions/${encodeURIComponent(questionId)}/media/${encodeURIComponent(mediaId)}/content`;
}

export async function previewBankOpenEdxImport(headers: HeadersInit, bankVersionId: string, olx: string, sourceRef = 'openedx-olx-import') {
  return parseResponse<BankOpenEdxImportPreview>(await apiFetch(`${API}/question-bank-v2/bank-versions/${encodeURIComponent(bankVersionId)}/questions/import-openedx/preview`, { method: 'POST', headers, body: JSON.stringify({olx, source_ref: sourceRef}) }));
}

export async function importBankOpenEdxQuestions(headers: HeadersInit, bankVersionId: string, olx: string, sourceRef = 'openedx-olx-import') {
  return parseResponse<BankOpenEdxImportResult>(await apiFetch(`${API}/question-bank-v2/bank-versions/${encodeURIComponent(bankVersionId)}/questions/import-openedx`, { method: 'POST', headers, body: JSON.stringify({olx, source_ref: sourceRef}) }));
}

export async function updateBankQuestion(
  headers: HeadersInit,
  bankVersionId: string,
  questionId: string,
  payload: {
    difficulty?: string;
    cognitive_level?: string;
    question_type?: string;
    question_content_json?: BankQuestionContent | Record<string, any>;
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
    await apiFetch(
      `${API}/question-bank-v2/bank-versions/${encodeURIComponent(bankVersionId)}/questions/${encodeURIComponent(questionId)}`,
      {
        method: "PATCH",
        headers,
        body: JSON.stringify(payload),
      },
    ),
  );
}

export async function reviewBankQuestion(
  headers: HeadersInit,
  bankVersionId: string,
  questionId: string,
  payload: { action: "approve" | "reject" | "back_to_review"; note?: string },
) {
  return parseResponse<BankQuestionReviewResult>(
    await apiFetch(
      `${API}/question-bank-v2/bank-versions/${encodeURIComponent(bankVersionId)}/questions/${encodeURIComponent(questionId)}/review`,
      {
        method: "POST",
        headers,
        body: JSON.stringify(payload),
      },
    ),
  );
}

export async function bulkReviewBankQuestions(
  headers: HeadersInit,
  bankVersionId: string,
  payload: {
    action: "approve" | "reject" | "back_to_review";
    question_ids?: string[];
    approve_all_pending?: boolean;
    apply_to_filtered?: boolean;
    status_filter?: string;
    difficulty?: string;
    search?: string;
    note?: string;
  },
) {
  return parseResponse<BankQuestionBulkReviewResult>(
    await apiFetch(
      `${API}/question-bank-v2/bank-versions/${encodeURIComponent(bankVersionId)}/questions/bulk-review`,
      {
        method: "POST",
        headers,
        body: JSON.stringify(payload),
      },
    ),
  );
}

export async function markBankDiffResolved(
  headers: HeadersInit,
  bankVersionId: string,
  payload: { note?: string } = {},
) {
  return parseResponse<BankDocumentDiffResolveResult>(
    await apiFetch(
      `${API}/question-bank-v2/bank-versions/${encodeURIComponent(bankVersionId)}/diff/mark-resolved`,
      {
        method: "POST",
        headers,
        body: JSON.stringify(payload),
      },
    ),
  );
}

export async function getBankReleaseReadiness(
  headers: HeadersInit,
  bankVersionId: string,
) {
  return parseResponse<BankReleaseReadiness>(
    await apiFetch(
      `${API}/question-bank-v2/bank-versions/${encodeURIComponent(bankVersionId)}/release/readiness`,
      { credentials: "include", headers },
    ),
  );
}

export async function getCourseQuizInstances(
  headers: HeadersInit,
  params: {
    openedx_course_id?: string;
    bank_release_id?: string;
    limit?: number;
  } = {},
) {
  const search = new URLSearchParams();
  if (params.openedx_course_id)
    search.set("openedx_course_id", params.openedx_course_id);
  if (params.bank_release_id)
    search.set("bank_release_id", params.bank_release_id);
  if (params.limit) search.set("limit", String(params.limit));
  const suffix = search.toString() ? `?${search.toString()}` : "";
  return parsePageItems<CourseQuizInstance>(
    await apiFetch(`${API}/question-bank-v2/course-quiz-instances${suffix}`, {
      credentials: "include",
      headers,
    }),
  );
}

export async function rollbackCourseQuizInstance(
  headers: HeadersInit,
  instanceId: string,
  payload: { mode?: "safe" | "manual"; note?: string } = {},
) {
  return parseResponse<CourseQuizRollbackResult>(
    await apiFetch(
      `${API}/question-bank-v2/course-quiz-instances/${encodeURIComponent(instanceId)}/rollback`,
      {
        method: "POST",
        headers,
        body: JSON.stringify(payload),
      },
    ),
  );
}

export async function getEffectiveRBAC(
  headers: HeadersInit,
): Promise<EffectiveRBAC> {
  return parseResponse<EffectiveRBAC>(
    await apiFetch(`${API}/rbac/me`, { credentials: "include", headers }),
  );
}

export async function getRBACRoles(headers: HeadersInit): Promise<RBACRole[]> {
  return parseResponse<RBACRole[]>(
    await apiFetch(`${API}/rbac/roles`, { credentials: "include", headers }),
  );
}

export async function getRBACPermissions(
  headers: HeadersInit,
): Promise<RBACPermission[]> {
  return parseResponse<RBACPermission[]>(
    await apiFetch(`${API}/rbac/permissions`, {
      credentials: "include",
      headers,
    }),
  );
}

export async function getRoleAssignments(
  headers: HeadersInit,
  filters: {
    userId?: string;
    roleCode?: string;
    scopeType?: string;
    scopeId?: string;
    includeRevoked?: boolean;
  } = {},
): Promise<RoleAssignmentListResponse> {
  const params = new URLSearchParams();
  if (filters.userId) params.set("user_id", filters.userId);
  if (filters.roleCode) params.set("role_code", filters.roleCode);
  if (filters.scopeType) params.set("scope_type", filters.scopeType);
  if (filters.scopeId) params.set("scope_id", filters.scopeId);
  if (filters.includeRevoked) params.set("include_revoked", "true");
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return parseResponse<RoleAssignmentListResponse>(
    await apiFetch(`${API}/rbac/assignments${suffix}`, {
      credentials: "include",
      headers,
    }),
  );
}

export async function createRoleAssignmentsBatch(
  payload: RoleAssignmentBatchCreate,
  headers: HeadersInit,
): Promise<RoleAssignmentBatchResponse> {
  return parseResponse<RoleAssignmentBatchResponse>(
    await apiFetch(`${API}/rbac/assignments/batch`, {
      method: "POST",
      headers,
      body: JSON.stringify(payload),
    }),
  );
}

export async function createRoleAssignment(
  payload: RoleAssignmentCreate,
  headers: HeadersInit,
): Promise<RoleAssignment> {
  return parseResponse<RoleAssignment>(
    await apiFetch(`${API}/rbac/assignments`, {
      method: "POST",
      headers,
      body: JSON.stringify(payload),
    }),
  );
}

export async function downloadRBACImportTemplate(
  headers: HeadersInit,
): Promise<Blob> {
  const response = await apiFetch(`${API}/rbac/assignments/import-template`, {
    credentials: "include",
    headers,
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || response.statusText);
  }
  return response.blob();
}

export async function importRoleAssignmentsFromExcel(
  headers: HeadersInit,
  file: File,
  dryRun = false,
): Promise<RoleAssignmentImportResponse> {
  const form = new FormData();
  form.append("file", file);
  const cleanHeaders = withoutContentType(headers);
  return parseResponse<RoleAssignmentImportResponse>(
    await apiFetch(
      `${API}/rbac/assignments/import?dry_run=${dryRun ? "true" : "false"}`,
      {
        method: "POST",
        headers: cleanHeaders,
        body: form,
      },
    ),
  );
}

export async function revokeRoleAssignment(
  assignmentId: string,
  headers: HeadersInit,
  revokeReason = "",
): Promise<RoleAssignment> {
  return parseResponse<RoleAssignment>(
    await apiFetch(
      `${API}/rbac/assignments/${encodeURIComponent(assignmentId)}`,
      {
        method: "DELETE",
        headers,
        body: JSON.stringify({ revoke_reason: revokeReason }),
      },
    ),
  );
}

// v25.9.16 Academic AP / Student Management API
export async function getAcademicTerms(
  headers: HeadersInit,
  filters: string | { branch?: string; active?: boolean | null } = "",
): Promise<AcademicTerm[]> {
  const params = new URLSearchParams();
  const branch = typeof filters === "string" ? filters : filters.branch || "";
  if (branch.trim()) params.set("branch", branch.trim());
  if (typeof filters !== "string" && typeof filters.active === "boolean")
    params.set("active", String(filters.active));
  return parseResponse(
    await apiFetch(`${API}/academic/terms?${params.toString()}`, {
      credentials: "include",
      headers,
    }),
  );
}

export async function saveAcademicTerm(
  headers: HeadersInit,
  payload: {
    id?: string | null;
    ap_term_id?: string | null;
    term_code: string;
    term_name: string;
    branch?: string;
    start_date?: string | null;
    end_date?: string | null;
    active?: boolean;
    blocks?: Array<{
      id?: string | null;
      block_code: string;
      block_name: string;
      start_date?: string | null;
      end_date?: string | null;
      sort_order?: number;
      active?: boolean;
    }>;
  },
): Promise<AcademicTerm> {
  return parseResponse(
    await apiFetch(`${API}/academic/terms`, {
      method: "POST",
      headers,
      body: JSON.stringify(payload),
    }),
  );
}

export async function getAcademicTermWithBlocks(
  headers: HeadersInit,
  termId: string,
): Promise<AcademicTerm & { blocks?: AcademicBlock[] }> {
  return parseResponse(
    await apiFetch(
      `${API}/academic/terms/${encodeURIComponent(termId)}/with-blocks`,
      { credentials: "include", headers },
    ),
  );
}

export async function deleteAcademicTerm(
  headers: HeadersInit,
  termId: string,
): Promise<AcademicTerm> {
  return parseResponse(
    await apiFetch(`${API}/academic/terms/${encodeURIComponent(termId)}`, {
      method: "DELETE",
      headers,
    }),
  );
}

export async function getAcademicBlocks(
  headers: HeadersInit,
  termId: string,
): Promise<AcademicBlock[]> {
  if (!termId) return [];
  return parseResponse(
    await apiFetch(
      `${API}/academic/blocks?term_id=${encodeURIComponent(termId)}`,
      { credentials: "include", headers },
    ),
  );
}

export async function getAcademicSubjectDeliveries(
  headers: HeadersInit,
  filters: {
    termId?: string
    blockId?: string
    branch?: string
    platform?: AcademicLearningPlatform | 'all' | 'mixed'
    managementScope?: 'delivery' | 'term'
    search?: string
    page?: number
    pageSize?: number
  } = {},
): Promise<AcademicSubjectDeliveryListResponse> {
  const params = new URLSearchParams()
  if (filters.termId) params.set('term_id', filters.termId)
  if (filters.blockId) params.set('block_id', filters.blockId)
  if (filters.branch) params.set('branch', filters.branch)
  if (filters.platform && filters.platform !== 'all') params.set('platform', filters.platform)
  if (filters.platform === null) params.set('platform', 'unassigned')
  if (filters.managementScope) params.set('management_scope', filters.managementScope)
  if (filters.search?.trim()) params.set('search', filters.search.trim())
  params.set('page', String(Math.max(1, filters.page || 1)))
  params.set('page_size', String(Math.max(1, Math.min(200, filters.pageSize || 50))))
  return parseResponse(
    await apiFetch(`${API}/academic/subject-deliveries?${params.toString()}`, {
      credentials: 'include',
      headers,
    }),
  )
}

export async function createAcademicSubjectCatalogRefreshJob(
  headers: HeadersInit,
  payload: { termId: string; blockId?: string | null; branch: string },
): Promise<AcademicSubjectCatalogRefreshResult> {
  return parseResponse(
    await apiFetch(`${API}/academic/subject-deliveries/catalog-refresh/jobs`, {
      method: 'POST',
      headers,
      body: JSON.stringify({ term_id: payload.termId, block_id: payload.blockId || null, branch: payload.branch }),
    }),
  )
}

export async function updateAcademicSubjectDeliveryPlatform(
  headers: HeadersInit,
  deliveryId: string,
  learningPlatform: AcademicLearningPlatform,
): Promise<AcademicSubjectPlatformMutationResult> {
  return parseResponse(
    await apiFetch(`${API}/academic/subject-deliveries/${encodeURIComponent(deliveryId)}/platform`, {
      method: 'PATCH',
      headers,
      body: JSON.stringify({ learning_platform: learningPlatform }),
    }),
  )
}

export async function bulkUpdateAcademicSubjectDeliveryPlatform(
  headers: HeadersInit,
  deliveryIds: string[],
  learningPlatform: AcademicLearningPlatform,
): Promise<AcademicSubjectPlatformMutationResult> {
  return parseResponse(
    await apiFetch(`${API}/academic/subject-deliveries/platform/bulk`, {
      method: 'POST',
      headers,
      body: JSON.stringify({ delivery_ids: deliveryIds, learning_platform: learningPlatform }),
    }),
  )
}

export async function downloadUdemyPlanImportTemplate(headers: HeadersInit): Promise<Blob> {
  const response = await apiFetch(`${API}/academic/udemy/plans/import-template.xlsx`, { credentials: 'include', headers })
  if (!response.ok) throw new Error((await response.text()) || response.statusText)
  return response.blob()
}

export async function previewUdemyPlanImport(headers: HeadersInit, file: File, branch: string): Promise<UdemyPlanImportPreview> {
  const form = new FormData()
  form.append('file', file)
  form.append('branch', branch)
  return parseResponse(
    await apiFetch(`${API}/academic/udemy/plans/import/preview`, {
      method: 'POST',
      headers: withoutContentType(headers),
      body: form,
    }),
  )
}

export async function downloadUdemyPlanImportErrors(headers: HeadersInit, previewToken: string): Promise<Blob> {
  const response = await apiFetch(`${API}/academic/udemy/plans/import/errors/${encodeURIComponent(previewToken)}.xlsx`, { credentials: 'include', headers })
  if (!response.ok) throw new Error((await response.text()) || response.statusText)
  return response.blob()
}

export async function commitUdemyPlanImport(headers: HeadersInit, previewToken: string): Promise<UdemyPlanMutationResult> {
  return parseResponse(
    await apiFetch(`${API}/academic/udemy/plans/import/commit`, {
      method: 'POST',
      headers,
      body: JSON.stringify({ preview_token: previewToken }),
    }),
  )
}

export async function getUdemyPlanDetail(headers: HeadersInit, deliveryId: string): Promise<UdemyPlanDetail> {
  return parseResponse(
    await apiFetch(`${API}/academic/subject-deliveries/${encodeURIComponent(deliveryId)}/udemy-plan`, { credentials: 'include', headers }),
  )
}

export async function getUdemyPlanHistory(headers: HeadersInit, deliveryId: string): Promise<UdemySubjectPlan[]> {
  return parseResponse(
    await apiFetch(`${API}/academic/subject-deliveries/${encodeURIComponent(deliveryId)}/udemy-plan/history`, { credentials: 'include', headers }),
  )
}

export async function createUdemyPlanVersion(
  headers: HeadersInit,
  deliveryId: string,
  payload: { item_count: number; milestones: UdemyPlanMilestone[]; note?: string | null },
): Promise<UdemyPlanMutationResult> {
  return parseResponse(
    await apiFetch(`${API}/academic/subject-deliveries/${encodeURIComponent(deliveryId)}/udemy-plan`, {
      method: 'POST',
      headers,
      body: JSON.stringify(payload),
    }),
  )
}

export async function createUdemyProgressImportJob(
  headers: HeadersInit,
  payload: {
    files: File[]
    termId: string
    blockId: string
    branch: string
    deliveryId?: string | null
    forceReimport?: boolean
  },
): Promise<UdemyProgressImportJobResult> {
  const form = new FormData()
  payload.files.forEach((file) => form.append('files', file))
  form.append('term_id', payload.termId)
  form.append('block_id', payload.blockId)
  form.append('branch', payload.branch)
  if (payload.deliveryId) form.append('delivery_id', payload.deliveryId)
  form.append('force_reimport', String(Boolean(payload.forceReimport)))
  return parseResponse(
    await apiFetch(`${API}/academic/udemy/progress/import/jobs`, {
      method: 'POST',
      headers: withoutContentType(headers),
      body: form,
    }),
  )
}

export async function retryUdemyProgressImportBatch(
  headers: HeadersInit,
  batchId: string,
): Promise<UdemyProgressImportJobResult> {
  return parseResponse(await apiFetch(`${API}/academic/udemy/progress/import-batches/${encodeURIComponent(batchId)}/retry`, {
    method: 'POST',
    credentials: 'include',
    headers,
  }))
}

export async function getUdemyProgressImportBatches(
  headers: HeadersInit,
  filters: { deliveryId?: string; parentJobId?: string; status?: string; limit?: number } = {},
): Promise<UdemyProgressImportBatch[]> {
  const params = new URLSearchParams()
  if (filters.deliveryId) params.set('delivery_id', filters.deliveryId)
  if (filters.parentJobId) params.set('parent_job_id', filters.parentJobId)
  if (filters.status) params.set('status', filters.status)
  params.set('limit', String(Math.max(1, Math.min(200, filters.limit || 50))))
  return parseResponse(await apiFetch(`${API}/academic/udemy/progress/import-batches?${params.toString()}`, { credentials: 'include', headers }))
}

export async function downloadUdemyProgressImportErrors(headers: HeadersInit, batchId: string): Promise<Blob> {
  const response = await apiFetch(`${API}/academic/udemy/progress/import-batches/${encodeURIComponent(batchId)}/errors.xlsx`, { credentials: 'include', headers })
  if (!response.ok) throw new Error((await response.text()) || response.statusText)
  return response.blob()
}

export async function getUdemyProgressSummary(headers: HeadersInit, deliveryId: string): Promise<UdemyProgressSummary> {
  return parseResponse(await apiFetch(`${API}/academic/subject-deliveries/${encodeURIComponent(deliveryId)}/udemy-progress/summary`, { credentials: 'include', headers }))
}

export async function getUdemyProgressDashboard(headers: HeadersInit, deliveryId: string): Promise<UdemyProgressDashboard> {
  return parseResponse(await apiFetch(`${API}/academic/subject-deliveries/${encodeURIComponent(deliveryId)}/udemy-progress/dashboard`, { credentials: 'include', headers, cache: 'no-store' }))
}

export async function getUdemyProgressStudents(
  headers: HeadersInit,
  deliveryId: string,
  filters: { q?: string; classId?: string; status?: string; page?: number; pageSize?: number; sortBy?: string; sortDir?: 'asc' | 'desc' } = {},
): Promise<UdemyProgressStudentList> {
  const params = new URLSearchParams()
  if (filters.q?.trim()) params.set('q', filters.q.trim())
  if (filters.classId) params.set('class_id', filters.classId)
  if (filters.status && filters.status !== 'all') params.set('status', filters.status)
  params.set('page', String(filters.page || 1))
  params.set('page_size', String(filters.pageSize || 50))
  params.set('sort_by', filters.sortBy || 'student')
  params.set('sort_dir', filters.sortDir || 'asc')
  return parseResponse(await apiFetch(`${API}/academic/subject-deliveries/${encodeURIComponent(deliveryId)}/udemy-progress/students?${params.toString()}`, { credentials: 'include', headers, cache: 'no-store' }))
}

export async function createUdemyProgressExportJob(
  headers: HeadersInit,
  deliveryId: string,
  filters: { q?: string; classId?: string; status?: string } = {},
): Promise<AcademicBulkOperationJob> {
  const params = new URLSearchParams()
  if (filters.q?.trim()) params.set('q', filters.q.trim())
  if (filters.classId) params.set('class_id', filters.classId)
  if (filters.status && filters.status !== 'all') params.set('status', filters.status)
  const suffix = params.toString() ? `?${params.toString()}` : ''
  return parseResponse(await apiFetch(`${API}/academic/subject-deliveries/${encodeURIComponent(deliveryId)}/udemy-progress/export-jobs${suffix}`, {
    method: 'POST',
    credentials: 'include',
    headers,
  }))
}

export async function downloadUdemyProgressExportJob(
  headers: HeadersInit,
  jobId: string,
): Promise<Blob> {
  const response = await apiFetch(`${API}/academic/udemy/progress/export-jobs/${encodeURIComponent(jobId)}/download`, { credentials: 'include', headers })
  if (!response.ok) return parseResponse(response)
  return response.blob()
}

export async function downloadUdemyProgressExport(
  headers: HeadersInit,
  deliveryId: string,
  filters: { q?: string; classId?: string; status?: string } = {},
): Promise<Blob> {
  const params = new URLSearchParams()
  if (filters.q?.trim()) params.set('q', filters.q.trim())
  if (filters.classId) params.set('class_id', filters.classId)
  if (filters.status && filters.status !== 'all') params.set('status', filters.status)
  const response = await apiFetch(`${API}/academic/subject-deliveries/${encodeURIComponent(deliveryId)}/udemy-progress/export.xlsx?${params.toString()}`, { credentials: 'include', headers })
  if (!response.ok) throw new Error((await response.text()) || response.statusText)
  return response.blob()
}


export async function getAcademicSubjects(
  headers: HeadersInit,
  filters: {
    termId?: string;
    blockId?: string;
    search?: string;
    branch?: string;
    learningPlatform?: 'cms' | 'udemy';
  } = {},
): Promise<AcademicSubject[]> {
  const params = new URLSearchParams();
  if (filters.termId) params.set("term_id", filters.termId);
  if (filters.blockId) params.set("block_id", filters.blockId);
  if (filters.search?.trim()) params.set("search", filters.search.trim());
  if (filters.branch?.trim()) params.set("branch", filters.branch.trim());
  if (filters.learningPlatform) params.set("learning_platform", filters.learningPlatform);
  return parseResponse(
    await apiFetch(`${API}/academic/subjects?${params.toString()}`, {
      credentials: "include",
      headers,
    }),
  );
}

export async function getAcademicClassQuizDeadlineOverrides(
  headers: HeadersInit,
  classId: string,
  courseId?: string | null,
): Promise<AcademicQuizDeadlineOverride[]> {
  const params = new URLSearchParams();
  if (courseId) params.set("course_id", courseId);
  return parseResponse(
    await apiFetch(
      `${API}/academic/classes/${encodeURIComponent(classId)}/quiz-deadline-overrides?${params.toString()}`,
      { credentials: "include", headers },
    ),
  );
}

export async function saveAcademicClassQuizDeadlineOverrides(
  headers: HeadersInit,
  classId: string,
  items: AcademicQuizDeadlineOverride[],
): Promise<AcademicQuizDeadlineOverride[]> {
  return parseResponse(
    await apiFetch(
      `${API}/academic/classes/${encodeURIComponent(classId)}/quiz-deadline-overrides`,
      {
        method: "PUT",
        credentials: "include",
        headers,
        body: JSON.stringify({ items }),
      },
    ),
  );
}

export async function getAcademicClassAssignmentDefenseScores(
  headers: HeadersInit,
  classId: string,
  courseId?: string | null,
): Promise<AcademicAssignmentDefenseScore[]> {
  const params = new URLSearchParams();
  if (courseId) params.set("course_id", courseId);
  return parseResponse(
    await apiFetch(
      `${API}/academic/classes/${encodeURIComponent(classId)}/assignment-defense-scores?${params.toString()}`,
      { credentials: "include", headers },
    ),
  );
}

export async function saveAcademicClassAssignmentDefenseScores(
  headers: HeadersInit,
  classId: string,
  items: AcademicAssignmentDefenseScore[],
): Promise<AcademicAssignmentDefenseScore[]> {
  return parseResponse(
    await apiFetch(
      `${API}/academic/classes/${encodeURIComponent(classId)}/assignment-defense-scores`,
      {
        method: "PUT",
        credentials: "include",
        headers,
        body: JSON.stringify({ items }),
      },
    ),
  );
}

function clampAcademicPageSize(value?: number | null, fallback = 50): number {
  const parsed = Number(value ?? fallback);
  if (!Number.isFinite(parsed)) return fallback;
  return Math.max(1, Math.min(200, Math.floor(parsed)));
}

export async function getAcademicTrainingTeacherReport(
  headers: HeadersInit,
  filters: {
    termId?: string;
    campus?: string;
    branch?: string;
    search?: string;
    learningStatus?: string;
    learningPlatform?: 'cms' | 'udemy';
    teacherId?: string;
    page?: number;
    pageSize?: number;
    includeClasses?: boolean;
    fresh?: boolean;
  } = {},
): Promise<AcademicTrainingTeacherReportResponse> {
  const params = new URLSearchParams();
  if (filters.termId) params.set("term_id", filters.termId);
  if (filters.campus?.trim()) params.set("campus", filters.campus.trim());
  if (filters.branch?.trim()) params.set("branch", filters.branch.trim());
  if (filters.search?.trim()) params.set("search", filters.search.trim());
  if (filters.learningStatus?.trim() && filters.learningStatus.trim() !== "all")
    params.set("learning_status", filters.learningStatus.trim());
  if (filters.learningPlatform) params.set("learning_platform", filters.learningPlatform);
  if (filters.teacherId?.trim())
    params.set("teacher_id", filters.teacherId.trim());
  if (typeof filters.includeClasses === "boolean")
    params.set("include_classes", filters.includeClasses ? "true" : "false");
  if (filters.fresh) params.set("fresh", "true");
  params.set("page", String(filters.page || 1));
  params.set("page_size", String(clampAcademicPageSize(filters.pageSize)));
  return parseResponse(
    await apiFetch(`${API}/academic/training/teachers?${params.toString()}`, {
      credentials: "include",
      headers,
    }),
  );
}

export async function downloadAcademicTrainingTeacherReport(
  headers: HeadersInit,
  filters: {
    termId?: string;
    campus?: string;
    branch?: string;
    search?: string;
    learningStatus?: string;
    learningPlatform?: 'cms' | 'udemy';
    teacherId?: string;
  } = {},
): Promise<Blob> {
  const params = new URLSearchParams();
  if (filters.termId) params.set("term_id", filters.termId);
  if (filters.campus?.trim()) params.set("campus", filters.campus.trim());
  if (filters.branch?.trim()) params.set("branch", filters.branch.trim());
  if (filters.search?.trim()) params.set("search", filters.search.trim());
  if (filters.learningStatus?.trim() && filters.learningStatus.trim() !== "all")
    params.set("learning_status", filters.learningStatus.trim());
  if (filters.learningPlatform) params.set("learning_platform", filters.learningPlatform);
  if (filters.teacherId?.trim())
    params.set("teacher_id", filters.teacherId.trim());
  const response = await apiFetch(
    `${API}/academic/training/teachers/export?${params.toString()}`,
    { credentials: "include", headers },
  );
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || response.statusText);
  }
  return response.blob();
}

export async function createAcademicTrainingTeacherCacheJob(
  headers: HeadersInit,
  filters: { termId: string; campus?: string; branch?: string; learningPlatform?: 'cms' | 'udemy' },
): Promise<AcademicTeacherReportJob> {
  const params = new URLSearchParams();
  params.set("term_id", filters.termId);
  if (filters.campus?.trim()) params.set("campus", filters.campus.trim());
  if (filters.branch?.trim()) params.set("branch", filters.branch.trim());
  if (filters.learningPlatform) params.set("learning_platform", filters.learningPlatform);
  return parseResponse(
    await apiFetch(
      `${API}/academic/training/teachers/report-cache/jobs?${params.toString()}`,
      { method: "POST", credentials: "include", headers },
    ),
  );
}

export async function createAcademicTrainingTeacherExportJob(
  headers: HeadersInit,
  filters: {
    termId: string;
    campus?: string;
    branch?: string;
    search?: string;
    learningStatus?: string;
    learningPlatform?: 'cms' | 'udemy';
    teacherId?: string;
  },
): Promise<AcademicTeacherReportJob> {
  const params = new URLSearchParams();
  params.set("term_id", filters.termId);
  if (filters.campus?.trim()) params.set("campus", filters.campus.trim());
  if (filters.branch?.trim()) params.set("branch", filters.branch.trim());
  if (filters.search?.trim()) params.set("search", filters.search.trim());
  if (filters.learningStatus?.trim() && filters.learningStatus.trim() !== "all")
    params.set("learning_status", filters.learningStatus.trim());
  if (filters.learningPlatform) params.set("learning_platform", filters.learningPlatform);
  if (filters.teacherId?.trim())
    params.set("teacher_id", filters.teacherId.trim());
  return parseResponse(
    await apiFetch(
      `${API}/academic/training/teachers/export/jobs?${params.toString()}`,
      { method: "POST", credentials: "include", headers },
    ),
  );
}

export async function createAcademicTrainingClassExportJob(
  headers: HeadersInit,
  classId: string,
): Promise<AcademicTeacherReportJob> {
  return parseResponse(
    await apiFetch(
      `${API}/academic/training/classes/${encodeURIComponent(classId)}/export/jobs`,
      { method: "POST", credentials: "include", headers },
    ),
  );
}


export async function getAcademicTrainingTeacherReportJob(
  headers: HeadersInit,
  jobId: string,
): Promise<AcademicTeacherReportJob> {
  return parseResponse(
    await apiFetch(
      `${API}/academic/training/teachers/report-jobs/${encodeURIComponent(jobId)}`,
      { credentials: "include", headers },
    ),
  );
}

export async function waitForAcademicTrainingTeacherReportJob(
  headers: HeadersInit,
  jobId: string,
  options: { timeoutMs?: number; signal?: AbortSignal } = {},
): Promise<AcademicTeacherReportJob> {
  const startedAt = Date.now();
  const timeoutMs = options.timeoutMs ?? 20 * 60 * 1000;
  let intervalMs = 1_500;
  let latest: AcademicTeacherReportJob | null = null;
  while (Date.now() - startedAt < timeoutMs) {
    if (options.signal?.aborted) throw options.signal.reason || new DOMException("Aborted", "AbortError");
    latest = await parseResponse<AcademicTeacherReportJob>(
      await apiFetch(
        `${API}/academic/training/teachers/report-jobs/${encodeURIComponent(jobId)}`,
        { credentials: "include", headers, signal: options.signal, retries: 1 },
      ),
    );
    if (latest.status === "completed") return latest;
    if (["failed", "canceled"].includes(latest.status)) {
      throw new Error(latest.error_message || latest.progress_label || "Xuất báo cáo giáo viên thất bại.");
    }
    await sleepWithSignal(intervalMs, options.signal);
    intervalMs = Math.min(10_000, Math.round(intervalMs * 1.7));
  }
  throw new Error(latest?.progress_label || "Tác vụ xuất báo cáo quá thời gian chờ. Vui lòng kiểm tra trang Tác vụ nền.");
}

export async function getAcademicTrainingTeacherReportJobs(
  headers: HeadersInit,
  filters: {
    status?:
      "active" | "queued" | "running" | "completed" | "failed" | "all" | string;
    limit?: number;
  } = {},
): Promise<AcademicTeacherReportJob[]> {
  const params = new URLSearchParams();
  if (filters.status) params.set("status", filters.status);
  params.set("limit", String(Math.max(1, Math.min(80, filters.limit || 20))));
  return parseResponse(
    await apiFetch(
      `${API}/academic/training/teachers/report-jobs?${params.toString()}`,
      { credentials: "include", headers },
    ),
  );
}

export async function downloadAcademicTrainingTeacherReportJob(
  headers: HeadersInit,
  jobId: string,
): Promise<Blob> {
  const response = await apiFetch(
    `${API}/academic/training/teachers/report-jobs/${encodeURIComponent(jobId)}/download`,
    { credentials: "include", headers },
  );
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || response.statusText);
  }
  return response.blob();
}

export async function getAcademicTeacherClasses(
  headers: HeadersInit,
  filters: {
    termId?: string;
    blockId?: string;
    subjectId?: string;
    campus?: string;
    branch?: string;
    search?: string;
    learningStatus?: string;
    learningPlatform?: 'cms' | 'udemy';
    page?: number;
    pageSize?: number;
  } = {},
): Promise<AcademicClassListResponse> {
  const params = new URLSearchParams();
  if (filters.termId) params.set("term_id", filters.termId);
  if (filters.blockId) params.set("block_id", filters.blockId);
  if (filters.subjectId) params.set("subject_id", filters.subjectId);
  if (filters.campus?.trim()) params.set("campus", filters.campus.trim());
  if (filters.branch?.trim()) params.set("branch", filters.branch.trim());
  if (filters.search?.trim()) params.set("search", filters.search.trim());
  if (filters.learningStatus?.trim() && filters.learningStatus.trim() !== "all")
    params.set("learning_status", filters.learningStatus.trim());
  if (filters.learningPlatform) params.set("learning_platform", filters.learningPlatform);
  params.set("page", String(filters.page || 1));
  params.set("page_size", String(clampAcademicPageSize(filters.pageSize)));
  return parseResponse(
    await apiFetch(`${API}/academic/teacher/classes?${params.toString()}`, {
      credentials: "include",
      headers,
    }),
  );
}

export async function getAcademicTeacherSubjects(
  headers: HeadersInit,
  filters: {
    termId?: string;
    campus?: string;
    branch?: string;
    search?: string;
    learningStatus?: string;
    learningPlatform?: 'cms' | 'udemy';
    page?: number;
    pageSize?: number;
  } = {},
): Promise<AcademicSubjectManagementListResponse> {
  const params = new URLSearchParams();
  if (filters.termId) params.set("term_id", filters.termId);
  if (filters.campus?.trim()) params.set("campus", filters.campus.trim());
  if (filters.branch?.trim()) params.set("branch", filters.branch.trim());
  if (filters.search?.trim()) params.set("search", filters.search.trim());
  if (filters.learningStatus?.trim() && filters.learningStatus.trim() !== "all")
    params.set("learning_status", filters.learningStatus.trim());
  if (filters.learningPlatform) params.set("learning_platform", filters.learningPlatform);
  params.set("page", String(filters.page || 1));
  params.set("page_size", String(clampAcademicPageSize(filters.pageSize)));
  return parseResponse(
    await apiFetch(`${API}/academic/teacher/subjects?${params.toString()}`, {
      credentials: "include",
      headers,
    }),
  );
}

export async function getAcademicSubjectClasses(
  headers: HeadersInit,
  subjectId: string,
  filters: {
    termId?: string;
    blockId?: string;
    campus?: string;
    branch?: string;
    search?: string;
    learningStatus?: string;
    learningPlatform?: 'cms' | 'udemy';
    page?: number;
    pageSize?: number;
  } = {},
): Promise<AcademicClassListResponse> {
  const params = new URLSearchParams();
  if (filters.termId) params.set("term_id", filters.termId);
  if (filters.blockId) params.set("block_id", filters.blockId);
  if (filters.campus?.trim()) params.set("campus", filters.campus.trim());
  if (filters.branch?.trim()) params.set("branch", filters.branch.trim());
  if (filters.search?.trim()) params.set("search", filters.search.trim());
  if (filters.learningStatus?.trim() && filters.learningStatus.trim() !== "all")
    params.set("learning_status", filters.learningStatus.trim());
  if (filters.learningPlatform) params.set("learning_platform", filters.learningPlatform);
  params.set("page", String(filters.page || 1));
  params.set("page_size", String(clampAcademicPageSize(filters.pageSize)));
  return parseResponse(
    await apiFetch(
      `${API}/academic/subjects/${encodeURIComponent(subjectId)}/classes?${params.toString()}`,
      { credentials: "include", headers },
    ),
  );
}

export async function autoMapAllAcademicSubjectCoursesAndSync(
  headers: HeadersInit,
  payload: {
    termId: string;
    branch?: string;
    campus?: string;
    search?: string;
    learningStatus?: string;
    force?: boolean;
    limit?: number;
    syncLearning?: boolean;
    maxClasses?: number;
    mode?: string | null;
  },
): Promise<AcademicSubjectAutoMapAllSyncResult> {
  return parseResponse(
    await apiFetch(
      `${API}/academic/subjects/course-mapping/auto-all-sync/jobs`,
      {
        method: "POST",
        headers,
        body: JSON.stringify({
          term_id: payload.termId,
          branch: payload.branch || null,
          campus: payload.campus || null,
          search: payload.search || null,
          learning_status:
            payload.learningStatus && payload.learningStatus !== "all"
              ? payload.learningStatus
              : null,
          force: payload.force !== false,
          limit: Math.max(1, Math.min(500, payload.limit || 500)),
          sync_learning: payload.syncLearning !== false,
          max_classes: Math.max(1, Math.min(5000, payload.maxClasses || 3000)),
          mode: payload.mode || null,
        }),
      },
    ),
  );
}

export async function getAcademicBulkOperationJobs(
  headers: HeadersInit,
  filters: {
    status?:
      "active" | "queued" | "running" | "completed" | "failed" | "all" | string;
    limit?: number;
  } = {},
): Promise<AcademicBulkOperationJob[]> {
  const params = new URLSearchParams();
  if (filters.status) params.set("status", filters.status);
  params.set("limit", String(Math.max(1, Math.min(100, filters.limit || 50))));
  return parseResponse(
    await apiFetch(`${API}/academic/bulk-operation-jobs?${params.toString()}`, {
      credentials: "include",
      headers,
    }),
  );
}

export async function getAcademicBulkOperationJob(
  headers: HeadersInit,
  jobId: string,
): Promise<AcademicBulkOperationJob> {
  return parseResponse(
    await apiFetch(
      `${API}/academic/bulk-operation-jobs/${encodeURIComponent(jobId)}`,
      { credentials: "include", headers },
    ),
  );
}

export async function autoMapAcademicSubjectCourse(
  headers: HeadersInit,
  subjectId: string,
  filters: { termId: string; branch?: string },
): Promise<AcademicSubjectCourseAutoMapResult> {
  const params = new URLSearchParams();
  params.set("term_id", filters.termId);
  if (filters.branch?.trim()) params.set("branch", filters.branch.trim());
  return parseResponse(
    await apiFetch(
      `${API}/academic/subjects/${encodeURIComponent(subjectId)}/course-mapping/auto?${params.toString()}`,
      { method: "POST", headers },
    ),
  );
}

export async function getAcademicClassStudents(
  headers: HeadersInit,
  classId: string,
  filters: {
    search?: string;
    learningStatus?: string;
    page?: number;
    pageSize?: number;
  } = {},
): Promise<AcademicStudentListResponse> {
  const params = new URLSearchParams();
  if (filters.search?.trim()) params.set("search", filters.search.trim());
  if (filters.learningStatus?.trim())
    params.set("learning_status", filters.learningStatus.trim());
  params.set("page", String(filters.page || 1));
  params.set("page_size", String(clampAcademicPageSize(filters.pageSize)));
  return parseResponse(
    await apiFetch(
      `${API}/academic/classes/${encodeURIComponent(classId)}/students?${params.toString()}`,
      { credentials: "include", headers },
    ),
  );
}

export async function getAcademicClass(
  headers: HeadersInit,
  classId: string,
): Promise<AcademicClass> {
  return parseResponse(
    await apiFetch(`${API}/academic/classes/${encodeURIComponent(classId)}`, {
      credentials: "include",
      headers,
    }),
  );
}

export async function getAcademicClassMappingSummary(
  headers: HeadersInit,
  classId: string,
): Promise<AcademicMappingSummary> {
  return parseResponse(
    await apiFetch(
      `${API}/academic/classes/${encodeURIComponent(classId)}/mapping-summary`,
      { credentials: "include", headers },
    ),
  );
}

export async function getAcademicClassLearningSummary(
  headers: HeadersInit,
  classId: string,
): Promise<AcademicLearningSummary> {
  return parseResponse(
    await apiFetch(
      `${API}/academic/classes/${encodeURIComponent(classId)}/learning-summary`,
      { credentials: "include", headers },
    ),
  );
}

export async function getAcademicClassIdentityReconciliation(
  headers: HeadersInit,
  classId: string,
  filters: { statusFilter?: string; page?: number; pageSize?: number } = {},
): Promise<AcademicIdentityReconciliationReport> {
  const params = new URLSearchParams();
  params.set("status_filter", filters.statusFilter || "all");
  params.set("page", String(filters.page || 1));
  params.set("page_size", String(filters.pageSize || 200));
  return parseResponse(
    await apiFetch(
      `${API}/academic/classes/${encodeURIComponent(classId)}/identity-reconciliation?${params.toString()}`,
      { credentials: "include", headers },
    ),
  );
}


export async function cleanupAcademicClassIdentityReconciliation(
  headers: HeadersInit,
  classId: string,
  payload: {
    dry_run?: boolean
    confirm_phrase?: string
    statuses?: string[]
    student_ids?: string[]
    delete_wrong_learning_snapshots?: boolean
  } = {},
): Promise<AcademicIdentityCleanupResult> {
  return parseResponse(
    await apiFetch(
      `${API}/academic/classes/${encodeURIComponent(classId)}/identity-reconciliation/uat-cleanup`,
      {
        method: "POST",
        credentials: "include",
        headers: { ...headers, "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      },
    ),
  );
}


export async function getAnalyticsDataQualityReport(
  headers: HeadersInit,
  filters: { classId?: string; courseId?: string } = {},
): Promise<AnalyticsDataQualityReport> {
  const params = new URLSearchParams();
  if (filters.classId?.trim()) params.set("class_id", filters.classId.trim());
  if (filters.courseId?.trim())
    params.set("course_id", filters.courseId.trim());
  return parseResponse(
    await apiFetch(`${API}/analytics/ops/data-quality?${params.toString()}`, {
      credentials: "include",
      headers,
    }),
  );
}





export async function getPilotOperationsReadiness(
  headers: HeadersInit,
  filters: { classId?: string; courseId?: string; branch?: string; campus?: string; sampleLimit?: number } = {},
): Promise<PilotOperationsReport> {
  const params = new URLSearchParams();
  if (filters.classId?.trim()) params.set("class_id", filters.classId.trim());
  if (filters.courseId?.trim()) params.set("course_id", filters.courseId.trim());
  if (filters.branch?.trim()) params.set("branch", filters.branch.trim());
  if (filters.campus?.trim()) params.set("campus", filters.campus.trim());
  params.set("sample_limit", String(filters.sampleLimit || 5));
  return parseResponse(
    await apiFetch(`${API}/health/pilot-operations?${params.toString()}`, {
      credentials: "include",
      headers,
    }),
  );
}

export async function getReleaseCandidateReadiness(
  headers: HeadersInit,
  filters: { classId?: string; courseId?: string; branch?: string; campus?: string; sampleLimit?: number } = {},
): Promise<ReleaseCandidateReport> {
  const params = new URLSearchParams();
  if (filters.classId?.trim()) params.set("class_id", filters.classId.trim());
  if (filters.courseId?.trim()) params.set("course_id", filters.courseId.trim());
  if (filters.branch?.trim()) params.set("branch", filters.branch.trim());
  if (filters.campus?.trim()) params.set("campus", filters.campus.trim());
  params.set("sample_limit", String(filters.sampleLimit || 5));
  return parseResponse(
    await apiFetch(`${API}/health/release-candidate?${params.toString()}`, {
      credentials: "include",
      headers,
    }),
  );
}

export async function getSecurityReadiness(
  headers: HeadersInit,
): Promise<SecurityReadinessReport> {
  return parseResponse(
    await apiFetch(`${API}/health/security-readiness`, {
      credentials: "include",
      headers,
    }),
  );
}

export async function getPerformanceReadiness(
  headers: HeadersInit,
): Promise<PerformanceReadinessReport> {
  return parseResponse(
    await apiFetch(`${API}/health/performance-readiness`, {
      credentials: "include",
      headers,
    }),
  );
}

export async function getAnalyticsProductionReadiness(
  headers: HeadersInit,
): Promise<AnalyticsProductionReadinessReport> {
  return parseResponse(
    await apiFetch(`${API}/analytics/ops/production-readiness`, {
      credentials: "include",
      headers,
    }),
  );
}

export async function getAnalyticsSlaReport(
  headers: HeadersInit,
  limit = 20,
): Promise<AnalyticsSlaReport> {
  const params = new URLSearchParams();
  params.set("limit", String(Math.max(1, Math.min(100, limit || 20))));
  return parseResponse(
    await apiFetch(`${API}/analytics/ops/sla?${params.toString()}`, {
      credentials: "include",
      headers,
    }),
  );
}

export async function getAnalyticsRolloutControl(
  headers: HeadersInit,
  filters: {
    classId?: string;
    courseId?: string;
    campus?: string;
    branch?: string;
    limit?: number;
  } = {},
): Promise<AnalyticsRolloutControlReport> {
  const params = new URLSearchParams();
  if (filters.classId?.trim()) params.set("class_id", filters.classId.trim());
  if (filters.courseId?.trim())
    params.set("course_id", filters.courseId.trim());
  if (filters.campus?.trim()) params.set("campus", filters.campus.trim());
  if (filters.branch?.trim()) params.set("branch", filters.branch.trim());
  params.set("limit", String(Math.max(1, Math.min(500, filters.limit || 100))));
  return parseResponse(
    await apiFetch(
      `${API}/analytics/ops/rollout-control?${params.toString()}`,
      { credentials: "include", headers },
    ),
  );
}

export async function getAnalyticsMonitoring(
  headers: HeadersInit,
  filters: { classId?: string; courseId?: string } = {},
): Promise<AnalyticsMonitoringReport> {
  const params = new URLSearchParams();
  if (filters.classId?.trim()) params.set("class_id", filters.classId.trim());
  if (filters.courseId?.trim())
    params.set("course_id", filters.courseId.trim());
  return parseResponse(
    await apiFetch(`${API}/analytics/ops/monitoring?${params.toString()}`, {
      credentials: "include",
      headers,
    }),
  );
}

export async function getAnalyticsPilotAcceptance(
  headers: HeadersInit,
  filters: {
    classId?: string;
    courseId?: string;
    campus?: string;
    branch?: string;
    sampleLimit?: number;
  } = {},
): Promise<AnalyticsPilotAcceptanceReport> {
  const params = new URLSearchParams();
  if (filters.classId?.trim()) params.set("class_id", filters.classId.trim());
  if (filters.courseId?.trim())
    params.set("course_id", filters.courseId.trim());
  if (filters.campus?.trim()) params.set("campus", filters.campus.trim());
  if (filters.branch?.trim()) params.set("branch", filters.branch.trim());
  params.set(
    "sample_limit",
    String(Math.max(1, Math.min(20, filters.sampleLimit || 5))),
  );
  return parseResponse(
    await apiFetch(
      `${API}/analytics/ops/pilot-acceptance?${params.toString()}`,
      { credentials: "include", headers },
    ),
  );
}


export async function getAnalyticsEvidencePack(
  headers: HeadersInit,
  filters: {
    classId?: string;
    courseId?: string;
    campus?: string;
    branch?: string;
    sampleLimit?: number;
  } = {},
): Promise<AnalyticsEvidencePackReport> {
  const params = new URLSearchParams();
  if (filters.classId?.trim()) params.set("class_id", filters.classId.trim());
  if (filters.courseId?.trim())
    params.set("course_id", filters.courseId.trim());
  if (filters.campus?.trim()) params.set("campus", filters.campus.trim());
  if (filters.branch?.trim()) params.set("branch", filters.branch.trim());
  params.set(
    "sample_limit",
    String(Math.max(1, Math.min(20, filters.sampleLimit || 5))),
  );
  return parseResponse(
    await apiFetch(`${API}/analytics/ops/evidence-pack?${params.toString()}`, {
      credentials: "include",
      headers,
    }),
  );
}

export async function getAnalyticsCourseClassMappingReport(
  headers: HeadersInit,
  filters: {
    classId?: string;
    courseId?: string;
    campus?: string;
    branch?: string;
    termId?: string;
    subjectId?: string;
    limit?: number;
  } = {},
): Promise<AnalyticsCourseClassMappingReport> {
  const params = new URLSearchParams();
  if (filters.classId?.trim()) params.set("class_id", filters.classId.trim());
  if (filters.courseId?.trim()) params.set("course_id", filters.courseId.trim());
  if (filters.campus?.trim()) params.set("campus", filters.campus.trim());
  if (filters.branch?.trim()) params.set("branch", filters.branch.trim());
  if (filters.termId?.trim()) params.set("term_id", filters.termId.trim());
  if (filters.subjectId?.trim()) params.set("subject_id", filters.subjectId.trim());
  params.set("limit", String(Math.max(1, Math.min(500, filters.limit || 50))));
  return parseResponse(
    await apiFetch(`${API}/analytics/ops/course-class-mapping?${params.toString()}`, {
      credentials: "include",
      headers,
    }),
  );
}

export async function getAnalyticsBackfillPlan(
  headers: HeadersInit,
  filters: {
    campus?: string;
    branch?: string;
    classId?: string;
    courseId?: string;
    limit?: number;
  } = {},
): Promise<AnalyticsBackfillPlanResponse> {
  const params = new URLSearchParams();
  if (filters.campus?.trim()) params.set("campus", filters.campus.trim());
  if (filters.branch?.trim()) params.set("branch", filters.branch.trim());
  if (filters.classId?.trim()) params.set("class_id", filters.classId.trim());
  if (filters.courseId?.trim())
    params.set("course_id", filters.courseId.trim());
  params.set("limit", String(Math.max(1, Math.min(200, filters.limit || 50))));
  return parseResponse(
    await apiFetch(`${API}/analytics/backfill/plan?${params.toString()}`, {
      credentials: "include",
      headers,
    }),
  );
}

export async function enqueueAnalyticsBackfillJobs(
  headers: HeadersInit,
  filters: {
    campus?: string;
    branch?: string;
    classId?: string;
    courseId?: string;
    limit?: number;
  } = {},
): Promise<AnalyticsBackfillJobsResponse> {
  const params = new URLSearchParams();
  if (filters.campus?.trim()) params.set("campus", filters.campus.trim());
  if (filters.branch?.trim()) params.set("branch", filters.branch.trim());
  if (filters.classId?.trim()) params.set("class_id", filters.classId.trim());
  if (filters.courseId?.trim())
    params.set("course_id", filters.courseId.trim());
  params.set("limit", String(Math.max(1, Math.min(50, filters.limit || 20))));
  return parseResponse(
    await apiFetch(`${API}/analytics/backfill/jobs?${params.toString()}`, {
      credentials: "include",
      method: "POST",
      headers,
    }),
  );
}

export async function getAnalyticsLearningDashboard(
  headers: HeadersInit,
  filters: {
    campus?: string;
    branch?: string;
    courseId?: string;
    classId?: string;
    classification?: string;
    dateFrom?: string;
    dateTo?: string;
    limit?: number;
  } = {},
): Promise<AnalyticsLearningDashboardResponse> {
  const params = new URLSearchParams();
  if (filters.campus?.trim()) params.set("campus", filters.campus.trim());
  if (filters.branch?.trim()) params.set("branch", filters.branch.trim());
  if (filters.courseId?.trim())
    params.set("course_id", filters.courseId.trim());
  if (filters.classId?.trim()) params.set("class_id", filters.classId.trim());
  if (filters.classification?.trim() && filters.classification !== "all")
    params.set("classification", filters.classification.trim());
  if (filters.dateFrom?.trim())
    params.set("date_from", filters.dateFrom.trim());
  if (filters.dateTo?.trim()) params.set("date_to", filters.dateTo.trim());
  params.set("limit", String(Math.max(1, Math.min(200, filters.limit || 50))));
  return parseResponse(
    await apiFetch(`${API}/analytics/learning/dashboard?${params.toString()}`, {
      credentials: "include",
      headers,
    }),
  );
}

export function buildAnalyticsLearningExportUrl(
  filters: {
    campus?: string;
    branch?: string;
    courseId?: string;
    classId?: string;
    classification?: string;
    dateFrom?: string;
    dateTo?: string;
  } = {},
) {
  const params = new URLSearchParams();
  if (filters.campus?.trim()) params.set("campus", filters.campus.trim());
  if (filters.branch?.trim()) params.set("branch", filters.branch.trim());
  if (filters.courseId?.trim())
    params.set("course_id", filters.courseId.trim());
  if (filters.classId?.trim()) params.set("class_id", filters.classId.trim());
  if (filters.classification?.trim() && filters.classification !== "all")
    params.set("classification", filters.classification.trim());
  if (filters.dateFrom?.trim())
    params.set("date_from", filters.dateFrom.trim());
  if (filters.dateTo?.trim()) params.set("date_to", filters.dateTo.trim());
  return `${API}/analytics/learning/export.csv?${params.toString()}`;
}

export async function getAnalyticsClassVideoSummary(
  headers: HeadersInit,
  classId: string,
  courseId?: string | null,
): Promise<AnalyticsClassVideoSummary> {
  const params = new URLSearchParams();
  if (courseId?.trim()) params.set("course_id", courseId.trim());
  return parseResponse(
    await apiFetch(
      `${API}/analytics/classes/${encodeURIComponent(classId)}/video-summary?${params.toString()}`,
      { credentials: "include", headers },
    ),
  );
}

export async function getAnalyticsClassSessionsProgress(
  headers: HeadersInit,
  classId: string,
  courseId?: string | null,
): Promise<AnalyticsClassSessionProgressResponse> {
  const params = new URLSearchParams();
  if (courseId?.trim()) params.set("course_id", courseId.trim());
  return parseResponse(
    await apiFetch(
      `${API}/analytics/classes/${encodeURIComponent(classId)}/sessions/progress?${params.toString()}`,
      { credentials: "include", headers },
    ),
  );
}

export async function getAnalyticsSubjectClassBehaviorOverview(
  headers: HeadersInit,
  subjectId: string,
  filters: {
    termId?: string | null;
    campus?: string | null;
    branch?: string | null;
    classification?: string;
    classId?: string | null;
    limit?: number;
    offset?: number;
  } = {},
): Promise<AnalyticsClassBehaviorOverviewResponse> {
  const params = new URLSearchParams();
  if (filters.termId?.trim()) params.set("term_id", filters.termId.trim());
  if (filters.campus?.trim()) params.set("campus", filters.campus.trim());
  if (filters.branch?.trim()) params.set("branch", filters.branch.trim());
  if (filters.classification?.trim() && filters.classification !== "all")
    params.set("classification", filters.classification.trim());
  if (filters.classId?.trim()) params.set("class_id", filters.classId.trim());
  params.set("limit", String(Math.max(1, Math.min(500, filters.limit || 200))));
  params.set("offset", String(Math.max(0, filters.offset || 0)));
  return parseResponse(
    await apiFetch(
      `${API}/analytics/subjects/${encodeURIComponent(subjectId)}/classes/learning-behavior/overview?${params.toString()}`,
      { credentials: "include", headers },
    ),
  );
}


export async function getAnalyticsClassResultDoctor(
  headers: HeadersInit,
  classId: string,
  courseId?: string | null,
): Promise<AnalyticsClassResultDoctor> {
  const params = new URLSearchParams();
  if (courseId?.trim()) params.set("course_id", courseId.trim());
  return parseResponse(
    await apiFetch(
      `${API}/analytics/classes/${encodeURIComponent(classId)}/doctor?${params.toString()}`,
      { credentials: "include", headers },
    ),
  );
}

export async function enqueueAnalyticsClassDoctorRecalculate(
  headers: HeadersInit,
  classId: string,
  courseId?: string | null,
  payload: { force?: boolean; limit?: number | null } = {},
): Promise<AcademicClassSyncJob> {
  const params = new URLSearchParams();
  if (courseId?.trim()) params.set("course_id", courseId.trim());
  if (payload.force) params.set("force", "true");
  if (payload.limit) params.set("limit", String(payload.limit));
  return parseResponse(
    await apiFetch(
      `${API}/analytics/classes/${encodeURIComponent(classId)}/doctor/recalculate?${params.toString()}`,
      { method: "POST", credentials: "include", headers },
    ),
  );
}

export async function getAnalyticsClassWorkspace(
  headers: HeadersInit,
  classId: string,
  filters: {
    courseId?: string | null;
    classification?: string;
    limit?: number;
    offset?: number;
  } = {},
): Promise<AnalyticsClassWorkspaceResponse> {
  const params = new URLSearchParams();
  if (filters.courseId?.trim()) params.set("course_id", filters.courseId.trim());
  if (filters.classification?.trim() && filters.classification !== "all")
    params.set("classification", filters.classification.trim());
  params.set("limit", String(Math.max(1, Math.min(200, filters.limit || 100))));
  params.set("offset", String(Math.max(0, filters.offset || 0)));
  return parseResponse(
    await apiFetch(
      `${API}/analytics/classes/${encodeURIComponent(classId)}/workspace?${params.toString()}`,
      { credentials: "include", headers },
    ),
  );
}

export async function getAnalyticsClassLearningBehaviorSummary(
  headers: HeadersInit,
  classId: string,
  courseId?: string | null,
): Promise<AnalyticsLearningBehaviorSummary> {
  const params = new URLSearchParams();
  if (courseId?.trim()) params.set("course_id", courseId.trim());
  return parseResponse(
    await apiFetch(
      `${API}/analytics/classes/${encodeURIComponent(classId)}/learning-behavior/summary?${params.toString()}`,
      { credentials: "include", headers },
    ),
  );
}

export async function getAnalyticsClassLearningBehavior(
  headers: HeadersInit,
  classId: string,
  filters: {
    courseId?: string | null;
    classification?: string;
    limit?: number;
    offset?: number;
  } = {},
): Promise<AnalyticsLearningBehaviorListResponse> {
  const params = new URLSearchParams();
  if (filters.courseId?.trim())
    params.set("course_id", filters.courseId.trim());
  if (filters.classification?.trim() && filters.classification !== "all")
    params.set("classification", filters.classification.trim());
  params.set("limit", String(Math.max(1, Math.min(200, filters.limit || 100))));
  params.set("offset", String(Math.max(0, filters.offset || 0)));
  return parseResponse(
    await apiFetch(
      `${API}/analytics/classes/${encodeURIComponent(classId)}/learning-behavior?${params.toString()}`,
      { credentials: "include", headers },
    ),
  );
}

export async function getAnalyticsStudentLearningBehaviorDetail(
  headers: HeadersInit,
  classId: string,
  username: string,
  courseId?: string | null,
): Promise<AnalyticsStudentLearningBehaviorDetail> {
  const params = new URLSearchParams();
  if (courseId?.trim()) params.set("course_id", courseId.trim());
  return parseResponse(
    await apiFetch(
      `${API}/analytics/classes/${encodeURIComponent(classId)}/students/${encodeURIComponent(username)}/learning-behavior?${params.toString()}`,
      { credentials: "include", headers },
    ),
  );
}

export async function recalculateAnalyticsClassLearningBehavior(
  headers: HeadersInit,
  classId: string,
  courseId: string,
  username?: string | null,
): Promise<JsonObject> {
  const params = new URLSearchParams();
  params.set("course_id", courseId);
  if (username?.trim()) params.set("username", username.trim());
  return parseResponse(
    await apiFetch(
      `${API}/analytics/classes/${encodeURIComponent(classId)}/learning-behavior/recalculate?${params.toString()}`,
      { method: "POST", credentials: "include", headers },
    ),
  );
}

export async function syncAcademicClassEnrollment(
  headers: HeadersInit,
  classId: string,
  payload: { force?: boolean; limit?: number; mode?: string } = {},
): Promise<AcademicEnrollmentSyncResult> {
  return parseResponse(
    await apiFetch(
      `${API}/academic/classes/${encodeURIComponent(classId)}/cms-enrollment-sync`,
      {
        method: "POST",
        headers,
        body: JSON.stringify({
          force: Boolean(payload.force),
          limit: payload.limit || 500,
          mode: payload.mode || null,
        }),
      },
    ),
  );
}

export async function syncAcademicClassLearning(
  headers: HeadersInit,
  classId: string,
  payload: { force?: boolean; limit?: number } = {},
): Promise<AcademicLearningSyncResult> {
  return parseResponse(
    await apiFetch(
      `${API}/academic/classes/${encodeURIComponent(classId)}/learning-sync`,
      {
        method: "POST",
        headers,
        body: JSON.stringify({
          force: Boolean(payload.force),
          limit: payload.limit || 500,
        }),
      },
    ),
  );
}

export async function enqueueAcademicClassCmsSyncJob(
  headers: HeadersInit,
  classId: string,
  payload: { force?: boolean; limit?: number } = {},
): Promise<AcademicClassSyncJob> {
  return parseResponse(
    await apiFetch(
      `${API}/academic/classes/${encodeURIComponent(classId)}/cms-sync-check/jobs`,
      {
        method: "POST",
        headers,
        body: JSON.stringify({
          force: Boolean(payload.force),
          limit: payload.limit || 500,
        }),
      },
    ),
  );
}

export async function enqueueAcademicClassEnrollmentSyncJob(
  headers: HeadersInit,
  classId: string,
  payload: { force?: boolean; limit?: number; mode?: string } = {},
): Promise<AcademicClassSyncJob> {
  return parseResponse(
    await apiFetch(
      `${API}/academic/classes/${encodeURIComponent(classId)}/cms-enrollment-sync/jobs`,
      {
        method: "POST",
        headers,
        body: JSON.stringify({
          force: Boolean(payload.force),
          limit: payload.limit || 500,
          mode: payload.mode || null,
        }),
      },
    ),
  );
}

export async function enqueueAcademicClassLearningSyncJob(
  headers: HeadersInit,
  classId: string,
  payload: { force?: boolean; limit?: number } = {},
): Promise<AcademicClassSyncJob> {
  return parseResponse(
    await apiFetch(
      `${API}/academic/classes/${encodeURIComponent(classId)}/learning-sync/jobs`,
      {
        method: "POST",
        headers,
        body: JSON.stringify({
          force: Boolean(payload.force),
          limit: payload.limit || 500,
        }),
      },
    ),
  );
}

export async function enqueueAcademicClassFullCmsSyncJob(
  headers: HeadersInit,
  classId: string,
  payload: {
    force?: boolean;
    limit?: number;
    mode?: string;
    autoMapCourse?: boolean;
    syncLearning?: boolean;
  } = {},
): Promise<AcademicClassSyncJob> {
  return parseResponse(
    await apiFetch(
      `${API}/academic/classes/${encodeURIComponent(classId)}/full-cms-sync/jobs`,
      {
        method: "POST",
        headers,
        body: JSON.stringify({
          force: Boolean(payload.force),
          limit: payload.limit || 500,
          mode: payload.mode || null,
          auto_map_course: payload.autoMapCourse !== false,
          sync_learning: payload.syncLearning !== false,
        }),
      },
    ),
  );
}

export async function getAcademicClassSyncJob(
  headers: HeadersInit,
  classId: string,
  jobId: string,
): Promise<AcademicClassSyncJob> {
  return parseResponse(
    await apiFetch(
      `${API}/academic/classes/${encodeURIComponent(classId)}/sync-jobs/${encodeURIComponent(jobId)}`,
      { credentials: "include", headers },
    ),
  );
}

export async function getAcademicClassSyncJobs(
  headers: HeadersInit,
  classId: string,
  limit = 10,
): Promise<AcademicClassSyncJob[]> {
  const params = new URLSearchParams();
  params.set("limit", String(Math.max(1, Math.min(50, limit))));
  return parseResponse(
    await apiFetch(
      `${API}/academic/classes/${encodeURIComponent(classId)}/sync-jobs?${params.toString()}`,
      { credentials: "include", headers },
    ),
  );
}

export async function getRecentAcademicClassSyncJobs(
  headers: HeadersInit,
  filters: {
    status?:
      "active" | "queued" | "running" | "completed" | "failed" | "all" | string;
    classId?: string;
    limit?: number;
  } = {},
): Promise<AcademicClassSyncJob[]> {
  const params = new URLSearchParams();
  if (filters.status) params.set("status", filters.status);
  if (filters.classId?.trim()) params.set("class_id", filters.classId.trim());
  params.set("limit", String(Math.max(1, Math.min(100, filters.limit || 30))));
  return parseResponse(
    await apiFetch(`${API}/academic/sync/class-jobs?${params.toString()}`, {
      credentials: "include",
      headers,
    }),
  );
}

export async function getAcademicCampuses(
  headers: HeadersInit,
  filters: { branch?: string; active?: boolean | null } = {},
): Promise<AcademicCampus[]> {
  const params = new URLSearchParams();
  if (filters.branch?.trim()) params.set("branch", filters.branch.trim());
  if (typeof filters.active === "boolean")
    params.set("active", String(filters.active));
  return parseResponse(
    await apiFetch(`${API}/academic/campuses?${params.toString()}`, {
      credentials: "include",
      headers,
    }),
  );
}

export async function saveAcademicCampus(
  headers: HeadersInit,
  payload: {
    campus_code: string;
    campus_name: string;
    branch?: string;
    active?: boolean;
    sort_order?: number;
  },
): Promise<AcademicCampus> {
  return parseResponse(
    await apiFetch(`${API}/academic/campuses`, {
      method: "POST",
      headers,
      body: JSON.stringify(payload),
    }),
  );
}

export async function updateAcademicCampus(
  headers: HeadersInit,
  campusId: string,
  payload: {
    campus_code?: string;
    campus_name?: string;
    branch?: string;
    active?: boolean;
    sort_order?: number;
  },
): Promise<AcademicCampus> {
  return parseResponse(
    await apiFetch(`${API}/academic/campuses/${encodeURIComponent(campusId)}`, {
      method: "PATCH",
      headers,
      body: JSON.stringify(payload),
    }),
  );
}

export async function deleteAcademicCampus(
  headers: HeadersInit,
  campusId: string,
): Promise<AcademicCampus> {
  return parseResponse(
    await apiFetch(`${API}/academic/campuses/${encodeURIComponent(campusId)}`, {
      method: "DELETE",
      headers,
    }),
  );
}

export async function getAcademicApSyncOptions(
  headers: HeadersInit,
  filters: {
    termName?: string;
    branch?: string;
    campus?: string;
    includeSubjects?: boolean;
  } = {},
): Promise<AcademicAPSyncOptions> {
  const params = new URLSearchParams();
  if (filters.termName?.trim())
    params.set("term_name", filters.termName.trim());
  if (filters.branch?.trim()) params.set("branch", filters.branch.trim());
  if (filters.campus?.trim()) params.set("campus", filters.campus.trim());
  if (filters.includeSubjects === false)
    params.set("include_subjects", "false");
  return parseResponse(
    await apiFetch(`${API}/academic/sync/ap/options?${params.toString()}`, {
      credentials: "include",
      headers,
    }),
  );
}

export async function syncAcademicFromAp(
  headers: HeadersInit,
  payload: {
    term_name: string;
    sync_scope?: "all" | "campus" | "subject";
    campus?: string;
    campuses?: string[];
    branch?: string;
    subject_codes?: string[];
    max_subjects?: number;
    dry_run?: boolean;
  },
): Promise<AcademicSyncResult> {
  return parseResponse(
    await apiFetch(`${API}/academic/sync/ap`, {
      method: "POST",
      headers,
      body: JSON.stringify(payload),
    }),
  );
}

export async function enqueueAcademicApSyncJob(
  headers: HeadersInit,
  payload: {
    term_name: string;
    sync_scope?: "all" | "campus" | "subject";
    campus?: string;
    campuses?: string[];
    branch?: string;
    subject_codes?: string[];
    max_subjects?: number;
    dry_run?: boolean;
  },
): Promise<AcademicSyncResult> {
  return parseResponse(
    await apiFetch(`${API}/academic/sync/ap/jobs`, {
      method: "POST",
      headers,
      body: JSON.stringify(payload),
    }),
  );
}

export async function getAcademicApSyncJobs(
  headers: HeadersInit,
  filters: {
    termName?: string;
    branch?: string;
    status?: "active" | "queued" | "running" | "completed" | "failed" | "all";
    limit?: number;
  } = {},
): Promise<AcademicSyncRun[]> {
  const params = new URLSearchParams();
  if (filters.termName?.trim())
    params.set("term_name", filters.termName.trim());
  if (filters.branch?.trim()) params.set("branch", filters.branch.trim());
  if (filters.status) params.set("status", filters.status);
  if (filters.limit) params.set("limit", String(filters.limit));
  return parseResponse(
    await apiFetch(`${API}/academic/sync/ap/jobs?${params.toString()}`, {
      credentials: "include",
      headers,
    }),
  );
}

export async function getAcademicApSyncJob(
  headers: HeadersInit,
  runId: string,
): Promise<AcademicSyncRun> {
  return parseResponse(
    await apiFetch(
      `${API}/academic/sync/ap/jobs/${encodeURIComponent(runId)}`,
      { credentials: "include", headers },
    ),
  );
}

export async function checkAcademicClassCmsSync(
  headers: HeadersInit,
  classId: string,
  payload: { force?: boolean; limit?: number } = {},
): Promise<AcademicMappingResolveResult> {
  return parseResponse(
    await apiFetch(
      `${API}/academic/classes/${encodeURIComponent(classId)}/cms-sync-check`,
      {
        method: "POST",
        headers,
        body: JSON.stringify({
          force: Boolean(payload.force),
          limit: payload.limit || 500,
        }),
      },
    ),
  );
}

export async function resolveAcademicClassOpenEdxUsers(
  headers: HeadersInit,
  classId: string,
  payload: { force?: boolean; limit?: number } = {},
): Promise<AcademicMappingResolveResult> {
  return checkAcademicClassCmsSync(headers, classId, payload);
}

export async function importAcademicOpenEdxUserMappings(
  headers: HeadersInit,
  records: Array<Record<string, unknown>>,
): Promise<AcademicManualMappingImportResult> {
  return parseResponse(
    await apiFetch(`${API}/academic/openedx-user-mappings/import`, {
      method: "POST",
      headers,
      body: JSON.stringify({ records }),
    }),
  );
}

export async function getAcademicCourseMappings(
  headers: HeadersInit,
  filters: {
    termId?: string;
    blockId?: string;
    subjectId?: string;
    search?: string;
    page?: number;
    pageSize?: number;
  } = {},
): Promise<AcademicCourseMappingListResponse> {
  const params = new URLSearchParams();
  if (filters.termId) params.set("term_id", filters.termId);
  if (filters.blockId) params.set("block_id", filters.blockId);
  if (filters.subjectId) params.set("subject_id", filters.subjectId);
  if (filters.search?.trim()) params.set("search", filters.search.trim());
  params.set("page", String(filters.page || 1));
  params.set("page_size", String(filters.pageSize || 50));
  return parseResponse(
    await apiFetch(`${API}/academic/course-mappings?${params.toString()}`, {
      credentials: "include",
      headers,
    }),
  );
}

export async function validateAcademicCourseMapping(
  headers: HeadersInit,
  payload: {
    term_id: string;
    subject_id: string;
    openedx_course_id: string;
    block_id?: string | null;
    campus?: string | null;
    branch?: string | null;
    openedx_course_title?: string | null;
  },
): Promise<AcademicCourseMappingValidation> {
  return parseResponse(
    await apiFetch(`${API}/academic/course-mappings/validate`, {
      method: "POST",
      headers,
      body: JSON.stringify(payload),
    }),
  );
}

export async function saveAcademicCourseMapping(
  headers: HeadersInit,
  payload: {
    term_id: string;
    subject_id: string;
    openedx_course_id: string;
    block_id?: string | null;
    campus?: string | null;
    branch?: string | null;
    openedx_course_title?: string | null;
    allow_warnings?: boolean;
    note?: string | null;
  },
): Promise<AcademicCourseMapping> {
  return parseResponse(
    await apiFetch(`${API}/academic/course-mappings`, {
      method: "POST",
      headers,
      body: JSON.stringify(payload),
    }),
  );
}

export async function getAcademicClassCourseMappingProposal(
  headers: HeadersInit,
  classId: string,
): Promise<AcademicClassCourseMappingProposal> {
  return parseResponse(
    await apiFetch(
      `${API}/academic/classes/${encodeURIComponent(classId)}/course-mapping/proposal`,
      { credentials: "include", headers },
    ),
  );
}

export async function validateAcademicClassCourseMapping(
  headers: HeadersInit,
  classId: string,
  payload: {
    openedx_course_id: string;
    openedx_cohort_name?: string | null;
    openedx_course_title?: string | null;
  },
): Promise<AcademicCourseMappingValidation> {
  return parseResponse(
    await apiFetch(
      `${API}/academic/classes/${encodeURIComponent(classId)}/course-mapping/validate`,
      { method: "POST", headers, body: JSON.stringify(payload) },
    ),
  );
}

export async function saveAcademicClassCourseMapping(
  headers: HeadersInit,
  classId: string,
  payload: {
    openedx_course_id: string;
    openedx_cohort_name?: string | null;
    openedx_course_title?: string | null;
    allow_warnings?: boolean;
    cleanup_previous_course?: boolean;
    note?: string | null;
  },
): Promise<AcademicClassCourseMapping> {
  return parseResponse(
    await apiFetch(
      `${API}/academic/classes/${encodeURIComponent(classId)}/course-mapping`,
      { method: "POST", headers, body: JSON.stringify(payload) },
    ),
  );
}

export async function getAnalyticsOpsStatus(
  headers: HeadersInit,
): Promise<AnalyticsOpsStatus> {
  return parseResponse(
    await apiFetch(`${API}/analytics/ops/status`, {
      credentials: "include",
      headers,
    }),
  );
}

export async function enqueueAnalyticsIngestJob(
  headers: HeadersInit,
  payload: { filePath?: string | null; maxLines?: number | null } = {},
): Promise<AnalyticsIngestJobResponse> {
  return parseResponse(
    await apiFetch(`${API}/analytics/ingest/jobs`, {
      method: "POST",
      credentials: "include",
      headers: { ...headers, "Content-Type": "application/json" },
      body: JSON.stringify({
        file_path: payload.filePath?.trim() || null,
        max_lines: payload.maxLines ?? null,
      }),
    }),
  );
}

export async function enqueueAnalyticsClassLearningBehaviorJob(
  headers: HeadersInit,
  classId: string,
  courseId: string,
  payload: {
    username?: string | null;
    force?: boolean;
    limit?: number | null;
  } = {},
): Promise<AcademicClassSyncJob> {
  const params = new URLSearchParams();
  params.set("course_id", courseId);
  if (payload.username?.trim()) params.set("username", payload.username.trim());
  if (payload.force) params.set("force", "true");
  if (payload.limit) params.set("limit", String(payload.limit));
  return parseResponse(
    await apiFetch(
      `${API}/analytics/classes/${encodeURIComponent(classId)}/learning-behavior/jobs?${params.toString()}`,
      { method: "POST", credentials: "include", headers },
    ),
  );
}
