import { Fragment, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { eventsApi } from '@/lib/events'
import { errorMessage } from '@/types/api'
import { useToast } from '@/context/ToastContext'
import type { SpanStoreRow } from '@/types/events'

const PAGE_SIZES = [25, 50, 100] as const

function formatTime(iso: string | null | undefined) {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleString(undefined, { dateStyle: 'short', timeStyle: 'short' })
}

function nerChips(row: SpanStoreRow) {
  const pairs: [string, string | null | undefined][] = [
    ['EVT_TYPE', row.evt_type],
    ['UNIT', row.units],
    ['ADDRESS', row.addresses],
    ['LOC', row.locations],
    ['STATUS', row.status],
    ['TIME', row.time_mentions],
  ]
  const chips: { label: string; value: string }[] = []
  for (const [label, raw] of pairs) {
    const v = (raw || '').trim()
    if (!v) continue
    for (const part of v.split(',').map((s) => s.trim()).filter(Boolean)) {
      chips.push({ label, value: part })
    }
  }
  return chips
}

function getLabelColor(label: string) {
  switch (label.toUpperCase()) {
    case 'EVT_TYPE':
      return 'bg-amber-500/15 text-amber-300 border-amber-500/30'
    case 'UNIT':
      return 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30'
    case 'LOC':
    case 'ADDRESS':
      return 'bg-sky-500/15 text-sky-300 border-sky-500/30'
    case 'STATUS':
      return 'bg-purple-500/15 text-purple-300 border-purple-500/30'
    case 'TIME':
      return 'bg-indigo-500/15 text-indigo-300 border-indigo-500/30'
    default:
      return 'bg-gray-500/15 text-gray-300 border-gray-500/30'
  }
}

function copyToClipboard(text: string, onSuccess: () => void) {
  void navigator.clipboard.writeText(text).then(onSuccess)
}

export function SpansTable() {
  const { addToast } = useToast()
  const [monitorId, setMonitorId] = useState<string>('')
  const [talkgroup, setTalkgroup] = useState<string>('')
  const [logEntryId, setLogEntryId] = useState<string>('')
  const [search, setSearch] = useState<string>('')
  const [debouncedSearch, setDebouncedSearch] = useState<string>('')
  const [sortBy, setSortBy] = useState<string>('id')
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('desc')
  const [pageSize, setPageSize] = useState<number>(50)
  const [page, setPage] = useState<number>(1)
  const [expandedId, setExpandedId] = useState<number | null>(null)
  const [jsonViewId, setJsonViewId] = useState<number | null>(null)

  useEffect(() => {
    const t = window.setTimeout(() => setDebouncedSearch(search), 400)
    return () => window.clearTimeout(t)
  }, [search])

  useEffect(() => {
    setPage(1)
  }, [monitorId, talkgroup, logEntryId, debouncedSearch, sortBy, sortOrder, pageSize])

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

  const logEntryFilter = logEntryId.trim() ? Number.parseInt(logEntryId, 10) : undefined
  const logEntryInvalid = logEntryId.trim() !== '' && !Number.isFinite(logEntryFilter)

  const listQuery = useQuery({
    queryKey: [
      'data-explorer-spans',
      page,
      pageSize,
      monitorId,
      talkgroup,
      logEntryFilter,
      debouncedSearch,
      sortBy,
      sortOrder,
    ],
    queryFn: () =>
      eventsApi.spanStore({
        monitorId: monitorId ? Number.parseInt(monitorId, 10) : undefined,
        talkgroup: talkgroup.trim() || undefined,
        logEntryId: logEntryFilter,
        q: debouncedSearch.trim() || undefined,
        sortBy,
        sortOrder,
        limit: pageSize,
        offset: (page - 1) * pageSize,
      }),
    enabled: !logEntryInvalid,
    staleTime: 5_000,
  })

  const total = listQuery.data?.total ?? 0
  const rows = listQuery.data?.items ?? []
  const totalPages = Math.max(1, Math.ceil(total / pageSize))

  const toggleSort = (col: string) => {
    if (sortBy === col) {
      setSortOrder(sortOrder === 'asc' ? 'desc' : 'asc')
    } else {
      setSortBy(col)
      setSortOrder('desc')
    }
  }

  const renderSortIndicator = (col: string) => {
    if (sortBy !== col) return <span className="ml-1 text-gray-600">↕</span>
    return <span className="ml-1 text-sky-400">{sortOrder === 'asc' ? '▲' : '▼'}</span>
  }

  return (
    <div className="ss-events-page">
      {/* Filters */}
      <div className="ss-events-debug-controls flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-3">
          <label className="flex items-center gap-2 text-xs text-gray-500" htmlFor="span-monitor">
            Monitor
          </label>
          <select
            id="span-monitor"
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

          <label className="flex items-center gap-2 text-xs text-gray-500" htmlFor="span-tg">
            Talkgroup
          </label>
          <input
            id="span-tg"
            type="search"
            className="ss-input h-8 w-36 text-xs"
            placeholder="contains…"
            value={talkgroup}
            onChange={(e) => setTalkgroup(e.target.value)}
          />

          <label className="flex items-center gap-2 text-xs text-gray-500" htmlFor="span-log">
            Log ID
          </label>
          <input
            id="span-log"
            type="text"
            inputMode="numeric"
            className="ss-input h-8 w-24 text-xs font-mono"
            placeholder="1234"
            value={logEntryId}
            onChange={(e) => setLogEntryId(e.target.value)}
          />

          <label className="flex items-center gap-2 text-xs text-gray-500" htmlFor="span-search">
            Transcript
          </label>
          <input
            id="span-search"
            type="search"
            className="ss-input h-8 min-w-[12rem] flex-1 text-xs"
            placeholder="Search transcript text…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />

          <label className="flex items-center gap-2 text-xs text-gray-500" htmlFor="span-page-size">
            Page Size
          </label>
          <select
            id="span-page-size"
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
            {total.toLocaleString()} span{total === 1 ? '' : 's'}
          </span>
        </div>

        <button
          type="button"
          className="ss-btn-ghost h-8 text-xs"
          disabled={listQuery.isFetching}
          onClick={() => void listQuery.refetch()}
        >
          Refresh
        </button>
      </div>

      {logEntryInvalid && (
        <p className="ss-form-error" role="alert">
          Log entry ID must be a valid integer.
        </p>
      )}

      {listQuery.isError && (
        <p className="ss-form-error" role="alert">
          {errorMessage(listQuery.error, 'Failed to load spans table')}
        </p>
      )}

      {listQuery.isSuccess && rows.length === 0 ? (
        <p className="ss-empty not-italic">No span_store entries match the selected filters.</p>
      ) : (
        <div className="ss-events-table-wrap overflow-x-auto">
          <table className="ss-events-table w-full text-left text-xs">
            <thead>
              <tr>
                <th className="w-8" />
                <th className="cursor-pointer select-none" onClick={() => toggleSort('id')}>
                  ID {renderSortIndicator('id')}
                </th>
                <th>Monitor</th>
                <th className="cursor-pointer select-none" onClick={() => toggleSort('log_entry_id')}>
                  Log Entry {renderSortIndicator('log_entry_id')}
                </th>
                <th className="cursor-pointer select-none" onClick={() => toggleSort('talkgroup')}>
                  Talkgroup {renderSortIndicator('talkgroup')}
                </th>
                <th>Extracted NER</th>
                <th>Transcript</th>
                <th>Linked Incidents</th>
                <th className="cursor-pointer select-none" onClick={() => toggleSort('created_at')}>
                  Created {renderSortIndicator('created_at')}
                </th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => {
                const isOpen = expandedId === row.id
                const chips = nerChips(row)
                return (
                  <Fragment key={row.id}>
                    <tr
                      className="cursor-pointer hover:bg-white/[0.03] transition-colors"
                      onClick={() => setExpandedId(isOpen ? null : row.id)}
                    >
                      <td className="text-gray-500">{isOpen ? '▼' : '▶'}</td>
                      <td className="font-mono text-gray-400">#{row.id}</td>
                      <td className="text-gray-300">
                        {monitorById.get(row.monitor_id) ?? `Monitor #${row.monitor_id}`}
                      </td>
                      <td className="font-mono">
                        {row.log_entry_id != null ? (
                          <Link
                            to="/data/logs"
                            className="text-emerald-300 hover:underline"
                            onClick={(e) => e.stopPropagation()}
                            title="View log entry in Audio Logs table"
                          >
                            #{row.log_entry_id}
                          </Link>
                        ) : (
                          '—'
                        )}
                      </td>
                      <td className="max-w-[8rem] truncate font-medium text-gray-300" title={row.talkgroup ?? ''}>
                        {row.talkgroup || '—'}
                      </td>
                      <td>
                        {chips.length === 0 ? (
                          <span className="text-gray-600">none</span>
                        ) : (
                          <div className="flex flex-wrap gap-1">
                            {chips.slice(0, 4).map((c, i) => (
                              <span
                                key={`${c.label}-${i}`}
                                className={`rounded px-1.5 py-0.5 text-[10px] font-medium border ${getLabelColor(
                                  c.label,
                                )}`}
                                title={`${c.label}: ${c.value}`}
                              >
                                {c.value}
                              </span>
                            ))}
                            {chips.length > 4 ? (
                              <span className="text-gray-500 text-[10px]">+{chips.length - 4}</span>
                            ) : null}
                          </div>
                        )}
                      </td>
                      <td className="max-w-[16rem] truncate text-gray-300">
                        {row.transcript || '—'}
                      </td>
                      <td>
                        {row.attached_event_ids.length === 0 ? (
                          <span className="text-gray-600">—</span>
                        ) : (
                          <div className="flex flex-wrap gap-1">
                            {row.attached_event_ids.map((eid) => (
                              <Link
                                key={eid}
                                to="/data/events"
                                className="font-mono text-sky-300/90 hover:underline text-[11px]"
                                onClick={(e) => e.stopPropagation()}
                                title={`Event ID: ${eid}`}
                              >
                                {eid.slice(0, 8)}
                              </Link>
                            ))}
                          </div>
                        )}
                      </td>
                      <td className="whitespace-nowrap text-gray-500">{formatTime(row.created_at)}</td>
                    </tr>

                    {isOpen ? (
                      <tr>
                        <td colSpan={9} className="border-t border-white/10 bg-black/30 p-4">
                          <div className="space-y-4">
                            <div className="flex flex-wrap items-center justify-between gap-2 border-b border-white/5 pb-2">
                              <div className="flex items-center gap-2">
                                <span className="font-mono text-xs text-sky-300">Span #{row.id}</span>
                                <span className="text-gray-500">·</span>
                                <span className="text-xs text-gray-400">
                                  Monitor: {monitorById.get(row.monitor_id) ?? row.monitor_id}
                                </span>
                                {row.log_entry_id && (
                                  <>
                                    <span className="text-gray-500">·</span>
                                    <span className="text-xs text-gray-400">Log Entry #{row.log_entry_id}</span>
                                  </>
                                )}
                              </div>
                              <div className="flex items-center gap-2">
                                <button
                                  type="button"
                                  className="ss-btn-ghost text-xs"
                                  onClick={() => setJsonViewId(jsonViewId === row.id ? null : row.id)}
                                >
                                  {jsonViewId === row.id ? 'Hide Raw JSON' : 'View Raw JSON'}
                                </button>
                                <button
                                  type="button"
                                  className="ss-btn-ghost text-xs"
                                  onClick={() => {
                                    copyToClipboard(JSON.stringify(row, null, 2), () => {
                                      addToast('Span JSON copied to clipboard', 'success')
                                    })
                                  }}
                                >
                                  Copy JSON
                                </button>
                              </div>
                            </div>

                            <div>
                              <span className="text-[11px] font-semibold uppercase tracking-wider text-gray-500">
                                Full Transcript
                              </span>
                              <p className="mt-1.5 whitespace-pre-wrap rounded-lg border border-white/10 bg-white/[0.02] p-3 text-xs leading-relaxed text-gray-200">
                                {row.transcript?.trim() || '—'}
                              </p>
                            </div>

                            {chips.length > 0 ? (
                              <div>
                                <span className="text-[11px] font-semibold uppercase tracking-wider text-gray-500">
                                  Extracted NER Observations
                                </span>
                                <div className="mt-2 flex flex-wrap gap-1.5">
                                  {chips.map((c, i) => (
                                    <span
                                      key={`${c.label}-${i}-full`}
                                      className={`rounded-md px-2 py-1 text-xs border ${getLabelColor(c.label)}`}
                                    >
                                      <span className="opacity-75 font-semibold">{c.label}:</span> {c.value}
                                    </span>
                                  ))}
                                </div>
                              </div>
                            ) : null}

                            {jsonViewId === row.id ? (
                              <div className="mt-3">
                                <span className="text-[11px] font-semibold uppercase tracking-wider text-gray-500">
                                  Raw JSON
                                </span>
                                <pre className="mt-1.5 max-h-60 overflow-auto rounded-lg border border-white/10 bg-black/60 p-3 font-mono text-xs text-sky-300">
                                  {JSON.stringify(row, null, 2)}
                                </pre>
                              </div>
                            ) : null}
                          </div>
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
            Showing {(page - 1) * pageSize + 1}–{Math.min(page * pageSize, total)} of {total.toLocaleString()} spans (Page {page} of {totalPages})
          </span>
          <div className="flex items-center gap-1.5">
            <button
              type="button"
              className="ss-btn-ghost h-7 px-2 text-xs"
              disabled={page <= 1 || listQuery.isFetching}
              onClick={() => setPage(1)}
              title="First Page"
            >
              ««
            </button>
            <button
              type="button"
              className="ss-btn-ghost h-7 px-2.5 text-xs"
              disabled={page <= 1 || listQuery.isFetching}
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
              disabled={page >= totalPages || listQuery.isFetching}
              onClick={() => setPage((p) => p + 1)}
            >
              Next
            </button>
            <button
              type="button"
              className="ss-btn-ghost h-7 px-2 text-xs"
              disabled={page >= totalPages || listQuery.isFetching}
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
