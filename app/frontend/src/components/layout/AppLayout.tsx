import { Navigate, Outlet, useLocation } from 'react-router-dom'
import { useAuth } from '@/context/AuthContext'
import { TopNav } from './TopNav'

export function AppLayout() {
  const { token, isLoading } = useAuth()
  const location = useLocation()
  const isFullBleed = location.pathname === '/' || location.pathname.startsWith('/intel')

  if (isLoading) {
    return (
      <div className="ss-splash">
        <span className="ss-splash-text">Loading…</span>
      </div>
    )
  }

  if (!token) return <Navigate to="/login" replace />

  return (
    <div className="ss-app">
      <TopNav />
      <main className={`ss-app-main ${isFullBleed ? 'ss-app-main--fullbleed' : ''}`}>
        <Outlet />
      </main>
    </div>
  )
}
