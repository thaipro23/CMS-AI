import type { AnalyticsMLAnalysis } from '../../types'
import { formatVNDateTime } from '../../lib/time'

const labels: Record<string, string> = {
  completion_watch_gap: 'Chênh lệch hoàn thành và xem', watch_ratio: 'Tỷ lệ thời gian xem',
  seeks_per_watch_minute: 'Lần tua trên mỗi phút xem', passive_ratio: 'Tỷ lệ xem thụ động',
  seconds_per_independent_submission: 'Giây giữa các lần nộp độc lập',
  successful_resets_per_attempt: 'Lần đặt lại thành công', submissions_per_response: 'Lần nộp trên mỗi đáp ứng',
}
const reasons: Record<string, string> = {
  BASELINE_TOO_SMALL: 'Chưa đủ sinh viên có dữ liệu tương đương để đối chiếu.',
  INSUFFICIENT_MEASURABLE_VIDEOS: 'Cần ít nhất ba video có số liệu đo hợp lệ.',
  MISSING_VIDEO_DURATION: 'Thiếu thời lượng video để đối chiếu.',
  MISSING_SESSION_MAPPING: 'Chưa xác định được nội dung học tương ứng.',
  MISSING_CONTENT_VERSION: 'Thiếu phiên bản câu hỏi đáng tin cậy.',
  UNTRUSTED_QUIZ_SESSION: 'Thiếu mốc bắt đầu được máy chủ xác nhận.',
  INSUFFICIENT_INDEPENDENT_TIMING: 'Chưa đủ mốc nộp độc lập để đối chiếu.',
  CONSTANT_FEATURES: 'Dữ liệu nhóm chưa có độ biến thiên để phân tích.',
  RECALCULATION_REQUIRED: 'Cần tính lại để cập nhật dữ liệu học máy.',
}
function measurement(feature: string, value: number) {
  return ['watch_ratio', 'passive_ratio', 'completion_watch_gap'].includes(feature)
    ? `${(value * 100).toFixed(1)}%` : value.toFixed(2)
}
export default function MLAnalysisCard({ analysis }: { analysis?: AnalyticsMLAnalysis | null }) {
  if (!analysis || analysis.status === 'DISABLED') return null
  const scored = analysis.status === 'SCORED'
  const title = analysis.family === 'video' ? 'Phân tích học máy video' : 'Phân tích học máy quiz'
  const status = scored ? (analysis.outlier ? 'Khác biệt so với nhóm tham chiếu' : 'Chưa thấy khác biệt rõ so với nhóm')
    : analysis.status === 'ERROR' ? 'Chưa tính được kết quả'
      : analysis.status === 'INSUFFICIENT_DATA' ? 'Chưa đủ dữ liệu' : 'Cần cập nhật kết quả'
  return <section className="analytics-detail-box" aria-label={title}>
    <h4>{title}</h4>
    <b>{status}</b>
    <p>Nhóm tham chiếu: {analysis.reference_count} sinh viên có dữ liệu tương đương.</p>
    {analysis.calculated_at && <small>Cập nhật: {formatVNDateTime(analysis.calculated_at)}</small>}
    {scored && analysis.reference_percentile != null && <p>Chỉ số khác biệt trong nhóm: <b>{analysis.reference_percentile.toFixed(1)}/100</b></p>}
    {analysis.reason_codes.map(code => <p key={code}>{reasons[code] || 'Chưa có đủ dữ liệu đo hợp lệ cho phân tích này.'}</p>)}
    {scored && analysis.deviations.length > 0 && <table className="table">
      <caption>Số liệu đo so với trung vị nhóm tham chiếu</caption>
      <thead><tr><th>Đặc trưng</th><th>Sinh viên</th><th>Trung vị nhóm</th></tr></thead>
      <tbody>{analysis.deviations.map(d => <tr key={d.feature}>
        <td>{labels[d.feature] || 'Đặc trưng đo được'}</td>
        <td>{measurement(d.feature, d.value)}</td><td>{measurement(d.feature, d.reference_median)}</td>
      </tr>)}</tbody>
    </table>}
    <small>Phân tích chạy song song với luật hiện có, không đổi điểm hoặc phân loại học tập. Chỉ số phản ánh mức khác biệt trong nhóm, không phải xác suất vi phạm. Các độ lệch mô tả số liệu; giảng viên cần xác minh.</small>
  </section>
}
