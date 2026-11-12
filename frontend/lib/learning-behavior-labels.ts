/** Display names only. Machine reason codes remain stable in API responses. */
const REASON_LABELS: Record<string, string> = {
  LARGE_SEEK_JUMP: 'Tua video qua một đoạn dài',
  HIGH_COMPLETION_LOW_WATCH_TIME: 'Video gần hoàn thành nhưng thời gian xem rất ít',
  MANY_VIDEOS_COMPLETED_TOO_FAST: 'Nhiều video hoàn thành quá nhanh so với thời lượng',
  QUIZ_BEFORE_VIDEO: 'Làm Quiz trước khi xem video',
  DEADLINE_PATTERN_MATCHED: 'Hoạt động học khớp mốc thời hạn',
  WATCH_THEN_ATTEMPT_PROBLEM: 'Có xem video trước khi làm Quiz',
  REPEATED_HIGH_COMPLETION_LOW_WATCH: 'Lặp lại việc hoàn thành video với thời gian xem rất ít',
  MISSING_WATCH_TIMING: 'Thiếu mốc thời gian xem video để đánh giá chính xác',
  BEHAVIOR_RULES_UPDATED: 'Quy tắc đánh giá đã cập nhật, cần tính lại nhận định',
  STALE_BEHAVIOR_SNAPSHOT: 'Kết quả đã cũ, cần tính lại trước khi sử dụng',
  NO_VIDEO_ACTIVITY: 'Chưa ghi nhận hoạt động xem video',
  MISSING_BEHAVIOR_SNAPSHOT: 'Chưa có kết quả phân tích học tập',
  MISSING_SESSION_MAPPING: 'Chưa xác định được video thuộc Bài nào',
  MISSING_DEADLINE_MAPPING: 'Chưa xác định được thời hạn học của Bài',
  MISSING_VIDEO_DURATION: 'Thiếu thời lượng video để đối chiếu thời gian xem',
  ONLY_CAPTION_EVENTS: 'Chỉ có hoạt động phụ đề, chưa đủ log xem video',
  LONG_PASSIVE_PLAYBACK: 'Phát video lâu nhưng ít ghi nhận tương tác',
  CRAMMED_LOW_WATCH: 'Học nhiều Bài trong thời gian ngắn với thời gian xem ít',
  CRAMMED_SESSIONS_CONTEXT_ONLY: 'Học nhiều Bài gần nhau, cần xem cùng các tín hiệu khác',
  COMPLETED_LATE: 'Hoàn thành Bài sau thời hạn',
  SUSPICIOUS_QUIZ_SPEED: 'Thời gian làm Quiz ngắn, cần kiểm tra thêm',
  FISHING_PATTERN: 'Nộp thử nhiều lần với thay đổi đáp án, cần kiểm tra thêm',
  MISSING_CONTENT_VERSION: 'Thiếu phiên bản nội dung tại lúc nộp để đối chiếu đáp án',
  MISSING_QUESTION_IDENTITY: 'Thiếu định danh câu hỏi để đối chiếu đúng câu',
  INSUFFICIENT_COMPARABLE_QUESTIONS: 'Chưa đủ câu hỏi có thể đối chiếu',
  BASELINE_TOO_SMALL: 'Chưa đủ sinh viên làm nhóm tham chiếu',
  INSUFFICIENT_INDEPENDENT_TIMING: 'Nộp cả Bài một lần nên chưa xác định được thời gian từng câu',
}

export function learningReasonText(code?: string | null): string {
  const value = String(code || '').trim().toUpperCase()
  if (!value) return ''
  return REASON_LABELS[value] || 'Dấu hiệu khác cần đối chiếu thêm'
}

export function learningReasonTexts(codes?: string[] | null): string[] {
  return Array.from(new Set((codes || []).map(learningReasonText).filter(Boolean)))
}

export function learningScoreText(score?: number | null): string {
  if (typeof score !== 'number' || !Number.isFinite(score)) return 'Chưa có dữ liệu'
  return `${Math.round(score * 10) / 10}/100`
}

export function watchDurationText(seconds?: number | null): string {
  if (typeof seconds !== 'number' || !Number.isFinite(seconds) || seconds < 0) return 'Chưa có dữ liệu'
  const total = Math.round(seconds)
  if (total < 60) return `${total} giây`
  const minutes = Math.floor(total / 60)
  const remain = total % 60
  if (minutes < 60) return `${minutes} phút${remain ? ` ${remain} giây` : ''}`
  return `${Math.floor(minutes / 60)} giờ${minutes % 60 ? ` ${minutes % 60} phút` : ''}`
}
