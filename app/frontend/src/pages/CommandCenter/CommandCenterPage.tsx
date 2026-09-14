import { useCallback, useEffect, useMemo, useState, useRef } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { eventsApi } from '@/lib/events'
import { insights } from '@/lib/insights'
import { useToast } from '@/context/ToastContext'
import { useWebSocket } from '@/hooks/useWebSocket'
import { errorMessage } from '@/types/api'
import type { WsMessage } from '@/types/watcher'
import type { EventListItem } from '@/types/events'
import type { PipelineEvent } from '@/pages/Events/IncidentsPage'
import { toPipelineEvent, getEventActivityTime } from '@/pages/Events/IncidentsPage'
import { CommandCenterMap } from './CommandCenterMap'
import { CommandCenterFeed, type FilterMode, type Timeframe } from './CommandCenterFeed'
import { CommandCenterTelemetry } from './CommandCenterTelemetry'

const WS_URL = `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}/ws`

export function CommandCenterPage() {
  const queryClient = useQueryClient()
  const { addToast } = useToast()

  const containerRef = useRef<HTMLDivElement>(null)
  const [isFullscreen, setIsFullscreen] = useState(false)

  const [selectedEventId, setSelectedEventId] = useState<string | null>(null)
  const [liveCpm, setLiveCpm] = useState<number | null>(null)
  const [activeTab, setActiveTab] = useState<'map' | 'feed'>('map')

  // Listen for fullscreenchange events to update state
  useEffect(() => {
    const handleFullscreenChange = () => {
      setIsFullscreen(!!document.fullscreenElement)
    }
    document.addEventListener('fullscreenchange', handleFullscreenChange)
    return () => document.removeEventListener('fullscreenchange', handleFullscreenChange)
  }, [])

  const toggleFullscreen = useCallback(async () => {
    if (!document.fullscreenElement) {
      try {
        await containerRef.current?.requestFullscreen()
      } catch (err) {
        addToast('Failed to enter fullscreen mode', 'error')
      }
    } else {
      if (document.exitFullscreen) {
        await document.exitFullscreen()
      }
    }
  }, [addToast])

  // Fetch Monitors
  const monitorsQuery = useQuery({
    queryKey: ['events-monitors'],
    queryFn: () => eventsApi.monitors(),
    staleTime: 60_000,
  })
  const monitors = useMemo(() => monitorsQuery.data ?? [], [monitorsQuery.data])
  const monitorNameMap = useMemo(() => {
    const map = new Map<number, string>()
    for (const m of monitors) {
      map.set(m.id, m.name)
    }
    return map
  }, [monitors])

  // Fetch Events (Incidents) sorted by latest activity
  const eventsQuery = useQuery({
    queryKey: ['events-list', 'command-center'],
    queryFn: () => eventsApi.list({ limit: 200, sortBy: 'updated_at', sortOrder: 'desc' }),
    staleTime: 10_000,
    refetchInterval: 15_000,
  })

  // Fetch Insights Summary for today
  const todayIso = new Date().toISOString().split('T')[0]
  const insightsQuery = useQuery({
    queryKey: ['insights-stats', todayIso, 'hourly'],
    queryFn: () => insights.stats(todayIso, 'hourly'),
    staleTime: 30_000,
  })

  // Poll live CPM
  useEffect(() => {
    const poll = async () => {
      try {
        const data = await insights.liveCpm()
        setLiveCpm(data.calls_per_minute)
      } catch {
        /* ignore */
      }
    }
    poll()
    const timer = setInterval(poll, 10_000)
    return () => clearInterval(timer)
  }, [])

  // Geocode Mutation
  const geocodeMutation = useMutation({
    mutationFn: (eventId: string) => eventsApi.geocode(eventId),
    onSuccess: (res) => {
      if (res.ok && res.latitude && res.longitude) {
        addToast(
          `Address resolved: ${res.resolved_address || `${res.latitude}, ${res.longitude}`}`,
          'success',
        )
      } else {
        addToast(res.message || 'Address could not be geocoded', 'warning')
      }
      void queryClient.invalidateQueries({ queryKey: ['events-list'] })
    },
    onError: (e: unknown) => {
      addToast(errorMessage(e, 'Geocoding request failed'), 'error')
    },
  })

  const removeGeocodeMutation = useMutation({
    mutationFn: (eventId: string) => eventsApi.removeGeocode(eventId),
    onSuccess: (res) => {
      addToast(res.message || 'Pin removed', 'success')
      void queryClient.invalidateQueries({ queryKey: ['events-list'] })
    },
    onError: (e: unknown) => {
      addToast(errorMessage(e, 'Failed to remove pin'), 'error')
    },
  })

  const handleRemoveGeocode = useCallback(
    (eventId: string) => {
      removeGeocodeMutation.mutate(eventId)
    },
    [removeGeocodeMutation],
  )

  const handleGeocode = useCallback(
    (eventId: string) => {
      geocodeMutation.mutate(eventId)
    },
    [geocodeMutation],
  )

  const [pinPlacementEventId, setPinPlacementEventId] = useState<string | null>(null)

  const setCoordinatesMutation = useMutation({
    mutationFn: (args: {
      eventId: string
      latitude: number
      longitude: number
      resolvedAddress?: string
      reverseLookup?: boolean
    }) =>
      eventsApi.setCoordinates(args.eventId, {
        latitude: args.latitude,
        longitude: args.longitude,
        resolved_address: args.resolvedAddress,
        reverse_lookup: args.reverseLookup,
      }),
    onSuccess: (res) => {
      addToast(
        res.resolved_address ? `Pin updated: ${res.resolved_address}` : 'Pin updated successfully',
        'success',
      )
      void queryClient.invalidateQueries({ queryKey: ['events-list'] })
    },
    onError: (e: unknown) => {
      addToast(errorMessage(e, 'Failed to update pin location'), 'error')
    },
  })

  const handleUpdateCoordinates = useCallback(
    async (
      eventId: string,
      latitude: number,
      longitude: number,
      resolvedAddress?: string,
      reverseLookup = true,
    ) => {
      await setCoordinatesMutation.mutateAsync({
        eventId,
        latitude,
        longitude,
        resolvedAddress,
        reverseLookup,
      })
    },
    [setCoordinatesMutation],
  )

  const handleMapClickToPin = useCallback(
    async (lat: number, lng: number) => {
      if (pinPlacementEventId) {
        const ev = (eventsQuery.data?.items ?? []).find((e) => e.event_id === pinPlacementEventId)
        const label = ev ? ev.event_type || 'this incident' : 'this incident'
        if (
          window.confirm(
            `Set pin for "${label}" at coordinates (${lat.toFixed(5)}, ${lng.toFixed(5)})?`,
          )
        ) {
          await handleUpdateCoordinates(pinPlacementEventId, lat, lng, undefined, true)
        }
        setPinPlacementEventId(null)
      }
    },
    [pinPlacementEventId, eventsQuery.data?.items, handleUpdateCoordinates],
  )

  const handleSelectEvent = useCallback((id: string) => {
    setSelectedEventId(id)
    setActiveTab('map')
  }, [])

  // Real-time WebSocket event handling
  const handleWsMessage = useCallback(
    (msg: WsMessage) => {
      if (msg.type === 'event_update' || msg.type === 'event_geocoded') {
        // Optimistic / fast query invalidation for new/updated incidents
        void queryClient.invalidateQueries({ queryKey: ['events-list'] })
      }
    },
    [queryClient],
  )

  useWebSocket(WS_URL, handleWsMessage)

  // Filter state (hoisted so Map can share it)
  const [search, setSearch] = useState('')
  const [selectedMonitor, setSelectedMonitor] = useState<number | 'all'>('all')
  const [filterMode, setFilterMode] = useState<FilterMode>('open')
  const [timeframe, setTimeframe] = useState<Timeframe>('24h')

  const [mapOptionsOpen, setMapOptionsOpen] = useState(false)
  const [mapOptions, setMapOptions] = useState({
    showLabels: true,
    clusterPins: false,
    unlockAllPins: false,
  })

  // Transform raw event items into PipelineEvents with monitor names
  const rawItems: EventListItem[] = eventsQuery.data?.items ?? []
  const pipelineEvents: PipelineEvent[] = useMemo(() => {
    return rawItems.map((item) => {
      const pe = toPipelineEvent(item)
      pe.monitorName = monitorNameMap.get(pe.monitorId) || `Monitor #${pe.monitorId}`
      return pe
    })
  }, [rawItems, monitorNameMap])

  const filteredEvents = useMemo(() => {
    const now = Date.now()
    return pipelineEvents
      .filter((ev) => {
        // Monitor filter
        if (selectedMonitor !== 'all' && ev.monitorId !== selectedMonitor) return false
        // Filter mode
        if (filterMode === 'open' && ev.status !== 'open') return false
        if (filterMode === 'closed' && ev.status !== 'closed') return false
        if (filterMode === 'mapped' && (ev.latitude == null || ev.longitude == null)) return false

        // Timeframe filter (based on most recent activity)
        const evTime = getEventActivityTime(ev)
        if (timeframe === '24h' && now - evTime > 24 * 60 * 60 * 1000) return false
        if (timeframe === '3day' && now - evTime > 3 * 24 * 60 * 60 * 1000) return false
        if (timeframe === '7day' && now - evTime > 7 * 24 * 60 * 60 * 1000) return false

        // Text search
        if (search.trim()) {
          const q = search.toLowerCase()
          const textToSearch = [
            ev.eventId,
            ev.eventType,
            ev.broadcastType,
            ev.status,
            ev.location,
            ev.resolvedAddress,
            ev.units,
            ev.talkgroup,
            ev.summary,
            ev.originalTranscription,
          ]
            .filter(Boolean)
            .join(' ')
            .toLowerCase()
          if (!textToSearch.includes(q)) return false
        }

        return true
      })
      .sort((a, b) => getEventActivityTime(b) - getEventActivityTime(a))
  }, [pipelineEvents, selectedMonitor, filterMode, timeframe, search])

  return (
    <div
      className={`ss-command-center ${isFullscreen ? 'ss-cc-fullscreen' : ''}`}
      ref={containerRef}
    >
      {/* Command Center Top Navigation Toolbar */}
      <header className="ss-cc-header">
        <div className="flex w-full items-center justify-between gap-2">
          <div className="ss-cc-title-group">
            <h1 className="ss-cc-title">
              <span className="text-xl">🗺️</span> Command Center
            </h1>
            <div className="ss-cc-live-badge">
              <span className="ss-cc-live-dot"></span>
              <span className="hidden sm:inline">LIVE FEED</span>
              <span className="sm:hidden">LIVE</span>
            </div>
          </div>

          <div className="ss-cc-controls">
            <div className="relative shrink-0">
              <button
                type="button"
                className="ss-btn-ghost text-xs py-1.5 px-2.5 flex items-center gap-1 whitespace-nowrap min-h-[38px] cursor-pointer"
                onClick={() => setMapOptionsOpen(!mapOptionsOpen)}
                aria-expanded={mapOptionsOpen}
                aria-label="Map Options"
              >
                <span>⚙️</span> <span className="hidden sm:inline">Map Options</span>
              </button>
              {mapOptionsOpen && (
                <div className="absolute top-full right-0 mt-1.5 w-56 bg-gray-900/95 border border-white/10 rounded-xl shadow-2xl p-3 z-[9999] flex flex-col gap-2.5 backdrop-blur-md">
                  <label className="flex items-center gap-2 text-xs text-gray-200 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={mapOptions.showLabels}
                      onChange={(e) =>
                        setMapOptions({ ...mapOptions, showLabels: e.target.checked })
                      }
                    />
                    Show Pin Labels
                  </label>
                  <label className="flex items-center gap-2 text-xs text-gray-200 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={mapOptions.clusterPins}
                      onChange={(e) =>
                        setMapOptions({ ...mapOptions, clusterPins: e.target.checked })
                      }
                    />
                    Cluster Pins
                  </label>
                  <label className="flex items-center gap-2 text-xs text-gray-200 cursor-pointer pt-1.5 border-t border-white/10">
                    <input
                      type="checkbox"
                      checked={mapOptions.unlockAllPins}
                      onChange={(e) =>
                        setMapOptions({ ...mapOptions, unlockAllPins: e.target.checked })
                      }
                    />
                    <span
                      className={mapOptions.unlockAllPins ? 'text-amber-400 font-semibold' : ''}
                    >
                      {mapOptions.unlockAllPins ? '🔓 All Pins Unlocked' : '🔒 Lock All Pins'}
                    </span>
                  </label>
                </div>
              )}
            </div>

            <button
              type="button"
              className="ss-btn-ghost text-xs py-1.5 px-2.5 flex items-center gap-1 whitespace-nowrap shrink-0 min-h-[38px] cursor-pointer"
              onClick={toggleFullscreen}
              title={isFullscreen ? 'Exit Fullscreen' : 'Enter Fullscreen'}
              aria-label={isFullscreen ? 'Exit Fullscreen' : 'Enter Fullscreen'}
            >
              <span>{isFullscreen ? '⛶' : '🖵'}</span>{' '}
              <span className="hidden sm:inline">{isFullscreen ? 'Exit' : 'Fullscreen'}</span>
            </button>

            <button
              type="button"
              className="ss-btn-ghost text-xs py-1.5 px-2.5 flex items-center gap-1 whitespace-nowrap shrink-0 min-h-[38px] cursor-pointer"
              onClick={() => {
                void queryClient.invalidateQueries({ queryKey: ['events-list'] })
                void queryClient.invalidateQueries({ queryKey: ['insights-stats'] })
              }}
              title="Refresh All"
              aria-label="Refresh All"
            >
              <span>🔄</span> <span className="hidden sm:inline">Refresh</span>
            </button>

            <Link
              to="/events"
              className="ss-btn-ghost text-xs py-1.5 px-2.5 hidden sm:flex items-center gap-1 whitespace-nowrap shrink-0 min-h-[38px]"
              title="Incidents Hub"
            >
              <span>📋</span> Incidents Hub
            </Link>

            <Link
              to="/dashboard"
              className="ss-btn-ghost text-xs py-1.5 px-2.5 hidden sm:flex items-center gap-1 whitespace-nowrap shrink-0 min-h-[38px]"
              title="Audio Console"
            >
              <span>🎧</span> Audio Console
            </Link>
          </div>
        </div>

        {/* Mobile View Toggle Bar: Full width segmented control for < 1024px screens */}
        <div className="w-full lg:hidden pt-0.5" role="tablist" aria-label="Mobile view switcher">
          <div className="grid grid-cols-2 bg-white/5 p-1 rounded-xl border border-white/10 w-full gap-1">
            <button
              type="button"
              role="tab"
              aria-selected={activeTab === 'map'}
              className={`flex items-center justify-center gap-1.5 py-2 px-3 text-xs font-semibold rounded-lg transition min-h-[42px] cursor-pointer ${
                activeTab === 'map'
                  ? 'bg-indigo-600 text-white shadow-md'
                  : 'text-gray-400 hover:text-gray-200'
              }`}
              onClick={() => setActiveTab('map')}
            >
              <span>🗺️</span> <span>Map</span>
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={activeTab === 'feed'}
              className={`flex items-center justify-center gap-1.5 py-2 px-3 text-xs font-semibold rounded-lg transition min-h-[42px] cursor-pointer ${
                activeTab === 'feed'
                  ? 'bg-indigo-600 text-white shadow-md'
                  : 'text-gray-400 hover:text-gray-200'
              }`}
              onClick={() => setActiveTab('feed')}
            >
              <span>📋</span> <span>Feed ({filteredEvents.length})</span>
            </button>
          </div>
        </div>
      </header>

      {/* Main 2-Pane Body: Map on the Left/Center, Feed Sidebar on the Right */}
      <div className={`ss-cc-body ${activeTab === 'map' ? 'ss-cc-body--map' : 'ss-cc-body--feed'}`}>
        <CommandCenterMap
          events={filteredEvents}
          selectedEventId={selectedEventId}
          onSelectEvent={handleSelectEvent}
          onGeocodeEvent={handleGeocode}
          onRemoveGeocodeEvent={handleRemoveGeocode}
          onUpdateCoordinates={handleUpdateCoordinates}
          isPlacingPin={!!pinPlacementEventId}
          onMapClick={handleMapClickToPin}
          onCancelPlacePin={() => setPinPlacementEventId(null)}
          isGeocoding={geocodeMutation.isPending || setCoordinatesMutation.isPending}
          unlockAllPins={mapOptions.unlockAllPins}
          activeTab={activeTab}
        />

        <CommandCenterFeed
          events={filteredEvents}
          rawEvents={pipelineEvents}
          monitors={monitors}
          selectedEventId={selectedEventId}
          onSelectEvent={handleSelectEvent}
          onGeocodeEvent={handleGeocode}
          onUpdateCoordinates={handleUpdateCoordinates}
          onStartPlacePin={(id) => setPinPlacementEventId(id)}
          isGeocoding={geocodeMutation.isPending || setCoordinatesMutation.isPending}
          search={search}
          setSearch={setSearch}
          selectedMonitor={selectedMonitor}
          setSelectedMonitor={setSelectedMonitor}
          filterMode={filterMode}
          setFilterMode={setFilterMode}
          timeframe={timeframe}
          setTimeframe={setTimeframe}
        />
      </div>

      {/* Bottom Insights Telemetry Drawer */}
      <CommandCenterTelemetry
        events={pipelineEvents}
        liveCpm={liveCpm}
        insightsSummary={insightsQuery.data?.summary ?? null}
      />
    </div>
  )
}
