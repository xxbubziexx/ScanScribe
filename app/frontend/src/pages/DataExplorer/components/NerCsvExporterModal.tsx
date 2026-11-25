import { useEffect, useMemo, useState } from 'react'
import { downloadEntitiesCsv } from '@/lib/events'
import { useToast } from '@/context/ToastContext'
import { errorMessage } from '@/types/api'

export interface NerExporterActiveFilters {
  monitorId?: number
  talkgroup?: string
  logEntryId?: number
  spanStoreId?: number
  q?: string
  dateFrom?: string
  dateTo?: string
  initialLabel?: string
}

export function NerCsvExporterModal({
  open,
  onClose,
  availableLabels,
  activeFilters,
  selectedIds,
  defaultScope = 'filters',
}: {
  open: boolean
  onClose: () => void
  availableLabels: string[]
  activeFilters: NerExporterActiveFilters
  selectedIds: Set<number>
  defaultScope?: 'filters' | 'selected'
}) {
  const { addToast } = useToast()
  const [selectedLabels, setSelectedLabels] = useState<string[]>([])
  const [scope, setScope] = useState<'filters' | 'selected'>('filters')
  const [deduplicate, setDeduplicate] = useState(true)
  const [includeCounts, setIncludeCounts] = useState(true)
  const [includeContext, setIncludeContext] = useState(false)
  const [isExporting, setIsExporting] = useState(false)

  useEffect(() => {
    if (!open) return
    if (activeFilters.initialLabel && availableLabels.includes(activeFilters.initialLabel)) {
      setSelectedLabels([activeFilters.initialLabel])
    } else {
      setSelectedLabels(availableLabels)
    }
    setScope(defaultScope === 'selected' && selectedIds.size > 0 ? 'selected' : 'filters')
  }, [open, activeFilters.initialLabel, availableLabels, defaultScope, selectedIds.size])

  const previewColumns = useMemo(() => {
    const singleLabel = selectedLabels.length === 1
    if (includeContext && !deduplicate) {
      return [
        'id',
        'timestamp',
        'label',
        'raw',
        'canonical',
        'talkgroup',
        'monitor_id',
        'span_store_id',
        'log_entry_id',
        'transcript',
      ]
    }
    if (includeContext && deduplicate) {
      return ['label', 'raw', 'count', 'talkgroups', 'first_seen', 'last_seen']
    }
    if (!includeContext && deduplicate) {
      if (singleLabel) return includeCounts ? ['raw', 'count'] : ['raw']
      return includeCounts ? ['label', 'raw', 'count'] : ['label', 'raw']
    }
    return singleLabel ? ['raw'] : ['label', 'raw']
  }, [deduplicate, includeContext, includeCounts, selectedLabels.length])

  if (!open) return null

  const toggleLabel = (lbl: string) => {
    setSelectedLabels((prev) =>
      prev.includes(lbl) ? prev.filter((item) => item !== lbl) : [...prev, lbl],
    )
  }

  const activeFilterSummary: string[] = []
  if (activeFilters.monitorId) activeFilterSummary.push(`Monitor #${activeFilters.monitorId}`)
  if (activeFilters.talkgroup) activeFilterSummary.push(`Talkgroup ~ "${activeFilters.talkgroup}"`)
  if (activeFilters.dateFrom || activeFilters.dateTo) {
    activeFilterSummary.push(`Dates: ${activeFilters.dateFrom || '…'} to ${activeFilters.dateTo || '…'}`)
  }
  if (activeFilters.q) activeFilterSummary.push(`Search: "${activeFilters.q}"`)
  if (activeFilters.spanStoreId) activeFilterSummary.push(`Span #${activeFilters.spanStoreId}`)
  if (activeFilters.logEntryId) activeFilterSummary.push(`Log #${activeFilters.logEntryId}`)

  const handleExport = async () => {
    if (selectedLabels.length === 0) {
      addToast('Select at least one NER entity label to export', 'error')
      return
    }
    if (scope === 'selected' && selectedIds.size === 0) {
      addToast('No observations selected', 'error')
      return
    }
    setIsExporting(true)
    try {
      const useSelected = scope === 'selected' && selectedIds.size > 0
      const { rowCount } = await downloadEntitiesCsv({
        labels: selectedLabels,
        ids: useSelected ? Array.from(selectedIds) : undefined,
        deduplicate,
        include_counts: includeCounts,
        include_context: includeContext,
        monitor_id: useSelected ? undefined : activeFilters.monitorId,
        talkgroup: useSelected ? undefined : activeFilters.talkgroup || undefined,
        log_entry_id: useSelected ? undefined : activeFilters.logEntryId,
        span_store_id: useSelected ? undefined : activeFilters.spanStoreId,
        q: useSelected ? undefined : activeFilters.q || undefined,
        date_from: useSelected ? undefined : activeFilters.dateFrom || undefined,
        date_to: useSelected ? undefined : activeFilters.dateTo || undefined,
      })
      addToast(`Exported ${rowCount.toLocaleString()} NER CSV rows`, 'success')
      onClose()
    } catch (err) {
      addToast(errorMessage(err, 'NER CSV export failed'), 'error')
    } finally {
      setIsExporting(false)
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4 backdrop-blur-sm"
      role="dialog"
      aria-modal="true"
      aria-labelledby="ner-exporter-title"
      onClick={onClose}
    >
      <div
        className="w-full max-w-xl rounded border border-white/15 bg-[#12161f] p-5 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-3 border-b border-white/10 pb-3">
          <div>
            <h2 id="ner-exporter-title" className="text-base font-semibold text-gray-100">
              NER Raw-Values CSV Exporter
            </h2>
            <p className="mt-0.5 text-xs text-gray-400">
              Choose which entity labels to extract and whether to export raw values or full context.
            </p>
          </div>
          <button
            type="button"
            className="ss-btn-ghost h-7 px-2 text-xs cursor-pointer"
            onClick={onClose}
            aria-label="Close exporter"
          >
            Close
          </button>
        </div>

        <div className="mt-4 space-y-4">
          {/* Scope */}
          <div>
            <span className="mb-1.5 block text-[11px] font-semibold uppercase tracking-wider text-gray-400">
              Export Scope
            </span>
            <div className="grid grid-cols-2 gap-2">
              <button
                type="button"
                className={`rounded-sm border px-3 py-2 text-left text-xs transition cursor-pointer ${
                  scope === 'filters'
                    ? 'border-indigo-500/60 bg-indigo-500/15 text-indigo-100'
                    : 'border-white/10 bg-white/[0.02] text-gray-400 hover:text-gray-200'
                }`}
                onClick={() => setScope('filters')}
              >
                <div className="font-semibold">Matching active filters</div>
                <div className="mt-0.5 text-[11px] text-gray-400">
                  {activeFilterSummary.length > 0
                    ? activeFilterSummary.join(' · ')
                    : 'All entity observations'}
                </div>
              </button>

              <button
                type="button"
                disabled={selectedIds.size === 0}
                className={`rounded-sm border px-3 py-2 text-left text-xs transition ${
                  selectedIds.size === 0
                    ? 'cursor-not-allowed border-white/5 bg-white/[0.01] text-gray-600'
                    : scope === 'selected'
                      ? 'cursor-pointer border-emerald-500/60 bg-emerald-500/15 text-emerald-100'
                      : 'cursor-pointer border-white/10 bg-white/[0.02] text-gray-400 hover:text-gray-200'
                }`}
                onClick={() => setScope('selected')}
              >
                <div className="font-semibold">Selected rows only ({selectedIds.size})</div>
                <div className="mt-0.5 text-[11px] text-gray-400">
                  {selectedIds.size > 0
                    ? 'Restricts export to checked table rows'
                    : 'Check rows in the table to enable'}
                </div>
              </button>
            </div>
          </div>

          {/* Label Multi-Select */}
          <div>
            <div className="mb-1.5 flex items-center justify-between">
              <span className="text-[11px] font-semibold uppercase tracking-wider text-gray-400">
                Entity Labels ({selectedLabels.length}/{availableLabels.length})
              </span>
              <div className="flex gap-2 text-xs">
                <button
                  type="button"
                  className="text-indigo-400 hover:text-indigo-300 cursor-pointer"
                  onClick={() => setSelectedLabels(availableLabels)}
                >
                  Select All
                </button>
                <span className="text-gray-600">·</span>
                <button
                  type="button"
                  className="text-gray-400 hover:text-gray-200 cursor-pointer"
                  onClick={() => setSelectedLabels([])}
                >
                  Clear
                </button>
              </div>
            </div>

            <div className="flex flex-wrap gap-2">
              {availableLabels.map((lbl) => {
                const active = selectedLabels.includes(lbl)
                return (
                  <button
                    key={lbl}
                    type="button"
                    onClick={() => toggleLabel(lbl)}
                    className={`rounded-sm border px-3 py-1.5 font-mono text-xs font-semibold transition cursor-pointer ${
                      active
                        ? 'border-emerald-500/50 bg-emerald-500/20 text-emerald-200'
                        : 'border-white/10 bg-white/[0.02] text-gray-400 hover:border-white/25 hover:text-gray-200'
                    }`}
                  >
                    {active ? '✓ ' : ''}
                    {lbl}
                  </button>
                )
              })}
            </div>
          </div>

          {/* Format Options */}
          <div className="space-y-2 rounded-sm border border-white/10 bg-black/25 p-3">
            <span className="block text-[11px] font-semibold uppercase tracking-wider text-gray-400">
              CSV Format Options
            </span>

            <label className="flex items-start gap-2.5 text-xs text-gray-200 cursor-pointer">
              <input
                type="checkbox"
                className="mt-0.5 accent-indigo-500"
                checked={deduplicate}
                onChange={(e) => setDeduplicate(e.target.checked)}
              />
              <span>
                <span className="font-medium">Deduplicate raw values</span>
                <span className="block text-[11px] text-gray-400">
                  Group identical extracted strings and sort by highest occurrence count.
                </span>
              </span>
            </label>

            {deduplicate && !includeContext && (
              <label className="ml-5 flex items-start gap-2.5 text-xs text-gray-200 cursor-pointer">
                <input
                  type="checkbox"
                  className="mt-0.5 accent-indigo-500"
                  checked={includeCounts}
                  onChange={(e) => setIncludeCounts(e.target.checked)}
                />
                <span>
                  <span className="font-medium">Include occurrence count column</span>
                  <span className="block text-[11px] text-gray-400">
                    Uncheck to export a pure single-column list of unique values.
                  </span>
                </span>
              </label>
            )}

            <label className="flex items-start gap-2.5 text-xs text-gray-200 cursor-pointer">
              <input
                type="checkbox"
                className="mt-0.5 accent-indigo-500"
                checked={includeContext}
                onChange={(e) => setIncludeContext(e.target.checked)}
              />
              <span>
                <span className="font-medium">Include context columns</span>
                <span className="block text-[11px] text-gray-400">
                  {deduplicate
                    ? 'Adds talkgroups, first_seen, and last_seen timestamps.'
                    : 'Adds timestamp, talkgroup, IDs, canonical value, and full transcript.'}
                </span>
              </span>
            </label>
          </div>

          {/* Live Column Preview */}
          <div className="rounded-sm border border-white/10 bg-black/40 p-2.5">
            <div className="text-[10px] font-semibold uppercase tracking-wider text-gray-500">
              CSV Header Preview
            </div>
            <div className="mt-1 font-mono text-xs text-sky-300">
              {previewColumns.join(', ')}
            </div>
          </div>
        </div>

        <div className="mt-5 flex items-center justify-end gap-2 border-t border-white/10 pt-3">
          <button
            type="button"
            className="ss-btn-ghost h-9 px-4 text-xs cursor-pointer"
            onClick={onClose}
            disabled={isExporting}
          >
            Cancel
          </button>
          <button
            type="button"
            className="ss-btn-primary h-9 px-4 text-xs cursor-pointer disabled:opacity-50"
            onClick={() => void handleExport()}
            disabled={isExporting || selectedLabels.length === 0}
          >
            {isExporting ? 'Generating CSV…' : 'Download CSV'}
          </button>
        </div>
      </div>
    </div>
  )
}
