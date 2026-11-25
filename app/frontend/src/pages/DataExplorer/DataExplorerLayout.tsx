import { Link, NavLink, Outlet } from 'react-router-dom'

export function DataExplorerLayout() {
  return (
    <div className="ss-events-hub">
      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-white/10 pb-4">
        <div>
          <h1 className="text-xl font-bold tracking-tight text-gray-100 flex items-center gap-2.5">
            <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-indigo-500/20 text-indigo-400 font-mono text-sm border border-indigo-500/30">
              DB
            </span>
            Database Explorer Suite
          </h1>
          <p className="mt-1 text-xs text-gray-400">
            Unified telemetry, bulk audio archiving, NER raw-value export, and cross-table inspection.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <span className="rounded-md border border-white/10 bg-white/[0.03] px-2.5 py-1 font-mono text-[11px] text-gray-400">
            SQLite WAL
          </span>
          <Link
            to="/data/entities?export=1"
            className="ss-btn-ghost h-8 px-3 text-xs flex items-center"
          >
            NER CSV Exporter
          </Link>
        </div>
      </div>

      <nav className="ss-events-subnav" aria-label="Database tables">
        <NavLink
          to="/data"
          end
          className={({ isActive }) =>
            isActive ? 'ss-events-tab ss-events-tab--active' : 'ss-events-tab'
          }
        >
          <span className="flex items-center gap-1.5">
            <span className="h-1.5 w-1.5 rounded-full bg-cyan-400" />
            Overview
          </span>
        </NavLink>
        <NavLink
          to="/data/logs"
          className={({ isActive }) =>
            isActive ? 'ss-events-tab ss-events-tab--active' : 'ss-events-tab'
          }
        >
          <span className="flex items-center gap-1.5">
            <span className="h-1.5 w-1.5 rounded-full bg-amber-400" />
            Audio Logs
          </span>
        </NavLink>
        <NavLink
          to="/data/spans"
          className={({ isActive }) =>
            isActive ? 'ss-events-tab ss-events-tab--active' : 'ss-events-tab'
          }
        >
          <span className="flex items-center gap-1.5">
            <span className="h-1.5 w-1.5 rounded-full bg-sky-400" />
            Span Store
          </span>
        </NavLink>
        <NavLink
          to="/data/entities"
          className={({ isActive }) =>
            isActive ? 'ss-events-tab ss-events-tab--active' : 'ss-events-tab'
          }
        >
          <span className="flex items-center gap-1.5">
            <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />
            NER Entities
          </span>
        </NavLink>
        <NavLink
          to="/data/events"
          className={({ isActive }) =>
            isActive ? 'ss-events-tab ss-events-tab--active' : 'ss-events-tab'
          }
        >
          <span className="flex items-center gap-1.5">
            <span className="h-1.5 w-1.5 rounded-full bg-indigo-400" />
            Events
          </span>
        </NavLink>
        <NavLink
          to="/data/dataset"
          className={({ isActive }) =>
            isActive ? 'ss-events-tab ss-events-tab--active' : 'ss-events-tab'
          }
        >
          <span className="flex items-center gap-1.5">
            <span className="h-1.5 w-1.5 rounded-full bg-pink-400" />
            Fine-Tuning Dataset
          </span>
        </NavLink>
      </nav>

      <Outlet />
    </div>
  )
}
