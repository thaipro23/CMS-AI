import { Suspense } from 'react'
import { BankDashboardPage } from './_components/BankPages'

function BankDashboardFallback() {
  return <div className="page-stack bank-multipage dashboard-modern-page">
    <div className="dashboard-hero card">
      <div>
        <span className="eyebrow">AI Question Bank · Open edX</span>
        <h1>Đang tải Dashboard...</h1>
        <p>Hệ thống đang chuẩn bị số liệu theo phạm vi quyền của bạn.</p>
      </div>
    </div>
    <div className="dashboard-kpi-grid">
      <div className="dashboard-skeleton" style={{ minHeight: 124 }} />
      <div className="dashboard-skeleton" style={{ minHeight: 124 }} />
      <div className="dashboard-skeleton" style={{ minHeight: 124 }} />
      <div className="dashboard-skeleton" style={{ minHeight: 124 }} />
    </div>
  </div>
}

export default function BankHome() {
  return <Suspense fallback={<BankDashboardFallback />}><BankDashboardPage /></Suspense>
}
