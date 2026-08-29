'use client'

import { useEffect } from 'react'
import { VisualIcon } from '../components/ui/VisualIcon'

export default function RouteError({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  useEffect(() => { console.error('Route render failed', error) }, [error])
  return <div className="route-state-page">
    <section className="route-state-card" role="alert">
      <VisualIcon label="Không tải được trang" icon="alert" tone="red" />
      <h1>Không tải được nội dung</h1>
      <p>Đã xảy ra lỗi khi dựng trang hoặc tải dữ liệu cần thiết. Hãy thử lại; nếu lỗi tiếp diễn, gửi mã yêu cầu trong Network cho quản trị viên.</p>
      <button className="btn" type="button" onClick={reset}>Thử lại</button>
    </section>
  </div>
}
