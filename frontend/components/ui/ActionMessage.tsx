'use client'

export type ActionMessageType = 'success' | 'error' | 'info' | 'warning'

export type ActionMessageData = {
  type: ActionMessageType
  title?: string
  body: string
  detail?: string
}

export function toUserError(error: unknown, fallback = 'Thao tác thất bại. Vui lòng kiểm tra lại hoặc xem log backend.'): ActionMessageData {
  const raw = error instanceof Error ? error.message : String(error || '')
  return { type: 'error', title: 'Có lỗi xảy ra', body: raw || fallback }
}

export function ActionMessage({ message, onClose }: { message: ActionMessageData | null; onClose?: () => void }) {
  if (!message) return null
  return <section className={`notice notice-${message.type}`}>
    <div>
      <strong>{message.title || titleFor(message.type)}</strong>
      <p>{message.body}</p>
      {message.detail && <small>{message.detail}</small>}
    </div>
    {onClose && <button className="notice-close" onClick={onClose} aria-label="Đóng thông báo">×</button>}
  </section>
}

function titleFor(type: ActionMessageType) {
  if (type === 'success') return 'Thành công'
  if (type === 'error') return 'Có lỗi xảy ra'
  if (type === 'warning') return 'Cần chú ý'
  return 'Thông báo'
}
