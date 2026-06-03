'use client'

import { createContext, useContext, useEffect, useMemo, useState } from 'react'
import { Permission, Role, ROLE_PERMISSIONS } from '../types'

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

type StoredSession = {
  access_token: string
  user_id?: string
  role?: Role
  email?: string | null
  course_ids?: string[]
}

export function AppProvider({ children }: { children: React.ReactNode }) {
  const [courseId, setCourseIdState] = useState('course-v1:FPT+PRN232+2026')
  const [role, setRoleState] = useState<Role>('teacher')
  const [userId, setUserIdState] = useState('demo-teacher')
  const [accessToken, setAccessTokenState] = useState('')
  const [authReady, setAuthReady] = useState(false)

  useEffect(() => {
    const savedCourseId = window.localStorage.getItem(STORAGE_KEYS.courseId)
    const savedRole = window.localStorage.getItem(STORAGE_KEYS.role) as Role | null
    const savedUserId = window.localStorage.getItem(STORAGE_KEYS.userId)
    const savedSession = window.sessionStorage.getItem(STORAGE_KEYS.sessionToken)
    if (savedCourseId) setCourseIdState(savedCourseId)
    if (savedRole && ROLE_PERMISSIONS[savedRole]) setRoleState(savedRole)
    if (savedUserId) setUserIdState(savedUserId)
    if (savedSession) {
      try {
        const session = JSON.parse(savedSession) as StoredSession
        if (session.access_token) {
          setAccessTokenState(session.access_token)
          if (session.role && ROLE_PERMISSIONS[session.role]) setRoleState(session.role)
          if (session.user_id) setUserIdState(session.user_id)
        }
      } catch {
        window.sessionStorage.removeItem(STORAGE_KEYS.sessionToken)
      }
    }
    setAuthReady(true)
  }, [])

  const setCourseId = (value: string) => {
    setCourseIdState(value)
    window.localStorage.setItem(STORAGE_KEYS.courseId, value)
  }

  const setRole = (value: Role) => {
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
      window.localStorage.setItem(STORAGE_KEYS.role, session.role)
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
    applyAuthSession,
    can: (permission: Permission | string) => ROLE_PERMISSIONS[role].includes(permission as Permission),
    authHeaders: (json = false) => {
      const headers: Record<string, string> = {}
      if (accessToken.trim()) {
        headers.Authorization = `Bearer ${accessToken.trim()}`
      } else {
        headers['X-User-Role'] = role
        headers['X-User-Id'] = userId
      }
      if (json) headers['Content-Type'] = 'application/json'
      return headers
    },
  }), [authReady, courseId, role, userId, accessToken])

  return <AppContext.Provider value={value}>{children}</AppContext.Provider>
}

export function useAppContext() {
  const value = useContext(AppContext)
  if (!value) throw new Error('useAppContext must be used inside AppProvider')
  return value
}
