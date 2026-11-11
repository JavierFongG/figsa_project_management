import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'
import { get, post, getToken, setToken } from './api'

export type User = { id: string; email: string; name: string; role: 'viewer' | 'editor'; can_write?: boolean }
type Ctx = {
  user: User | null
  loading: boolean
  canWrite: boolean
  login: (email: string, password: string) => Promise<void>
  logout: () => void
}
const AuthCtx = createContext<Ctx>(null as any)
export const useAuth = () => useContext(AuthCtx)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(!!getToken())

  useEffect(() => {
    if (getToken()) {
      get<User>('/auth/me').then(setUser).catch(() => setToken(null)).finally(() => setLoading(false))
    }
    const off = () => setUser(null)
    window.addEventListener('figsa:logout', off)
    return () => window.removeEventListener('figsa:logout', off)
  }, [])

  const login = async (email: string, password: string) => {
    const r = await post('/auth/login', { email, password })
    setToken(r.access_token)
    setUser({ ...r.user, can_write: r.user.role === 'editor' })
  }
  const logout = () => { setToken(null); setUser(null) }

  return <AuthCtx.Provider value={{ user, loading, canWrite: user?.role === 'editor', login, logout }}>{children}</AuthCtx.Provider>
}
