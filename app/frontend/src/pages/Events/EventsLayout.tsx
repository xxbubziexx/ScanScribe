import { NavLink, Outlet } from 'react-router-dom'
import { useAdminCapability } from '@/hooks/useAdminCapability'

export function EventsLayout() {
  const { canAdmin } = useAdminCapability()

  return (
    <div className="ss-events-hub">
      {canAdmin && (
        <nav className="ss-events-subnav hidden md:flex" aria-label="Events section">
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
            Pipeline & LLM Debug
          </NavLink>
        </nav>
      )}
      <Outlet />
    </div>
  )
}
