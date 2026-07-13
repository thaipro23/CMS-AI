'use client'

import { useMemo } from 'react'
import { EnterpriseDataTable, type EnterpriseTableColumn } from '../../../components/table/EnterpriseDataTable'
import type { TableDensity } from '../../../hooks/useUrlTableState'
import type { BankVersionQuestion } from '../../../types'
import { statusClass, statusLabel } from './shared'

function difficultyLabel(value?: string | null) {
  if (value === 'easy') return 'Dễ'
  if (value === 'medium') return 'Trung bình'
  if (value === 'hard') return 'Khó'
  return value || '—'
}

export function BankQuestionEnterpriseTable({
  rows,
  density,
  page,
  pageSize,
  total,
  totalPages,
  selectedKeys,
  loading,
  error,
  locked,
  canReview,
  onDensityChange,
  onPageChange,
  onPageSizeChange,
  onToggle,
  onTogglePage,
  onPreview,
  onEdit,
  onApprove,
  onReject,
  onBackToReview,
  onRetry,
}: {
  rows: BankVersionQuestion[]
  density: TableDensity
  page: number
  pageSize: number
  total: number
  totalPages: number
  selectedKeys: Set<string>
  loading?: boolean
  error?: string
  locked?: boolean
  canReview?: boolean
  onDensityChange: (density: TableDensity) => void
  onPageChange: (page: number) => void
  onPageSizeChange: (pageSize: number) => void
  onToggle: (row: BankVersionQuestion) => void
  onTogglePage: (rows: BankVersionQuestion[], selected: boolean) => void
  onPreview: (row: BankVersionQuestion) => void
  onEdit: (row: BankVersionQuestion) => void
  onApprove: (row: BankVersionQuestion) => void
  onReject: (row: BankVersionQuestion) => void
  onBackToReview: (row: BankVersionQuestion) => void
  onRetry?: () => void
}) {
  const columns = useMemo<EnterpriseTableColumn<BankVersionQuestion>[]>(() => [
    { key: 'stt', header: 'STT', width: 64, minWidth: 64, sticky: 'left', stickyOffset: 44, hideable: false, className: 'stt-cell', render: (_row, index) => (page - 1) * pageSize + index + 1 },
    { key: 'question', header: 'Câu hỏi', minWidth: 380, sticky: 'left', stickyOffset: 108, hideable: false, render: (row) => <button className="bank-question-link-button" type="button" onClick={() => onPreview(row)}><b>{row.question_text || 'Câu hỏi chưa có nội dung'}</b><small>{row.question_family_id ? `Family: ${row.question_family_id}` : row.concept_title || 'Chưa gắn concept'}</small></button> },
    { key: 'status', header: 'Trạng thái', minWidth: 145, hideable: true, render: (row) => <span className={statusClass(row.status)}>{statusLabel(row.status)}</span> },
    { key: 'difficulty', header: 'Độ khó', minWidth: 120, hideable: true, render: (row) => difficultyLabel(row.difficulty) },
    { key: 'concept', header: 'Concept', minWidth: 180, hideable: true, render: (row) => row.concept_title || '—' },
    { key: 'answer', header: 'Đáp án', align: 'center', minWidth: 90, hideable: true, render: (row) => <b>{row.correct_answer || '—'}</b> },
    { key: 'quality', header: 'Chất lượng', align: 'right', minWidth: 110, hideable: true, render: (row) => `${Math.round(Number(row.quality_score || 0) * 100)}%` },
    { key: 'source', header: 'Nguồn', minWidth: 150, hideable: true, defaultVisible: false, render: (row) => row.source_type || (row.is_carry_over ? 'Clone kỳ trước' : 'AI/Bank') },
    { key: 'actions', header: 'Thao tác', minWidth: 260, sticky: 'right', stickyOffset: 0, hideable: false, render: (row) => <div className="enterprise-row-actions">
      <button className="btn small secondary" onClick={() => onPreview(row)}>Xem trước</button>
      {!locked && canReview && row.status !== 'published' && <button className="btn small secondary" onClick={() => onEdit(row)}>Sửa</button>}
      {!locked && canReview && ['pending_review', 'needs_review', 'rejected'].includes(row.status) && <button className="btn small success" onClick={() => onApprove(row)}>{row.status === 'rejected' ? 'Duyệt lại' : 'Duyệt'}</button>}
      {!locked && canReview && !['rejected', 'published'].includes(row.status) && <button className="btn small danger" onClick={() => onReject(row)}>{row.status === 'draft_error' ? 'Bỏ câu lỗi' : 'Bỏ'}</button>}
      {!locked && canReview && row.status === 'approved' && <button className="btn small secondary" onClick={() => onBackToReview(row)}>Hoàn tác</button>}
    </div> },
  ], [canReview, locked, onApprove, onBackToReview, onEdit, onPreview, onReject, page, pageSize])

  return <EnterpriseDataTable
    tableId="bank-chapter-questions"
    caption="Danh sách câu hỏi"
    rows={rows}
    columns={columns}
    rowKey={(row) => row.id}
    density={density}
    onDensityChange={onDensityChange}
    selection={{ selectedKeys, onToggle, onTogglePage, isSelectable: (row) => row.status !== 'published' && !locked }}
    loading={loading}
    error={error}
    onRetry={onRetry}
    page={page}
    pageSize={pageSize}
    total={total}
    totalPages={Math.max(1, totalPages)}
    onPageChange={onPageChange}
    onPageSizeChange={onPageSizeChange}
    label="câu hỏi"
    emptyTitle="Không có câu hỏi phù hợp"
    emptyDescription="Xóa bộ lọc, import câu hỏi hoặc sinh câu hỏi từ tài liệu để tiếp tục."
  />
}
