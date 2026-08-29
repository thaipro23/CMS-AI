'use client'

import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react'
import { Permission, Role, ROLE_PERMISSIONS } from '../types'
import { API, apiFetch } from '../lib/api'

type AppContextValue = {
  authReady: boolean
  isAuthenticated: boolean
  courseId: string
  setCourseId: (value: string) => void
  role: Role
  setRole: (value: Role) => void
  userId: string
  setUserId: (value: string) => void
  accessToken: string
  setAccessToken: (value: string) => void
  businessPermissions: string[]
  isSystemAdmin: boolean
  assignments: EffectiveAssignment[]
  applyAuthSession: (session: { access_token?: string; user_id: string; role: Role; email?: string | null; course_ids?: string[] }) => void
  refreshAuthSession: (sessionToken?: string) => Promise<boolean>
  clearAuthSession: () => void
  can: (permission: Permission | string) => boolean
  canScope: (permission: Permission | string, target: ScopeTarget) => boolean
  authHeaders: (json?: boolean) => HeadersInit
}

type ScopeType = 'SYSTEM' | 'DEPARTMENT' | 'SUBJECT' | 'SUBJECT_VERSION' | 'CHAPTER' | 'CAMPUS' | 'CLASS' | 'COURSE' | 'BANK_VERSION' | 'RELEASE'

type ScopeTarget = {
  scopeType: ScopeType
  scopeId?: string
  departmentId?: string
  subjectId?: string
  subjectOfferingId?: string
  chapterId?: string
  campus?: string
  classId?: string
  courseId?: string
}

type EffectiveAssignment = {
  role_code: string
  scope_type: ScopeType | string
  scope_id: string
  permission_codes?: string[]
}

const AppContext = createContext<AppContextValue | null>(null)

const STORAGE_KEYS = {
  courseId: 'ai_openedx_course_id',
  role: 'ai_openedx_role',
  userId: 'ai_openedx_user_id',
  sessionToken: 'ai_openedx_session_token',
}

const IS_PRODUCTION = process.env.NEXT_PUBLIC_APP_ENV === 'production' || process.env.NODE_ENV === 'production'

const LEGACY_PERMISSION_BRIDGE: Record<string, string[]> = {
  view_dashboard: ['bank.view', 'audit.view'],
  view_questions: ['bank.view', 'question.edit', 'question.approve', 'question.reject'],
  view_jobs: ['jobs.view'],
  view_ops_readiness: ['ops.readiness.view'],
  view_rbac: ['rbac.view', 'user.manage_all', 'subject.assign_owner', 'reviewer.assign'],
  sync_course: ['course.sync'],
  estimate_cost: ['question.generate', 'document.manage', 'bank.view'],
  generate_questions: ['question.generate'],
  edit_questions: ['subject.update', 'document.manage', 'question.edit'],
  delete_questions: ['question.edit'],
  review_questions: ['question.approve', 'question.reject'],
  publish_questions: ['bank.release.create', 'bank.release.publish', 'quiz.preview', 'quiz.create_openedx'],
  export_questions: ['bank.release.create', 'bank.release.publish'],
  publish_to_openedx: ['bank.release.publish', 'quiz.create_openedx'],
  manage_settings: ['user.manage_all', 'department.manage_all', 'department.assign_head'],
  manage_department: ['department.manage_all', 'department.update'],
  view_user_analytics: ['user.manage_all'],
  view_training_reports: ['academic.view', 'view_training_reports'],
  manage_training_deadlines: ['academic.manage_campus'],
}


function hasBusinessPermission(permission: Permission | string, businessPermissions: string[]) {
  if (businessPermissions.includes(permission)) return true
  const mapped = LEGACY_PERMISSION_BRIDGE[permission] || [permission]
  return mapped.some((item) => businessPermissions.includes(item))
}


function normalized(value?: string | null) {
  return String(value || '').trim().toLowerCase()
}

