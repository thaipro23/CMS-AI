import Link from 'next/link'
import { PageHeader, PageRoot } from '../../../components/layout/PageHeader'
import { InlineNotice } from '../../../components/ui/InlineNotice'

export default function LoggedOutPage() {
  return <PageRoot className="page-stack auth-logged-out-page">
    <PageHeader eyebrow="Bảo mật phiên" title="Đã đăng xuất khỏi AI Server" icon="shield" />
    <section className="card section-card auth-logged-out-card">
      <InlineNotice notice={{
        type: 'success',
        title: 'Phiên AI Server đã được thu hồi',
        body: 'Cookie đăng nhập đã được xóa và mã phiên đã bị đánh dấu không còn hiệu lực. Phiên Open edX/CMS của bạn không bị đăng xuất.',
      }} />
      <div className="section-actions">
        <Link className="btn primary" href="/bank">Đăng nhập lại bằng CMS</Link>
      </div>
    </section>
  </PageRoot>
}
