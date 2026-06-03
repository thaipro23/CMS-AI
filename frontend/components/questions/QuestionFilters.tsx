'use client'

import { QuestionFilters } from '../../types'

export const DEFAULT_FILTERS: QuestionFilters = {
  status: 'all',
  difficulty: 'all',
  nodeId: 'all',
  sourceType: 'all',
  search: '',
  sortBy: 'created_at',
  sortDir: 'desc',
}

export function sameFilters(left: QuestionFilters, right: QuestionFilters) {
  return JSON.stringify(left) === JSON.stringify(right)
}

export function QuestionFiltersBar({
  filters,
  onChange,
  onReset,
  loading = false,
}: {
  filters: QuestionFilters
  onChange: (filters: QuestionFilters) => void
  onReset: () => void
  loading?: boolean
}) {
  const update = <K extends keyof QuestionFilters>(key: K, value: QuestionFilters[K]) => onChange({ ...filters, [key]: value })
  return <section className="card">
    <div className="section-head">
      <div>
        <h2>Lọc / Tìm kiếm / Sắp xếp</h2>
        <p className="helper">Chọn filter là hệ thống tự tải lại. Selection đang tick vẫn được giữ theo ID, kể cả khi bị ẩn bởi filter.</p>
        {loading && <span className="soft-tag"><span className="spinner tiny" /> Đang tải theo filter...</span>}
      </div>
      <div className="button-row compact">
        <button className="btn secondary" onClick={onReset} disabled={loading}>Đặt lại bộ lọc</button>
      </div>
    </div>
    <div className="grid grid-3">
      <div><label>Trạng thái</label><select className="input" value={filters.status} onChange={(event) => update('status', event.target.value)}><option value="all">Tất cả</option><option value="pending_review">Chờ duyệt</option><option value="approved">Đã duyệt</option><option value="rejected">Đã từ chối</option><option value="published">Đã publish</option><option value="draft_error">Cần sửa</option></select></div>
      <div><label>Độ khó</label><select className="input" value={filters.difficulty} onChange={(event) => update('difficulty', event.target.value)}><option value="all">Tất cả</option><option value="easy">Easy</option><option value="medium">Medium</option><option value="hard">Hard</option></select></div>
      <div><label>ID node nguồn</label><input className="input" value={filters.nodeId === 'all' ? '' : (filters.nodeId || '')} onChange={(event) => update('nodeId', event.target.value || 'all')} placeholder="Để trống = tất cả" /></div>
      <div><label>Loại nguồn</label><select className="input" value={filters.sourceType || 'all'} onChange={(event) => update('sourceType', event.target.value)}><option value="all">Tất cả</option><option value="html">HTML</option><option value="transcript">Transcript</option><option value="problem">Problem/Quiz</option><option value="file">File</option></select></div>
      <div><label>Tìm kiếm</label><input className="input" value={filters.search} onChange={(event) => update('search', event.target.value)} placeholder="Tự load sau khi nhập..." /></div>
      <div><label>Sắp xếp theo</label><select className="input" value={filters.sortBy} onChange={(event) => update('sortBy', event.target.value)}><option value="created_at">Ngày tạo</option><option value="updated_at">Ngày sửa</option><option value="difficulty">Độ khó</option><option value="status">Trạng thái</option><option value="quality_score">Điểm chất lượng</option><option value="version">Phiên bản</option><option value="source_node_id">Node nguồn</option><option value="chapter_title">Chương/Module</option><option value="target_library_key">Thư viện</option></select></div>
      <div><label>Chiều sắp xếp</label><select className="input" value={filters.sortDir} onChange={(event) => update('sortDir', event.target.value)}><option value="desc">Mới nhất trước</option><option value="asc">Cũ nhất trước</option></select></div>
    </div>
  </section>
}
