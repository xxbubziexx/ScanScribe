import { Fragment, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useAuth } from '@/context/AuthContext'
import { useToast } from '@/context/ToastContext'
import {
  buildListParams,
  downloadBulkAudioZip,
  downloadLogsExport,
  logsApi,
} from '@/lib/logs'
import { DatabaseDateRangePicker } from '@/components/database/DatabaseDateRangePicker'
import { TalkgroupMultiSelect } from '@/components/database/TalkgroupMultiSelect'
import { errorMessage } from '@/types/api'
import type { LogsSortBy } from '@/types/logs'

import { LogRow } from './components/LogRow'
import { LogExpandedRow } from './components/LogExpandedRow'
import { MobileLogCard } from './components/MobileLogCard'
import { ColResizeHandle, useResizableColumns } from '@/pages/DataExplorer/hooks/useResizableColumns'
import { WorkbenchRefreshControl } from '@/pages/DataExplorer/components/WorkbenchRefreshControl'

const DEFAULT_COL_WIDTHS = {
  time: 155,
  talkgroup: 195,
  filename: 220,
  transcript: 320,
  dur: 68,
  size: 84,
  conf: 68,
  actions: 128,
} as const

type TransmissionsCol = keyof typeof DEFAULT_COL_WIDTHS

const SORT_OPTIONS: { value: LogsSortBy; label: string }[] = [
  { value: 'timestamp_desc', label: 'Newest first' },
  { value: 'timestamp_asc', label: 'Oldest first' },
  { value: 'filename', label: 'Filename' },
  { value: 'talkgroup', label: 'Talkgroup' },
]

const PAGE_SIZES = [25, 50, 100] as const

