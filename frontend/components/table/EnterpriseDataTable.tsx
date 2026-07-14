'use client'

import { Fragment, useEffect, useMemo, useRef, useState } from 'react'
import type { CSSProperties, ReactNode } from 'react'
import { PaginationControls } from '../ui/PaginationControls'
import { TableEmptyState, TableErrorState, TableLoadingState } from './TableStates'
import type { TableDensity } from '../../hooks/useUrlTableState'

export type EnterpriseColumnKind = 'index' | 'selection' | 'identity' | 'number' | 'status' | 'date' | 'progress' | 'actions' | 'text'
export type EnterpriseColumnPriority = 'required' | 'important' | 'optional'

type ResponsiveTableMode = 'desktop' | 'tablet' | 'mobile'

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
const RESPONSIVE_DETAILS_WIDTH = 44
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
    case 'number': return 82
    case 'status': return 126
    case 'date': return 138
    case 'progress': return 150
    case 'actions': return 132
    case 'identity': return 250
    default: return 170
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

function responsiveWidth(kind: EnterpriseColumnKind, size: number, mode: ResponsiveTableMode) {
  if (mode === 'desktop') return size
  if (mode === 'tablet') {
    if (kind === 'identity') return Math.min(size, 220)
    if (kind === 'actions') return Math.min(size, 112)
    return size
  }
  if (kind === 'index') return 44
  if (kind === 'identity') return Math.min(size, 190)
  if (kind === 'actions') return Math.min(size, 96)
  if (kind === 'number') return Math.min(size, 70)
  if (kind === 'status') return Math.min(size, 108)
  return Math.min(size, 150)
}

function cellClass<Row>(layout: ColumnLayout<Row>) {
  return [
    layout.column.className || '',
    `enterprise-kind-${layout.kind}`,
    `enterprise-priority-${layout.priority}`,
    layout.column.sticky ? `sticky-${layout.column.sticky}` : '',
    layout.column.truncateLines ? `enterprise-clamp-${layout.column.truncateLines}` : '',
  ].filter(Boolean).join(' ')
}

