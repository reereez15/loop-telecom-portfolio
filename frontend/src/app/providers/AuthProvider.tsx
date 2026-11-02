import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react'
import { api, setCsrfToken } from '../../services/apiClient'
import type { Profile, SessionInfo } from '../../services/types'

interface AuthValue {
  user: Profile | null
  session: SessionInfo | null
  setUser: (u: Profile | null) => void
  checking: boolean
  isAdmin: boolean
  login: (email: string, password: string) => Promise<Profile>
  logout: () => Promise<void>
  forgetSession: () => void
}

interface SessionData { user: Profile; csrf_token: string; session?: SessionInfo }

const AuthContext = createContext<AuthValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<Profile | null>(null)
  const [session, setSession] = useState<SessionInfo | null>(null)
  const [checking, setChecking] = useState(true)

  // 새로고침해도 DB 세션이 살아 있으면 로그인 상태와 CSRF 토큰을 복원
  useEffect(() => {
    api<SessionData>('/auth/me')
      .then((d) => { setCsrfToken(d.csrf_token); setUser(d.user); setSession(d.session ?? null) })
      .catch(() => setUser(null))
      .finally(() => setChecking(false))
  }, [])

  const login = useCallback(async (email: string, password: string) => {
    const d = await api<SessionData>('/auth/login', { method: 'POST', body: { email, password } })
    setCsrfToken(d.csrf_token)
    setUser(d.user)
    setSession(d.session ?? null)
    return d.user
  }, [])

  // 서버가 세션을 폐기한 경우(비밀번호 변경·탈퇴) 화면 쪽 상태만 비운다
  const forgetSession = useCallback(() => { setCsrfToken(null); setUser(null); setSession(null) }, [])

  const logout = useCallback(async () => {
    try { await api('/auth/logout', { method: 'POST' }) } finally { forgetSession() }
  }, [forgetSession])

  return (
    <AuthContext.Provider
      value={{ user, session, setUser, checking, login, logout, forgetSession, isAdmin: !!user && user.role !== 'CUSTOMER' }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth(): AuthValue {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('AuthProvider 안에서만 사용할 수 있습니다.')
  return ctx
}
