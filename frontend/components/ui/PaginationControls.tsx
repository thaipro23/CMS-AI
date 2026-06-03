'use client'

export type PaginationState = {
  page: number
  pageSize: number
  total: number
  totalPages: number
}

export function PaginationControls({
  page,
  pageSize,
  total,
  totalPages,
  onPageChange,
  onPageSizeChange,
  loading = false,
  label = 'items',
}: PaginationState & {
  onPageChange: (page: number) => void
  onPageSizeChange: (pageSize: number) => void
  loading?: boolean
  label?: string
}) {
  const safeTotalPages = Math.max(1, totalPages || 1)
  const currentPage = Math.min(Math.max(1, page), safeTotalPages)
  const from = total === 0 ? 0 : (currentPage - 1) * pageSize + 1
  const to = Math.min(total, currentPage * pageSize)
  const pageWindow = Array.from(new Set([
    1,
    currentPage - 1,
    currentPage,
    currentPage + 1,
    safeTotalPages,
  ].filter((item) => item >= 1 && item <= safeTotalPages)))

  return <div className="pagination-bar">
    <div className="pagination-summary">
      <b>{from.toLocaleString('vi-VN')}–{to.toLocaleString('vi-VN')}</b>
      <span>/ {total.toLocaleString('vi-VN')} {label}</span>
      {loading && <span className="soft-tag"><span className="spinner tiny" /> Đang tải trang...</span>}
    </div>
    <div className="pagination-actions">
      <button className="btn small secondary" disabled={loading || currentPage <= 1} onClick={() => onPageChange(1)}>Đầu</button>
      <button className="btn small secondary" disabled={loading || currentPage <= 1} onClick={() => onPageChange(currentPage - 1)}>Trước</button>
      <div className="page-number-list">
        {pageWindow.map((item, index) => <button
          key={item}
          className={item === currentPage ? 'page-number active' : 'page-number'}
          disabled={loading}
          onClick={() => onPageChange(item)}
        >{index > 0 && item - pageWindow[index - 1] > 1 ? '… ' : ''}{item}</button>)}
      </div>
      <button className="btn small secondary" disabled={loading || currentPage >= safeTotalPages} onClick={() => onPageChange(currentPage + 1)}>Sau</button>
      <button className="btn small secondary" disabled={loading || currentPage >= safeTotalPages} onClick={() => onPageChange(safeTotalPages)}>Cuối</button>
      <select className="input page-size-select" value={pageSize} disabled={loading} onChange={(event) => onPageSizeChange(Number(event.target.value))}>
        <option value={10}>10/trang</option>
        <option value={20}>20/trang</option>
        <option value={50}>50/trang</option>
        <option value={100}>100/trang</option>
      </select>
    </div>
  </div>
}
