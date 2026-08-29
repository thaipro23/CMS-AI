'use client'

export default function GlobalError({ reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return <html lang="vi-VN"><body><main className="route-state-page"><section className="route-state-card" role="alert"><h1>Hệ thống tạm thời không thể hiển thị</h1><p>Ứng dụng gặp lỗi ở lớp giao diện chung. Hãy tải lại hoặc thử lại sau.</p><button className="btn" type="button" onClick={reset}>Tải lại giao diện</button></section></main></body></html>
}
