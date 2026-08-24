import { Fragment, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { eventsApi } from '@/lib/events'
import { errorMessage } from '@/types/api'
import { useToast } from '@/context/ToastContext'
import type { EntityObservationItem } from '@/types/events'

const PAGE_SIZES = [25, 50, 100] as const

function formatTime(iso: string | null | undefined) {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleString(undefined, { dateStyle: 'short', timeStyle: 'short' })
}

function getLabelBadgeClass(label: string) {
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

export function EntitiesTable() {
  const { addToast } = useToast()
  const [monitorId, setMonitorId] = useState<string>('')
  const [label, setLabel] = useState<string>('')
  const [talkgroup, setTalkgroup] = useState<string>('')
  const [logEntryId, setLogEntryId] = useState<string>('')
  const [spanStoreId, setSpanStoreId] = useState<string>('')
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
  }, [monitorId, label, talkgroup, logEntryId, spanStoreId, debouncedSearch, sortBy, sortOrder, pageSize])

  const monitorsQuery = useQuery({
    queryKey: ['events-monitors'],
    queryFn: () => eventsApi.monitors(),
    staleTime: 60_000,
  })

  const labelsQuery = useQuery({
    queryKey: ['ner-labels'],
    queryFn: () => eventsApi.nerLabels(),
    staleTime: 5 * 60_000,
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

  const spanStoreFilter = spanStoreId.trim() ? Number.parseInt(spanStoreId, 10) : undefined
  const spanStoreInvalid = spanStoreId.trim() !== '' && !Number.isFinite(spanStoreFilter)

  const listQuery = useQuery({
    queryKey: [
      'data-explorer-entities',
      page,
      pageSize,
      monitorId,
      label,
      talkgroup,
      logEntryFilter,
      spanStoreFilter,
      debouncedSearch,
      sortBy,
      sortOrder,
    ],
    queryFn: () =>
      eventsApi.entities({
        monitorId: monitorId ? Number.parseInt(monitorId, 10) : undefined,
        label: label || undefined,
        talkgroup: talkgroup.trim() || undefined,
        logEntryId: logEntryFilter,
        spanStoreId: spanStoreFilter,
        q: debouncedSearch.trim() || undefined,
        sortBy,
        sortOrder,
        limit: pageSize,
        offset: (page - 1) * pageSize,
      }),
    enabled: !logEntryInvalid && !spanStoreInvalid,
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
    return <span className="ml-1 text-emerald-400">{sortOrder === 'asc' ? '▲' : '▼'}</span>
  }

  return (
    <div className="ss-events-page">
      {/* Filters */}
      <div className="ss-events-debug-controls flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-3">
          <label className="flex items-center gap-2 text-xs text-gray-500" htmlFor="entity-monitor">
            Monitor
          </label>
          <select
            id="entity-monitor"
            className="ss-select h-8 min-w-[9rem] text-xs"
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

          <label className="flex items-center gap-2 text-xs text-gray-500" htmlFor="entity-label">
            Label
          </label>
          <select
            id="entity-label"
            className="ss-select h-8 min-w-[8rem] text-xs"
            value={label}
            onChange={(e) => setLabel(e.target.value)}
          >
            <option value="">All Labels</option>
            {(labelsQuery.data?.labels ?? ['EVT_TYPE', 'LOC', 'ADDRESS', 'UNIT', 'STATUS', 'TIME']).map((l) => (
              <option key={l} value={l}>
                {l}
              </option>
            ))}
          </select>

          <label className="flex items-center gap-2 text-xs text-gray-500" htmlFor="entity-tg">
            Talkgroup
          </label>
          <input
            id="entity-tg"
            type="search"
            className="ss-input h-8 w-32 text-xs"
            placeholder="contains…"
            value={talkgroup}
            onChange={(e) => setTalkgroup(e.target.value)}
          />

          <label className="flex items-center gap-2 text-xs text-gray-500" htmlFor="entity-span">
            Span ID
          </label>
          <input
            id="entity-span"
            type="text"
            inputMode="numeric"
            className="ss-input h-8 w-20 text-xs font-mono"
            placeholder="span"
            value={spanStoreId}
            onChange={(e) => setSpanStoreId(e.target.value)}
          />

          <label className="flex items-center gap-2 text-xs text-gray-500" htmlFor="entity-log">
            Log ID
          </label>
          <input
            id="entity-log"
            type="text"
            inputMode="numeric"
            className="ss-input h-8 w-20 text-xs font-mono"
            placeholder="log"
            value={logEntryId}
            onChange={(e) => setLogEntryId(e.target.value)}
          />

          <label className="flex items-center gap-2 text-xs text-gray-500" htmlFor="entity-search">
            Search
          </label>
          <input
            id="entity-search"
            type="search"
            className="ss-input h-8 min-w-[11rem] flex-1 text-xs"
            placeholder="Canonical or raw text…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />

          <label className="flex items-center gap-2 text-xs text-gray-500" htmlFor="entity-page-size">
            Page Size
          </label>
          <select
            id="entity-page-size"
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
            {total.toLocaleString()} observation{total === 1 ? '' : 's'}
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

      {(logEntryInvalid || spanStoreInvalid) && (
        <p className="ss-form-error" role="alert">
          Span ID and Log Entry ID must be numbers.
        </p>
      )}

      {listQuery.isError && (
        <p className="ss-form-error" role="alert">
          {errorMessage(listQuery.error, 'Failed to load entity observations')}
        </p>
      )}

      {listQuery.isSuccess && rows.length === 0 ? (
        <p className="ss-empty not-italic">No entity observations found matching the selected filters.</p>
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
                <th className="cursor-pointer select-none" onClick={() => toggleSort('label')}>
                  Label {renderSortIndicator('label')}
                </th>
                <th className="cursor-pointer select-none" onClick={() => toggleSort('canonical')}>
                  Canonical Normalized {renderSortIndicator('canonical')}
                </th>
                <th className="cursor-pointer select-none" onClick={() => toggleSort('raw')}>
                  Raw Span {renderSortIndicator('raw')}
                </th>
                <th className="cursor-pointer select-none" onClick={() => toggleSort('talkgroup')}>
                  Talkgroup {renderSortIndicator('talkgroup')}
                </th>
                <th className="cursor-pointer select-none" onClick={() => toggleSort('span_store_id')}>
                  Span ID {renderSortIndicator('span_store_id')}
                </th>
                <th className="cursor-pointer select-none" onClick={() => toggleSort('log_entry_id')}>
                  Log ID {renderSortIndicator('log_entry_id')}
                </th>
                <th className="cursor-pointer select-none" onClick={() => toggleSort('ts')}>
                  Observed {renderSortIndicator('ts')}
                </th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row: EntityObservationItem) => {
                const isOpen = expandedId === row.id
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
                      <td>
                        <span
                          className={`rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase border ${getLabelBadgeClass(
                            row.label,
                          )}`}
                        >
                          {row.label}
                        </span>
                      </td>
                      <td className="max-w-[14rem] truncate font-medium text-emerald-300/90" title={row.canonical}>
                        {row.canonical}
                      </td>
                      <td className="max-w-[14rem] truncate text-gray-300" title={row.raw}>
                        {row.raw}
                      </td>
                      <td className="max-w-[8rem] truncate text-gray-400" title={row.talkgroup ?? ''}>
                        {row.talkgroup || '—'}
                      </td>
                      <td className="font-mono">
                        <Link
                          to="/data/spans"
                          className="text-sky-300 hover:underline"
                          onClick={(e) => e.stopPropagation()}
                          title="Open in Spans table"
                        >
                          #{row.span_store_id}
                        </Link>
                      </td>
                      <td className="font-mono text-gray-400">
                        {row.log_entry_id != null ? (
                          <Link
                            to="/data/logs"
                            className="text-amber-300/90 hover:underline"
                            onClick={(e) => e.stopPropagation()}
                            title="Open in Audio Logs"
                          >
                            #{row.log_entry_id}
                          </Link>
                        ) : (
                          '—'
                        )}
                      </td>
                      <td className="whitespace-nowrap text-gray-500">{formatTime(row.ts)}</td>
                    </tr>

                    {isOpen ? (
                      <tr>
                        <td colSpan={10} className="border-t border-white/10 bg-black/30 p-4">
                          <div className="space-y-4">
                            <div className="flex flex-wrap items-center justify-between gap-2 border-b border-white/5 pb-2">
                              <div className="flex items-center gap-2">
                                <span className="font-mono text-xs text-emerald-300">Observation #{row.id}</span>
                                <span className="text-gray-500">·</span>
                                <span
                                  className={`rounded px-1.5 py-0.5 text-[10px] font-semibold border ${getLabelBadgeClass(
                                    row.label,
                                  )}`}
                                >
                                  {row.label}
                                </span>
                                <span className="text-gray-500">·</span>
                                <span className="text-xs text-gray-400">
                                  Monitor: {monitorById.get(row.monitor_id) ?? row.monitor_id}
                                </span>
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
                                      addToast('Entity observation JSON copied', 'success')
                                    })
                                  }}
                                >
                                  Copy JSON
                                </button>
                              </div>
                            </div>

                            <div className="grid gap-3 md:grid-cols-2">
                              <div className="rounded-lg border border-emerald-500/20 bg-emerald-950/20 p-3">
                                <span className="block text-[10px] font-semibold uppercase tracking-wider text-emerald-400">
                                  Canonical / Normalized Entity
                                </span>
                                <p className="mt-1 font-mono text-sm font-medium text-emerald-200 break-words">
                                  {row.canonical}
                                </p>
                                <span className="mt-2 block text-[11px] text-gray-400">
                                  Canonical representation produced by normalize_entity() for analytics & indexing.
                                </span>
                              </div>

                              <div className="rounded-lg border border-white/10 bg-white/[0.02] p-3">
                                <span className="block text-[10px] font-semibold uppercase tracking-wider text-gray-400">
                                  Raw Model Span
                                </span>
                                <p className="mt-1 font-mono text-sm text-gray-200 break-words">
                                  {row.raw}
                                </p>
                                <span className="mt-2 block text-[11px] text-gray-500">
                                  Original text span identified directly by the GLiNER NER model.
                                </span>
                              </div>
                            </div>

                            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs">
                              <div className="rounded-md border border-white/5 bg-white/[0.02] p-2">
                                <span className="block text-[10px] uppercase text-gray-500">Talkgroup</span>
                                <span className="mt-0.5 block font-medium text-gray-200">{row.talkgroup || '—'}</span>
                              </div>
                              <div className="rounded-md border border-white/5 bg-white/[0.02] p-2">
                                <span className="block text-[10px] uppercase text-gray-500">Span Store ID</span>
                                <span className="mt-0.5 block font-mono text-sky-300">#{row.span_store_id}</span>
                              </div>
                              <div className="rounded-md border border-white/5 bg-white/[0.02] p-2">
                                <span className="block text-[10px] uppercase text-gray-500">Log Entry ID</span>
                                <span className="mt-0.5 block font-mono text-amber-300">
                                  {row.log_entry_id ? `#${row.log_entry_id}` : '—'}
                                </span>
                              </div>
                              <div className="rounded-md border border-white/5 bg-white/[0.02] p-2">
                                <span className="block text-[10px] uppercase text-gray-500">Timestamp</span>
                                <span className="mt-0.5 block text-gray-300">{formatTime(row.ts)}</span>
                              </div>
                            </div>

                            {jsonViewId === row.id ? (
                              <div className="mt-3">
                                <span className="text-[11px] font-semibold uppercase tracking-wider text-gray-500">
                                  Raw JSON
                                </span>
                                <pre className="mt-1.5 max-h-60 overflow-auto rounded-lg border border-white/10 bg-black/60 p-3 font-mono text-xs text-emerald-300">
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
            Showing {(page - 1) * pageSize + 1}–{Math.min(page * pageSize, total)} of {total.toLocaleString()} observations (Page {page} of {totalPages})
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
