export type JsonPrimitive = string | number | boolean | null
export type JsonValue = JsonPrimitive | undefined | JsonValue[] | { [key: string]: JsonValue }
export type JsonObject = { [key: string]: JsonValue }

export type UiStatus = 'success' | 'error' | 'warning' | 'info'
export type BackendUiNotice = {
  ui_status?: UiStatus | string | null
  ui_title?: string | null
  ui_message?: string | null
}

export type Role = 'admin' | 'teacher' | 'reviewer' | 'viewer'

export type Permission =
  | 'sync_course'
  | 'estimate_cost'
  | 'generate_questions'
  | 'edit_questions'
  | 'delete_questions'
  | 'review_questions'
  | 'publish_questions'
  | 'export_questions'
  | 'publish_to_openedx'
  | 'view_dashboard'
  | 'view_jobs'
  | 'view_questions'
  | 'manage_settings'
  | 'view_user_analytics'

export const ROLE_LABELS: Record<Role, string> = {
  admin: 'Quản trị viên - toàn quyền',
  teacher: 'Giảng viên - đồng bộ/tạo/duyệt/publish',
  reviewer: 'Người duyệt - duyệt/sửa câu hỏi',
  viewer: 'Người xem - chỉ xem',
}

export const ROLE_PERMISSIONS: Record<Role, Permission[]> = {
  admin: ['sync_course', 'estimate_cost', 'generate_questions', 'edit_questions', 'delete_questions', 'review_questions', 'publish_questions', 'export_questions', 'publish_to_openedx', 'view_dashboard', 'view_jobs', 'view_questions', 'manage_settings', 'view_user_analytics'],
  teacher: ['sync_course', 'estimate_cost', 'generate_questions', 'edit_questions', 'delete_questions', 'review_questions', 'publish_questions', 'export_questions', 'publish_to_openedx', 'view_dashboard', 'view_jobs', 'view_questions'],
  reviewer: ['estimate_cost', 'edit_questions', 'review_questions', 'export_questions', 'view_dashboard', 'view_jobs', 'view_questions'],
  viewer: ['view_dashboard', 'view_jobs', 'view_questions'],
}


export type PaginatedResponse<T> = {
  items: T[]
  total: number
  total_tokens?: number
  page: number
  page_size: number
  total_pages: number
  has_next?: boolean
}

export type CursorPaginatedResponse<T> = {
  items: T[]
  limit: number
  has_next: boolean
  next_cursor?: { created_at?: string | null; id?: string | null } | null
  total?: number | null
}

export type CostEstimateOutputCalibration = {
  strategy?: string | null
  multiplier?: number | null
  sample_size?: number | null
}

export type CostEstimateLike = {
  estimated_input_tokens?: number | null
  estimated_cached_input_tokens?: number | null
  estimated_output_tokens?: number | null
  estimated_output_tokens_per_question?: number | null
  estimated_raw_cost_usd?: number | null
  estimated_cost_usd?: number | null
  estimated_cost_vnd?: number | null
  model_name?: string | null
  token_source?: string | null
  estimate_token_source?: string | null
  quota_message?: string | null
  output_calibration?: CostEstimateOutputCalibration | null
}

export type QuestionStatus = 'pending_review' | 'approved' | 'rejected' | 'published' | 'draft_error' | string

export type Question = {
  id: string
  course_id: string
  lesson_id?: string | null
  lesson_title?: string | null
  block_id?: string | null
  node_id?: string | null
  node_title?: string | null
  topic?: string | null
  concept_id?: string | null
  concept_title?: string | null
  concept_key?: string | null
  question_family_id?: string | null
  variant_no?: number | null
  source_evidence?: string | null
  difficulty: string
  cognitive_level: string
  learning_objective: string
  question_type: string
  question_text: string
  option_a: string
  option_b: string
  option_c: string
  option_d: string
  correct_answer: string
  explanation: string
  source_ref: string
  source_type: string
  source_page?: number | null
  source_timestamp_start?: string | null
  source_timestamp_end?: string | null
  source_chunk_id?: string | null
  source_node_id?: string | null
  source_node_title?: string | null
  chapter_node_id?: string | null
  chapter_title?: string | null
  target_library_id?: string | null
  target_library_key?: string | null
  source_excerpt: string
  tags?: string[] | null
  quality_score: number
  quality_flags?: string[] | null
  draft_error_reason?: string | null
  draft_error_detail?: Record<string, any> | null
  repair_attempt_count?: number
  is_duplicate: boolean
  duplicate_score?: number | null
  duplicate_of_question_id?: string | null
  model_provider: string
  model_name: string
  status: QuestionStatus
  version: number
  reviewed_by?: string | null
  reviewed_at?: string | null
  published_at?: string | null
  openedx_block_id?: string | null
  openedx_library_problem_id?: string | null
  imported_library_at?: string | null
  publish_error?: string | null
  publish_status?: string | null
  publish_verification_json?: Record<string, any> | null
  published_by?: string | null
  openedx_publish_status?: string | null
  openedx_verification_status?: string | null
  openedx_delete_status?: string | null
  openedx_manual_action_required?: boolean | null
  created_at: string
  updated_at: string
}

export type Job = {
  id: string
  course_id: string
  question_count: number
  status: string
  estimated_input_tokens: number
  estimated_cached_input_tokens: number
  estimated_uncached_input_tokens: number
  estimated_output_tokens: number
  estimated_raw_cost_usd: number
  estimated_cost_usd: number
  estimated_cost_vnd: number
  estimate_token_source?: string | null
  estimated_output_tokens_per_question?: number
  output_calibration?: string | null
  actual_input_tokens: number
  actual_cached_input_tokens: number
  actual_uncached_input_tokens: number
  actual_output_tokens: number
  actual_cost_usd: number
  actual_cost_vnd: number
  usage_token_source?: string | null
  estimate_accuracy_percent: number
  input_accuracy_percent?: number
  output_accuracy_percent?: number
  actual_output_tokens_per_question?: number
  output_delta_tokens?: number
  cost_delta_usd: number
  completed_question_count?: number
  openai_response_ids?: string | null
  model_parse_error?: string | null
  error_message?: string | null
}


export type BankOperationJob = {
  id: string
  operation_type: string
  status: string
  target_type: string
  target_id?: string | null
  bank_version_id?: string | null
  release_id?: string | null
  material_version_id?: string | null
  course_quiz_instance_id?: string | null
  requested_by?: string | null
  course_id?: string | null
  progress_current: number
  progress_total: number
  progress_percent: number
  progress_label: string
  request?: Record<string, unknown>
  result?: Record<string, unknown>
  celery_task_id?: string | null
  task_name?: string | null
  enqueued_at?: string | null
  retry_token?: string | null
  enqueue_history?: Array<Record<string, unknown>>
  error_message?: string | null
  created_at?: string | null
  started_at?: string | null
  finished_at?: string | null
  updated_at?: string | null
}

export type BankOperationJobQueued = {
  ok: boolean
  job: BankOperationJob
  message: string
}

export type QuestionStats = {
  total: number
  pending_review: number
  approved: number
  rejected: number
  published: number
  draft_error: number
  openedx_verified?: number
  openedx_pending?: number
  openedx_manual_delete_required?: number
}

export type CourseChunk = {
  id: string
  course_id: string
  block_id: string
  node_id?: string | null
  node_title?: string | null
  content: string
  token_count: number
  source_type: string
  page_number?: number | null
  timestamp_start?: string | null
  timestamp_end?: string | null
  source_ref?: string | null
  created_at: string
}


export type Topic = {
  id: string
  course_id: string
  lesson_id?: string | null
  title: string
  summary: string
  importance_score: number
  chunk_count: number
  token_count: number
}

export type CourseTreeNode = {
  node_id: string
  parent_id?: string | null
  block_type: string
  title: string
  path: string
  chunk_count: number
  token_count: number
  children: CourseTreeNode[]
}


export type CourseOption = {
  course_id: string
  title: string
  node_count: number
  chunk_count: number
  token_count: number
  last_synced_at?: string | null
}

export type CourseNodeOption = {
  node_id: string
  parent_id?: string | null
  block_type: string
  title: string
  path: string
  depth: number
  chunk_count: number
  token_count: number
}

export type Concept = {
  id: string
  course_id: string
  chapter_node_id?: string | null
  source_node_id?: string | null
  source_node_title?: string | null
  concept_key: string
  title: string
  summary: string
  learning_objective: string
  difficulty_hint: string
  importance_score: number
  source_chunk_ids?: string[] | null
  source_evidence: string
  token_count: number
  status: string
  metadata_json?: Record<string, any> | null
  created_at: string
  updated_at: string
}

export type ConceptExtractResponse = {
  course_id: string
  node_id?: string | null
  concept_count: number
  reused_existing: boolean
  concepts: Concept[]
}

export type ConceptListResponse = {
  course_id: string
  node_id?: string | null
  total: number
  concepts: Concept[]
}

export type CourseFileUploadResponse = {
  course_id: string
  node_id: string
  parent_node_id?: string | null
  filename: string
  source_type: string
  chunks_created: number
  tokens_indexed: number
  status: string
  message?: string
}

export type CourseNodeDeleteResponse = {
  course_id: string
  node_id: string
  deleted_nodes: number
  deleted_chunks: number
  status: string
  message?: string
}

export type CourseCleanResyncResponse = {
  course_id: string
  deleted_nodes: number
  deleted_chunks: number
  deleted_topics?: number
  blocks_seen: number
  changed_blocks: number
  status: string
  message?: string
}

export type AnalyticsOverview = {
  questions: {
    total: number
    by_status: Record<string, number>
    by_difficulty: Record<string, number>
    by_cognitive_level: Record<string, number>
    top_scopes: { scope: string; count: number }[]
    approve_rate_percent: number
    duplicate_count: number
    quality_average: number
    openedx?: {
      verified: number
      pending: number
      manual_action_required: number
      delete_failed_or_manual: number
    }
  }
  jobs: {
    total: number
    by_status: Record<string, number>
    retry_total: number
    failed_jobs: number
    estimated_cost_usd: number
    estimated_raw_cost_usd: number
    actual_job_cost_usd: number
    estimate_accuracy_percent: number
    output_accuracy_percent?: number
    estimated_output_tokens_per_question?: number
    actual_output_tokens_per_question?: number
    output_delta_tokens?: number
    cost_delta_usd: number
    estimated_input_tokens: number
    estimated_output_tokens: number
    actual_input_tokens: number
    actual_cached_input_tokens: number
    actual_output_tokens: number
  }
  cost: {
    total_usage_cost_usd: number
    total_usage_cost_vnd: number
    monthly_budget_usd: number
    budget_used_percent: number
    by_feature: Record<string, number>
    by_model: Record<string, number>
    actual_input_tokens: number
    actual_cached_input_tokens: number
    actual_uncached_input_tokens: number
    actual_output_tokens: number
  }
  course_sync: {
    nodes: number
    chunks: number
    content_hash_rows: number
    tokens_indexed: number
    by_source_type: Record<string, number>
  }
  governance: {
    quota_max_questions_per_course: number
    quota_used_percent: number
    hard_stop_enabled: boolean
    review_log_count: number
  }
}

