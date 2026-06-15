'use client'

import { createContext, useContext, useEffect, useMemo, useState } from 'react'
import { Permission, Role, ROLE_PERMISSIONS } from '../types'
import { API } from '../lib/api'

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
  applyAuthSession: (session: { access_token: string; user_id: string; role: Role; email?: string | null; course_ids?: string[] }) => void
  can: (permission: Permission | string) => boolean
  authHeaders: (json?: boolean) => HeadersInit
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
  view_jobs: ['bank.view', 'audit.view'],
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
  view_user_analytics: ['user.manage_all'],
}

function hasBusinessPermission(permission: Permission | string, businessPermissions: string[]) {
  if (businessPermissions.includes(permission)) return true
  const mapped = LEGACY_PERMISSION_BRIDGE[permission] || [permission]
  return mapped.some((item) => businessPermissions.includes(item))
}

function getStoredSession(): StoredSession | null {
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

function getStoredString(key: string, fallback: string) {
  if (typeof window === 'undefined') return fallback
  return window.localStorage.getItem(key) || fallback
}

type StoredSession = {
  access_token: string
  user_id?: string
  role?: Role
  email?: string | null
  course_ids?: string[]
}

export function AppProvider({ children }: { children: React.ReactNode }) {
  const [courseId, setCourseIdState] = useState(() => getStoredString(STORAGE_KEYS.courseId, 'course-v1:FPT+PRN232+2026'))
  const [role, setRoleState] = useState<Role>(() => {
    if (IS_PRODUCTION) return 'viewer'
    const saved = getStoredString(STORAGE_KEYS.role, 'teacher') as Role
    return ROLE_PERMISSIONS[saved] ? saved : 'teacher'
  })
  const [userId, setUserIdState] = useState(() => getStoredSession()?.user_id || getStoredString(STORAGE_KEYS.userId, 'demo-teacher'))
  const [accessToken, setAccessTokenState] = useState(() => getStoredSession()?.access_token || '')
  const [businessPermissions, setBusinessPermissions] = useState<string[]>([])
  const [authReady, setAuthReady] = useState(() => typeof window !== 'undefined')

  useEffect(() => {
    const savedCourseId = window.localStorage.getItem(STORAGE_KEYS.courseId)
    const savedRole = window.localStorage.getItem(STORAGE_KEYS.role) as Role | null
    const savedUserId = window.localStorage.getItem(STORAGE_KEYS.userId)
    const savedSession = getStoredSession()
    if (savedCourseId) setCourseIdState(savedCourseId)
    if (!IS_PRODUCTION && savedRole && ROLE_PERMISSIONS[savedRole]) setRoleState(savedRole)
    if (savedUserId) setUserIdState(savedUserId)
    if (savedSession) {
      setAccessTokenState(savedSession.access_token)
      if (savedSession.role && ROLE_PERMISSIONS[savedSession.role]) setRoleState(savedSession.role)
      if (savedSession.user_id) setUserIdState(savedSession.user_id)
    }
    setAuthReady(true)
  }, [])


  useEffect(() => {
    if (!authReady) return
    const token = accessToken.trim() || getStoredSession()?.access_token || ''
    if (!token) {
      setBusinessPermissions([])
      return
    }
    let cancelled = false
    fetch(`${API}/rbac/me`, { headers: { Authorization: `Bearer ${token}` } })
      .then(async (response) => {
        if (!response.ok) throw new Error(response.statusText)
        return response.json() as Promise<{ effective_legacy_role?: Role | string; permissions?: string[] }>
      })
      .then((data) => {
        if (cancelled) return
        setBusinessPermissions(Array.isArray(data.permissions) ? data.permissions : [])
        const effectiveRole = data.effective_legacy_role as Role | undefined
        if (effectiveRole && ROLE_PERMISSIONS[effectiveRole]) setRoleState(effectiveRole)
      })
      .catch(() => {
        if (!cancelled) setBusinessPermissions([])
      })
    return () => { cancelled = true }
  }, [authReady, accessToken])

  const setCourseId = (value: string) => {
    setCourseIdState(value)
    window.localStorage.setItem(STORAGE_KEYS.courseId, value)
  }

  const setRole = (value: Role) => {
    if (IS_PRODUCTION) return
    setRoleState(value)
    window.localStorage.setItem(STORAGE_KEYS.role, value)
  }

  const setUserId = (value: string) => {
    setUserIdState(value)
    window.localStorage.setItem(STORAGE_KEYS.userId, value)
  }

  const setAccessToken = (value: string) => {
    // Production safety: never store Bearer tokens in localStorage. For CMS SSO we
    // keep the short-lived AI session token in sessionStorage only, so refresh in
    // the same tab keeps working while closing the browser clears it.
    const token = value.trim()
    setAccessTokenState(token)
    if (token) {
      window.sessionStorage.setItem(STORAGE_KEYS.sessionToken, JSON.stringify({ access_token: token, user_id: userId, role }))
    } else {
      window.sessionStorage.removeItem(STORAGE_KEYS.sessionToken)
    }
  }

  const applyAuthSession = (session: { access_token: string; user_id: string; role: Role; email?: string | null; course_ids?: string[] }) => {
    const token = session.access_token || ''
    setAccessTokenState(token)
    if (token) {
      window.sessionStorage.setItem(STORAGE_KEYS.sessionToken, JSON.stringify(session))
      window.sessionStorage.removeItem('ai_openedx_cms_bridge_started_at')
    }
    if (session.role && ROLE_PERMISSIONS[session.role]) {
      setRoleState(session.role)
      if (!IS_PRODUCTION) window.localStorage.setItem(STORAGE_KEYS.role, session.role)
    }
    if (session.user_id) {
      setUserIdState(session.user_id)
      window.localStorage.setItem(STORAGE_KEYS.userId, session.user_id)
    }
  }

  const value = useMemo<AppContextValue>(() => ({
    authReady,
    isAuthenticated: !!accessToken.trim(),
    courseId,
    setCourseId,
    role,
    setRole,
    userId,
    setUserId,
    accessToken,
    setAccessToken,
    businessPermissions,
    applyAuthSession,
    can: (permission: Permission | string) => ROLE_PERMISSIONS[role].includes(permission as Permission) || hasBusinessPermission(permission, businessPermissions),
    authHeaders: (json = false) => {
      const headers: Record<string, string> = {}
      const sessionToken = accessToken.trim() || getStoredSession()?.access_token || ''
      if (sessionToken) {
        headers.Authorization = `Bearer ${sessionToken}`
      } else if (!IS_PRODUCTION) {
        headers['X-User-Role'] = role
        headers['X-User-Id'] = userId
      }
      if (json) headers['Content-Type'] = 'application/json'
      return headers
    },
  }), [authReady, courseId, role, userId, accessToken, businessPermissions])

  return <AppContext.Provider value={value}>{children}</AppContext.Provider>
}

export function useAppContext() {
  const value = useContext(AppContext)
  if (!value) throw new Error('useAppContext must be used inside AppProvider')
  return value
}
