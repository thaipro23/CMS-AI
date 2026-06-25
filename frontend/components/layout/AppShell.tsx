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
  icon: IconName
  group: 'work' | 'operations' | 'admin'
  permission?: string
}

type IconName = 'dashboard' | 'bank' | 'quiz' | 'history' | 'building' | 'calendar' | 'sync' | 'students' | 'jobs' | 'audit' | 'users' | 'settings'

const navItems: NavItem[] = [
  { href: '/bank', label: 'Tổng quan', desc: 'Số liệu & việc cần xử lý', icon: 'dashboard', group: 'work' },
  { href: '/bank/departments', label: 'Ngân hàng đề', desc: 'Bộ môn, môn, phiên bản', icon: 'bank', group: 'work' },
  { href: '/bank/quiz', label: 'Tạo Quiz', desc: 'Đưa bài kiểm tra lên CMS', icon: 'quiz', group: 'work' },
  { href: '/bank/history', label: 'Lịch sử Quiz', desc: 'Đã tạo & khôi phục', icon: 'history', group: 'work' },
  { href: '/premises', label: 'Cơ sở', desc: 'Premises AP', icon: 'building', group: 'operations', permission: 'manage_settings' },
  { href: '/semesters', label: 'Học kỳ', desc: 'Term & Block AP', icon: 'calendar', group: 'operations', permission: 'manage_settings' },
  { href: '/ap-sync', label: 'Đồng bộ AP', desc: 'Theo kỳ, theo hệ', icon: 'sync', group: 'operations', permission: 'manage_settings' },
  { href: '/student-management', label: 'Sinh viên & lớp', desc: 'Danh sách AP, đồng bộ CMS', icon: 'students', group: 'operations' },
  { href: '/jobs', label: 'Tiến trình', desc: 'Việc đang xử lý', icon: 'jobs', group: 'operations' },
  { href: '/audit', label: 'Nhật ký', desc: 'Lịch sử thao tác', icon: 'audit', group: 'operations' },
  { href: '/users', label: 'Phân quyền', desc: 'Gán quyền theo phạm vi', icon: 'users', group: 'admin', permission: 'view_questions' },
  { href: '/settings', label: 'Cấu hình', desc: 'Chính sách hệ thống', icon: 'settings', group: 'admin', permission: 'manage_settings' },
]

const navGroups: Array<{ key: NavItem['group']; label: string }> = [
  { key: 'work', label: 'Công việc chính' },
  { key: 'operations', label: 'Vận hành' },
  { key: 'admin', label: 'Quản trị' },
]


function ShellIcon({ name }: { name: IconName }) {
  const common = { width: 18, height: 18, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 1.8, strokeLinecap: 'round' as const, strokeLinejoin: 'round' as const, 'aria-hidden': true }
  const icons: Record<IconName, React.ReactNode> = {
    dashboard: <><path d="M4 13h6V4H4z" /><path d="M14 20h6V4h-6z" /><path d="M4 20h6v-3H4z" /></>,
    bank: <><path d="M4 10h16" /><path d="M6 10v8" /><path d="M10 10v8" /><path d="M14 10v8" /><path d="M18 10v8" /><path d="M3 20h18" /><path d="M12 4l8 4H4z" /></>,
    quiz: <><path d="M9 11l2 2 4-5" /><path d="M5 4h14v16H5z" /><path d="M8 17h8" /></>,
    history: <><path d="M3 12a9 9 0 1 0 3-6.7" /><path d="M3 4v5h5" /><path d="M12 7v6l4 2" /></>,
    building: <><path d="M4 20h16" /><path d="M6 20V6h8v14" /><path d="M14 10h4v10" /><path d="M8 9h2" /><path d="M8 13h2" /></>,
    calendar: <><path d="M7 3v4" /><path d="M17 3v4" /><path d="M4 8h16" /><path d="M5 5h14v15H5z" /></>,
    sync: <><path d="M21 12a8.5 8.5 0 0 1-14.5 6" /><path d="M3 12a8.5 8.5 0 0 1 14.5-6" /><path d="M18 3v5h-5" /><path d="M6 21v-5h5" /></>,
    students: <><path d="M16 11a4 4 0 1 0-8 0" /><path d="M4 20a8 8 0 0 1 16 0" /><path d="M17 8a3 3 0 0 1 3 3" /></>,
    jobs: <><path d="M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6z" /><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1-2 3-.2-.1a1.7 1.7 0 0 0-2 .1 1.7 1.7 0 0 0-.8 1.5V22h-3.6v-.5a1.7 1.7 0 0 0-.8-1.5 1.7 1.7 0 0 0-2-.1l-.2.1-2-3 .1-.1a1.7 1.7 0 0 0 .3-1.9 1.7 1.7 0 0 0-1.4-1.1H4v-3.8h.4a1.7 1.7 0 0 0 1.4-1.1" /></>,
    audit: <><path d="M5 4h14" /><path d="M5 8h14" /><path d="M5 12h10" /><path d="M5 16h8" /><path d="M5 20h14" /></>,
    users: <><path d="M16 21v-2a4 4 0 0 0-4-4H7a4 4 0 0 0-4 4v2" /><path d="M9.5 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8z" /><path d="M17 11l2 2 3-4" /></>,
    settings: <><path d="M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6z" /><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1-2 3-.2-.1a1.7 1.7 0 0 0-2 .1 1.7 1.7 0 0 0-.8 1.5V22h-3.6v-.5a1.7 1.7 0 0 0-.8-1.5 1.7 1.7 0 0 0-2-.1l-.2.1-2-3 .1-.1a1.7 1.7 0 0 0 .3-1.9 1.7 1.7 0 0 0-1.4-1.1H4v-3.8h.4a1.7 1.7 0 0 0 1.4-1.1" /></>,
  }
  return <svg {...common}>{icons[name]}</svg>
}

