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
import { errorMessage } from '@/types/api'
import type { LogsSortBy } from '@/types/logs'

import { LogRow } from './components/LogRow'
import { LogExpandedRow } from './components/LogExpandedRow'
import { MobileLogCard } from './components/MobileLogCard'

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
  const [talkgroup, setTalkgroup] = useState(() => searchParams.get('talkgroup') ?? '')

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
  const [isDownloadingZip, setIsDownloadingZip] = useState(false)

  useEffect(() => {
    const t = window.setTimeout(() => setDebouncedSearch(searchInput), 400)
    return () => window.clearTimeout(t)
  }, [searchInput])

  useEffect(() => {
    setPage(1)
  }, [debouncedSearch, talkgroup, dateFrom, dateTo, sortBy, pageSize])

  useEffect(() => {
    setExpandedId(null)
  }, [page, pageSize, debouncedSearch, talkgroup, dateFrom, dateTo, sortBy])

  const query = useQuery({
    queryKey: [
      'database-logs',
      page,
      pageSize,
      debouncedSearch,
      talkgroup,
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
          talkgroup,
          dateFrom,
          dateTo,
          sortBy,
        }),
      ),
  })

  const data = query.data
  const rows = data?.logs ?? []
  const total = data?.total ?? 0
  const totalPages = data?.total_pages ?? 0

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
      await downloadLogsExport({ search: debouncedSearch, talkgroup, dateFrom, dateTo })
      addToast('CSV export started', 'success')
    } catch (e) {
      addToast(errorMessage(e, 'Export failed'), 'error')
    }
  }

  const hasFilters = Boolean(searchInput.trim() || talkgroup || dateFrom || dateTo)
  const clearFilters = () => {
    setSearchInput('')
    setDebouncedSearch('')
    setTalkgroup('')
    setDateFrom('')
    setDateTo('')
  }

  return (
    <div className="ss-db-page">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 className="text-base font-semibold text-gray-200">Audio Logs</h2>
          <p className="text-xs text-gray-500">
            Browse, filter, select rows across pages, and download bulk audio ZIP archives.
          </p>
        </div>
        {hasFilters && (
          <button
            type="button"
            className="ss-btn-ghost h-8 px-3 text-xs cursor-pointer"
            onClick={clearFilters}
          >
            Clear filters
          </button>
        )}
      </div>

      <div className="ss-db-filters">
        <div className="min-w-0 w-full md:flex-1">
          <label className="ss-form-label" htmlFor="db-search">
            Search
          </label>
          <input
            id="db-search"
            type="search"
            className="ss-input min-h-[40px]"
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            placeholder="Transcript, filename, talkgroup…"
            autoComplete="off"
          />
        </div>
        <div className="w-full sm:w-auto">
          <label className="ss-form-label" htmlFor="db-talkgroup">
            Talkgroup
          </label>
          <select
            id="db-talkgroup"
            className="ss-select w-full sm:min-w-[11rem] min-h-[40px]"
            value={talkgroup}
            onChange={(e) => setTalkgroup(e.target.value)}
          >
            <option value="">All Talkgroups</option>
            {talkgroupList.map((tg) => (
              <option key={tg} value={tg}>
                {tg}
              </option>
            ))}
          </select>
        </div>
        <div className="w-full sm:w-auto">
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
        <div className="flex flex-wrap items-end gap-2.5 w-full sm:w-auto">
          <div className="flex-1 sm:flex-initial">
            <label className="ss-form-label" htmlFor="db-sort">
              Sort
            </label>
            <select
              id="db-sort"
              className="ss-select w-full sm:min-w-[10rem] min-h-[40px]"
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
          <div>
            <label className="ss-form-label" htmlFor="db-ps">
              Per page
            </label>
            <select
              id="db-ps"
              className="ss-select w-[4.5rem] min-h-[40px]"
              value={String(pageSize)}
              onChange={(e) => setPageSize(Number(e.target.value))}
            >
              {PAGE_SIZES.map((n) => (
                <option key={n} value={n}>
                  {n}
                </option>
              ))}
            </select>
          </div>
          <div className="flex items-end">
            <button
              type="button"
              className="ss-btn-ghost min-h-[40px] px-3.5 flex items-center justify-center cursor-pointer"
              onClick={onExport}
              disabled={query.isFetching}
            >
              Export CSV
            </button>
          </div>
        </div>
      </div>

      {selectedIds.size > 0 && (
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-indigo-500/35 bg-indigo-500/10 px-4 py-2.5">
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
              className="ss-btn-primary h-8 px-3.5 text-xs cursor-pointer disabled:opacity-50"
              onClick={() => void onBulkDownloadZip()}
              disabled={isDownloadingZip}
            >
              {isDownloadingZip
                ? 'Building ZIP…'
                : `Download ZIP (${selectedIds.size})`}
            </button>
            {isAdmin && (
              <button
                type="button"
                className="ss-btn-ghost h-8 px-3 text-xs text-red-300 border-red-500/30 hover:bg-red-500/15 cursor-pointer disabled:opacity-50"
                onClick={onBulkDelete}
                disabled={bulkDelMutation.isPending}
              >
                {bulkDelMutation.isPending ? 'Deleting…' : 'Delete Selected'}
              </button>
            )}
          </div>
        </div>
      )}

      {query.isError && (
        <p className="ss-form-error mb-4" role="alert">
          {errorMessage(query.error, 'Failed to load logs')}
        </p>
      )}

      {query.isLoading && <p className="text-sm text-gray-500">Loading…</p>}

      {!query.isLoading && !query.isError && rows.length === 0 && (
        <p className="ss-empty not-italic">No log entries for these filters.</p>
      )}

      {!query.isLoading && !query.isError && rows.length > 0 && (
        <>
          <div className="hidden md:block ss-db-table-wrap">
            <table className="ss-db-table">
              <thead>
                <tr>
                  <th className="ss-db-th w-9 text-center">
                    <input
                      ref={selectAllRef}
                      type="checkbox"
                      className="h-4 w-4 accent-indigo-500 cursor-pointer"
                      checked={allOnPageSelected}
                      onChange={toggleSelectPage}
                      aria-label="Select all entries on this page"
                    />
                  </th>
                  <th className="ss-db-th">Time</th>
                  <th className="ss-db-th">Talkgroup</th>
                  <th className="ss-db-th">Filename</th>
                  <th className="ss-db-th">Transcript</th>
                  <th className="ss-db-th">Dur</th>
                  <th className="ss-db-th">Size</th>
                  <th className="ss-db-th">Conf.</th>
                  <th className="ss-db-th text-right"> </th>
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
                      <tr>
                        <td className="ss-db-td p-0" colSpan={9}>
                          <LogExpandedRow row={row} />
                        </td>
                      </tr>
                    )}
                  </Fragment>
                ))}
              </tbody>
            </table>
          </div>

          <div className="md:hidden flex flex-col gap-3">
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

          <div className="ss-db-pager">
            <span className="w-full sm:w-auto text-center sm:text-left text-xs sm:text-sm">
              {total.toLocaleString()} entries
              {query.isFetching && !query.isLoading ? ' · …' : ''}
            </span>
            <div className="flex items-center justify-between sm:justify-end gap-2 w-full sm:w-auto">
              <button
                type="button"
                className="ss-btn-ghost min-h-[42px] px-4 flex-1 sm:flex-initial cursor-pointer"
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page <= 1 || query.isFetching}
              >
                Previous
              </button>
              <span className="text-gray-400 text-xs sm:text-sm px-1">
                Page {page}
                {totalPages > 0 ? ` of ${totalPages}` : ''}
              </span>
              <button
                type="button"
                className="ss-btn-ghost min-h-[42px] px-4 flex-1 sm:flex-initial cursor-pointer"
                onClick={() => setPage((p) => p + 1)}
                disabled={totalPages === 0 || page >= totalPages || query.isFetching}
              >
                Next
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  )
}
