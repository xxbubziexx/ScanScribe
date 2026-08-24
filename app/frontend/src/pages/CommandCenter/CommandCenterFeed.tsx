import { useMemo, useState } from 'react'
import type { MonitorResponse } from '@/types/events'
import type { PipelineEvent } from '@/pages/Events/IncidentsPage'
import { formatTime, splitBadgeEntries, typeDisplayFor } from '@/pages/Events/IncidentsPage'

interface CommandCenterFeedProps {
  events: PipelineEvent[]
  monitors: MonitorResponse[]
  selectedEventId: string | null
  onSelectEvent: (eventId: string) => void
  onGeocodeEvent?: (eventId: string) => void
  isGeocoding?: boolean
}

type FilterMode = 'all' | 'open' | 'mapped' | 'unmapped'

export function CommandCenterFeed({
  events,
  monitors,
  selectedEventId,
  onSelectEvent,
  onGeocodeEvent,
  isGeocoding,
}: CommandCenterFeedProps) {
  const [search, setSearch] = useState('')
  const [selectedMonitor, setSelectedMonitor] = useState<number | 'all'>('all')
  const [filterMode, setFilterMode] = useState<FilterMode>('open')

  const filteredEvents = useMemo(() => {
    return events.filter((ev) => {
      // Monitor filter
      if (selectedMonitor !== 'all' && ev.monitorId !== selectedMonitor) {
        return false
      }

      // Filter Mode
      if (filterMode === 'open' && ev.status !== 'open') {
        return false
      }
      if (filterMode === 'mapped') {
        if (typeof ev.latitude !== 'number' || typeof ev.longitude !== 'number') return false
      }
      if (filterMode === 'unmapped') {
        if (typeof ev.latitude === 'number' && typeof ev.longitude === 'number') return false
      }

      // Search Query
      if (search.trim()) {
        const q = search.toLowerCase()
        const textToSearch = [
          ev.eventType,
          ev.broadcastType,
          ev.location,
          ev.resolvedAddress,
          ev.units,
          ev.talkgroup,
          ev.statusDetail,
          ev.summary,
          ev.originalTranscription,
          ev.monitorName,
        ]
          .filter(Boolean)
          .join(' ')
          .toLowerCase()

        if (!textToSearch.includes(q)) return false
      }

      return true
    })
  }, [events, selectedMonitor, filterMode, search])

  const counts = useMemo(() => {
    let openCount = 0
    let mappedCount = 0
    let unmappedCount = 0
    for (const e of events) {
      if (e.status === 'open') openCount++
      if (typeof e.latitude === 'number' && typeof e.longitude === 'number') mappedCount++
      else unmappedCount++
    }
    return { total: events.length, open: openCount, mapped: mappedCount, unmapped: unmappedCount }
  }, [events])

  return (
    <aside className="ss-cc-feed-sidebar" aria-label="Live Incident Feed">
      {/* Sidebar Top Filter Header */}
      <div className="ss-cc-feed-header">
        <div className="flex items-center justify-between gap-2">
          <h3 className="text-sm font-bold text-white flex items-center gap-1.5">
            <span>📡</span> Live Incident Feed
          </h3>
          <span className="text-xs text-gray-400 font-mono">
            {filteredEvents.length} / {events.length}
          </span>
        </div>

        {/* Search Input */}
        <div className="relative">
          <input
            type="text"
            className="ss-input text-xs py-1.5 pl-8 w-full"
            placeholder="Search address, units, types…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
          <span className="absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-500 text-xs">🔍</span>
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

        {/* Filter Toolbar */}
        <div className="flex items-center gap-2">
          <select
            className="ss-input text-xs py-1 flex-1"
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
          <div className="flex rounded-lg border border-white/10 bg-white/[0.04] p-0.5 text-[11px]">
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
              onClick={() => setFilterMode('mapped')}
              className={`px-2 py-0.5 rounded ${
                filterMode === 'mapped' ? 'bg-indigo-600 text-white font-semibold' : 'text-gray-400 hover:text-white'
              }`}
            >
              Map ({counts.mapped})
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
      </div>

      {/* Incident Cards Scrollable List */}
      <div className="ss-cc-feed-list">
        {filteredEvents.length === 0 ? (
          <div className="flex flex-col items-center justify-center p-8 text-center text-gray-500">
            <span className="text-3xl mb-2">📻</span>
            <p className="text-sm font-semibold text-gray-400">No matching incidents</p>
            <p className="text-xs text-gray-600 mt-1">Try adjusting your filters or search query</p>
          </div>
        ) : (
          filteredEvents.map((ev) => {
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
                    {formatTime(ev.incidentAt ?? ev.createdAt)}
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
