'use client'

import { Question } from '../../types'
import { StatusBadge } from '../ui/StatusBadge'
import { LoadingButton } from '../ui/LoadingButton'

type QuestionTableProps = {
  questions: Question[]
  withCheckbox?: boolean
  selectedIds?: string[]
  onToggleSelect?: (id: string) => void
  canEdit: boolean
  canReview: boolean
  canPublish: boolean
  canDelete?: boolean
  onEdit: (question: Question) => void
  onApprove: (id: string) => void
  onReject: (id: string) => void
  onPublish: (id: string) => void
  onDelete?: (question: Question) => void
  onRepair?: (question: Question) => void
  onKeepAnyway?: (question: Question) => void
  onChangeStatus: (id: string, status: string, note: string) => void
  onPreviewOlx: (id: string) => void
  onSourceTrace?: (question: Question) => void
  actionLoading?: string | null
  startIndex?: number
}

const answerRows = [
  ['A', 'option_a'],
  ['B', 'option_b'],
  ['C', 'option_c'],
  ['D', 'option_d'],
] as const

function errorMessage(question: Question) {
  const reason = question.draft_error_reason || (question.quality_flags || [])[0]
  if (!reason) return null
  const detail = question.draft_error_detail || {}
  if (reason === 'duplicate_question') {
    const score = question.duplicate_score || detail.duplicate_score
    return `Trùng/gần trùng${score ? ` (${Math.round(Number(score) * 100)}%)` : ''}${question.duplicate_of_question_id ? ` với ${question.duplicate_of_question_id.slice(0, 8)}` : ''}`
  }
  const labels: Record<string, string> = {
    invalid_answer: 'Đáp án đúng không hợp lệ',
    invalid_source_chunk: 'Source chunk không tồn tại',
    similar_options: 'Các đáp án quá giống nhau',
    duplicate_options: 'Đáp án bị trùng',
    anti_trick: 'Vi phạm anti-trick rule',
    double_negative: 'Câu hỏi có phủ định kép',
    missing_options: 'Thiếu đáp án',
    missing_question: 'Thiếu câu hỏi',
  }
  return labels[reason] || reason
}

