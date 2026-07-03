'use client'

import { useEffect, useMemo, useState } from 'react'
import Link from 'next/link'
import { usePathname, useRouter } from 'next/navigation'
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
  { href: '/bank', label: 'Tổng quan', desc: 'Số liệu & việc cần xử lý', icon: '⌁', group: 'work', permission: 'view_questions' },
  { href: '/bank/departments', label: 'Ngân hàng đề', desc: 'Bộ môn, môn, phiên bản', icon: '▦', group: 'work', permission: 'view_questions' },
  { href: '/bank/quiz', label: 'Tạo Quiz', desc: 'Đưa bài kiểm tra lên CMS', icon: '◈', group: 'work', permission: 'publish_questions' },
  { href: '/bank/history', label: 'Lịch sử Quiz', desc: 'Đã tạo & khôi phục', icon: '◷', group: 'work', permission: 'publish_questions' },
  { href: '/premises', label: 'Cơ sở', desc: 'Premises AP', icon: '▣', group: 'operations', permission: 'manage_training_deadlines' },
  { href: '/semesters', label: 'Học kỳ', desc: 'Term & Block AP', icon: '◫', group: 'operations', permission: 'manage_settings' },
  { href: '/ap-sync', label: 'Đồng bộ AP', desc: 'Theo kỳ, theo hệ', icon: '⇄', group: 'operations', permission: 'manage_training_deadlines' },
  { href: '/student-management', label: 'Sinh viên & lớp', desc: 'Danh sách AP, đồng bộ CMS', icon: '◎', group: 'operations', permission: 'view_training_reports' },
  { href: '/teacher-management', label: 'Quản lý giảng viên', desc: 'GV, lớp, tiến độ', icon: '▤', group: 'operations', permission: 'view_training_reports' },
  { href: '/analytics/learning', label: 'Học online', desc: 'Tín hiệu học theo log', icon: '◌', group: 'operations', permission: 'view_dashboard' },
  { href: '/jobs', label: 'Tiến trình', desc: 'Việc đang xử lý', icon: '⚙', group: 'operations', permission: 'view_jobs' },
  { href: '/audit', label: 'Nhật ký', desc: 'Lịch sử thao tác', icon: '☷', group: 'operations', permission: 'view_jobs' },
  { href: '/users', label: 'Phân quyền', desc: 'Gán quyền theo phạm vi', icon: '◎', group: 'admin', permission: 'manage_settings' },
  { href: '/settings', label: 'Cấu hình', desc: 'Chính sách hệ thống', icon: '◇', group: 'admin', permission: 'manage_settings' },
]

const navGroups: Array<{ key: NavItem['group']; label: string }> = [
  { key: 'work', label: 'Công việc chính' },
  { key: 'operations', label: 'Vận hành' },
  { key: 'admin', label: 'Quản trị' },
]


function requiredPermissionForPath(pathname: string): string | null {
  const rules: Array<[RegExp, string]> = [
    [/^\/bank\/quiz(?:\/|$)/, 'publish_questions'],
    [/^\/bank\/history(?:\/|$)/, 'publish_questions'],
    [/^\/bank(?:\/|$)/, 'view_questions'],
    [/^\/question-bank(?:\/|$)/, 'view_questions'],
    [/^\/review(?:\/|$)/, 'review_questions'],
    [/^\/generate(?:\/|$)/, 'generate_questions'],
    [/^\/export(?:\/|$)/, 'export_questions'],
    [/^\/workflow(?:\/|$)/, 'view_questions'],
    [/^\/sync(?:\/|$)/, 'sync_course'],
    [/^\/dashboard(?:\/|$)/, 'view_dashboard'],
    [/^\/premises(?:\/|$)/, 'manage_training_deadlines'],
    [/^\/semesters(?:\/|$)/, 'manage_settings'],
    [/^\/ap-sync(?:\/|$)/, 'manage_training_deadlines'],
    [/^\/student-management(?:\/|$)/, 'view_training_reports'],
    [/^\/analytics(?:\/|$)/, 'view_dashboard'],
    [/^\/teacher-management(?:\/|$)/, 'view_training_reports'],
    [/^\/training-management(?:\/|$)/, 'view_training_reports'],
    [/^\/jobs(?:\/|$)/, 'view_jobs'],
    [/^\/audit(?:\/|$)/, 'view_jobs'],
    [/^\/users(?:\/|$)/, 'manage_settings'],
    [/^\/settings(?:\/|$)/, 'manage_settings'],
  ]
  return rules.find(([pattern]) => pattern.test(pathname))?.[1] || null
}

function pageTitle(pathname: string) {
  const exact = navItems.find((item) => pathname === item.href)
  if (exact) return exact.label
  const nested = navItems
    .filter((item) => pathname.startsWith(`${item.href}/`))
    .sort((a, b) => b.href.length - a.href.length)[0]
  return nested ? nested.label : 'AI Server'
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

  if (subjectIdMatch || classIdMatch) {
    items.push({
      label: subjectCode || 'Môn đã chọn',
      href: classIdMatch ? subjectHref : undefined,
    })
  }

  if (classIdMatch) {
    items.push({ label: 'Lớp' })
  }

  return items
}

