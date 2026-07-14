'use client'

import { useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { PageHeader } from '../../components/layout/PageHeader'

export default function TrainingManagementRedirectPage() {
  const router = useRouter()
  useEffect(() => { router.replace('/teacher-management') }, [router])
  return <div className="page-stack student-management-page academic-flow-page training-management-page"><PageHeader eyebrow="Vận hành đào tạo" title="Đang chuyển sang Quản lý giảng viên..." description="Đường dẫn mới là /teacher-management." icon="teachers" /></div>
}
