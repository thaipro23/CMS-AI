import { Suspense } from 'react'
import { DepartmentsPage } from '../_components/BankPages'

export default function Page() {
  return <Suspense fallback={<div className="card empty-state">Đang tải danh sách bộ môn...</div>}><DepartmentsPage /></Suspense>
}
