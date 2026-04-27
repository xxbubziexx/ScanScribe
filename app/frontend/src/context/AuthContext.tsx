import { createContext, useCallback, useContext, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { auth } from '@/lib/api'
import type { UserResponse } from '@/types/api'

interface AuthState {
  user: UserResponse | null
  token: string | null
  isLoading: boolean
}

interface AuthContextValue extends AuthState {
  login: (username: string, password: string) => Promise<void>
  logout: () => void
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const navigate = useNavigate()

  const [state, setState] = useState<AuthState>({
    user: null,
    token: localStorage.getItem('access_token'),
    isLoading: true,
  })

  // Hydrate user from stored token on mount
  useEffect(() => {
    const storedToken = localStorage.getItem('access_token')
    if (!storedToken) {
      setState((s) => ({ ...s, isLoading: false }))
      return
    }

    auth
      .me()
      .then((user) => setState({ user, token: storedToken, isLoading: false }))
      .catch(() => {
        localStorage.removeItem('access_token')
        localStorage.removeItem('username')
        setState({ user: null, token: null, isLoading: false })
      })
  }, [])

  const login = useCallback(async (username: string, password: string) => {
    const tokenData = await auth.login(username, password)
    localStorage.setItem('access_token', tokenData.access_token)
    localStorage.setItem('username', username)

    const user = await auth.me()
    localStorage.setItem('username', user.username)

    setState({ user, token: tokenData.access_token, isLoading: false })
    navigate('/')
  }, [navigate])

  const logout = useCallback(() => {
    localStorage.removeItem('access_token')
    localStorage.removeItem('username')
    setState({ user: null, token: null, isLoading: false })
    navigate('/login')
  }, [navigate])

  return (
    <AuthContext.Provider value={{ ...state, login, logout }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used inside <AuthProvider>')
  return ctx
}
