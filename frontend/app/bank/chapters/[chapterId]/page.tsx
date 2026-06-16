import { Suspense } from 'react'
import { ChapterWorkspacePage } from '../../_components/BankPages'

function ChapterWorkspaceFallback() {
  return <div className="page-stack bank-multipage">
    <div className="card"><b>Đang tải workspace...</b><p>Hệ thống đang áp dụng bộ lọc và quyền truy cập.</p></div>
    <div className="dashboard-skeleton" style={{ minHeight: 180 }} />
  </div>
}

export default function Page({ params }: { params: { chapterId: string } }) {
  return <Suspense fallback={<ChapterWorkspaceFallback />}><ChapterWorkspacePage chapterId={params.chapterId} /></Suspense>
}
