'use client'

import { Suspense, useEffect, useRef, useState } from 'react'
import Link from 'next/link'
import { useRouter, useSearchParams } from 'next/navigation'
import { clearCmsSessionBridgeAttempt, consumeCmsPostAuthReturnPath, exchangeOpenEdxSessionTicket, normalizeInternalReturnPath } from '../../../lib/api'
import { useAppContext } from '../../../context/AppContext'
import { ActionMessage, ActionMessageData, toUserError } from '../../../components/ui/ActionMessage'
import { PageHeader, PageRoot } from '../../../components/layout/PageHeader'

function CmsCallbackContent() {
  const router = useRouter()
  const params = useSearchParams()
  const { applyAuthSession } = useAppContext()
  const processedTicketRef = useRef<string | null>(null)
  const [message, setMessage] = useState<ActionMessageData | null>({ type: 'info', body: 'Đang nhận phiên đăng nhập từ CMS...' })

  useEffect(() => {
    const ticket = params.get('ticket') || ''
    if (!ticket) {
      clearCmsSessionBridgeAttempt()
      setMessage({ type: 'warning', title: 'Thiếu CMS session ticket', body: 'CMS không trả về ticket. Hãy đăng nhập CMS rồi thử lại.' })
      return
    }
    if (processedTicketRef.current === ticket) return
    processedTicketRef.current = ticket

    exchangeOpenEdxSessionTicket(ticket)
      .then((session) => {
        applyAuthSession(session)
        clearCmsSessionBridgeAttempt()
        const storedTarget = consumeCmsPostAuthReturnPath('/bank')
        const target = normalizeInternalReturnPath(params.get('next'), storedTarget)
        setMessage({ type: 'success', title: 'Đăng nhập CMS thành công', body: `Đã nhận quyền ${session.role} cho user ${session.user_id}. Đang chuyển về màn hình yêu cầu...` })
        window.setTimeout(() => router.replace(target), 350)
      })
      .catch((error) => {
        processedTicketRef.current = null
        clearCmsSessionBridgeAttempt()
        setMessage(toUserError(error))
      })
  }, [params, applyAuthSession, router])

  return <PageRoot className="page-stack">
    <PageHeader eyebrow="CMS SSO" title="Đăng nhập bằng phiên CMS/Open edX" icon="shield" primaryAction={<Link className="btn secondary" href="/dashboard">Về dashboard</Link>} />
    <ActionMessage message={message} onClose={() => setMessage(null)} />
  </PageRoot>
}

function CmsCallbackFallback() {
  return <PageRoot className="page-stack">
    <PageHeader eyebrow="CMS SSO" title="Đang chuẩn bị nhận phiên CMS..." icon="shield" primaryAction={<Link className="btn secondary" href="/dashboard">Về dashboard</Link>} />
  </PageRoot>
}

export default function CmsCallbackPage() {
  return <Suspense fallback={<CmsCallbackFallback />}>
    <CmsCallbackContent />
  </Suspense>
}
