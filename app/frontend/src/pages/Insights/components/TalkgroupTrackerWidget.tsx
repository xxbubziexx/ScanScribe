import { useState, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import type { TalkgroupEntry, TalkgroupTrackerTelemetry } from '@/types/insights'
import { WidgetInfoTooltip } from './WidgetInfoTooltip'

interface TalkgroupTrackerWidgetProps {
  data?: TalkgroupTrackerTelemetry
  fallbackTalkgroups?: TalkgroupEntry[]
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

function FireIcon({ className = '' }: { className?: string }) {
  return (
    <svg width="14" height="14" viewBox="0 0 16 16" className={`h-3.5 w-3.5 shrink-0 ${className}`} fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
      <path d="M8 1c.5 2 2 3.5 2 5.5a4 4 0 11-8 0C2 4.5 5 2.5 5.5 1c1.5 1.5 2 3 2.5 4 .5-1 1-2.5 0-4z" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

function SparklesIcon({ className = '' }: { className?: string }) {
  return (
    <svg width="14" height="14" viewBox="0 0 16 16" className={`h-3.5 w-3.5 shrink-0 ${className}`} fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
      <path d="M8 1.5l1.5 4.5 4.5 1.5-4.5 1.5L8 13.5l-1.5-4.5-4.5-1.5 4.5-1.5L8 1.5z" strokeLinecap="round" strokeLinejoin="round" />
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

export function TalkgroupTrackerWidget({
  data,
  fallbackTalkgroups,
  dateFrom,
  dateTo,
}: TalkgroupTrackerWidgetProps) {
  const navigate = useNavigate()
  const [metricMode, setMetricMode] = useState<'airtime' | 'volume'>('airtime')
  const [filterTab, setFilterTab] = useState<'all' | 'new' | 'yesterday'>('all')
  const [searchQuery, setSearchQuery] = useState('')

  // Resolve items either from telemetry or fallback
  const rankedItems = useMemo(() => {
    if (data?.ranked_talkgroups && data.ranked_talkgroups.length > 0) {
      return data.ranked_talkgroups
    }
    return fallbackTalkgroups ?? []
  }, [data, fallbackTalkgroups])

  // Aggregate telemetry
  const { totalCalls, totalAirtimeSec, busiestTg, maxMetricVal, newTgsCount, newVsYesterdayCount } = useMemo(() => {
    let calls = data?.total_calls ?? 0
    let airtime = data?.total_airtime ?? 0
    let top = data?.busiest_talkgroup ?? null

    if (!data || calls === 0) {
      calls = 0
      airtime = 0
      for (const tg of rankedItems) {
        calls += tg.count
        airtime += tg.duration || 0
        if (!top || tg.count > top.count) {
          top = tg
        }
      }
    }

    const newCount = data?.new_talkgroups_count ?? rankedItems.filter((i) => i.is_new).length
    const yesterdayCount = data?.new_vs_yesterday?.length ?? rankedItems.filter((i) => i.is_new_vs_yesterday).length

    const maxVal = rankedItems.length > 0
      ? Math.max(...rankedItems.map((i) => (metricMode === 'airtime' ? (i.percentage ?? 0) : i.count)))
      : 1

    return {
      totalCalls: calls,
      totalAirtimeSec: airtime,
      busiestTg: top,
      maxMetricVal: Math.max(maxVal, 1),
      newTgsCount: newCount,
      newVsYesterdayCount: yesterdayCount,
    }
  }, [data, rankedItems, metricMode])

  // Filtered items based on tab & search
  const visibleItems = useMemo(() => {
    let filtered = rankedItems

    if (filterTab === 'new') {
      filtered = filtered.filter((i) => i.is_new)
    } else if (filterTab === 'yesterday') {
      filtered = filtered.filter((i) => i.is_new_vs_yesterday)
    }

    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase().trim()
      filtered = filtered.filter((i) => i.talkgroup.toLowerCase().includes(q))
    }

    return filtered
  }, [rankedItems, filterTab, searchQuery])

  const handleDrilldown = (talkgroup: string) => {
    const params = new URLSearchParams()
    if (dateFrom) params.set('date_from', dateFrom)
    if (dateTo) params.set('date_to', dateTo)
    params.set('talkgroup', talkgroup)
    navigate(`/search?${params.toString()}`)
  }

  if (rankedItems.length === 0) {
    return (
      <div className="ss-glass-panel relative flex min-h-[320px] flex-col items-center justify-center p-8 text-center text-sm text-gray-500">
        <RadioTowerIcon className="mb-2 h-7 w-7 text-gray-600" />
        <p className="font-medium text-gray-300">No talkgroup transmissions recorded</p>
        <p className="mt-1 text-xs text-gray-500">No radio channels observed for the selected date window.</p>
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
                <h3 className="text-sm font-semibold text-gray-100">Talkgroup Intelligence & Tracker</h3>
                <WidgetInfoTooltip
                  title="Talkgroup Intelligence & Tracker"
                  description="Complete channel tracking and volume ranking across public safety talkgroups in the scoped date window. Retired and superseded Talkgroup Share of Voice."
                  bullets={[
                    'Ranking System: Complete ordered list of every active talkgroup observed.',
                    'Busiest Talkgroup: Surfaces the dominant channel by call density and airtime.',
                    'New Seen Channels: Tracks newly discovered channels and talkgroups active today that were quiet yesterday.',
                    'Archive Drilldown: Click any channel to jump into Search with that talkgroup filtered.',
                  ]}
                />
              </div>
              <p className="text-xs text-gray-400">Transmission volume ranking, airtime allocation, and newly discovered channels</p>
            </div>
          </div>

          {/* Metric Toggle */}
          <div className="flex items-center rounded-lg border border-gray-800 bg-gray-900/60 p-0.5 text-xs">
            <button
              type="button"
              onClick={() => setMetricMode('airtime')}
              className={`rounded-md px-2.5 py-1 font-medium transition-all cursor-pointer ${
                metricMode === 'airtime'
                  ? 'border border-sky-500/30 bg-sky-500/15 text-sky-300 shadow-sm'
                  : 'text-gray-400 hover:text-gray-200'
              }`}
            >
              Airtime Share (%)
            </button>
            <button
              type="button"
              onClick={() => setMetricMode('volume')}
              className={`rounded-md px-2.5 py-1 font-medium transition-all cursor-pointer ${
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
        <div className="mt-3.5 grid grid-cols-2 gap-2.5 sm:grid-cols-4">
          {/* Active Channels */}
          <div className="rounded-lg border border-gray-800/80 bg-gray-950/40 p-2.5">
            <span className="block text-[10px] font-medium uppercase tracking-wider text-gray-400">Active Channels</span>
            <div className="flex items-baseline gap-1 mt-0.5">
              <span className="font-mono text-base font-semibold text-gray-100">{rankedItems.length}</span>
              <span className="text-[11px] text-gray-500">talkgroups</span>
            </div>
          </div>

          {/* Busiest Channel of the Day */}
          <div
            onClick={() => busiestTg?.talkgroup && handleDrilldown(busiestTg.talkgroup)}
            className="group rounded-lg border border-amber-500/30 bg-amber-500/5 p-2.5 transition-all hover:border-amber-500/60 hover:bg-amber-500/10 cursor-pointer"
            title={busiestTg?.talkgroup ? `Click to filter Search by ${busiestTg.talkgroup}` : undefined}
          >
            <div className="flex items-center justify-between">
              <span className="text-[10px] font-medium uppercase tracking-wider text-amber-300 flex items-center gap-1">
                <FireIcon className="text-amber-400" /> Busiest Channel
              </span>
              <JumpSearchIcon className="h-3 w-3 text-amber-400/60 opacity-0 group-hover:opacity-100 transition-opacity" />
            </div>
            <span className="block truncate font-mono text-sm font-semibold text-amber-100 mt-0.5" title={busiestTg?.talkgroup}>
              {busiestTg?.talkgroup || 'N/A'}
            </span>
            <span className="text-[11px] text-amber-300/80 font-mono">
              {busiestTg ? `${busiestTg.count} calls (${busiestTg.percentage ?? 0}%)` : '—'}
            </span>
          </div>

          {/* Newly Observed Channels */}
          <div
            onClick={() => setFilterTab(filterTab === 'new' ? 'all' : 'new')}
            className={`rounded-lg border p-2.5 transition-all cursor-pointer ${
              filterTab === 'new'
                ? 'border-emerald-500/60 bg-emerald-500/15'
                : 'border-emerald-500/20 bg-emerald-500/5 hover:border-emerald-500/40'
            }`}
          >
            <div className="flex items-center justify-between">
              <span className="text-[10px] font-medium uppercase tracking-wider text-emerald-300 flex items-center gap-1">
                <SparklesIcon className="text-emerald-400" /> New Seen
              </span>
              <span className="text-[10px] text-emerald-400/70 font-mono">filter</span>
            </div>
            <div className="flex items-baseline gap-1 mt-0.5">
              <span className="font-mono text-base font-semibold text-emerald-100">{newTgsCount}</span>
              <span className="text-[11px] text-emerald-300/70">first seen in period</span>
            </div>
          </div>

          {/* Total Airtime */}
          <div className="rounded-lg border border-gray-800/80 bg-gray-950/40 p-2.5">
            <span className="block text-[10px] font-medium uppercase tracking-wider text-gray-400">Total Voice Airtime</span>
            <div className="flex items-baseline gap-1 mt-0.5">
              <span className="font-mono text-base font-semibold text-sky-300">
                {formatDuration(totalAirtimeSec)}
              </span>
              <span className="text-[11px] text-gray-500 font-mono">({totalCalls.toLocaleString()} calls)</span>
            </div>
          </div>
        </div>

        {/* Filter Sub-nav & Search */}
        <div className="mt-4 flex flex-wrap items-center justify-between gap-2.5 border-t border-gray-800/60 pt-3">
          <div className="flex items-center gap-1.5 text-xs">
            <button
              type="button"
              onClick={() => setFilterTab('all')}
              className={`rounded-md px-2.5 py-1 transition-all cursor-pointer font-medium ${
                filterTab === 'all'
                  ? 'bg-gray-800 text-white'
                  : 'text-gray-400 hover:text-gray-200'
              }`}
            >
              All Ranked ({rankedItems.length})
            </button>
            <button
              type="button"
              onClick={() => setFilterTab('new')}
              className={`rounded-md px-2.5 py-1 transition-all cursor-pointer font-medium flex items-center gap-1 ${
                filterTab === 'new'
                  ? 'bg-emerald-500/20 border border-emerald-500/40 text-emerald-200'
                  : 'text-gray-400 hover:text-emerald-300'
              }`}
            >
              <SparklesIcon className="h-3 w-3 text-emerald-400" />
              New to System ({newTgsCount})
            </button>
            <button
              type="button"
              onClick={() => setFilterTab('yesterday')}
              className={`rounded-md px-2.5 py-1 transition-all cursor-pointer font-medium flex items-center gap-1 ${
                filterTab === 'yesterday'
                  ? 'bg-indigo-500/20 border border-indigo-500/40 text-indigo-200'
                  : 'text-gray-400 hover:text-indigo-300'
              }`}
            >
              New vs Yesterday ({newVsYesterdayCount})
            </button>
          </div>

          {/* Quick Search in List */}
          <div className="relative w-full sm:w-48">
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Filter channels..."
              className="w-full rounded-md border border-gray-800 bg-gray-900/60 px-2.5 py-1 text-xs text-gray-200 placeholder-gray-500 focus:border-sky-500/60 focus:outline-none"
            />
            {searchQuery && (
              <button
                type="button"
                onClick={() => setSearchQuery('')}
                className="absolute right-2 top-1/2 -translate-y-1/2 text-xs text-gray-500 hover:text-gray-300"
              >
                ×
              </button>
            )}
          </div>
        </div>

        {/* Scrollable Ranked Channel List */}
        <div className="mt-3 max-h-[360px] overflow-y-auto space-y-2 pr-1.5 focus:outline-none" tabIndex={0} aria-label="Ranked talkgroups scrollable list">
          {visibleItems.length === 0 ? (
            <div className="py-8 text-center text-xs text-gray-500">
              No talkgroups match the current filter.
            </div>
          ) : (
            visibleItems.map((tg) => {
              // Calculate global rank
              const originalRank = rankedItems.findIndex((item) => item.talkgroup === tg.talkgroup) + 1
              const pct = tg.percentage ?? (totalAirtimeSec > 0 ? ((tg.duration || 0) / totalAirtimeSec) * 100 : 0)
              const barWidth = metricMode === 'airtime'
                ? Math.min(100, Math.max(3, (pct / maxMetricVal) * 100))
                : Math.min(100, Math.max(3, (tg.count / maxMetricVal) * 100))

              const isBusiest = originalRank === 1
              const isNew = Boolean(tg.is_new)
              const isNewYesterday = Boolean(tg.is_new_vs_yesterday && !tg.is_new)

              return (
                <div
                  key={tg.talkgroup}
                  onClick={() => handleDrilldown(tg.talkgroup)}
                  className={`group relative cursor-pointer rounded-lg border p-2.5 transition-all ${
                    isBusiest
                      ? 'border-amber-500/30 bg-amber-500/5 hover:border-amber-500/60 hover:bg-amber-500/10'
                      : isNew
                        ? 'border-emerald-500/25 bg-emerald-500/5 hover:border-emerald-500/50 hover:bg-emerald-500/10'
                        : 'border-gray-800/60 bg-gray-900/30 hover:border-sky-500/40 hover:bg-gray-800/40'
                  }`}
                >
                  <div className="mb-1.5 flex items-center justify-between gap-2 text-xs">
                    <div className="flex items-center gap-2 overflow-hidden min-w-0">
                      {/* Rank Number Badge */}
                      <span
                        className={`flex h-5 w-5 shrink-0 items-center justify-center rounded font-mono text-[10px] font-bold ${
                          originalRank === 1
                            ? 'bg-amber-500/20 text-amber-300 border border-amber-500/40'
                            : originalRank === 2
                              ? 'bg-slate-300/20 text-slate-200 border border-slate-300/40'
                              : originalRank === 3
                                ? 'bg-amber-700/20 text-amber-400 border border-amber-700/40'
                                : 'bg-gray-800/80 text-gray-400 group-hover:text-sky-300'
                        }`}
                      >
                        {originalRank}
                      </span>

                      {/* Talkgroup Name */}
                      <span className="truncate font-mono font-medium text-gray-200 group-hover:text-white" title={tg.talkgroup}>
                        {tg.talkgroup}
                      </span>

                      {/* Attribute Badges */}
                      {isBusiest && (
                        <span className="shrink-0 rounded bg-amber-500/20 border border-amber-500/30 px-1.5 py-0.2 text-[9px] font-bold uppercase tracking-wider text-amber-300">
                          Busiest
                        </span>
                      )}
                      {isNew && (
                        <span className="shrink-0 rounded bg-emerald-500/20 border border-emerald-500/30 px-1.5 py-0.2 text-[9px] font-bold uppercase tracking-wider text-emerald-300">
                          New
                        </span>
                      )}
                      {isNewYesterday && (
                        <span className="shrink-0 rounded bg-indigo-500/20 border border-indigo-500/30 px-1.5 py-0.2 text-[9px] font-bold uppercase tracking-wider text-indigo-300">
                          vs Yest
                        </span>
                      )}
                    </div>

                    {/* Stats & Jump Search */}
                    <div className="flex shrink-0 items-center gap-3">
                      <span className="font-mono text-gray-300 font-medium">
                        {metricMode === 'airtime' ? `${pct.toFixed(1)}%` : `${tg.count} calls`}
                      </span>
                      <span className="hidden font-mono text-[11px] text-gray-500 sm:inline">
                        {tg.duration ? formatDuration(tg.duration) : ''}
                        {tg.avg_duration ? ` (~${tg.avg_duration}s/call)` : ''}
                      </span>
                      <JumpSearchIcon className="h-3 w-3 text-gray-500 opacity-0 transition-opacity group-hover:opacity-100 group-hover:text-sky-400" />
                    </div>
                  </div>

                  {/* Visual Progress Bar */}
                  <div className="h-1.5 w-full overflow-hidden rounded-full bg-gray-800/80">
                    <div
                      className={`h-full rounded-full transition-all duration-300 group-hover:brightness-125 ${
                        isBusiest
                          ? 'bg-gradient-to-r from-amber-500 to-orange-500'
                          : isNew
                            ? 'bg-gradient-to-r from-emerald-500 to-teal-400'
                            : 'bg-gradient-to-r from-sky-500 to-indigo-500'
                      }`}
                      style={{ width: `${barWidth}%` }}
                    />
                  </div>
                </div>
              )
            })
          )}
        </div>
      </div>

      {/* Footer Info */}
      <div className="mt-3.5 flex flex-wrap items-center justify-between border-t border-gray-800/60 pt-2.5 text-[11px] text-gray-400 gap-2">
        <span>Click any talkgroup to filter transmission archive in Search</span>
        <span className="font-mono text-gray-400">
          Showing {visibleItems.length} of {rankedItems.length} channels
        </span>
      </div>
    </div>
  )
}