function pageTitle(pathname: string) {
  const exact = navItems.find((item) => pathname === item.href)
  if (exact) return exact.label
  const nested = navItems
    .filter((item) => pathname.startsWith(`${item.href}/`))
    .sort((a, b) => b.href.length - a.href.length)[0]
  return nested ? nested.label : 'AI Server'
}

function pageSubtitle(pathname: string) {
  if (pathname.startsWith('/bank/chapters/')) return 'Không gian làm việc bài học, học liệu và câu hỏi.'
  if (pathname.startsWith('/bank/departments')) return 'Quản trị cấu trúc ngân hàng đề theo bộ môn.'
  if (pathname.startsWith('/bank/subjects')) return 'Quản trị phiên bản môn và vòng đời học liệu.'
  if (pathname.startsWith('/student-management')) return 'Theo dõi lớp, sinh viên, enrollment và tiến độ CMS.'
  if (pathname.startsWith('/jobs')) return 'Giám sát tác vụ nền, queue và lỗi vận hành.'
  if (pathname.startsWith('/settings')) return 'Cấu hình chính sách tích hợp và vận hành hệ thống.'
  return 'Ngân hàng đề · Open edX · AP Sync · Quiz trên CMS'
}

function buildStudentManagementTopbar(pathname: string, searchParams: { get(name: string): string | null }) {
  if (!pathname.startsWith('/student-management')) return null

  const subjectIdMatch = pathname.match(/^\/student-management\/subjects\/([^/]+)\/classes/)
  const classIdMatch = pathname.match(/^\/student-management\/classes\/([^/]+)/)
  const subjectId = subjectIdMatch?.[1] || searchParams.get('subject_id') || ''
  const subjectCode = searchParams.get('subject_code') || ''
  const subjectName = searchParams.get('subject_name') || ''
  const termId = searchParams.get('term_id') || ''
  const termName = searchParams.get('term_name') || ''
  const branch = searchParams.get('branch') || 'poly'
  const campus = searchParams.get('campus') || ''

  const subjectParams = new URLSearchParams()
  if (termId) subjectParams.set('term_id', termId)
  if (branch) subjectParams.set('branch', branch)
  if (campus) subjectParams.set('campus', campus)
  if (termName) subjectParams.set('term_name', termName)
  if (subjectCode) subjectParams.set('subject_code', subjectCode)
  if (subjectName) subjectParams.set('subject_name', subjectName)
  const subjectHref = subjectId
    ? `/student-management/subjects/${encodeURIComponent(subjectId)}/classes${subjectParams.toString() ? `?${subjectParams.toString()}` : ''}`
    : '/student-management'

  const items: Array<{ label: string; href?: string }> = [
    { label: 'Quản lý sinh viên', href: '/student-management' },
    { label: 'Môn', href: pathname === '/student-management' ? undefined : '/student-management' },
  ]

  if (subjectIdMatch || classIdMatch) items.push({ label: subjectCode || 'Môn đã chọn', href: classIdMatch ? subjectHref : undefined })
  if (classIdMatch) items.push({ label: 'Lớp' })
  return items
}

