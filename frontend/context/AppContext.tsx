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
  isSystemAdmin: boolean
  assignments: EffectiveAssignment[]
  applyAuthSession: (session: { access_token: string; user_id: string; role: Role; email?: string | null; course_ids?: string[] }) => void
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

function getStoredString(key: string, fallback: string) {
  if (IS_PRODUCTION || typeof window === 'undefined') return fallback
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
  const [courseId, setCourseIdState] = useState(() => getStoredString(STORAGE_KEYS.courseId, ''))
  const [role, setRoleState] = useState<Role>(() => {
    if (IS_PRODUCTION) return 'viewer'
    const saved = getStoredString(STORAGE_KEYS.role, 'teacher') as Role
    return ROLE_PERMISSIONS[saved] ? saved : 'teacher'
  })
  const [userId, setUserIdState] = useState(() => getStoredSession()?.user_id || getStoredString(STORAGE_KEYS.userId, ''))
  const [accessToken, setAccessTokenState] = useState(() => getStoredSession()?.access_token || '')
  const [businessPermissions, setBusinessPermissions] = useState<string[]>([])
  const [isSystemAdmin, setIsSystemAdmin] = useState(false)
  const [assignments, setAssignments] = useState<EffectiveAssignment[]>([])
  const [cookieAuthenticated, setCookieAuthenticated] = useState(false)
  const [clientReady, setClientReady] = useState(() => typeof window !== 'undefined')
  const [authReady, setAuthReady] = useState(() => !IS_PRODUCTION && typeof window !== 'undefined')

  useEffect(() => {
    const savedCourseId = window.localStorage.getItem(STORAGE_KEYS.courseId)
    const savedRole = window.localStorage.getItem(STORAGE_KEYS.role) as Role | null
    const savedUserId = window.localStorage.getItem(STORAGE_KEYS.userId)
    const savedSession = getStoredSession()
    if (!IS_PRODUCTION && savedCourseId) setCourseIdState(savedCourseId)
    if (!IS_PRODUCTION && savedRole && ROLE_PERMISSIONS[savedRole]) setRoleState(savedRole)
    if (!IS_PRODUCTION && savedUserId) setUserIdState(savedUserId)
    if (savedSession) {
      setAccessTokenState(savedSession.access_token)
      if (savedSession.role && ROLE_PERMISSIONS[savedSession.role]) setRoleState(savedSession.role)
      if (savedSession.user_id) setUserIdState(savedSession.user_id)
    }
    setClientReady(true)
    if (!IS_PRODUCTION) setAuthReady(true)
  }, [])


  useEffect(() => {
    if (!clientReady) return
    const token = accessToken.trim() || getStoredSession()?.access_token || ''
    if (!token && !IS_PRODUCTION) {
      setCookieAuthenticated(false)
      setBusinessPermissions([])
      setIsSystemAdmin(false)
      setAssignments([])
      setAuthReady(true)
      return
    }
    let cancelled = false
    setAuthReady(false)
    fetch(`${API}/rbac/me`, { headers: token ? { Authorization: `Bearer ${token}` } : {}, credentials: 'include' })
      .then(async (response) => {
        if (!response.ok) throw new Error(response.statusText)
        return response.json() as Promise<{ user_id?: string; effective_legacy_role?: Role | string; role?: Role | string; is_system_admin?: boolean; permissions?: string[]; business_permissions?: string[]; assignments?: EffectiveAssignment[] }>
      })
      .then((data) => {
        if (cancelled) return
        setCookieAuthenticated(true)
        setBusinessPermissions(Array.isArray(data.business_permissions) ? data.business_permissions : (Array.isArray(data.permissions) ? data.permissions : []))
        setIsSystemAdmin(Boolean(data.is_system_admin))
        setAssignments(Array.isArray(data.assignments) ? data.assignments : [])
        const effectiveRole = (data.effective_legacy_role || data.role) as Role | undefined
        if (effectiveRole && ROLE_PERMISSIONS[effectiveRole]) setRoleState(effectiveRole)
        if (data.user_id) setUserIdState(String(data.user_id))
      })
      .catch(() => {
        if (!cancelled) {
          setCookieAuthenticated(false)
          setBusinessPermissions([])
          setIsSystemAdmin(false)
          setAssignments([])
        }
      })
      .finally(() => {
        if (!cancelled) setAuthReady(true)
      })
    return () => { cancelled = true }
  }, [clientReady, accessToken])

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
    setAccessTokenState(token)
    if (token && !IS_PRODUCTION) {
      window.sessionStorage.setItem(STORAGE_KEYS.sessionToken, JSON.stringify({ access_token: token, user_id: userId, role }))
    } else {
      window.sessionStorage.removeItem(STORAGE_KEYS.sessionToken)
    }
  }

  const applyAuthSession = (session: { access_token: string; user_id: string; role: Role; email?: string | null; course_ids?: string[] }) => {
    const token = session.access_token || ''
    setAccessTokenState(token)
    setCookieAuthenticated(true)
    setAuthReady(true)
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
    }
  }, [authReady, courseId, role, userId, accessToken, businessPermissions, cookieAuthenticated, isSystemAdmin, assignments])


  return <AppContext.Provider value={value}>{children}</AppContext.Provider>
}

export function useAppContext() {
  const value = useContext(AppContext)
  if (!value) throw new Error('useAppContext must be used inside AppProvider')
  return value
}