function assignmentCoversTarget(assignment: EffectiveAssignment, target: ScopeTarget) {
  const scopeType = String(assignment.scope_type || '').toUpperCase()
  const scopeId = normalized(assignment.scope_id)
  if (scopeType === 'SYSTEM' || scopeId === '*') return true
  if (scopeType === 'DEPARTMENT') return scopeId === normalized(target.departmentId || (target.scopeType === 'DEPARTMENT' ? target.scopeId : ''))
  if (scopeType === 'SUBJECT') return scopeId === normalized(target.subjectId || (target.scopeType === 'SUBJECT' ? target.scopeId : ''))
  if (scopeType === 'SUBJECT_VERSION') return scopeId === normalized(target.subjectOfferingId || (target.scopeType === 'SUBJECT_VERSION' ? target.scopeId : ''))
  if (scopeType === 'CHAPTER') return scopeId === normalized(target.chapterId || (target.scopeType === 'CHAPTER' ? target.scopeId : ''))
  if (scopeType === 'CAMPUS') return scopeId === normalized(target.campus || (target.scopeType === 'CAMPUS' ? target.scopeId : ''))
  if (scopeType === 'CLASS') return scopeId === normalized(target.classId || (target.scopeType === 'CLASS' ? target.scopeId : ''))
  if (scopeType === 'COURSE') return scopeId === normalized(target.courseId || (target.scopeType === 'COURSE' ? target.scopeId : ''))
  if (scopeType === 'BANK_VERSION') return scopeId === normalized(target.scopeType === 'BANK_VERSION' ? target.scopeId : '')
  if (scopeType === 'RELEASE') return scopeId === normalized(target.scopeType === 'RELEASE' ? target.scopeId : '')
  return false
}

function getStoredSession(): StoredSession | null {
  if (IS_PRODUCTION) return null
  if (typeof window === 'undefined') return null
  const raw = window.sessionStorage.getItem(STORAGE_KEYS.sessionToken)
  if (!raw) return null
  try {
    const session = JSON.parse(raw) as StoredSession
    return session.access_token ? session : null
  } catch {
    window.sessionStorage.removeItem(STORAGE_KEYS.sessionToken)
    return null
  }
}

type StoredSession = {
  access_token: string
  user_id?: string
  role?: Role
  email?: string | null
  course_ids?: string[]
}

type EffectiveSession = {
  user_id?: string
  effective_legacy_role?: Role | string
  role?: Role | string
  is_system_admin?: boolean
  permissions?: string[]
  business_permissions?: string[]
  assignments?: EffectiveAssignment[]
}

