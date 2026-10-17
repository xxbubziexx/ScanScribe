import { useState, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import type { TalkgroupEntry } from '@/types/insights'
import { WidgetInfoTooltip } from './WidgetInfoTooltip'

interface TalkgroupShareWidgetProps {
  data?: TalkgroupEntry[]
  dateFrom?: string
  dateTo?: string
}

function RadioTowerIcon({ className = '' }: { className?: string }) {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" className={`h-4 w-4 shrink-0 ${className}`} fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
      <path d="M8 1v14M5 5l6 6M11 5L5 11" strokeLinecap="round" />
      <circle cx="8" cy="2" r="1.5" fill="currentColor" />
      <path d="M3 15h10" strokeLinecap="round" />
    </svg>
  )
}

function JumpSearchIcon({ className = '' }: { className?: string }) {
  return (
    <svg width="12" height="12" viewBox="0 0 16 16" className={`h-3 w-3 shrink-0 ${className}`} fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
      <path d="M6 3h7v7M13 3L6 10" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

function formatDuration(seconds: number): string {
  if (seconds < 60) return `${Math.round(seconds)}s`
  const mins = Math.floor(seconds / 60)
  const remSec = Math.round(seconds % 60)
  if (mins < 60) return `${mins}m ${remSec > 0 ? `${remSec}s` : ''}`
  const hours = (seconds / 3600).toFixed(1)
  return `${hours}h`
}

export function TalkgroupShareWidget({ data, dateFrom, dateTo }: TalkgroupShareWidgetProps) {
  const navigate = useNavigate()
  const [metricMode, setMetricMode] = useState<'airtime' | 'volume'>('airtime')

  // Unconditional hook resolution
  const items = useMemo(() => data ?? [], [data])

  const { totalCalls, totalAirtimeSec, topTg, maxMetricVal } = useMemo(() => {
    let calls = 0
    let airtime = 0
    let top: TalkgroupEntry | null = null

    for (const tg of items) {
      calls += tg.count
      airtime += tg.duration || 0
      if (!top || tg.count > top.count) {
        top = tg
      }
    }

    const maxVal = items.length > 0
      ? Math.max(...items.map((i) => (metricMode === 'airtime' ? (i.percentage ?? 0) : i.count)))
      : 1

    return {
      totalCalls: calls,
      totalAirtimeSec: airtime,
      topTg: top,
      maxMetricVal: Math.max(maxVal, 1),
    }
  }, [items, metricMode])

  const handleDrilldown = (talkgroup: string) => {
    const params = new URLSearchParams()
    if (dateFrom) params.set('date_from', dateFrom)
    if (dateTo) params.set('date_to', dateTo)
    params.set('talkgroups', talkgroup)
    navigate(`/search?${params.toString()}`)
  }

  if (!data || items.length === 0) {
    return (
      <div className="ss-glass-panel relative flex min-h-[300px] flex-col items-center justify-center p-8 text-center text-sm text-gray-500">
        <RadioTowerIcon className="mb-2 h-6 w-6 text-gray-600" />
        <p>No talkgroup transmissions recorded in selected window.</p>
      </div>
    )
  }

  return (
    <div className="ss-glass-panel relative flex flex-col justify-between overflow-hidden p-5">
      {/* Top Header */}
      <div>
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-gray-800/80 pb-3">
          <div className="flex items-center gap-2.5">
            <div className="flex h-7 w-7 items-center justify-center rounded-lg border border-sky-500/30 bg-sky-500/10 text-sky-400">
              <RadioTowerIcon className="h-4 w-4" />
            </div>
            <div>
              <div className="flex items-center gap-1.5">
                <h3 className="text-sm font-semibold text-gray-100">Talkgroup Share of Voice</h3>
                <WidgetInfoTooltip
                  title="Talkgroup Share of Voice"
                  description="Measures radio airtime utilization and transmission volume distribution across active public safety talkgroup channels."
                  bullets={[
                    'Airtime Share: Percentage of total radio voice broadcast time consumed.',
                    'Average Call Length: Typical transmission duration in seconds.',
                    'Channel Drilldown: Click any talkgroup row to filter the archive.',
                  ]}
                />
              </div>
              <p className="text-xs text-gray-400">Airtime allocation and transmission density across channels</p>
            </div>
          </div>

          {/* Metric Toggle */}
          <div className="flex items-center rounded-lg border border-gray-800 bg-gray-900/60 p-0.5 text-xs">
            <button
              onClick={() => setMetricMode('airtime')}
              className={`rounded-md px-2.5 py-1 font-medium transition-all ${
                metricMode === 'airtime'
                  ? 'border border-sky-500/30 bg-sky-500/15 text-sky-300 shadow-sm'
                  : 'text-gray-400 hover:text-gray-200'
              }`}
            >
              Airtime Share (%)
            </button>
            <button
              onClick={() => setMetricMode('volume')}
              className={`rounded-md px-2.5 py-1 font-medium transition-all ${
                metricMode === 'volume'
                  ? 'border border-sky-500/30 bg-sky-500/15 text-sky-300 shadow-sm'
                  : 'text-gray-400 hover:text-gray-200'
              }`}
            >
              Call Volume
            </button>
          </div>
        </div>

        {/* Telemetry Summary Cards */}
        <div className="mt-3 grid grid-cols-2 gap-2.5 sm:grid-cols-3">
          <div className="rounded-lg border border-gray-800/80 bg-gray-950/40 p-2.5">
            <span className="block text-[10px] font-medium uppercase tracking-wider text-gray-400">Active Channels</span>
            <span className="font-mono text-base font-semibold text-gray-100">{items.length}</span>
            <span className="ml-1 text-[11px] text-gray-500">talkgroups</span>
          </div>

          <div className="rounded-lg border border-gray-800/80 bg-gray-950/40 p-2.5">
            <span className="block text-[10px] font-medium uppercase tracking-wider text-gray-400">Total Voice Airtime</span>
            <span className="font-mono text-base font-semibold text-sky-300">
              {formatDuration(totalAirtimeSec)}
            </span>
            <span className="ml-1 text-[11px] text-gray-500">({totalCalls.toLocaleString()} calls)</span>
          </div>

          <div className="col-span-2 rounded-lg border border-gray-800/80 bg-gray-950/40 p-2.5 sm:col-span-1">
            <span className="block text-[10px] font-medium uppercase tracking-wider text-gray-400">Dominant Channel</span>
            <span className="block truncate font-mono text-sm font-semibold text-gray-200" title={topTg?.talkgroup}>
              {topTg?.talkgroup || 'N/A'}
            </span>
            <span className="text-[11px] text-gray-500">
              {topTg?.percentage ? `${topTg.percentage}% share` : `${topTg?.count ?? 0} transmissions`}
            </span>
          </div>
        </div>

        {/* Channel Breakdown List */}
        <div className="mt-4 space-y-2.5">
          {items.slice(0, 8).map((tg, idx) => {
            const pct = tg.percentage ?? (totalAirtimeSec > 0 ? ((tg.duration || 0) / totalAirtimeSec) * 100 : 0)
            const barWidth = metricMode === 'airtime'
              ? Math.min(100, Math.max(4, (pct / maxMetricVal) * 100))
              : Math.min(100, Math.max(4, (tg.count / maxMetricVal) * 100))

            return (
              <div
                key={tg.talkgroup || idx}
                onClick={() => handleDrilldown(tg.talkgroup)}
                className="group relative cursor-pointer rounded-lg border border-gray-800/60 bg-gray-900/30 p-2.5 transition-all hover:border-sky-500/40 hover:bg-gray-800/40"
              >
                <div className="mb-1.5 flex items-center justify-between gap-2 text-xs">
                  <div className="flex items-center gap-2 overflow-hidden">
                    <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded font-mono text-[10px] font-bold text-gray-400 bg-gray-800/80 group-hover:text-sky-300">
                      {idx + 1}
                    </span>
                    <span className="truncate font-medium text-gray-200 group-hover:text-white" title={tg.talkgroup}>
                      {tg.talkgroup}
                    </span>
                  </div>

                  <div className="flex shrink-0 items-center gap-3">
                    <span className="font-mono text-gray-300">
                      {metricMode === 'airtime' ? `${pct.toFixed(1)}%` : `${tg.count} calls`}
                    </span>
                    <span className="hidden font-mono text-[11px] text-gray-500 sm:inline">
                      {tg.duration ? formatDuration(tg.duration) : ''}
                      {tg.avg_duration ? ` (~${tg.avg_duration}s/call)` : ''}
                    </span>
                    <JumpSearchIcon className="h-3 w-3 text-gray-500 opacity-0 transition-opacity group-hover:opacity-100 group-hover:text-sky-400" />
                  </div>
                </div>

                {/* Progress Bar */}
                <div className="h-1.5 w-full overflow-hidden rounded-full bg-gray-800/80">
                  <div
                    className="h-full rounded-full bg-gradient-to-r from-sky-500 to-indigo-500 transition-all duration-300 group-hover:brightness-125"
                    style={{ width: `${barWidth}%` }}
                  />
                </div>
              </div>
            )
          })}
        </div>
      </div>

      {/* Footer Info */}
      <div className="mt-4 flex items-center justify-between border-t border-gray-800/60 pt-3 text-[11px] text-gray-400">
        <span>Click any talkgroup to filter transmission archive</span>
        <span className="font-mono text-gray-400">Showing top 8 channels</span>
      </div>
    </div>
  )
}
