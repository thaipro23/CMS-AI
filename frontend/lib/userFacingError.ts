/** Keep actionable validation text; diagnostic codes remain on ApiRequestError. */
export function userFacingError(error: unknown, fallback = 'Thao tác chưa hoàn tất. Vui lòng thử lại.'): string {
  const raw = error instanceof Error ? error.message : typeof error === 'string' ? error : ''
  const message = raw.trim().replace(/\s*\[[A-Z][A-Z0-9_.:-]+\]\s*$/, '').replace(/^Value error,\s*/i, '')
  if (!message) return fallback
  if (/traceback|sqlalchemy|stack trace|<!doctype|<html|\b(?:TypeError|ReferenceError):|\{"(?:error|detail)"/i.test(message)) return fallback
  if (/^(?:HTTP\s*)?401\b|unauthori[sz]ed|invalid access token|missing bearer/i.test(message)) return 'Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại.'
  if (/^(?:HTTP\s*)?403\b|forbidden|does not have permission|access denied/i.test(message)) return 'Bạn không có quyền thực hiện thao tác này.'
  if (/^(?:HTTP\s*)?404\b|^(?:question|course|release|batch|job) not found$/i.test(message)) return 'Không tìm thấy dữ liệu cần xử lý.'
  if (/failed to fetch|network error|networkerror/i.test(message)) return 'Không kết nối được máy chủ. Vui lòng thử lại.'
  if (/timeout|timed out/i.test(message)) return 'Yêu cầu xử lý quá thời gian cho phép. Kiểm tra trạng thái tác vụ trước khi thử lại.'
  if (/^(?:internal server error|bad gateway|service unavailable)$/i.test(message)) return 'Máy chủ tạm thời chưa đáp ứng. Vui lòng thử lại sau.'
  return message
}

const fieldLabels: Record<string, string> = {
  user_id: 'Tài khoản', email: 'Email', role_code: 'Vai trò', scope_type: 'Loại phạm vi', scope_id: 'Phạm vi', scope_ids: 'Phạm vi',
  campus_code: 'Mã cơ sở', campus_name: 'Tên cơ sở', branch: 'Hệ đào tạo', term_code: 'Mã học kỳ', term_name: 'Tên học kỳ',
  term_id: 'Học kỳ', block_id: 'Block', subject_id: 'Môn học', subject_code: 'Mã môn', class_id: 'Lớp',
  total_questions: 'Số câu hỏi', difficulty_easy: 'Tỷ lệ câu dễ', difficulty_medium: 'Tỷ lệ câu trung bình', difficulty_hard: 'Tỷ lệ câu khó',
  start_date: 'Ngày bắt đầu', end_date: 'Ngày kết thúc', title: 'Tiêu đề', file: 'Tệp', files: 'Tệp',
}

/** Preserve structured validation for diagnostics; translate its visible text. */
export function userFacingValidation(entry: Record<string, unknown>): string {
  const type = String(entry.type || '')
  const context = entry.ctx && typeof entry.ctx === 'object' ? entry.ctx as Record<string, unknown> : {}
  let message = String(entry.msg || entry.message || entry.detail || 'Dữ liệu không hợp lệ.').replace(/^Value error,\s*/i, '')
  if (type === 'missing') message = 'Cần nhập hoặc chọn giá trị.'
  else if (type === 'greater_than_equal') message = `Giá trị phải từ ${context.ge} trở lên.`
  else if (type === 'less_than_equal') message = `Giá trị không được vượt quá ${context.le}.`
  else if (type === 'greater_than') message = `Giá trị phải lớn hơn ${context.gt}.`
  else if (type === 'less_than') message = `Giá trị phải nhỏ hơn ${context.lt}.`
  else if (type === 'string_too_short') message = `Cần ít nhất ${context.min_length} ký tự.`
  else if (type === 'string_too_long') message = `Chỉ nhập tối đa ${context.max_length} ký tự.`
  else if (type === 'too_short') message = `Cần chọn ít nhất ${context.min_length} mục.`
  else if (type === 'too_long') message = `Chỉ chọn tối đa ${context.max_length} mục.`
  else if (/^(int|float|decimal)_/.test(type)) message = 'Cần nhập số hợp lệ.'
  else if (/^(date|datetime)_/.test(type)) message = 'Cần nhập ngày hợp lệ.'
  else if (type === 'literal_error' || type === 'enum') message = 'Giá trị không thuộc danh sách cho phép.'
  else if (type === 'json_invalid') message = 'Dữ liệu gửi lên không đúng định dạng.'
  const loc = Array.isArray(entry.loc) ? entry.loc : []
  const field = [...loc].reverse().find((part) => typeof part === 'string' && fieldLabels[part]) as string | undefined
  return `${field ? `${fieldLabels[field]}: ` : ''}${userFacingError(message)}`
}