function AppFooter() {
  return <footer className="app-footer">
    <span>AI Server · Open edX CMS</span>
    <span>v25.9.16.5.34</span>
  </footer>
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname()
  const [topbarSearch, setTopbarSearch] = useState('')
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const {
    courseId,
    role,
    userId,
    can,
    isAuthenticated,
    authReady,
  } = useAppContext()
  const [autoLoginMessage, setAutoLoginMessage] = useState('')
  const [theme, setTheme] = useState<'dark' | 'light'>('dark')

  useEffect(() => {
    if (typeof window === 'undefined') return
    const stored = window.localStorage.getItem('ai-server-theme')
    const systemDark = window.matchMedia?.('(prefers-color-scheme: dark)').matches
    const nextTheme = stored === 'light' || stored === 'dark' ? stored : (systemDark ? 'dark' : 'light')
    setTheme(nextTheme)
  }, [])

  useEffect(() => {
    if (typeof document === 'undefined') return
    document.documentElement.setAttribute('data-ai-theme', theme)
    document.body.classList.toggle('ai-theme-dark', theme === 'dark')
    document.body.classList.toggle('ai-theme-light', theme === 'light')
    try { window.localStorage.setItem('ai-server-theme', theme) } catch (error) { /* ignore */ }
  }, [theme])

  const toggleTheme = () => setTheme((current) => current === 'dark' ? 'light' : 'dark')
  const visibleItems = useMemo(() => navItems.filter((item) => !item.permission || can(item.permission)), [can])
  const currentTitle = pageTitle(pathname)
  const currentSubtitle = pageSubtitle(pathname)
  const studentTopbar = buildStudentManagementTopbar(pathname, new URLSearchParams(topbarSearch))

  useEffect(() => {
    if (typeof window === 'undefined') return
    setTopbarSearch(window.location.search || '')
    setSidebarOpen(false)
  }, [pathname])

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

  return <div className={`app-layout ${sidebarOpen ? 'sidebar-open' : ''}`}>
    <a className="skip-link" href="#main-content">Bỏ qua menu, tới nội dung chính</a>
    <button className="sidebar-scrim" type="button" aria-label="Đóng menu" onClick={() => setSidebarOpen(false)} />

    <aside className="sidebar" aria-label="Điều hướng chính">
      <Link href="/bank" className="brand" aria-label="Open edX AI Server">
        <div className="brand-mark">AI</div>
        <div><b>AI Server</b><small>Ngân hàng đề · Open edX</small></div>
      </Link>

      <nav className="side-nav grouped-side-nav">
        {navGroups.map((group) => {
          const items = visibleItems.filter((item) => item.group === group.key)
          if (!items.length) return null
          return <div className="nav-group" key={group.key}>
            <div className="nav-group-title">{group.label}</div>
            <div className="nav-group-items">
              {items.map((item) => {
                const active = pathname === item.href || pathname.startsWith(`${item.href}/`)
                return <Link key={item.href} href={item.href} className={active ? 'nav-link active' : 'nav-link'} aria-current={active ? 'page' : undefined}>
                  <span className="nav-icon" aria-hidden="true"><ShellIcon name={item.icon} /></span>
                  <span className="nav-text"><b>{item.label}</b><small>{item.desc}</small></span>
                </Link>
              })}
            </div>
          </div>
        })}
      </nav>

      <div className="sidebar-note">
        <span className={isAuthenticated ? 'session-dot ok' : 'session-dot wait'} />
        <div><b>{isAuthenticated ? 'Đã đăng nhập' : 'Đang lấy phiên CMS'}</b><span>{isAuthenticated ? `${userId || 'user'} · ${ROLE_LABELS[role]}` : (autoLoginMessage || 'AI Server sẽ tự nhận phiên từ CMS khi có thể.')}</span></div>
        <button className="btn small secondary" type="button" onClick={loginWithCms}>{isAuthenticated ? 'Làm mới phiên' : 'Đăng nhập CMS'}</button>
      </div>
    </aside>

    <div className="main-area">
      <header className="workspace-topbar">
        <button className="mobile-menu-button" type="button" onClick={() => setSidebarOpen(true)} aria-label="Mở menu">☰</button>
        <div className="workspace-topbar-main">
          <span className="eyebrow">AI Server</span>
          <h1>{currentTitle}</h1>
          <p>{currentSubtitle}</p>
          {studentTopbar && <nav className="workspace-breadcrumb" aria-label="Điều hướng Quản lý sinh viên">
            {studentTopbar.map((item, index) => <span key={`${item.label}-${index}`} className="workspace-breadcrumb-item">
              {index > 0 && <span className="workspace-breadcrumb-separator">/</span>}
              {item.href ? <Link href={item.href}>{item.label}</Link> : <b>{item.label}</b>}
            </span>)}
          </nav>}
        </div>
        <div className="workspace-topbar-actions">
          <span className={isAuthenticated ? 'topbar-session ok' : 'topbar-session'}>{isAuthenticated ? 'Live' : 'Đang xác thực'}</span>
          <button
            type="button"
            className="theme-toggle-button"
            onClick={toggleTheme}
            aria-label={theme === 'dark' ? 'Chuyển sang giao diện sáng' : 'Chuyển sang giao diện tối'}
            title={theme === 'dark' ? 'Chuyển sang giao diện sáng' : 'Chuyển sang giao diện tối'}
          >
            <span aria-hidden="true">{theme === 'dark' ? '☀' : '☾'}</span>
            <b>{theme === 'dark' ? 'Sáng' : 'Tối'}</b>
          </button>
        </div>
      </header>

      <main id="main-content" className="content-shell" tabIndex={-1}>{children}</main>
      <AppFooter />
    </div>
  </div>
}
