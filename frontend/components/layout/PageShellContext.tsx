'use client'

import { createContext, useContext, useId, useLayoutEffect, type ReactNode } from 'react'
import type { AppIconName } from '../icons/AppIcon'
import type { VisualTone } from '../ui/VisualIcon'

export type PageChrome = {
  registrationId: string
  eyebrow?: string
  title: string
  icon?: AppIconName
  tone?: VisualTone
}

type PageShellRegistration = {
  registerChrome: (value: PageChrome) => () => void
  registerLayout: (registrationId: string, className: string) => () => void
}

const PageShellContext = createContext<PageShellRegistration | null>(null)

export const PageShellProvider = PageShellContext.Provider

export function usePageShellRegistration() {
  return useContext(PageShellContext)
}

export function PageRoot({ className, children }: { className: string; children: ReactNode }) {
  const registration = usePageShellRegistration()
  const registrationId = useId()

  useLayoutEffect(() => {
    if (!registration) return undefined
    return registration.registerLayout(registrationId, className)
  }, [className, registration, registrationId])

  return <>{children}</>
}
