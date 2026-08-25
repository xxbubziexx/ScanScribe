import { useEffect, useMemo, useRef, useState } from 'react'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { MapContainer, TileLayer, Marker, Popup, useMap } from 'react-leaflet'
import type { PipelineEvent } from '@/pages/Events/IncidentsPage'
import { formatTimeOnly, splitBadgeEntries, typeDisplayFor } from '@/pages/Events/IncidentsPage'

interface CommandCenterMapProps {
  events: PipelineEvent[]
  selectedEventId: string | null
  onSelectEvent: (eventId: string) => void
  onGeocodeEvent?: (eventId: string) => void
  onRemoveGeocodeEvent?: (eventId: string) => void
  isGeocoding?: boolean
}

// Controller component to smoothly fly map to selected event coordinates
function MapFlyController({ selectedEvent }: { selectedEvent: PipelineEvent | null }) {
  const map = useMap()
  const lastFlyId = useRef<string | null>(null)

  useEffect(() => {
    if (!selectedEvent || typeof selectedEvent.latitude !== 'number' || typeof selectedEvent.longitude !== 'number') {
      return
    }
    if (lastFlyId.current !== selectedEvent.eventId) {
      lastFlyId.current = selectedEvent.eventId
      map.flyTo([selectedEvent.latitude, selectedEvent.longitude], Math.max(map.getZoom(), 15), {
        duration: 1.2,
      })
    }
  }, [selectedEvent, map])

  return null
}

// Automatically fit bounds of all mapped incidents on initial load
function MapBoundsFitter({ events }: { events: PipelineEvent[] }) {
  const map = useMap()
  const initialFitDone = useRef(false)

  useEffect(() => {
    if (initialFitDone.current || events.length === 0) return
    const validCoords = events
      .filter((e) => typeof e.latitude === 'number' && typeof e.longitude === 'number')
      .map((e) => [e.latitude!, e.longitude!] as [number, number])

    if (validCoords.length > 0) {
      initialFitDone.current = true
      const bounds = L.latLngBounds(validCoords)
      map.fitBounds(bounds, { padding: [50, 50], maxZoom: 14 })
    }
  }, [events, map])

  return null
}

function getMarkerColor(eventType: string | null, broadcastType: string | null): {
  bg: string
  border: string
  pulse: string
  icon: string
} {
  const typeStr = (eventType || '').toLowerCase()
  const bcStr = (broadcastType || '').toLowerCase()

  if (typeStr.includes('fire') || typeStr.includes('smoke') || typeStr.includes('alarm') || typeStr.includes('hazmat')) {
    return { bg: '#ef4444', border: '#fca5a5', pulse: 'rgba(239, 68, 68, 0.4)', icon: '🔥' }
  }
  if (typeStr.includes('police') || typeStr.includes('traffic') || typeStr.includes('chase') || bcStr.includes('attempt_to_locate')) {
    return { bg: '#3b82f6', border: '#93c5fd', pulse: 'rgba(59, 130, 246, 0.4)', icon: '🚔' }
  }
  if (typeStr.includes('med') || typeStr.includes('ems') || typeStr.includes('injury') || typeStr.includes('rescue')) {
    return { bg: '#f59e0b', border: '#fcd34d', pulse: 'rgba(245, 158, 11, 0.4)', icon: '🚑' }
  }
  if (bcStr.includes('storm_warning') || typeStr.includes('weather') || typeStr.includes('tornado')) {
    return { bg: '#8b5cf6', border: '#c4b5fd', pulse: 'rgba(139, 92, 246, 0.4)', icon: '⚠️' }
  }
  return { bg: '#06b6d4', border: '#67e8f9', pulse: 'rgba(6, 182, 212, 0.4)', icon: '📍' }
}