export function AppProvider({ children }: { children: React.ReactNode }) {
  // Keep the first client render identical to SSR. Browser-backed session and
  // preferences are hydrated in the effect below, preventing AppShell/nav
  // hydration errors when a local session already exists.
  const [courseId, setCourseIdState] = useState('')
  const [role, setRoleState] = useState<Role>(IS_PRODUCTION ? 'viewer' : 'teacher')
  const [userId, setUserIdState] = useState('')
  const [accessToken, setAccessTokenState] = useState('')
  const [businessPermissions, setBusinessPermissions] = useState<string[]>([])
  const [isSystemAdmin, setIsSystemAdmin] = useState(false)
  const [assignments, setAssignments] = useState<EffectiveAssignment[]>([])
  const [cookieAuthenticated, setCookieAuthenticated] = useState(false)
  const [clientReady, setClientReady] = useState(false)
  const [authReady, setAuthReady] = useState(false)
  const accessTokenRef = useRef('')
  const authRequestSequenceRef = useRef(0)

  const refreshAuthSession = useCallback(async (sessionToken?: string): Promise<boolean> => {
    const sequence = ++authRequestSequenceRef.current
    const token = String(sessionToken || accessTokenRef.current || getStoredSession()?.access_token || '').trim()
    if (!token && !IS_PRODUCTION) {
      if (sequence !== authRequestSequenceRef.current) return false
      setCookieAuthenticated(false)
      setBusinessPermissions([])
      setIsSystemAdmin(false)
      setAssignments([])
      setAuthReady(true)
      return false
    }

    setAuthReady(false)
    try {
      let response: Response | null = null
      // The callback exchange and the provider's first anonymous /rbac/me can
      // overlap. Retry one cookie bootstrap 401 briefly, while the sequence guard
      // prevents any older anonymous response from clearing the newer session.
      for (let attempt = 0; attempt < 2; attempt += 1) {
        response = await apiFetch(`${API}/rbac/me`, {
          headers: token ? { Authorization: `Bearer ${token}` } : {},
          credentials: 'include',
          timeoutMs: 20_000,
          retries: 1,
          skipAuthExpiredEvent: true,
          cache: 'no-store',
        })
        if (sequence !== authRequestSequenceRef.current) {
          await response.body?.cancel().catch(() => undefined)
          return false
        }
        if (response.status !== 401 || attempt === 1) break
        await response.body?.cancel().catch(() => undefined)
        await new Promise((resolve) => window.setTimeout(resolve, 200))
      }
      if (!response?.ok) throw new Error(response?.statusText || 'Không xác nhận được phiên CMS')
      const data = await response.json() as EffectiveSession
      if (sequence !== authRequestSequenceRef.current) return false
      setCookieAuthenticated(true)
      setBusinessPermissions(Array.isArray(data.business_permissions) ? data.business_permissions : (Array.isArray(data.permissions) ? data.permissions : []))
      setIsSystemAdmin(Boolean(data.is_system_admin))
      setAssignments(Array.isArray(data.assignments) ? data.assignments : [])
      const effectiveRole = (data.effective_legacy_role || data.role) as Role | undefined
      if (effectiveRole && ROLE_PERMISSIONS[effectiveRole]) setRoleState(effectiveRole)
      if (data.user_id) setUserIdState(String(data.user_id))
      return true
    } catch {
      if (sequence === authRequestSequenceRef.current) {
        setCookieAuthenticated(false)
        setBusinessPermissions([])
        setIsSystemAdmin(false)
        setAssignments([])
      }
      return false
    } finally {
      if (sequence === authRequestSequenceRef.current) setAuthReady(true)
    }
  }, [])

  useEffect(() => {
    const savedCourseId = window.localStorage.getItem(STORAGE_KEYS.courseId)
    const savedRole = window.localStorage.getItem(STORAGE_KEYS.role) as Role | null
    const savedUserId = window.localStorage.getItem(STORAGE_KEYS.userId)
    const savedSession = getStoredSession()
    if (!IS_PRODUCTION && savedCourseId) setCourseIdState(savedCourseId)
    if (!IS_PRODUCTION && savedRole && ROLE_PERMISSIONS[savedRole]) setRoleState(savedRole)
    if (!IS_PRODUCTION && savedUserId) setUserIdState(savedUserId)
    if (savedSession) {
      accessTokenRef.current = savedSession.access_token
      setAccessTokenState(savedSession.access_token)
      if (savedSession.role && ROLE_PERMISSIONS[savedSession.role]) setRoleState(savedSession.role)
      if (savedSession.user_id) setUserIdState(savedSession.user_id)
    }
    setClientReady(true)
    if (!IS_PRODUCTION) setAuthReady(true)
  }, [])


  useEffect(() => {
    const handleExpired = () => {
      authRequestSequenceRef.current += 1
      accessTokenRef.current = ''
      setAccessTokenState('')
      setCookieAuthenticated(false)
      setBusinessPermissions([])
      setIsSystemAdmin(false)
      setAssignments([])
      setUserIdState('')
      setAuthReady(true)
      window.sessionStorage.removeItem(STORAGE_KEYS.sessionToken)
      window.sessionStorage.removeItem('ai_openedx_cms_bridge_started_at')
      if (IS_PRODUCTION && !window.location.pathname.startsWith('/auth/')) {
        window.location.assign('/auth/logged-out?reason=session-expired')
      }
    }
    window.addEventListener('ai:auth-expired', handleExpired)
    return () => window.removeEventListener('ai:auth-expired', handleExpired)
  }, [])

  useEffect(() => {
    if (!clientReady) return
    void refreshAuthSession()
  }, [clientReady, refreshAuthSession])

  const setCourseId = (value: string) => {
    setCourseIdState(value)
    if (!IS_PRODUCTION) window.localStorage.setItem(STORAGE_KEYS.courseId, value)
  }

  const setRole = (value: Role) => {
    if (IS_PRODUCTION) return
    setRoleState(value)
    window.localStorage.setItem(STORAGE_KEYS.role, value)
  }

  const setUserId = (value: string) => {
    setUserIdState(value)
    if (!IS_PRODUCTION) window.localStorage.setItem(STORAGE_KEYS.userId, value)
  }

  const setAccessToken = (value: string) => {
    // Production safety: never store Bearer tokens in localStorage. For CMS SSO we
    // keep the short-lived AI session token in sessionStorage only, so refresh in
    // the same tab keeps working while closing the browser clears it.
    const token = value.trim()
    accessTokenRef.current = token
    setAccessTokenState(token)
    if (token && !IS_PRODUCTION) {
      window.sessionStorage.setItem(STORAGE_KEYS.sessionToken, JSON.stringify({ access_token: token, user_id: userId, role }))
    } else {
      window.sessionStorage.removeItem(STORAGE_KEYS.sessionToken)
    }
  }

  const applyAuthSession = (session: { access_token?: string; user_id: string; role: Role; email?: string | null; course_ids?: string[] }) => {
    const token = session.access_token || ''
    authRequestSequenceRef.current += 1
    accessTokenRef.current = token
    setAccessTokenState(token)
    setCookieAuthenticated(true)
    setAuthReady(false)
    setBusinessPermissions([])
    setIsSystemAdmin(false)
    setAssignments([])
    if (token && !IS_PRODUCTION) {
      window.sessionStorage.setItem(STORAGE_KEYS.sessionToken, JSON.stringify(session))
      window.sessionStorage.removeItem('ai_openedx_cms_bridge_started_at')
    } else if (IS_PRODUCTION) {
      window.sessionStorage.removeItem(STORAGE_KEYS.sessionToken)
      window.sessionStorage.removeItem('ai_openedx_cms_bridge_started_at')
    }
    if (session.role && ROLE_PERMISSIONS[session.role]) {
      setRoleState(session.role)
      if (!IS_PRODUCTION) window.localStorage.setItem(STORAGE_KEYS.role, session.role)
    }
    if (session.user_id) {
      setUserIdState(session.user_id)
      if (!IS_PRODUCTION) window.localStorage.setItem(STORAGE_KEYS.userId, session.user_id)
    }
  }

  const clearAuthSession = () => {
    authRequestSequenceRef.current += 1
    accessTokenRef.current = ''
    setAccessTokenState('')
    setCookieAuthenticated(false)
    setAuthReady(true)
    setBusinessPermissions([])
    setIsSystemAdmin(false)
    setAssignments([])
    setUserIdState('')
    if (typeof window !== 'undefined') {
      window.sessionStorage.removeItem(STORAGE_KEYS.sessionToken)
      window.sessionStorage.removeItem('ai_openedx_cms_bridge_started_at')
      if (!IS_PRODUCTION) window.localStorage.removeItem(STORAGE_KEYS.userId)
    }
  }

  const value = useMemo<AppContextValue>(() => {
    const canUseLegacyRoleFallback = !IS_PRODUCTION && !cookieAuthenticated
    return {
      authReady,
      isAuthenticated: !!accessToken.trim() || cookieAuthenticated,
      courseId,
      setCourseId,
      role,
      setRole,
      userId,
      setUserId,
      accessToken,
      setAccessToken,
      businessPermissions,
      isSystemAdmin,
      assignments,
      applyAuthSession,
      refreshAuthSession,
      clearAuthSession,
      can: (permission: Permission | string) => {
        if (isSystemAdmin) return true
        if (cookieAuthenticated) return hasBusinessPermission(permission, businessPermissions)
        return (canUseLegacyRoleFallback && ROLE_PERMISSIONS[role].includes(permission as Permission)) || hasBusinessPermission(permission, businessPermissions)
      },
      canScope: (permission: Permission | string, target: ScopeTarget) => {
        if (isSystemAdmin) return true
        const wanted = LEGACY_PERMISSION_BRIDGE[permission] || [String(permission)]
        if (cookieAuthenticated) {
          return assignments.some((assignment) => {
            const assignmentPermissions = Array.isArray(assignment.permission_codes) ? assignment.permission_codes : []
            return wanted.some((item) => assignmentPermissions.includes(item)) && assignmentCoversTarget(assignment, target)
          })
        }
        return ((canUseLegacyRoleFallback && ROLE_PERMISSIONS[role].includes(permission as Permission)) || hasBusinessPermission(permission, businessPermissions))
      },
      authHeaders: (json = false) => {
        const headers: Record<string, string> = {}
        const sessionToken = !IS_PRODUCTION ? (accessToken.trim() || getStoredSession()?.access_token || '') : ''
        if (sessionToken) {
          headers.Authorization = `Bearer ${sessionToken}`
        } else if (!IS_PRODUCTION) {
          headers['X-User-Role'] = role
          headers['X-User-Id'] = userId
        }
        if (json) headers['Content-Type'] = 'application/json'
        return headers
      },
    }
  }, [authReady, courseId, role, userId, accessToken, businessPermissions, cookieAuthenticated, isSystemAdmin, assignments, refreshAuthSession])


  return <AppContext.Provider value={value}>{children}</AppContext.Provider>
}

export function useAppContext() {
  const value = useContext(AppContext)
  if (!value) throw new Error('useAppContext must be used inside AppProvider')
  return value
}
