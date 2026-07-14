'use client'

import { useEffect, useMemo, useRef, useState } from 'react'
import type { CSSProperties, ReactNode } from 'react'
import { PaginationControls } from '../ui/PaginationControls'
import { TableEmptyState, TableErrorState, TableLoadingState } from './TableStates'
import type { TableDensity } from '../../hooks/useUrlTableState'

export type EnterpriseColumnKind = 'index' | 'selection' | 'identity' | 'number' | 'status' | 'date' | 'progress' | 'actions' | 'text'
export type EnterpriseColumnPriority = 'required' | 'important' | 'optional'

export type EnterpriseTableColumn<Row> = {
  key: string
  header: string
  render: (row: Row, rowIndex: number) => ReactNode
  width?: number | string
  minWidth?: number
  align?: 'left' | 'center' | 'right'
  sticky?: 'left' | 'right'
  /** @deprecated Sticky offsets are calculated from rendered columns. */
  stickyOffset?: number
  hideable?: boolean
  defaultVisible?: boolean
  sortable?: boolean
  className?: string
  kind?: EnterpriseColumnKind
  priority?: EnterpriseColumnPriority
  truncateLines?: 1 | 2 | 3
}

export type EnterpriseTableSelection<Row> = {
  selectedKeys: Set<string>
  onToggle: (row: Row) => void
  onTogglePage: (rows: Row[], selected: boolean) => void
  isSelectable?: (row: Row) => boolean
}

export type EnterpriseDataTableProps<Row> = {
  tableId: string
  caption: string
  rows: Row[]
  columns: EnterpriseTableColumn<Row>[]
  rowKey: (row: Row) => string
  density?: TableDensity
  onDensityChange?: (density: TableDensity) => void
  selection?: EnterpriseTableSelection<Row>
  loading?: boolean
  error?: string
  onRetry?: () => void
  emptyTitle?: string
  emptyDescription?: string
  emptyAction?: ReactNode
  page?: number
  pageSize?: number
  total?: number
  totalPages?: number
  onPageChange?: (page: number) => void
  onPageSizeChange?: (pageSize: number) => void
  label?: string
  getRowClassName?: (row: Row) => string
}

type ColumnLayout<Row> = {
  column: EnterpriseTableColumn<Row>
  size: number
  stickyOffset: number
  kind: EnterpriseColumnKind
  priority: EnterpriseColumnPriority
}

const SELECTION_COLUMN_WIDTH = 44
const INDEX_COLUMN_KEYS = new Set(['stt', 'index', 'row_number', 'rowNumber'])
const NUMBER_WORDS = ['số', 'tổng', 'đã duyệt', 'chưa duyệt', 'bài', 'môn', 'lớp', 'sinh viên', 'câu', 'lượt', 'blocker', 'cảnh báo']
const DATE_WORDS = ['ngày', 'thời điểm', 'bắt đầu', 'kết thúc', 'cập nhật']

function inferKind(key: string, header: string): EnterpriseColumnKind {
  const normalizedKey = key.toLowerCase()
  const normalizedHeader = header.trim().toLowerCase()
  if (INDEX_COLUMN_KEYS.has(key) || normalizedHeader === 'stt') return 'index'
  if (normalizedKey.includes('action') || normalizedHeader === 'thao tác') return 'actions'
  if (normalizedKey.includes('status') || normalizedHeader === 'trạng thái' || normalizedHeader === 'kết quả') return 'status'
  if (normalizedKey.includes('progress') || normalizedHeader.includes('tiến độ')) return 'progress'
  if (DATE_WORDS.some((word) => normalizedHeader.includes(word))) return 'date'
  if (normalizedKey.includes('count') || normalizedKey.includes('total') || NUMBER_WORDS.some((word) => normalizedHeader === word || normalizedHeader.startsWith(`${word} `))) return 'number'
  if (['name', 'title', 'question', 'teacher', 'student', 'subject', 'class', 'job'].some((word) => normalizedKey.includes(word))) return 'identity'
  return 'text'
}

function defaultPriority(kind: EnterpriseColumnKind): EnterpriseColumnPriority {
  if (kind === 'index' || kind === 'identity' || kind === 'actions') return 'required'
  if (kind === 'status' || kind === 'number' || kind === 'progress') return 'important'
  return 'optional'
}

function defaultWidth(kind: EnterpriseColumnKind) {
  switch (kind) {
    case 'index': return 52
    case 'number': return 76
    case 'status': return 118
    case 'date': return 128
    case 'progress': return 150
    case 'actions': return 112
    case 'identity': return 240
    default: return 160
  }
}

function numericWidth(width: number | string | undefined, minWidth: number | undefined, kind: EnterpriseColumnKind) {
  const fallback = defaultWidth(kind)
  if (typeof width === 'number' && Number.isFinite(width)) return Math.max(width, minWidth || 0)
  if (typeof width === 'string') {
    const match = width.trim().match(/^(\d+(?:\.\d+)?)px$/i)
    if (match) return Math.max(Number(match[1]), minWidth || 0)
  }
  return Math.max(minWidth || 0, fallback)
}

