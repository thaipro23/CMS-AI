'use client'

import { useEffect, useState } from 'react'
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
  group: 'bank' | 'ops' | 'admin'
  permission?: string
}

const navItems: NavItem[] = [
  { href: '/bank', label: 'Dashboard Bank', desc: 'Việc cần làm', icon: '🏦', group: 'bank' },
  { href: '/bank/departments', label: 'Bộ môn', desc: 'Môn, version, bài', icon: '📚', group: 'bank' },
  { href: '/bank/quiz', label: 'Tạo Quiz Open edX', desc: 'Map course & timer', icon: '🧩', group: 'bank' },
  { href: '/bank/history', label: 'Lịch sử Quiz', desc: 'Theo dõi & rollback', icon: '🕘', group: 'bank' },
  { href: '/premises', label: 'Cơ sở', desc: 'Premises AP', icon: '🏢', group: 'ops', permission: 'manage_settings' },
  { href: '/student-management', label: 'Lớp & sinh viên', desc: 'AP roster, phân công', icon: '🎓', group: 'ops' },
  { href: '/jobs', label: 'Tiến trình job', desc: 'Generate, publish, tạo quiz', icon: '⚙️', group: 'ops' },
  { href: '/audit', label: 'Nhật ký thao tác', desc: 'Ai làm gì, lỗi gì', icon: '🧾', group: 'ops' },
  { href: '/users', label: 'Người dùng & quyền', desc: 'RBAC Bank-first', icon: '👥', group: 'admin', permission: 'view_questions' },
  { href: '/settings', label: 'Cấu hình', desc: 'Quyền & hệ thống', icon: '🔐', group: 'admin', permission: 'manage_settings' },
]

const navGroups: Array<{ key: NavItem['group']; label: string }> = [
  { key: 'bank', label: 'Ngân hàng đề' },
  { key: 'ops', label: 'Vận hành' },
  { key: 'admin', label: 'Quản trị' },
]

function pageTitle(pathname: string) {
  const item = navItems.find((item) => pathname === item.href || pathname.startsWith(`${item.href}/`))
  return item ? item.label : 'Máy chủ AI học liệu'
}

function AppFooter({ compact = false }: { compact?: boolean }) {
  return <footer className={compact ? 'app-footer app-footer-compact' : 'app-footer'}>
    <div>
      <b>Open edX AI Server</b>
      <span>Ngân hàng đề · Tạo Quiz Open edX · Theo dõi giáo viên</span>
    </div>
    <div className="footer-links">
      <Link href="/bank">Dashboard Bank</Link>
      <Link href="/bank/quiz">Tạo Quiz</Link>
      <Link href="/audit">Nhật ký</Link>
      <span>v25.9.16.2.12</span>
    </div>
  </footer>
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname()
  const { courseId, setCourseId, role, setRole, userId, setUserId, accessToken, setAccessToken, can, isAuthenticated, authReady } = useAppContext()
  const [autoLoginMessage, setAutoLoginMessage] = useState('')
  const visibleItems = navItems.filter((item) => !item.permission || can(item.permission))
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

  const hideTopbar = true
  return <div className="app-layout">
    <aside className="sidebar">
      <div className="brand">
        <div className="brand-mark">AI</div>
        <div><b>Open edX AI</b><small>Máy chủ học liệu</small></div>
      </div>
      <nav className="side-nav grouped-side-nav">
        {navGroups.map((group) => {
          const items = visibleItems.filter((item) => item.group === group.key)
          if (!items.length) return null
          return <div className="nav-group" key={group.key}>
            <div className="nav-group-title">{group.label}</div>
            <div className="nav-group-items">
              {items.map((item) => <Link key={item.href} href={item.href} className={pathname === item.href || pathname.startsWith(`${item.href}/`) ? 'nav-link active' : 'nav-link'}>
                <span className="nav-icon" aria-hidden="true">{item.icon}</span>
                <span className="nav-text"><b>{item.label}</b><small>{item.desc}</small></span>
              </Link>)}
            </div>
          </div>
        })}
      </nav>
      <div className="sidebar-note">
        <b>{accessToken.trim() ? 'Đã có phiên AI' : 'Đang lấy phiên CMS'}</b>
        <span>{accessToken.trim() ? `User ${userId} · ${ROLE_LABELS[role]}` : (autoLoginMessage || 'Nếu đã đăng nhập CMS/Open edX, AI Server sẽ tự nhận phiên.')} </span>
        <button className="btn small secondary" onClick={loginWithCms}>{accessToken.trim() ? 'Làm mới phiên CMS' : 'Lấy phiên CMS ngay'}</button>
      </div>
    </aside>
    <div className="main-area">
      {!hideTopbar ? <header className="topbar">
        <div>
          <div className="eyebrow">Máy chủ AI / {pageTitle(pathname)}</div>
          <h1>{pageTitle(pathname)}</h1>
          <p>Khóa học: <b>{courseId}</b></p>
        </div>
        <div className="topbar-controls">
          <label>Mã khóa học</label>
          <input className="input" value={courseId} onChange={(event) => setCourseId(event.target.value)} />
          <div className="topbar-grid">
            <div><label>Người dùng demo</label><input className="input" value={userId} onChange={(event) => setUserId(event.target.value)} disabled={!!accessToken.trim()} /></div>
            <div><label>Vai trò demo</label><select className="input" value={role} onChange={(event) => setRole(event.target.value as Role)} disabled={!!accessToken.trim()}><option value="admin">admin</option><option value="teacher">teacher</option><option value="reviewer">reviewer</option><option value="viewer">viewer</option></select></div>
          </div>
          <label>Token JWT/SSO</label>
          <input className="input" type="password" placeholder="Bearer token production/SSO, để trống khi demo" value={accessToken} onChange={(event) => setAccessToken(event.target.value)} />
          <small>{accessToken.trim() ? 'Đang dùng Authorization Bearer token trong memory; reload trang sẽ mất token, role demo không gửi lên backend.' : ROLE_LABELS[role]}</small>
        </div>
      </header> : null}
      <main className="content-shell compact-content-shell">{children}</main>
      <AppFooter />
    </div>
  </div>
}
