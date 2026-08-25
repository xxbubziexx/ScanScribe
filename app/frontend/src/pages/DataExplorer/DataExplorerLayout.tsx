import { NavLink, Outlet } from 'react-router-dom'

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
            Unified data viewer for pipeline incidents, transcript spans, NER entity observations, and audio logs.
          </p>
        </div>
      </div>

      <nav className="ss-events-subnav" aria-label="Database tables">
        <NavLink
          to="/data/events"
          className={({ isActive }) =>
            isActive ? 'ss-events-tab ss-events-tab--active' : 'ss-events-tab'
          }
        >
          <span className="flex items-center gap-1.5">
            <span className="h-1.5 w-1.5 rounded-full bg-indigo-400" />
            Events Table
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
            Span Store (Transcripts)
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
            NER Entity Observations
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