export function QuestionTable({ questions, withCheckbox = false, selectedIds = [], onToggleSelect, canEdit, canReview, canPublish, canDelete = false, onEdit, onApprove, onReject, onPublish, onDelete, onRepair, onKeepAnyway, onChangeStatus, onPreviewOlx, onSourceTrace, actionLoading = null, startIndex = 0 }: QuestionTableProps) {
  if (!questions.length) return <div className="empty-state">Chưa có câu hỏi phù hợp với bộ lọc hiện tại.</div>

  return <div className="question-card-list">
    {questions.map((question, index) => {
      const draftReason = question.status === 'draft_error' ? errorMessage(question) : null
      const busy = (action: string) => actionLoading === `${question.id}:${action}`
      const anyBusy = Boolean(actionLoading)
      return <article className={anyBusy && actionLoading?.startsWith(question.id) ? 'question-review-card busy-card' : 'question-review-card'} key={question.id}>
        <div className="question-main-box">
          <div className="question-main-head">
            <div className="question-index">#{startIndex + index + 1}</div>
            {withCheckbox && (question.status === 'pending_review' || question.status === 'needs_review') && <label className="question-select">
              <input type="checkbox" checked={selectedIds.includes(question.id)} onChange={() => onToggleSelect?.(question.id)} />
              <span>Chọn</span>
            </label>}
          </div>
          <div className="question-prompt">{question.question_text}</div>
          <div className="answer-grid">
            {answerRows.map(([letter, field]) => {
              const isCorrect = question.correct_answer === letter
              return <div key={letter} className={isCorrect ? 'answer-option correct' : 'answer-option'}>
                <span className="answer-letter">{letter}</span>
                <span>{question[field]}</span>
              </div>
            })}
          </div>
          <div className="question-meta-row">
            {question.concept_title && <span>Concept: <b>{question.concept_title}</b></span>}
            {question.question_family_id && <span>Family: <code>{question.question_family_id}</code></span>}
            {question.variant_no && <span>Variant: <b>{question.variant_no}</b></span>}
          </div>
          {draftReason && <div className="draft-error-reason">
            <strong>Lý do draft_error:</strong> {draftReason}
            {question.draft_error_detail?.message && <span> · {String(question.draft_error_detail.message)}</span>}
          </div>}
        </div>

        <div className="question-control-box">
          <div className="question-control-status">
            <div className="box-label">Trạng thái</div>
            <StatusBadge status={question.status} />
            {question.difficulty && <small className="control-note">{question.difficulty.toUpperCase()}</small>}
          </div>
          <div className="question-control-actions">
            <div className="box-label">Thao tác</div>
            <div className="question-actions">
              {question.status !== 'published' && <LoadingButton className="btn small secondary" loading={busy('edit')} disabled={!canEdit || anyBusy} onClick={() => onEdit(question)}>Sửa</LoadingButton>}
              {question.status === 'draft_error' && <>
                {onRepair && <LoadingButton className="btn small" loading={busy('repair')} disabled={!canEdit || anyBusy} onClick={() => onRepair(question)}>Sửa lỗi</LoadingButton>}
                {onKeepAnyway && <LoadingButton className="btn small success" loading={busy('keep')} disabled={!canReview || anyBusy} onClick={() => onKeepAnyway(question)}>Giữ lại</LoadingButton>}
              </>}
              {(question.status === 'pending_review' || question.status === 'needs_review') && <>
                <LoadingButton className="btn small success" loading={busy('approve')} disabled={!canReview || anyBusy} onClick={() => onApprove(question.id)}>Duyệt</LoadingButton>
                <LoadingButton className="btn small danger" loading={busy('reject')} disabled={!canReview || anyBusy} onClick={() => onReject(question.id)}>Từ chối</LoadingButton>
              </>}
              {question.status === 'approved' && <>
                <LoadingButton className="btn small" loading={busy('publish')} disabled={!canPublish || anyBusy} onClick={() => onPublish(question.id)}>Publish</LoadingButton>
                <LoadingButton className="btn small secondary" loading={busy('undo')} disabled={!canReview || anyBusy} onClick={() => onChangeStatus(question.id, 'pending_review', 'Hoàn tác duyệt')}>Hoàn tác</LoadingButton>
                <LoadingButton className="btn small danger" loading={busy('reject')} disabled={!canReview || anyBusy} onClick={() => onChangeStatus(question.id, 'rejected', 'Chuyển sang từ chối')}>Từ chối</LoadingButton>
              </>}
              {question.status === 'rejected' && <>
                <LoadingButton className="btn small secondary" loading={busy('undo')} disabled={!canReview || anyBusy} onClick={() => onChangeStatus(question.id, 'pending_review', 'Hoàn tác từ chối')}>Hoàn tác</LoadingButton>
                <LoadingButton className="btn small success" loading={busy('approve')} disabled={!canReview || anyBusy} onClick={() => onChangeStatus(question.id, 'approved', 'Chuyển sang duyệt')}>Duyệt</LoadingButton>
              </>}
              <LoadingButton className="btn small secondary" loading={busy('olx')} disabled={anyBusy} onClick={() => onPreviewOlx(question.id)}>OLX</LoadingButton>
              {onSourceTrace && <LoadingButton className="btn small secondary" loading={busy('source')} disabled={anyBusy} onClick={() => onSourceTrace(question)}>Xem nguồn</LoadingButton>}
              {onDelete && question.status !== 'published' && <LoadingButton className="btn small danger" loading={busy('delete')} disabled={!canDelete || anyBusy} onClick={() => onDelete(question)}>Xóa</LoadingButton>}
            </div>
            {question.status === 'published' && <small className="control-note">Đã publish: không xóa trực tiếp để tránh lệch với Open edX.</small>}
          </div>
        </div>
      </article>
    })}
  </div>
}
