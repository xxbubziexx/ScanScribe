import { useEffect, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'

export function formatRelativeElapsed(ms: number): string {
  if (ms < 10_000) return 'just now'
  if (ms < 60_000) return `${Math.floor(ms / 1000)}s ago`
  if (ms < 3_600_000) return `${Math.floor(ms / 60_000)}m ago`
  return `${Math.floor(ms / 3_600_000)}h ago`
}

export interface WorkbenchRefreshControlProps {
  total: number | undefined
  dataUpdatedAt: number
  isFetching: boolean
  onRefresh: () => Promise<number | undefined>
  filterKey?: string
}

export function WorkbenchRefreshControl({
  total,
  dataUpdatedAt,
  isFetching,
  onRefresh,
  filterKey,
}: WorkbenchRefreshControlProps) {
  const queryClient = useQueryClient()
  const [lastRefreshedAt, setLastRefreshedAt] = useState<number | null>(() =>
    dataUpdatedAt > 0 ? dataUpdatedAt : null,
  )
  const [lastDelta, setLastDelta] = useState<number | null>(null)
  const [now, setNow] = useState<number>(() => Date.now())

  useEffect(() => {
    if (dataUpdatedAt > 0) {
      setLastRefreshedAt((prev) => (prev === null || dataUpdatedAt > prev ? dataUpdatedAt : prev))
      setNow(Date.now())
    }
  }, [dataUpdatedAt])

  useEffect(() => {
    setLastDelta(null)
  }, [filterKey])

  useEffect(() => {
    if (lastRefreshedAt === null) return
    const timer = window.setInterval(() => {
      setNow(Date.now())
    }, 10_000)
    return () => window.clearInterval(timer)
  }, [lastRefreshedAt])

  const handleRefresh = async () => {
    const prevTotal = total
    const nextTotal = await onRefresh()
    void queryClient.invalidateQueries({ queryKey: ['database-overview'] })
    const completedAt = Date.now()
    setLastRefreshedAt(completedAt)
    setNow(completedAt)
    if (typeof prevTotal === 'number' && typeof nextTotal === 'number') {
      setLastDelta(nextTotal - prevTotal)
    }
  }

  const deltaLabel =
    lastDelta === null
      ? null
      : lastDelta >= 0
        ? `+${lastDelta.toLocaleString()}`
        : lastDelta.toLocaleString()

  const deltaTone =
    lastDelta === null
      ? ''
      : lastDelta > 0
        ? 'border-emerald-500/35 bg-emerald-500/15 text-emerald-300 font-semibold'
        : lastDelta === 0
          ? 'border-white/10 bg-white/[0.04] text-slate-400'
          : 'border-rose-500/30 bg-rose-500/10 text-rose-300 font-semibold'

  const deltaTitle =
    lastDelta === null
      ? undefined
      : lastDelta > 0
        ? `${lastDelta.toLocaleString()} new entries since previous refresh`
        : lastDelta === 0
          ? 'No new entries since previous refresh'
          : `${Math.abs(lastDelta).toLocaleString()} fewer entries since previous refresh`

  return (
    <div className="flex items-center gap-2">
      {lastRefreshedAt !== null && (
        <span
          className="hidden sm:inline font-mono text-[11px] text-slate-500"
          title={new Date(lastRefreshedAt).toLocaleTimeString()}
        >
          Last refreshed:{' '}
          <span className="text-slate-300">
            {formatRelativeElapsed(Math.max(0, now - lastRefreshedAt))}
          </span>
        </span>
      )}
      {deltaLabel !== null && (
        <span
          className={`rounded-sm border px-1.5 py-0.5 font-mono text-[11px] leading-none ${deltaTone}`}
          title={deltaTitle}
        >
          {deltaLabel}
        </span>
      )}
      <button
        type="button"
        className="ss-btn-ghost h-8 px-3 text-xs cursor-pointer"
        onClick={() => void handleRefresh()}
        disabled={isFetching}
      >
        {isFetching ? 'Refreshing…' : 'Refresh'}
      </button>
    </div>
  )
}