export type QuestionFilters = {
  status: string
  difficulty: string
  nodeId?: string
  sourceType?: string
  search: string
  sortBy: string
  sortDir: string
}

export type EditQuestionForm = {
  topic: string
  node_title: string
  difficulty: string
  cognitive_level: string
  learning_objective: string
  question_text: string
  option_a: string
  option_b: string
  option_c: string
  option_d: string
  correct_answer: string
  explanation: string
  source_ref: string
  source_type: string
  source_page: string
  source_timestamp_start: string
  source_timestamp_end: string
  source_chunk_id: string
  source_excerpt: string
  question_family_id: string
  variant_no: string
  source_evidence: string
  tags_text: string
  target_status: string
}

export function toEditForm(question: Question): EditQuestionForm {
  return {
    topic: question.node_title || question.topic || '',
    node_title: question.node_title || question.topic || '',
    difficulty: question.difficulty || 'easy',
    cognitive_level: question.cognitive_level || 'remember',
    learning_objective: question.learning_objective || '',
    question_text: question.question_text || '',
    option_a: question.option_a || '',
    option_b: question.option_b || '',
    option_c: question.option_c || '',
    option_d: question.option_d || '',
    correct_answer: question.correct_answer || 'A',
    explanation: question.explanation || '',
    source_ref: question.source_ref || '',
    source_type: question.source_type || 'course_component',
    source_page: question.source_page ? String(question.source_page) : '',
    source_timestamp_start: question.source_timestamp_start || '',
    source_timestamp_end: question.source_timestamp_end || '',
    source_chunk_id: question.source_chunk_id || '',
    source_excerpt: question.source_excerpt || '',
    question_family_id: question.question_family_id || '',
    variant_no: question.variant_no ? String(question.variant_no) : '',
    source_evidence: question.source_evidence || '',
    tags_text: (question.tags || []).join(', '),
    target_status: ['pending_review', 'approved', 'rejected'].includes(question.status) ? question.status : 'pending_review',
  }
}


export type UserAnalyticsRow = {
  user_id: string
  generate_jobs: number
  questions_requested: number
  approved: number
  rejected: number
  published: number
  edits: number
  input_tokens: number
  cached_input_tokens: number
  uncached_input_tokens: number
  output_tokens: number
  estimated_cost_usd: number
  actual_cost_usd: number
  estimate_accuracy_percent: number
  cost_usd: number
  cost_vnd: number
  last_activity?: string | null
  audit_actions?: number
  audit_failed?: number
  bank_entity_changes?: number
  quiz_creates?: number
  release_publishes?: number
  rollbacks?: number
  last_action?: string | null
}

export type UserAnalyticsResponse = {
  course_id?: string | null
  total_users: number
  users: UserAnalyticsRow[]
}


export type RuntimeSettings = {
  model: {
    model_provider: string
    openai_model: string
    openai_api_mode: string
    mock_llm: boolean
    has_openai_api_key: boolean
    openai_api_key_masked: string
  }
  openedx: {
    use_mock_openedx: boolean
    openedx_base_url: string
    openedx_cms_base_url: string
    openedx_lms_base_url: string
    openedx_oauth_base_url: string
    openedx_client_id: string
    has_openedx_client_secret: boolean
    openedx_client_secret_masked: string
    has_openedx_access_token: boolean
    openedx_access_token_masked: string
    openedx_oauth_token_url: string
    openedx_course_blocks_path: string
    openedx_publish_endpoint: string
    openedx_library_endpoint: string
    openedx_library_import_endpoint: string
  }
  sso: {
    auth_mode: string
    allow_demo_role_header: boolean
    has_jwt_secret: boolean
    jwt_secret_masked: string
  }
  cost: {
    cost_input_price_per_1m: number
    cost_cached_input_price_per_1m: number
    cost_output_price_per_1m: number
    cost_safety_factor: number
    usd_to_vnd: number
  }
  worker?: {
    openai_parallel_enabled: boolean
    openai_max_parallel_calls: number
    openai_retry_max_attempts: number
    openai_retry_base_seconds: number
    openai_prompt_cache_warmup_enabled: boolean
    generation_tail_batch_wait_enabled: boolean
  }
  runtime_config_path: string
}

export type PricingResponse = {
  model: string
  input_price_per_1m: number
  cached_input_price_per_1m: number
  output_price_per_1m: number
  currency: string
  unit: string
  service_tier: string
  context: string
  source: string
  fetched_at?: number | null
  fetched_at_iso?: string | null
  note?: string | null
}

export type RuntimeSettingsUpdate = {
  model: {
    model_provider: string
    openai_model: string
    openai_api_mode: string
    mock_llm: boolean
    openai_api_key?: string | null
  }
  openedx: {
    use_mock_openedx: boolean
    openedx_base_url: string
    openedx_cms_base_url: string
    openedx_lms_base_url: string
    openedx_oauth_base_url: string
    openedx_client_id?: string | null
    openedx_client_secret?: string | null
    openedx_access_token?: string | null
    openedx_oauth_token_url: string
    openedx_course_blocks_path: string
    openedx_publish_endpoint: string
    openedx_library_endpoint: string
    openedx_library_import_endpoint: string
  }
  sso: {
    auth_mode: string
    allow_demo_role_header: boolean
    jwt_secret?: string | null
  }
  cost: {
    cost_input_price_per_1m: number
    cost_cached_input_price_per_1m: number
    cost_output_price_per_1m: number
    cost_safety_factor: number
    usd_to_vnd: number
  }
  worker?: {
    openai_parallel_enabled: boolean
    openai_max_parallel_calls: number
    openai_retry_max_attempts: number
    openai_retry_base_seconds: number
    openai_prompt_cache_warmup_enabled: boolean
    generation_tail_batch_wait_enabled: boolean
  }
}


export type CoursePolicy = {
  course_id: string
  monthly_budget_usd: number
  max_questions_per_course: number
  max_questions_per_job: number
  max_retry: number
  generated_questions: number
  remaining_questions: number
}

export type CoursePolicyUpdate = {
  course_id: string
  monthly_budget_usd: number
  max_questions_per_course: number
  max_questions_per_job: number
  max_retry: number
}

export type AuditLogRow = {
  id: string
  course_id?: string | null
  actor_id: string
  actor_role?: string | null
  action: string
  target_type?: string | null
  target_id?: string | null
  status: string
  error_type?: string | null
  message: string
  metadata?: Record<string, any>
  created_at?: string | null
}


export type PublishLibrarySummary = {
  difficulty: string
  library_key: string
  library_display_name?: string
  component_count: number
  verified_count?: number
  pending_count?: number
  failed_count?: number
  status: string
  studio_url?: string | null
  problem_bank_hint?: string
}

export type PublishBatchSummary = {
  id: string
  course_id: string
  actor_id: string
  mode: string
  status: string
  total_questions: number
  published_count: number
  failed_count: number
  warning_count: number
  summary?: { libraries?: PublishLibrarySummary[]; family_bank_plan?: FamilyBankPlan; family_bank_slots?: FamilyBankSlot[]; family_bank_coverage?: FamilyBankCoverage[] }
  errors?: any[]
  created_at?: string | null
  completed_at?: string | null
}

export type PublishResult = {
  course_id: string
  batch_id?: string
  mode?: string
  published: number
  failed: number
  warnings?: number
  status: string
  errors?: any[]
  libraries?: PublishLibrarySummary[]
  problem_bank_guide?: string[]
  family_bank_plan?: FamilyBankPlan
  family_bank_slots?: FamilyBankSlot[]
  family_bank_coverage?: FamilyBankCoverage[]
}

export type SourceTrace = {
  question_id: string
  course_id: string
  source_node?: { id?: string | null; title?: string | null; block_type?: string | null; sync_status?: string | null }
  chapter_node?: { id?: string | null; title?: string | null; block_type?: string | null }
  chunk?: { id?: string | null; block_id?: string | null; source_type?: string | null; source_ref?: string | null; page_number?: number | null; timestamp_start?: string | null; timestamp_end?: string | null; token_count?: number | null; content?: string }
  question_source_excerpt?: string
  concept?: { id?: string | null; title?: string | null; key?: string | null; family_id?: string | null; variant_no?: number | null; source_evidence?: string | null }
  publish_trace?: Record<string, any>
  tags?: string[]
}

export type FamilyBankFamily = {
  family_id: string
  family_name: string
  concept_id?: string | null
  concept_title?: string | null
  variant_count: number
  question_ids: string[]
}

export type FamilyBankSlot = {
  slot_no: number
  difficulty: string
  pick_count: number
  repeated_family?: boolean
  families: FamilyBankFamily[]
  family_names: string[]
  question_ids: string[]
  variant_count: number
  rule: string
  warning?: string
}

export type FamilyBankCoverage = {
  difficulty: string
  target_slots: number
  available_families: number
  selected_slots: number
  optional_family_count: number
  repeated_slot_count: number
  status: string
}

export type FamilyBankHardGuard = {
  valid: boolean
  mode: string
  eligible_question_count: number
  eligible_record_count?: number
  deduplicated_record_count?: number
  assigned_question_count: number
  slot_count: number
  all_questions_assigned: boolean
  no_cross_slot_duplicates: boolean
  no_duplicate_anywhere?: boolean
  duplicate_question_ids?: string[]
  duplicate_component_ids?: string[]
  duplicate_fingerprint_count?: number
  duplicate_family_ids?: string[]
  family_mismatch_question_ids?: string[]
  family_mismatch_slots?: number[]
  difficulty_mismatch_question_ids?: string[]
  duplicate_record_question_ids_in_plan?: string[]
  duplicate_inside_slot_question_ids?: string[]
  duplicate_inside_slot_component_ids?: string[]
  duplicate_inside_slot_fingerprint_count?: number
  unknown_question_ids?: string[]
  missing_question_ids?: string[]
  empty_slots?: number[]
  mixed_scope_slots?: number[]
  summary: string
}

export type FamilyBankPlan = {
  ok: boolean
  course_id: string
  chapter_node_id?: string | null
  total_questions: number
  target_counts: Record<string, number>
  shortage_policy: string
  max_families_per_bank: number
  coverage: FamilyBankCoverage[]
  slots: FamilyBankSlot[]
  warnings: string[]
  combination_count_estimate: number
  message?: string
  requested_total_questions?: number
  planner_engine?: string
  planner_mode?: string
  uses_llm?: boolean
  stable_family_count?: number
  effective_target_counts?: Record<string, number>
  family_reconciliation?: {
    strategy: string
    uses_llm: boolean
    question_count: number
    family_count_before: number
    family_count_after: number
    merged_family_count: number
    updated_question_count: number
    variant_no_updated_count: number
  }
  eligible_question_count?: number
  eligible_record_count?: number
  assigned_question_count?: number
  identity_unit_count?: number
  exact_duplicate_record_count?: number
  excluded_duplicate_question_ids?: string[]
  require_all_approved?: boolean
  hard_guard?: FamilyBankHardGuard
}

export type CmsQuizNodeResult = {
  ok: boolean
  created: boolean
  status: string
  course_id: string
  parent_node_id: string
  parent_title?: string
  parent_type?: string
  quiz_title: string
  unit_title: string
  created_nodes: Array<{ usage_key: string; block_id?: string; block_type: string; display_name: string; parent_usage_key?: string | null; created?: boolean }>
  leaf_unit_node_id?: string
  leaf_unit_type?: string
  manual_publish_required?: boolean
  problem_bank_auto_inserted?: boolean
  message?: string
  next_step?: string
}

