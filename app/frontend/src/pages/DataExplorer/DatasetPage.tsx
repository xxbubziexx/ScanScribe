import { Fragment, useCallback, useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useAuth } from '@/context/AuthContext'
import { useToast } from '@/context/ToastContext'
import { buildListParams, downloadAudioFile, downloadDatasetExport, logsApi } from '@/lib/logs'
import { DatabaseDateRangePicker } from '@/components/database/DatabaseDateRangePicker'
import { getSavedDateRange, saveDateRange } from '@/lib/dateSelection'
import { errorMessage } from '@/types/api'
import type { LogListEntry, LogsSortBy } from '@/types/logs'
import { ScAudioPlayer } from '@/components/ui/ScAudioPlayer'

function formatBytes(bytes: number) {
  if (!bytes) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return `${parseFloat((bytes / k ** i).toFixed(1))} ${sizes[i]}`
}

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
  const totalPages = data?.total_pages ?? 0

  const delMutation = useMutation({
    mutationFn: (id: number) => logsApi.delete(id),
    onSuccess: () => {
      addToast('Log entry removed', 'success')
      void queryClient.invalidateQueries({ queryKey: ['dataset-logs'] })
      void queryClient.invalidateQueries({ queryKey: ['database-logs'] })
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

  return (
    <div className="ss-db-page">
      <h1 className="ss-db-title">Fine-Tuning Dataset</h1>
      <p className="mb-4 text-sm text-gray-500">Manage reviewed spans for your Whisper fine-tuning dataset.</p>

      <div className="ss-db-filters">
        <div className="min-w-0 flex-1">
          <label className="ss-form-label" htmlFor="db-search">
            Search
          </label>
          <input
            id="db-search"
            type="search"
            className="ss-input"
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            placeholder="Transcript, filename, talkgroup…"
            autoComplete="off"
          />
        </div>
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
        <div>
          <label className="ss-form-label" htmlFor="db-sort">
            Sort
          </label>
          <select
            id="db-sort"
            className="ss-select min-w-[10rem]"
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
            className="ss-select w-[4.5rem]"
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
        <div className="flex items-end gap-2">
          <button
            type="button"
            className="ss-btn-ghost text-red-400 hover:bg-red-400/10 hover:text-red-300 border-red-500/30"
            onClick={onClearDataset}
            disabled={clearMutation.isPending || query.isFetching || total === 0}
            title="Unreview and remove all spans from this dataset"
          >
            {clearMutation.isPending ? 'Clearing…' : 'Clear Dataset'}
          </button>
          <button
            type="button"
            className="ss-btn-ghost"
            onClick={onExportDataset}
            disabled={query.isFetching || total === 0}
          >
            Export Fine-Tuning Dataset
          </button>
        </div>
      </div>

      {selectedIds.size > 0 && (
        <div className="bg-indigo-500/10 border border-indigo-500/30 p-2 rounded flex items-center justify-between mb-4">
          <span className="text-sm text-indigo-200 ml-2 font-bold">{selectedIds.size} spans selected</span>
          <div className="flex gap-2">
            <button className="ss-btn-ghost text-red-400 hover:bg-red-400/10 text-xs py-1" onClick={async () => {
              if (!window.confirm(`Remove ${selectedIds.size} spans from dataset?`)) return
              for (const id of selectedIds) await logsApi.unreview(id)
              addToast('Removed selected spans', 'success')
              setSelectedIds(new Set())
              void queryClient.invalidateQueries({ queryKey: ['dataset-logs'] })
              void queryClient.invalidateQueries({ queryKey: ['database-logs'] })
            }}>Remove Selected</button>
            <button className="ss-btn-primary text-xs py-1" onClick={async () => {
              try {
                const res = await fetch('/api/logs/export-dataset', {
                  method: 'POST',
                  headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${localStorage.getItem('token')}`
                  },
                  body: JSON.stringify({ log_ids: Array.from(selectedIds) })
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
              } catch (e: any) {
                addToast(e.message, 'error')
              }
            }}>Download Selected</button>
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
          <div className="ss-db-table-wrap">
            <table className="ss-db-table">
              <thead>
                <tr>
                  <th className="ss-db-th w-10"></th>
                  <th className="ss-db-th">Time</th>
                  <th className="ss-db-th">Talkgroup</th>
                  <th className="ss-db-th">Filename</th>
                  <th className="ss-db-th">Transcript</th>
                  <th className="ss-db-th text-right"> </th>
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
                        <td className="ss-db-td p-0" colSpan={6}>
                          <LogExpandedRow row={row} />
                        </td>
                      </tr>
                    )}
                  </Fragment>
                ))}
              </tbody>
            </table>
          </div>

          <div className="ss-db-pager">
            <span>
              {total} entries
              {query.isFetching && !query.isLoading ? ' · …' : ''}
            </span>
            <div className="flex items-center gap-2">
              <button
                type="button"
                className="ss-btn-ghost"
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page <= 1 || query.isFetching}
              >
                Previous
              </button>
              <span className="text-gray-400">
                Page {page}
                {totalPages > 0 ? ` of ${totalPages}` : ''}
              </span>
              <button
                type="button"
                className="ss-btn-ghost"
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
      className={`ss-db-row ${expanded ? 'ss-db-row--expanded' : ''}`}
      onClick={onToggleExpand}
      aria-expanded={expanded}
        >
      <td className="ss-db-td text-center" onClick={(e) => e.stopPropagation()}>
        <input type="checkbox" className="ss-checkbox" checked={selected} onChange={(e) => { e.stopPropagation(); if (onToggleSelect) onToggleSelect(); }} />
      </td>
      <td className="ss-db-td font-mono text-xs text-gray-400">
        <span className={`ss-db-expand-icon ${expanded ? 'ss-db-expand-icon--open' : ''}`}>▶</span>{' '}
        {row.timestamp
          ? new Date(row.timestamp).toLocaleString(undefined, { dateStyle: 'short', timeStyle: 'short' })
          : '—'}
      </td>
      <td className="ss-db-td">
        <span className="inline-block max-w-[12rem] truncate text-indigo-200" title={row.talkgroup ?? ''}>
          {row.talkgroup || '—'}
        </span>
      </td>
      <td className="ss-db-td" title={row.filename}>
        <span className="ss-db-filename-clip block">{row.filename || '—'}</span>
      </td>
      <td className="ss-db-td">
        <span className="ss-db-td-clip block text-gray-400">
          
          {row.corrected_transcript || row.transcript || '—'}
        </span>
      </td>
      
      
      
      <td className="ss-db-td text-right">
        <div className="ss-db-actions">
          {hasAudio && (
            <button
              type="button"
              className="ss-text-link"
              onClick={(e) => {
                e.stopPropagation()
                void downloadAudioFile(row.audio_path!, row.filename || undefined).catch((err) => {
                  console.error('Download failed:', err)
                })
              }}
              title="Download audio file directly"
              aria-label="Download audio file directly"
            >
              ⬇️
            </button>
          )}
          {isAdmin && (
            <button
              type="button"
              className="ss-btn-filter-clear"
              onClick={(e) => {
                e.stopPropagation()
                onDelete(row.id)
              }}
              disabled={deleting}
              title="Remove log entry"
              aria-label="Remove log entry"
            >
              🗑️
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
