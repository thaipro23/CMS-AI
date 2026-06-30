'use client'

import { useEffect } from 'react'
import { useRouter } from 'next/navigation'

export default function TrainingManagementRedirectPage() {
  const router = useRouter()
  useEffect(() => { router.replace('/teacher-management') }, [router])
  return <div className="page-stack student-management-page academic-flow-page training-management-page"><section className="card academic-unified-card"><h2>Đang chuyển sang Quản lý giảng viên...</h2><p>Đường dẫn mới là /teacher-management.</p></section></div>
}
