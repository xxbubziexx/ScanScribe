import { Navigate, Outlet, useLocation } from 'react-router-dom'
import { useAdminCapability } from '@/hooks/useAdminCapability'

/**
 * Nested routes under this outlet are only reachable for administrators
 * on non-mobile (desktop) clients.
 * Mobile clients and non-admin accounts are redirected.
 */
export function RequireAdmin({ children }: { children?: React.ReactNode } = {}) {
  const { canAdmin } = useAdminCapability()
  const location = useLocation()

  if (!canAdmin) {
    if (location.pathname.startsWith('/events')) {
      return <Navigate to="/events" replace />
    }
    return <Navigate to="/" replace />
  }

  return children ? <>{children}</> : <Outlet />
}
