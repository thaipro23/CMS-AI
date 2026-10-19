import type { AnalyticsMLAnalysis } from '../../types'
import { formatVNDateTime } from '../../lib/time'

const labels: Record<string, string> = {
  completion_watch_gap: 'Chênh lệch hoàn thành và nội dung đã xem', watch_ratio: 'Tỷ lệ nội dung đã xem',
  seeks_per_watch_minute: 'Lần tua trên mỗi phút nội dung', passive_ratio: 'Tỷ lệ xem thụ động',
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
  MISSING_PLAYBACK_MEASUREMENT: 'Thiếu số đo tiến trình nội dung để chuẩn hóa tốc độ phát.',
  INCOMPLETE_PLAYBACK_HISTORY: 'Lịch sử xem chưa đủ để đối chiếu theo tốc độ phát.',
  COMPARISON_UNAVAILABLE: 'Đã tính xếp hạng theo trung vị và MAD; mô hình đối chiếu hiện chưa sẵn sàng.',
}
function measurement(feature: string, value: number) {
  return ['watch_ratio', 'passive_ratio', 'completion_watch_gap'].includes(feature)
    ? `${(value * 100).toFixed(1)}%` : value.toFixed(2)
}
export default function MLAnalysisCard({ analysis }: { analysis?: AnalyticsMLAnalysis | null }) {
  if (!analysis || analysis.status === 'DISABLED') return null
  const scored = analysis.status === 'SCORED'
  const title = analysis.family === 'video' ? 'Xếp hạng hành vi xem video' : 'Xếp hạng hành vi làm quiz'
  const status = scored ? 'Điểm xếp hạng tương đối'
    : analysis.status === 'ERROR' ? 'Chưa tính được kết quả'
      : analysis.status === 'INSUFFICIENT_DATA' ? 'Chưa đủ dữ liệu' : 'Cần cập nhật kết quả'
  return <section className="analytics-detail-box" aria-label={title}>
    <h4>{title}</h4>
    <b>{status}</b>
    <p>Nhóm tham chiếu: {analysis.reference_count} sinh viên có dữ liệu tương đương.</p>
    {scored && analysis.confidence === 'LOW' && <p role="status"><b>Độ tin cậy thấp</b>: nhóm có từ 30 đến 49 sinh viên.</p>}
    {analysis.calculated_at && <small>Cập nhật: {formatVNDateTime(analysis.calculated_at)}</small>}
    {scored && analysis.reference_percentile != null && <p><b>{analysis.reference_percentile.toFixed(1)}/100</b> — điểm cao hơn thể hiện chênh lệch lớn hơn trên các đặc trưng đo được.</p>}
    {scored && analysis.primary_method === 'median_mad' && <p>Trung vị và MAD: đối chiếu từng đặc trưng với trung vị và độ lệch tuyệt đối trung vị của nhóm.</p>}
    {scored && analysis.comparison_status === 'AGREES' && <p>Hai phương pháp cho thứ hạng gần nhau; hiển thị cách giải thích bằng trung vị và MAD.</p>}
    {scored && analysis.comparison_status === 'DIFFERS' && <p>Hai phương pháp cho thứ hạng khác nhau. Điểm đối chiếu Isolation Forest: <b>{analysis.comparison_percentile?.toFixed(1)}/100</b>.</p>}
    {scored && analysis.comparison_status === 'UNINFORMATIVE' && <p>Mô hình đối chiếu chưa tạo được thứ hạng phân biệt rõ.</p>}
    {scored && analysis.measurement?.observed_playback_rate != null && <p>Tốc độ quan sát trung bình: <b>{analysis.measurement.observed_playback_rate.toFixed(2)}×</b>. Tỷ lệ xem đã chuẩn hóa theo tiến trình nội dung.</p>}
    {scored && (analysis.measurement?.pooled_course_count || 0) > 1 && <p>Dữ liệu video tổng hợp từ {analysis.measurement?.pooled_course_count} khóa trong nhóm đối chiếu.</p>}
    {analysis.reason_codes.map(code => <p key={code}>{reasons[code] || 'Chưa có đủ dữ liệu đo hợp lệ cho phân tích này.'}</p>)}
    {scored && analysis.deviations.length > 0 && <table className="table">
      <caption>Các đặc trưng đóng góp vào xếp hạng theo trung vị và MAD</caption>
      <thead><tr><th>Đặc trưng</th><th>Sinh viên</th><th>Trung vị nhóm</th><th>MAD</th></tr></thead>
      <tbody>{analysis.deviations.map(d => <tr key={d.feature}>
        <td>{labels[d.feature] || 'Đặc trưng đo được'}</td>
        <td>{measurement(d.feature, d.value)}</td><td>{measurement(d.feature, d.reference_median)}</td>
        <td>{d.reference_mad != null ? measurement(d.feature, d.reference_mad) : '—'}</td>
      </tr>)}</tbody>
    </table>}
    <small>Xếp hạng dựa trên dữ liệu đo được và giữ nguyên điểm học tập. Giảng viên xem các đặc trưng cùng bối cảnh học của sinh viên.</small>
  </section>
}
