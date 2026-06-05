'use client'

import { EditQuestionForm, Question } from '../../types'

type Props = {
  question: Question
  form: EditQuestionForm
  canEdit: boolean
  onChange: <K extends keyof EditQuestionForm>(key: K, value: EditQuestionForm[K]) => void
  onSave: () => void
  onCancel: () => void
}

export function QuestionEditPanel({ question, form, canEdit, onChange, onSave, onCancel }: Props) {
  return <div className="modal-backdrop"><section className="card edit-panel modal-card">
    <h2>Sửa câu hỏi</h2>
    <p className="helper"><b>ID:</b> {question.id} · <b>Phiên bản:</b> {question.version} · <b>Trạng thái:</b> {question.status}</p>
    <div className="grid grid-3">
      <div><label>Node / Phạm vi</label><input className="input" value={form.node_title} onChange={(event) => onChange('node_title', event.target.value)} /></div>
      <div><label>Độ khó</label><select className="input" value={form.difficulty} onChange={(event) => onChange('difficulty', event.target.value)}><option value="easy">Dễ</option><option value="medium">Trung bình</option><option value="hard">Khó</option></select></div>
      <div><label>Trạng thái review</label><select className="input" value={form.target_status} onChange={(event) => onChange('target_status', event.target.value)}><option value="pending_review">Chờ duyệt</option><option value="approved">Đã duyệt</option><option value="rejected">Đã từ chối</option></select></div>
      <div><label>Family ID (backend tự tính)</label><input className="input" value={form.question_family_id} readOnly /></div>
      <div><label>Variant (backend tự đánh số)</label><input className="input" type="number" min="1" value={form.variant_no} readOnly /></div>
      <div><label>Mức nhận thức</label><select className="input" value={form.cognitive_level} onChange={(event) => onChange('cognitive_level', event.target.value)}><option value="remember">Ghi nhớ</option><option value="understand">Hiểu</option><option value="recognize_example">Nhận diện ví dụ</option><option value="simple_apply">Áp dụng đơn giản</option></select></div>
      <div><label>Đáp án đúng</label><select className="input" value={form.correct_answer} onChange={(event) => onChange('correct_answer', event.target.value)}><option>A</option><option>B</option><option>C</option><option>D</option></select></div>
    </div>
    <label>Mục tiêu học tập</label><input className="input" value={form.learning_objective} onChange={(event) => onChange('learning_objective', event.target.value)} />
    <label>Câu hỏi</label><textarea className="input" rows={3} value={form.question_text} onChange={(event) => onChange('question_text', event.target.value)} />
    <div className="grid grid-2"><div><label>A</label><input className="input" value={form.option_a} onChange={(event) => onChange('option_a', event.target.value)} /></div><div><label>B</label><input className="input" value={form.option_b} onChange={(event) => onChange('option_b', event.target.value)} /></div><div><label>C</label><input className="input" value={form.option_c} onChange={(event) => onChange('option_c', event.target.value)} /></div><div><label>D</label><input className="input" value={form.option_d} onChange={(event) => onChange('option_d', event.target.value)} /></div></div>
    <label>Giải thích</label><textarea className="input" rows={2} value={form.explanation} onChange={(event) => onChange('explanation', event.target.value)} />
    <div className="grid grid-3"><div><label>Loại nguồn</label><input className="input" value={form.source_type} onChange={(event) => onChange('source_type', event.target.value)} /></div><div><label>Nguồn tham chiếu</label><input className="input" value={form.source_ref} onChange={(event) => onChange('source_ref', event.target.value)} /></div><div><label>Trang nguồn</label><input className="input" value={form.source_page} onChange={(event) => onChange('source_page', event.target.value)} /></div><div><label>Thời điểm bắt đầu</label><input className="input" value={form.source_timestamp_start} onChange={(event) => onChange('source_timestamp_start', event.target.value)} /></div><div><label>Thời điểm kết thúc</label><input className="input" value={form.source_timestamp_end} onChange={(event) => onChange('source_timestamp_end', event.target.value)} /></div><div><label>ID chunk</label><input className="input" value={form.source_chunk_id} onChange={(event) => onChange('source_chunk_id', event.target.value)} /></div></div>
    <label>Trích đoạn nguồn</label><textarea className="input" rows={2} value={form.source_excerpt} onChange={(event) => onChange('source_excerpt', event.target.value)} />
    <label>Source evidence / bằng chứng nguồn</label><textarea className="input" rows={2} value={form.source_evidence} onChange={(event) => onChange('source_evidence', event.target.value)} />
    <label>Tags, ngăn cách bằng dấu phẩy</label><input className="input" value={form.tags_text} onChange={(event) => onChange('tags_text', event.target.value)} />
    <div className="button-row"><button className="btn" disabled={!canEdit} onClick={onSave}>Lưu chỉnh sửa</button><button className="btn secondary" onClick={onCancel}>Hủy</button></div>
  </section></div>
}