export type CmsProblemBankBlock = {
  usage_key: string
  block_id?: string
  block_type: string
  display_name: string
  parent_usage_key?: string | null
  created?: boolean
  slot_no?: number
  difficulty?: string
  family_names?: string[]
  pick_count?: number
  library_key?: string
  openedx_problem_ids?: string[]
  selection_verified?: boolean
  verification?: Record<string, any>
  diagnostics?: any[]
}

export type CmsProblemBankInsertResult = {
  ok: boolean
  implementation?: string
  created: boolean
  status: string
  course_id: string
  unit_node_id: string
  unit_title?: string
  problem_bank_blocks: CmsProblemBankBlock[]
  slots_requested: number
  slots_inserted: number
  course_local_problem_children_created?: number
  legacy_ai_randomized_blocks_removed?: number
  manual_component_selection_required?: boolean
  warnings?: string[]
  message?: string
  next_step?: string
}

export type Department = {
  id: string
  code: string
  name: string
  description: string
  status: string
  created_at: string
  updated_at: string
}

export type Subject = {
  id: string
  department_id: string
  code: string
  name: string
  description: string
  status: string
  created_at: string
  updated_at: string
}

export type SubjectOffering = {
  id: string
  department_id?: string | null
  subject_id: string
  code: string
  name: string
  term?: string | null
  version_code: string
  based_on_offering_id?: string | null
  status: string
  metadata_json?: Record<string, any> | null
  created_by?: string | null
  approved_by?: string | null
  published_at?: string | null
  created_at: string
  updated_at: string
}

export type SubjectChapter = {
  id: string
  subject_id: string
  subject_offering_id?: string | null
  chapter_no: number
  title: string
  description: string
  sort_order: number
  status: string
  created_at: string
  updated_at: string
}

export type BankVersion = {
  id: string
  subject_id: string
  chapter_id: string
  subject_offering_id?: string | null
  version_no: number
  version_code: string
  title: string
  change_note: string
  status: string
  based_on_version_id?: string | null
  created_by?: string | null
  approved_by?: string | null
  published_at?: string | null
  metadata_json?: Record<string, any> | null
  created_at: string
  updated_at: string
}

export type MaterialVersion = {
  id: string
  subject_id: string
  chapter_id: string
  bank_version_id: string
  title: string
  file_name: string
  file_type: string
  storage_path: string
  content_hash?: string | null
  version_no: number
  change_type: string
  uploaded_by?: string | null
  status: string
  created_at: string
}


export type BankReleasePublishAudit = {
  ok: boolean
  audit_status: string
  release_id: string
  release_code?: string
  release_status?: string
  bank_version_id?: string
  chapter_id?: string
  subject_id?: string
  openedx_library_key?: string | null
  expected_openedx_library_key?: string | null
  published_at?: string | null
  message: string
  counts: Record<string, number>
  checks: Array<{ code: string; status: string; message: string; blocking?: boolean; detail?: Record<string, any> }>
  blockers?: Array<{ code: string; status: string; message: string; blocking?: boolean; detail?: Record<string, any> }>
  warnings?: Array<{ code: string; status: string; message: string; blocking?: boolean; detail?: Record<string, any> }>
  next_actions?: string[]
  quiz_instances?: Array<{ id: string; openedx_course_id?: string; status?: string; openedx_unit_node_id?: string | null; openedx_quiz_node_id?: string | null; created_at?: string | null; updated_at?: string | null }>
  read_only?: boolean
  mutation_performed?: boolean
}

export type BankReleasePublishResult = {
  ok: boolean
  release_id: string
  release_code: string
  status: string
  openedx_library_key?: string | null
  question_count: number
  imported_now_count: number
  skipped_existing_count: number
  library_result?: Record<string, any> | null
  imported?: any[]
  errors?: any[]
}

export type MappingCheck = {
  code: string
  status: 'pass' | 'warn' | 'fail' | string
  message: string
  blocking: boolean
  detail?: Record<string, any>
}

export type MappingValidation = {
  ok: boolean
  risk_level: 'low' | 'medium' | 'high' | string
  checks: MappingCheck[]
  can_create_mapping: boolean
  message: string
}

export type BankRelease = {
  id: string
  bank_version_id: string
  subject_id: string
  chapter_id: string
  release_code: string
  title: string
  status: string
  approved_question_count: number
  easy_count: number
  medium_count: number
  hard_count: number
  family_count: number
  openedx_library_key?: string | null
  openedx_library_version?: number | null
  publish_batch_id?: string | null
  published_at?: string | null
  published_by?: string | null
  metadata_json?: Record<string, any> | null
  created_at: string
  updated_at: string
}

export type BankReleasePreviewQuestion = {
  release_question_id: string
  question_id: string
  question_text: string
  option_a?: string | null
  option_b?: string | null
  option_c?: string | null
  option_d?: string | null
  correct_answer: string
  difficulty: string
  concept_title?: string | null
  question_family_id?: string | null
  included_at?: string | null
}

export type BankReleasePreview = {
  release: BankRelease
  frozen_snapshot: boolean
  total_questions: number
  counts: Record<string, number>
  questions: BankReleasePreviewQuestion[]
}

export type EdxCourseMapping = {
  id: string
  openedx_course_id: string
  department_id?: string | null
  subject_id: string
  subject_offering_id?: string | null
  term?: string | null
  status: string
  validation_status?: string
  validation_json?: MappingValidation | Record<string, any> | null
  validated_at?: string | null
  created_by?: string | null
  created_at: string
  updated_at: string
}

export type EdxCourseChapterMapping = {
  id: string
  course_mapping_id: string
  subject_chapter_id: string
  bank_release_id?: string | null
  openedx_parent_node_id?: string | null
  enabled: boolean
  validation_status?: string
  validation_json?: MappingValidation | Record<string, any> | null
  validated_at?: string | null
  created_at: string
  updated_at: string
}

export type QuizBlueprint = {
  id: string
  subject_id: string
  chapter_id: string
  title: string
  total_questions: number
  difficulty_easy: number
  difficulty_medium: number
  difficulty_hard: number
  max_families_per_bank: number
  pick_count_per_slot: number
  status: string
  created_at: string
  updated_at: string
}

export type BankSummary = {
  departments: number
  subjects: number
  subject_offerings?: number
  chapters: number
  bank_versions: number
  releases: number
  published_releases: number
  course_mappings: number
  quiz_blueprints: number
  material_versions: number
  material_chunks: number
  bank_questions: number
  bank_diffs?: number
  carry_over_questions?: number
  retired_questions?: number
}


export type MaterialChunk = {
  id: string
  material_version_id: string
  bank_version_id: string
  subject_id: string
  chapter_id: string
  chunk_index: number
  content: string
  token_count: number
  source_type: string
  page_number?: number | null
  source_ref: string
  content_hash?: string | null
  created_at: string
}

export type MaterialUploadResult = {
  ok: boolean
  reused_existing: boolean
  material_version: MaterialVersion
  chunks_created: number
  tokens_indexed: number
  source_types: string[]
  diff_required?: boolean
  diff_base_bank_version_id?: string | null
  document_change_state?: string | null
  auto_retire_result?: Record<string, any> | null
  message: string
}

export type BankGeneratePreview = {
  ok: boolean
  bank_version_id: string
  chapter_id: string
  question_count: number
  difficulty_counts: Record<string, number>
  current_question_count: number
  chapter_question_limit: number
  remaining_quota: number
  estimated_input_tokens: number
  estimated_cached_input_tokens: number
  estimated_output_tokens: number
  estimated_raw_cost_usd: number
  estimated_cost_usd: number
  estimated_cost_vnd: number
  model_name: string
  pricing?: Record<string, any> | null
  token_source: string
  message: string
}

export type BankGenerateResult = {
  ok: boolean
  bank_version_id: string
  requested_questions: number
  created_questions: number
  pending_review_count: number
  approved_count: number
  draft_error_count: number
  input_chunks: number
  input_tokens: number
  difficulty_counts: Record<string, number>
  questions: string[]
  usage: Record<string, any>[]
  errors: Record<string, any>[]
  message: string
}


export type BankQuestionListItem = {
  id: string
  bank_version_id?: string | null
  subject_id?: string | null
  subject_chapter_id?: string | null
  difficulty: string
  status: string
  question_text_preview: string
  option_a_preview?: string | null
  option_b_preview?: string | null
  option_c_preview?: string | null
  option_d_preview?: string | null
  correct_answer: string
  concept_title?: string | null
  question_family_id?: string | null
  variant_no?: number | null
  quality_score: number
  draft_error_reason?: string | null
  is_duplicate?: boolean | null
  is_retired?: boolean | null
  previous_question_id?: string | null
  lineage_root_question_id?: string | null
  question_revision_no?: number | null
  is_carry_over?: boolean | null
  created_at: string
}



export type BankQuestionImportPreview = {
  ok: boolean
  preview_token: string
  total_rows: number
  valid_count: number
  error_count: number
  preview_rows: Array<Record<string, any>>
  errors: Array<{ row?: number; field?: string; code?: string; message?: string }>
  can_commit: boolean
  message: string
}

export type BankVersionQuestion = {
  id: string
  bank_version_id?: string | null
  subject_id?: string | null
  subject_chapter_id?: string | null
  material_version_id?: string | null
  concept_version_id?: string | null
  concept_title?: string | null
  question_family_id?: string | null
  variant_no?: number | null
  difficulty: string
  cognitive_level?: string | null
  learning_objective?: string | null
  question_type?: string | null
  question_text: string
  option_a?: string | null
  option_b?: string | null
  option_c?: string | null
  option_d?: string | null
  correct_answer: string
  explanation?: string | null
  source_ref?: string | null
  source_type?: string | null
  source_excerpt?: string | null
  source_evidence?: string | null
  status: string
  quality_score: number
  quality_flags?: string[] | null
  draft_error_reason?: string | null
  draft_error_detail?: Record<string, any> | null
  is_duplicate?: boolean | null
  duplicate_score?: number | null
  duplicate_of_question_id?: string | null
  previous_question_id?: string | null
  lineage_root_question_id?: string | null
  question_revision_no?: number
  is_carry_over?: boolean
  is_retired?: boolean
  retired_reason?: string | null
  retired_at?: string | null
  created_at: string
}

export type BankVersionDiffSummary = {
  from_bank_version_id: string
  to_bank_version_id: string
  from_version_code?: string | null
  to_version_code?: string | null
  material_similarity?: number | null
  source_material_count: number
  target_material_count: number
  exact_shared_material_count: number
  unchanged_concept_count: number
  changed_concept_count: number
  new_concept_count: number
  removed_concept_count: number
  source_approved_question_count: number
  carry_over_candidate_count: number
  retire_candidate_count: number
  review_candidate_count: number
  already_exists_count: number
  recommendation?: string | null
  changed_concepts: string[]
  new_concepts: string[]
  removed_concepts: string[]
}

