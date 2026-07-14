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

  return <nav className="pagination-bar" aria-label="Phân trang dữ liệu">
    <div className="pagination-summary" aria-live="polite">
      <b>{from.toLocaleString('vi-VN')}–{to.toLocaleString('vi-VN')}</b>
      <span>/ {total.toLocaleString('vi-VN')} {label}</span>
      {loading && <span className="soft-tag"><span className="spinner tiny" /> Đang tải trang...</span>}
    </div>
    <div className="pagination-actions">
      <button type="button" className="btn small secondary" aria-label="Về trang đầu" disabled={loading || currentPage <= 1} onClick={() => onPageChange(1)}>Đầu</button>
      <button type="button" className="btn small secondary" aria-label="Về trang trước" disabled={loading || currentPage <= 1} onClick={() => onPageChange(currentPage - 1)}>Trước</button>
      <div className="page-number-list" aria-label={`Trang ${currentPage} trên ${safeTotalPages}`}>
        {pageWindow.map((item, index) => <button
          type="button"
          key={item}
          className={item === currentPage ? 'page-number active' : 'page-number'}
          disabled={loading}
          aria-current={item === currentPage ? 'page' : undefined}
          aria-label={`Trang ${item}`}
          onClick={() => onPageChange(item)}
        >{index > 0 && item - pageWindow[index - 1] > 1 ? '… ' : ''}{item}</button>)}
      </div>
      <button type="button" className="btn small secondary" aria-label="Sang trang sau" disabled={loading || currentPage >= safeTotalPages} onClick={() => onPageChange(currentPage + 1)}>Sau</button>
      <button type="button" className="btn small secondary" aria-label="Đến trang cuối" disabled={loading || currentPage >= safeTotalPages} onClick={() => onPageChange(safeTotalPages)}>Cuối</button>
      <label className="page-size-control"><span className="sr-only">Số bản ghi mỗi trang</span><select className="input page-size-select" aria-label="Số bản ghi mỗi trang" value={pageSize} disabled={loading} onChange={(event) => onPageSizeChange(Number(event.target.value))}>
        <option value={10}>10/trang</option>
        <option value={20}>20/trang</option>
        <option value={50}>50/trang</option>
        <option value={100}>100/trang</option>
      </select></label>
    </div>
  </nav>
}
