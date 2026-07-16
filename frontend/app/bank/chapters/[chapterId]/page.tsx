import { PageRoot } from '../../../../components/layout/PageHeader'
import { Suspense } from 'react'
import { ChapterWorkspacePage } from '../../_components/BankPages'

function ChapterWorkspaceFallback() {
  return <PageRoot className="page-stack bank-multipage bank-contract-page">
    <div className="card"><b>Đang tải workspace...</b><p>Hệ thống đang áp dụng bộ lọc và quyền truy cập.</p></div>
    <div className="dashboard-skeleton" style={{ minHeight: 180 }} />
  </PageRoot>
}

export default function Page({ params }: { params: { chapterId: string } }) {
  return <Suspense fallback={<ChapterWorkspaceFallback />}><ChapterWorkspacePage chapterId={params.chapterId} /></Suspense>
}
