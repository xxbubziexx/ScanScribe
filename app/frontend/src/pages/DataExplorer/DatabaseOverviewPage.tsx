import { Link, useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { maintenanceApi } from '@/lib/maintenance'
import { formatBytes } from '@/pages/Database/utils/formatBytes'
import { errorMessage } from '@/types/api'

function formatDurationHours(seconds: number): string {
  if (!seconds || seconds <= 0) return '0.0 hrs'
  if (seconds < 3600) return `${(seconds / 60).toFixed(1)} min`
  return `${(seconds / 3600).toFixed(1)} hrs`
}

function formatDateSpan(oldest: string | null, newest: string | null): string {
  if (!oldest && !newest) return 'No records'
  const fmt = (raw: string | null) => {
    if (!raw) return '—'
    if (/^\d{4}-\d{2}-\d{2}$/.test(raw)) return raw
    const d = new Date(raw)
    return Number.isNaN(d.getTime()) ? raw.slice(0, 10) : d.toLocaleDateString()
  }
  const left = fmt(oldest)
  const right = fmt(newest)
  return left === right ? left : `${left} → ${right}`
}

function labelBarColor(label: string): string {
  switch (label.toUpperCase()) {
    case 'EVT_TYPE':
      return 'bg-amber-400/80'
    case 'UNIT':
      return 'bg-emerald-400/80'
    case 'LOC':
    case 'ADDRESS':
      return 'bg-sky-400/80'
    case 'STATUS':
      return 'bg-purple-400/80'
    case 'TIME':
      return 'bg-indigo-400/80'
    default:
      return 'bg-gray-400/80'
  }
}

export function DatabaseOverviewPage() {
  const navigate = useNavigate()

  const overviewQuery = useQuery({
    queryKey: ['database-overview'],
    queryFn: () => maintenanceApi.overview(),
    staleTime: 15_000,
  })

  const data = overviewQuery.data

  if (overviewQuery.isLoading) {
    return (
      <div className="space-y-4">
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {[0, 1, 2, 3].map((idx) => (
            <div
              key={idx}
              className="h-28 animate-pulse rounded-xl border border-white/10 bg-white/[0.02]"
            />
          ))}
        </div>
        <div className="h-48 animate-pulse rounded-xl border border-white/10 bg-white/[0.02]" />
      </div>
    )
  }

  if (overviewQuery.isError || !data) {
    return (
      <div className="rounded-xl border border-red-500/30 bg-red-500/10 p-4 text-sm text-red-200">
        <p className="font-medium">Failed to load database overview</p>
        <p className="mt-1 text-xs text-red-300/80">
          {errorMessage(overviewQuery.error, 'Unknown error')}
        </p>
        <button
          type="button"
          className="ss-btn-ghost mt-3 text-xs"
          onClick={() => void overviewQuery.refetch()}
        >
          Retry
        </button>
      </div>
    )
  }

  const { storage, tables, ner, daily_volume, top_talkgroups_24h } = data
  const maxDailyCount = Math.max(1, ...daily_volume.map((d) => d.count))
  const maxLabelCount = Math.max(1, ...ner.labels.map((l) => l.total_count))
  const totalLogs = tables.find((t) => t.key === 'logs')?.row_count ?? ner.total_logs

  const nerModeBadge = !ner.pipeline_enabled
    ? { text: 'Disabled', cls: 'border-white/15 bg-white/5 text-gray-400' }
    : ner.ner_only
      ? { text: 'NER-Only', cls: 'border-emerald-500/30 bg-emerald-500/15 text-emerald-300' }
      : { text: 'Full Pipeline', cls: 'border-indigo-500/30 bg-indigo-500/15 text-indigo-300' }

  return (
    <div className="space-y-6">
      {/* Toolbar */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-2 text-xs text-gray-400">
          <span>
            Snapshot generated{' '}
            <span className="font-mono text-gray-300">
              {new Date(data.generated_at).toLocaleTimeString()}
            </span>
          </span>
          <span className="text-gray-600">·</span>
          <span className="font-mono uppercase text-[11px] text-gray-400">
            SQLite {storage.journal_mode}
          </span>
          <span className="text-gray-600">·</span>
          <span className="font-mono text-[11px] text-gray-400">
            Audio layout: {storage.audio_layout}
          </span>
        </div>

        <div className="flex items-center gap-2">
          <Link
            to="/data/entities?export=1"
            className="ss-btn-ghost h-8 px-3 text-xs flex items-center"
          >
            Export NER CSV
          </Link>
          <button
            type="button"
            className="ss-btn-ghost h-8 px-3 text-xs cursor-pointer"
            disabled={overviewQuery.isFetching}
            onClick={() => void overviewQuery.refetch()}
          >
            {overviewQuery.isFetching ? 'Refreshing…' : 'Refresh'}
          </button>
        </div>
      </div>

      {/* Top 4 KPI Cards */}
      <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4" aria-label="Database KPIs">
        <div className="rounded-xl border border-white/10 bg-white/[0.02] p-4">
          <div className="flex items-center justify-between text-[11px] font-semibold uppercase tracking-wider text-gray-400">
            <span>Audio Logs</span>
            <span className="font-mono text-amber-300">+{data.logs_last_24h.toLocaleString()} / 24h</span>
          </div>
          <div className="mt-2 font-mono text-2xl font-bold text-gray-100">
            {totalLogs.toLocaleString()}
          </div>
          <div className="mt-1 text-xs text-gray-500">
            {formatDurationHours(data.total_audio_duration_seconds)} total captured audio
          </div>
        </div>

        <div className="rounded-xl border border-white/10 bg-white/[0.02] p-4">
          <div className="flex items-center justify-between text-[11px] font-semibold uppercase tracking-wider text-gray-400">
            <span>SQLite Footprint</span>
            <span className="rounded border border-white/10 bg-white/5 px-1.5 py-0.5 font-mono text-[10px] uppercase text-gray-300">
              {storage.journal_mode}
            </span>
          </div>
          <div className="mt-2 font-mono text-2xl font-bold text-gray-100">
            {formatBytes(storage.total_sqlite_bytes)}
          </div>
          <div className="mt-1 text-xs text-gray-500">
            DB {formatBytes(storage.db_bytes)} · WAL {formatBytes(storage.wal_bytes)} · Free{' '}
            {formatBytes(storage.reclaimable_bytes)}
          </div>
        </div>

        <div className="rounded-xl border border-white/10 bg-white/[0.02] p-4">
          <div className="flex items-center justify-between text-[11px] font-semibold uppercase tracking-wider text-gray-400">
            <span>Audio Storage</span>
            <span className="font-mono text-gray-400">
              {storage.retention_days > 0 ? `${storage.retention_days}d retention` : 'Retention off'}
            </span>
          </div>
          <div className="mt-2 font-mono text-2xl font-bold text-gray-100">
            {formatBytes(storage.audio_bytes)}
          </div>
          <div className="mt-1 text-xs text-gray-500">
            {storage.audio_files_count.toLocaleString()} saved files · {storage.audio_layout}
          </div>
        </div>

        <div className="rounded-xl border border-white/10 bg-white/[0.02] p-4">
          <div className="flex items-center justify-between text-[11px] font-semibold uppercase tracking-wider text-gray-400">
            <span>NER Coverage</span>
            <span className={`rounded border px-1.5 py-0.5 text-[10px] font-semibold ${nerModeBadge.cls}`}>
              {nerModeBadge.text}
            </span>
          </div>
          <div className="mt-2 font-mono text-2xl font-bold text-gray-100">
            {ner.coverage_pct.toFixed(1)}%
          </div>
          <div className="mt-1 text-xs text-gray-500">
            {ner.total_observations.toLocaleString()} entities across{' '}
            {ner.covered_logs.toLocaleString()} logs
          </div>
        </div>
      </section>

      {/* Table Inventory */}
      <section aria-label="Table inventory">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-xs font-semibold uppercase tracking-wider text-gray-400">
            Table Inventory
          </h2>
          <span className="text-xs text-gray-500">Click any table to browse and filter rows</span>
        </div>

        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {tables.map((tbl) => (
            <Link
              key={tbl.key}
              to={tbl.route}
              className="group rounded-xl border border-white/10 bg-white/[0.02] p-4 transition hover:border-indigo-500/40 hover:bg-indigo-500/[0.04]"
            >
              <div className="flex items-start justify-between gap-2">
                <div>
                  <div className="text-sm font-semibold text-gray-200 group-hover:text-white">
                    {tbl.label}
                  </div>
                  <div className="mt-1 font-mono text-xl font-bold text-gray-100">
                    {tbl.row_count.toLocaleString()}
                  </div>
                </div>
                {tbl.secondary_label && tbl.secondary_value != null && (
                  <div className="text-right">
                    <div className="text-[10px] uppercase tracking-wider text-gray-500">
                      {tbl.secondary_label}
                    </div>
                    <div className="mt-0.5 font-mono text-xs font-semibold text-indigo-300">
                      {tbl.secondary_value}
                    </div>
                  </div>
                )}
              </div>

              <div className="mt-3 flex items-center justify-between border-t border-white/5 pt-2.5 text-[11px] text-gray-500">
                <span className="truncate font-mono">{formatDateSpan(tbl.oldest, tbl.newest)}</span>
                <span className="text-indigo-400 opacity-80 group-hover:opacity-100">Open →</span>
              </div>
            </Link>
          ))}
        </div>
      </section>

      {/* NER Distribution + Ingest Telemetry */}
      <section className="grid gap-4 lg:grid-cols-2">
        {/* NER Entity Distribution */}
        <div className="rounded-xl border border-white/10 bg-white/[0.02] p-4">
          <div className="mb-4 flex flex-wrap items-center justify-between gap-2 border-b border-white/5 pb-3">
            <div>
              <h2 className="text-sm font-semibold text-gray-200">NER Entity Breakdown</h2>
              <p className="text-xs text-gray-500">
                {ner.total_spans.toLocaleString()} spans ·{' '}
                {ner.ner_loaded ? 'Model loaded in memory' : 'Model not loaded'}
              </p>
            </div>
            <Link
              to="/data/entities?export=1"
              className="ss-btn-ghost h-7 px-2.5 text-xs flex items-center"
            >
              Export Raw CSV
            </Link>
          </div>

          {ner.labels.length === 0 ? (
            <p className="py-6 text-center text-xs text-gray-500">
              No NER observations recorded yet.
            </p>
          ) : (
            <div className="space-y-3">
              {ner.labels.map((item) => {
                const widthPct = Math.max(4, Math.round((item.total_count / maxLabelCount) * 100))
                return (
                  <button
                    key={item.label}
                    type="button"
                    onClick={() => navigate(`/data/entities?label=${encodeURIComponent(item.label)}`)}
                    className="block w-full text-left group cursor-pointer"
                    title={`Browse ${item.label} observations`}
                  >
                    <div className="flex items-center justify-between text-xs mb-1">
                      <div className="flex items-center gap-2">
                        <span className="font-mono font-semibold text-gray-200 group-hover:text-indigo-300">
                          {item.label}
                        </span>
                        <span className="text-[11px] text-gray-500">
                          {item.unique_raw_count.toLocaleString()} unique
                        </span>
                      </div>
                      <span className="font-mono text-gray-300">
                        {item.total_count.toLocaleString()}{' '}
                        <span className="text-gray-500">({item.pct_of_total.toFixed(1)}%)</span>
                      </span>
                    </div>
                    <div className="h-2 w-full overflow-hidden rounded-full bg-white/5">
                      <div
                        className={`h-full rounded-full transition-all ${labelBarColor(item.label)}`}
                        style={{ width: `${widthPct}%` }}
                      />
                    </div>
                  </button>
                )
              })}
            </div>
          )}
        </div>

        {/* 7-Day Ingest Volume & Top 24h Talkgroups */}
        <div className="rounded-xl border border-white/10 bg-white/[0.02] p-4 space-y-5">
          <div>
            <div className="mb-3 flex items-center justify-between border-b border-white/5 pb-3">
              <div>
                <h2 className="text-sm font-semibold text-gray-200">7-Day Ingest Volume</h2>
                <p className="text-xs text-gray-500">Active transcriptions per local capture date</p>
              </div>
              <Link to="/data/logs" className="text-xs text-indigo-400 hover:text-indigo-300">
                Browse Logs →
              </Link>
            </div>

            <div className="grid grid-cols-7 items-end gap-2 h-28 pt-2">
              {daily_volume.map((pt) => {
                const heightPct = pt.count > 0 ? Math.max(8, Math.round((pt.count / maxDailyCount) * 100)) : 2
                return (
                  <div
                    key={pt.date}
                    className="flex flex-col items-center justify-end h-full gap-1"
                    title={`${pt.date}: ${pt.count.toLocaleString()} logs`}
                  >
                    <span className="font-mono text-[10px] text-gray-400">
                      {pt.count > 0 ? pt.count.toLocaleString() : '0'}
                    </span>
                    <div className="w-full flex-1 flex items-end">
                      <div
                        className={`w-full rounded-t ${
                          pt.count > 0 ? 'bg-indigo-500/70' : 'bg-white/10'
                        }`}
                        style={{ height: `${heightPct}%` }}
                      />
                    </div>
                    <span className="font-mono text-[10px] text-gray-500">
                      {pt.date.slice(5)}
                    </span>
                  </div>
                )
              })}
            </div>
          </div>

          <div className="border-t border-white/5 pt-4">
            <h3 className="mb-2.5 text-xs font-semibold uppercase tracking-wider text-gray-400">
              Top Talkgroups (Last 24h)
            </h3>
            {top_talkgroups_24h.length === 0 ? (
              <p className="text-xs text-gray-500">No transmissions logged in the last 24 hours.</p>
            ) : (
              <div className="space-y-1.5 max-h-52 overflow-y-auto pr-1">
                {top_talkgroups_24h.map((tg) => (
                  <button
                    key={tg.talkgroup}
                    type="button"
                    onClick={() =>
                      navigate(`/data/logs?talkgroup=${encodeURIComponent(tg.talkgroup)}`)
                    }
                    className="flex w-full items-center justify-between rounded-lg border border-white/5 bg-black/20 px-3 py-1.5 text-xs transition hover:border-indigo-500/30 hover:bg-indigo-500/10 cursor-pointer"
                  >
                    <span className="truncate font-medium text-indigo-200">{tg.talkgroup}</span>
                    <span className="shrink-0 font-mono text-gray-400">
                      {tg.count.toLocaleString()} clips · {(tg.duration_seconds / 60).toFixed(1)}m
                    </span>
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>
      </section>
    </div>
  )
}
