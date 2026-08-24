import { Fragment, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { downloadEventsExportHeaders, eventsApi } from '@/lib/events'
import { errorMessage } from '@/types/api'
import { useToast } from '@/context/ToastContext'
import type { EventDetailResponse, EventListItem } from '@/types/events'

const PAGE_SIZES = [25, 50, 100] as const

function formatTime(iso: string | null | undefined) {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleString(undefined, { dateStyle: 'short', timeStyle: 'short' })
}

function copyToClipboard(text: string, onSuccess: () => void) {
  void navigator.clipboard.writeText(text).then(onSuccess)
}

function EventDetailSection({ eventId, event }: { eventId: string; event: EventListItem }) {
  const { addToast } = useToast()
  const [activeTab, setActiveTab] = useState<'overview' | 'transcripts' | 'json'>('overview')

  const detailQuery = useQuery<EventDetailResponse>({
    queryKey: ['event-detail', eventId],
    queryFn: () => eventsApi.detail(eventId),
    staleTime: 10_000,
  })

  const detail = detailQuery.data
  const rawPayload = detail ? detail : event

  return (
    <div className="border-t border-white/10 bg-black/30 p-4">
      {/* Sub tabs inside drawer */}
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3 border-b border-white/10 pb-3">
        <div className="flex gap-2">
          <button
            type="button"
            className={`rounded-md px-3 py-1 text-xs font-medium transition ${
              activeTab === 'overview'
                ? 'bg-indigo-500/20 text-indigo-200 border border-indigo-500/30'
                : 'text-gray-400 hover:text-gray-200'
            }`}
            onClick={() => setActiveTab('overview')}
          >
            Overview & Summary
          </button>
          <button
            type="button"
            className={`rounded-md px-3 py-1 text-xs font-medium transition ${
              activeTab === 'transcripts'
                ? 'bg-indigo-500/20 text-indigo-200 border border-indigo-500/30'
                : 'text-gray-400 hover:text-gray-200'
            }`}
            onClick={() => setActiveTab('transcripts')}
          >
            Linked Transcripts ({detail?.transcripts.length ?? event.spans_attached})
          </button>
          <button
            type="button"
            className={`rounded-md px-3 py-1 text-xs font-medium transition ${
              activeTab === 'json'
                ? 'bg-indigo-500/20 text-indigo-200 border border-indigo-500/30'
                : 'text-gray-400 hover:text-gray-200'
            }`}
            onClick={() => setActiveTab('json')}
          >
            Raw JSON Payload
          </button>
        </div>

        <div className="flex items-center gap-2">
          <button
            type="button"
            className="ss-btn-ghost text-xs"
            onClick={() => {
              copyToClipboard(JSON.stringify(rawPayload, null, 2), () => {
                addToast('Event JSON copied to clipboard', 'success')
              })
            }}
          >
            Copy JSON
          </button>
          <Link
            to="/events"
            className="ss-btn-ghost text-xs text-sky-300 hover:text-sky-200"
          >
            View in Incidents →
          </Link>
        </div>
      </div>

      {activeTab === 'overview' && (
        <div className="grid gap-4 md:grid-cols-2">
          <div className="space-y-3">
            <div>
              <span className="text-[11px] font-semibold uppercase tracking-wider text-gray-500">Summary</span>
              <p className="mt-1 rounded-md border border-white/5 bg-white/[0.02] p-3 text-xs leading-relaxed text-gray-200">
                {event.summary || 'No summary generated yet.'}
              </p>
            </div>

            <div>
              <span className="text-[11px] font-semibold uppercase tracking-wider text-gray-500">Trigger Transcript</span>
              <p className="mt-1 rounded-md border border-white/5 bg-white/[0.02] p-3 font-mono text-xs text-gray-300">
                {event.original_transcription || '—'}
              </p>
            </div>
          </div>

          <div className="space-y-3">
            <div className="grid grid-cols-2 gap-3 text-xs">
              <div className="rounded-md border border-white/5 bg-white/[0.02] p-2.5">
                <span className="block text-[10px] uppercase text-gray-500">Status Detail</span>
                <span className="mt-0.5 block font-medium text-gray-200">{event.status_detail || '—'}</span>
              </div>
              <div className="rounded-md border border-white/5 bg-white/[0.02] p-2.5">
                <span className="block text-[10px] uppercase text-gray-500">Broadcast Type</span>
                <span className="mt-0.5 block font-medium text-gray-200">{event.broadcast_type || '—'}</span>
              </div>
              <div className="rounded-md border border-white/5 bg-white/[0.02] p-2.5">
                <span className="block text-[10px] uppercase text-gray-500">Resolved Address</span>
                <span className="mt-0.5 block font-medium text-gray-200">{event.resolved_address || '—'}</span>
              </div>
              <div className="rounded-md border border-white/5 bg-white/[0.02] p-2.5">
                <span className="block text-[10px] uppercase text-gray-500">Coordinates</span>
                <span className="mt-0.5 block font-mono text-gray-200">
                  {event.latitude != null && event.longitude != null
                    ? `${event.latitude.toFixed(5)}, ${event.longitude.toFixed(5)}`
                    : '—'}
                </span>
              </div>
            </div>

            {event.units ? (
              <div>
                <span className="text-[11px] font-semibold uppercase tracking-wider text-gray-500">Units Mentioned</span>
                <div className="mt-1 flex flex-wrap gap-1">
                  {event.units.split(',').map((u, i) => (
                    <span
                      key={i}
                      className="rounded bg-emerald-500/10 px-2 py-0.5 font-mono text-xs text-emerald-300 border border-emerald-500/20"
                    >
                      {u.trim()}
                    </span>
                  ))}
                </div>
              </div>
            ) : null}
          </div>
        </div>
      )}

      {activeTab === 'transcripts' && (
        <div className="space-y-3">
          {detailQuery.isLoading ? (
            <p className="text-xs text-gray-500">Loading linked audio transcripts…</p>
          ) : detail?.transcripts.length === 0 ? (
            <p className="text-xs text-gray-500">No transcripts linked to this event.</p>
          ) : (
            <div className="space-y-2 max-h-96 overflow-y-auto pr-1">
              {detail?.transcripts.map((t, i) => (
                <div key={i} className="rounded-lg border border-white/10 bg-white/[0.02] p-3 text-xs">
                  <div className="flex flex-wrap items-center justify-between gap-2 border-b border-white/5 pb-2">
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-gray-400">Log #{t.log_entry_id}</span>
                      <span className="rounded bg-indigo-500/10 px-1.5 py-0.5 text-[10px] text-indigo-300">
                        {t.talkgroup}
                      </span>
                      {t.is_trigger ? (
                        <span className="rounded bg-amber-500/15 px-1.5 py-0.5 text-[10px] font-semibold text-amber-200">
                          Trigger
                        </span>
                      ) : null}
                    </div>
                    <span className="text-gray-500">{formatTime(t.timestamp)}</span>
                  </div>

                  <p className="mt-2 text-gray-200 whitespace-pre-wrap">{t.transcript}</p>

                  {t.llm_reason ? (
                    <div className="mt-2 text-[11px] text-gray-400 italic">
                      <span className="text-gray-500">LLM Reasoning:</span> {t.llm_reason}
                    </div>
                  ) : null}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {activeTab === 'json' && (
        <pre className="max-h-[32rem] overflow-auto rounded-lg border border-white/10 bg-black/60 p-4 font-mono text-xs leading-relaxed text-emerald-300">
          {JSON.stringify(rawPayload, null, 2)}
        </pre>
      )}
    </div>
  )
}

export function EventsTable() {
  const { addToast } = useToast()
  const [monitorId, setMonitorId] = useState<string>('')
  const [status, setStatus] = useState<string>('')
  const [search, setSearch] = useState<string>('')
  const [debouncedSearch, setDebouncedSearch] = useState<string>('')
  const [sortBy, setSortBy] = useState<string>('created_at')
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('desc')
  const [pageSize, setPageSize] = useState<number>(50)
  const [page, setPage] = useState<number>(1)
  const [expandedId, setExpandedId] = useState<string | null>(null)
  const [isExporting, setIsExporting] = useState<boolean>(false)

  useEffect(() => {
    const t = window.setTimeout(() => setDebouncedSearch(search), 400)
    return () => window.clearTimeout(t)
  }, [search])

  useEffect(() => {
    setPage(1)
  }, [monitorId, status, debouncedSearch, sortBy, sortOrder, pageSize])

  const monitorsQuery = useQuery({
    queryKey: ['events-monitors'],
    queryFn: () => eventsApi.monitors(),
    staleTime: 60_000,
  })

  const monitorById = useMemo(() => {
    const m = new Map<number, string>()
    for (const row of monitorsQuery.data ?? []) {
      m.set(row.id, row.name)
    }
    return m
  }, [monitorsQuery.data])

  const eventsQuery = useQuery({
    queryKey: [
      'data-explorer-events',
      page,
      pageSize,
      monitorId,
      status,
      debouncedSearch,
      sortBy,
      sortOrder,
    ],
    queryFn: () =>
      eventsApi.list({
        monitorId: monitorId ? Number.parseInt(monitorId, 10) : undefined,
        status: status || undefined,
        q: debouncedSearch.trim() || undefined,
        sortBy,
        sortOrder,
        limit: pageSize,
        offset: (page - 1) * pageSize,
      }),
    staleTime: 5_000,
  })

  const total = eventsQuery.data?.total ?? 0
  const rows = eventsQuery.data?.items ?? []
  const totalPages = Math.max(1, Math.ceil(total / pageSize))

  const toggleSort = (col: string) => {
    if (sortBy === col) {
      setSortOrder(sortOrder === 'asc' ? 'desc' : 'asc')
    } else {
      setSortBy(col)
      setSortOrder('desc')
    }
  }

  const handleExport = async () => {
    setIsExporting(true)
    try {
      await downloadEventsExportHeaders({
        monitorId: monitorId ? Number.parseInt(monitorId, 10) : undefined,
        status: status || undefined,
      })
      addToast('Events exported successfully', 'success')
    } catch (e) {
      addToast(errorMessage(e, 'Failed to export events'), 'error')
    } finally {
      setIsExporting(false)
    }
  }

  const renderSortIndicator = (col: string) => {
    if (sortBy !== col) return <span className="ml-1 text-gray-600">↕</span>
    return <span className="ml-1 text-indigo-400">{sortOrder === 'asc' ? '▲' : '▼'}</span>
  }

  return (
    <div className="ss-events-page">
      {/* Filter Controls */}
      <div className="ss-events-debug-controls flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-3">
          <label className="flex items-center gap-2 text-xs text-gray-500" htmlFor="event-monitor">
            Monitor
          </label>
          <select
            id="event-monitor"
            className="ss-select h-8 min-w-[10rem] text-xs"
            value={monitorId}
            onChange={(e) => setMonitorId(e.target.value)}
          >
            <option value="">All Monitors</option>
            {(monitorsQuery.data ?? []).map((m) => (
              <option key={m.id} value={String(m.id)}>
                {m.name}
              </option>
            ))}
          </select>

          <label className="flex items-center gap-2 text-xs text-gray-500" htmlFor="event-status">
            Status
          </label>
          <select
            id="event-status"
            className="ss-select h-8 w-28 text-xs"
            value={status}
            onChange={(e) => setStatus(e.target.value)}
          >
            <option value="">All Statuses</option>
            <option value="open">Open</option>
            <option value="closed">Closed</option>
          </select>

          <label className="flex items-center gap-2 text-xs text-gray-500" htmlFor="event-search">
            Search
          </label>
          <input
            id="event-search"
            type="search"
            className="ss-input h-8 min-w-[12rem] flex-1 text-xs"
            placeholder="Type, location, units, summary…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />

          <label className="flex items-center gap-2 text-xs text-gray-500" htmlFor="event-page-size">
            Page Size
          </label>
          <select
            id="event-page-size"
            className="ss-select h-8 text-xs"
            value={String(pageSize)}
            onChange={(e) => setPageSize(Number(e.target.value))}
          >
            {PAGE_SIZES.map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </select>

          <span className="ss-events-pill-tiny">
            {total.toLocaleString()} event{total === 1 ? '' : 's'}
          </span>
        </div>

        <div className="flex items-center gap-2">
          <button
            type="button"
            className="ss-btn-ghost h-8 text-xs"
            disabled={eventsQuery.isFetching}
            onClick={() => void eventsQuery.refetch()}
          >
            Refresh
          </button>
          <button
            type="button"
            className="ss-btn-ghost h-8 text-xs"
            disabled={isExporting}
            onClick={() => void handleExport()}
          >
            {isExporting ? 'Exporting…' : 'Export CSV'}
          </button>
        </div>
      </div>

      {eventsQuery.isError && (
        <p className="ss-form-error" role="alert">
          {errorMessage(eventsQuery.error, 'Failed to load events table')}
        </p>
      )}

      {eventsQuery.isSuccess && rows.length === 0 ? (
        <p className="ss-empty not-italic">No events match the selected filters.</p>
      ) : (
        <div className="ss-events-table-wrap overflow-x-auto">
          <table className="ss-events-table w-full text-left text-xs">
            <thead>
              <tr>
                <th className="w-8" />
                <th className="cursor-pointer select-none" onClick={() => toggleSort('event_id')}>
                  Event ID {renderSortIndicator('event_id')}
                </th>
                <th className="cursor-pointer select-none" onClick={() => toggleSort('status')}>
                  Status {renderSortIndicator('status')}
                </th>
                <th>Monitor</th>
                <th className="cursor-pointer select-none" onClick={() => toggleSort('event_type')}>
                  Type {renderSortIndicator('event_type')}
                </th>
                <th className="cursor-pointer select-none" onClick={() => toggleSort('location')}>
                  Location {renderSortIndicator('location')}
                </th>
                <th>Units</th>
                <th>Spans</th>
                <th className="cursor-pointer select-none" onClick={() => toggleSort('created_at')}>
                  Created {renderSortIndicator('created_at')}
                </th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => {
                const isOpen = expandedId === row.event_id
                return (
                  <Fragment key={row.event_id}>
                    <tr
                      className="cursor-pointer hover:bg-white/[0.03] transition-colors"
                      onClick={() => setExpandedId(isOpen ? null : row.event_id)}
                    >
                      <td className="text-gray-500">{isOpen ? '▼' : '▶'}</td>
                      <td className="font-mono text-indigo-300/90 font-medium">
                        {row.event_id.length > 12 ? row.event_id.slice(0, 12) + '…' : row.event_id}
                      </td>
                      <td>
                        <span
                          className={`rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase ${
                            row.status === 'open'
                              ? 'bg-emerald-500/15 text-emerald-300 border border-emerald-500/20'
                              : 'bg-gray-500/15 text-gray-400 border border-gray-500/20'
                          }`}
                        >
                          {row.status}
                        </span>
                      </td>
                      <td className="text-gray-300">
                        {monitorById.get(row.monitor_id) ?? `Monitor #${row.monitor_id}`}
                      </td>
                      <td>
                        <div className="flex flex-col">
                          <span className="font-medium text-gray-200">{row.event_type || '—'}</span>
                          {row.broadcast_type ? (
                            <span className="text-[10px] text-amber-300/80">{row.broadcast_type}</span>
                          ) : null}
                        </div>
                      </td>
                      <td className="max-w-[14rem] truncate text-gray-300" title={row.location || ''}>
                        {row.location || '—'}
                      </td>
                      <td className="max-w-[8rem] truncate text-gray-400" title={row.units || ''}>
                        {row.units || '—'}
                      </td>
                      <td>
                        <span className="rounded bg-white/5 px-2 py-0.5 font-mono text-[11px] text-gray-300">
                          {row.spans_attached}
                        </span>
                      </td>
                      <td className="whitespace-nowrap text-gray-500">{formatTime(row.created_at)}</td>
                    </tr>

                    {isOpen ? (
                      <tr>
                        <td colSpan={9} className="p-0">
                          <EventDetailSection eventId={row.event_id} event={row} />
                        </td>
                      </tr>
                    ) : null}
                  </Fragment>
                )
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* Pagination Controls */}
      {total > 0 ? (
        <div className="mt-4 flex flex-wrap items-center justify-between gap-3 text-xs text-gray-500">
          <span>
            Showing {(page - 1) * pageSize + 1}–{Math.min(page * pageSize, total)} of {total.toLocaleString()} events (Page {page} of {totalPages})
          </span>
          <div className="flex items-center gap-1.5">
            <button
              type="button"
              className="ss-btn-ghost h-7 px-2 text-xs"
              disabled={page <= 1 || eventsQuery.isFetching}
              onClick={() => setPage(1)}
              title="First Page"
            >
              ««
            </button>
            <button
              type="button"
              className="ss-btn-ghost h-7 px-2.5 text-xs"
              disabled={page <= 1 || eventsQuery.isFetching}
              onClick={() => setPage((p) => Math.max(1, p - 1))}
            >
              Previous
            </button>
            <span className="px-2 font-mono text-gray-400">
              {page} / {totalPages}
            </span>
            <button
              type="button"
              className="ss-btn-ghost h-7 px-2.5 text-xs"
              disabled={page >= totalPages || eventsQuery.isFetching}
              onClick={() => setPage((p) => p + 1)}
            >
              Next
            </button>
            <button
              type="button"
              className="ss-btn-ghost h-7 px-2 text-xs"
              disabled={page >= totalPages || eventsQuery.isFetching}
              onClick={() => setPage(totalPages)}
              title="Last Page"
            >
              »»
            </button>
          </div>
        </div>
      ) : null}
    </div>
  )
}
