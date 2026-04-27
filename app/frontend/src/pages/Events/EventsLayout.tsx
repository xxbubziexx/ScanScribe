import { NavLink, Outlet } from 'react-router-dom'

export function EventsLayout() {
  return (
    <div className="ss-events-hub">
      <nav className="ss-events-subnav" aria-label="Events section">
        <NavLink
          to="."
          end
          className={({ isActive }) =>
            isActive ? 'ss-events-tab ss-events-tab--active' : 'ss-events-tab'
          }
        >
          Incidents
        </NavLink>
        <NavLink
          to="monitors"
          className={({ isActive }) =>
            isActive ? 'ss-events-tab ss-events-tab--active' : 'ss-events-tab'
          }
        >
          Monitor config
        </NavLink>
        <NavLink
          to="debug"
          className={({ isActive }) =>
            isActive ? 'ss-events-tab ss-events-tab--active' : 'ss-events-tab'
          }
        >
          Debug
        </NavLink>
      </nav>
      <Outlet />
    </div>
  )
}
