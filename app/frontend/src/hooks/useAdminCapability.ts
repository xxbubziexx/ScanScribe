import { useContext, useEffect, useState } from 'react'
import { AuthContext, useAuth } from '@/context/AuthContext'

export const MOBILE_BREAKPOINT = 768

/**
 * Returns true if the current viewport is narrower than the specified breakpoint (default: 768px).
 */
export function useIsMobile(breakpoint = MOBILE_BREAKPOINT): boolean {
  const [isMobile, setIsMobile] = useState<boolean>(() => {
    if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return false
    return window.matchMedia(`(max-width: ${breakpoint - 1}px)`).matches
  })

  useEffect(() => {
    if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return
    const mq = window.matchMedia(`(max-width: ${breakpoint - 1}px)`)
    const onChange = () => setIsMobile(mq.matches)
    onChange()
    mq.addEventListener('change', onChange)
    return () => mq.removeEventListener('change', onChange)
  }, [breakpoint])

  return isMobile
}

export interface AdminCapability {
  /** True only if the user has is_admin privileges AND is NOT accessing from a mobile client. */
  canAdmin: boolean
  /** Whether the current client is on a mobile viewport (< 768px). */
  isMobile: boolean
  /** Whether the authenticated user account itself has admin role on the backend. */
  isAccountAdmin: boolean
}

/**
 * Hook to enforce client-level administrative capability restrictions.
 * Restricts all administrative capabilities from mobile clients (< 768px)
 * even if the user account is an administrator.
 */
export function useAdminCapability(breakpoint = MOBILE_BREAKPOINT): AdminCapability {
  let user = null
  try {
    const auth = useAuth()
    user = auth?.user ?? null
  } catch {
    const auth = useContext(AuthContext)
    user = auth?.user ?? null
  }
  const isMobile = useIsMobile(breakpoint)

  const isAccountAdmin = Boolean(user?.is_admin)
  const canAdmin = isAccountAdmin && !isMobile

  return {
    canAdmin,
    isMobile,
    isAccountAdmin,
  }
}
