'use client'

import Link from 'next/link'
import { usePathname, useRouter } from 'next/navigation'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useAppContext } from '../../context/AppContext'
import { buildCmsSessionBridgeUrl } from '../../lib/api'
import { SHOW_DIAGNOSTICS_UI } from '../../lib/runtime'
import { ROLE_LABELS } from '../../types'
import { AppIcon, type AppIconName } from '../icons/AppIcon'
import { PageShellProvider, type PageChrome } from './PageShellContext'
import { VisualIcon } from '../ui/VisualIcon'

type NavGroupKey = 'overview' | 'bank' | 'training' | 'operations' | 'catalog' | 'admin'

type NavItem = {
  href: string
  label: string
  icon: AppIconName
  group: NavGroupKey
  permission?: string
  diagnostic?: boolean
}

const SIDEBAR_STORAGE_KEY = 'ai-shell-sidebar'
const GROUP_STORAGE_KEY = 'ai-shell-nav-groups'

const navGroups: Array<{ key: NavGroupKey; label: string }> = [
  { key: 'overview', label: 'Tổng quan' },
  { key: 'bank', label: 'Ngân hàng đề' },
  { key: 'training', label: 'Vận hành đào tạo' },
  { key: 'operations', label: 'Vận hành hệ thống' },
  { key: 'catalog', label: 'Danh mục' },
  { key: 'admin', label: 'Quản trị' },
]

const navItems: NavItem[] = [
  { href: '/bank', label: 'Tổng quan', icon: 'dashboard', group: 'overview', permission: 'view_questions' },
  { href: '/bank/departments', label: 'Ngân hàng đề', icon: 'bank', group: 'bank', permission: 'view_questions' },
  { href: '/bank/search', label: 'Tìm kiếm câu hỏi', icon: 'search', group: 'bank', permission: 'view_questions' },
  { href: '/bank/quiz', label: 'Tạo Quiz', icon: 'quiz', group: 'bank', permission: 'publish_questions' },
  { href: '/bank/history', label: 'Lịch sử Quiz', icon: 'release', group: 'bank', permission: 'publish_questions' },
  { href: '/student-management', label: 'Quản lý sinh viên', icon: 'students', group: 'training', permission: 'view_training_reports' },
  { href: '/teacher-management', label: 'Quản lý giảng viên', icon: 'teachers', group: 'training', permission: 'view_training_reports' },
  { href: '/analytics/learning', label: 'Phân tích học tập', icon: 'analytics', group: 'training', permission: 'view_training_reports' },
  { href: '/jobs', label: 'Tác vụ nền', icon: 'jobs', group: 'operations', permission: 'view_jobs' },
  { href: '/audit', label: 'Nhật ký hoạt động', icon: 'audit', group: 'operations', permission: 'view_jobs' },
  { href: '/ap-sync', label: 'Đồng bộ AP', icon: 'sync', group: 'operations', permission: 'manage_training_deadlines' },
  { href: '/ops/readiness', label: 'Kiểm tra vận hành', icon: 'readiness', group: 'operations', permission: 'view_ops_readiness', diagnostic: true },
  { href: '/premises', label: 'Cơ sở', icon: 'campus', group: 'catalog', permission: 'manage_training_deadlines' },
  { href: '/semesters', label: 'Học kỳ', icon: 'semester', group: 'catalog', permission: 'manage_settings' },
  { href: '/users', label: 'Người dùng & phân quyền', icon: 'users', group: 'admin', permission: 'view_rbac' },
  { href: '/settings', label: 'Cài đặt', icon: 'settings', group: 'admin', permission: 'manage_settings' },
]

function isPathActive(pathname: string, href: string) {
  return pathname === href || pathname.startsWith(`${href}/`)
}

