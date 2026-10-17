import { Fragment, useCallback, useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useAuth } from '@/context/AuthContext'
import { useToast } from '@/context/ToastContext'
import { buildListParams, downloadLogsExport, logsApi } from '@/lib/logs'
import { DatabaseDateRangePicker } from '@/components/database/DatabaseDateRangePicker'
import { getSavedDateRange, saveDateRange } from '@/lib/dateSelection'
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
  const isAdmin = user?.is_admin === true

  const [searchInput, setSearchInput] = useState('')
  const [debouncedSearch, setDebouncedSearch] = useState('')

  const saved = getSavedDateRange()
  const [dateFrom, setDateFrom] = useState(saved?.dateFrom ?? '')
  const [dateTo, setDateTo] = useState(saved?.dateTo ?? '')

  const activeDatesQuery = useQuery({
    queryKey: ['database-active-dates'],
    queryFn: () => logsApi.activeDates(),
    staleTime: 5 * 60_000,
  })
  const activeDateList = activeDatesQuery.data?.dates
  const [sortBy, setSortBy] = useState<LogsSortBy>('timestamp_desc')
  const [pageSize, setPageSize] = useState(50)
  const [page, setPage] = useState(1)
  const [expandedId, setExpandedId] = useState<number | null>(null)

  useEffect(() => {
    const t = window.setTimeout(() => setDebouncedSearch(searchInput), 400)
    return () => window.clearTimeout(t)
  }, [searchInput])

  useEffect(() => {
    setPage(1)
  }, [debouncedSearch, dateFrom, dateTo, sortBy, pageSize])

  useEffect(() => {
    setExpandedId(null)
  }, [page, pageSize, debouncedSearch, dateFrom, dateTo, sortBy])

  const query = useQuery({
    queryKey: ['database-logs', page, pageSize, debouncedSearch, dateFrom, dateTo, sortBy],
    queryFn: () =>
      logsApi.list(
        buildListParams({
          page,
          pageSize,
          search: debouncedSearch,
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

  const delMutation = useMutation({
    mutationFn: (id: number) => logsApi.delete(id),
    onSuccess: () => {
      addToast('Log entry removed', 'success')
      void queryClient.invalidateQueries({ queryKey: ['database-logs'] })
      void queryClient.invalidateQueries({ queryKey: ['dataset-logs'] })
    },
    onError: (e: unknown) => addToast(errorMessage(e, 'Delete failed'), 'error'),
  })

  const onDelete = useCallback(
    (id: number) => {
      if (!isAdmin) return
      if (!window.confirm('Delete this log entry?')) return
      delMutation.mutate(id)
    },
    [delMutation, isAdmin],
  )

  const onExport = async () => {
    try {
      await downloadLogsExport({ search: debouncedSearch, dateFrom, dateTo })
      addToast('Export started', 'success')
    } catch (e) {
      addToast(errorMessage(e, 'Export failed'), 'error')
    }
  }

  return (
    <div className="ss-db-page">
      <h1 className="ss-db-title">Database</h1>
      <p className="mb-4 text-sm text-gray-500">Browse and search transcription log entries.</p>

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
          <DatabaseDateRangePicker
            from={dateFrom}
            to={dateTo}
            onChange={(a, b) => {
              setDateFrom(a)
              setDateTo(b)
              saveDateRange(a, b)
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
                      onDelete={onDelete}
                      deleting={delMutation.isPending}
                      expanded={expandedId === row.id}
                      onToggleExpand={() =>
                        setExpandedId((cur) => (cur === row.id ? null : row.id))
                      }
                    />
                    {expandedId === row.id && (
                      <tr>
                        <td className="ss-db-td p-0" colSpan={8}>
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
                onDelete={onDelete}
                deleting={delMutation.isPending}
                expanded={expandedId === row.id}
                onToggleExpand={() => setExpandedId((cur) => (cur === row.id ? null : row.id))}
              />
            ))}
          </div>

          <div className="ss-db-pager">
            <span className="w-full sm:w-auto text-center sm:text-left text-xs sm:text-sm">
              {total} entries
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
