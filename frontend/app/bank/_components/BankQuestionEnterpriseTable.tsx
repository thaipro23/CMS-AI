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

function reviewActionLabel(row: BankVersionQuestion) {
  if (row.status === 'approved') return 'Xem lại'
  if (row.status === 'rejected') return 'Duyệt lại'
  if (row.status === 'draft_error') return 'Xử lý lỗi'
  return 'Mở duyệt'
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
  activeQuestionId,
  onDensityChange,
  onPageChange,
  onPageSizeChange,
  onToggle,
  onTogglePage,
  onPreview,
  onEdit,
  onApprove: _onApprove,
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
  activeQuestionId?: string | null
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
    {
      key: 'stt', header: 'STT', kind: 'index', width: 52, sticky: 'left', hideable: false,
      render: (_row, index) => (page - 1) * pageSize + index + 1,
    },
    {
      key: 'question', header: 'Câu hỏi', kind: 'identity', minWidth: 390, priority: 'required', hideable: false, truncateLines: 2,
      render: (row) => <button className="bank-question-link-button" type="button" onClick={() => onPreview(row)} aria-label={`Mở duyệt câu hỏi: ${row.question_text || 'chưa có nội dung'}`}>
        <b>{row.question_text || 'Câu hỏi chưa có nội dung'}</b>
        <small>{row.question_family_id ? `Family: ${row.question_family_id}` : row.concept_title || 'Chưa gắn concept'}</small>
      </button>,
    },
    {
      key: 'status', header: 'Trạng thái', kind: 'status', width: 116, priority: 'important', hideable: true,
      render: (row) => <span className={statusClass(row.status)}>{statusLabel(row.status)}</span>,
    },
    {
      key: 'difficulty', header: 'Độ khó', kind: 'status', width: 90, priority: 'important', hideable: true,
      render: (row) => difficultyLabel(row.difficulty),
    },
    {
      key: 'quality', header: 'Chất lượng', kind: 'number', width: 88, priority: 'important', align: 'center', hideable: true,
      render: (row) => <span className={`quality-score ${Number(row.quality_score || 0) < .6 ? 'low' : ''}`}>{Math.round(Number(row.quality_score || 0) * 100)}%</span>,
    },
    {
      key: 'concept', header: 'Concept', kind: 'text', minWidth: 150, priority: 'optional', hideable: true, defaultVisible: false, truncateLines: 2,
      render: (row) => row.concept_title || '—',
    },
    {
      key: 'source', header: 'Nguồn', kind: 'text', minWidth: 130, priority: 'optional', hideable: true, defaultVisible: false,
      render: (row) => row.source_type || (row.is_carry_over ? 'Clone kỳ trước' : 'AI/Bank'),
    },
    {
      key: 'actions', header: 'Thao tác', kind: 'actions', width: 126, sticky: 'right', hideable: false,
      render: (row) => <div className="question-row-actions question-row-actions-review-first">
        <button className="btn small" type="button" onClick={() => onPreview(row)}>{reviewActionLabel(row)}</button>
      </div>,
    },
  ], [canReview, locked, onBackToReview, onEdit, onPreview, onReject, page, pageSize])

  return <EnterpriseDataTable
    tableId="bank-chapter-questions-v3"
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
    getRowClassName={(row) => row.id === activeQuestionId ? 'is-active-review-row' : ''}
    emptyTitle="Không có câu hỏi phù hợp"
    emptyDescription="Xóa bộ lọc, import câu hỏi hoặc sinh câu hỏi từ tài liệu để tiếp tục."
  />
}