function modeForWidth(width: number): ResponsiveTableMode {
  if (width <= 720) return 'mobile'
  if (width <= 1080) return 'tablet'
  return 'desktop'
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
  const shellRef = useRef<HTMLElement | null>(null)
  const headerCheckboxRef = useRef<HTMLInputElement | null>(null)
  const [responsiveMode, setResponsiveMode] = useState<ResponsiveTableMode>('desktop')
  const [expandedRows, setExpandedRows] = useState<Set<string>>(new Set())
  const defaultKeys = useMemo(() => columns.filter((column) => column.defaultVisible !== false).map((column) => column.key), [columns])
  const [visibleKeys, setVisibleKeys] = useState<string[]>(defaultKeys)

  useEffect(() => {
    const shell = shellRef.current
    if (!shell) return undefined
    const update = () => setResponsiveMode(modeForWidth(shell.getBoundingClientRect().width))
    update()
    if (typeof ResizeObserver !== 'undefined') {
      const observer = new ResizeObserver(update)
      observer.observe(shell)
      return () => observer.disconnect()
    }
    window.addEventListener('resize', update)
    return () => window.removeEventListener('resize', update)
  }, [])

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
      const requiredDefaults = defaultKeys.filter((key) => !retained.includes(key))
      const next = retained.length ? [...retained, ...requiredDefaults] : defaultKeys
      return next.length === current.length && next.every((key, index) => key === current[index]) ? current : next
    })
  }, [columns, defaultKeys])

  const userVisibleColumns = useMemo(() => columns.filter((column) => visibleKeys.includes(column.key)), [columns, visibleKeys])
  const priorityFor = (column: EnterpriseTableColumn<Row>) => column.priority || defaultPriority(column.kind || inferKind(column.key, column.header))
  const visibleColumns = useMemo(() => userVisibleColumns.filter((column) => {
    const priority = priorityFor(column)
    if (responsiveMode === 'mobile') return priority === 'required'
    if (responsiveMode === 'tablet') return priority !== 'optional'
    return true
  }), [responsiveMode, userVisibleColumns])
  const responsiveHiddenColumns = useMemo(() => userVisibleColumns.filter((column) => !visibleColumns.includes(column)), [userVisibleColumns, visibleColumns])
  const hasResponsiveDetails = responsiveHiddenColumns.length > 0

  const columnLayouts = useMemo<ColumnLayout<Row>[]>(() => {
    const layouts = visibleColumns.map((column) => {
      const kind = column.kind || inferKind(column.key, column.header)
      const priority = column.priority || defaultPriority(kind)
      const baseSize = numericWidth(column.width, column.minWidth, kind)
      return { column, size: responsiveWidth(kind, baseSize, responsiveMode), stickyOffset: 0, kind, priority }
    })
    let leftOffset = selection ? SELECTION_COLUMN_WIDTH : 0
    layouts.forEach((layout) => {
      if (layout.column.sticky !== 'left') return
      layout.stickyOffset = leftOffset
      leftOffset += layout.size
    })
    let rightOffset = hasResponsiveDetails ? RESPONSIVE_DETAILS_WIDTH : 0
    ;[...layouts].reverse().forEach((layout) => {
      if (layout.column.sticky !== 'right') return
      layout.stickyOffset = rightOffset
      rightOffset += layout.size
    })
    return layouts
  }, [hasResponsiveDetails, responsiveMode, selection, visibleColumns])

  const baseTableWidth = useMemo(() => {
    const totalWidth = columnLayouts.reduce((sum, layout) => sum + layout.size, selection ? SELECTION_COLUMN_WIDTH : 0) + (hasResponsiveDetails ? RESPONSIVE_DETAILS_WIDTH : 0)
    const minimum = responsiveMode === 'mobile' ? 320 : responsiveMode === 'tablet' ? 520 : 620
    return Math.max(minimum, totalWidth)
  }, [columnLayouts, hasResponsiveDetails, responsiveMode, selection])

  const selectableRows = selection ? rows.filter((row) => selection.isSelectable?.(row) !== false) : []
  const selectedOnPage = selection ? selectableRows.filter((row) => selection.selectedKeys.has(rowKey(row))).length : 0
  const allPageSelected = Boolean(selection && selectableRows.length && selectedOnPage === selectableRows.length)
  const somePageSelected = Boolean(selection && selectedOnPage > 0 && !allPageSelected)

  useEffect(() => {
    if (headerCheckboxRef.current) headerCheckboxRef.current.indeterminate = somePageSelected
  }, [somePageSelected])

  useEffect(() => {
    const valid = new Set(rows.map(rowKey))
    setExpandedRows((current) => {
      const next = new Set(Array.from(current).filter((key) => valid.has(key)))
      const unchanged = next.size === current.size && Array.from(next).every((key) => current.has(key))
      return unchanged ? current : next
    })
  }, [rowKey, rows])

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
  const toggleResponsiveDetails = (key: string) => setExpandedRows((current) => {
    const next = new Set(current)
    if (next.has(key)) next.delete(key)
    else next.add(key)
    return next
  })
  const hasPagination = page !== undefined && pageSize !== undefined && total !== undefined && totalPages !== undefined && onPageChange && onPageSizeChange

  if (loading && !rows.length) return <TableLoadingState />
  if (error && !rows.length) return <TableErrorState message={error} onRetry={onRetry} />

  const cellStyle = (layout: ColumnLayout<Row>): CSSProperties => ({
    width: responsiveMode === 'desktop' ? layout.column.width || `${layout.size}px` : `${layout.size}px`,
    minWidth: `${layout.size}px`,
    maxWidth: layout.kind === 'identity' || layout.kind === 'text' ? undefined : `${layout.size}px`,
    textAlign: layout.kind === 'index' || layout.kind === 'number' ? 'center' : layout.column.align,
    boxSizing: 'border-box',
    '--sticky-offset': `${layout.stickyOffset}px`,
  } as CSSProperties)

  const columnCount = columnLayouts.length + (selection ? 1 : 0) + (hasResponsiveDetails ? 1 : 0)

  return <section ref={shellRef} className={`enterprise-table-shell density-${density}`} aria-busy={loading} data-responsive-mode={responsiveMode}>
    <div className="enterprise-table-controls">
      <div className="enterprise-table-summary" aria-live="polite"><b>{caption}</b><span>{(total ?? rows.length).toLocaleString('vi-VN')} {label}</span>{loading && <span className="soft-tag"><span className="spinner tiny" /> Đang cập nhật</span>}</div>
      <div className="enterprise-table-view-actions">
        {hasResponsiveDetails && <span className="enterprise-responsive-note">{responsiveHiddenColumns.length} cột phụ nằm trong Chi tiết</span>}
        {onDensityChange && <label className="enterprise-density-control"><span>Mật độ</span><select className="input" value={density} onChange={(event) => onDensityChange(event.target.value as TableDensity)}><option value="compact">Thu gọn</option><option value="standard">Tiêu chuẩn</option><option value="comfortable">Thoáng</option></select></label>}
        <details className="enterprise-column-menu"><summary className="btn small secondary">Cột hiển thị</summary><div className="enterprise-column-menu-popover"><b>Chọn cột</b>{columns.map((column) => <label key={column.key}><input type="checkbox" checked={visibleKeys.includes(column.key)} disabled={!column.hideable} onChange={() => toggleColumn(column.key)} />{column.header}</label>)}<button className="btn small secondary" type="button" onClick={() => persistColumns(defaultKeys)}>Mặc định</button></div></details>
      </div>
    </div>
    {!rows.length ? <TableEmptyState title={emptyTitle} description={emptyDescription} action={emptyAction} /> : <div className="enterprise-table-scroll" tabIndex={0} role="region" aria-label={`${caption}, có thể cuộn ngang; dùng phím mũi tên hoặc thao tác cuộn khi màn hình hẹp`}>
      <table className="enterprise-data-table" style={{ minWidth: `${baseTableWidth}px` }}>
        <caption className="sr-only">{caption}</caption>
        <colgroup>
          {selection && <col className="enterprise-select-column" style={{ width: `${SELECTION_COLUMN_WIDTH}px` }} />}
          {columnLayouts.map((layout) => <col key={layout.column.key} className={`enterprise-kind-${layout.kind} enterprise-priority-${layout.priority}`} style={{ width: responsiveMode === 'desktop' ? layout.column.width || `${layout.size}px` : `${layout.size}px`, minWidth: `${layout.size}px` }} />)}
          {hasResponsiveDetails && <col className="enterprise-responsive-details-column" style={{ width: `${RESPONSIVE_DETAILS_WIDTH}px` }} />}
        </colgroup>
        <thead><tr>
          {selection && <th className="enterprise-select-column sticky-left" style={{ width: `${SELECTION_COLUMN_WIDTH}px`, minWidth: `${SELECTION_COLUMN_WIDTH}px`, '--sticky-offset': '0px' } as CSSProperties}><input ref={headerCheckboxRef} type="checkbox" aria-label="Chọn tất cả bản ghi trên trang" checked={allPageSelected} onChange={(event) => selection.onTogglePage(selectableRows, event.target.checked)} /></th>}
          {columnLayouts.map((layout) => <th key={layout.column.key} className={cellClass(layout)} style={cellStyle(layout)} scope="col">{layout.column.header}</th>)}
          {hasResponsiveDetails && <th className="enterprise-responsive-details-column sticky-right" style={{ '--sticky-offset': '0px' } as CSSProperties} scope="col"><span className="sr-only">Chi tiết cột ẩn</span></th>}
        </tr></thead>
        <tbody>{rows.map((row, rowIndex) => {
          const key = rowKey(row)
          const detailsId = `${tableId}-responsive-details-${key.replace(/[^a-zA-Z0-9_-]/g, '-')}`
          const expanded = expandedRows.has(key)
          return <Fragment key={key}>
            <tr className={getRowClassName?.(row) || ''}>
              {selection && <td className="enterprise-select-column sticky-left" style={{ width: `${SELECTION_COLUMN_WIDTH}px`, minWidth: `${SELECTION_COLUMN_WIDTH}px`, '--sticky-offset': '0px' } as CSSProperties}><input type="checkbox" aria-label={`Chọn dòng ${rowIndex + 1}`} disabled={selection.isSelectable?.(row) === false} checked={selection.selectedKeys.has(key)} onChange={() => selection.onToggle(row)} /></td>}
              {columnLayouts.map((layout) => <td key={layout.column.key} className={cellClass(layout)} style={cellStyle(layout)}>{layout.column.render(row, rowIndex)}</td>)}
              {hasResponsiveDetails && <td className="enterprise-responsive-details-column sticky-right" style={{ '--sticky-offset': '0px' } as CSSProperties}><button type="button" className="enterprise-row-details-toggle" aria-expanded={expanded} aria-controls={detailsId} aria-label={`${expanded ? 'Ẩn' : 'Xem'} cột phụ của dòng ${rowIndex + 1}`} onClick={() => toggleResponsiveDetails(key)}>•••</button></td>}
            </tr>
            {hasResponsiveDetails && expanded && <tr className="enterprise-responsive-details-row" id={detailsId}><td colSpan={columnCount}><dl>{responsiveHiddenColumns.map((column) => <div key={column.key}><dt>{column.header}</dt><dd>{column.render(row, rowIndex)}</dd></div>)}</dl></td></tr>}
          </Fragment>
        })}</tbody>
      </table>
    </div>}
    {hasPagination && <PaginationControls page={page} pageSize={pageSize} total={total} totalPages={totalPages} onPageChange={onPageChange} onPageSizeChange={onPageSizeChange} loading={loading} label={label} />}
  </section>
}
