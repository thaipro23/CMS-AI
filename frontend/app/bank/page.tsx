import { Suspense } from 'react'
import { BankDashboardPage } from './_components/BankPages'

function BankDashboardFallback() {
  return <div className="page-stack bank-multipage">
    <section className="card page-intro">
      <div>
        <div className="eyebrow">Ngân hàng đề</div>
        <h2>Đang tải tổng quan...</h2>
        <p className="helper">Hệ thống đang chuẩn bị dữ liệu dashboard.</p>
      </div>
    </section>
  </div>
}

export default function BankHome() {
  return <Suspense fallback={<BankDashboardFallback />}>
    <BankDashboardPage />
  </Suspense>
}
