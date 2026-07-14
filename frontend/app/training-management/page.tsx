'use client'

import { useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { PageHeader, PageRoot } from '../../components/layout/PageHeader'

export default function TrainingManagementRedirectPage() {
  const router = useRouter()
  useEffect(() => { router.replace('/teacher-management') }, [router])
  return <PageRoot className="page-stack student-management-page academic-flow-page training-management-page"><PageHeader eyebrow="Vận hành đào tạo" title="Đang chuyển sang Quản lý giảng viên..." icon="teachers" /></PageRoot>
}
