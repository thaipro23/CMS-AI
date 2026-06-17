import { Suspense } from 'react'
import { ChapterWorkspacePage } from '../../_components/BankPages'

function ChapterWorkspaceFallback() {
  return <div className="page-stack bank-multipage">
    <section className="card page-intro">
      <div>
        <div className="eyebrow">Ngân hàng đề</div>
        <h2>Đang tải bài học...</h2>
        <p className="helper">Hệ thống đang chuẩn bị workspace câu hỏi.</p>
      </div>
    </section>
  </div>
}

export default function Page({ params }: { params: { chapterId: string } }) {
  return <Suspense fallback={<ChapterWorkspaceFallback />}>
    <ChapterWorkspacePage chapterId={params.chapterId} />
  </Suspense>
}
