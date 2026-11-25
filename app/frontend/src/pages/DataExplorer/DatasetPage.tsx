import { Fragment, useCallback, useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useAuth } from '@/context/AuthContext'
import { useToast } from '@/context/ToastContext'
import { buildListParams, downloadAudioFile, downloadDatasetExport, logsApi } from '@/lib/logs'
import { DatabaseDateRangePicker } from '@/components/database/DatabaseDateRangePicker'
import { errorMessage } from '@/types/api'
import type { LogListEntry, LogsSortBy } from '@/types/logs'
import { ScAudioPlayer } from '@/components/ui/ScAudioPlayer'
import { formatBytes } from '@/pages/Database/utils/formatBytes'

const SORT_OPTIONS: { value: LogsSortBy; label: string }[] = [
  { value: 'timestamp_desc', label: 'Newest first' },
  { value: 'timestamp_asc', label: 'Oldest first' },
  { value: 'filename', label: 'Filename' },
  { value: 'talkgroup', label: 'Talkgroup' },
]

const PAGE_SIZES = [25, 50, 100] as const

export function DatasetPage() {
  const { user } = useAuth()
  const { addToast } = useToast()
  const queryClient = useQueryClient()
  const isAdmin = user?.is_admin === true

  const [searchInput, setSearchInput] = useState('')
  const [debouncedSearch, setDebouncedSearch] = useState('')
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')

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
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set())

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
    queryKey: [
      'dataset-logs',
      page,
      pageSize,
      debouncedSearch,
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
          dateFrom,
          dateTo,
          sortBy,
          is_reviewed: true,
        }),
      ),
  })

  const data = query.data
  const rows = data?.logs ?? []
  const total = data?.total ?? 0
  const totalPages = Math.max(1, data?.total_pages ?? 1)

  const delMutation = useMutation({
    mutationFn: (id: number) => logsApi.delete(id),
    onSuccess: () => {
      addToast('Log entry removed', 'success')
      void queryClient.invalidateQueries({ queryKey: ['dataset-logs'] })
      void queryClient.invalidateQueries({ queryKey: ['database-logs'] })
      void queryClient.invalidateQueries({ queryKey: ['database-overview'] })
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

  const clearMutation = useMutation({
    mutationFn: () => logsApi.clearReviewed(),
    onSuccess: (res) => {
      addToast(res.message || 'Dataset cleared', 'success')
      setSelectedIds(new Set())
      void queryClient.invalidateQueries({ queryKey: ['dataset-logs'] })
      void queryClient.invalidateQueries({ queryKey: ['database-logs'] })
      void queryClient.invalidateQueries({ queryKey: ['database-overview'] })
    },
    onError: (e: unknown) => addToast(errorMessage(e, 'Failed to clear dataset'), 'error'),
  })

  const onClearDataset = () => {
    if (!window.confirm('Clear all spans from the dataset? This will unreview all entries and empty the dataset list.')) return
    clearMutation.mutate()
  }

  const onExportDataset = async () => {
    try {
      await downloadDatasetExport()
      addToast('Dataset export started', 'success')
    } catch (e) {
      addToast(errorMessage(e, 'Dataset export failed'), 'error')
    }
  }

  const allOnPageSelected = rows.length > 0 && rows.every((r) => selectedIds.has(r.id))
  const hasFilters = Boolean(searchInput.trim() || dateFrom || dateTo)

  return (
    <div className="ss-workbench-pane">
      <div className="ss-workbench-header">
        <div className="flex items-center gap-3">
          <h2 className="text-sm font-semibold text-gray-100">Fine-Tuning Dataset</h2>
          <span className="ss-events-pill-tiny font-mono">
            {total.toLocaleString()} reviewed
          </span>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {hasFilters && (
            <button
              type="button"
              className="ss-btn-ghost h-8 px-3 text-xs cursor-pointer"
              onClick={() => {
                setSearchInput('')
                setDebouncedSearch('')
                setDateFrom('')
                setDateTo('')
              }}
            >
              Clear Filters
            </button>
          )}
          <button
            type="button"
            className="ss-btn-ghost h-8 px-3 text-xs text-red-400 hover:bg-red-400/10 hover:text-red-300 border-red-500/30 cursor-pointer"
            onClick={onClearDataset}
            disabled={clearMutation.isPending || query.isFetching || total === 0}
            title="Unreview and remove all spans from this dataset"
          >
            {clearMutation.isPending ? 'Clearing…' : 'Clear Dataset'}
          </button>
          <button
            type="button"
            className="ss-btn-primary h-8 px-3 text-xs cursor-pointer"
            onClick={onExportDataset}
            disabled={query.isFetching || total === 0}
          >
            Export Whisper ZIP
          </button>
        </div>
      </div>

      <div className="ss-workbench-filters">
        <div className="min-w-[14rem] flex-1">
          <label className="ss-form-label" htmlFor="dataset-search">
            Search
          </label>
          <input
            id="dataset-search"
            type="search"
            className="ss-input h-8 text-xs"
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            placeholder="Transcript, filename, talkgroup…"
            autoComplete="off"
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
          <label className="ss-form-label" htmlFor="dataset-sort">
            Sort
          </label>
          <select
            id="dataset-sort"
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
            <span className="font-semibold text-indigo-100">{selectedIds.size} spans selected</span>
            <button
              type="button"
              className="text-indigo-300 hover:text-white underline cursor-pointer"
              onClick={() => setSelectedIds(new Set())}
            >
              Clear selection
            </button>
          </div>
          <div className="flex gap-2">
            <button
              type="button"
              className="ss-btn-ghost h-7 px-3 text-xs text-red-300 border-red-500/30 hover:bg-red-500/15 cursor-pointer"
              onClick={async () => {
                if (!window.confirm(`Remove ${selectedIds.size} spans from dataset?`)) return
                for (const id of selectedIds) await logsApi.unreview(id)
                addToast('Removed selected spans', 'success')
                setSelectedIds(new Set())
                void queryClient.invalidateQueries({ queryKey: ['dataset-logs'] })
                void queryClient.invalidateQueries({ queryKey: ['database-logs'] })
                void queryClient.invalidateQueries({ queryKey: ['database-overview'] })
              }}
            >
              Remove Selected
            </button>
            <button
              type="button"
              className="ss-btn-primary h-7 px-3 text-xs cursor-pointer"
              onClick={async () => {
                try {
                  const token = localStorage.getItem('access_token')
                  const res = await fetch('/api/logs/export-dataset', {
                    method: 'POST',
                    headers: {
                      'Content-Type': 'application/json',
                      ...(token ? { Authorization: `Bearer ${token}` } : {}),
                    },
                    body: JSON.stringify({ log_ids: Array.from(selectedIds) }),
                  })
                  if (!res.ok) throw new Error('Export failed')
                  const blob = await res.blob()
                  const url = window.URL.createObjectURL(blob)
                  const a = document.createElement('a')
                  a.href = url
                  a.download = `whisper_dataset_selected.zip`
                  document.body.appendChild(a)
                  a.click()
                  a.remove()
                  window.URL.revokeObjectURL(url)
                  addToast('Dataset exported', 'success')
                } catch (e: unknown) {
                  addToast(errorMessage(e, 'Export failed'), 'error')
                }
              }}
            >
              Download Selected ZIP
            </button>
          </div>
        </div>
      )}

      <div className="ss-workbench-grid-wrap">
        {query.isError && (
          <p className="ss-form-error m-4" role="alert">
            {errorMessage(query.error, 'Failed to load logs')}
          </p>
        )}

        {query.isLoading && <p className="p-5 text-xs text-gray-500">Loading dataset…</p>}

        {!query.isLoading && !query.isError && rows.length === 0 && (
          <p className="ss-empty m-4 not-italic">No reviewed entries for these filters.</p>
        )}

        {!query.isLoading && !query.isError && rows.length > 0 && (
          <table className="ss-workbench-table">
            <thead>
              <tr>
                <th className="w-9 text-center">
                  <input
                    type="checkbox"
                    className="h-3.5 w-3.5 accent-indigo-500 cursor-pointer"
                    checked={allOnPageSelected}
                    onChange={() => {
                      const next = new Set(selectedIds)
                      if (allOnPageSelected) {
                        for (const r of rows) next.delete(r.id)
                      } else {
                        for (const r of rows) next.add(r.id)
                      }
                      setSelectedIds(next)
                    }}
                    aria-label="Select all dataset spans on this page"
                  />
                </th>
                <th>Time</th>
                <th>Talkgroup</th>
                <th>Filename</th>
                <th>Reviewed Transcript</th>
                <th className="text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <Fragment key={row.id}>
                  <LogRow
                    selected={selectedIds.has(row.id)}
                    onToggleSelect={() => {
                      const newSet = new Set(selectedIds)
                      if (newSet.has(row.id)) newSet.delete(row.id)
                      else newSet.add(row.id)
                      setSelectedIds(newSet)
                    }}
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
                      <td className="p-0" colSpan={6}>
                        <LogExpandedRow row={row} />
                      </td>
                    </tr>
                  )}
                </Fragment>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="ss-workbench-footer">
        <div className="flex items-center gap-3">
          <span>
            {total > 0
              ? `Showing ${(page - 1) * pageSize + 1}–${Math.min(page * pageSize, total)} of ${total.toLocaleString()}`
              : '0 entries'}
          </span>
          <label className="flex items-center gap-1.5 text-gray-500" htmlFor="dataset-ps">
            <span>Rows</span>
            <select
              id="dataset-ps"
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
          >
            »»
          </button>
        </div>
      </div>
    </div>
  )
}

