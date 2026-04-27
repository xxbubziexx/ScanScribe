import { NavLink } from 'react-router-dom'
import { useAuth } from '@/context/AuthContext'

const NAV_ITEMS = [
  { to: '/', label: 'Dashboard', end: true },
  { to: '/insights', label: 'Insights' },
  { to: '/logs', label: 'Database' },
  { to: '/events', label: 'Events' },
  { to: '/users', label: 'Users' },
  { to: '/settings', label: 'Settings' },
]

export function TopNav() {
  const { user, logout } = useAuth()

  return (
    <header className="ss-top">
      <div className="ss-top-inner">
        <span className="ss-logo">ScanScribe</span>
        <nav className="ss-top-nav">
          {NAV_ITEMS.map(({ to, label, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) =>
                isActive ? 'ss-nav-link ss-nav-link--active' : 'ss-nav-link'
              }
            >
              {label}
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
        </div>
      </div>
    </header>
  )
}