function requiredPermissionForPath(pathname: string): string | null {
  const rules: Array<[RegExp, string]> = [
    [/^\/bank\/(?:quiz|history)(?:\/|$)/, 'publish_questions'],
    [/^\/bank(?:\/|$)/, 'view_questions'],
    [/^\/(?:question-bank|review|generate|workflow)(?:\/|$)/, 'view_questions'],
    [/^\/export(?:\/|$)/, 'publish_questions'],
    [/^\/(?:student-management|teacher-management|training-management|analytics)(?:\/|$)/, 'view_training_reports'],
    [/^\/premises(?:\/|$)/, 'manage_training_deadlines'],
    [/^\/semesters(?:\/|$)/, 'manage_settings'],
    [/^\/ap-sync(?:\/|$)/, 'manage_training_deadlines'],
    [/^\/ops\/readiness(?:\/|$)/, 'view_ops_readiness'],
    [/^\/(?:jobs|audit)(?:\/|$)/, 'view_jobs'],
    [/^\/users(?:\/|$)/, 'view_rbac'],
    [/^\/settings(?:\/|$)/, 'manage_settings'],
  ]
  return rules.find(([pattern]) => pattern.test(pathname))?.[1] || null
}

function pageLabel(pathname: string) {
  const exact = navItems.find((item) => pathname === item.href)
  if (exact) return exact.label
  return navItems
    .filter((item) => isPathActive(pathname, item.href))
    .sort((a, b) => b.href.length - a.href.length)[0]?.label || 'AI Server'
}

function fallbackPageLayoutClass(pathname: string) {
  const classes = ['page-stack']
  if (pathname.startsWith('/bank')) classes.push('bank-multipage')
  if (pathname === '/bank') classes.push('dashboard-modern-page')
  if (pathname.startsWith('/bank/quiz')) classes.push('bank-quiz-page', 'quiz-creation-workbench')
  if (pathname.startsWith('/bank/search')) classes.push('dashboard-search-page')
  if (pathname.startsWith('/student-management')) classes.push('student-management-page', 'academic-flow-page', 'training-operations-page')
  if (pathname.startsWith('/teacher-management')) classes.push('training-management-page', 'teacher-management-page', 'training-operations-page')
  if (pathname.startsWith('/analytics')) classes.push('learning-analytics-page', 'academic-flow-page', 'training-operations-page')
  if (pathname.startsWith('/jobs')) classes.push('ops-console', 'jobs-console', 'ux-enterprise-page')
  if (pathname.startsWith('/audit')) classes.push('ops-console', 'audit-console', 'ux-enterprise-page')
  if (pathname.startsWith('/ap-sync')) classes.push('ap-sync-page')
  if (pathname.startsWith('/premises')) classes.push('premises-page')
  if (pathname.startsWith('/semesters')) classes.push('semesters-page')
  if (pathname.startsWith('/settings')) classes.push('settings-page')
  if (pathname.startsWith('/users')) classes.push('access-console', 'access-console-v2')
  return classes.join(' ')
}