function LogRow({
  row,
  isAdmin,
  onDelete,
  deleting,
  expanded,
  onToggleExpand,
  selected,
  onToggleSelect,
}: {
  row: LogListEntry
  isAdmin: boolean
  selected?: boolean
  onToggleSelect?: () => void
  onDelete: (id: number) => void
  deleting: boolean
  expanded: boolean
  onToggleExpand: () => void
}) {
  const hasAudio = row.audio_path && row.audio_path !== 'file not saved'
  return (
    <tr
      className={`ss-db-row ${expanded ? 'ss-db-row--expanded' : ''} ${
        selected ? 'bg-indigo-500/[0.08]' : ''
      }`}
      onClick={onToggleExpand}
      aria-expanded={expanded}
    >
      <td className="text-center" onClick={(e) => e.stopPropagation()}>
        <input
          type="checkbox"
          className="h-3.5 w-3.5 accent-indigo-500 cursor-pointer"
          checked={selected}
          onChange={(e) => {
            e.stopPropagation()
            if (onToggleSelect) onToggleSelect()
          }}
        />
      </td>
      <td className="whitespace-nowrap font-mono text-xs text-slate-300">
        <span className={`ss-db-expand-icon ${expanded ? 'ss-db-expand-icon--open' : ''}`}>▶</span>{' '}
        {row.timestamp
          ? new Date(row.timestamp).toLocaleString(undefined, { dateStyle: 'short', timeStyle: 'short' })
          : '—'}
      </td>
      <td>
        <span className="inline-block max-w-[13rem] truncate font-semibold text-sky-300" title={row.talkgroup ?? ''}>
          {row.talkgroup || '—'}
        </span>
      </td>
      <td title={row.filename}>
        <span className="block max-w-[18rem] truncate font-mono text-[11px] text-slate-500">{row.filename || '—'}</span>
      </td>
      <td>
        <span className="ss-db-td-clip block font-medium text-slate-100">
          {row.corrected_transcript || row.transcript || '—'}
        </span>
      </td>
      <td className="text-right">
        <div className="ss-db-actions">
          {hasAudio && (
            <button
              type="button"
              className="rounded px-2 py-0.5 text-[11px] font-medium text-sky-300 transition hover:bg-sky-500/15 hover:text-sky-200 cursor-pointer"
              onClick={(e) => {
                e.stopPropagation()
                void downloadAudioFile(row.audio_path!, row.filename || undefined).catch((err) => {
                  console.error('Download failed:', err)
                })
              }}
              title="Download audio file directly"
              aria-label="Download audio file directly"
            >
              Audio
            </button>
          )}
          {isAdmin && (
            <button
              type="button"
              className="rounded px-2 py-0.5 text-[11px] font-medium text-rose-400 transition hover:bg-rose-500/15 hover:text-rose-300 cursor-pointer disabled:opacity-40"
              onClick={(e) => {
                e.stopPropagation()
                onDelete(row.id)
              }}
              disabled={deleting}
              title="Remove log entry"
              aria-label="Remove log entry"
            >
              Delete
            </button>
          )}
        </div>
      </td>
    </tr>
  )
}

