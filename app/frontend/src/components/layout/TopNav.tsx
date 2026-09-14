import { NavLink } from 'react-router-dom'
import { useEffect, useState } from 'react'
import { createPortal } from 'react-dom'
import { useAuth } from '@/context/AuthContext'

import { useAdminCapability } from '@/hooks/useAdminCapability'

interface NavItemDef {
  to: string
  label: string
  icon: string
  end?: boolean
  adminOnly?: boolean
}

const NAV_ITEMS: readonly NavItemDef[] = [
  { to: '/', label: 'Command Center', icon: '🗺️', end: true },
  { to: '/dashboard', label: 'Audio Feed', icon: '📻' },
  { to: '/insights', label: 'Insights', icon: '📊' },
  { to: '/events', label: 'Events', icon: '🚨' },
  { to: '/data', label: 'Database', icon: '💾', adminOnly: true },
  { to: '/users', label: 'Users', icon: '👥', adminOnly: true },
  { to: '/settings', label: 'Settings', icon: '⚙️', adminOnly: true },
] as const

export function TopNav() {
  const { user, logout } = useAuth()
  const { canAdmin, isMobile } = useAdminCapability()
  const desktopNavItems = canAdmin ? NAV_ITEMS : NAV_ITEMS.filter((i) => !i.adminOnly)
  // Mobile clients are strictly restricted from admin capabilities
  const mobileNavItems = NAV_ITEMS.filter((i) => !i.adminOnly)
  const [menuOpen, setMenuOpen] = useState(false)

  useEffect(() => {
    if (!menuOpen) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setMenuOpen(false)
    }
    window.addEventListener('keydown', onKey)
    document.body.style.overflow = 'hidden'
    return () => {
      window.removeEventListener('keydown', onKey)
      document.body.style.overflow = ''
    }
  }, [menuOpen])

  useEffect(() => {
    const mq = window.matchMedia?.('(min-width: 768px)')
    if (!mq) return
    const onChange = () => {
      if (mq.matches) setMenuOpen(false)
    }
    mq.addEventListener('change', onChange)
    return () => mq.removeEventListener('change', onChange)
  }, [])

  return (
    <header className="ss-top">
      <div className="ss-top-inner">
        <NavLink
          to="/"
          end
          className={({ isActive }) =>
            isActive ? 'ss-logo ss-logo-link ss-logo-link--active' : 'ss-logo ss-logo-link'
          }
          onClick={() => setMenuOpen(false)}
        >
          ScanScribe
        </NavLink>

        <nav className="ss-top-nav ss-top-nav--desktop">
          {desktopNavItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) =>
                isActive ? 'ss-nav-link ss-nav-link--active' : 'ss-nav-link'
              }
            >
              {item.label}
            </NavLink>
          ))}
        </nav>

        <div className="ss-top-user">
          {user && (
            <span className="ss-top-user-text">
              {user.username}
              {canAdmin && <span className="ss-pill-admin">admin</span>}
            </span>
          )}
          <button onClick={logout} className="ss-btn-logout hidden sm:inline-flex" type="button">
            Logout
          </button>
          <button
            type="button"
            className="ss-nav-menu-btn"
            aria-expanded={menuOpen}
            aria-controls="ss-mobile-drawer"
            aria-label={menuOpen ? 'Close navigation drawer' : 'Open navigation drawer'}
            onClick={() => setMenuOpen((o) => !o)}
          >
            <span
              className={menuOpen ? 'ss-nav-menu-icon ss-nav-menu-icon--open' : 'ss-nav-menu-icon'}
            />
          </button>
        </div>
      </div>

      {/* Mobile Navigation Slide-over Drawer Portal */}
      {menuOpen &&
        typeof document !== 'undefined' &&
        createPortal(
          <div
            className="fixed inset-0 z-[99999] md:hidden"
            id="ss-mobile-drawer"
            role="dialog"
            aria-modal="true"
            aria-label="Navigation drawer"
          >
            {/* Backdrop */}
            <div
              className="fixed inset-0 bg-black/75 backdrop-blur-sm transition-opacity"
              onClick={() => setMenuOpen(false)}
              aria-hidden="true"
            />

            {/* Drawer Panel */}
            <div
              className="fixed inset-y-0 right-0 w-[min(320px,85vw)] h-full h-dvh bg-[#0f1117] border-l border-white/10 shadow-2xl flex flex-col z-10 animate-slide-in"
              style={{ backgroundColor: '#0f1117' }}
            >
              {/* Drawer Header */}
              <div className="p-4 border-b border-white/10 bg-white/[0.02] shrink-0">
                <div className="flex items-center justify-between">
                  <span className="text-base font-bold text-white tracking-tight flex items-center gap-2">
                    <span>🎙️</span> ScanScribe
                  </span>
                  <button
                    type="button"
                    onClick={() => setMenuOpen(false)}
                    className="w-11 h-11 flex items-center justify-center rounded-xl text-gray-400 hover:text-white hover:bg-white/10 text-xl transition cursor-pointer"
                    aria-label="Close menu"
                  >
                    ✕
                  </button>
                </div>

                {user && (
                  <div className="mt-3 flex items-center gap-3 p-2.5 rounded-xl bg-white/5 border border-white/10">
                    <div className="w-9 h-9 rounded-full bg-indigo-600/40 border border-indigo-400/40 flex items-center justify-center text-sm font-bold text-indigo-200 shrink-0">
                      {user.username.charAt(0).toUpperCase()}
                    </div>
                    <div className="flex flex-col min-w-0 flex-1">
                      <span className="text-sm font-semibold text-gray-100 truncate">
                        {user.username}
                      </span>
                      <span className="text-xs text-gray-400">
                        {user.is_admin ? (isMobile ? 'Admin (Desktop Only)' : 'Administrator') : 'Viewer'}
                      </span>
                    </div>
                    {canAdmin && <span className="ss-pill-admin shrink-0">admin</span>}
                  </div>
                )}
              </div>

              {/* Nav Items */}
              <nav
                className="flex-1 overflow-y-auto p-3 flex flex-col gap-1.5"
                aria-label="Mobile main navigation"
              >
                {mobileNavItems.map((item) => (
                  <NavLink
                    key={item.to}
                    to={item.to}
                    end={item.end}
                    onClick={() => setMenuOpen(false)}
                    className={({ isActive }) =>
                      `flex items-center gap-3 px-3.5 py-3 rounded-xl text-sm font-medium transition min-h-[48px] ${
                        isActive
                          ? 'bg-indigo-600 text-white shadow-md font-semibold'
                          : 'text-gray-300 hover:bg-white/5 hover:text-white'
                      }`
                    }
                  >
                    <span className="text-lg shrink-0">{item.icon}</span>
                    <span className="flex-1 text-sm">{item.label}</span>
                  </NavLink>
                ))}
              </nav>

              {/* Drawer Footer */}
              <div className="p-3 border-t border-white/10 bg-white/[0.01] shrink-0">
                <button
                  type="button"
                  onClick={() => {
                    setMenuOpen(false)
                    logout()
                  }}
                  className="w-full flex items-center justify-center gap-2 py-3 px-4 rounded-xl border border-red-500/30 bg-red-500/10 text-red-300 font-medium text-sm hover:bg-red-500/20 transition min-h-[48px] cursor-pointer"
                >
                  <span>🚪</span>
                  <span>Log Out</span>
                </button>
              </div>
            </div>
          </div>,
          document.body,
        )}
    </header>
  )
}
