import Link from 'next/link'
import { VisualIcon } from '../components/ui/VisualIcon'

export default function NotFound() {
  return <div className="route-state-page">
    <section className="route-state-card">
      <VisualIcon label="Không tìm thấy trang" icon="search" tone="slate" />
      <h1>Không tìm thấy trang</h1>
      <p>Đường dẫn không tồn tại, đã bị ẩn khỏi production hoặc nằm ngoài phạm vi bạn được phân công.</p>
      <Link className="btn" href="/bank">Về trang tổng quan</Link>
    </section>
  </div>
}
