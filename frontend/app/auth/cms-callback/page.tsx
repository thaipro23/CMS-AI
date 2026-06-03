'use client'

import { Suspense, useEffect, useState } from 'react'
import Link from 'next/link'
import { useRouter, useSearchParams } from 'next/navigation'
import { exchangeOpenEdxSessionTicket } from '../../../lib/api'
import { useAppContext } from '../../../context/AppContext'
import { ActionMessage, ActionMessageData, toUserError } from '../../../components/ui/ActionMessage'

function CmsCallbackContent() {
  const router = useRouter()
  const params = useSearchParams()
  const { applyAuthSession } = useAppContext()
  const [message, setMessage] = useState<ActionMessageData | null>({ type: 'info', body: 'Đang nhận phiên đăng nhập từ CMS...' })

  useEffect(() => {
    const ticket = params.get('ticket') || ''
    if (!ticket) {
      setMessage({ type: 'warning', title: 'Thiếu CMS session ticket', body: 'CMS không trả về ticket. Hãy đăng nhập CMS rồi thử lại.' })
      return
    }
    exchangeOpenEdxSessionTicket(ticket)
      .then((session) => {
        applyAuthSession(session)
        setMessage({ type: 'success', title: 'Đăng nhập CMS thành công', body: `Đã nhận quyền ${session.role} cho user ${session.user_id}. Đang chuyển về dashboard...` })
        window.setTimeout(() => router.push('/dashboard'), 700)
      })
      .catch((error) => setMessage(toUserError(error)))
  }, [params, applyAuthSession, router])

  return <div className="page-stack">
    <section className="card page-intro">
      <div>
        <div className="eyebrow">CMS SSO</div>
        <h2>Đăng nhập bằng phiên CMS/Open edX</h2>
        <p className="helper">Nếu bạn đã đăng nhập CMS, AI Server sẽ đổi session bridge ticket thành token nội bộ ngắn hạn.</p>
      </div>
      <Link className="btn secondary" href="/dashboard">Về dashboard</Link>
    </section>
    <ActionMessage message={message} onClose={() => setMessage(null)} />
  </div>
}

function CmsCallbackFallback() {
  return <div className="page-stack">
    <section className="card page-intro">
      <div>
        <div className="eyebrow">CMS SSO</div>
        <h2>Đang chuẩn bị nhận phiên CMS...</h2>
        <p className="helper">Vui lòng chờ trong giây lát.</p>
      </div>
      <Link className="btn secondary" href="/dashboard">Về dashboard</Link>
    </section>
  </div>
}

export default function CmsCallbackPage() {
  return <Suspense fallback={<CmsCallbackFallback />}>
    <CmsCallbackContent />
  </Suspense>
}
