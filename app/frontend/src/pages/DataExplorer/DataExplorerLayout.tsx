import { Link, NavLink, Outlet } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { maintenanceApi } from '@/lib/maintenance'
import { formatBytes } from '@/pages/Database/utils/formatBytes'

const TABLE_NAV_ITEMS = [
  {
    key: 'logs',
    to: '/data/logs',
    label: 'Audio Logs',
    sqlName: 'log_entries',
    dotClass: 'bg-amber-400',
  },
  {
    key: 'spans',
    to: '/data/spans',
    label: 'Span Store',
    sqlName: 'span_store',
    dotClass: 'bg-sky-400',
  },
  {
    key: 'entities',
    to: '/data/entities',
    label: 'NER Entities',
    sqlName: 'entity_observations',
    dotClass: 'bg-emerald-400',
  },
  {
    key: 'events',
    to: '/data/events',
    label: 'Events',
    sqlName: 'events',
    dotClass: 'bg-indigo-400',
  },
  {
    key: 'dataset',
    to: '/data/dataset',
    label: 'Fine-Tuning Dataset',
    sqlName: 'reviewed',
    dotClass: 'bg-pink-400',
  },
] as const

export function DataExplorerLayout() {
  const overviewQuery = useQuery({
    queryKey: ['database-overview'],
    queryFn: () => maintenanceApi.overview(),
    staleTime: 30_000,
  })

  const data = overviewQuery.data
  const countByKey = new Map<string, number>(
    (data?.tables ?? []).map((t) => [t.key, t.row_count]),
  )

  const nerBadge = !data?.ner
    ? null
    : !data.ner.pipeline_enabled
      ? { text: 'Off', cls: 'border-white/10 bg-white/5 text-gray-400' }
      : data.ner.ner_only
        ? { text: 'NER-Only', cls: 'border-emerald-500/30 bg-emerald-500/15 text-emerald-300' }
        : { text: 'Full', cls: 'border-indigo-500/30 bg-indigo-500/15 text-indigo-300' }

  return (
    <div className="ss-workbench">
      <aside className="ss-workbench-rail">
        <div className="flex items-center justify-between gap-2 border-b border-white/10 px-4 py-3">
          <div className="flex items-center gap-2 min-w-0">
            <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-md border border-indigo-500/35 bg-indigo-500/20 font-mono text-[11px] font-bold text-indigo-300">
              DB
            </span>
            <div className="min-w-0">
              <h1 className="truncate text-sm font-semibold tracking-tight text-gray-100">
                Database
              </h1>
              <div className="font-mono text-[10px] uppercase tracking-wider text-gray-500">
                SQLite {data?.storage.journal_mode ?? 'wal'}
              </div>
            </div>
          </div>

          <button
            type="button"
            className="rounded-md border border-white/10 bg-white/[0.03] px-2 py-1 text-[11px] text-gray-400 transition hover:border-white/20 hover:text-gray-200 cursor-pointer disabled:opacity-50"
            onClick={() => void overviewQuery.refetch()}
            disabled={overviewQuery.isFetching}
            title="Refresh live table counts"
          >
            {overviewQuery.isFetching ? '…' : 'Sync'}
          </button>
        </div>

        <nav
          className="flex flex-row gap-1 overflow-x-auto px-2 py-2 lg:flex-col lg:overflow-x-visible lg:px-2.5 lg:py-3"
          aria-label="Database tables"
        >
          <div className="hidden px-2 pb-1 text-[10px] font-semibold uppercase tracking-wider text-gray-500 lg:block">
            Tables
          </div>
          {TABLE_NAV_ITEMS.map((item) => {
            const count = countByKey.get(item.key)
            return (
              <NavLink
                key={item.key}
                to={item.to}
                className={({ isActive }) =>
                  `group flex shrink-0 items-center justify-between gap-2 rounded-lg px-2.5 py-2 text-xs transition ${
                    isActive
                      ? 'bg-indigo-500/15 text-white border border-indigo-500/30'
                      : 'text-gray-400 border border-transparent hover:bg-white/[0.04] hover:text-gray-200'
                  }`
                }
              >
                <span className="flex items-center gap-2 min-w-0">
                  <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${item.dotClass}`} />
                  <span className="min-w-0">
                    <span className="block truncate font-medium">{item.label}</span>
                    <span className="hidden font-mono text-[10px] text-gray-500 lg:block">
                      {item.sqlName}
                    </span>
                  </span>
                </span>
                {count !== undefined && (
                  <span className="rounded bg-white/[0.06] px-1.5 py-0.5 font-mono text-[10px] text-gray-300 tabular-nums">
                    {count.toLocaleString()}
                  </span>
                )}
              </NavLink>
            )
          })}
        </nav>

        <div className="hidden border-t border-white/10 px-2.5 py-2.5 lg:block">
          <div className="px-2 pb-1.5 text-[10px] font-semibold uppercase tracking-wider text-gray-500">
            Tools
          </div>
          <div className="space-y-1">
            <Link
              to="/data/entities?export=1"
              className="flex items-center justify-between rounded-lg px-2.5 py-1.5 text-xs text-emerald-300/90 transition hover:bg-emerald-500/10 hover:text-emerald-200"
            >
              <span>NER CSV Exporter</span>
              <span className="font-mono text-[10px] text-emerald-400/70">CSV</span>
            </Link>
            <Link
              to="/events/monitors"
              className="flex items-center justify-between rounded-lg px-2.5 py-1.5 text-xs text-gray-400 transition hover:bg-white/[0.04] hover:text-gray-200"
            >
              <span>Monitors</span>
              <span className="font-mono text-[10px] text-gray-500">
                {countByKey.get('monitors') ?? '—'}
              </span>
            </Link>
          </div>
        </div>

        <div
          className="mt-auto hidden border-t border-white/10 bg-black/25 p-3.5 lg:block"
          aria-label="Storage and pipeline telemetry"
        >
          <div className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-gray-500">
            Storage & Pipeline
          </div>
          {data ? (
            <dl className="space-y-1.5 text-[11px]">
              <div className="flex items-center justify-between gap-2">
                <dt className="text-gray-500">SQLite + WAL</dt>
                <dd className="font-mono text-gray-200">
                  {formatBytes(data.storage.total_sqlite_bytes)}
                </dd>
              </div>
              <div className="flex items-center justify-between gap-2">
                <dt className="text-gray-500">Audio ({data.storage.audio_files_count.toLocaleString()})</dt>
                <dd className="font-mono text-gray-200">
                  {formatBytes(data.storage.audio_bytes)}
                </dd>
              </div>
              <div className="flex items-center justify-between gap-2">
                <dt className="text-gray-500">NER Coverage</dt>
                <dd className="flex items-center gap-1.5 font-mono text-gray-200">
                  <span>{data.ner.coverage_pct.toFixed(1)}%</span>
                  {nerBadge && (
                    <span className={`rounded border px-1 py-0 text-[9px] font-semibold ${nerBadge.cls}`}>
                      {nerBadge.text}
                    </span>
                  )}
                </dd>
              </div>
              <div className="flex items-center justify-between gap-2">
                <dt className="text-gray-500">Ingest (24h)</dt>
                <dd className="font-mono text-amber-300">
                  {data.logs_last_24h.toLocaleString()} clips
                </dd>
              </div>
            </dl>
          ) : (
            <div className="text-[11px] text-gray-500">Loading telemetry…</div>
          )}
        </div>
      </aside>

      <div className="ss-workbench-main">
        <Outlet />
      </div>
    </div>
  )
}
