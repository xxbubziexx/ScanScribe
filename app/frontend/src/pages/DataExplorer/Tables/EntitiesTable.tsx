import { Fragment, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { eventsApi } from '@/lib/events'
import { logsApi } from '@/lib/logs'
import { DatabaseDateRangePicker } from '@/components/database/DatabaseDateRangePicker'
import { errorMessage } from '@/types/api'
import { useToast } from '@/context/ToastContext'
import type { EntityObservationItem } from '@/types/events'
import { NerCsvExporterModal } from '../components/NerCsvExporterModal'
import { ColResizeHandle, useResizableColumns } from '../hooks/useResizableColumns'

const PAGE_SIZES = [25, 50, 100] as const

const DEFAULT_COL_WIDTHS = {
  id: 68,
  monitor: 135,
  label: 105,
  raw: 240,
  talkgroup: 185,
  span_id: 88,
  log_id: 88,
  observed: 155,
} as const

type EntitiesCol = keyof typeof DEFAULT_COL_WIDTHS

function formatTime(iso: string | null | undefined) {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleString(undefined, { dateStyle: 'short', timeStyle: 'short' })
}

function getLabelBadgeClass(label: string) {
  switch (label.toUpperCase()) {
    case 'EVT_TYPE':
      return 'text-amber-300'
    case 'UNIT':
      return 'text-emerald-300'
    case 'LOC':
    case 'ADDRESS':
      return 'text-sky-300'
    case 'STATUS':
      return 'text-purple-300'
    case 'TIME':
      return 'text-indigo-300'
    default:
      return 'text-gray-300'
  }
}

function copyToClipboard(text: string, onSuccess: () => void) {
  void navigator.clipboard.writeText(text).then(onSuccess)
}

export function EntitiesTable() {
  const { addToast } = useToast()
  const [searchParams, setSearchParams] = useSearchParams()
  const [monitorId, setMonitorId] = useState<string>('')
  const [label, setLabel] = useState<string>(() => searchParams.get('label') ?? '')
  const [talkgroup, setTalkgroup] = useState<string>(() => searchParams.get('talkgroup') ?? '')
  const [logEntryId, setLogEntryId] = useState<string>(() => searchParams.get('log_entry_id') ?? '')
  const [spanStoreId, setSpanStoreId] = useState<string>(() => searchParams.get('span_store_id') ?? '')
  const [search, setSearch] = useState<string>(() => searchParams.get('q') ?? '')
  const [debouncedSearch, setDebouncedSearch] = useState<string>(() => searchParams.get('q') ?? '')
  const [dateFrom, setDateFrom] = useState<string>('')
  const [dateTo, setDateTo] = useState<string>('')
  const [sortBy, setSortBy] = useState<string>('id')
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('desc')
  const [pageSize, setPageSize] = useState<number>(50)
  const [page, setPage] = useState<number>(1)
  const [expandedId, setExpandedId] = useState<number | null>(null)
  const [jsonViewId, setJsonViewId] = useState<number | null>(null)
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set())
  const [exporterOpen, setExporterOpen] = useState<boolean>(() => searchParams.get('export') === '1')
  const [exporterDefaultScope, setExporterDefaultScope] = useState<'filters' | 'selected'>('filters')

  useEffect(() => {
    if (searchParams.get('export') === '1') {
      setExporterOpen(true)
      const next = new URLSearchParams(searchParams)
      next.delete('export')
      setSearchParams(next, { replace: true })
    }
  }, [searchParams, setSearchParams])

  const activeDatesQuery = useQuery({
    queryKey: ['database-active-dates'],
    queryFn: () => logsApi.activeDates(),
    staleTime: 5 * 60_000,
  })
  const activeDateList = activeDatesQuery.data?.dates

  useEffect(() => {
    const t = window.setTimeout(() => setDebouncedSearch(search), 400)
    return () => window.clearTimeout(t)
  }, [search])

  useEffect(() => {
    setPage(1)
  }, [monitorId, label, talkgroup, logEntryId, spanStoreId, debouncedSearch, dateFrom, dateTo, sortBy, sortOrder, pageSize])

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
      dateFrom,
      dateTo,
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
        dateFrom: dateFrom.trim() || undefined,
        dateTo: dateTo.trim() || undefined,
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
  const availableLabels = labelsQuery.data?.labels ?? ['EVT_TYPE', 'LOC', 'ADDRESS', 'UNIT', 'STATUS', 'TIME']

  const pageIds = useMemo(() => rows.map((r) => r.id), [rows])
  const selectedOnPageCount = useMemo(
    () => pageIds.filter((id) => selectedIds.has(id)).length,
    [pageIds, selectedIds],
  )
  const allOnPageSelected = pageIds.length > 0 && selectedOnPageCount === pageIds.length
  const someOnPageSelected = selectedOnPageCount > 0 && selectedOnPageCount < pageIds.length

  const selectAllRef = useRef<HTMLInputElement | null>(null)
  useEffect(() => {
    if (selectAllRef.current) {
      selectAllRef.current.indeterminate = someOnPageSelected
    }
  }, [someOnPageSelected])

  const toggleRowSelect = useCallback((id: number) => {
    setSelectedIds((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }, [])

  const toggleSelectPage = useCallback(() => {
    setSelectedIds((prev) => {
      const next = new Set(prev)
      if (allOnPageSelected) {
        for (const id of pageIds) next.delete(id)
      } else {
        for (const id of pageIds) next.add(id)
      }
      return next
    })
  }, [allOnPageSelected, pageIds])

  const hasFilters = Boolean(
    monitorId || label || talkgroup.trim() || logEntryId.trim() || spanStoreId.trim() || search.trim() || dateFrom || dateTo,
  )
  const {
    widths: colWidths,
    totalWidth: colTotalWidth,
    isCustomized: hasCustomWidths,
    activeCol: activeResizeCol,
    startResize,
    resetColumn,
    resetAll: resetColWidths,
  } = useResizableColumns<EntitiesCol>('entities', DEFAULT_COL_WIDTHS)
  const clearFilters = () => {
    setMonitorId('')
    setLabel('')
    setTalkgroup('')
    setLogEntryId('')
    setSpanStoreId('')
    setSearch('')
    setDebouncedSearch('')
    setDateFrom('')
    setDateTo('')
  }

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
    <div className="ss-workbench-pane">
      <div className="ss-workbench-header">
        <div className="flex items-center gap-2.5">
          <h2 className="text-sm font-semibold tracking-tight text-slate-100">NER Entity Observations</h2>
          <span className="font-mono text-[11px] text-slate-500">entity_observations</span>
          <span className="ss-events-pill-tiny font-mono">
            {total.toLocaleString()} observation{total === 1 ? '' : 's'}
          </span>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {hasCustomWidths && (
            <button
              type="button"
              className="ss-btn-ghost h-8 px-3 text-xs cursor-pointer"
              onClick={resetColWidths}
            >
              Reset Widths
            </button>
          )}
          {hasFilters && (
            <button
              type="button"
              className="ss-btn-ghost h-8 px-3 text-xs cursor-pointer"
              onClick={clearFilters}
            >
              Clear Filters
            </button>
          )}
          <button
            type="button"
            className="ss-btn-primary h-8 px-3 text-xs cursor-pointer"
            onClick={() => {
              setExporterDefaultScope('filters')
              setExporterOpen(true)
            }}
          >
            Export NER CSV
          </button>
          <button
            type="button"
            className="ss-btn-ghost h-8 px-3 text-xs cursor-pointer"
            disabled={listQuery.isFetching}
            onClick={() => void listQuery.refetch()}
          >
            {listQuery.isFetching ? 'Refreshing…' : 'Refresh'}
          </button>
        </div>
      </div>

      {/* Filters */}
      <div className="ss-workbench-filters">
        <div>
          <label className="ss-form-label" htmlFor="entity-monitor">
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
        </div>

        <div>
          <label className="ss-form-label" htmlFor="entity-label">
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
        </div>

        <div>
          <label className="ss-form-label" htmlFor="entity-tg">
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
        </div>

        <div>
          <label className="ss-form-label" htmlFor="entity-span">
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
        </div>

        <div>
          <label className="ss-form-label" htmlFor="entity-log">
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
        </div>

        <div>
          <DatabaseDateRangePicker
            from={dateFrom}
            to={dateTo}
            onChange={(f, t) => {
              setDateFrom(f)
              setDateTo(t)
            }}
            activeDates={activeDateList}
          />
        </div>

        <div className="min-w-[11rem] flex-1">
          <label className="ss-form-label" htmlFor="entity-search">
            Search
          </label>
          <input
            id="entity-search"
            type="search"
            className="ss-input h-8 text-xs"
            placeholder="Search entity text…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
      </div>

      {selectedIds.size > 0 && (
        <div className="ss-workbench-bulkbar border-emerald-500/35 bg-emerald-500/10">
          <div className="flex items-center gap-3 text-xs">
            <span className="font-semibold text-emerald-100">
              {selectedIds.size} observation{selectedIds.size === 1 ? '' : 's'} selected
            </span>
            <button
              type="button"
              className="text-emerald-300 hover:text-white underline cursor-pointer"
              onClick={() => setSelectedIds(new Set())}
            >
              Clear selection
            </button>
          </div>
          <button
            type="button"
            className="ss-btn-primary h-7 px-3 text-xs cursor-pointer"
            onClick={() => {
              setExporterDefaultScope('selected')
              setExporterOpen(true)
            }}
          >
            Export Selected CSV ({selectedIds.size})
          </button>
        </div>
      )}

      <div className="ss-workbench-grid-wrap">
        {(logEntryInvalid || spanStoreInvalid) && (
          <p className="ss-form-error m-4" role="alert">
            Span ID and Log Entry ID must be numbers.
          </p>
        )}

        {listQuery.isError && (
          <p className="ss-form-error m-4" role="alert">
            {errorMessage(listQuery.error, 'Failed to load entity observations')}
          </p>
        )}

        {listQuery.isLoading && <p className="p-5 text-xs text-gray-500">Loading NER observations…</p>}

        {listQuery.isSuccess && rows.length === 0 ? (
          <p className="ss-empty m-4 not-italic">No entity observations found matching the selected filters.</p>
        ) : !listQuery.isLoading && !listQuery.isError && rows.length > 0 ? (
          <table
            className="ss-workbench-table ss-workbench-table--resizable"
            style={{ width: `${colTotalWidth + 64}px`, minWidth: '100%' }}
          >
            <colgroup>
              <col style={{ width: '32px' }} />
              <col style={{ width: '32px' }} />
              <col style={{ width: `${colWidths.id}px` }} />
              <col style={{ width: `${colWidths.monitor}px` }} />
              <col style={{ width: `${colWidths.label}px` }} />
              <col style={{ width: `${colWidths.raw}px` }} />
              <col style={{ width: `${colWidths.talkgroup}px` }} />
              <col style={{ width: `${colWidths.span_id}px` }} />
              <col style={{ width: `${colWidths.log_id}px` }} />
              <col style={{ width: `${colWidths.observed}px` }} />
            </colgroup>
            <thead>
              <tr>
                <th className="w-8 text-center">
                  <input
                    ref={selectAllRef}
                    type="checkbox"
                    className="h-3.5 w-3.5 accent-emerald-500 cursor-pointer"
                    checked={allOnPageSelected}
                    onChange={toggleSelectPage}
                    aria-label="Select all observations on this page"
                  />
                </th>
                <th className="w-8" />
                <th className="cursor-pointer select-none" onClick={() => toggleSort('id')}>
                  ID {renderSortIndicator('id')}
                  <ColResizeHandle
                    col="id"
                    label="ID"
                    isActive={activeResizeCol === 'id'}
                    onMouseDown={(e) => startResize('id', e)}
                    onDoubleClick={() => resetColumn('id')}
                  />
                </th>
                <th>
                  Monitor
                  <ColResizeHandle
                    col="monitor"
                    label="Monitor"
                    isActive={activeResizeCol === 'monitor'}
                    onMouseDown={(e) => startResize('monitor', e)}
                    onDoubleClick={() => resetColumn('monitor')}
                  />
                </th>
                <th className="cursor-pointer select-none" onClick={() => toggleSort('label')}>
                  Label {renderSortIndicator('label')}
                  <ColResizeHandle
                    col="label"
                    label="Label"
                    isActive={activeResizeCol === 'label'}
                    onMouseDown={(e) => startResize('label', e)}
                    onDoubleClick={() => resetColumn('label')}
                  />
                </th>
                <th className="cursor-pointer select-none" onClick={() => toggleSort('raw')}>
                  Entity Span {renderSortIndicator('raw')}
                  <ColResizeHandle
                    col="raw"
                    label="Entity Span"
                    isActive={activeResizeCol === 'raw'}
                    onMouseDown={(e) => startResize('raw', e)}
                    onDoubleClick={() => resetColumn('raw')}
                  />
                </th>
                <th className="cursor-pointer select-none" onClick={() => toggleSort('talkgroup')}>
                  Talkgroup {renderSortIndicator('talkgroup')}
                  <ColResizeHandle
                    col="talkgroup"
                    label="Talkgroup"
                    isActive={activeResizeCol === 'talkgroup'}
                    onMouseDown={(e) => startResize('talkgroup', e)}
                    onDoubleClick={() => resetColumn('talkgroup')}
                  />
                </th>
                <th className="cursor-pointer select-none" onClick={() => toggleSort('span_store_id')}>
                  Span ID {renderSortIndicator('span_store_id')}
                  <ColResizeHandle
                    col="span_id"
                    label="Span ID"
                    isActive={activeResizeCol === 'span_id'}
                    onMouseDown={(e) => startResize('span_id', e)}
                    onDoubleClick={() => resetColumn('span_id')}
                  />
                </th>
                <th className="cursor-pointer select-none" onClick={() => toggleSort('log_entry_id')}>
                  Log ID {renderSortIndicator('log_entry_id')}
                  <ColResizeHandle
                    col="log_id"
                    label="Log ID"
                    isActive={activeResizeCol === 'log_id'}
                    onMouseDown={(e) => startResize('log_id', e)}
                    onDoubleClick={() => resetColumn('log_id')}
                  />
                </th>
                <th className="cursor-pointer select-none" onClick={() => toggleSort('ts')}>
                  Observed {renderSortIndicator('ts')}
                  <ColResizeHandle
                    col="observed"
                    label="Observed"
                    isActive={activeResizeCol === 'observed'}
                    onMouseDown={(e) => startResize('observed', e)}
                    onDoubleClick={() => resetColumn('observed')}
                  />
                </th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row: EntityObservationItem) => {
                const isOpen = expandedId === row.id
                const isSelected = selectedIds.has(row.id)
                return (
                  <Fragment key={row.id}>
                    <tr
                      className={`cursor-pointer hover:bg-white/[0.03] transition-colors ${isSelected ? 'bg-emerald-500/[0.07]' : ''
                        }`}
                      onClick={() => setExpandedId(isOpen ? null : row.id)}
                    >
                      <td
                        className="text-center"
                        onClick={(e) => {
                          e.stopPropagation()
                        }}
                      >
                        <input
                          type="checkbox"
                          className="h-3.5 w-3.5 accent-emerald-500 cursor-pointer"
                          checked={isSelected}
                          onChange={() => toggleRowSelect(row.id)}
                          aria-label={`Select observation ${row.id}`}
                        />
                      </td>
                      <td className="text-gray-500">{isOpen ? '▼' : '▶'}</td>
                      <td className="whitespace-nowrap font-mono text-slate-400">#{row.id}</td>
                      <td className="font-medium text-slate-300">
                        {monitorById.get(row.monitor_id) ?? `Monitor #${row.monitor_id}`}
                      </td>
                      <td>
                        <span
                          className={`font-bold uppercase text-[11px] tracking-wide ${getLabelBadgeClass(
                            row.label,
                          )}`}
                        >
                          {row.label}
                        </span>
                      </td>
                      <td className="truncate font-semibold text-slate-100" title={row.raw}>
                        {row.raw}
                      </td>
                      <td className="truncate font-semibold text-sky-300/90" title={row.talkgroup ?? ''}>
                        {row.talkgroup || '—'}
                      </td>
                      <td className="whitespace-nowrap font-mono">
                        <Link
                          to={`/data/spans?log_entry_id=${row.log_entry_id ?? ''}`}
                          className="font-medium text-sky-300 hover:underline"
                          onClick={(e) => e.stopPropagation()}
                          title="Open in Spans table"
                        >
                          #{row.span_store_id}
                        </Link>
                      </td>
                      <td className="whitespace-nowrap font-mono text-slate-400">
                        {row.log_entry_id != null ? (
                          <Link
                            to={`/data/logs?search=${encodeURIComponent(row.talkgroup || '')}`}
                            className="font-medium text-amber-300/90 hover:underline"
                            onClick={(e) => e.stopPropagation()}
                            title="Open in Transmissions"
                          >
                            #{row.log_entry_id}
                          </Link>
                        ) : (
                          '—'
                        )}
                      </td>
                      <td className="whitespace-nowrap font-mono text-slate-400">{formatTime(row.ts)}</td>
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
                                  className={`font-semibold uppercase text-[11px] tracking-wide ${getLabelBadgeClass(
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

                            <div className="rounded-sm border border-white/10 bg-white/[0.02] p-3.5">
                              <span className="block text-[10px] font-semibold uppercase tracking-wider text-gray-400">
                                Entity Span
                              </span>
                              <p className="mt-1 font-mono text-sm font-medium text-gray-100 break-words">
                                {row.raw}
                              </p>
                              <span className="mt-2 block text-[11px] text-gray-500">
                                Text span extracted directly from the transcript.
                              </span>
                            </div>

                            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs">
                              <div className="rounded-sm border border-white/5 bg-white/[0.02] p-2">
                                <span className="block text-[10px] uppercase text-gray-500">Talkgroup</span>
                                <span className="mt-0.5 block font-medium text-gray-200">{row.talkgroup || '—'}</span>
                              </div>
                              <div className="rounded-sm border border-white/5 bg-white/[0.02] p-2">
                                <span className="block text-[10px] uppercase text-gray-500">Span Store ID</span>
                                <span className="mt-0.5 block font-mono text-sky-300">#{row.span_store_id}</span>
                              </div>
                              <div className="rounded-sm border border-white/5 bg-white/[0.02] p-2">
                                <span className="block text-[10px] uppercase text-gray-500">Log Entry ID</span>
                                <span className="mt-0.5 block font-mono text-amber-300">
                                  {row.log_entry_id ? `#${row.log_entry_id}` : '—'}
                                </span>
                              </div>
                              <div className="rounded-sm border border-white/5 bg-white/[0.02] p-2">
                                <span className="block text-[10px] uppercase text-gray-500">Timestamp</span>
                                <span className="mt-0.5 block text-gray-300">{formatTime(row.ts)}</span>
                              </div>
                            </div>

                            {jsonViewId === row.id ? (
                              <div className="mt-3">
                                <span className="text-[11px] font-semibold uppercase tracking-wider text-gray-500">
                                  Raw JSON
                                </span>
                                <pre className="mt-1.5 max-h-60 overflow-auto rounded-sm border border-white/10 bg-black/60 p-3 font-mono text-xs text-emerald-300">
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
        ) : null}
      </div>

      {/* Pagination Controls */}
      <div className="ss-workbench-footer">
        <div className="flex items-center gap-3">
          <span>
            {total > 0
              ? `Showing ${(page - 1) * pageSize + 1}–${Math.min(page * pageSize, total)} of ${total.toLocaleString()}`
              : '0 observations'}
          </span>
          <label className="flex items-center gap-1.5 text-gray-500" htmlFor="entity-page-size">
            <span>Rows</span>
            <select
              id="entity-page-size"
              className="ss-select h-7 w-[4.25rem] text-xs"
              value={String(pageSize)}
              onChange={(e) => setPageSize(Number(e.target.value))}
            >
              {PAGE_SIZES.map((n) => (
                <option key={n} value={n}>
                  {n}
                </option>
              ))}
            </select>
          </label>
        </div>

        <div className="flex items-center gap-1.5">
          <button
            type="button"
            className="ss-btn-ghost h-7 px-2 text-xs cursor-pointer"
            disabled={page <= 1 || listQuery.isFetching}
            onClick={() => setPage(1)}
            title="First Page"
          >
            ««
          </button>
          <button
            type="button"
            className="ss-btn-ghost h-7 px-2.5 text-xs cursor-pointer"
            disabled={page <= 1 || listQuery.isFetching}
            onClick={() => setPage((p) => Math.max(1, p - 1))}
          >
            Previous
          </button>
          <span className="px-2 font-mono text-gray-300">
            {page} / {totalPages}
          </span>
          <button
            type="button"
            className="ss-btn-ghost h-7 px-2.5 text-xs cursor-pointer"
            disabled={total === 0 || page >= totalPages || listQuery.isFetching}
            onClick={() => setPage((p) => p + 1)}
          >
            Next
          </button>
          <button
            type="button"
            className="ss-btn-ghost h-7 px-2 text-xs cursor-pointer"
            disabled={total === 0 || page >= totalPages || listQuery.isFetching}
            onClick={() => setPage(totalPages)}
            title="Last Page"
          >
            »»
          </button>
        </div>
      </div>

      <NerCsvExporterModal
        open={exporterOpen}
        onClose={() => setExporterOpen(false)}
        availableLabels={availableLabels}
        selectedIds={selectedIds}
        defaultScope={exporterDefaultScope}
        activeFilters={{
          monitorId: monitorId ? Number.parseInt(monitorId, 10) : undefined,
          talkgroup: talkgroup.trim() || undefined,
          logEntryId: logEntryFilter,
          spanStoreId: spanStoreFilter,
          q: debouncedSearch.trim() || undefined,
          dateFrom: dateFrom.trim() || undefined,
          dateTo: dateTo.trim() || undefined,
          initialLabel: label || undefined,
        }}
      />
    </div>
  )
}