export type BankVersionDiffPreview = {
  ok: boolean
  diff_id?: string | null
  summary: BankVersionDiffSummary
  material_similarity?: number | null
  carry_over_candidates: string[]
  retire_candidates: string[]
  review_candidates: string[]
  already_exists: string[]
  message: string
}


export type BankMaterialRecheckResult = {
  ok: boolean
  bank_version_id?: string | null
  candidate_count: number
  kept_count: number
  safe_skipped_count: number
  retired_count: number
  release_removed_count?: number
  current_material_chunk_count?: number
  message: string
  user_message?: string | null
  [key: string]: any
}

export type BankCarryOverResult = {
  ok: boolean
  created_count: number
  skipped_count: number
  created_question_ids: string[]
  skipped: Record<string, any>[]
  message: string
}

export type BankRetireResult = {
  ok: boolean
  retired_count: number
  retired_question_ids: string[]
  source_question_ids?: string[]
  excluded_count?: number
  excluded_question_ids?: string[]
  skipped?: Record<string, any>[]
  message: string
}


export type BankReleaseQuizPlan = BackendUiNotice & {
  ok: boolean
  planner_engine?: string | null
  uses_llm: boolean
  release_id: string
  release_code: string
  openedx_library_key?: string | null
  requested_total_questions: number
  total_questions: number
  target_counts: Record<string, number>
  effective_target_counts: Record<string, number>
  coverage: Record<string, any>[]
  slots: Record<string, any>[]
  warnings: string[]
  assigned_question_count: number
  assigned_component_count: number
  hard_guard: Record<string, any>
  message: string
}

export type BankReleaseQuizCreateResult = BackendUiNotice & {
  ok: boolean
  status: string
  course_quiz_instance_id: string
  openedx_course_id: string
  openedx_quiz_node_id?: string | null
  openedx_unit_node_id?: string | null
  bank_release_id: string
  release_code: string
  plan: Record<string, any>
  quiz_result: Record<string, any>
  problem_bank_result: Record<string, any>
  timer_config?: Record<string, any>
  message: string
}


export type BankReleaseReadiness = {
  ok: boolean
  bank_version_id: string
  can_create_release: boolean
  status: string
  checks: Record<string, any>[]
  stats: Record<string, any>
  recommended_actions: string[]
  message: string
}

export type BankQuestionReviewResult = {
  ok: boolean
  question: BankVersionQuestion
  old_status: string
  new_status: string
  message: string
}

export type BankQuestionBulkReviewResult = {
  ok: boolean
  changed_count: number
  skipped_count: number
  changed_question_ids: string[]
  skipped: Record<string, any>[]
  message: string
}

export type BankDocumentDiffResolveResult = {
  ok: boolean
  bank_version_id: string
  diff_required: boolean
  document_change_state: string
  message: string
}

export type CourseQuizInstance = {
  id: string
  openedx_course_id: string
  subject_id: string
  chapter_id: string
  subject_offering_id?: string | null
  bank_release_id: string
  quiz_blueprint_id?: string | null
  openedx_quiz_node_id?: string | null
  openedx_unit_node_id?: string | null
  status: string
  metadata_json?: Record<string, any> | null
  created_at: string
  updated_at: string
}




export type QuizChapterAction = 'quiz' | 'skip' | 'assignment' | 'final_test'

export type QuizChapterPlanItem = {
  chapter_id: string
  action: QuizChapterAction
}

export type QuizAutoMapCandidate = {
  offering_id: string
  offering_code: string
  name?: string | null
  term?: string | null
  version_code?: string | null
  status?: string | null
  score: number
  course_run_match: boolean
  all_ready: boolean
  chapter_count: number
  ready_chapter_count: number
  missing_chapters: string[]
  disabled_reason?: string | null
  selection_note?: string | null
}

export type QuizAutoMapResult = BackendUiNotice & {
  ok: boolean
  openedx_course_id: string
  mode: 'preview' | 'applied' | string
  subject?: { id: string; code: string; name: string; department_id?: string | null; department_name?: string | null } | null
  offering?: { id: string; code: string; name?: string | null; term?: string | null; version_code?: string | null } | null
  course_mapping?: { id: string; openedx_course_id: string; status?: string } | null
  summary: Record<string, any> & { candidates?: QuizAutoMapCandidate[]; selected_subject_offering_id?: string | null }
  sections: Array<{ openedx_section_id: string; title: string; type: string }>
  mappings: Array<{
    chapter_id: string
    chapter_title: string
    release_id?: string | null
    release_code?: string | null
    openedx_library_key?: string | null
    openedx_section_id?: string | null
    openedx_section_title?: string | null
    match_score: number
    match_reason: string
    action?: QuizChapterAction
    action_label?: string
    assessment_type?: 'quiz' | 'final_test' | 'skip' | string
    requires_quiz?: boolean
    requires_release?: boolean
    requires_section?: boolean
    skipped?: boolean
    ready: boolean
    can_create?: boolean
    production_ready?: boolean
    status_code?: string | null
    status_label?: string | null
    status_severity?: 'success' | 'warning' | 'danger' | 'info' | string | null
    missing_requirements?: string[]
    recommended_action?: string | null
    recommended_quiz_title?: string | null
    recommended_unit_title?: string | null
    mapping_status?: string | null
    course_chapter_mapping_id?: string | null
  }>
  warnings: string[]
  blocking_errors: string[]
  can_apply: boolean
  message: string
}

export type CourseQuizRollbackResult = BackendUiNotice & {
  ok: boolean
  course_quiz_instance_id: string
  status: string
  openedx_deleted: boolean
  manual_cleanup_required: boolean
  delete_result: Record<string, any>
  message: string
}

export type BankReviewStatusStats = {
  total_questions: number
  approved_count: number
  pending_review_count: number
  draft_error_count: number
  unresolved_count: number
  rejected_count?: number
  is_review_done: boolean
  status: string
  has_questions?: boolean
  subject_count?: number
  review_done_subject_count?: number
  review_not_done_subject_count?: number
  subject_version_count?: number
  review_done_version_count?: number
  review_not_done_version_count?: number
  chapter_count?: number
  review_done_chapter_count?: number
  review_not_done_chapter_count?: number
  material_count?: number
  bank_version_count?: number
  release_count?: number
  published_release_count?: number
  ready_to_release?: boolean
  ready_to_release_chapter_count?: number
  question_limit?: number
  remaining_quota?: number
  [key: string]: any
}


export type DashboardDrilldown = { route: string; query?: Record<string, string | number | boolean | null | undefined> }
export type DashboardKpi = { key: string; label: string; value: number; delta?: number; delta_label?: string; percent?: number; overdue?: number; drilldown?: DashboardDrilldown }
export type DashboardChartItem = {
  key?: string
  label?: string
  value?: number
  percent?: number
  date?: string
  current?: number
  previous?: number
  delta?: number
  approved?: number
  pending?: number
  rejected?: number
  subject_id?: string
  drilldown?: DashboardDrilldown
  [key: string]: any
}
export type DashboardChart = {
  key: string
  title: string
  type: 'donut' | 'line' | 'horizontal_bar' | 'grouped_bar' | string
  current_term?: string
  previous_term?: string
  items: DashboardChartItem[]
}
export type DashboardAlert = {
  id: string
  severity: 'critical' | 'warning' | 'info' | 'success' | string
  type: string
  title: string
  description?: string
  age_days?: number
  drilldown?: DashboardDrilldown
}
export type DashboardActivity = {
  id: string
  actor?: { id?: string | null; name?: string | null }
  action: string
  message: string
  status?: string
  created_at?: string | null
  relative_time?: string
  target?: { type?: string | null; id?: string | null; label?: string | null }
  drilldown?: DashboardDrilldown | null
}
export type DashboardAnalytics = {
  scope: { role: string; label: string; scope_type: string; scope_id: string }
  filters: { date_range: string; from_date: string; to_date: string }
  kpis: {
    total_questions: DashboardKpi
    pending_review: DashboardKpi
    approved: DashboardKpi
    rejected: DashboardKpi
    [key: string]: DashboardKpi
  }
  charts: {
    question_status: DashboardChart
    new_questions_by_day: DashboardChart
    questions_by_subject: DashboardChart
    difficulty_distribution: DashboardChart
    question_type_distribution: DashboardChart
    term_comparison: DashboardChart
    [key: string]: DashboardChart
  }
  alerts: DashboardAlert[]
  activity_feed: DashboardActivity[]
  meta?: Record<string, number | string | boolean | null | undefined>
  generated_at?: string
  cache?: { hit: boolean; ttl_seconds: number }
}

export type BankDashboardOverview = {
  ok: boolean
  departments_total: number
  departments_done: number
  departments_not_done: number
  subjects_total: number
  subjects_done: number
  subjects_not_done: number
  subject_versions_total: number
  subject_versions_done: number
  subject_versions_not_done: number
  chapters_total: number
  chapters_needing_review: number
  chapters_ready_to_release: number
  total_questions: number
  approved_count: number
  pending_review_count: number
  draft_error_count: number
  next_actions: Array<{ type: string; title: string; message: string; href: string; priority: number }>
}

export type BankSearchResult = {
  type: 'department' | 'subject' | 'subject_version' | 'chapter' | 'question' | string
  id?: string
  title: string
  subtitle: string
  href: string
  stats?: BankReviewStatusStats
  question_id?: string
  bank_version_id?: string | null
  chapter_id?: string | null
  status?: string
  difficulty?: string
  reviewed_by?: string | null
  reviewed_at?: string | null
  reject_reason?: string | null
  review_note?: string | null
  reviewer_name?: string | null
  action_by?: string | null
  action_by_name?: string | null
  question_type?: string | null
  created_at?: string | null
  updated_at?: string | null
  subject_id?: string | null
  subject_label?: string | null
  chapter_title?: string | null
}

export type BankSearchGroupedResponse = {
  q: string
  limit: number
  total: number
  items: BankSearchResult[]
  groups?: {
    departments?: BankSearchResult[]
    subjects?: BankSearchResult[]
    subject_versions?: BankSearchResult[]
    chapters?: BankSearchResult[]
    questions?: BankSearchResult[]
  }
}


export type BankDashboardDrilldownResponse = {
  entity: string
  filters?: Record<string, string | number | boolean | null | undefined>
  limit: number
  total: number
  returned?: number
  source?: string
  items: BankSearchResult[]
  generated_at?: string
}

export type DepartmentSummary = { department: Department; stats: BankReviewStatusStats }
export type SubjectSummary = { subject: Subject; stats: BankReviewStatusStats }
export type SubjectVersionSummary = { subject_version: SubjectOffering; stats: BankReviewStatusStats }
export type ChapterSummary = { chapter: SubjectChapter; stats: BankReviewStatusStats }

export type BusinessRoleCode = 'SYSTEM_ADMIN' | 'DEPARTMENT_HEAD' | 'SUBJECT_OWNER' | 'QUESTION_REVIEWER' | 'CAMPUS_OWNER' | 'CAMPUS_MANAGER' | 'TEACHER_ASSIGNED'
export type BusinessScopeType = 'SYSTEM' | 'DEPARTMENT' | 'SUBJECT' | 'SUBJECT_VERSION' | 'CHAPTER' | 'COURSE' | 'CAMPUS' | 'CLASS'

export type RBACRole = {
  code: BusinessRoleCode | string
  name: string
  description: string
  rank: number
  status: string
}

