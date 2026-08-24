import { Fragment, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { eventsApi } from '../../lib/events'
import { errorMessage } from '../../types/api'
import type { SpanStoreRow } from '../../types/events'

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

function transcriptPreview(text: string | null | undefined, max = 120) {
  const t = (text || '').trim()
  if (!t) return '—'
  return t.length > max ? `${t.slice(0, max)}…` : t
}

export function EventsSpanStorePage() {
  const [monitorId, setMonitorId] = useState('')
  const [talkgroup, setTalkgroup] = useState('')
  const [logEntryId, setLogEntryId] = useState('')
  const [search, setSearch] = useState('')
  const [debouncedSearch, setDebouncedSearch] = useState('')
  const [pageSize, setPageSize] = useState<number>(50)
  const [page, setPage] = useState(1)
  const [expandedId, setExpandedId] = useState<number | null>(null)

  useEffect(() => {
    const t = window.setTimeout(() => setDebouncedSearch(search), 400)
    return () => window.clearTimeout(t)
  }, [search])

  useEffect(() => {
    setPage(1)
  }, [monitorId, talkgroup, logEntryId, debouncedSearch, pageSize])

  useEffect(() => {
    setExpandedId(null)
  }, [page, pageSize, monitorId, talkgroup, logEntryId, debouncedSearch])

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
      'events-span-store',
      page,
      pageSize,
      monitorId,
      talkgroup,
      logEntryFilter,
      debouncedSearch,
    ],
    queryFn: () =>
      eventsApi.spanStore({
        monitorId: monitorId ? Number.parseInt(monitorId, 10) : undefined,
        talkgroup: talkgroup.trim() || undefined,
        logEntryId: logEntryFilter,
        q: debouncedSearch.trim() || undefined,
        limit: pageSize,
        offset: (page - 1) * pageSize,
      }),
    enabled: !logEntryInvalid,
    staleTime: 5_000,
  })

  const total = listQuery.data?.total ?? 0
  const rows = listQuery.data?.items ?? []
  const totalPages = Math.max(1, Math.ceil(total / pageSize))

  return (
    <div className="ss-events-page">
      <div className="ss-events-topbar">
        <h1 className="ss-events-title">Span store</h1>
        <div className="ss-events-live">
          <button
            type="button"
            className="ss-btn-ghost"
            disabled={listQuery.isFetching}
            onClick={() => void listQuery.refetch()}
          >
            Refresh
          </button>
        </div>
      </div>
      <p className="ss-events-sub">
        Read-only browser for <code className="text-gray-400">span_store</code> in the events database — every
        ingested transcript with NER columns. Linked incidents show public event IDs when a span was attached.
      </p>

      <div className="ss-events-debug-controls flex-wrap">
        <label className="flex items-center gap-2 text-xs text-gray-500" htmlFor="span-monitor">
          Monitor
        </label>
        <select
          id="span-monitor"
          className="ss-select h-8 min-w-[10rem] text-xs"
          value={monitorId}
          onChange={(e) => setMonitorId(e.target.value)}
        >
          <option value="">All monitors</option>
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
          className="ss-input h-8 w-40 text-xs"
          placeholder="contains…"
          value={talkgroup}
          onChange={(e) => setTalkgroup(e.target.value)}
        />

        <label className="flex items-center gap-2 text-xs text-gray-500" htmlFor="span-log">
          Log entry
        </label>
        <input
          id="span-log"
          type="text"
          inputMode="numeric"
          className="ss-input h-8 w-28 text-xs font-mono"
          placeholder="id"
          value={logEntryId}
          onChange={(e) => setLogEntryId(e.target.value)}
        />

        <label className="flex items-center gap-2 text-xs text-gray-500" htmlFor="span-q">
          Transcript
        </label>
        <input
          id="span-q"
          type="search"
          className="ss-input h-8 min-w-[12rem] flex-1 text-xs"
          placeholder="search text…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />

        <label className="flex items-center gap-2 text-xs text-gray-500" htmlFor="span-page-size">
          Page
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
          {total.toLocaleString()} row{total === 1 ? '' : 's'}
        </span>
      </div>

      {logEntryInvalid && (
        <p className="ss-form-error" role="alert">
          Log entry must be a number.
        </p>
      )}

      {listQuery.isError && (
        <p className="ss-form-error" role="alert">
          {errorMessage(listQuery.error, 'Failed to load span store')}
        </p>
      )}

      {listQuery.isSuccess && rows.length === 0 ? (
        <p className="ss-empty not-italic">No span_store rows match these filters.</p>
      ) : (
        <div className="ss-events-table-wrap overflow-x-auto">
          <table className="ss-events-table w-full text-left text-xs">
            <thead>
              <tr>
                <th className="w-8" />
                <th>ID</th>
                <th>Monitor</th>
                <th>Log</th>
                <th>Talkgroup</th>
                <th>NER</th>
                <th>Transcript</th>
                <th>Linked events</th>
                <th>Stored</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => {
                const open = expandedId === row.id
                const chips = nerChips(row)
                return (
                  <Fragment key={row.id}>
                    <tr
                      className="cursor-pointer hover:bg-white/[0.03]"
                      onClick={() => setExpandedId(open ? null : row.id)}
                    >
                      <td className="text-gray-500">{open ? '▼' : '▶'}</td>
                      <td className="font-mono text-gray-400">{row.id}</td>
                      <td>{monitorById.get(row.monitor_id) ?? row.monitor_id}</td>
                      <td className="font-mono">
                        {row.log_entry_id != null ? (
                          <Link
                            to="/logs"
                            className="text-emerald-300/90 hover:underline"
                            onClick={(e) => e.stopPropagation()}
                            title="Open logs database"
                          >
                            {row.log_entry_id}
                          </Link>
                        ) : (
                          '—'
                        )}
                      </td>
                      <td className="max-w-[8rem] truncate" title={row.talkgroup ?? ''}>
                        {row.talkgroup || '—'}
                      </td>
                      <td>
                        {chips.length === 0 ? (
                          <span className="text-gray-500">empty</span>
                        ) : (
                          <span className="ss-events-ner-list">
                            {chips.slice(0, 4).map((c, i) => (
                              <span key={`${c.label}-${i}`} className="ss-events-ner-chip" title={c.label}>
                                {c.value}
                              </span>
                            ))}
                            {chips.length > 4 ? (
                              <span className="text-gray-500">+{chips.length - 4}</span>
                            ) : null}
                          </span>
                        )}
                      </td>
                      <td className="max-w-[16rem] truncate text-gray-300">
                        {transcriptPreview(row.transcript)}
                      </td>
                      <td>
                        {row.attached_event_ids.length === 0 ? (
                          <span className="text-gray-500">—</span>
                        ) : (
                          <span className="flex flex-wrap gap-1">
                            {row.attached_event_ids.map((eid) => (
                              <Link
                                key={eid}
                                to="/events"
                                className="font-mono text-sky-300/90 hover:underline"
                                onClick={(e) => e.stopPropagation()}
                                title={eid}
                              >
                                {eid.slice(0, 8)}
                              </Link>
                            ))}
                          </span>
                        )}
                      </td>
                      <td className="whitespace-nowrap text-gray-500">{formatTime(row.created_at)}</td>
                    </tr>
                    {open ? (
                      <tr>
                        <td colSpan={9} className="bg-black/20 p-0">
                          <div className="space-y-3 p-4">
                            <div>
                              <span className="ss-events-k">Full transcript</span>
                              <p className="ss-events-body mt-1 whitespace-pre-wrap">
                                {row.transcript?.trim() || '—'}
                              </p>
                            </div>
                            {chips.length > 0 ? (
                              <div>
                                <span className="ss-events-k">NER (comma-joined columns)</span>
                                <div className="ss-events-ner-list mt-2">
                                  {chips.map((c, i) => (
                                    <span key={`${c.label}-${i}-full`} className="ss-events-ner-chip">
                                      <span className="text-gray-500">{c.label}:</span> {c.value}
                                    </span>
                                  ))}
                                </div>
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

      {total > 0 ? (
        <div className="mt-4 flex flex-wrap items-center justify-between gap-2 text-xs text-gray-500">
          <span>
            Page {page} of {totalPages}
          </span>
          <div className="flex gap-2">
            <button
              type="button"
              className="ss-btn-ghost"
              disabled={page <= 1 || listQuery.isFetching}
              onClick={() => setPage((p) => Math.max(1, p - 1))}
            >
              Previous
            </button>
            <button
              type="button"
              className="ss-btn-ghost"
              disabled={page >= totalPages || listQuery.isFetching}
              onClick={() => setPage((p) => p + 1)}
            >
              Next
            </button>
          </div>
        </div>
      ) : null}
    </div>
  )
}
