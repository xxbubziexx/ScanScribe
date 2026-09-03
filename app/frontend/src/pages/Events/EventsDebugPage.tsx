import { useMemo, useState, useRef, useEffect } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { errorMessage } from '@/types/api'
import { eventsApi } from '@/lib/events'
import { useToast } from '@/context/ToastContext'
import type { PipelineDebugEntry } from '@/types/events'

function fmtTs(ts?: number): string {
  if (ts == null || Number.isNaN(ts)) return '—'
  return new Date(ts * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

function isPipelineDebugFailure(e: PipelineDebugEntry): boolean {
  const a = (e.action || '').toLowerCase()
  return (
    a.includes('error') ||
    a.includes('fail') ||
    a === 'router_error' ||
    Boolean(e.error && e.error.trim().length > 0)
  )
}

function isPipelineDebugConfigWarning(e: PipelineDebugEntry): boolean {
  const a = (e.action || '').toLowerCase()
  return a.includes('config') || a.includes('missing')
}

export function EventsDebugPage() {
  const queryClient = useQueryClient()
  const { addToast } = useToast()
  const [limit, setLimit] = useState(80)
  const [viewMode, setViewMode] = useState<'both' | 'terminal' | 'cards'>('both')
  const [autoScroll, setAutoScroll] = useState(true)
  const [consoleFilter, setConsoleFilter] = useState('')
  const terminalEndRef = useRef<HTMLDivElement>(null)

  const debugQuery = useQuery({
    queryKey: ['events-debug', limit],
    queryFn: () => eventsApi.debugRecent(limit),
    refetchInterval: 3000,
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

  // Ascending order for the terminal so the newest logs appear at the bottom
  const chronologicalEntries = useMemo(() => [...entries].reverse(), [entries])

  const withErrors = useMemo(
    () => entries.filter((e) => isPipelineDebugFailure(e) && (e.error || '').trim().length > 0).length,
    [entries],
  )

  useEffect(() => {
    if (autoScroll && terminalEndRef.current) {
      terminalEndRef.current.scrollIntoView({ behavior: 'smooth' })
    }
  }, [chronologicalEntries, autoScroll])

  const rawConsoleOutput = useMemo(() => {
    return chronologicalEntries.map((e) => {
      const time = fmtTs(e.ts)
      const action = (e.action || 'IDLE').toUpperCase()
      const logId = e.log_entry_id ? `#${e.log_entry_id}` : 'N/A'
      const duration = e.duration_ms ? `${e.duration_ms}ms` : '0ms'
      const transcript = e.transcript || ''
      const err = e.error ? `\n  [ERROR] ${e.error}` : ''
      const llm = e.llm_output ? `\n  [LLM_OUTPUT] ${e.llm_output}` : ''
      return `[${time}] [${action}] [Log ${logId}] (${duration}) "${transcript}"${err}${llm}`
    }).join('\n\n')
  }, [chronologicalEntries])

  const copyToClipboard = () => {
    navigator.clipboard.writeText(rawConsoleOutput)
    addToast('Raw terminal log copied to clipboard', 'success')
  }

  const filteredChronological = useMemo(() => {
    if (!consoleFilter.trim()) return chronologicalEntries
    const q = consoleFilter.toLowerCase()
    return chronologicalEntries.filter(
      (e) =>
        (e.transcript && e.transcript.toLowerCase().includes(q)) ||
        (e.action && e.action.toLowerCase().includes(q)) ||
        (e.llm_output && e.llm_output.toLowerCase().includes(q)) ||
        (e.error && e.error.toLowerCase().includes(q))
    )
  }, [chronologicalEntries, consoleFilter])

  return (
    <div className="ss-events-page p-6 max-w-7xl mx-auto flex flex-col gap-6">
      {/* Top Header */}
      <div className="ss-events-topbar flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-xl font-bold text-gray-100 flex items-center gap-2.5">
            <span>Pipeline & LLM Terminal Console</span>
            <span className="flex h-2 w-2 relative">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
              <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
            </span>
          </h1>
          <p className="text-xs text-gray-400 mt-1">
            Real-time live telemetry stream of incoming spans, prompt routing, OpenRouter responses, and errors.
          </p>
        </div>
        <div className="flex items-center gap-2">
          {/* View Mode Toggle */}
          <div className="flex rounded-lg border border-white/10 bg-black/40 p-0.5 text-xs">
            <button
              type="button"
              onClick={() => setViewMode('both')}
              className={`px-2.5 py-1 rounded transition ${viewMode === 'both' ? 'bg-indigo-600 text-white font-medium' : 'text-gray-400 hover:text-white'}`}
            >
              Split View
            </button>
            <button
              type="button"
              onClick={() => setViewMode('terminal')}
              className={`px-2.5 py-1 rounded transition ${viewMode === 'terminal' ? 'bg-indigo-600 text-white font-medium' : 'text-gray-400 hover:text-white'}`}
            >
              Raw Console Only
            </button>
            <button
              type="button"
              onClick={() => setViewMode('cards')}
              className={`px-2.5 py-1 rounded transition ${viewMode === 'cards' ? 'bg-indigo-600 text-white font-medium' : 'text-gray-400 hover:text-white'}`}
            >
              Cards Only
            </button>
          </div>

          <button
            type="button"
            className="ss-btn-ghost text-xs"
            disabled={debugQuery.isFetching}
            onClick={() => void debugQuery.refetch()}
          >
            {debugQuery.isFetching ? 'Polling…' : 'Refresh'}
          </button>
          <button
            type="button"
            className="ss-btn-danger-soft text-xs"
            disabled={clearMutation.isPending || entries.length === 0}
            onClick={() => {
              if (!window.confirm('Clear all pipeline debug entries from the database?')) return
              clearMutation.mutate()
            }}
          >
            Clear Log
          </button>
        </div>
      </div>

      {/* RAW TERMINAL / CONSOLE PANEL */}
      {(viewMode === 'both' || viewMode === 'terminal') && (
        <section className="rounded-xl border border-white/15 bg-[#0b0f19] shadow-2xl overflow-hidden flex flex-col font-mono">
          {/* Terminal Window Header Bar */}
          <div className="flex flex-wrap items-center justify-between gap-3 px-4 py-2.5 bg-black/70 border-b border-white/10 text-xs select-none">
            <div className="flex items-center gap-2">
              <span className="h-3 w-3 rounded-full bg-red-500/80 inline-block"></span>
              <span className="h-3 w-3 rounded-full bg-amber-500/80 inline-block"></span>
              <span className="h-3 w-3 rounded-full bg-emerald-500/80 inline-block"></span>
              <span className="text-gray-400 ml-2 font-semibold">tty1: scanscribe-pipeline-daemon</span>
            </div>

            <div className="flex items-center gap-3">
              <input
                type="text"
                className="bg-white/5 border border-white/10 rounded px-2 py-0.5 text-[11px] text-gray-200 placeholder-gray-500 focus:outline-none focus:border-indigo-500 w-36 sm:w-48"
                placeholder="Filter terminal output…"
                value={consoleFilter}
                onChange={(e) => setConsoleFilter(e.target.value)}
              />

              <label className="flex items-center gap-1.5 text-[11px] text-gray-400 cursor-pointer">
                <input
                  type="checkbox"
                  checked={autoScroll}
                  onChange={(e) => setAutoScroll(e.target.checked)}
                  className="rounded border-white/20 bg-black/40 text-indigo-500 focus:ring-0"
                />
                Auto-scroll
              </label>

              <button
                type="button"
                onClick={copyToClipboard}
                className="text-[11px] px-2 py-0.5 rounded bg-white/10 hover:bg-white/20 text-gray-200 transition"
              >
                Copy Raw
              </button>
            </div>
          </div>

          {/* Terminal Body Screen */}
          <div className="p-4 overflow-y-auto max-h-[480px] min-h-[260px] text-xs leading-relaxed flex flex-col gap-2.5 selection:bg-indigo-500 selection:text-white">
            {filteredChronological.length === 0 ? (
              <p className="text-gray-600 italic">No console transmissions recorded yet. Radio traffic will stream here...</p>
            ) : (
              filteredChronological.map((row, idx) => {
                const isErr = isPipelineDebugFailure(row)

                return (
                  <div key={`console-line-${idx}-${row.ts}`} className="flex flex-col gap-1 border-b border-white/[0.04] pb-2">
                    <div className="flex flex-wrap items-baseline gap-2">
                      <span className="text-gray-500 select-none">[{fmtTs(row.ts)}]</span>
                      <span
                        className={`font-bold px-1 rounded text-[10px] uppercase select-none ${
                          isErr
                            ? 'bg-red-500/20 text-red-400 border border-red-500/30'
                            : row.action?.includes('create')
                            ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30'
                            : row.action?.includes('attach')
                            ? 'bg-sky-500/20 text-sky-300 border border-sky-500/30'
                            : 'bg-white/10 text-gray-300'
                        }`}
                      >
                        {row.action || 'IDLE'}
                      </span>
                      <span className="text-indigo-300 font-semibold">Log #{row.log_entry_id ?? 'N/A'}</span>
                      <span className="text-gray-500">({row.duration_ms ?? 0}ms)</span>
                      {row.llm_model && <span className="text-gray-500 text-[10px]">[{row.llm_model}]</span>}
                    </div>

                    <div className="text-gray-200 pl-4 border-l-2 border-indigo-500/40">
                      <span className="text-gray-400 select-none">&gt;&gt; </span>
                      <span className="italic">&ldquo;{row.transcript || 'No transcript text'}&rdquo;</span>
                    </div>

                    {row.error && (
                      <div className="text-red-400 pl-4 border-l-2 border-red-500 bg-red-950/20 p-1.5 rounded-r">
                        <span className="font-bold select-none">[FATAL_ERROR] </span>
                        <span>{row.error}</span>
                      </div>
                    )}

                    {row.llm_output && (
                      <div className="text-indigo-200 pl-4 border-l-2 border-indigo-400/20 bg-black/40 p-2 rounded-r mt-0.5">
                        <span className="text-[10px] text-gray-500 select-none block mb-1 font-bold">[RAW_LLM_RESPONSE]</span>
                        <pre className="text-[11px] whitespace-pre-wrap break-all text-emerald-300 font-mono">
                          {row.llm_output}
                        </pre>
                      </div>
                    )}
                  </div>
                )
              })
            )}
            <div ref={terminalEndRef} />
          </div>
        </section>
      )}

      {/* DETAILED CARD VIEW */}
      {(viewMode === 'both' || viewMode === 'cards') && (
        <section className="flex flex-col gap-4">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold uppercase tracking-wider text-gray-400">Structured Inspection Cards</h2>
            <div className="flex items-center gap-3">
              <label className="text-xs text-gray-500" htmlFor="debug-limit">Rows:</label>
              <select
                id="debug-limit"
                className="ss-select h-7 text-xs bg-black/40 border border-white/20 rounded px-2"
                value={String(limit)}
                onChange={(e) => setLimit(Number(e.target.value))}
              >
                {[40, 80, 120, 160, 200].map((n) => (
                  <option key={n} value={n}>
                    {n}
                  </option>
                ))}
              </select>
              <span className="text-xs text-gray-500 font-mono bg-white/5 px-2 py-0.5 rounded">
                {entries.length} loaded
              </span>
              {withErrors > 0 && (
                <span className="rounded-md border border-red-500/30 bg-red-500/10 px-2 py-0.5 text-[11px] font-semibold text-red-200">
                  {withErrors} error{withErrors === 1 ? '' : 's'}
                </span>
              )}
            </div>
          </div>

          <ul className="flex flex-col gap-3">
            {entries.map((row, i) => (
              <li key={`debug-card-${i}-${row.log_entry_id ?? 0}-${row.ts ?? 0}`}>
                <DebugEntryCard entry={row} index={entries.length - i} />
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  )
}

function DebugEntryCard({ entry, index }: { entry: PipelineDebugEntry; index: number }) {
  const [open, setOpen] = useState(false)
  const err = (entry.error || '').trim()
  const isFail = isPipelineDebugFailure(entry)
  const isConfigWarn = isPipelineDebugConfigWarning(entry)

  return (
    <article className="border border-white/10 bg-white/[0.02] hover:bg-white/[0.04] transition rounded-xl p-4">
      <button
        type="button"
        className="flex w-full flex-wrap items-start justify-between gap-3 text-left"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
      >
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="font-mono text-[11px] text-gray-500">#{index}</span>
            <span className="text-gray-600">·</span>
            <span className="text-xs text-gray-400 font-mono">{fmtTs(entry.ts)}</span>
            <span className="text-gray-600">·</span>
            <span className="font-mono text-xs font-semibold px-1.5 py-0.5 rounded bg-indigo-500/20 text-indigo-300 border border-indigo-500/30">
              {entry.action || '—'}
            </span>
            {entry.event_id && (
              <span className="font-mono text-xs text-amber-300 bg-amber-500/10 px-1.5 py-0.5 rounded border border-amber-500/20">
                Evt: {entry.event_id}
              </span>
            )}
          </div>
          <p className="mt-2 text-xs font-medium text-gray-200 italic line-clamp-2">
            &ldquo;{entry.transcript || 'No transcript text'}&rdquo;
          </p>
          <p className="mt-2 text-[11px] text-gray-500 font-mono">
            Monitor {entry.monitor_id ?? '—'} · Log #{entry.log_entry_id ?? '—'} · {entry.duration_ms ?? '—'} ms
            {entry.llm_model ? ` · ${entry.llm_model}` : ''}
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          {isFail && (
            <span className="rounded bg-red-500/20 border border-red-500/40 px-2 py-0.5 text-[10px] font-bold uppercase text-red-200">
              Error
            </span>
          )}
          {isConfigWarn && (
            <span className="rounded bg-amber-500/20 border border-amber-500/40 px-2 py-0.5 text-[10px] font-bold uppercase text-amber-200">
              Setup
            </span>
          )}
          <span className="text-xs text-gray-400 bg-white/5 hover:bg-white/10 px-2 py-1 rounded">
            {open ? 'Hide JSON ▲' : 'View Raw LLM & NER ▼'}
          </span>
        </div>
      </button>

      {open && (
        <div className="mt-4 pt-4 border-t border-white/10 flex flex-col gap-3">
          {err && (
            <div>
              <p className="text-xs font-semibold uppercase text-red-400 mb-1">Error Message</p>
              <pre className="overflow-x-auto rounded-lg border border-red-500/30 bg-red-950/30 p-3 text-xs text-red-200 font-mono">
                {err}
              </pre>
            </div>
          )}

          {entry.llm_output && (
            <div>
              <div className="flex items-center justify-between mb-1">
                <p className="text-xs font-semibold uppercase text-indigo-300">Raw LLM Output (JSON / OpenRouter)</p>
                <span className="text-[10px] text-gray-500 font-mono">{entry.llm_model}</span>
              </div>
              <pre className="max-h-80 overflow-auto rounded-lg border border-indigo-500/20 bg-black/60 p-3 text-xs font-mono text-indigo-100">
                {entry.llm_output}
              </pre>
            </div>
          )}

          {entry.entities && (
            <div>
              <p className="text-xs font-semibold uppercase text-emerald-400 mb-1">Extracted Entities (NER)</p>
              <pre className="max-h-60 overflow-auto rounded-lg border border-emerald-500/20 bg-black/60 p-3 text-xs font-mono text-emerald-100">
                {entry.entities}
              </pre>
            </div>
          )}

          {entry.raw_output && (
            <div>
              <p className="text-xs font-semibold uppercase text-gray-400 mb-1">Raw Token Extractions</p>
              <pre className="max-h-48 overflow-auto rounded-lg border border-white/10 bg-black/40 p-3 text-xs font-mono text-gray-300">
                {entry.raw_output}
              </pre>
            </div>
          )}
        </div>
      )}
    </article>
  )
}