export type RBACPermission = {
  code: string
  name: string
  group_code: string
}

export type RoleAssignment = {
  id: string
  user_id: string
  email?: string | null
  role_code: BusinessRoleCode | string
  role_name?: string | null
  scope_type: BusinessScopeType | string
  scope_id: string
  scope_label?: string | null
  granted_by?: string | null
  grant_reason?: string
  metadata_json?: Record<string, any> | null
  revoked_at?: string | null
  revoked_by?: string | null
  revoke_reason?: string
  created_at: string
  updated_at: string
}

export type RoleAssignmentCreate = {
  user_id: string
  email?: string | null
  role_code: BusinessRoleCode | string
  scope_type: BusinessScopeType | string
  scope_id: string
  grant_reason?: string
  sync_openedx?: boolean
}

export type RoleAssignmentListResponse = {
  items: RoleAssignment[]
  total: number
}

export type EffectiveRBAC = {
  user_id: string
  legacy_role: string
  effective_legacy_role: string
  permissions: string[]
  assignments: RoleAssignment[]
}


export type RoleAssignmentImportRow = {
  row_index: number
  status: 'valid' | 'created' | 'skipped' | 'failed' | string
  message: string
  user_id: string
  email?: string | null
  role_code: BusinessRoleCode | string
  scope_type: BusinessScopeType | string
  scope_id: string
  scope_label?: string | null
  assignment?: RoleAssignment | null
}

export type RoleAssignmentImportResponse = {
  ok: boolean
  dry_run: boolean
  total_rows: number
  valid_rows: number
  created_count: number
  skipped_count: number
  failed_count: number
  rows: RoleAssignmentImportRow[]
}

// v25.9.16 Academic AP / Student Management types
export type AcademicTerm = {
  id: string
  ap_term_id?: string | null
  term_code: string
  term_name: string
  branch?: string | null
  start_date?: string | null
  end_date?: string | null
  active: boolean
  metadata_json?: Record<string, any> | null
}

export type AcademicBlock = {
  id: string
  term_id: string
  ap_block_id?: string | null
  block_code: string
  block_name: string
  start_date?: string | null
  end_date?: string | null
  sort_order: number
  active: boolean
  metadata_json?: Record<string, any> | null
}

export type AcademicSubject = {
  id: string
  ap_subject_id?: string | null
  subject_code: string
  subject_name: string
  subject_name_en?: string | null
  skill_code?: string | null
  branch?: string | null
  active: boolean
}

export type AcademicLearningComponentScore = {
  key?: string | null
  name: string
  category?: string | null
  earned?: number | null
  possible?: number | null
  percent?: number | null
  weight?: number | null
  source?: string | null
  planned?: boolean | null
  order?: number | null
  quiz_number?: number | null
  submitted_at?: string | null
  available_from?: string | null
  deadline_date?: string | null
  deadline_mode?: string | null
  schedule_warning?: string | null
  quiz_status?: string | null
}

export type AcademicQuizDeadlineOverride = {
  id?: string
  class_id?: string
  course_id?: string | null
  component_key?: string | null
  component_label?: string | null
  quiz_number?: number | null
  start_date?: string | null
  deadline_date?: string | null
  reason?: string | null
  created_by?: string | null
  updated_by?: string | null
  created_at?: string | null
  updated_at?: string | null
}

export type AcademicAssignmentDefenseScore = {
  id?: string
  class_id?: string
  student_id: string
  student_code?: string | null
  student_username?: string | null
  student_name?: string | null
  course_id?: string | null
  assignment_key?: string | null
  assignment_label?: string | null
  score_10?: number | null
  defense_status?: string | null
  graded_by?: string | null
  graded_at?: string | null
  note?: string | null
  created_at?: string | null
  updated_at?: string | null
}

export type AcademicSubjectManagement = AcademicSubject & {
  class_count: number
  campus_count: number
  teacher_count: number
  student_count: number
  relearn_student_count?: number
  total_relearn_count?: number
  cms_synced_count: number
  cms_unsynced_count: number
  course_mapping_status: string
  course_mapping_label: string
  openedx_course_id?: string | null
  openedx_course_title?: string | null
  openedx_mapping_id?: string | null
  suggested_openedx_course_id?: string | null
  learning_enrolled_count?: number
  learning_active_count?: number
  learning_synced_count?: number
  learning_not_enrolled_count?: number
  learning_avg_progress_percent?: number | null
  learning_avg_grade_percent?: number | null
  learning_last_synced_at?: string | null
  learning_component_summaries?: AcademicLearningComponentScore[]
  learning_alerts?: string[]
}

export type AcademicSubjectManagementSummary = {
  subject_count: number
  class_count: number
  student_count: number
  teacher_count: number
  cms_synced_count: number
  cms_unsynced_count: number
  course_mapped_count: number
  course_missing_count: number
  learning_enrolled_count: number
  learning_active_count: number
  learning_synced_count: number
  alert_subject_count: number
  scope_label: string
}

export type AcademicClass = {
  id: string
  ap_class_id?: string | null
  term_id: string
  term_name?: string | null
  block_id?: string | null
  block_name?: string | null
  subject_id: string
  subject_code?: string | null
  subject_name?: string | null
  class_code: string
  class_name: string
  campus?: string | null
  branch?: string | null
  start_date?: string | null
  end_date?: string | null
  active: boolean
  teacher_username?: string | null
  teacher_name?: string | null
  student_count: number
  cms_synced_count?: number
  cms_unsynced_count?: number
  openedx_course_id?: string | null
  openedx_cohort_name?: string | null
  openedx_mapping_source?: string | null
  openedx_mapping_validation_status?: string | null
  quiz_count?: number | null
  learning_enrolled_count?: number
  learning_active_count?: number
  learning_synced_count?: number
  learning_not_enrolled_count?: number
  learning_avg_progress_percent?: number | null
  learning_avg_grade_percent?: number | null
  learning_last_synced_at?: string | null
  learning_component_summaries?: AcademicLearningComponentScore[]
  learning_alerts?: string[]
}


export type AcademicTrainingPolicy = {
  policy_version?: string | null
  quiz_rule?: string | null
  final_test_rule?: string | null
  quiz_total?: number
  quiz_passed_count?: number
  quiz_failed_count?: number
  quiz_late_count?: number
  quiz_not_attempted_count?: number
  quiz_early_count?: number
  quiz_missing_deadline_count?: number
  all_quizzes_eligible?: boolean
  assignment_expected?: boolean
  assignment_status?: string | null
  assignment_score_10?: number | null
  assignment_note?: string | null
  exam_eligible?: boolean
  exam_status?: string | null
  exam_status_label?: string | null
  exam_reasons?: string[]
  exam_notes?: string[]
  quiz_results?: Array<Record<string, any>>
  deadline_mode?: string | null
  deadline_mode_note?: string | null
}

export type AcademicStudent = {
  id: string
  class_id?: string
  student_code?: string | null
  username: string
  email?: string | null
  full_name: string
  phone?: string | null
  total_relearn?: number
  campus?: string | null
  branch?: string | null
  active: boolean
  synced_at?: string | null
  mapping_id?: string | null
  openedx_user_id?: string | null
  openedx_username?: string | null
  openedx_email?: string | null
  openedx_is_active?: boolean | null
  match_status?: string
  match_method?: string
  mapping_confidence?: number
  mapping_note?: string
  last_resolved_at?: string | null
  learning_snapshot_id?: string | null
  learning_enrollment_status?: string | null
  learning_enrollment_mode?: string | null
  learning_progress_percent?: number | null
  learning_progress_source?: string | null
  learning_grade_percent?: number | null
  learning_passed?: boolean | null
  learning_completed_blocks?: number | null
  learning_total_blocks?: number | null
  learning_last_activity_at?: string | null
  learning_last_synced_at?: string | null
  learning_enrollment_synced_at?: string | null
  learning_status?: string
  learning_sync_note?: string | null
  learning_diagnostics?: Record<string, any> | null
  learning_component_scores?: AcademicLearningComponentScore[]
  training_policy?: AcademicTrainingPolicy | null
  exam_eligible?: boolean | null
  exam_status?: string | null
  exam_status_label?: string | null
  exam_reasons?: string[]
  assignment_defense_status?: string | null
  assignment_score_10?: number | null
}

export type AcademicLearningSummary = {
  class_id: string
  openedx_course_id?: string | null
  total: number
  counts: Record<string, number>
  active_count?: number
  avg_progress_percent?: number | null
  avg_grade_percent?: number | null
  last_synced_at?: string | null
  component_summaries?: AcademicLearningComponentScore[]
  status_counts?: Record<string, number>
  alert_counts?: Record<string, number>
  diagnostic_counts?: Record<string, number>
  source_counts?: Record<string, number>
  diagnostic_note?: string | null
}

export type AcademicIdentityReconciliationItem = {
  student_id: string
  student_code?: string | null
  full_name: string
  email?: string | null
  ap_username?: string | null
  canonical_username: string
  openedx_username?: string | null
  openedx_user_id?: string | null
  openedx_is_active?: boolean | null
  match_status: string
  match_method: string
  status: string
  severity: 'blocker' | 'warning' | 'info' | string
  can_enroll: boolean
  recommended_action: string
  blockers: string[]
  warnings: string[]
  duplicate_rollnumber_count: number
  duplicate_canonical_mapping_count: number
}

export type AcademicIdentityReconciliationReport = {
  ok: boolean
  class_id: string
  class_code?: string | null
  status: 'ready' | 'needs_sync' | 'blocked' | string
  message: string
  policy: string
  dry_run: boolean
  mutation_performed: boolean
  counts: Record<string, number>
  total: number
  page: number
  page_size: number
  total_pages: number
  has_next: boolean
  items: AcademicIdentityReconciliationItem[]
  next_actions: string[]
}


export type AcademicIdentityCleanupResult = {
  ok: boolean
  class_id: string
  class_code?: string | null
  dry_run: boolean
  mutation_performed: boolean
  destructive_allowed: boolean
  confirm_phrase_required: string
  policy: string
  counts: Record<string, number>
  deleted_mapping_ids: string[]
  deleted_snapshot_ids: string[]
  skipped: Array<Record<string, unknown>>
  items: AcademicIdentityReconciliationItem[]
  message: string
  next_actions: string[]
}


export type AcademicLearningSyncResult = AcademicLearningSummary & {
  ok: boolean
  updated: number
  message: string
  connector_counts?: Record<string, number>
  connector_diagnostics?: Record<string, any> | null
}

export type AcademicEnrollmentSyncResult = {
  ok: boolean
  class_id: string
  openedx_course_id?: string | null
  total: number
  updated: number
  counts: Record<string, number>
  message: string
  learning_summary?: AcademicLearningSummary | null
  teachers?: { total?: number; updated?: number; counts?: Record<string, number> } | null
}

export type AcademicMappingSummary = {
  class_id: string
  total: number
  counts: Record<string, number>
}

export type AcademicMappingResolveResult = {
  ok: boolean
  class_id: string
  total: number
  updated: number
  counts: Record<string, number>
  message: string
  enrollment?: AcademicEnrollmentSyncResult | null
  teachers?: { total?: number; updated?: number; counts?: Record<string, number> } | null
}

