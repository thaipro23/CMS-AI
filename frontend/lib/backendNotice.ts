import { BackendUiNotice, UiStatus } from '../types'

export type InlineMessageTone = 'success' | 'danger' | 'warning' | 'info'

export type BackendInlineMessage = {
  tone: InlineMessageTone
  text: string
  title?: string
}

function normalizeUiStatus(raw: unknown, fallback: UiStatus = 'info'): UiStatus {
  const value = String(raw || '').trim().toLowerCase()
  if (value === 'danger') return 'error'
  if (value === 'success' || value === 'error' || value === 'warning' || value === 'info') return value
  return fallback
}

export function toneFromUiStatus(raw: unknown, fallback: UiStatus = 'info'): InlineMessageTone {
  const status = normalizeUiStatus(raw, fallback)
  return status === 'error' ? 'danger' : status
}

export function inlineMessageFromBackend(
  result: BackendUiNotice | null | undefined,
  fallbackText: string,
  fallbackStatus: UiStatus = 'info',
): BackendInlineMessage {
  const status = normalizeUiStatus(result?.ui_status, fallbackStatus)
  return {
    tone: status === 'error' ? 'danger' : status,
    text: String(result?.ui_message || fallbackText),
    title: result?.ui_title || undefined,
  }
}