export function DatabasePage() {
  const { user } = useAuth()
  const { addToast } = useToast()
  const queryClient = useQueryClient()
  const [searchParams] = useSearchParams()
  const isAdmin = user?.is_admin === true

  const [searchInput, setSearchInput] = useState(() => searchParams.get('search') ?? '')
  const [debouncedSearch, setDebouncedSearch] = useState(() => searchParams.get('search') ?? '')
  const [selectedTalkgroups, setSelectedTalkgroups] = useState<string[]>(() =>
    searchParams
      .getAll('talkgroup')
      .map((s) => s.trim())
      .filter(Boolean),
  )
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')

  const activeDatesQuery = useQuery({
    queryKey: ['database-active-dates'],
    queryFn: () => logsApi.activeDates(),
    staleTime: 5 * 60_000,
  })
  const activeDateList = activeDatesQuery.data?.dates

  const talkgroupsQuery = useQuery({
    queryKey: ['logs-talkgroups-all'],
    queryFn: () => logsApi.talkgroups(),
    staleTime: 60_000,
  })
  const talkgroupList = talkgroupsQuery.data?.talkgroups ?? []

  const [sortBy, setSortBy] = useState<LogsSortBy>('timestamp_desc')
  const [pageSize, setPageSize] = useState(50)
  const [page, setPage] = useState(1)
  const [expandedId, setExpandedId] = useState<number | null>(null)
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set())
  const {
    widths: colWidths,
    totalWidth: colTotalWidth,
    isCustomized: hasCustomWidths,
    activeCol: activeResizeCol,
    startResize,
    resetColumn,
    resetAll: resetColWidths,
  } = useResizableColumns<TransmissionsCol>('transmissions', DEFAULT_COL_WIDTHS)
  const [isDownloadingZip, setIsDownloadingZip] = useState(false)

  useEffect(() => {
    const t = window.setTimeout(() => setDebouncedSearch(searchInput), 400)
    return () => window.clearTimeout(t)
  }, [searchInput])

  useEffect(() => {
    setPage(1)
  }, [debouncedSearch, selectedTalkgroups, dateFrom, dateTo, sortBy, pageSize])

  useEffect(() => {
    setExpandedId(null)
  }, [page, pageSize, debouncedSearch, selectedTalkgroups, dateFrom, dateTo, sortBy])

  const query = useQuery({
    queryKey: [
      'database-logs',
      page,
      pageSize,
      debouncedSearch,
      selectedTalkgroups,
      dateFrom,
      dateTo,
      sortBy,
    ],
    queryFn: () =>
      logsApi.list(
        buildListParams({
          page,
          pageSize,
          search: debouncedSearch,
          talkgroups: selectedTalkgroups,
          dateFrom,
          dateTo,
          sortBy,
        }),
      ),
  })

  const data = query.data
  const rows = data?.logs ?? []
  const total = data?.total ?? 0
  const totalPages = Math.max(1, data?.total_pages ?? 1)

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

  const delMutation = useMutation({
    mutationFn: (id: number) => logsApi.delete(id),
    onSuccess: (_res, id) => {
      addToast('Log entry removed', 'success')
      setSelectedIds((prev) => {
        if (!prev.has(id)) return prev
        const next = new Set(prev)
        next.delete(id)
        return next
      })
      void queryClient.invalidateQueries({ queryKey: ['database-logs'] })
      void queryClient.invalidateQueries({ queryKey: ['dataset-logs'] })
      void queryClient.invalidateQueries({ queryKey: ['database-overview'] })
    },
    onError: (e: unknown) => addToast(errorMessage(e, 'Delete failed'), 'error'),
  })

  const bulkDelMutation = useMutation({
    mutationFn: (ids: number[]) => logsApi.bulkDelete(ids),
    onSuccess: (res) => {
      addToast(`Deleted ${res.deleted} log entries`, 'success')
      setSelectedIds(new Set())
      void queryClient.invalidateQueries({ queryKey: ['database-logs'] })
      void queryClient.invalidateQueries({ queryKey: ['dataset-logs'] })
      void queryClient.invalidateQueries({ queryKey: ['database-overview'] })
    },
    onError: (e: unknown) => addToast(errorMessage(e, 'Bulk delete failed'), 'error'),
  })

  const onDelete = useCallback(
    (id: number) => {
      if (!isAdmin) return
      if (!window.confirm('Delete this log entry?')) return
      delMutation.mutate(id)
    },
    [delMutation, isAdmin],
  )

  const onBulkDelete = () => {
    if (!isAdmin || selectedIds.size === 0) return
    if (!window.confirm(`Permanently delete ${selectedIds.size} selected log entries and their audio files?`)) {
      return
    }
    bulkDelMutation.mutate(Array.from(selectedIds))
  }

  const onBulkDownloadZip = async () => {
    if (selectedIds.size === 0) return
    setIsDownloadingZip(true)
    try {
      const { exportCount, audioCount } = await downloadBulkAudioZip(Array.from(selectedIds))
      addToast(
        `Downloaded ZIP (${exportCount} log${exportCount === 1 ? '' : 's'}, ${audioCount} audio file${audioCount === 1 ? '' : 's'})`,
        'success',
      )
    } catch (e) {
      addToast(errorMessage(e, 'Bulk ZIP download failed'), 'error')
    } finally {
      setIsDownloadingZip(false)
    }
  }

  const onExport = async () => {
    try {
      await downloadLogsExport({
        search: debouncedSearch,
        talkgroups: selectedTalkgroups,
        dateFrom,
        dateTo,
      })
      addToast('CSV export started', 'success')
    } catch (e) {
      addToast(errorMessage(e, 'Export failed'), 'error')
    }
  }

  const hasFilters = Boolean(searchInput.trim() || selectedTalkgroups.length > 0 || dateFrom || dateTo)
  const clearFilters = () => {
    setSearchInput('')
    setDebouncedSearch('')
    setSelectedTalkgroups([])
    setDateFrom('')
    setDateTo('')
  }

  return (
    <div className="ss-workbench-pane">
      <div className="ss-workbench-header">
        <div className="flex items-center gap-2.5">
          <h2 className="text-sm font-semibold tracking-tight text-slate-100">Transmissions</h2>
          <span className="font-mono text-[11px] text-slate-500">log_entries</span>
          <span className="ss-events-pill-tiny font-mono">
            {total.toLocaleString()} row{total === 1 ? '' : 's'}
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
          <WorkbenchRefreshControl
            total={data?.total}
            dataUpdatedAt={query.dataUpdatedAt}
            isFetching={query.isFetching}
            filterKey={JSON.stringify([debouncedSearch, selectedTalkgroups, dateFrom, dateTo])}
            onRefresh={async () => {
              const res = await query.refetch()
              return res.data?.total
            }}
          />
          <button
            type="button"
            className="ss-btn-ghost h-8 px-3 text-xs cursor-pointer"
            onClick={onExport}
            disabled={query.isFetching}
          >
            Export CSV
          </button>
        </div>
      </div>

      <div className="ss-workbench-filters">
        <div className="min-w-[14rem] flex-1">
          <label className="ss-form-label" htmlFor="db-search">
            Search
          </label>
          <input
            id="db-search"
            type="search"
            className="ss-input h-8 text-xs"
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            placeholder="Transcript, filename, talkgroup…"
            autoComplete="off"
          />
        </div>

        <div>
          <label className="ss-form-label" htmlFor="db-talkgroup">
            Talkgroup
          </label>
          <TalkgroupMultiSelect
            id="db-talkgroup"
            talkgroups={talkgroupList}
            selected={selectedTalkgroups}
            onChange={setSelectedTalkgroups}
          />
        </div>

        <div>
          <DatabaseDateRangePicker
            from={dateFrom}
            to={dateTo}
            onChange={(a, b) => {
              setDateFrom(a)
              setDateTo(b)
            }}
            activeDates={activeDateList}
          />
        </div>

        <div>
          <label className="ss-form-label" htmlFor="db-sort">
            Sort
          </label>
          <select
            id="db-sort"
            className="ss-select h-8 min-w-[9.5rem] text-xs"
            value={sortBy}
            onChange={(e) => setSortBy(e.target.value as LogsSortBy)}
          >
            {SORT_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </div>
      </div>

      {selectedIds.size > 0 && (
        <div className="ss-workbench-bulkbar">
          <div className="flex items-center gap-3 text-xs">
            <span className="font-semibold text-indigo-100">
              {selectedIds.size} {selectedIds.size === 1 ? 'entry' : 'entries'} selected
            </span>
            <button
              type="button"
              className="text-indigo-300 hover:text-white underline cursor-pointer"
              onClick={() => setSelectedIds(new Set())}
            >
              Clear selection
            </button>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              className="ss-btn-primary h-7 px-3 text-xs cursor-pointer disabled:opacity-50"
              onClick={() => void onBulkDownloadZip()}
              disabled={isDownloadingZip}
            >
              {isDownloadingZip ? 'Building ZIP…' : `Download ZIP (${selectedIds.size})`}
            </button>
            {isAdmin && (
              <button
                type="button"
                className="ss-btn-ghost h-7 px-3 text-xs text-red-300 border-red-500/30 hover:bg-red-500/15 cursor-pointer disabled:opacity-50"
                onClick={onBulkDelete}
                disabled={bulkDelMutation.isPending}
              >
                {bulkDelMutation.isPending ? 'Deleting…' : 'Delete Selected'}
              </button>
            )}
          </div>
        </div>
      )}

      <div className="ss-workbench-grid-wrap">
        {query.isError && (
          <p className="ss-form-error m-4" role="alert">
            {errorMessage(query.error, 'Failed to load logs')}
          </p>
        )}

        {query.isLoading && <p className="p-5 text-xs text-gray-500">Loading transmissions…</p>}

        {!query.isLoading && !query.isError && rows.length === 0 && (
          <p className="ss-empty m-4 not-italic">No log entries for these filters.</p>
        )}

        {!query.isLoading && !query.isError && rows.length > 0 && (
          <>
            <div className="hidden md:block">
              <table
                className="ss-workbench-table ss-workbench-table--resizable"
                style={{ width: `${colTotalWidth + 36}px`, minWidth: '100%' }}
              >
                <colgroup>
                  <col style={{ width: '36px' }} />
                  <col style={{ width: `${colWidths.time}px` }} />
                  <col style={{ width: `${colWidths.talkgroup}px` }} />
                  <col style={{ width: `${colWidths.filename}px` }} />
                  <col style={{ width: `${colWidths.transcript}px` }} />
                  <col style={{ width: `${colWidths.dur}px` }} />
                  <col style={{ width: `${colWidths.size}px` }} />
                  <col style={{ width: `${colWidths.conf}px` }} />
                  <col style={{ width: `${colWidths.actions}px` }} />
                </colgroup>
                <thead>
                  <tr>
                    <th className="w-9 text-center">
                      <input
                        ref={selectAllRef}
                        type="checkbox"
                        className="h-3.5 w-3.5 accent-indigo-500 cursor-pointer"
                        checked={allOnPageSelected}
                        onChange={toggleSelectPage}
                        aria-label="Select all entries on this page"
                      />
                    </th>
                    <th>
                      Time
                      <ColResizeHandle
                        col="time"
                        label="Time"
                        isActive={activeResizeCol === 'time'}
                        onMouseDown={(e) => startResize('time', e)}
                        onDoubleClick={() => resetColumn('time')}
                      />
                    </th>
                    <th>
                      Talkgroup
                      <ColResizeHandle
                        col="talkgroup"
                        label="Talkgroup"
                        isActive={activeResizeCol === 'talkgroup'}
                        onMouseDown={(e) => startResize('talkgroup', e)}
                        onDoubleClick={() => resetColumn('talkgroup')}
                      />
                    </th>
                    <th>
                      Filename
                      <ColResizeHandle
                        col="filename"
                        label="Filename"
                        isActive={activeResizeCol === 'filename'}
                        onMouseDown={(e) => startResize('filename', e)}
                        onDoubleClick={() => resetColumn('filename')}
                      />
                    </th>
                    <th>
                      Transcript
                      <ColResizeHandle
                        col="transcript"
                        label="Transcript"
                        isActive={activeResizeCol === 'transcript'}
                        onMouseDown={(e) => startResize('transcript', e)}
                        onDoubleClick={() => resetColumn('transcript')}
                      />
                    </th>
                    <th>
                      Dur
                      <ColResizeHandle
                        col="dur"
                        label="Dur"
                        isActive={activeResizeCol === 'dur'}
                        onMouseDown={(e) => startResize('dur', e)}
                        onDoubleClick={() => resetColumn('dur')}
                      />
                    </th>
                    <th>
                      Size
                      <ColResizeHandle
                        col="size"
                        label="Size"
                        isActive={activeResizeCol === 'size'}
                        onMouseDown={(e) => startResize('size', e)}
                        onDoubleClick={() => resetColumn('size')}
                      />
                    </th>
                    <th>
                      Conf.
                      <ColResizeHandle
                        col="conf"
                        label="Conf."
                        isActive={activeResizeCol === 'conf'}
                        onMouseDown={(e) => startResize('conf', e)}
                        onDoubleClick={() => resetColumn('conf')}
                      />
                    </th>
                    <th className="text-right">
                      Actions
                      <ColResizeHandle
                        col="actions"
                        label="Actions"
                        isActive={activeResizeCol === 'actions'}
                        onMouseDown={(e) => startResize('actions', e)}
                        onDoubleClick={() => resetColumn('actions')}
                      />
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row) => (
                    <Fragment key={row.id}>
                      <LogRow
                        row={row}
                        isAdmin={isAdmin}
                        selected={selectedIds.has(row.id)}
                        onToggleSelect={() => toggleRowSelect(row.id)}
                        onDelete={onDelete}
                        deleting={delMutation.isPending}
                        expanded={expandedId === row.id}
                        onToggleExpand={() =>
                          setExpandedId((cur) => (cur === row.id ? null : row.id))
                        }
                      />
                      {expandedId === row.id && (
                        <tr className="ss-db-expand-tr">
                          <td className="p-0" colSpan={9}>
                            <LogExpandedRow row={row} />
                          </td>
                        </tr>
                      )}
                    </Fragment>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="md:hidden flex flex-col gap-3 p-3">
              {rows.map((row) => (
                <MobileLogCard
                  key={row.id}
                  row={row}
                  isAdmin={isAdmin}
                  selected={selectedIds.has(row.id)}
                  onToggleSelect={() => toggleRowSelect(row.id)}
                  onDelete={onDelete}
                  deleting={delMutation.isPending}
                  expanded={expandedId === row.id}
                  onToggleExpand={() => setExpandedId((cur) => (cur === row.id ? null : row.id))}
                />
              ))}
            </div>
          </>
        )}
      </div>

      <div className="ss-workbench-footer">
        <div className="flex items-center gap-3">
          <span>
            {total > 0
              ? `Showing ${(page - 1) * pageSize + 1}–${Math.min(page * pageSize, total)} of ${total.toLocaleString()}`
              : '0 entries'}
          </span>
          <label className="flex items-center gap-1.5 text-gray-500" htmlFor="db-ps">
            <span>Rows</span>
            <select
              id="db-ps"
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
            disabled={page <= 1 || query.isFetching}
            onClick={() => setPage(1)}
            title="First Page"
          >
            ««
          </button>
          <button
            type="button"
            className="ss-btn-ghost h-7 px-2.5 text-xs cursor-pointer"
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            disabled={page <= 1 || query.isFetching}
          >
            Previous
          </button>
          <span className="px-2 font-mono text-gray-300">
            {page} / {totalPages}
          </span>
          <button
            type="button"
            className="ss-btn-ghost h-7 px-2.5 text-xs cursor-pointer"
            onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
            disabled={total === 0 || page >= totalPages || query.isFetching}
          >
            Next
          </button>
          <button
            type="button"
            className="ss-btn-ghost h-7 px-2 text-xs cursor-pointer"
            disabled={total === 0 || page >= totalPages || query.isFetching}
            onClick={() => setPage(totalPages)}
            title="Last Page"
          >
            »»
          </button>
        </div>
      </div>
    </div>
  )
}