export type AcademicClassSyncJob = {
  id: string
  job_type: 'cms_sync_check' | 'cms_enrollment_sync' | 'learning_sync' | string
  status: 'queued' | 'running' | 'completed' | 'failed' | string
  class_id: string
  requested_by?: string | null
  force?: boolean
  limit?: number
  mode?: string | null
  progress_current?: number
  progress_total?: number
  progress_label?: string
  request_json?: Record<string, any> | null
  result_json?: Record<string, any> | null
  error_message?: string | null
  created_at?: string | null
  started_at?: string | null
  finished_at?: string | null
  updated_at?: string | null
}

export type AcademicManualMappingImportResult = {
  ok: boolean
  total: number
  counters: Record<string, number>
  errors: Array<Record<string, any>>
}

export type AcademicTrainingClassReport = {
  class_id: string
  class_code: string
  class_name?: string | null
  term_id?: string | null
  term_name?: string | null
  block_id?: string | null
  block_name?: string | null
  subject_id?: string | null
  subject_code?: string | null
  subject_name?: string | null
  campus?: string | null
  branch?: string | null
  student_count: number
  relearn_student_count?: number
  total_relearn_count?: number
  cms_synced_count: number
  cms_unsynced_count: number
  openedx_course_id?: string | null
  openedx_mapping_source?: string | null
  learning_enrolled_count: number
  learning_active_count: number
  learning_synced_count: number
  learning_avg_progress_percent?: number | null
  learning_avg_grade_percent?: number | null
  learning_avg_grade_10?: number | null
  learning_last_synced_at?: string | null
  learning_component_summaries?: AcademicLearningComponentScore[]
  status_counts?: Record<string, number>
  learning_alerts?: string[]
  risk_student_count?: number | null
  deadline_quiz_count?: number | null
  deadline_due_quiz_count?: number | null
  deadline_completed_due_quiz_count?: number | null
  deadline_late_student_count?: number | null
  deadline_late_quiz_count?: number | null
  deadline_next_quiz_label?: string | null
  deadline_next_quiz_from_date?: string | null
  deadline_next_quiz_due_date?: string | null
  deadline_schedule_note?: string | null
  exam_eligible_student_count?: number | null
  exam_not_eligible_student_count?: number | null
  exam_insufficient_data_student_count?: number | null
  quiz_failed_count?: number | null
  quiz_late_count?: number | null
  quiz_not_attempted_count?: number | null
  quiz_missing_deadline_count?: number | null
  assignment_not_graded_count?: number | null
}

export type AcademicTrainingTeacherReport = {
  teacher_id: string
  teacher_code?: string | null
  teacher_username: string
  teacher_name: string
  teacher_email?: string | null
  campus?: string | null
  branch?: string | null
  subject_count: number
  subject_codes: string[]
  class_count: number
  student_count: number
  unique_student_count: number
  relearn_student_count?: number
  total_relearn_count?: number
  cms_synced_count: number
  cms_unsynced_count: number
  learning_enrolled_count: number
  learning_active_count: number
  learning_synced_count: number
  classes_without_course_count: number
  deadline_late_student_count?: number | null
  deadline_late_quiz_count?: number | null
  deadline_due_quiz_count?: number | null
  exam_eligible_student_count?: number | null
  exam_not_eligible_student_count?: number | null
  exam_insufficient_data_student_count?: number | null
  quiz_failed_count?: number | null
  assignment_not_graded_count?: number | null
  learning_avg_progress_percent?: number | null
  learning_avg_grade_percent?: number | null
  learning_avg_grade_10?: number | null
  risk_student_count: number
  status_counts: Record<string, number>
  learning_alerts: string[]
  last_synced_at?: string | null
  classes?: AcademicTrainingClassReport[]
}

export type AcademicTrainingTeacherReportResponse = PaginatedResponse<AcademicTrainingTeacherReport> & {
  summary_scope?: 'current_page' | 'filtered' | 'cached_filtered' | string
  cache?: { status?: string; scope_key?: string | null; built_at?: string | null; row_count?: number | null }
  summary: {
    teacher_count: number
    class_count: number
    subject_count: number
    student_count: number
    unique_student_count: number
    relearn_student_count: number
    total_relearn_count: number
    cms_synced_count: number
    learning_enrolled_count: number
    learning_active_count: number
    risk_student_count: number
    classes_without_course_count: number
    deadline_late_student_count: number
    deadline_late_quiz_count: number
    exam_eligible_student_count?: number
    exam_not_eligible_student_count?: number
    exam_insufficient_data_student_count?: number
    quiz_failed_count?: number
    assignment_not_graded_count?: number
  }
}


export type AcademicBulkOperationJob = {
  id: string
  job_type: string
  status: string
  term_id?: string | null
  branch?: string | null
  campus?: string | null
  requested_by?: string | null
  progress_current: number
  progress_total: number
  progress_label: string
  request_json?: Record<string, any> | null
  result_json?: Record<string, any> | null
  error_message?: string | null
  created_at?: string | null
  started_at?: string | null
  finished_at?: string | null
  updated_at?: string | null
}

export type AcademicTeacherReportJob = {
  id: string
  job_type: string
  status: string
  term_id?: string | null
  branch?: string | null
  campus?: string | null
  requested_by?: string | null
  progress_current: number
  progress_total: number
  progress_label: string
  request_json?: Record<string, any> | null
  result_json?: Record<string, any> | null
  file_path?: string | null
  file_name?: string | null
  error_message?: string | null
  created_at?: string | null
  started_at?: string | null
  finished_at?: string | null
  updated_at?: string | null
}

export type AcademicClassListSummary = {
  class_count?: number
  student_count?: number
  cms_synced_count?: number
  cms_unsynced_count?: number
  learning_enrolled_count?: number
  learning_synced_count?: number
  learning_active_count?: number
  course_mapped_count?: number
  course_missing_count?: number
  alert_class_count?: number
  scope_label?: string
}

export type AcademicClassListResponse = PaginatedResponse<AcademicClass> & { summary?: AcademicClassListSummary }


export type AnalyticsLearningBehaviorClassification =
  | 'LIKELY_REAL_LEARNING'
  | 'POSSIBLE_IDLE'
  | 'POSSIBLE_ANOMALY'
  | 'POSSIBLE_CHEATING'
  | 'INSUFFICIENT_DATA'
  | 'NORMAL'
  | string


export type AnalyticsClassResultDoctor = {
  status: 'ready' | 'partial' | 'waiting' | 'blocked' | 'needs_recalculate' | string
  data_gap: 'READY' | 'PARTIAL_SNAPSHOT' | 'HAS_ACTIVITY_NO_SNAPSHOT' | 'NO_TRACKING_EVENTS' | 'NO_COURSE_MAPPING' | 'AMBIGUOUS_COURSE_MAPPING' | 'NO_ROSTER' | 'CLASS_NOT_FOUND' | string
  message?: string | null
  recommended_action?: string | null
  class?: {
    class_id?: string | null
    class_code?: string | null
    class_name?: string | null
    campus?: string | null
    branch?: string | null
    term_id?: string | null
    term_name?: string | null
    subject_id?: string | null
    subject_code?: string | null
  }
  course_mapping?: {
    status?: string | null
    resolved_course_id?: string | null
    mapping_source?: string | null
    candidate_count?: number
    mapped_course_ids?: string[]
    candidates?: Array<Record<string, any>>
    message?: string | null
  }
  resolved_course_id?: string | null
  roster_count: number
  snapshot_count: number
  missing_snapshot_count: number
  tracking_event_count: number
  tracking_user_count?: number
  latest_tracking_event_at?: string | null
  video_progress_count?: number
  video_user_count?: number
  session_progress_count?: number
  session_user_count?: number
  session_structure_count?: number
  latest_behavior_calculated_at?: string | null
  last_recalculate_job?: Record<string, any> | null
  active_recalculate_job?: Record<string, any> | null
  recalculate?: {
    can_enqueue?: boolean
    course_id?: string | null
    disabled_reasons?: string[]
    guard?: Record<string, any>
  }
  safe_policy?: string
}

export type AnalyticsLearningBehaviorSummary = {
  total_students: number
  roster_count?: number
  snapshot_count?: number
  missing_snapshot_count?: number
  data_status?: 'ready' | 'partial' | 'not_calculated' | string
  likely_real_learning_count: number
  possible_idle_count: number
  possible_suspicious_count: number
  insufficient_data_count: number
  normal_count: number
  data_quality_breakdown?: Record<string, number>
  current_week?: number | null
  due_sessions_this_week?: number[] | null
  overdue_sessions?: number[] | null
  diagnostics?: AnalyticsClassResultDoctor | null
  disclaimer?: string
}

export type AnalyticsLearningBehaviorRow = {
  username: string
  student_code?: string | null
  full_name?: string | null
  user_id?: string | null
  course_id: string
  class_id?: string | null
  classification: AnalyticsLearningBehaviorClassification
  display_label?: string | null
  confidence_score: number
  real_learning_score: number
  idle_score: number
  suspicious_score: number
  deadline_compliance_percent?: number | null
  crammed_session_count?: number
  quiz_before_video_count?: number
  reason_codes?: string[]
  human_readable_summary?: string | null
  recommended_action?: string | null
  data_quality?: string | null
  calculated_at?: string | null
  last_activity_at?: string | null
}


export type AnalyticsClassBehaviorOverviewItem = {
  class_id: string
  class_code: string
  class_name?: string | null
  campus?: string | null
  branch?: string | null
  openedx_course_id?: string | null
  openedx_mapping_source?: string | null
  student_count: number
  roster_count?: number
  snapshot_count: number
  missing_snapshot_count?: number
  likely_real_learning_count: number
  possible_idle_count: number
  possible_suspicious_count: number
  insufficient_data_count: number
  normal_count: number
  focus_count: number
  dominant_classification: AnalyticsLearningBehaviorClassification
  dominant_label?: string | null
  data_status: 'ready' | 'not_calculated' | string
  last_activity_at?: string | null
  calculated_at?: string | null
}

export type AnalyticsClassBehaviorOverviewSummary = {
  total_classes: number
  total_students: number
  roster_count?: number
  snapshot_count: number
  missing_snapshot_count?: number
  likely_real_learning_count: number
  possible_idle_count: number
  possible_suspicious_count: number
  insufficient_data_count: number
  normal_count: number
  not_calculated_class_count: number
}

export type AnalyticsLearningPermissionScope = {
  mode?: 'all' | 'scoped' | string
  unrestricted?: boolean
  teacher_ids?: string[]
  subject_codes?: string[]
  campus_codes?: string[]
  enforced_by_backend?: boolean
  label?: string
}

export type AnalyticsClassBehaviorOverviewResponse = {
  total: number
  items: AnalyticsClassBehaviorOverviewItem[]
  summary: AnalyticsClassBehaviorOverviewSummary
  classification_filter: string
  safe_policy?: string
  permission_scope?: AnalyticsLearningPermissionScope
}

export type AnalyticsLearningBehaviorListResponse = {
  total: number
  items: AnalyticsLearningBehaviorRow[]
  roster_fallback?: boolean
  diagnostics?: AnalyticsClassResultDoctor | null
}