function isCompactKind(kind: EnterpriseColumnKind) {
  return kind === 'index' || kind === 'number' || kind === 'actions'
}

function cellClass<Row>(layout: ColumnLayout<Row>) {
  return [
    layout.column.className || '',
    `enterprise-kind-${layout.kind}`,
    `enterprise-priority-${layout.priority}`,
    layout.column.sticky ? `sticky-${layout.column.sticky}` : '',
  ].filter(Boolean).join(' ')
}

export function EnterpriseDataTable<Row>({
  tableId,
  caption,
  rows,
  columns,
  rowKey,
  density = 'compact',
  onDensityChange,
  selection,
  loading = false,
  error,
  onRetry,
  emptyTitle = 'Chưa có dữ liệu',
  emptyDescription,
  emptyAction,
  page,
  pageSize,
  total,
  totalPages,
  onPageChange,
  onPageSizeChange,
  label = 'bản ghi',
  getRowClassName,
}: EnterpriseDataTableProps<Row>) {
  // v2 deliberately resets the old responsive preferences that automatically hid columns.
  const storageKey = `ai-enterprise-table:${tableId}:columns:full-v2`
  const shellRef = useRef<HTMLElement | null>(null)
  const headerCheckboxRef = useRef<HTMLInputElement | null>(null)
  const defaultKeys = useMemo(() => columns.map((column) => column.key), [columns])
  const [visibleKeys, setVisibleKeys] = useState<string[]>(defaultKeys)

  useEffect(() => {
    try {
      const saved = window.localStorage.getItem(storageKey)
      if (!saved) return
      const parsed = JSON.parse(saved)
      if (Array.isArray(parsed)) {
        const allowed = new Set(columns.map((column) => column.key))
        const next = parsed.filter((key): key is string => typeof key === 'string' && allowed.has(key))
        if (next.length) setVisibleKeys(next)
      }
    } catch {
      // Invalid local preferences must never block the table.
    }
  }, [columns, storageKey])

  useEffect(() => {
    const allowed = new Set(columns.map((column) => column.key))
    setVisibleKeys((current) => {
      const retained = current.filter((key) => allowed.has(key))
      const added = defaultKeys.filter((key) => !retained.includes(key))
      const next = retained.length ? [...retained, ...added] : defaultKeys
      return next.length === current.length && next.every((key, index) => key === current[index]) ? current : next
    })
  }, [columns, defaultKeys])

  const visibleColumns = useMemo(() => columns.filter((column) => visibleKeys.includes(column.key)), [columns, visibleKeys])
  const columnLayouts = useMemo<ColumnLayout<Row>[]>(() => {
    const layouts = visibleColumns.map((column) => {
      const kind = column.kind || inferKind(column.key, column.header)
      const priority = column.priority || defaultPriority(kind)
      return { column, size: numericWidth(column.width, column.minWidth, kind), stickyOffset: 0, kind, priority }
    })
    let leftOffset = selection ? SELECTION_COLUMN_WIDTH : 0
    layouts.forEach((layout) => {
      if (layout.column.sticky !== 'left') return
      layout.stickyOffset = leftOffset
      // Sticky columns need a stable width. Non-sticky content remains content-driven.
      leftOffset += layout.size
    })
    let rightOffset = 0
    ;[...layouts].reverse().forEach((layout) => {
      if (layout.column.sticky !== 'right') return
      layout.stickyOffset = rightOffset
      rightOffset += layout.size
    })
    return layouts
  }, [selection, visibleColumns])

  const selectableRows = selection ? rows.filter((row) => selection.isSelectable?.(row) !== false) : []
  const selectedOnPage = selection ? selectableRows.filter((row) => selection.selectedKeys.has(rowKey(row))).length : 0
  const allPageSelected = Boolean(selection && selectableRows.length && selectedOnPage === selectableRows.length)
  const somePageSelected = Boolean(selection && selectedOnPage > 0 && !allPageSelected)

  useEffect(() => {
    if (headerCheckboxRef.current) headerCheckboxRef.current.indeterminate = somePageSelected
  }, [somePageSelected])

  const persistColumns = (keys: string[]) => {
    setVisibleKeys(keys)
    try { window.localStorage.setItem(storageKey, JSON.stringify(keys)) } catch { /* storage may be unavailable */ }
  }
  const toggleColumn = (key: string) => {
    const column = columns.find((item) => item.key === key)
    if (!column?.hideable) return
    const next = visibleKeys.includes(key)
      ? visibleKeys.filter((item) => item !== key)
      : columns.map((item) => item.key).filter((item) => item === key || visibleKeys.includes(item))
    if (next.length) persistColumns(next)
  }
  const hasPagination = page !== undefined && pageSize !== undefined && total !== undefined && totalPages !== undefined && onPageChange && onPageSizeChange

  if (loading && !rows.length) return <TableLoadingState />
  if (error && !rows.length) return <TableErrorState message={error} onRetry={onRetry} />

  const cellStyle = (layout: ColumnLayout<Row>): CSSProperties => {
    const compact = isCompactKind(layout.kind)
    const stickyIdentity = layout.column.sticky && layout.kind === 'identity'
    const stableWidth = compact || stickyIdentity
    return {
      width: stableWidth ? `${layout.size}px` : undefined,
      minWidth: compact ? `${layout.size}px` : stickyIdentity ? `${Math.min(layout.size, 260)}px` : undefined,
      maxWidth: compact ? `${layout.size}px` : stickyIdentity ? `${Math.min(layout.size, 320)}px` : undefined,
      textAlign: layout.kind === 'index' || layout.kind === 'number' ? 'center' : layout.column.align,
      boxSizing: 'border-box',
      '--sticky-offset': `${layout.stickyOffset}px`,
    } as CSSProperties
  }

  return <section ref={shellRef} className={`enterprise-table-shell density-${density}`} aria-busy={loading} data-column-contract="full-content">
    <div className="enterprise-table-controls">
      <div className="enterprise-table-summary" aria-live="polite"><b>{caption}</b><span>{(total ?? rows.length).toLocaleString('vi-VN')} {label}</span>{loading && <span className="soft-tag"><span className="spinner tiny" /> Đang cập nhật</span>}</div>
      <div className="enterprise-table-view-actions">
        {onDensityChange && <label className="enterprise-density-control"><span>Mật độ</span><select className="input" value={density} onChange={(event) => onDensityChange(event.target.value as TableDensity)}><option value="compact">Thu gọn</option><option value="standard">Tiêu chuẩn</option><option value="comfortable">Thoáng</option></select></label>}
        <details className="enterprise-column-menu"><summary className="btn small secondary">Cột hiển thị</summary><div className="enterprise-column-menu-popover"><b>Chọn cột</b>{columns.map((column) => <label key={column.key}><input type="checkbox" checked={visibleKeys.includes(column.key)} disabled={!column.hideable} onChange={() => toggleColumn(column.key)} />{column.header}</label>)}<button className="btn small secondary" type="button" onClick={() => persistColumns(defaultKeys)}>Hiện tất cả</button></div></details>
      </div>
    </div>
    {!rows.length ? <TableEmptyState title={emptyTitle} description={emptyDescription} action={emptyAction} /> : <div className="enterprise-table-scroll" tabIndex={0} role="region" aria-label={`${caption}. Bảng hiển thị đầy đủ các cột; chỉ cuộn ngang khi nội dung thực sự không thể xuống dòng.`}>
      <table className="enterprise-data-table">
        <caption className="sr-only">{caption}</caption>
        <colgroup>
          {selection && <col className="enterprise-select-column" style={{ width: `${SELECTION_COLUMN_WIDTH}px` }} />}
          {columnLayouts.map((layout) => <col key={layout.column.key} className={`enterprise-kind-${layout.kind} enterprise-priority-${layout.priority}`} style={isCompactKind(layout.kind) || (layout.column.sticky && layout.kind === 'identity') ? { width: `${layout.size}px` } : undefined} />)}
        </colgroup>
        <thead><tr>
          {selection && <th className="enterprise-select-column sticky-left" style={{ width: `${SELECTION_COLUMN_WIDTH}px`, minWidth: `${SELECTION_COLUMN_WIDTH}px`, '--sticky-offset': '0px' } as CSSProperties}><input ref={headerCheckboxRef} type="checkbox" aria-label="Chọn tất cả bản ghi trên trang" checked={allPageSelected} onChange={(event) => selection.onTogglePage(selectableRows, event.target.checked)} /></th>}
          {columnLayouts.map((layout) => <th key={layout.column.key} className={cellClass(layout)} style={cellStyle(layout)} scope="col">{layout.column.header}</th>)}
        </tr></thead>
        <tbody>{rows.map((row, rowIndex) => {
          const key = rowKey(row)
          return <tr className={getRowClassName?.(row) || ''} key={key}>
            {selection && <td className="enterprise-select-column sticky-left" style={{ width: `${SELECTION_COLUMN_WIDTH}px`, minWidth: `${SELECTION_COLUMN_WIDTH}px`, '--sticky-offset': '0px' } as CSSProperties}><input type="checkbox" aria-label={`Chọn dòng ${rowIndex + 1}`} disabled={selection.isSelectable?.(row) === false} checked={selection.selectedKeys.has(key)} onChange={() => selection.onToggle(row)} /></td>}
            {columnLayouts.map((layout) => <td key={layout.column.key} className={cellClass(layout)} style={cellStyle(layout)}>{layout.column.render(row, rowIndex)}</td>)}
          </tr>
        })}</tbody>
      </table>
    </div>}
    {hasPagination && <PaginationControls page={page} pageSize={pageSize} total={total} totalPages={totalPages} onPageChange={onPageChange} onPageSizeChange={onPageSizeChange} loading={loading} label={label} />}
  </section>
}
