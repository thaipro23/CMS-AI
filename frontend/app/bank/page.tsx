import { PageRoot } from '../../components/layout/PageHeader'
import { Suspense } from 'react'
import { BankDashboardPage } from './_components/BankPages'

function BankDashboardFallback() {
  return <PageRoot className="page-stack bank-multipage dashboard-modern-page">
    <div className="dashboard-hero card">
      <div>
        <h1>Đang tải Tổng quan Ngân hàng câu hỏi...</h1>
      </div>
    </div>
    <div className="dashboard-kpi-grid">
      <div className="dashboard-skeleton" style={{ minHeight: 124 }} />
      <div className="dashboard-skeleton" style={{ minHeight: 124 }} />
      <div className="dashboard-skeleton" style={{ minHeight: 124 }} />
      <div className="dashboard-skeleton" style={{ minHeight: 124 }} />
    </div>
  </PageRoot>
}

export default function BankHome() {
  return <Suspense fallback={<BankDashboardFallback />}><BankDashboardPage /></Suspense>
}
