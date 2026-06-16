import { Suspense } from 'react'
import SearchPageClient from './SearchPageClient'

function BankSearchFallback() {
  return <div className="page-stack bank-multipage dashboard-search-page">
    <div className="dashboard-search-hero card">
      <div>
        <span className="eyebrow">Drill-down</span>
        <h1>Đang tải danh sách xử lý...</h1>
        <p>Hệ thống đang đọc bộ lọc và kiểm tra phạm vi quyền của bạn.</p>
      </div>
    </div>
    <div className="dashboard-search-list">
      <div className="dashboard-skeleton" style={{ minHeight: 96 }} />
      <div className="dashboard-skeleton" style={{ minHeight: 96 }} />
      <div className="dashboard-skeleton" style={{ minHeight: 96 }} />
    </div>
  </div>
}

export default function BankSearchPage() {
  return <Suspense fallback={<BankSearchFallback />}><SearchPageClient /></Suspense>
}
