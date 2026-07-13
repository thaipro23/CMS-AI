'use client'

import { useEffect, useMemo, useState } from 'react'
import type { CSSProperties, ReactNode } from 'react'
import { PaginationControls } from '../ui/PaginationControls'
import { TableEmptyState, TableErrorState, TableLoadingState } from './TableStates'
import type { TableDensity } from '../../hooks/useUrlTableState'

export type EnterpriseTableColumn<Row> = {
  key: string
  header: string
  render: (row: Row, rowIndex: number) => ReactNode
  width?: number | string
  minWidth?: number
  align?: 'left' | 'center' | 'right'
  sticky?: 'left' | 'right'
  /** @deprecated Sticky offsets are calculated from visible column widths. */
  stickyOffset?: number
  hideable?: boolean
  defaultVisible?: boolean
  sortable?: boolean
  className?: string
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
  indexColumn: boolean
}

const SELECTION_COLUMN_WIDTH = 52
const DEFAULT_COLUMN_WIDTH = 160
const INDEX_COLUMN_KEYS = new Set(['stt', 'index', 'row_number', 'rowNumber'])

function numericWidth(width: number | string | undefined, minWidth?: number, indexColumn = false) {
  if (indexColumn) return 64
  if (typeof width === 'number' && Number.isFinite(width)) return Math.max(width, minWidth || 0)
  if (typeof width === 'string') {
    const match = width.trim().match(/^(\d+(?:\.\d+)?)px$/i)
    if (match) return Math.max(Number(match[1]), minWidth || 0)
  }
  return Math.max(minWidth || 0, DEFAULT_COLUMN_WIDTH)
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
  const storageKey = `ai-enterprise-table:${tableId}:columns`
  const defaultKeys = useMemo(() => columns.filter((column) => column.defaultVisible !== false).map((column) => column.key), [columns])
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
      // Ignore invalid local preferences; table defaults remain usable.
    }
  }, [columns, storageKey])

  const visibleColumns = useMemo(() => columns.filter((column) => visibleKeys.includes(column.key)), [columns, visibleKeys])
  const columnLayouts = useMemo<ColumnLayout<Row>[]>(() => {
    const layouts = visibleColumns.map((column) => {
      const indexColumn = INDEX_COLUMN_KEYS.has(column.key) || column.header.trim().toUpperCase() === 'STT'
      return { column, size: numericWidth(column.width, column.minWidth, indexColumn), stickyOffset: 0, indexColumn }
    })
    let leftOffset = selection ? SELECTION_COLUMN_WIDTH : 0
    layouts.forEach((layout) => {
      if (layout.column.sticky !== 'left') return
      layout.stickyOffset = leftOffset
      leftOffset += layout.size
    })
    let rightOffset = 0
    ;[...layouts].reverse().forEach((layout) => {
      if (layout.column.sticky !== 'right') return
      layout.stickyOffset = rightOffset
      rightOffset += layout.size
    })
    return layouts
  }, [visibleColumns, selection])

  const selectableRows = selection ? rows.filter((row) => selection.isSelectable?.(row) !== false) : []
  const allPageSelected = Boolean(selection && selectableRows.length && selectableRows.every((row) => selection.selectedKeys.has(rowKey(row))))
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

  const cellStyle = (layout: ColumnLayout<Row>): CSSProperties => ({
    width: layout.column.width || `${layout.size}px`,
    minWidth: `${layout.size}px`,
    maxWidth: layout.column.sticky ? `${layout.size}px` : undefined,
    textAlign: layout.indexColumn ? 'center' : layout.column.align,
    boxSizing: 'border-box',
    '--sticky-offset': `${layout.stickyOffset}px`,
  } as CSSProperties)

  return <section className={`enterprise-table-shell density-${density}`} aria-busy={loading}>
    <div className="enterprise-table-controls">
      <div className="enterprise-table-summary"><b>{caption}</b><span>{(total ?? rows.length).toLocaleString('vi-VN')} {label}</span>{loading && <span className="soft-tag"><span className="spinner tiny" /> Đang cập nhật</span>}</div>
      <div className="enterprise-table-view-actions">
        {onDensityChange && <label className="enterprise-density-control"><span>Mật độ</span><select className="input" value={density} onChange={(event) => onDensityChange(event.target.value as TableDensity)}><option value="compact">Thu gọn</option><option value="standard">Tiêu chuẩn</option><option value="comfortable">Thoáng</option></select></label>}
        <details className="enterprise-column-menu"><summary className="btn small secondary">Cột hiển thị</summary><div className="enterprise-column-menu-popover"><b>Chọn cột</b>{columns.map((column) => <label key={column.key}><input type="checkbox" checked={visibleKeys.includes(column.key)} disabled={!column.hideable} onChange={() => toggleColumn(column.key)} />{column.header}</label>)}<button className="btn small secondary" type="button" onClick={() => persistColumns(defaultKeys)}>Mặc định</button></div></details>
      </div>
    </div>
    {!rows.length ? <TableEmptyState title={emptyTitle} description={emptyDescription} action={emptyAction} /> : <div className="enterprise-table-scroll" tabIndex={0} aria-label={`${caption}, có thể cuộn ngang`}>
      <table className="enterprise-data-table">
        <caption className="sr-only">{caption}</caption>
        <colgroup>
          {selection && <col style={{ width: `${SELECTION_COLUMN_WIDTH}px` }} />}
          {columnLayouts.map((layout) => <col key={layout.column.key} style={{ width: layout.column.width || `${layout.size}px`, minWidth: `${layout.size}px` }} />)}
        </colgroup>
        <thead><tr>
          {selection && <th className="enterprise-select-column sticky-left" style={{ width: `${SELECTION_COLUMN_WIDTH}px`, minWidth: `${SELECTION_COLUMN_WIDTH}px`, '--sticky-offset': '0px' } as CSSProperties}><input type="checkbox" aria-label="Chọn tất cả bản ghi trên trang" checked={allPageSelected} onChange={(event) => selection.onTogglePage(selectableRows, event.target.checked)} /></th>}
          {columnLayouts.map((layout) => <th key={layout.column.key} className={`${layout.column.className || ''} ${layout.indexColumn ? 'enterprise-index-column' : ''} ${layout.column.sticky ? `sticky-${layout.column.sticky}` : ''}`} style={cellStyle(layout)}>{layout.column.header}</th>)}
        </tr></thead>
        <tbody>{rows.map((row, rowIndex) => <tr key={rowKey(row)} className={getRowClassName?.(row) || ''}>
          {selection && <td className="enterprise-select-column sticky-left" style={{ width: `${SELECTION_COLUMN_WIDTH}px`, minWidth: `${SELECTION_COLUMN_WIDTH}px`, '--sticky-offset': '0px' } as CSSProperties}><input type="checkbox" aria-label={`Chọn dòng ${rowIndex + 1}`} disabled={selection.isSelectable?.(row) === false} checked={selection.selectedKeys.has(rowKey(row))} onChange={() => selection.onToggle(row)} /></td>}
          {columnLayouts.map((layout) => <td key={layout.column.key} className={`${layout.column.className || ''} ${layout.indexColumn ? 'enterprise-index-column' : ''} ${layout.column.sticky ? `sticky-${layout.column.sticky}` : ''}`} style={cellStyle(layout)}>{layout.column.render(row, rowIndex)}</td>)}
        </tr>)}</tbody>
      </table>
    </div>}
    {hasPagination && <PaginationControls page={page} pageSize={pageSize} total={total} totalPages={totalPages} onPageChange={onPageChange} onPageSizeChange={onPageSizeChange} loading={loading} label={label} />}
  </section>
}
