import { AppIcon, type AppIconName } from '../icons/AppIcon'

export type VisualTone = 'blue' | 'green' | 'amber' | 'red' | 'violet' | 'cyan' | 'slate'

export type VisualMeta = { icon: AppIconName; tone: VisualTone }

const rules: Array<{ words: string[]; icon: AppIconName; tone: VisualTone }> = [
  { words: ['sinh viên', 'người học', 'enroll'], icon: 'students', tone: 'green' },
  { words: ['giảng viên', 'teacher'], icon: 'teachers', tone: 'cyan' },
  { words: ['bộ môn', 'môn học', 'câu hỏi', 'ngân hàng', 'tài liệu'], icon: 'book', tone: 'blue' },
  { words: ['phiên bản', 'release', 'bài học', 'chapter'], icon: 'layers', tone: 'violet' },
  { words: ['quiz', 'bài kiểm tra', 'final test'], icon: 'quiz', tone: 'violet' },
  { words: ['course cms', 'cms', 'mapping', 'ghép'], icon: 'link', tone: 'violet' },
  { words: ['cần kiểm tra', 'cảnh báo', 'thất bại', 'từ chối', 'lỗi', 'thiếu'], icon: 'alert', tone: 'red' },
  { words: ['chờ', 'đang chạy', 'deadline', 'thời điểm'], icon: 'clock', tone: 'amber' },
  { words: ['đã duyệt', 'hoàn tất', 'thành công', 'đang dùng', 'hiệu lực'], icon: 'check', tone: 'green' },
  { words: ['học kỳ', 'block', 'tuần học', 'ngày'], icon: 'calendar', tone: 'amber' },
  { words: ['cơ sở', 'campus'], icon: 'campus', tone: 'cyan' },
  { words: ['phân tích', 'tiến độ', 'học tập', 'kết quả'], icon: 'analytics', tone: 'blue' },
  { words: ['tác vụ', 'job', 'việc'], icon: 'jobs', tone: 'cyan' },
  { words: ['nhật ký', 'audit', 'lịch sử'], icon: 'audit', tone: 'slate' },
  { words: ['đồng bộ', 'sync'], icon: 'sync', tone: 'cyan' },
  { words: ['người dùng', 'phân quyền', 'vai trò'], icon: 'users', tone: 'violet' },
  { words: ['bảo mật', 'xác thực', 'sso', 'quyền'], icon: 'shield', tone: 'violet' },
  { words: ['cài đặt', 'cấu hình', 'giới hạn'], icon: 'settings', tone: 'slate' },
  { words: ['mô hình', 'worker', 'máy chủ'], icon: 'server', tone: 'cyan' },
  { words: ['database', 'dữ liệu'], icon: 'database', tone: 'blue' },
  { words: ['chi phí', 'ngân sách', 'pricing'], icon: 'money', tone: 'amber' },
  { words: ['tìm', 'lọc'], icon: 'search', tone: 'blue' },
  { words: ['import', 'tải lên'], icon: 'upload', tone: 'blue' },
  { words: ['export', 'tải xuống'], icon: 'download', tone: 'cyan' },
]

export function inferVisualMeta(label: string, fallback: VisualMeta = { icon: 'dashboard', tone: 'blue' }): VisualMeta {
  const value = String(label || '').toLowerCase()
  return rules.find((rule) => rule.words.some((word) => value.includes(word))) || fallback
}

export function VisualIcon({ label, icon, tone, size = 19, className = '' }: { label?: string; icon?: AppIconName; tone?: VisualTone; size?: number; className?: string }) {
  const inferred = inferVisualMeta(label || '')
  return <span className={`visual-icon visual-tone-${tone || inferred.tone} ${className}`.trim()} aria-hidden="true"><AppIcon name={icon || inferred.icon} size={size} /></span>
}
