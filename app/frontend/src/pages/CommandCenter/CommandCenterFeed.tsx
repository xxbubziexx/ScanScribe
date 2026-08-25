import { useMemo, useEffect, useState } from 'react'
import type { MonitorResponse } from '@/types/events'
import type { PipelineEvent } from '@/pages/Events/IncidentsPage'
import { splitBadgeEntries, typeDisplayFor } from '@/pages/Events/IncidentsPage'

export type FilterMode = 'open' | 'closed' | 'mapped' | 'all'
export type Timeframe = '24h' | '3day' | '7day' | 'all'

interface CommandCenterFeedProps {
  events: PipelineEvent[] // filtered events
  rawEvents: PipelineEvent[] // unfiltered events
  monitors: MonitorResponse[]
  selectedEventId: string | null
  onSelectEvent: (eventId: string) => void
  onGeocodeEvent?: (eventId: string) => void
  isGeocoding?: boolean
  search: string
  setSearch: (s: string) => void
  selectedMonitor: number | 'all'
  setSelectedMonitor: (m: number | 'all') => void
  filterMode: FilterMode
  setFilterMode: (m: FilterMode) => void
  timeframe: Timeframe
  setTimeframe: (t: Timeframe) => void
}


function formatRelativeTime(dateStr: string): string {
  const date = new Date(dateStr)
  const now = new Date()
  const diffMs = now.getTime() - date.getTime()
  
  if (diffMs < 0) return 'just now'
  
  const diffSec = Math.floor(diffMs / 1000)
  if (diffSec < 60) return `${diffSec}s ago`
  
  const diffMin = Math.floor(diffSec / 60)
  if (diffMin < 60) return `${diffMin}m ago`
  
  const diffHour = Math.floor(diffMin / 60)
  if (diffHour < 24) return `${diffHour}h ago`
  
  return 'over 24h ago'
}