export type AnalyticsStudentSessionProgress = {
  session_index: number
  session_title?: string | null
  week_index?: number | null
  deadline_at?: string | null
  deadline_source?: string | null
  total_videos: number
  videos_seen: number
  videos_completed: number
  avg_video_completion_percent?: number | null
  estimated_watch_seconds?: number | null
  quiz_attempted?: boolean
  quiz_completed?: boolean
  quiz_score?: number | null
  started_at?: string | null
  last_activity_at?: string | null
  completed_before_deadline?: boolean | null
  completed_late?: boolean | null
  session_learning_status?: string | null
  reason_codes?: string[]
  evidence?: Record<string, any>
}

export type AnalyticsStudentVideoProgress = {
  video_id: string
  video_code?: string | null
  session_index?: number | null
  component_title?: string | null
  duration_seconds?: number | null
  max_position_seconds?: number | null
  completion_percent?: number | null
  estimated_watch_seconds?: number | null
  estimated_watch_percent?: number | null
  play_count?: number
  pause_count?: number
  stop_count?: number
  seek_count?: number
  is_completed?: boolean
  is_suspicious?: boolean
  suspicious_reason?: string | null
  first_played_at?: string | null
  last_event_at?: string | null
}

export type AnalyticsStudentLearningBehaviorDetail = {
  behavior?: AnalyticsLearningBehaviorRow | null
  sessions: AnalyticsStudentSessionProgress[]
  videos: AnalyticsStudentVideoProgress[]
  timeline_weeks?: { week_index: number; sessions: number[] }[]
  disclaimer?: string
}



export type AnalyticsDataQualityIssue = {
  severity: 'BLOCKER' | 'WARNING' | 'INFO' | 'error' | 'warning' | 'info' | string
  code: string
  category?: string | null
  message: string
  action?: string | null
  command?: string | null
  source?: string | null
  blocking?: boolean
  details?: Record<string, any>
}

export type AnalyticsDataQualityReport = {
  status: string
  version?: string
  readiness: 'READY' | 'NEEDS_BACKFILL' | 'CONFIG_NEEDED' | 'NO_SCOPE' | string
  class_id?: string | null
  course_id?: string | null
  counts?: Record<string, number>
  deadline_sources?: Record<string, number>
  latest_behavior_calculated_at?: string | null
  ingest?: Record<string, any>
  issues?: AnalyticsDataQualityIssue[]
  next_actions?: string[]
  safe_policy?: string
  disclaimer?: string
}

export type AnalyticsProductionReadinessSection = {
  category: string
  status: 'OK' | 'BLOCKED' | 'WARNING' | 'INFO' | string
  blocker_count: number
  warning_count: number
  issues?: AnalyticsDataQualityIssue[]
}

export type AnalyticsProductionReadinessReport = {
  version?: string
  ready_for_production: boolean
  readiness: 'PRODUCTION_READY' | 'PRODUCTION_READY_WITH_WARNINGS' | 'NOT_READY' | string
  stage_status?: 'READY' | 'READY_WITH_WARNINGS' | 'BLOCKED' | string
  summary_label?: string
  message?: string
  blocker_count: number
  warning_count: number
  info_count?: number
  issue_count: number
  primary_blocker?: AnalyticsDataQualityIssue | null
  blockers?: AnalyticsDataQualityIssue[]
  warnings?: AnalyticsDataQualityIssue[]
  infos?: AnalyticsDataQualityIssue[]
  issues?: AnalyticsDataQualityIssue[]
  sections?: AnalyticsProductionReadinessSection[]
  checks?: Record<string, any>
  next_actions?: string[]
  can_pilot?: boolean
  can_broad_rollout?: boolean
  safe_policy?: string
  disclaimer?: string
}


export type AnalyticsSlaClassGap = {
  class_id: string
  class_code?: string | null
  campus?: string | null
  branch?: string | null
  course_id?: string | null
  student_count: number
  snapshot_count: number
  missing_snapshot_count: number
  latest_snapshot_at?: string | null
  snapshot_age_seconds?: number | null
  gap_status: 'NO_SNAPSHOT' | 'PARTIAL_SNAPSHOT' | 'STALE_SNAPSHOT' | string
}

export type AnalyticsSlaSection = {
  key: string
  title: string
  status: 'OK' | 'WARNING' | 'BLOCKED' | string
  target_seconds?: number | null
  actual_seconds?: number | null
  metrics?: Record<string, any>
}

export type AnalyticsSlaReport = {
  version?: string
  sla_status: 'OK' | 'WARNING' | 'BLOCKED' | string
  summary_label?: string
  generated_at?: string
  targets?: Record<string, number>
  counters?: Record<string, number>
  latency?: Record<string, number | null>
  ingest?: Record<string, any>
  post_ingest_recalculate?: Record<string, any>
  sections?: AnalyticsSlaSection[]
  issues?: AnalyticsDataQualityIssue[]
  next_actions?: string[]
  classes_needing_snapshot?: AnalyticsSlaClassGap[]
  safe_policy?: string
  disclaimer?: string
}

export type AnalyticsOpsStatus = Record<string, unknown> & {
  ingest?: Record<string, unknown>
  events?: Record<string, unknown>
  snapshots?: Record<string, unknown>
  status?: string
}

export type AnalyticsIngestJobResponse = {
  status: string
  task_name?: string
  celery_task_id?: string | null
  max_lines?: number
  message?: string
  safe_policy?: string
}



export type AnalyticsRolloutClass = {
  class_id: string
  class_code?: string | null
  class_name?: string | null
  campus?: string | null
  branch?: string | null
  course_id?: string | null
  student_count?: number
  session_count?: number
  behavior_snapshot_count?: number
  in_rollout: boolean
  rollout_reasons?: string[]
  recommended_action?: string | null
}

export type AnalyticsRolloutControlReport = {
  version?: string
  rollout_status: 'READY' | 'READY_WITH_WARNINGS' | 'DISABLED' | string
  enabled: boolean
  mode: string
  allow_backfill: boolean
  allow_export: boolean
  scope?: Record<string, string[]>
  counters?: Record<string, number>
  blocker_count: number
  warning_count: number
  issues?: AnalyticsDataQualityIssue[]
  items?: AnalyticsRolloutClass[]
  next_actions?: string[]
  safe_policy?: string
  disclaimer?: string
}

export type AnalyticsMonitoringReport = {
  version?: string
  monitoring_status: 'OK' | 'WARNING' | 'BLOCKED' | string
  ready_for_rollout: boolean
  scheduler_enabled: boolean
  seconds_since_last_ingest?: number | null
  active_analytics_jobs: number
  stuck_analytics_job_count: number
  stuck_jobs?: { id: string; class_id?: string | null; status?: string | null; created_at?: string | null; progress_label?: string | null }[]
  snapshot_count: number
  stale_snapshot_count: number
  latest_behavior_calculated_at?: string | null
  ingest?: Record<string, any>
  issue_count: number
  blocker_count: number
  warning_count: number
  issues?: AnalyticsDataQualityIssue[]
  next_actions?: string[]
  safe_policy?: string
}

export type AnalyticsPilotAcceptanceClass = {
  class_id: string
  class_code?: string | null
  class_name?: string | null
  campus?: string | null
  branch?: string | null
  course_id?: string | null
  student_count: number
  behavior_snapshot_count: number
  session_count: number
  session_progress_count: number
  video_progress_count: number
  classification_breakdown?: Record<string, number>
  data_quality_breakdown?: Record<string, number>
  latest_behavior_calculated_at?: string | null
  acceptance_status: 'PASS' | 'WARN' | 'FAIL' | string
  reasons?: string[]
  recommended_action?: string | null
}

export type AnalyticsPilotAcceptanceStudent = {
  class_id: string
  course_id: string
  username: string
  classification?: string | null
  display_label?: string | null
  confidence_score?: number | null
  real_learning_score?: number | null
  idle_score?: number | null
  suspicious_score?: number | null
  reason_codes?: string[]
  summary?: string | null
  recommended_action?: string | null
  data_quality?: string | null
  calculated_at?: string | null
}

export type AnalyticsPilotAcceptanceReport = {
  version?: string
  pilot_status: 'PASS' | 'PASS_WITH_WARNINGS' | 'FAIL' | string
  ready_for_pilot: boolean
  ready_for_broad_production: boolean
  blocker_count: number
  warning_count: number
  blocker_codes?: string[]
  warning_codes?: string[]
  filters?: Record<string, any>
  checks?: Record<string, any>
  checklist?: { key: string; label: string; passed: boolean }[]
  classes?: AnalyticsPilotAcceptanceClass[]
  sample_students?: AnalyticsPilotAcceptanceStudent[]
  next_actions?: string[]
  production_readiness?: AnalyticsProductionReadinessReport
  data_quality?: AnalyticsDataQualityReport
  backfill_plan?: AnalyticsBackfillPlanResponse
  safe_policy?: string
  disclaimer?: string
}


export type AnalyticsEvidencePackReport = {
  version?: string
  artifact_type?: string
  evidence_status: 'PASS' | 'PASS_WITH_WARNINGS' | 'FAIL' | string
  generated_at?: string | null
  filters?: Record<string, any>
  summary?: {
    ready_for_production?: boolean
    ready_for_pilot?: boolean
    ready_for_broad_production?: boolean
    sla_status?: string | null
    pilot_status?: string | null
    blocker_count?: number
    warning_count?: number
    pilot_class_count?: number
    sample_student_count?: number
  }
  blockers?: AnalyticsDataQualityIssue[]
  warnings?: AnalyticsDataQualityIssue[]
  next_actions?: string[]
  reports?: Record<string, any>
  safe_policy?: string
  read_only_guarantees?: string[]
  disclaimer?: string
}

export type AnalyticsCourseClassMappingItem = {
  class_id: string
  class_code?: string | null
  class_name?: string | null
  campus?: string | null
  branch?: string | null
  term_id?: string | null
  term_name?: string | null
  subject_id?: string | null
  subject_code?: string | null
  subject_name?: string | null
  mapping_status: string
  reliability_status: string
  resolved_course_id?: string | null
  mapping_source?: string | null
  candidate_count: number
  confidence_score: number
  roster_count: number
  tracking_event_count: number
  tracking_user_count: number
  latest_tracking_event_at?: string | null
  course_session_count: number
  video_progress_count: number
  session_progress_count: number
  snapshot_count: number
  latest_snapshot_at?: string | null
  missing_snapshot_count: number
  reasons?: string[]
  recommended_action?: string | null
  mapping?: Record<string, any>
}

export type AnalyticsCourseClassMappingReport = {
  version?: string
  report_type?: string
  status: 'READY' | 'READY_WITH_WARNINGS' | 'BLOCKED' | string
  summary_label?: string
  generated_at?: string | null
  filters?: Record<string, any>
  dry_run: boolean
  read_only: boolean
  mutation_performed: boolean
  total_scope_classes: number
  returned_classes: number
  blocker_count: number
  warning_count: number
  counts?: Record<string, number>
  resolved_course_count?: number
  courses_with_events_without_class_mapping_count?: number
  courses_with_events_without_class_mapping?: Array<{ course_id: string; event_count: number; user_count: number; latest_event_at?: string | null; recommended_action?: string | null }>
  items?: AnalyticsCourseClassMappingItem[]
  next_actions?: string[]
  safe_policy?: string
  read_only_guarantees?: string[]
  disclaimer?: string
}