function loadGroupPreference(): Record<NavGroupKey, boolean> {
  const defaults = Object.fromEntries(navGroups.map((group) => [group.key, true])) as Record<NavGroupKey, boolean>
  try {
    const parsed = JSON.parse(window.localStorage.getItem(GROUP_STORAGE_KEY) || '{}') as Partial<Record<NavGroupKey, boolean>>
    return { ...defaults, ...parsed }
  } catch {
    return defaults
  }
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname()
  const router = useRouter()
  const drawerRef = useRef<HTMLElement>(null)
  const menuButtonRef = useRef<HTMLButtonElement>(null)
  const userMenuRef = useRef<HTMLDetailsElement>(null)
  const layoutRegistrationRef = useRef<string | null>(null)
  const [collapsed, setCollapsed] = useState(true)
  const [mobile, setMobile] = useState(false)
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [openGroups, setOpenGroups] = useState<Record<NavGroupKey, boolean>>(() => Object.fromEntries(navGroups.map((group) => [group.key, true])) as Record<NavGroupKey, boolean>)
  const [pageChrome, setPageChrome] = useState<PageChrome | null>(null)
  const [pageLayoutClass, setPageLayoutClass] = useState(() => fallbackPageLayoutClass(pathname))
  const { courseId, role, userId, can, isAuthenticated, authReady } = useAppContext()

  const registerChrome = useCallback((value: PageChrome) => {
    setPageChrome(value)
    return () => setPageChrome((current) => current?.registrationId === value.registrationId ? null : current)
  }, [])

  const registerLayout = useCallback((registrationId: string, className: string) => {
    layoutRegistrationRef.current = registrationId
    setPageLayoutClass(className)
    return () => {
      if (layoutRegistrationRef.current !== registrationId) return
      layoutRegistrationRef.current = null
      setPageLayoutClass(fallbackPageLayoutClass(pathname))
    }
  }, [pathname])

  const pageShellRegistration = useMemo(() => ({ registerChrome, registerLayout }), [registerChrome, registerLayout])

  const availableItems = useMemo(() => navItems.filter((item) => !item.diagnostic || SHOW_DIAGNOSTICS_UI), [])
  const visibleItems = useMemo(() => authReady ? availableItems.filter((item) => !item.permission || can(item.permission)) : [], [authReady, availableItems, can])
  const currentGroup = useMemo(() => availableItems.find((item) => isPathActive(pathname, item.href))?.group, [availableItems, pathname])
  const routePermission = requiredPermissionForPath(pathname)
  const diagnosticsRouteBlocked = pathname.startsWith('/ops/readiness') && !SHOW_DIAGNOSTICS_UI
  const routeAllowed = !diagnosticsRouteBlocked && (!routePermission || (authReady && can(routePermission)))
  const fallbackHref = visibleItems[0]?.href || '/bank'

  useEffect(() => {
    const media = window.matchMedia('(max-width: 767px)')
    const updateMobile = () => setMobile(media.matches)
    updateMobile()
    if (typeof media.addEventListener === 'function') media.addEventListener('change', updateMobile)
    else media.addListener(updateMobile)
    const sidebarPreference = window.localStorage.getItem(SIDEBAR_STORAGE_KEY)
    const nextCollapsed = sidebarPreference ? sidebarPreference !== 'expanded' : true
    setCollapsed(nextCollapsed)
    document.documentElement.dataset.sidebar = nextCollapsed ? 'collapsed' : 'expanded'
    setOpenGroups(loadGroupPreference())
    document.documentElement.dataset.theme = 'light'
    document.documentElement.dataset.aiTheme = 'light'
    return () => {
      if (typeof media.removeEventListener === 'function') media.removeEventListener('change', updateMobile)
      else media.removeListener(updateMobile)
    }
  }, [])

  useEffect(() => {
    if (!currentGroup) return
    setOpenGroups((current) => current[currentGroup] ? current : { ...current, [currentGroup]: true })
  }, [currentGroup])

  useEffect(() => {
    setDrawerOpen(false)
  }, [pathname])

  useEffect(() => {
    document.documentElement.dataset.mobileNav = drawerOpen ? 'open' : 'closed'
    const drawer = drawerRef.current
    if (drawer) {
      const shouldDisable = mobile && !drawerOpen
      if ('inert' in drawer) drawer.inert = shouldDisable
      drawer.toggleAttribute('inert', shouldDisable)
      const controls = drawer.querySelectorAll<HTMLElement>('a[href], button, summary, input, select, textarea, [tabindex]')
      controls.forEach((control) => {
        if (shouldDisable) {
          if (!control.hasAttribute('data-shell-tabindex')) control.setAttribute('data-shell-tabindex', control.getAttribute('tabindex') ?? '')
          control.setAttribute('tabindex', '-1')
        } else if (control.hasAttribute('data-shell-tabindex')) {
          const previous = control.getAttribute('data-shell-tabindex') || ''
          if (previous) control.setAttribute('tabindex', previous)
          else control.removeAttribute('tabindex')
          control.removeAttribute('data-shell-tabindex')
        }
      })
    }
    document.body.style.overflow = drawerOpen && mobile ? 'hidden' : ''
    if (!drawerOpen || !mobile) return () => { document.body.style.overflow = '' }
    const focusable = drawer?.querySelectorAll<HTMLElement>('a[href], button:not([disabled]), summary, input, select, textarea, [tabindex]:not([tabindex="-1"])')
    const first = focusable?.[0]
    const last = focusable?.[focusable.length - 1]
    first?.focus()
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault()
        setDrawerOpen(false)
        menuButtonRef.current?.focus()
        return
      }
      if (event.key !== 'Tab' || !first || !last) return
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault()
        last.focus()
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault()
        first.focus()
      }
    }
    document.addEventListener('keydown', onKeyDown)
    return () => {
      document.removeEventListener('keydown', onKeyDown)
      document.body.style.overflow = ''
    }
  }, [drawerOpen, mobile])

  useEffect(() => {
    const details = userMenuRef.current
    if (!details) return undefined
    const close = (event: Event) => {
      if (event instanceof KeyboardEvent && event.key !== 'Escape') return
      if (event instanceof MouseEvent && details.contains(event.target as Node)) return
      details.open = false
    }
    document.addEventListener('keydown', close)
    document.addEventListener('pointerdown', close)
    return () => {
      document.removeEventListener('keydown', close)
      document.removeEventListener('pointerdown', close)
    }
  }, [])

  useEffect(() => {
    if (!authReady || routeAllowed || pathname.startsWith('/auth/')) return
    if (fallbackHref !== pathname) router.replace(fallbackHref)
  }, [authReady, fallbackHref, pathname, routeAllowed, router])

  useEffect(() => {
    if (!authReady || isAuthenticated || pathname.startsWith('/auth/cms-callback')) return
    const enabled = (process.env.NEXT_PUBLIC_AUTO_CMS_SESSION_LOGIN || 'true').toLowerCase() !== 'false'
    if (!enabled) return
    const startedAt = Number(window.sessionStorage.getItem('ai_openedx_cms_bridge_started_at') || 0)
    const now = Date.now()
    if (startedAt && now - startedAt < 30000) {
      return
    }
    try {
      window.sessionStorage.setItem('ai_openedx_cms_bridge_started_at', String(now))
      window.location.href = buildCmsSessionBridgeUrl(courseId)
    } catch (error) {
      console.error('Không tạo được liên kết CMS', error)
    }
  }, [authReady, courseId, isAuthenticated, pathname])

  const toggleSidebar = () => {
    if (mobile) {
      setDrawerOpen((value) => !value)
      return
    }
    const next = !collapsed
    setCollapsed(next)
    document.documentElement.dataset.sidebar = next ? 'collapsed' : 'expanded'
    window.localStorage.setItem(SIDEBAR_STORAGE_KEY, next ? 'collapsed' : 'expanded')
  }

  const toggleGroup = (key: NavGroupKey) => {
    if (currentGroup === key) return
    setOpenGroups((current) => {
      const next = { ...current, [key]: !current[key] }
      window.localStorage.setItem(GROUP_STORAGE_KEY, JSON.stringify(next))
      return next
    })
  }

  const reconnectCms = () => {
    try {
      window.location.href = buildCmsSessionBridgeUrl(courseId)
    } catch (error) {
      window.alert(error instanceof Error ? error.message : 'Không tạo được liên kết CMS')
    }
  }

  const guardedChildren = routeAllowed ? children : <section className="card empty-state permission-hidden-state">
    <h2>{authReady ? 'Bạn không có quyền truy cập chức năng này' : 'Đang kiểm tra quyền truy cập'}</h2>
    <p>{authReady ? 'Hệ thống đang chuyển về màn hình phù hợp với phạm vi được phân công.' : 'Vui lòng chờ trong khi hệ thống xác định quyền từ phiên CMS.'}</p>
  </section>

  return <PageShellProvider value={pageShellRegistration}><div className="enterprise-app-shell">
    <a className="skip-link" href="#main-content">Bỏ qua điều hướng</a>
    {drawerOpen && mobile && <button className="enterprise-sidebar-overlay" aria-label="Đóng menu" type="button" onClick={() => setDrawerOpen(false)} />}

    <aside ref={drawerRef} className={`enterprise-sidebar${drawerOpen ? ' mobile-open' : ''}`} aria-label="Điều hướng chính" aria-hidden={mobile && !drawerOpen ? true : undefined} role={mobile ? 'dialog' : undefined} aria-modal={mobile && drawerOpen ? true : undefined}>
      <div className="enterprise-sidebar-header">
        <Link href="/bank" className="enterprise-brand" aria-label="AI Server ACMS">
          <span className="enterprise-brand-mark">AI</span>
          <span className="enterprise-brand-copy"><b>AI Server ACMS</b></span>
        </Link>
        {mobile && <button className="enterprise-icon-button sidebar-mobile-close" type="button" aria-label="Đóng menu" onClick={() => setDrawerOpen(false)}><AppIcon name="close" /></button>}
      </div>

      <nav className="enterprise-navigation" aria-label="Chức năng hệ thống">
        {!authReady && <div className="enterprise-nav-skeleton" aria-label="Đang tải quyền"><span/><span/><span/><span/></div>}
        {navGroups.map((group) => {
          const items = visibleItems.filter((item) => item.group === group.key)
          if (!items.length) return null
          const activeGroup = group.key === currentGroup
          const expanded = activeGroup || openGroups[group.key] || collapsed
          return <section className={`enterprise-nav-group${activeGroup ? ' active-group' : ''}`} key={group.key}>
            <button className="enterprise-nav-group-toggle" type="button" aria-expanded={expanded} onClick={() => toggleGroup(group.key)} disabled={collapsed || activeGroup}>
              <span>{group.label}</span><AppIcon name="chevron-down" size={14}/>
            </button>
            {expanded && <div className="enterprise-nav-items">
              {items.map((item) => {
                const active = isPathActive(pathname, item.href)
                return <Link
                  key={item.href}
                  href={item.href}
                  className={`enterprise-nav-link${active ? ' active' : ''}`}
                  aria-current={active ? 'page' : undefined}
                  data-tooltip={item.label}
                >
                  <span className="enterprise-nav-icon"><AppIcon name={item.icon}/></span>
                  <span className="enterprise-nav-copy"><b>{item.label}</b></span>
                </Link>
              })}
            </div>}
          </section>
        })}
      </nav>

    </aside>

    <div className="enterprise-workspace">
      <header className="enterprise-topbar">
        <div className="enterprise-topbar-start">
          <button ref={menuButtonRef} className="enterprise-icon-button" type="button" aria-label={mobile ? 'Mở menu' : collapsed ? 'Mở rộng sidebar' : 'Thu gọn sidebar'} aria-expanded={mobile ? drawerOpen : !collapsed} onClick={toggleSidebar}>
            <AppIcon name={mobile ? 'menu' : collapsed ? 'panel-left-open' : 'panel-left-close'} />
          </button>
          <div className="enterprise-topbar-page-heading" aria-live="polite">
            {pageChrome?.icon ? <VisualIcon label={pageChrome.title} icon={pageChrome.icon} tone={pageChrome.tone} size={17} className="enterprise-topbar-page-icon" /> : null}
            <span className="enterprise-topbar-page-copy">
              {pageChrome?.eyebrow ? <small>{pageChrome.eyebrow}</small> : null}
              <h1>{pageChrome?.title || pageLabel(pathname)}</h1>
            </span>
          </div>
        </div>
        <div className="enterprise-topbar-end">
          <span className={`enterprise-cms-pill ${isAuthenticated ? 'ok' : 'wait'}`} role="status" aria-live="polite"><span aria-hidden="true" />{isAuthenticated ? 'CMS OK' : 'Đang kết nối'}</span>
          <details ref={userMenuRef} className="enterprise-user-menu">
            <summary aria-label="Mở menu tài khoản">
              <span className="enterprise-avatar">{String(userId || 'U').slice(0, 2).toUpperCase()}</span>
              <span className="enterprise-user-summary"><b>{ROLE_LABELS[role]}</b></span>
              <AppIcon name="chevron-down" size={14}/>
            </summary>
            <div className="enterprise-user-popover">
              <div className="enterprise-user-popover-head"><AppIcon name="user"/><span><b>{userId || 'Người dùng'}</b><small>{ROLE_LABELS[role]}</small></span></div>
              <button type="button" onClick={reconnectCms}><AppIcon name="sync"/> Kết nối lại CMS</button>
            </div>
          </details>
        </div>
      </header>

      <main id="main-content" className={`enterprise-content ${pageLayoutClass}`.trim()} tabIndex={-1}>{guardedChildren}</main>
    </div>
  </div></PageShellProvider>
}
