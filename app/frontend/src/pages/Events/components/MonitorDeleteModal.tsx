import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { eventsApi } from '@/lib/events'
import { errorMessage } from '@/types/api'
import type { MonitorResponse } from '@/types/events'

export function MonitorDeleteModal({
  monitor,
  onClose,
  onConfirmDelete,
  onDisableInstead,
  isDeleting,
  isDisabling,
}: {
  monitor: MonitorResponse | null
  onClose: () => void
  onConfirmDelete: (id: number) => void
  onDisableInstead: (monitor: MonitorResponse) => void
  isDeleting: boolean
  isDisabling: boolean
}) {
  const [confirmInput, setConfirmInput] = useState('')

  useEffect(() => {
    setConfirmInput('')
  }, [monitor?.id])

  const impactQuery = useQuery({
    queryKey: ['monitor-delete-impact', monitor?.id],
    queryFn: () => eventsApi.monitorDeleteImpact(monitor!.id),
    enabled: Boolean(monitor),
    staleTime: 0,
  })

  if (!monitor) return null

  const nameMatches = confirmInput.trim() === monitor.name.trim()
  const impact = impactQuery.data
  const busy = isDeleting || isDisabling

  const impactRows = impact
    ? [
        { label: 'Events', table: 'events', count: impact.events_count },
        { label: 'Event Transcript Links', table: 'event_transcript_links', count: impact.event_links_count },
        { label: 'Span Store', table: 'span_store', count: impact.span_store_count },
        { label: 'NER Entity Observations', table: 'entity_observations', count: impact.entity_observations_count },
      ]
    : []

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 p-4 backdrop-blur-sm"
      role="dialog"
      aria-modal="true"
      aria-labelledby="monitor-delete-title"
      onClick={() => {
        if (!busy) onClose()
      }}
    >
      <div
        className="w-full max-w-lg rounded border border-rose-500/40 bg-[#12151e] p-5 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-3 border-b border-rose-500/20 pb-3">
          <div>
            <div className="text-[10px] font-bold uppercase tracking-[0.08em] text-rose-400">
              Permanent Database Deletion
            </div>
            <h2 id="monitor-delete-title" className="mt-0.5 text-base font-semibold text-slate-100">
              Delete monitor “{monitor.name}”?
            </h2>
          </div>
          <button
            type="button"
            className="ss-btn-ghost h-7 px-2 text-xs cursor-pointer"
            onClick={onClose}
            disabled={busy}
          >
            Close
          </button>
        </div>

        <div className="mt-4 space-y-3.5 text-xs">
          <div className="rounded-sm border border-rose-500/30 bg-rose-950/25 p-3 text-rose-100 leading-relaxed">
            Deleting a monitor triggers <span className="font-mono font-semibold">ON DELETE CASCADE</span>{' '}
            and permanently erases all pipeline database records belonging to this monitor. This action cannot be undone.
          </div>

          <div className="rounded-sm border border-white/10 bg-[#0b0e15] p-3">
            <div className="mb-2 flex items-center justify-between text-[10px] font-semibold uppercase tracking-wider text-slate-400">
              <span>Records That Will Be Permanently Deleted</span>
              {impact && (
                <span className="font-mono text-rose-300">
                  {impact.total_dependent_rows.toLocaleString()} total rows
                </span>
              )}
            </div>

            {impactQuery.isLoading ? (
              <p className="py-2 font-mono text-xs text-slate-400">Calculating database impact…</p>
            ) : impactQuery.isError ? (
              <p className="text-xs text-amber-300">
                {errorMessage(impactQuery.error, 'Could not query row counts — cascade deletion still applies.')}
              </p>
            ) : (
              <dl className="grid grid-cols-2 gap-2">
                {impactRows.map((item) => (
                  <div
                    key={item.table}
                    className="flex items-center justify-between rounded-sm border border-white/[0.06] bg-white/[0.02] px-2.5 py-1.5"
                  >
                    <div>
                      <dt className="font-medium text-slate-200">{item.label}</dt>
                      <dd className="font-mono text-[10px] text-slate-500">{item.table}</dd>
                    </div>
                    <span
                      className={`font-mono text-sm font-bold tabular-nums ${
                        item.count > 0 ? 'text-rose-300' : 'text-slate-500'
                      }`}
                    >
                      {item.count.toLocaleString()}
                    </span>
                  </div>
                ))}
              </dl>
            )}

            <p className="mt-2.5 border-t border-white/5 pt-2 text-[11px] text-slate-400">
              Transmissions (<span className="font-mono text-slate-300">log_entries</span>) and stored audio files are{' '}
              <strong className="text-slate-200">not</strong> deleted.
            </p>
          </div>

          {monitor.enabled && (
            <div className="flex items-center justify-between gap-3 rounded-sm border border-amber-500/25 bg-amber-500/10 px-3 py-2">
              <span className="text-[11px] text-amber-100">
                Want to stop ingesting this monitor without losing historical spans, entities, or events?
              </span>
              <button
                type="button"
                className="ss-btn-ghost shrink-0 h-7 px-2.5 text-[11px] border-amber-400/40 text-amber-200 hover:bg-amber-500/20 cursor-pointer disabled:opacity-50"
                disabled={busy}
                onClick={() => onDisableInstead(monitor)}
              >
                {isDisabling ? 'Disabling…' : 'Disable Monitor Instead'}
              </button>
            </div>
          )}

          <div>
            <label
              htmlFor="monitor-delete-confirm-input"
              className="mb-1.5 block text-[11px] font-medium text-slate-300"
            >
              Type <span className="rounded-sm bg-white/10 px-1.5 py-0.5 font-mono font-semibold text-white">{monitor.name}</span> to confirm permanent deletion:
            </label>
            <input
              id="monitor-delete-confirm-input"
              type="text"
              className="ss-input w-full rounded-sm font-mono text-xs"
              value={confirmInput}
              onChange={(e) => setConfirmInput(e.target.value)}
              placeholder={monitor.name}
              autoComplete="off"
              disabled={busy}
            />
          </div>
        </div>

        <div className="mt-5 flex items-center justify-end gap-2 border-t border-white/10 pt-3">
          <button
            type="button"
            className="ss-btn-ghost h-8 px-3.5 text-xs cursor-pointer"
            onClick={onClose}
            disabled={busy}
          >
            Cancel
          </button>
          <button
            type="button"
            className="h-8 rounded-sm border border-rose-500 bg-rose-600 px-3.5 text-xs font-semibold text-white transition hover:bg-rose-500 cursor-pointer disabled:cursor-not-allowed disabled:opacity-40"
            disabled={!nameMatches || busy}
            onClick={() => onConfirmDelete(monitor.id)}
          >
            {isDeleting ? 'Deleting…' : 'Delete Monitor & Data'}
          </button>
        </div>
      </div>
    </div>
  )
}
