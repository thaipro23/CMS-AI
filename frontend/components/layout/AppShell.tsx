'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { useAppContext } from '../../context/AppContext'
import { ROLE_LABELS, Role } from '../../types'
import { buildCmsSessionBridgeUrl } from '../../lib/api'

const navItems: { href: string; label: string; desc: string; permission?: string }[] = [
  { href: '/workflow', label: 'Quy trình tạo câu hỏi', desc: 'Luồng chính' },
  { href: '/dashboard', label: 'Tổng quan', desc: 'Thống kê khóa học' },
  { href: '/sync', label: 'Đồng bộ học liệu', desc: 'Open edX nodes/chunks' },
  { href: '/generate', label: 'Tạo câu hỏi', desc: 'Generate nâng cao' },
  { href: '/review', label: 'Duyệt câu hỏi', desc: 'Hàng chờ giảng viên' },
  { href: '/question-bank', label: 'Ngân hàng câu hỏi', desc: 'Lọc, sửa, publish' },
  { href: '/export', label: 'Xuất Open edX', desc: 'OLX/XML' },
  { href: '/jobs', label: 'Tiến trình', desc: 'Theo dõi job' },
  { href: '/audit', label: 'Nhật ký hệ thống', desc: 'Lỗi do ai/cái gì' },
  { href: '/users', label: 'Thống kê người dùng', desc: 'Theo từng user', permission: 'view_user_analytics' },
  { href: '/settings', label: 'Cấu hình', desc: 'Quyền & hệ thống', permission: 'manage_settings' },
]

function pageTitle(pathname: string) {
  const item = navItems.find((item) => item.href === pathname)
  return item ? item.label : 'Máy chủ AI học liệu'
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname()
  const { courseId, setCourseId, role, setRole, userId, setUserId, accessToken, setAccessToken, can, isAuthenticated, authReady } = useAppContext()
  const [autoLoginMessage, setAutoLoginMessage] = useState('')
  const loginWithCms = () => {
    try {
      window.location.href = buildCmsSessionBridgeUrl(courseId)
    } catch (error) {
      alert(error instanceof Error ? error.message : 'Không tạo được CMS login URL')
    }
  }
  useEffect(() => {
    // Production behavior: if user already has a CMS/Studio session, they should
    // appear in AI Server automatically. We still need a top-level redirect to CMS
    // because browser security prevents AI Server from reading CMS cookies directly
    // across domains. The CMS bridge endpoint reads its own session cookie and
    // returns a short-lived signed ticket.
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
      <nav className="side-nav">
        {navItems.filter((item) => !item.permission || can(item.permission)).map((item) => <Link key={item.href} href={item.href} className={pathname === item.href ? 'nav-link active' : 'nav-link'}>
          <b>{item.label}</b><small>{item.desc}</small>
        </Link>)}
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
    </div>
  </div>
}
