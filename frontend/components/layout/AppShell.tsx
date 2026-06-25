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
  { href: '/bank', label: 'Tổng quan', desc: 'Số liệu & việc cần xử lý', icon: '⌁', group: 'work' },
  { href: '/bank/departments', label: 'Ngân hàng đề', desc: 'Bộ môn, môn, phiên bản', icon: '▦', group: 'work' },
  { href: '/bank/quiz', label: 'Tạo Quiz', desc: 'Đưa bài kiểm tra lên CMS', icon: '◈', group: 'work' },
  { href: '/bank/history', label: 'Lịch sử Quiz', desc: 'Đã tạo & khôi phục', icon: '◷', group: 'work' },
  { href: '/premises', label: 'Cơ sở', desc: 'Premises AP', icon: '▣', group: 'operations', permission: 'manage_settings' },
  { href: '/semesters', label: 'Học kỳ', desc: 'Term & Block AP', icon: '◫', group: 'operations', permission: 'manage_settings' },
  { href: '/ap-sync', label: 'Đồng bộ AP', desc: 'Theo kỳ, theo hệ', icon: '⇄', group: 'operations', permission: 'manage_settings' },
  { href: '/student-management', label: 'Sinh viên & lớp', desc: 'Danh sách AP, đồng bộ CMS', icon: '◎', group: 'operations' },
  { href: '/jobs', label: 'Tiến trình', desc: 'Việc đang xử lý', icon: '⚙', group: 'operations' },
  { href: '/audit', label: 'Nhật ký', desc: 'Lịch sử thao tác', icon: '☷', group: 'operations' },
  { href: '/users', label: 'Phân quyền', desc: 'Gán quyền theo phạm vi', icon: '◎', group: 'admin', permission: 'view_questions' },
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
  return <footer className="app-footer app-footer-compact product-footer">
    <div><b>Open edX AI Server</b><span>Ngân hàng đề · Quản lý AP · Quiz trên CMS</span></div>
    <div className="footer-links"><span>v25.9.16.5.29</span></div>
  </footer>
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname()
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

  const visibleItems = useMemo(() => navItems.filter((item) => !item.permission || can(item.permission)), [can])
  const currentTitle = pageTitle(pathname)
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

  return <div className="app-layout product-shell">
    <a className="skip-link" href="#main-content">Bỏ qua menu, tới nội dung chính</a>
    <aside className="sidebar product-sidebar" aria-label="Điều hướng chính">
      <Link href="/bank" className="brand product-brand" aria-label="Open edX AI Server">
        <div className="brand-mark product-brand-mark">AI</div>
        <div><b>AI Server</b><small>Ngân hàng đề · Open edX</small></div>
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
        <span className={isAuthenticated ? 'session-dot ok' : 'session-dot wait'} />
        <div><b>{isAuthenticated ? 'Đã đăng nhập' : 'Đang lấy phiên CMS'}</b><span>{isAuthenticated ? `${userId || 'user'} · ${ROLE_LABELS[role]}` : (autoLoginMessage || 'AI Server sẽ tự nhận phiên từ CMS khi có thể.')}</span></div>
        <button className="btn small secondary" type="button" onClick={loginWithCms}>{isAuthenticated ? 'Làm mới' : 'Đăng nhập CMS'}</button>
      </div>
    </aside>

    <div className="main-area product-main">
      <header className={studentTopbar ? 'workspace-topbar workspace-topbar-minimal workspace-student-management-topbar' : 'workspace-topbar workspace-topbar-minimal'}>
        <div className="workspace-topbar-main">
          <h1>{currentTitle}</h1>
          {studentTopbar && <nav className="workspace-breadcrumb" aria-label="Điều hướng Quản lý sinh viên">
            {studentTopbar.map((item, index) => <span key={`${item.label}-${index}`} className="workspace-breadcrumb-item">
              {index > 0 && <span className="workspace-breadcrumb-separator">/</span>}
              {item.href ? <Link href={item.href}>{item.label}</Link> : <b>{item.label}</b>}
            </span>)}
          </nav>}
        </div>
      </header>

      <main id="main-content" className="content-shell compact-content-shell product-content" tabIndex={-1}>{children}</main>
      <AppFooter />
    </div>
  </div>
}