export function CommandCenterFeed({
  events,
  rawEvents,
  monitors,
  selectedEventId,
  onSelectEvent,
  onGeocodeEvent,
  isGeocoding,
  search,
  setSearch,
  selectedMonitor,
  setSelectedMonitor,
  filterMode,
  setFilterMode,
  timeframe,
  setTimeframe,
}: CommandCenterFeedProps) {

  const [, setTick] = useState(0)
  useEffect(() => {
    const interval = setInterval(() => setTick(t => t + 1), 5000)
    return () => clearInterval(interval)
  }, [])

  // Counts based on time and monitor filters (but ignoring mode filter)
  const counts = useMemo(() => {
    const now = Date.now()
    const base = rawEvents.filter((ev) => {
      if (selectedMonitor !== 'all' && ev.monitorId !== selectedMonitor) return false
      
      const evTime = new Date(ev.incidentAt ?? ev.createdAt).getTime()
      if (timeframe === '24h' && now - evTime > 24 * 60 * 60 * 1000) return false
      if (timeframe === '3day' && now - evTime > 3 * 24 * 60 * 60 * 1000) return false
      if (timeframe === '7day' && now - evTime > 7 * 24 * 60 * 60 * 1000) return false
      
      return true
    })

    return {
      open: base.filter((e) => e.status === 'open').length,
      closed: base.filter((e) => e.status === 'closed').length,
      mapped: base.filter((e) => typeof e.latitude === 'number' && typeof e.longitude === 'number').length,
      all: base.length,
    }
  }, [rawEvents, selectedMonitor, timeframe])

  return (
    <aside className="ss-cc-feed-sidebar" aria-label="Live Incident Feed">
      <div className="ss-cc-feed-header gap-3">
        
        {/* Top Header Row with Title and Stats */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="text-lg">📡</span>
            <h2 className="font-bold text-gray-100 tracking-wide text-[15px]">
              Live Incident Feed
            </h2>
          </div>
          <span className="text-xs font-mono text-gray-500 bg-black/40 px-2 py-0.5 rounded border border-white/10">
            {events.length} / {rawEvents.length}
          </span>
        </div>

        {/* Search Bar */}
        <div className="relative">
          <span className="absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-500 text-xs">
            🔍
          </span>
          <input
            type="text"
            className="ss-input text-xs pl-8 py-1.5 w-full bg-white/[0.03]"
            placeholder="Search address, units, types..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
          {search && (
            <button
              type="button"
              className="absolute right-2.5 top-1/2 -translate-y-1/2 text-gray-500 hover:text-gray-300 text-xs"
              onClick={() => setSearch('')}
            >
              ✕
            </button>
          )}
        </div>

        {/* Filter Toolbar (Row 1) */}
        <div className="flex items-center gap-2">
          <select
            className="ss-input text-xs py-1 flex-1 min-w-0"
            value={selectedMonitor}
            onChange={(e) => setSelectedMonitor(e.target.value === 'all' ? 'all' : Number(e.target.value))}
          >
            <option value="all">All Monitors ({monitors.length})</option>
            {monitors.map((m) => (
              <option key={m.id} value={m.id}>
                {m.name}
              </option>
            ))}
          </select>

          {/* Quick Filter Mode Selector */}
          <div className="flex rounded-lg border border-white/10 bg-white/[0.04] p-0.5 text-[11px] shrink-0">
            <button
              type="button"
              onClick={() => setFilterMode('open')}
              className={`px-2 py-0.5 rounded ${
                filterMode === 'open' ? 'bg-indigo-600 text-white font-semibold' : 'text-gray-400 hover:text-white'
              }`}
            >
              Open ({counts.open})
            </button>
            <button
              type="button"
              onClick={() => setFilterMode('closed')}
              className={`px-2 py-0.5 rounded ${
                filterMode === 'closed' ? 'bg-indigo-600 text-white font-semibold' : 'text-gray-400 hover:text-white'
              }`}
            >
              Closed ({counts.closed})
            </button>
            <button
              type="button"
              onClick={() => setFilterMode('all')}
              className={`px-2 py-0.5 rounded ${
                filterMode === 'all' ? 'bg-indigo-600 text-white font-semibold' : 'text-gray-400 hover:text-white'
              }`}
            >
              All
            </button>
          </div>
        </div>

        {/* Filter Toolbar (Row 2 - Timeframe) */}
        <div className="flex items-center gap-2">
          <select
            className="ss-input text-xs py-1 flex-1 min-w-0"
            value={timeframe}
            onChange={(e) => setTimeframe(e.target.value as Timeframe)}
          >
            <option value="24h">Past 24 Hours</option>
            <option value="3day">Past 3 Days</option>
            <option value="7day">Past 7 Days</option>
            <option value="all">All Time</option>
          </select>
        </div>
      </div>

      {/* Incident Cards Scrollable List */}
      <div className="ss-cc-feed-list">
        {events.length === 0 ? (
          <div className="flex flex-col items-center justify-center p-8 text-center text-gray-500">
            <span className="text-3xl mb-2">📻</span>
            <p className="text-sm font-semibold text-gray-400">No matching incidents</p>
            <p className="text-xs text-gray-600 mt-1">Try adjusting your filters or search query</p>
          </div>
        ) : (
          events.map((ev) => {
            const isSelected = ev.eventId === selectedEventId
            const isMapped = typeof ev.latitude === 'number' && typeof ev.longitude === 'number'

            return (
              <div
                key={ev.eventId}
                onClick={() => onSelectEvent(ev.eventId)}
                className={`group p-3 rounded-xl border transition cursor-pointer flex flex-col gap-2 relative ${
                  isSelected
                    ? 'border-indigo-500 bg-indigo-950/40 shadow-lg shadow-indigo-950/50'
                    : 'border-white/10 bg-white/[0.02] hover:border-white/20 hover:bg-white/[0.04]'
                }`}
              >
                {/* Top Row: Status + Monitor + Time */}
                <div className="flex items-center justify-between gap-2 text-xs">
                  <div className="flex items-center gap-1.5">
                    <span
                      className={`w-2 h-2 rounded-full ${
                        ev.status === 'open' ? 'bg-emerald-400 animate-pulse' : 'bg-gray-500'
                      }`}
                    />
                    <span
                      className={`font-semibold uppercase tracking-wider text-[10px] ${
                        ev.status === 'open' ? 'text-emerald-400' : 'text-gray-400'
                      }`}
                    >
                      {ev.status}
                    </span>
                    <span className="text-gray-600">·</span>
                    <span className="text-gray-300 font-medium truncate max-w-[120px]">
                      {ev.monitorName || 'Monitor'}
                    </span>
                  </div>

                  <span className="text-[11px] text-gray-400 font-mono">
                    {formatRelativeTime(ev.incidentAt ?? ev.createdAt)}
                  </span>
                </div>

                {/* Event Type & Status Detail */}
                <div>
                  <h4 className="text-sm font-bold text-white group-hover:text-indigo-200 transition leading-tight">
                    {typeDisplayFor(ev)}
                  </h4>
                  {ev.statusDetail && (
                    <p className="text-xs text-indigo-300 font-medium mt-0.5">
                      {ev.statusDetail}
                    </p>
                  )}
                </div>

                {/* Location / Geocode Status Banner */}
                <div
                  className={`flex items-center justify-between gap-2 rounded-lg p-2 text-xs border ${
                    isMapped
                      ? 'bg-emerald-950/20 border-emerald-500/20 text-emerald-300'
                      : 'bg-amber-950/20 border-amber-500/20 text-amber-300'
                  }`}
                >
                  <div className="flex items-center gap-1.5 min-w-0 flex-1">
                    <span>{isMapped ? '📍' : '⚠️'}</span>
                    <span className="truncate font-medium text-gray-200" title={ev.resolvedAddress || ev.location || ''}>
                      {ev.location || 'No location given'}
                    </span>
                  </div>

                  {isMapped ? (
                    <span className="text-[10px] font-mono text-emerald-400 bg-emerald-500/10 px-1.5 py-0.5 rounded shrink-0 border border-emerald-500/20">
                      Mapped
                    </span>
                  ) : (
                    onGeocodeEvent && (
                      <button
                        type="button"
                        className="text-[10px] font-semibold text-amber-300 hover:text-white bg-amber-500/20 hover:bg-amber-500/30 px-2 py-0.5 rounded border border-amber-500/30 transition shrink-0"
                        disabled={isGeocoding}
                        onClick={(e) => {
                          e.stopPropagation()
                          onGeocodeEvent(ev.eventId)
                        }}
                      >
                        {isGeocoding ? 'Resolving…' : 'Geocode'}
                      </button>
                    )
                  )}
                </div>

                {/* Talkgroup and Units chips */}
                <div className="flex flex-wrap items-center gap-1">
                  {splitBadgeEntries(ev.talkgroup).map((tg) => (
                    <span
                      key={`${ev.eventId}-tg-${tg}`}
                      className="px-1.5 py-0.5 rounded bg-white/5 text-gray-300 text-[10px] font-mono border border-white/5"
                    >
                      {tg}
                    </span>
                  ))}
                  {splitBadgeEntries(ev.units).map((u) => (
                    <span
                      key={`${ev.eventId}-u-${u}`}
                      className="px-1.5 py-0.5 rounded bg-blue-500/10 text-blue-300 text-[10px] font-mono border border-blue-500/20"
                    >
                      {u}
                    </span>
                  ))}
                </div>

                {/* Transcript snippet / summary preview */}
                {(ev.summary || ev.originalTranscription) && (
                  <p className="text-xs text-gray-400 line-clamp-2 italic bg-black/20 p-1.5 rounded border border-white/5">
                    &ldquo;{ev.summary || ev.originalTranscription}&rdquo;
                  </p>
                )}
              </div>
            )
          })
        )}
      </div>
    </aside>
  )
}
