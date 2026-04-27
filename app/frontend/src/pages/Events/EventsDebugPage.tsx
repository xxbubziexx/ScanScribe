import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { eventsApi } from '../../lib/events'
import { errorMessage } from '../../types/api'
import { useToast } from '../../context/ToastContext'
import type { PipelineDebugEntry } from '../../types/events'

function fmtTs(ts: number | undefined) {
  if (ts == null || Number.isNaN(ts)) return '—'
  return new Date(ts * 1000).toLocaleString()
}

export function EventsDebugPage() {
  const queryClient = useQueryClient()
  const { addToast } = useToast()
  const [limit, setLimit] = useState(80)

  const debugQuery = useQuery({
    queryKey: ['events-debug', limit],
    queryFn: () => eventsApi.debugRecent(limit),
    staleTime: 5_000,
  })

  const clearMutation = useMutation({
    mutationFn: () => eventsApi.clearDebug(),
    onSuccess: (data) => {
      addToast(`Cleared ${data.removed} debug entr${data.removed === 1 ? 'y' : 'ies'}`, 'success')
      void queryClient.invalidateQueries({ queryKey: ['events-debug'] })
    },
    onError: (e: unknown) => addToast(errorMessage(e, 'Failed to clear debug log'), 'error'),
  })

  const entries = debugQuery.data ?? []

  const withErrors = useMemo(() => entries.filter((e) => (e.error || '').trim().length > 0).length, [entries])

  return (
    <div className="ss-events-page">
      <div className="ss-events-topbar">
        <h1 className="ss-events-title">Pipeline debug</h1>
        <div className="ss-events-live">
          <button
            type="button"
            className="ss-btn-ghost"
            disabled={debugQuery.isFetching}
            onClick={() => void debugQuery.refetch()}
          >
            Refresh
          </button>
          <button
            type="button"
            className="ss-btn-danger-soft"
            disabled={clearMutation.isPending || entries.length === 0}
            onClick={() => {
              if (!window.confirm('Clear all pipeline debug entries from the events database?')) return
              clearMutation.mutate()
            }}
          >
            Clear all
          </button>
        </div>
      </div>
      <p className="ss-events-sub">
        Recent NER / LLM routing entries from the events pipeline (newest first). Stored in the events DB; safe to clear
        for housekeeping.
      </p>

      <div className="ss-events-debug-controls">
        <label className="flex items-center gap-2 text-xs text-gray-500" htmlFor="debug-limit">
          Rows
        </label>
        <select
          id="debug-limit"
          className="ss-select h-8 text-xs"
          value={String(limit)}
          onChange={(e) => setLimit(Number(e.target.value))}
        >
          {[40, 80, 120, 160, 200].map((n) => (
            <option key={n} value={n}>
              {n}
            </option>
          ))}
        </select>
        <span className="ss-events-pill-tiny">{entries.length} loaded</span>
        {withErrors > 0 ? (
          <span className="rounded-md border border-amber-500/30 bg-amber-500/10 px-2 py-1 text-[10px] font-medium text-amber-200">
            {withErrors} with error
          </span>
        ) : null}
      </div>

      {debugQuery.isError && (
        <p className="ss-form-error" role="alert">
          {errorMessage(debugQuery.error, 'Failed to load debug entries')}
        </p>
      )}

      {debugQuery.isSuccess && entries.length === 0 ? (
        <p className="ss-empty not-italic">No debug entries yet. Run the events pipeline to populate this log.</p>
      ) : (
        <ul className="ss-events-debug-list">
          {entries.map((row, i) => (
            <li key={`debug-${i}-${row.log_entry_id ?? 0}-${row.ts ?? 0}`}>
              <DebugEntryCard entry={row} index={entries.length - i} />
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

function DebugEntryCard({ entry, index }: { entry: PipelineDebugEntry; index: number }) {
  const [open, setOpen] = useState(false)
  const err = (entry.error || '').trim()

  return (
    <article className="ss-events-debug-card">
      <button
        type="button"
        className="flex w-full flex-wrap items-start justify-between gap-2 text-left"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
      >
        <div className="min-w-0 flex-1">
          <p className="font-mono text-[11px] text-gray-500">
            #{index} · {fmtTs(entry.ts)}
          </p>
          <p className="mt-0.5 truncate text-sm font-medium text-gray-200">
            <span className="text-indigo-200/90">{entry.action || '—'}</span>
            <span className="mx-1.5 text-gray-600">·</span>
            <span className="font-mono text-xs text-gray-400">{entry.event_id || '—'}</span>
          </p>
          <p className="mt-1 text-[11px] text-gray-500">
            monitor {entry.monitor_id ?? '—'} · log_entry {entry.log_entry_id ?? '—'} · {entry.duration_ms ?? '—'} ms
            {entry.llm_model ? ` · ${entry.llm_model}` : ''}
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          {err ? (
            <span className="rounded bg-amber-500/15 px-1.5 py-0.5 text-[10px] font-semibold uppercase text-amber-200">
              Error
            </span>
          ) : null}
          <span className="text-[11px] text-gray-500">{open ? '▼' : '▶'}</span>
        </div>
      </button>

      {entry.transcript ? (
        <p className="ss-events-debug-preview">{entry.transcript}</p>
      ) : null}

      {open ? (
        <div className="ss-events-debug-body">
          {err ? (
            <div>
              <p className="ss-events-section-title mb-1">Error</p>
              <pre className="ss-events-pre-block overflow-x-auto rounded-md border border-amber-500/20 bg-black/40 p-2 text-xs text-amber-100">
                {err}
              </pre>
            </div>
          ) : null}
          {entry.transcript ? (
            <div>
              <p className="ss-events-section-title mb-1">Transcript</p>
              <pre className="ss-events-pre-block max-h-48 overflow-auto text-xs text-gray-300">{entry.transcript}</pre>
            </div>
          ) : null}
          {entry.entities ? (
            <div>
              <p className="ss-events-section-title mb-1">Entities</p>
              <pre className="ss-events-pre-block max-h-48 overflow-auto text-xs text-gray-300">{entry.entities}</pre>
            </div>
          ) : null}
          {entry.llm_output ? (
            <div>
              <p className="ss-events-section-title mb-1">LLM output</p>
              <pre className="ss-events-pre-block max-h-64 overflow-auto text-xs text-gray-300">{entry.llm_output}</pre>
            </div>
          ) : null}
          {entry.raw_output ? (
            <div>
              <p className="ss-events-section-title mb-1">Raw output</p>
              <pre className="ss-events-pre-block max-h-64 overflow-auto text-xs text-gray-300">{entry.raw_output}</pre>
            </div>
          ) : null}
        </div>
      ) : null}
    </article>
  )
}
