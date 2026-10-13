import { useMemo, useEffect, useState, useRef, memo, useCallback } from 'react'
import { Link } from 'react-router-dom'
import { eventsApi } from '@/lib/events'
import type { MonitorResponse } from '@/types/events'
import type { PipelineEvent } from '@/pages/Events/IncidentsPage'
import {
  splitBadgeEntries,
  typeDisplayFor,
  formatRelativeTime,
  formatTimeLong,
  getEventActivityTime,
} from '@/pages/Events/IncidentsPage'

export type FilterMode = 'open' | 'closed' | 'mapped' | 'all'
export type Timeframe = '24h' | '3day' | '7day' | 'all'

interface CommandCenterFeedProps {
  events: PipelineEvent[] // filtered events
  rawEvents: PipelineEvent[] // unfiltered events
  monitors: MonitorResponse[]
  selectedEventId: string | null
  onSelectEvent: (eventId: string) => void
  onGeocodeEvent?: (eventId: string) => void
  onUpdateCoordinates?: (
    eventId: string,
    lat: number,
    lng: number,
    address?: string,
    reverseLookup?: boolean,
  ) => Promise<void> | void
  onStartPlacePin?: (eventId: string) => void
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

function formatAudioTime(seconds: number): string {
  if (!seconds || isNaN(seconds)) return '0:00'
  const m = Math.floor(seconds / 60)
  const s = Math.floor(seconds % 60)
  return `${m}:${s < 10 ? '0' : ''}${s}`
}

interface CommandCenterFeedCardProps {
  ev: PipelineEvent
  isSelected: boolean
  isGeocoding?: boolean
  isSearchingAddress: boolean
  addressInput: string
  suggestions: Array<{
    latitude: number
    longitude: number
    label: string
    display_name: string
  }>
  isSearchingSuggestions: boolean
  isPlayingAudio: boolean
  audioProgress?: { current: number; duration: number }
  onSelectEvent: (eventId: string) => void
  onGeocodeEvent?: (eventId: string) => void
  onStartPlacePin?: (eventId: string) => void
  onToggleSearchAddress: (eventId: string, initialLocation?: string) => void
  onAddressInputChange: (val: string) => void
  onCloseSearchAddress: () => void
  onSelectSuggestion: (
    eventId: string,
    cand: { latitude: number; longitude: number; display_name: string },
  ) => void
  onToggleAudio: (eventId: string, audioPath: string) => void
  onAudioSeek: (eventId: string, time: number) => void
}

const CommandCenterFeedCard = memo(function CommandCenterFeedCard({
  ev,
  isSelected,
  isGeocoding,
  isSearchingAddress,
  addressInput,
  suggestions,
  isSearchingSuggestions,
  isPlayingAudio,
  audioProgress,
  onSelectEvent,
  onGeocodeEvent,
  onStartPlacePin,
  onToggleSearchAddress,
  onAddressInputChange,
  onCloseSearchAddress,
  onSelectSuggestion,
  onToggleAudio,
  onAudioSeek,
}: CommandCenterFeedCardProps) {
  const isMapped = typeof ev.latitude === 'number' && typeof ev.longitude === 'number'

  return (
    <div
      onClick={() => onSelectEvent(ev.eventId)}
      className={`group p-2.5 rounded-xl border transition cursor-pointer flex flex-col gap-1.5 relative ${
        isSelected
          ? 'border-indigo-500 bg-indigo-950/40 shadow-lg shadow-indigo-950/50'
          : 'border-white/10 bg-white/[0.02] hover:border-white/20 hover:bg-white/[0.04]'
      }`}
    >
      {/* Top Row: Status + Monitor + Spans + Time */}
      <div className="flex items-center justify-between gap-2 text-xs">
        <div className="flex items-center gap-1.5 min-w-0 flex-wrap">
          <span
            className={`w-2 h-2 rounded-full shrink-0 ${
              ev.status === 'open' ? 'bg-emerald-400 animate-pulse' : 'bg-gray-500'
            }`}
          />
          <span
            className={`font-semibold uppercase tracking-wider text-[10px] shrink-0 ${
              ev.status === 'open' ? 'text-emerald-400' : 'text-gray-400'
            }`}
          >
            {ev.status}
          </span>
          <span className="text-gray-600">·</span>
          <span className="text-gray-300 font-medium truncate max-w-[120px]">
            {ev.monitorName || 'Monitor'}
          </span>
          <span className="text-gray-600">·</span>
          <span
            className="px-1.5 py-0.5 rounded bg-indigo-500/15 text-indigo-300 text-[10px] font-mono border border-indigo-500/25 shrink-0 inline-flex items-center gap-1"
            title={`${typeof ev.spansAttached === 'number' ? ev.spansAttached : 1} attached transmission${(typeof ev.spansAttached === 'number' ? ev.spansAttached : 1) === 1 ? '' : 's'}`}
          >
            <span>📎</span>
            <span>
              {typeof ev.spansAttached === 'number' ? ev.spansAttached : 1}{' '}
              {(typeof ev.spansAttached === 'number' ? ev.spansAttached : 1) === 1
                ? 'span'
                : 'spans'}
            </span>
          </span>
        </div>

        <span
          className="text-[11px] text-gray-400 font-mono shrink-0"
          title={
            ev.incidentAt || ev.createdAt
              ? `Initial: ${formatTimeLong(ev.incidentAt ?? ev.createdAt)}${ev.lastSpanAt || ev.updatedAt ? `\nLast updated: ${formatTimeLong(ev.lastSpanAt ?? ev.updatedAt)}` : ''}`
              : undefined
          }
        >
          {formatRelativeTime(
            ev.lastSpanAt ?? ev.updatedAt ?? ev.incidentAt ?? ev.createdAt,
            ev.incidentAt || ev.createdAt,
          )}
        </span>
      </div>

      {/* Event Type & Status Detail */}
      <div>
        <h4 className="text-sm font-bold text-white group-hover:text-indigo-200 transition leading-tight">
          {typeDisplayFor(ev)}
        </h4>
        {ev.statusDetail && (
          <p className="text-xs text-indigo-300 font-medium mt-0.5">{ev.statusDetail}</p>
        )}
      </div>

      {/* Location / Geocode Status Banner */}
      <div
        className={`flex flex-col gap-1.5 rounded-lg p-1.5 text-xs border ${
          isMapped
            ? 'bg-emerald-950/20 border-emerald-500/20 text-emerald-300'
            : 'bg-amber-950/20 border-amber-500/20 text-amber-300'
        }`}
      >
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-1.5 min-w-0 flex-1">
            <span>{isMapped ? '📍' : '⚠️'}</span>
            <span
              className="truncate font-medium text-gray-200"
              title={ev.resolvedAddress || ev.location || ''}
            >
              {ev.resolvedAddress || ev.location || 'No location given'}
            </span>
          </div>

          <div className="flex items-center gap-1 shrink-0">
            {isMapped ? (
              <span className="text-[10px] font-mono text-emerald-400 bg-emerald-500/10 px-1.5 py-0.5 rounded border border-emerald-500/20">
                Mapped
              </span>
            ) : (
              <>
                {onGeocodeEvent && (
                  <button
                    type="button"
                    className="text-xs font-semibold text-amber-300 hover:text-white bg-amber-500/20 hover:bg-amber-500/30 px-3 py-1.5 rounded-lg border border-amber-500/30 transition min-h-[36px] flex items-center justify-center"
                    disabled={isGeocoding}
                    onClick={(e) => {
                      e.stopPropagation()
                      onGeocodeEvent(ev.eventId)
                    }}
                  >
                    {isGeocoding ? 'Resolving…' : 'Geocode'}
                  </button>
                )}
                {onStartPlacePin && (
                  <button
                    type="button"
                    className="text-xs font-semibold text-indigo-300 hover:text-white bg-indigo-500/20 hover:bg-indigo-500/30 px-3 py-1.5 rounded-lg border border-indigo-500/30 transition flex items-center justify-center gap-1.5 min-h-[36px]"
                    onClick={(e) => {
                      e.stopPropagation()
                      onStartPlacePin(ev.eventId)
                    }}
                    title="Click on the map to place a pin for this incident"
                  >
                    <span>📍</span> Pick on Map
                  </button>
                )}
              </>
            )}

            <button
              type="button"
              className="text-xs text-gray-400 hover:text-white bg-white/5 hover:bg-white/10 px-2.5 py-1.5 rounded-lg border border-white/10 transition min-h-[36px] min-w-[36px] flex items-center justify-center"
              onClick={(e) => {
                e.stopPropagation()
                onToggleSearchAddress(ev.eventId, ev.location || '')
              }}
              title="Search and assign address"
            >
              🔍
            </button>
          </div>
        </div>

        {/* Inline Address Search & Autocomplete Dropdown */}
        {isSearchingAddress && (
          <div
            className="flex flex-col gap-1 mt-1 bg-gray-950 p-2 rounded-lg border border-indigo-500/40 relative shadow-xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center gap-1.5">
              <input
                type="text"
                autoFocus
                placeholder="Type address or road name..."
                value={addressInput}
                onChange={(e) => onAddressInputChange(e.target.value)}
                className="ss-input text-xs py-1 px-2 flex-1 bg-black/60 border-white/20 text-white"
                onKeyDown={(e) => {
                  if (e.key === 'Escape') {
                    onCloseSearchAddress()
                  }
                }}
              />
              <button
                type="button"
                onClick={onCloseSearchAddress}
                className="text-xs text-gray-400 hover:text-white px-1.5 py-0.5"
              >
                ✕
              </button>
            </div>

            {isSearchingSuggestions && (
              <span className="text-[10px] text-indigo-300 animate-pulse px-1">
                Searching candidates...
              </span>
            )}

            {suggestions.length > 0 && (
              <div className="flex flex-col gap-1 mt-1 max-h-40 overflow-y-auto bg-gray-900 border border-white/10 rounded shadow-lg">
                {suggestions.map((cand, idx) => (
                  <button
                    key={idx}
                    type="button"
                    onClick={() => onSelectSuggestion(ev.eventId, cand)}
                    className="text-left px-2.5 py-1.5 hover:bg-indigo-600/30 transition border-b border-white/5 last:border-0 flex flex-col"
                  >
                    <span className="font-bold text-white text-xs">{cand.label}</span>
                    <span className="text-[10px] text-gray-400 truncate">
                      {cand.display_name}
                    </span>
                  </button>
                ))}
              </div>
            )}
          </div>
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
        <p className="text-xs text-gray-300 italic bg-black/20 p-2 rounded border border-white/5 leading-relaxed break-words">
          &ldquo;{ev.summary || ev.originalTranscription}&rdquo;
        </p>
      )}

      {/* Compact Inline Audio Player */}
      {ev.audioPath && ev.audioPath !== 'file not saved' && (
        <div
          className="ss-cc-audio-row flex items-center gap-2.5 bg-black/40 px-2.5 py-2 rounded-lg border border-white/10 min-h-[44px]"
          onClick={(e) => e.stopPropagation()}
        >
          <button
            type="button"
            className="w-10 h-10 sm:w-8 sm:h-8 min-w-[40px] sm:min-w-[32px] rounded-full bg-indigo-600 hover:bg-indigo-500 text-white flex items-center justify-center text-sm sm:text-xs shrink-0 transition shadow-md cursor-pointer"
            onClick={() => onToggleAudio(ev.eventId, ev.audioPath!)}
            title={
              isPlayingAudio
                ? 'Pause dispatch audio'
                : 'Play dispatch audio'
            }
            aria-label={
              isPlayingAudio
                ? 'Pause dispatch audio'
                : 'Play dispatch audio'
            }
          >
            {isPlayingAudio ? '❚❚' : '▶'}
          </button>
          <div className="flex-1 min-w-0 flex flex-col justify-center">
            <input
              type="range"
              min={0}
              max={audioProgress?.duration || 1}
              step={0.1}
              value={audioProgress?.current || 0}
              onChange={(e) => onAudioSeek(ev.eventId, Number(e.target.value))}
              className="w-full h-2.5 sm:h-1.5 bg-white/20 rounded appearance-none cursor-pointer accent-indigo-400 py-1"
            />
            <div className="flex justify-between text-[10px] font-mono text-gray-400 mt-0.5">
              <span>{formatAudioTime(audioProgress?.current || 0)}</span>
              <span>{formatAudioTime(audioProgress?.duration || 0)}</span>
            </div>
          </div>
        </div>
      )}

      {/* Card Footer: Event ID & Link to Incidents Hub */}
      <div className="flex items-center justify-between gap-2 pt-1 border-t border-white/5 text-[11px]">
        <span className="font-mono text-[10px] text-gray-500 truncate">{ev.eventId}</span>
        <Link
          to={`/events?incident_id=${encodeURIComponent(ev.eventId)}`}
          className="inline-flex items-center gap-1 text-[11px] font-semibold text-indigo-400 hover:text-indigo-200 transition"
          onClick={(e) => e.stopPropagation()}
          title="Open in Incidents Hub"
        >
          <span>View Event</span> &rarr;
        </Link>
      </div>
    </div>
  )
})

function CommandCenterFeedComponent({

  events,
  rawEvents,
  monitors,
  selectedEventId,
  onSelectEvent,
  onGeocodeEvent,
  onUpdateCoordinates,
  onStartPlacePin,
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
  // Audio Playback State
  const [playingAudioId, setPlayingAudioId] = useState<string | null>(null)
  const [audioProgress, setAudioProgress] = useState<
    Record<string, { current: number; duration: number }>
  >({})
  const audioRef = useRef<HTMLAudioElement | null>(null)

  const toggleAudio = useCallback((eventId: string, audioPath: string) => {
    setPlayingAudioId((currentPlayingId) => {
      if (currentPlayingId === eventId) {
        if (audioRef.current) {
          audioRef.current.pause()
        }
        return null
      }

      if (audioRef.current) {
        audioRef.current.pause()
      }

      const audio = new Audio(`/${audioPath}`)
      audioRef.current = audio

      audio.ontimeupdate = () => {
        setAudioProgress((prev) => ({
          ...prev,
          [eventId]: { current: audio.currentTime, duration: audio.duration || 0 },
        }))
      }

      audio.onloadedmetadata = () => {
        setAudioProgress((prev) => ({
          ...prev,
          [eventId]: { current: 0, duration: audio.duration || 0 },
        }))
      }

      audio.onended = () => {
        setPlayingAudioId(null)
        setAudioProgress((prev) => ({
          ...prev,
          [eventId]: { current: 0, duration: audio.duration || 0 },
        }))
      }

      audio.play().catch(() => setPlayingAudioId(null))
      return eventId
    })
  }, [])

  const handleAudioSeek = useCallback((eventId: string, time: number) => {
    if (audioRef.current) {
      audioRef.current.currentTime = time
      setAudioProgress((prev) => ({
        ...prev,
        [eventId]: { ...prev[eventId], current: time, duration: prev[eventId]?.duration || 0 },
      }))
    }
  }, [])

  useEffect(() => {
    return () => {
      if (audioRef.current) {
        audioRef.current.pause()
      }
    }
  }, [])

  // Quick Address Search & Autocomplete State
  const [searchTargetEventId, setSearchTargetEventId] = useState<string | null>(null)
  const [addressInput, setAddressInput] = useState<string>('')
  const [suggestions, setSuggestions] = useState<
    Array<{
      latitude: number
      longitude: number
      label: string
      display_name: string
    }>
  >([])
  const [isSearchingSuggestions, setIsSearchingSuggestions] = useState(false)

  const handleToggleSearchAddress = useCallback((eventId: string, initialLocation?: string) => {
    setSearchTargetEventId((prev) => {
      if (prev === eventId) {
        setSuggestions([])
        return null
      }
      setAddressInput(initialLocation || '')
      return eventId
    })
  }, [])

  const handleCloseSearchAddress = useCallback(() => {
    setSearchTargetEventId(null)
    setSuggestions([])
  }, [])

  useEffect(() => {
    if (!searchTargetEventId || !addressInput || addressInput.trim().length < 2) {
      setSuggestions([])
      return
    }

    const timer = setTimeout(async () => {
      setIsSearchingSuggestions(true)
      try {
        const targetEv = events.find((e) => e.eventId === searchTargetEventId)
        const res = await eventsApi.autocomplete(addressInput.trim(), targetEv?.monitorId)
        setSuggestions(res.candidates || [])
      } catch {
        setSuggestions([])
      } finally {
        setIsSearchingSuggestions(false)
      }
    }, 300)

    return () => clearTimeout(timer)
  }, [addressInput, searchTargetEventId, events])

  const handleSelectSuggestion = useCallback(
    async (
      eventId: string,
      cand: { latitude: number; longitude: number; display_name: string },
    ) => {
      if (onUpdateCoordinates) {
        await onUpdateCoordinates(eventId, cand.latitude, cand.longitude, cand.display_name, false)
      }
      setSearchTargetEventId(null)
      setAddressInput('')
      setSuggestions([])
    },
    [onUpdateCoordinates],
  )

  const [, setTick] = useState(0)
  useEffect(() => {
    const interval = setInterval(() => setTick((t) => t + 1), 5000)
    return () => clearInterval(interval)
  }, [])

  // Counts based on time and monitor filters (but ignoring mode filter)
  const counts = useMemo(() => {
    const now = Date.now()
    const base = rawEvents.filter((ev) => {
      if (selectedMonitor !== 'all' && ev.monitorId !== selectedMonitor) return false

      const evTime = getEventActivityTime(ev)
      if (timeframe === '24h' && now - evTime > 24 * 60 * 60 * 1000) return false
      if (timeframe === '3day' && now - evTime > 3 * 24 * 60 * 60 * 1000) return false
      if (timeframe === '7day' && now - evTime > 7 * 24 * 60 * 60 * 1000) return false

      return true
    })

    return {
      open: base.filter((e) => e.status === 'open').length,
      closed: base.filter((e) => e.status === 'closed').length,
      mapped: base.filter((e) => typeof e.latitude === 'number' && typeof e.longitude === 'number')
        .length,
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
            className="ss-input text-xs pl-8 pr-9 py-2 w-full bg-white/[0.03] min-h-[42px]"
            placeholder="Search address, units, types..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
          {search && (
            <button
              type="button"
              className="absolute right-1 top-1/2 -translate-y-1/2 text-gray-400 hover:text-white text-xs w-9 h-9 flex items-center justify-center rounded-lg cursor-pointer"
              onClick={() => setSearch('')}
              aria-label="Clear search"
            >
              ✕
            </button>
          )}
        </div>

        {/* Filter Toolbar (Row 1) */}
        <div className="flex items-center gap-2">
          <select
            className="ss-input text-xs py-2 flex-1 min-w-0 min-h-[42px]"
            value={selectedMonitor}
            onChange={(e) =>
              setSelectedMonitor(e.target.value === 'all' ? 'all' : Number(e.target.value))
            }
          >
            <option value="all">All Monitors ({monitors.length})</option>
            {monitors.map((m) => (
              <option key={m.id} value={m.id}>
                {m.name}
              </option>
            ))}
          </select>

          {/* Quick Filter Mode Selector */}
          <div className="flex rounded-lg border border-white/10 bg-white/[0.04] p-0.5 text-xs shrink-0">
            <button
              type="button"
              onClick={() => setFilterMode('open')}
              className={`px-3 py-2 rounded-md min-h-[38px] cursor-pointer transition ${
                filterMode === 'open'
                  ? 'bg-indigo-600 text-white font-semibold shadow-sm'
                  : 'text-gray-400 hover:text-white'
              }`}
            >
              Open ({counts.open})
            </button>
            <button
              type="button"
              onClick={() => setFilterMode('closed')}
              className={`px-3 py-2 rounded-md min-h-[38px] cursor-pointer transition ${
                filterMode === 'closed'
                  ? 'bg-indigo-600 text-white font-semibold shadow-sm'
                  : 'text-gray-400 hover:text-white'
              }`}
            >
              Closed ({counts.closed})
            </button>
            <button
              type="button"
              onClick={() => setFilterMode('all')}
              className={`px-3 py-2 rounded-md min-h-[38px] cursor-pointer transition ${
                filterMode === 'all'
                  ? 'bg-indigo-600 text-white font-semibold shadow-sm'
                  : 'text-gray-400 hover:text-white'
              }`}
            >
              All
            </button>
          </div>
        </div>

        {/* Filter Toolbar (Row 2 - Timeframe) */}
        <div className="flex items-center gap-2">
          <select
            className="ss-input text-xs py-2 flex-1 min-w-0 min-h-[42px]"
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
          events.map((ev) => (
            <CommandCenterFeedCard
              key={ev.eventId}
              ev={ev}
              isSelected={ev.eventId === selectedEventId}
              isGeocoding={isGeocoding}
              isSearchingAddress={searchTargetEventId === ev.eventId}
              addressInput={addressInput}
              suggestions={suggestions}
              isSearchingSuggestions={isSearchingSuggestions}
              isPlayingAudio={playingAudioId === ev.eventId}
              audioProgress={audioProgress[ev.eventId]}
              onSelectEvent={onSelectEvent}
              onGeocodeEvent={onGeocodeEvent}
              onStartPlacePin={onStartPlacePin}
              onToggleSearchAddress={handleToggleSearchAddress}
              onAddressInputChange={setAddressInput}
              onCloseSearchAddress={handleCloseSearchAddress}
              onSelectSuggestion={handleSelectSuggestion}
              onToggleAudio={toggleAudio}
              onAudioSeek={handleAudioSeek}
            />
          ))
        )}
      </div>
    </aside>
  )
}

export const CommandCenterFeed = memo(CommandCenterFeedComponent)

