import { NavLink } from 'react-router-dom'
import { useEffect, useState } from 'react'
import { useAuth } from '@/context/AuthContext'

const NAV_ITEMS = [
  { to: '/', label: 'Command Center', end: true },
  { to: '/dashboard', label: 'Audio Feed' },
  { to: '/insights', label: 'Insights' },
  { to: '/logs', label: 'Database', adminOnly: true },
  { to: '/events', label: 'Events', adminOnly: true },
  { to: '/users', label: 'Users', adminOnly: true },
  { to: '/settings', label: 'Settings', adminOnly: true },
] as const

export function TopNav() {
  const { user, logout } = useAuth()
  const navItems = user?.is_admin ? NAV_ITEMS : NAV_ITEMS.filter((i) => !('adminOnly' in i && i.adminOnly))
  const [menuOpen, setMenuOpen] = useState(false)

  useEffect(() => {
    if (!menuOpen) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setMenuOpen(false)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [menuOpen])

  useEffect(() => {
    const mq = window.matchMedia('(min-width: 768px)')
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
          {navItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={'end' in item ? item.end : false}
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
              {user.is_admin && <span className="ss-pill-admin">admin</span>}
            </span>
          )}
          <button onClick={logout} className="ss-btn-logout" type="button">
            Logout
          </button>
          <button
            type="button"
            className="ss-nav-menu-btn"
            aria-expanded={menuOpen}
            aria-controls="ss-mobile-nav"
            aria-label={menuOpen ? 'Close menu' : 'Open menu'}
            onClick={() => setMenuOpen((o) => !o)}
          >
            <span className={menuOpen ? 'ss-nav-menu-icon ss-nav-menu-icon--open' : 'ss-nav-menu-icon'} />
          </button>
        </div>
      </div>

      {menuOpen && (
        <nav id="ss-mobile-nav" className="ss-top-nav--mobile" aria-label="Main">
          {navItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={'end' in item ? item.end : false}
              onClick={() => setMenuOpen(false)}
              className={({ isActive }) =>
                isActive ? 'ss-nav-link ss-nav-link--active' : 'ss-nav-link'
              }
            >
              {item.label}
            </NavLink>
          ))}
        </nav>
      )}
    </header>
  )
}