export type AnalyticsBackfillPlanItem = {
  class_id: string
  class_code?: string | null
  class_name?: string | null
  campus?: string | null
  branch?: string | null
  course_id?: string | null
  student_count: number
  session_count: number
  behavior_snapshot_count: number
  latest_behavior_calculated_at?: string | null
  can_enqueue: boolean
  reasons?: string[]
  recommended_action?: string | null
}

export type AnalyticsBackfillPlanResponse = {
  status: string
  version?: string
  filters?: Record<string, any>
  total: number
  counters?: Record<string, number>
  items: AnalyticsBackfillPlanItem[]
  safe_policy?: string
}

export type AnalyticsBackfillJobsResponse = {
  status: string
  queued_jobs: number
  skipped_count: number
  jobs: Array<{ job_id: string; class_id?: string | null; course_id?: string | null; status?: string | null; progress_label?: string | null }>
  skipped: Array<{ class_id?: string | null; class_code?: string | null; reasons?: string[] }>
  safe_policy?: string
}

export type AnalyticsLearningDashboardStudent = AnalyticsLearningBehaviorRow & {
  class_code?: string | null
  campus?: string | null
}

export type AnalyticsLearningDashboardClassItem = {
  class_id: string
  class_code?: string | null
  class_name?: string | null
  campus?: string | null
  branch?: string | null
  course_id?: string | null
  total_students: number
  likely_real_learning_count: number
  possible_idle_count: number
  possible_suspicious_count: number
  insufficient_data_count: number
  normal_count: number
  avg_confidence_score?: number | null
  avg_deadline_compliance_percent?: number | null
}

export type AnalyticsLearningDashboardResponse = AnalyticsLearningBehaviorSummary & {
  filters?: Record<string, any>
  class_items?: AnalyticsLearningDashboardClassItem[]
  top_possible_suspicious?: AnalyticsLearningDashboardStudent[]
  top_possible_idle?: AnalyticsLearningDashboardStudent[]
  deadline_attention?: AnalyticsLearningDashboardStudent[]
}

export type AnalyticsClassVideoSummary = {
  class_id?: string | null
  course_id?: string | null
  total_students: number
  students_with_video_activity: number
  students_without_video_activity: number
  avg_completion_percent?: number | null
  avg_watch_seconds?: number | null
  completed_video_count: number
  low_activity_student_count: number
  possible_idle_count: number
  possible_suspicious_count: number
  likely_real_learning_count: number
  insufficient_data_count: number
  disclaimer?: string
}

export type AnalyticsClassSessionProgressItem = {
  session_index: number
  session_title?: string | null
  week_index?: number | null
  deadline_at?: string | null
  deadline_source?: string | null
  total_students: number
  completed_before_deadline_count: number
  completed_late_count: number
  not_started_count: number
  possible_idle_count: number
  possible_suspicious_count: number
  avg_video_completion_percent?: number | null
  avg_watch_seconds?: number | null
}

export type AnalyticsClassSessionProgressResponse = {
  class_id?: string | null
  course_id?: string | null
  total: number
  items: AnalyticsClassSessionProgressItem[]
}

export type AcademicStudentListResponse = PaginatedResponse<AcademicStudent>



export type AcademicCampus = {
  id: string
  campus_code: string
  campus_name: string
  branch?: string | null
  active: boolean
  sort_order: number
  metadata_json?: Record<string, any> | null
}

export type AcademicAPOption = {
  value: string
  label: string
  description?: string | null
  meta?: Record<string, any>
}

export type AcademicAPSyncOptions = {
  branches: AcademicAPOption[]
  campuses: AcademicAPOption[]
  terms: AcademicAPOption[]
  subjects: AcademicAPOption[]
  warnings: string[]
}

export type AcademicSyncRun = {
  id: string
  source: string
  mode: string
  status: string
  requested_by?: string | null
  term_name?: string | null
  campus?: string | null
  branch?: string | null
  counters_json?: Record<string, any> | null
  error_message?: string | null
  started_at: string
  finished_at?: string | null
  created_at: string
}

export type AcademicSyncResult = {
  ok: boolean
  message: string
  sync_run: AcademicSyncRun
  counters: Record<string, number>
}


export type AcademicCourseMappingValidation = {
  ok: boolean
  can_save: boolean
  risk_level: 'low' | 'medium' | 'high' | string
  message: string
  checks: Array<Record<string, any>>
  suggested_openedx_course_id?: string | null
  parsed_course?: Record<string, any> | null
}

export type AcademicCourseMapping = {
  id: string
  term_id: string
  term_name?: string | null
  block_id?: string | null
  block_name?: string | null
  subject_id: string
  subject_code?: string | null
  subject_name?: string | null
  campus?: string | null
  branch?: string | null
  openedx_course_id: string
  openedx_course_title?: string | null
  validation_status: string
  validation_json?: Record<string, any> | null
  validated_at?: string | null
  note?: string
  active: boolean
  created_by?: string | null
  updated_by?: string | null
  created_at?: string | null
  updated_at?: string | null
}

export type AcademicClassCourseMapping = {
  id: string
  class_id: string
  class_code?: string | null
  openedx_course_id: string
  openedx_cohort_name?: string | null
  openedx_course_title?: string | null
  mapping_source: string
  validation_status: string
  validation_json?: Record<string, any> | null
  validated_at?: string | null
  note?: string
  active: boolean
}

export type AcademicClassCourseMappingProposal = {
  class_id: string
  class_code: string
  suggested_openedx_course_id: string
  suggested_cohort_name: string
  inherited_course_mapping?: AcademicCourseMapping | null
  effective_openedx_course_id?: string | null
  effective_openedx_cohort_name?: string | null
  effective_mapping_source: string
  checks: Array<Record<string, any>>
}

export type AcademicCourseMappingListResponse = PaginatedResponse<AcademicCourseMapping>
export type AcademicSubjectManagementListResponse = PaginatedResponse<AcademicSubjectManagement> & { summary?: AcademicSubjectManagementSummary }


export type AcademicSubjectAutoMapAllSyncResult = {
  ok: boolean
  message: string
  job_id?: string | null
  status?: string | null
  term_id: string
  branch?: string | null
  campus?: string | null
  subject_total: number
  subject_mapped: number
  subject_already_mapped: number
  subject_failed: number
  class_total: number
  jobs_queued: number
  jobs_reused: number
  jobs_skipped: number
  capped?: boolean
  subject_results?: Array<Record<string, any>>
  job_ids?: string[]
}

export type AcademicSubjectCourseAutoMapResult = {
  ok: boolean
  status: string
  message: string
  suggested_openedx_course_id?: string | null
  mapping?: AcademicCourseMapping | null
}



export type SecurityReadinessCheck = {
  category?: string
  code?: string
  severity?: 'BLOCKER' | 'WARNING' | 'INFO' | string
  ok?: boolean
  message?: string
  action?: string
  actual?: any
  target?: string
}

export type SecurityReadinessReport = {
  version?: string
  report_type?: string
  generated_at?: string | null
  app_env?: string
  status: 'READY' | 'READY_WITH_WARNINGS' | 'BLOCKED' | string
  summary_label?: string
  blocker_count: number
  warning_count: number
  info_count?: number
  can_pilot?: boolean
  can_broad_production?: boolean
  primary_blocker?: SecurityReadinessCheck | null
  checks?: SecurityReadinessCheck[]
  sections?: Array<{ key: string; title?: string; status?: string; blocker_count?: number; warning_count?: number; check_count?: number }>
  next_actions?: string[]
  safe_policy?: string
  read_only_guarantees?: string[]
  disclaimer?: string
}



export type ReleaseCandidateGate = {
  key: string
  title?: string
  status?: 'OK' | 'WARNING' | 'BLOCKED' | string
  blocker_count?: number
  warning_count?: number
  message?: string
  report_endpoint?: string
}

export type ReleaseCandidateIssue = {
  source?: string
  severity?: 'BLOCKER' | 'WARNING' | 'INFO' | string
  code?: string
  message?: string
  action?: string
}

export type ReleaseCandidateReport = {
  version?: string
  report_type?: string
  release_candidate?: string
  generated_at?: string | null
  status: 'PASS' | 'PASS_WITH_WARNINGS' | 'FAIL' | string
  go_no_go?: 'GO_PILOT' | 'GO_PILOT_WITH_MONITORING' | 'GO_BROAD_PRODUCTION' | 'HOLD' | string
  summary_label?: string
  ready_for_pilot?: boolean
  ready_for_broad_production?: boolean
  blocker_count?: number
  warning_count?: number
  filters?: Record<string, any>
  gates?: ReleaseCandidateGate[]
  blockers?: ReleaseCandidateIssue[]
  warnings?: ReleaseCandidateIssue[]
  next_actions?: string[]
  reports?: Record<string, any>
  safe_policy?: string
  read_only_guarantees?: string[]
  disclaimer?: string
}



export type PilotOperationsPhase = {
  key: string
  title?: string
  status?: string
  checks?: string[]
}

export type PilotOperationsTrigger = {
  code?: string
  severity?: string
  condition?: string
  action?: string
}

export type PilotOperationsReport = {
  version?: string
  report_type?: string
  release_candidate?: string
  generated_at?: string | null
  status: 'PILOT_READY' | 'PILOT_WITH_MONITORING' | 'HOLD' | string
  decision?: 'GO_PILOT' | 'GO_CONTROLLED_PILOT' | 'NO_GO' | string
  summary_label?: string
  ready_for_pilot?: boolean
  ready_for_broad_production?: boolean
  blocker_count?: number
  warning_count?: number
  filters?: Record<string, any>
  release_candidate_summary?: Record<string, any>
  gates?: ReleaseCandidateGate[]
  phases?: PilotOperationsPhase[]
  monitoring_cadence?: Array<{ window?: string; frequency?: string; check?: string }>
  rollback_triggers?: PilotOperationsTrigger[]
  evidence_required?: string[]
  signoff?: Record<string, any>
  blockers?: ReleaseCandidateIssue[]
  warnings?: ReleaseCandidateIssue[]
  next_actions?: string[]
  safe_policy?: string
  read_only_guarantees?: string[]
  disclaimer?: string
}

export type PerformanceReadinessCheck = {
  category?: string
  code?: string
  severity?: 'BLOCKER' | 'WARNING' | 'INFO' | string
  ok?: boolean
  message?: string
  action?: string
  actual?: any
  target?: string
  table?: string
  missing_indexes?: string[]
}

export type PerformanceReadinessReport = {
  version?: string
  report_type?: string
  generated_at?: string | null
  status: 'READY' | 'READY_WITH_WARNINGS' | 'BLOCKED' | string
  summary_label?: string
  blocker_count: number
  warning_count: number
  checks?: PerformanceReadinessCheck[]
  sections?: Array<{ key: string; title?: string; status?: string; blocker_count?: number; warning_count?: number; check_count?: number }>
  table_estimates?: { source?: string; items?: Array<{ table: string; estimated_rows?: number }>; error_type?: string }
  queue_pressure?: Record<string, any>
  limits?: Record<string, any>
  next_actions?: string[]
  safe_policy?: string
  read_only_guarantees?: string[]
  disclaimer?: string
}
