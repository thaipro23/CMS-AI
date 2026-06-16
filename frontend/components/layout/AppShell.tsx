'use client'

import { useEffect, useMemo, useState } from 'react'
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { useAppContext } from '../../context/AppContext'
import { ROLE_LABELS } from '../../types'
import { buildCmsSessionBridgeUrl } from '../../lib/api'

type NavItem = {
  href: string
  label: string
  desc: string
  icon: string
  group: 'work' | 'operations' | 'admin'
  permission?: string
}

const navItems: NavItem[] = [
  { href: '/bank', label: 'Tổng quan', desc: 'Dashboard', icon: '⌁', group: 'work' },
  { href: '/bank/departments', label: 'Ngân hàng đề', desc: 'Bộ môn, môn, bài', icon: '▦', group: 'work' },
  { href: '/bank/quiz', label: 'Tạo Quiz', desc: 'Map Open edX', icon: '◈', group: 'work' },
  { href: '/bank/history', label: 'Lịch sử Quiz', desc: 'Release & rollback', icon: '◷', group: 'work' },
  { href: '/jobs', label: 'Tiến trình', desc: 'Job đang chạy', icon: '⚙', group: 'operations' },
  { href: '/audit', label: 'Nhật ký', desc: 'Theo dõi thao tác', icon: '☷', group: 'operations' },
  { href: '/users', label: 'Phân quyền', desc: 'Gán quyền theo scope', icon: '◎', group: 'admin', permission: 'view_questions' },
  { href: '/settings', label: 'Cấu hình', desc: 'Chính sách hệ thống', icon: '◇', group: 'admin', permission: 'manage_settings' },
]

const navGroups: Array<{ key: NavItem['group']; label: string }> = [
  { key: 'work', label: 'Công việc chính' },
  { key: 'operations', label: 'Vận hành' },
  { key: 'admin', label: 'Quản trị' },
]

function pageTitle(pathname: string) {
  const exact = navItems.find((item) => pathname === item.href)
  if (exact) return exact.label
  const nested = navItems
    .filter((item) => pathname.startsWith(`${item.href}/`))
    .sort((a, b) => b.href.length - a.href.length)[0]
  return nested ? nested.label : 'AI Server'
}

function AppFooter() {
  return <footer className="app-footer app-footer-compact product-footer">
    <div><b>Open edX AI Server</b><span>Ngân hàng đề · Phân quyền · Quiz Open edX</span></div>
    <div className="footer-links"><span>v25.9.15.6.38.8.4</span></div>
  </footer>
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname()
  const {
    courseId,
    role,
    userId,
    accessToken,
    can,
    isAuthenticated,
    authReady,
  } = useAppContext()
  const [autoLoginMessage, setAutoLoginMessage] = useState('')

  const visibleItems = useMemo(() => navItems.filter((item) => !item.permission || can(item.permission)), [can])
  const currentTitle = pageTitle(pathname)

  const loginWithCms = () => {
    try {
      window.location.href = buildCmsSessionBridgeUrl(courseId)
    } catch (error) {
      alert(error instanceof Error ? error.message : 'Không tạo được CMS login URL')
    }
  }

  useEffect(() => {
    if (typeof window === 'undefined') return
    if (!authReady) return
    if (isAuthenticated) {
      window.sessionStorage.removeItem('ai_openedx_cms_bridge_started_at')
      return
    }
    if (pathname.startsWith('/auth/cms-callback')) return
    const autoLoginEnabled = (process.env.NEXT_PUBLIC_AUTO_CMS_SESSION_LOGIN || 'true').toLowerCase() !== 'false'
    if (!autoLoginEnabled) return
    const startedAtRaw = window.sessionStorage.getItem('ai_openedx_cms_bridge_started_at')
    const startedAt = startedAtRaw ? Number(startedAtRaw) : 0
    const now = Date.now()
    if (startedAt && now - startedAt < 30000) {
      setAutoLoginMessage('Đang chờ CMS trả phiên đăng nhập...')
      return
    }
    try {
      setAutoLoginMessage('Đang chuyển sang CMS để lấy phiên đăng nhập...')
      window.sessionStorage.setItem('ai_openedx_cms_bridge_started_at', String(now))
      window.location.href = buildCmsSessionBridgeUrl(courseId)
    } catch (error) {
      setAutoLoginMessage(error instanceof Error ? error.message : 'Không tạo được CMS session bridge URL')
    }
  }, [authReady, courseId, isAuthenticated, pathname])

  return <div className="app-layout product-shell">
    <a className="skip-link" href="#main-content">Bỏ qua menu, tới nội dung chính</a>
    <aside className="sidebar product-sidebar" aria-label="Điều hướng chính">
      <Link href="/bank" className="brand product-brand" aria-label="Open edX AI Server">
        <div className="brand-mark product-brand-mark">AI</div>
        <div><b>AI Server</b><small>Question Bank · Open edX</small></div>
      </Link>

      <nav className="side-nav grouped-side-nav product-nav">
        {navGroups.map((group) => {
          const items = visibleItems.filter((item) => item.group === group.key)
          if (!items.length) return null
          return <div className="nav-group" key={group.key}>
            <div className="nav-group-title">{group.label}</div>
            <div className="nav-group-items">
              {items.map((item) => {
                const active = pathname === item.href || pathname.startsWith(`${item.href}/`)
                return <Link key={item.href} href={item.href} className={active ? 'nav-link active' : 'nav-link'} aria-current={active ? 'page' : undefined}>
                  <span className="nav-icon" aria-hidden="true">{item.icon}</span>
                  <span className="nav-text"><b>{item.label}</b><small>{item.desc}</small></span>
                </Link>
              })}
            </div>
          </div>
        })}
      </nav>

      <div className="sidebar-note product-session-card">
        <span className={accessToken.trim() ? 'session-dot ok' : 'session-dot wait'} />
        <div><b>{accessToken.trim() ? 'Đã đăng nhập' : 'Đang lấy phiên CMS'}</b><span>{accessToken.trim() ? `${userId || 'user'} · ${ROLE_LABELS[role]}` : (autoLoginMessage || 'AI Server sẽ tự nhận phiên từ CMS khi có thể.')}</span></div>
        <button className="btn small secondary" type="button" onClick={loginWithCms}>{accessToken.trim() ? 'Làm mới' : 'Đăng nhập CMS'}</button>
      </div>
    </aside>

    <div className="main-area product-main">
      <header className="workspace-topbar workspace-topbar-minimal">
        <div>
          <h1>{currentTitle}</h1>
        </div>
      </header>

      <main id="main-content" className="content-shell compact-content-shell product-content" tabIndex={-1}>{children}</main>
      <AppFooter />
    </div>
  </div>
}
