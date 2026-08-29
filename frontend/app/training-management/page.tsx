'use client'

import { useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { PageRoot } from '../../components/layout/PageHeader'
import { EnterpriseScreenHeader } from '../../components/layout/EnterpriseDesignContract'

export default function TrainingManagementRedirectPage() {
  const router = useRouter()
  useEffect(() => { router.replace('/teacher-management/cms') }, [router])
  return <PageRoot className="page-stack enterprise-standard-page student-management-page academic-flow-page training-management-page"><EnterpriseScreenHeader eyebrow="Vận hành đào tạo" title="Đang chuyển sang Quản lý giảng viên CMS..." description="Hệ thống đang mở màn hình quản lý giảng viên CMS theo cấu trúc vận hành đào tạo mới." icon="teachers" tone="blue" breadcrumbs={[{ label: 'Vận hành đào tạo' }, { label: 'Quản lý giảng viên CMS' }]} /></PageRoot>
}
