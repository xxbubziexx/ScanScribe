import { Link, NavLink, Outlet } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { maintenanceApi } from '@/lib/maintenance'
import { formatBytes } from '@/pages/Database/utils/formatBytes'

const TABLE_NAV_ITEMS = [
  {
    key: 'logs',
    to: '/data/logs',
    label: 'Transmissions',
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
        <div className="flex items-center justify-between gap-2 border-b border-[#1e2433] px-4 py-2.5">
          <div className="flex items-center gap-2 min-w-0">
            <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-sm border border-indigo-500/40 bg-indigo-500/15 font-mono text-[10px] font-bold tracking-tight text-indigo-300">
              DB
            </span>
            <div className="min-w-0">
              <h1 className="truncate text-sm font-semibold tracking-tight text-slate-100">
                Database
              </h1>
              <div className="font-mono text-[10px] uppercase tracking-[0.06em] text-slate-500">
                SQLite {data?.storage.journal_mode ?? 'wal'}
              </div>
            </div>
          </div>

          <button
            type="button"
            className="rounded-sm border border-[#273045] bg-[#141926] px-2 py-1 text-[11px] font-medium text-slate-300 transition hover:border-[#3a4766] hover:text-white cursor-pointer disabled:opacity-50"
            onClick={() => void overviewQuery.refetch()}
            disabled={overviewQuery.isFetching}
            title="Refresh live table counts"
          >
            {overviewQuery.isFetching ? '…' : 'Sync'}
          </button>
        </div>

        <nav
          className="flex flex-row gap-0.5 overflow-x-auto px-2 py-2 lg:flex-col lg:overflow-x-visible lg:px-2 lg:py-3"
          aria-label="Database tables"
        >
          <div className="hidden px-2.5 pb-1.5 text-[10px] font-semibold uppercase tracking-[0.08em] text-slate-500 lg:block">
            Schema
          </div>
          {TABLE_NAV_ITEMS.map((item) => {
            const count = countByKey.get(item.key)
            return (
              <NavLink
                key={item.key}
                to={item.to}
                className={({ isActive }) =>
                  `group flex shrink-0 items-center justify-between gap-2 rounded-sm border-l-2 px-2.5 py-2 text-xs transition ${
                    isActive
                      ? 'border-l-indigo-400 bg-[#151a28] text-white'
                      : 'border-l-transparent text-slate-400 hover:bg-white/[0.03] hover:text-slate-200'
                  }`
                }
              >
                <span className="flex items-center gap-2 min-w-0">
                  <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${item.dotClass}`} />
                  <span className="min-w-0">
                    <span className="block truncate font-medium">{item.label}</span>
                    <span className="hidden font-mono text-[10px] text-slate-500 lg:block">
                      {item.sqlName}
                    </span>
                  </span>
                </span>
                {count !== undefined && (
                  <span className="rounded-sm border border-white/[0.06] bg-[#141926] px-1.5 py-0.5 font-mono text-[10px] text-slate-300 tabular-nums">
                    {count.toLocaleString()}
                  </span>
                )}
              </NavLink>
            )
          })}
        </nav>

        <div className="hidden border-t border-[#1e2433] px-2 py-2.5 lg:block">
          <div className="px-2.5 pb-1.5 text-[10px] font-semibold uppercase tracking-[0.08em] text-slate-500">
            Utilities
          </div>
          <div className="space-y-0.5">
            <Link
              to="/data/entities?export=1"
              className="flex items-center justify-between rounded-sm px-2.5 py-1.5 text-xs font-medium text-emerald-300/90 transition hover:bg-emerald-500/10 hover:text-emerald-200"
            >
              <span>NER CSV Exporter</span>
              <span className="font-mono text-[10px] text-emerald-400/70">CSV</span>
            </Link>
            <Link
              to="/events/monitors"
              className="flex items-center justify-between rounded-sm px-2.5 py-1.5 text-xs font-medium text-slate-400 transition hover:bg-white/[0.03] hover:text-slate-200"
            >
              <span>Monitors</span>
              <span className="font-mono text-[10px] text-slate-500">
                {countByKey.get('monitors') ?? '—'}
              </span>
            </Link>
          </div>
        </div>

        <div
          className="mt-auto hidden border-t border-[#1e2433] bg-[#0a0c12] p-3.5 lg:block"
          aria-label="Storage and pipeline telemetry"
        >
          <div className="mb-2 text-[10px] font-semibold uppercase tracking-[0.08em] text-slate-500">
            Engine Telemetry
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
                    <span className={`rounded-sm border px-1 py-0 text-[9px] font-semibold ${nerBadge.cls}`}>
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