function AppFooter() {
  const version = process.env.NEXT_PUBLIC_APP_VERSION || '25.9.16.7.2.26'
  return <footer className="app-footer app-footer-compact product-footer">
    <div><b>Open edX AI Server</b><span>Ngân hàng đề · Vận hành đào tạo · Open edX CMS</span></div>
    <div className="footer-links"><span>v{version}</span></div>
  </footer>
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname()
  const router = useRouter()
  const [topbarSearch, setTopbarSearch] = useState('')
  const {
    courseId,
    role,
    userId,
    can,
    isAuthenticated,
    authReady,
  } = useAppContext()
  const [autoLoginMessage, setAutoLoginMessage] = useState('')

  const visibleItems = useMemo(() => authReady ? navItems.filter((item) => !item.permission || can(item.permission)) : [], [authReady, can])
  const currentTitle = pageTitle(pathname)
  const currentNavItem = useMemo(() => {
    const exact = navItems.find((item) => pathname === item.href)
    if (exact) return exact
    return navItems
      .filter((item) => pathname.startsWith(`${item.href}/`))
      .sort((a, b) => b.href.length - a.href.length)[0]
  }, [pathname])
  const routePermission = requiredPermissionForPath(pathname)
  const routeAllowed = !routePermission || (authReady && can(routePermission))
  const fallbackHref = visibleItems[0]?.href || '/bank'
  const studentTopbar = buildStudentManagementTopbar(pathname, new URLSearchParams(topbarSearch))

  useEffect(() => {
    if (typeof window === 'undefined') return
    setTopbarSearch(window.location.search || '')
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

  useEffect(() => {
    if (!authReady) return
    if (routeAllowed) return
    if (pathname.startsWith('/auth/')) return
    if (fallbackHref && fallbackHref !== pathname) router.replace(fallbackHref)
  }, [authReady, fallbackHref, pathname, routeAllowed, router])

  const guardedChildren = routeAllowed ? children : <section className="card empty-state permission-hidden-state">
    <h2>{authReady ? 'Không có chức năng phù hợp với quyền hiện tại' : 'Đang kiểm tra quyền truy cập'}</h2>
    <p>{authReady ? 'Hệ thống đã ẩn chức năng này và đang chuyển về màn bạn được phép sử dụng.' : 'Các chức năng sẽ chỉ hiện sau khi hệ thống xác định đúng quyền ACMS/AI Server của tài khoản.'}</p>
  </section>

  return <div className="app-layout product-shell">
    <a className="skip-link" href="#main-content">Bỏ qua menu, tới nội dung chính</a>
    <aside className="sidebar product-sidebar" aria-label="Điều hướng chính">
      <Link href="/bank" className="brand product-brand" aria-label="Open edX AI Server">
        <div className="brand-mark product-brand-mark">AI</div>
        <div><b>AI Server ACMS</b><small>Question Bank · Training Ops</small></div>
      </Link>

      <nav className="side-nav grouped-side-nav product-nav">
        {!authReady && <div className="nav-loading-stack" aria-label="Đang tải quyền">
          <span /><span /><span /><span />
        </div>}
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

      <div className="sidebar-note product-session-card product-session-card-compact">
        <span className={isAuthenticated ? 'session-dot ok' : 'session-dot wait'} />
        <div><b>{isAuthenticated ? 'CMS OK' : 'Chờ CMS'}</b><span>{isAuthenticated ? (userId || 'user') : (autoLoginMessage || 'Đang lấy phiên')}</span></div>
        <button className="btn small secondary" type="button" onClick={loginWithCms}>{isAuthenticated ? 'Kết nối lại CMS' : 'Đăng nhập CMS'}</button>
      </div>
    </aside>

    <div className="main-area product-main">
      <header className={studentTopbar ? 'workspace-topbar workspace-topbar-minimal workspace-student-management-topbar product-command-topbar' : 'workspace-topbar workspace-topbar-minimal product-command-topbar'}>
        <div className="workspace-topbar-main product-topbar-copy">
          <h1>{currentTitle}</h1>
          {studentTopbar && <nav className="workspace-breadcrumb" aria-label="Điều hướng Quản lý sinh viên">
            {studentTopbar.map((item, index) => <span key={`${item.label}-${index}`} className="workspace-breadcrumb-item">
              {index > 0 && <span className="workspace-breadcrumb-separator">/</span>}
              {item.href ? <Link href={item.href}>{item.label}</Link> : <b>{item.label}</b>}
            </span>)}
          </nav>}
        </div>
        <div className="product-topbar-meta" aria-label="Thông tin phiên làm việc">
          <span className={isAuthenticated ? 'topbar-session-pill ok' : 'topbar-session-pill wait'}>{isAuthenticated ? 'CMS OK' : 'Chờ CMS'}</span>
          <span className="topbar-role-pill">{ROLE_LABELS[role]}</span>
        </div>
      </header>

      <main id="main-content" className="content-shell compact-content-shell product-content" tabIndex={-1}>{guardedChildren}</main>
      <AppFooter />
    </div>
  </div>
}
