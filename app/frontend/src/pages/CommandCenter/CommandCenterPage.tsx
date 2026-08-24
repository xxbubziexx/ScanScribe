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
import { toPipelineEvent } from '@/pages/Events/IncidentsPage'
import { CommandCenterMap } from './CommandCenterMap'
import { CommandCenterFeed } from './CommandCenterFeed'
import { CommandCenterTelemetry } from './CommandCenterTelemetry'

const WS_URL = `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}/ws`

export function CommandCenterPage() {
  const queryClient = useQueryClient()
  const { addToast } = useToast()
  
  const containerRef = useRef<HTMLDivElement>(null)
  const [isFullscreen, setIsFullscreen] = useState(false)

  const [selectedEventId, setSelectedEventId] = useState<string | null>(null)
  const [liveCpm, setLiveCpm] = useState<number | null>(null)

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

  // Fetch Events (Incidents)
  const eventsQuery = useQuery({
    queryKey: ['events-list', 'command-center'],
    queryFn: () => eventsApi.list({ limit: 200 }),
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
        addToast(`Address resolved: ${res.resolved_address || `${res.latitude}, ${res.longitude}`}`, 'success')
      } else {
        addToast(res.message || 'Address could not be geocoded', 'warning')
      }
      void queryClient.invalidateQueries({ queryKey: ['events-list'] })
    },
    onError: (e: unknown) => {
      addToast(errorMessage(e, 'Geocoding request failed'), 'error')
    },
  })

  const handleGeocode = useCallback(
    (eventId: string) => {
      geocodeMutation.mutate(eventId)
    },
    [geocodeMutation],
  )

  // Real-time WebSocket event handling
  const handleWsMessage = useCallback(
    (msg: WsMessage) => {
      if (msg.type === 'event_update') {
        // Optimistic / fast query invalidation for new/updated incidents
        void queryClient.invalidateQueries({ queryKey: ['events-list'] })
      } else if (msg.type === 'event_geocoded') {
        // When an event gets geocoded in background, refresh the list immediately
        void queryClient.invalidateQueries({ queryKey: ['events-list'] })
      }
    },
    [queryClient],
  )

  useWebSocket(WS_URL, handleWsMessage)

  // Transform raw event items into PipelineEvents with monitor names
  const rawItems: EventListItem[] = eventsQuery.data?.items ?? []
  const pipelineEvents: PipelineEvent[] = useMemo(() => {
    return rawItems.map((item) => {
      const pe = toPipelineEvent(item)
      pe.monitorName = monitorNameMap.get(pe.monitorId) || `Monitor #${pe.monitorId}`
      return pe
    })
  }, [rawItems, monitorNameMap])

  return (
    <div className={`ss-command-center ${isFullscreen ? 'ss-cc-fullscreen' : ''}`} ref={containerRef}>
      {/* Command Center Top Navigation Toolbar */}
      <header className="ss-cc-header">
        <div className="ss-cc-title-group">
          <h1 className="ss-cc-title">
            <span className="text-xl">🗺️</span> Command Center
          </h1>
          <div className="ss-cc-live-badge">
            <span className="ss-cc-live-dot"></span>
            <span>LIVE FEED</span>
          </div>
        </div>

        <div className="ss-cc-controls">
          <button
            type="button"
            className="ss-btn-ghost text-xs py-1 px-2.5 flex items-center gap-1"
            onClick={toggleFullscreen}
            title={isFullscreen ? "Exit Fullscreen" : "Enter Fullscreen"}
          >
            <span>{isFullscreen ? '⛶' : '🖵'}</span> {isFullscreen ? 'Exit Fullscreen' : 'Fullscreen'}
          </button>

          <button
            type="button"
            className="ss-btn-ghost text-xs py-1 px-2.5 flex items-center gap-1"
            onClick={() => {
              void queryClient.invalidateQueries({ queryKey: ['events-list'] })
              void queryClient.invalidateQueries({ queryKey: ['insights-stats'] })
            }}
            title="Refresh All"
          >
            <span>🔄</span> Refresh
          </button>

          <Link
            to="/events"
            className="ss-btn-ghost text-xs py-1 px-2.5 flex items-center gap-1"
          >
            <span>📋</span> Incidents Hub
          </Link>

          <Link
            to="/dashboard"
            className="ss-btn-ghost text-xs py-1 px-2.5 flex items-center gap-1"
          >
            <span>🎧</span> Audio Console
          </Link>
        </div>
      </header>

      {/* Main 2-Pane Body: Map on the Left/Center, Feed Sidebar on the Right */}
      <div className="ss-cc-body">
        <CommandCenterMap
          events={pipelineEvents}
          selectedEventId={selectedEventId}
          onSelectEvent={(id) => setSelectedEventId(id)}
          onGeocodeEvent={handleGeocode}
          isGeocoding={geocodeMutation.isPending}
        />

        <CommandCenterFeed
          events={pipelineEvents}
          monitors={monitors}
          selectedEventId={selectedEventId}
          onSelectEvent={(id) => setSelectedEventId(id)}
          onGeocodeEvent={handleGeocode}
          isGeocoding={geocodeMutation.isPending}
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