function kv(label: string, value: string) {
  return (
    <div className="ss-db-expand-field">
      <span className="ss-db-expand-label">{label}</span>
      <span className="ss-db-expand-value">{value}</span>
    </div>
  )
}

function LogExpandedRow({ row }: { row: LogListEntry }) {
  const hasAudio = !!row.audio_path && row.audio_path !== 'file not saved'
  const audioSrc = hasAudio ? `/${row.audio_path}` : ''
  const ts = row.timestamp
    ? new Date(row.timestamp).toLocaleString(undefined, {
        dateStyle: 'short',
        timeStyle: 'medium',
      })
    : '—'
  const confidence = row.confidence != null ? `${Math.round(row.confidence * 100)}%` : '—'

  const [text, setText] = useState(row.corrected_transcript ?? row.transcript ?? '')
  const queryClient = useQueryClient()
  const { addToast } = useToast()

  const unreviewMutation = useMutation({
    mutationFn: () => logsApi.unreview(row.id),
    onSuccess: () => {
      addToast('Removed from dataset', 'success')
      void queryClient.invalidateQueries({ queryKey: ['dataset-logs'] })
      void queryClient.invalidateQueries({ queryKey: ['database-logs'] })
      void queryClient.invalidateQueries({ queryKey: ['database-overview'] })
    },
  })

  const reviewMutation = useMutation({
    mutationFn: (newText: string) => logsApi.review(row.id, newText),
    onSuccess: () => {
      addToast('Transcript updated', 'success')
      void queryClient.invalidateQueries({ queryKey: ['dataset-logs'] })
      void queryClient.invalidateQueries({ queryKey: ['database-logs'] })
    },
    onError: (e: unknown) => addToast(errorMessage(e, 'Update failed'), 'error'),
  })

  return (
    <div className="ss-db-expand">
      <div className="ss-db-expand-grid">
        {kv('ID', String(row.id))}
        {kv('Filename', row.filename || '—')}
        {kv('Talkgroup', row.talkgroup || '—')}
        {kv('Date & time', ts)}
        {kv('Duration', typeof row.duration === 'number' ? `${row.duration.toFixed(2)} seconds` : '—')}
        {kv('File size', formatBytes(row.file_size || 0))}
        {kv('Confidence', confidence)}
        {kv('Audio path', row.audio_path || '—')}
      </div>

      <div className="ss-db-expand-field mt-4">
        <span className="ss-db-expand-label flex items-center gap-2">
          Full transcript {row.is_reviewed && <span className="text-green-500 text-sm">✓ Reviewed</span>}
        </span>
        <textarea
          className="ss-input mt-1 w-full min-h-[100px] font-mono text-sm"
          value={text}
          onChange={(e) => setText(e.target.value)}
        />
        <div className="mt-2 flex gap-2">
          <button
            type="button"
            className="ss-btn-primary"
            onClick={() => reviewMutation.mutate(text)}
            disabled={reviewMutation.isPending}
          >
            {reviewMutation.isPending ? 'Saving...' : 'Accept & Save'}
          </button>
          <button
            type="button"
            className="ss-btn-ghost text-red-400 hover:bg-red-400/10 py-1.5 px-3"
            onClick={() => unreviewMutation.mutate()}
            disabled={unreviewMutation.isPending}
          >
            {unreviewMutation.isPending ? 'Removing...' : 'Remove from Dataset'}
          </button>
        </div>
      </div>

      {hasAudio && (
        <div className="ss-db-expand-audio mt-4">
          <span className="ss-db-expand-label">Audio playback</span>
          <ScAudioPlayer src={audioSrc} />
        </div>
      )}
    </div>
  )
}
