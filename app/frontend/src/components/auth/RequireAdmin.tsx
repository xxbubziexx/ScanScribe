import { Navigate, Outlet } from 'react-router-dom'
import { useAuth } from '@/context/AuthContext'

/** Nested routes under this outlet are only reachable for admins. */
export function RequireAdmin() {
  const { user } = useAuth()
  if (!user?.is_admin) return <Navigate to="/" replace />
  return <Outlet />
}
