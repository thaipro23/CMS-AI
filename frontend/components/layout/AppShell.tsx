'use client'

import { useEffect, useMemo, useState } from 'react'
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { useAppContext } from '../../context/AppContext'
import { ROLE_LABELS, Role } from '../../types'
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
  { href: '/bank', label: 'Tổng quan', desc: 'Việc cần xử lý', icon: '⌁', group: 'work' },
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

function pageDescription(pathname: string) {
  if (pathname.startsWith('/bank/chapters/')) return 'Duyệt, sửa và kiểm tra chất lượng câu hỏi trong chapter.'
  if (pathname.startsWith('/bank/search')) return 'Danh sách xử lý được mở từ dashboard và đã lọc theo phân quyền.'
  const item = navItems.find((item) => pathname === item.href || pathname.startsWith(`${item.href}/`))
  return item?.desc || 'Quản lý ngân hàng đề và tích hợp Open edX.'
}

function AppFooter() {
  return <footer className="app-footer app-footer-compact product-footer">
    <div><b>Open edX AI Server</b><span>Ngân hàng đề · Phân quyền · Quiz Open edX</span></div>
    <div className="footer-links"><span>v25.9.15.6.38.8</span></div>
  </footer>
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname()
  const {
    courseId,
    setCourseId,
    role,
    setRole,
    userId,
    setUserId,
    accessToken,
    setAccessToken,
    can,
    isAuthenticated,
    authReady,
  } = useAppContext()
  const [autoLoginMessage, setAutoLoginMessage] = useState('')
  const [sessionOpen, setSessionOpen] = useState(false)

  const visibleItems = useMemo(() => navItems.filter((item) => !item.permission || can(item.permission)), [can])
  const currentTitle = pageTitle(pathname)
  const currentDesc = pageDescription(pathname)

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
      <header className="workspace-topbar">
        <div>
          <span className="eyebrow">Không gian làm việc</span>
          <h1>{currentTitle}</h1>
          <p>{currentDesc}</p>
        </div>
        <div className="workspace-actions">
          <span className="workspace-chip">Scope theo phân quyền</span>
          <button className="btn secondary small" type="button" onClick={() => setSessionOpen(true)}>Phiên làm việc</button>
        </div>
      </header>

      <main id="main-content" className="content-shell compact-content-shell product-content" tabIndex={-1}>{children}</main>
      <AppFooter />
    </div>

    {sessionOpen ? <div className="modal-backdrop" onMouseDown={() => setSessionOpen(false)}>
      <section className="modal-card session-modal" role="dialog" aria-modal="true" aria-labelledby="session-title" onMouseDown={(event) => event.stopPropagation()}>
        <div className="section-head"><div><h2 id="session-title">Phiên làm việc</h2><p className="helper">Chỉ dùng khi cần kiểm tra course, token hoặc tài khoản demo.</p></div><button className="btn small secondary" type="button" onClick={() => setSessionOpen(false)}>Đóng</button></div>
        <div className="grid grid-2">
          <label>Mã khóa học<input className="input" value={courseId} onChange={(event) => setCourseId(event.target.value)} /></label>
          <label>Người dùng demo<input className="input" value={userId} onChange={(event) => setUserId(event.target.value)} disabled={!!accessToken.trim()} /></label>
          <label>Vai trò demo<select className="input" value={role} onChange={(event) => setRole(event.target.value as Role)} disabled={!!accessToken.trim()}><option value="admin">admin</option><option value="teacher">teacher</option><option value="reviewer">reviewer</option><option value="viewer">viewer</option></select></label>
          <label>Token JWT/SSO<input className="input" type="password" placeholder="Bearer token production/SSO" value={accessToken} onChange={(event) => setAccessToken(event.target.value)} /></label>
        </div>
        <div className="button-row"><button className="btn" type="button" onClick={loginWithCms}>Lấy phiên CMS</button><span className="helper">{accessToken.trim() ? 'Đang dùng Bearer token trong memory.' : ROLE_LABELS[role]}</span></div>
      </section>
    </div> : null}
  </div>
}