function createIncidentDivIcon(event: PipelineEvent, isSelected: boolean, isMostRecent: boolean, isAnimating: boolean) {
  const color = getMarkerColor(event.eventType, event.broadcastType)

  const html = `
    <div class="ss-map-pin ${isSelected ? 'ss-map-pin--selected' : ''} ${isAnimating ? 'ss-map-pin--animating' : ''}">
      ${isMostRecent ? `<div class="ss-map-pin-pulse" style="background: ${color.pulse};"></div>` : ''}
      <div class="ss-map-pin-circle" style="background: ${color.bg}; border-color: ${isSelected ? '#eab308' : color.border};">
        <span>${color.icon}</span>
      </div>
    </div>
  `

  return L.divIcon({
    html,
    className: 'ss-leaflet-div-icon',
    iconSize: [32, 32],
    iconAnchor: [16, 16],
    popupAnchor: [0, -18],
  })
}

export function CommandCenterMap({
  events,
  selectedEventId,
  onSelectEvent,
  onGeocodeEvent,
  onRemoveGeocodeEvent,
  isGeocoding,
}: CommandCenterMapProps) {

  const prevSpans = useRef<Record<string, number>>({})
  const [animating, setAnimating] = useState<Record<string, number>>({})

  useEffect(() => {
    let changed = false
    const newAnimating = { ...animating }
    const now = Date.now()

    for (const ev of events) {
      const prev = prevSpans.current[ev.eventId]
      if (prev !== undefined && ev.spansAttached > prev) {
        newAnimating[ev.eventId] = now + 2000
        changed = true
      }
      prevSpans.current[ev.eventId] = ev.spansAttached
    }

    if (changed) {
      setAnimating(newAnimating)
      setTimeout(() => {
        setAnimating((current) => {
          const cleaned = { ...current }
          const time = Date.now()
          let hasCleanup = false
          for (const key in cleaned) {
            if (time >= cleaned[key]) {
              delete cleaned[key]
              hasCleanup = true
            }
          }
          return hasCleanup ? cleaned : current
        })
      }, 2500)
    }
  }, [events])

  const mappedEvents = useMemo(
    () => events.filter((e) => typeof e.latitude === 'number' && typeof e.longitude === 'number'),
    [events],
  )

  const mostRecentEventId = useMemo(
    () => (mappedEvents.length > 0 ? mappedEvents[0].eventId : null),
    [mappedEvents],
  )

  const selectedEvent = useMemo(
    () => events.find((e) => e.eventId === selectedEventId) || null,
    [events, selectedEventId],
  )

  // Default fallback center (Continental US center or first event)
  const defaultCenter: [number, number] = useMemo(() => {
    if (mappedEvents.length > 0) {
      return [mappedEvents[0].latitude!, mappedEvents[0].longitude!]
    }
    return [41.8781, -87.6298] // Default Chicago
  }, [mappedEvents])

  return (
    <div className="ss-cc-map-container">
      <MapContainer
        center={defaultCenter}
        zoom={11}
        scrollWheelZoom={true}
        zoomControl={false}
        attributionControl={false}
      >
        {/* CartoDB Dark Matter tile layer for high-contrast tactical dark dashboard */}
        <TileLayer
          url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
          maxZoom={19}
          subdomains="abcd"
        />

        <MapFlyController selectedEvent={selectedEvent} />
        <MapBoundsFitter events={mappedEvents} />

        {mappedEvents.map((ev) => {
          const isSelected = ev.eventId === selectedEventId
          const isMostRecent = ev.eventId === mostRecentEventId
          const isAnimating = !!animating[ev.eventId]
          const icon = createIncidentDivIcon(ev, isSelected, isMostRecent, isAnimating)

          return (
            <Marker
              key={`marker-${ev.eventId}`}
              position={[ev.latitude!, ev.longitude!]}
              icon={icon}
              eventHandlers={{
                click: () => onSelectEvent(ev.eventId),
              }}
            >
              <Popup className="ss-map-popup">
                <div className="p-3.5 max-w-xs flex flex-col gap-2">
                  <div className="flex items-center justify-between gap-2 border-b border-white/10 pb-2 pr-5">
                    <span
                      className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wide ${
                        ev.status === 'open'
                          ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30'
                          : 'bg-gray-700/50 text-gray-400 border border-gray-600/30'
                      }`}
                    >
                      {ev.status}
                    </span>
                    <span className="text-[11px] font-medium text-gray-400">
                      {ev.monitorName || 'Monitor'} · {formatTimeOnly(ev.incidentAt ?? ev.createdAt)}
                    </span>
                  </div>

                  <div>
                    <h4 className="text-sm font-bold text-white leading-tight">
                      {typeDisplayFor(ev)}
                    </h4>
                    {ev.statusDetail && (
                      <p className="text-xs font-semibold text-indigo-300 mt-0.5">
                        {ev.statusDetail}
                      </p>
                    )}
                  </div>

                  <div className="bg-black/30 rounded p-2 border border-white/5 flex flex-col gap-1 text-xs">
                    <p className="font-semibold text-gray-200 flex items-center gap-1">
                      <span>📍</span> {ev.location || 'Unknown location'}
                    </p>
                    {ev.resolvedAddress && (
                      <p className="text-[11px] text-gray-400 leading-tight">
                        {ev.resolvedAddress}
                      </p>
                    )}
                  </div>

                  {splitBadgeEntries(ev.units).length > 0 && (
                    <div className="flex flex-wrap gap-1 items-center">
                      <span className="text-[10px] uppercase text-gray-500 font-bold">Units:</span>
                      {splitBadgeEntries(ev.units).map((u) => (
                        <span
                          key={u}
                          className="px-1.5 py-0.5 rounded bg-blue-500/20 text-blue-300 border border-blue-500/30 text-[10px] font-mono"
                        >
                          {u}
                        </span>
                      ))}
                    </div>
                  )}

                  {(ev.summary || ev.originalTranscription) && (
                    <p className="text-xs text-gray-300 italic bg-white/[0.02] p-1.5 rounded border border-white/5">
                      &ldquo;{ev.summary || ev.originalTranscription}&rdquo;
                    </p>
                  )}

                  <div className="flex items-center justify-between gap-2 pt-1 border-t border-white/10 text-[11px]">
                    <span className="text-gray-500 font-mono text-[10px]">
                      {ev.latitude?.toFixed(4)}, {ev.longitude?.toFixed(4)}
                    </span>
                    <div className="flex items-center gap-3">
                      {onRemoveGeocodeEvent && (
                        <button
                          type="button"
                          className="text-red-400 hover:text-red-300 font-medium underline transition"
                          onClick={(e) => {
                            e.stopPropagation()
                            onRemoveGeocodeEvent(ev.eventId)
                          }}
                        >
                          Remove Pin
                        </button>
                      )}
                      {onGeocodeEvent && (
                        <button
                          type="button"
                          className="text-indigo-400 hover:text-indigo-300 font-medium underline transition"
                          disabled={isGeocoding}
                          onClick={(e) => {
                            e.stopPropagation()
                            onGeocodeEvent(ev.eventId)
                          }}
                        >
                          {isGeocoding ? 'Resolving…' : 'Re-Geocode'}
                        </button>
                      )}
                    </div>
                  </div>
                </div>
              </Popup>
            </Marker>
          )
        })}
      </MapContainer>

      {/* Floating Map Overlay Legend / Info */}
      <div className="absolute top-3 left-3 z-[400] flex flex-col gap-1.5 bg-gray-950/85 backdrop-blur-md px-3 py-2 rounded-lg border border-white/10 text-xs shadow-lg pointer-events-auto">
        <div className="flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
          <span className="font-semibold text-white">Live Incident Map</span>
        </div>
        <div className="flex items-center gap-3 text-[11px] text-gray-400">
          <span>{mappedEvents.length} Plotted</span>
          <span>·</span>
          <span>{events.length - mappedEvents.length} Unmapped</span>
        </div>
      </div>
    </div>
  )
}
