import { useEffect, useMemo, useRef, useState } from 'react'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { MapContainer, TileLayer, Marker, Popup, useMap, useMapEvents } from 'react-leaflet'
import { Link } from 'react-router-dom'
import type { PipelineEvent } from '@/pages/Events/IncidentsPage'
import { formatTimeOnly, splitBadgeEntries, typeDisplayFor } from '@/pages/Events/IncidentsPage'

interface CommandCenterMapProps {
  events: PipelineEvent[]
  selectedEventId: string | null
  onSelectEvent: (eventId: string) => void
  onGeocodeEvent?: (eventId: string) => void
  onRemoveGeocodeEvent?: (eventId: string) => void
  onUpdateCoordinates?: (
    eventId: string,
    lat: number,
    lng: number,
    address?: string,
    reverseLookup?: boolean,
  ) => Promise<void> | void
  isPlacingPin?: boolean
  onMapClick?: (lat: number, lng: number) => void
  onCancelPlacePin?: () => void
  isGeocoding?: boolean
  unlockAllPins?: boolean
  activeTab?: 'map' | 'feed'
}

function MapClickHandler({
  isPlacingPin,
  onMapClick,
}: {
  isPlacingPin?: boolean
  onMapClick?: (lat: number, lng: number) => void
}) {
  useMapEvents({
    click: (e) => {
      if (isPlacingPin && onMapClick) {
        onMapClick(e.latlng.lat, e.latlng.lng)
      }
    },
  })
  return null
}

/**
 * Ensures that the popup element is fully visible within the map container's bounds.
 * If any edge is clipped (e.g. top cut off above the map header), it smoothly pans the map
 * by the exact pixel delta needed so that the entire card is visible without scrollbars.
 */
export function ensurePopupInView(
  map: L.Map,
  popupEl: HTMLElement,
  options: { padding?: number; animate?: boolean } = {},
): boolean {
  const padding = options.padding ?? 20
  const container = map.getContainer()
  if (!container || !popupEl) return false

  const mapRect = container.getBoundingClientRect()
  const popupRect = popupEl.getBoundingClientRect()

  // Zero dimensions check (e.g. hidden tab during initial render)
  if (mapRect.width === 0 || mapRect.height === 0 || popupRect.width === 0 || popupRect.height === 0) {
    return false
  }

  let dx = 0
  let dy = 0

  // Vertical check
  if (popupRect.top < mapRect.top + padding) {
    dy = popupRect.top - (mapRect.top + padding)
  } else if (popupRect.bottom > mapRect.bottom - padding) {
    const headroomTop = Math.max(0, popupRect.top - (mapRect.top + padding))
    const overflowBottom = popupRect.bottom - (mapRect.bottom - padding)
    dy = Math.min(overflowBottom, headroomTop)
  }

  // Horizontal check
  if (popupRect.left < mapRect.left + padding) {
    dx = popupRect.left - (mapRect.left + padding)
  } else if (popupRect.right > mapRect.right - padding) {
    const headroomLeft = Math.max(0, popupRect.left - (mapRect.left + padding))
    const overflowRight = popupRect.right - (mapRect.right - padding)
    dx = Math.min(overflowRight, headroomLeft)
  }

  if (dx !== 0 || dy !== 0) {
    map.panBy([dx, dy], { animate: options.animate ?? true })
    return true
  }
  return false
}

/**
 * Controller component to automatically position the map so that the selected
 * event card and pin are fully visible in the screen/viewport without being cut off.
 */
function MapCardFitController({
  selectedEvent,
  markerRefs,
}: {
  selectedEvent: PipelineEvent | null
  markerRefs: React.MutableRefObject<Map<string, L.Marker>>
}) {
  const map = useMap()

  // Triggered when selectedEvent changes (e.g. from feed or pin selection)
  useEffect(() => {
    if (
      !selectedEvent ||
      typeof selectedEvent.latitude !== 'number' ||
      typeof selectedEvent.longitude !== 'number'
    ) {
      return
    }

    const eventId = selectedEvent.eventId
    const marker = markerRefs.current.get(eventId)
    const targetLatLng: [number, number] = [selectedEvent.latitude, selectedEvent.longitude]
    const targetZoom = Math.max(map.getZoom(), 15)

    // Center on target pin
    map.setView(targetLatLng, targetZoom)

    if (marker && !marker.isPopupOpen()) {
      marker.openPopup()
    }

    // Measure and ensure popup is fully in view
    const raf = requestAnimationFrame(() => {
      const popupEl = map.getContainer().querySelector<HTMLElement>('.leaflet-popup')
      if (popupEl) {
        ensurePopupInView(map, popupEl, { animate: true })
      }
    })

    // Safety timeout in case map container just transitioned to visible (e.g. mobile tab switch)
    const timer = setTimeout(() => {
      const popupEl = map.getContainer().querySelector<HTMLElement>('.leaflet-popup')
      if (popupEl) {
        ensurePopupInView(map, popupEl, { animate: true })
      }
    }, 120)

    return () => {
      cancelAnimationFrame(raf)
      clearTimeout(timer)
    }
  }, [selectedEvent, map, markerRefs])

  // Listen for popupopen events (e.g. when user clicks marker pin directly on the map)
  useEffect(() => {
    const onPopupOpen = (e: L.PopupEvent) => {
      requestAnimationFrame(() => {
        const popupEl = e.popup.getElement()
        if (popupEl) {
          ensurePopupInView(map, popupEl, { animate: true })
        }
      })
    }

    map.on('popupopen', onPopupOpen)
    return () => {
      map.off('popupopen', onPopupOpen)
    }
  }, [map])

  // Re-adjust view on map resize or orientation change
  useEffect(() => {
    const onResize = () => {
      const popupEl = map.getContainer().querySelector<HTMLElement>('.leaflet-popup')
      if (popupEl) {
        ensurePopupInView(map, popupEl, { animate: false })
      }
    }

    map.on('resize', onResize)
    return () => {
      map.off('resize', onResize)
    }
  }, [map])

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

function MapResizeInvalidator({ activeTab }: { activeTab?: 'map' | 'feed' }) {
  const map = useMap()
  useEffect(() => {
    if (activeTab === 'map' || !activeTab) {
      const timer = setTimeout(() => {
        map.invalidateSize()
      }, 100)
      return () => clearTimeout(timer)
    }
  }, [activeTab, map])

  useEffect(() => {
    const handleResize = () => {
      map.invalidateSize()
    }
    window.addEventListener('resize', handleResize)
    return () => window.removeEventListener('resize', handleResize)
  }, [map])

  return null
}

function getMarkerColor(
  eventType: string | null,
  broadcastType: string | null,
): {
  bg: string
  border: string
  pulse: string
  icon: string
} {
  const typeStr = (eventType || '').toLowerCase()
  const bcStr = (broadcastType || '').toLowerCase()

  if (
    typeStr.includes('fire') ||
    typeStr.includes('smoke') ||
    typeStr.includes('alarm') ||
    typeStr.includes('hazmat')
  ) {
    return { bg: '#ef4444', border: '#fca5a5', pulse: 'rgba(239, 68, 68, 0.4)', icon: '🔥' }
  }
  if (
    typeStr.includes('police') ||
    typeStr.includes('traffic') ||
    typeStr.includes('chase') ||
    bcStr.includes('attempt_to_locate')
  ) {
    return { bg: '#3b82f6', border: '#93c5fd', pulse: 'rgba(59, 130, 246, 0.4)', icon: '🚔' }
  }
  if (
    typeStr.includes('med') ||
    typeStr.includes('ems') ||
    typeStr.includes('injury') ||
    typeStr.includes('rescue')
  ) {
    return { bg: '#f59e0b', border: '#fcd34d', pulse: 'rgba(245, 158, 11, 0.4)', icon: '🚑' }
  }
  if (
    bcStr.includes('storm_warning') ||
    typeStr.includes('weather') ||
    typeStr.includes('tornado')
  ) {
    return { bg: '#8b5cf6', border: '#c4b5fd', pulse: 'rgba(139, 92, 246, 0.4)', icon: '⚠️' }
  }
  return { bg: '#06b6d4', border: '#67e8f9', pulse: 'rgba(6, 182, 212, 0.4)', icon: '📍' }
}

function createIncidentDivIcon(
  event: PipelineEvent,
  isSelected: boolean,
  isMostRecent: boolean,
  isAnimating: boolean,
  isEditable: boolean = false,
) {
  const color = getMarkerColor(event.eventType, event.broadcastType)

  const html = `
    <div class="ss-map-pin ${isSelected ? 'ss-map-pin--selected' : ''} ${isAnimating ? 'ss-map-pin--animating' : ''} ${isEditable ? 'ss-map-pin--editable' : ''}">
      ${isMostRecent ? `<div class="ss-map-pin-pulse" style="background: ${color.pulse};"></div>` : ''}
      <div class="ss-map-pin-circle" style="background: ${color.bg}; border-color: ${isEditable ? '#f59e0b' : isSelected ? '#eab308' : color.border};">
        <span>${isEditable ? '✋' : color.icon}</span>
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
  onUpdateCoordinates,
  isPlacingPin,
  onMapClick,
  onCancelPlacePin,
  isGeocoding,
  unlockAllPins = false,
  activeTab,
}: CommandCenterMapProps) {
  const markerRefs = useRef<Map<string, L.Marker>>(new Map())
  const prevSpans = useRef<Record<string, number>>({})
  const [animating, setAnimating] = useState<Record<string, number>>({})
  const [editableEventId, setEditableEventId] = useState<string | null>(null)

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
        {/* Standard OpenStreetMap tiles inverted via CSS for a free dark mode map without API keys */}
        <TileLayer
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          maxZoom={19}
          className="ss-map-tiles-dark"
        />

        <MapResizeInvalidator activeTab={activeTab} />
        <MapCardFitController selectedEvent={selectedEvent} markerRefs={markerRefs} />
        <MapBoundsFitter events={mappedEvents} />
        <MapClickHandler isPlacingPin={isPlacingPin} onMapClick={onMapClick} />

        {mappedEvents.map((ev) => {
          const isSelected = ev.eventId === selectedEventId
          const isMostRecent = ev.eventId === mostRecentEventId
          const isAnimating = !!animating[ev.eventId]
          const isEditable = Boolean(unlockAllPins || editableEventId === ev.eventId)
          const icon = createIncidentDivIcon(ev, isSelected, isMostRecent, isAnimating, isEditable)

          return (
            <Marker
              key={`marker-${ev.eventId}`}
              ref={(marker) => {
                if (marker) {
                  markerRefs.current.set(ev.eventId, marker)
                } else {
                  markerRefs.current.delete(ev.eventId)
                }
              }}
              position={[ev.latitude!, ev.longitude!]}
              icon={icon}
              draggable={isEditable}
              eventHandlers={{
                click: () => onSelectEvent(ev.eventId),
                dragend: (e) => {
                  const marker = e.target
                  const position = marker.getLatLng()
                  const confirmMsg = `Move pin for "${typeDisplayFor(ev)}" to this new location?\n\nLatitude: ${position.lat.toFixed(5)}\nLongitude: ${position.lng.toFixed(5)}\n\n(Address will be automatically updated and reverse-geocoded)`
                  if (window.confirm(confirmMsg)) {
                    if (onUpdateCoordinates) {
                      void onUpdateCoordinates(
                        ev.eventId,
                        position.lat,
                        position.lng,
                        undefined,
                        true,
                      )
                    }
                    setEditableEventId(null)
                  } else {
                    marker.setLatLng([ev.latitude!, ev.longitude!])
                  }
                },
              }}
            >
              <Popup
                className="ss-map-popup"
                autoPan={false}
                maxWidth={420}
                minWidth={280}
              >
                <div className="ss-map-card-popup p-3 sm:p-3.5 flex flex-col gap-2">
                  <div className="flex items-center justify-between gap-2 border-b border-white/10 pb-2 pr-6 shrink-0">
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
                      {ev.monitorName || 'Monitor'} ·{' '}
                      {typeof ev.spansAttached === 'number' ? ev.spansAttached : 1}{' '}
                      {(typeof ev.spansAttached === 'number' ? ev.spansAttached : 1) === 1
                        ? 'span'
                        : 'spans'}{' '}
                      · {formatTimeOnly(ev.incidentAt ?? ev.createdAt)}
                    </span>
                  </div>

                  <div className="shrink-0">
                    <h4 className="text-sm font-bold text-white leading-tight">
                      {typeDisplayFor(ev)}
                    </h4>
                    {ev.statusDetail && (
                      <p className="text-xs font-semibold text-indigo-300 mt-0.5">
                        {ev.statusDetail}
                      </p>
                    )}
                  </div>

                  <div className="bg-black/30 rounded p-2 border border-white/5 flex flex-col gap-1 text-xs shrink-0">
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
                    <div className="flex flex-wrap gap-1 items-center shrink-0">
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
                    <p className="text-xs text-gray-300 italic bg-white/[0.02] p-2 rounded border border-white/5 leading-relaxed">
                      &ldquo;{ev.summary || ev.originalTranscription}&rdquo;
                    </p>
                  )}

                  <Link
                    to={`/events?incident_id=${encodeURIComponent(ev.eventId)}`}
                    className="flex items-center justify-center gap-1.5 py-2 px-3 rounded-lg bg-indigo-600/30 hover:bg-indigo-600/50 text-indigo-200 hover:text-white border border-indigo-500/40 text-xs font-semibold transition text-center shadow-sm shrink-0 min-h-[38px]"
                    onClick={(e) => e.stopPropagation()}
                  >
                    <span>📋</span> Open in Incidents Hub &rarr;
                  </Link>

                  {isEditable ? (
                    <div className="flex items-center justify-between gap-1.5 text-[10px] text-amber-300 bg-amber-500/15 px-2.5 py-1.5 rounded border border-amber-500/30 shrink-0">
                      <span className="flex items-center gap-1 font-semibold">
                        <span>✋</span> Marker Unlocked: Drag to reposition
                      </span>
                      {editableEventId === ev.eventId && (
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation()
                            setEditableEventId(null)
                          }}
                          className="text-[10px] text-amber-200 hover:text-white underline font-bold"
                        >
                          Lock Pin
                        </button>
                      )}
                    </div>
                  ) : (
                    <div className="flex items-center justify-between gap-2 text-[10px] bg-white/5 px-2.5 py-1.5 rounded border border-white/10 shrink-0">
                      <span className="text-gray-400 flex items-center gap-1">
                        <span>🔒</span> Pin location locked
                      </span>
                      <button
                        type="button"
                        className="text-amber-400 hover:text-amber-300 font-semibold flex items-center gap-1 transition hover:underline"
                        onClick={(e) => {
                          e.stopPropagation()
                          setEditableEventId(ev.eventId)
                        }}
                        title="Unlock marker to move its location"
                      >
                        <span>✏️</span> Move Pin
                      </button>
                    </div>
                  )}

                  <div className="flex items-center justify-between gap-2 pt-1 border-t border-white/10 text-[11px] shrink-0">
                    <span className="text-gray-500 font-mono text-[10px]">
                      {ev.latitude?.toFixed(4)}, {ev.longitude?.toFixed(4)}
                    </span>
                    <div className="flex items-center gap-3">
                      {onRemoveGeocodeEvent && (
                        <button
                          type="button"
                          className="text-red-400 hover:text-red-300 font-medium underline transition min-h-[28px]"
                          onClick={(e) => {
                            e.stopPropagation()
                            if (
                              window.confirm(
                                'Are you sure you want to remove this pin from the map? (The incident will not be deleted from the database)',
                              )
                            ) {
                              onRemoveGeocodeEvent(ev.eventId)
                            }
                          }}
                        >
                          Remove Pin
                        </button>
                      )}
                      {onGeocodeEvent && (
                        <button
                          type="button"
                          className="text-indigo-400 hover:text-indigo-300 font-medium underline transition min-h-[28px]"
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

      {/* Floating Pin-Repositioning Mode Banner */}
      {editableEventId && (
        <div className="absolute top-3 left-1/2 -translate-x-1/2 z-[1000] w-[calc(100vw-2rem)] max-w-md bg-amber-950/95 border border-amber-400/60 shadow-2xl text-white px-3 py-2 rounded-xl flex items-center justify-between gap-2 backdrop-blur-md animate-pulse">
          <div className="flex items-center gap-2 min-w-0">
            <span className="text-base shrink-0">✋</span>
            <span className="text-xs font-semibold text-amber-200 truncate">
              Drag marker to reposition pin
            </span>
          </div>
          <button
            type="button"
            onClick={() => setEditableEventId(null)}
            className="text-xs bg-amber-500/30 hover:bg-amber-500/50 px-2.5 py-1 rounded text-white font-bold transition border border-amber-400/40 shrink-0 min-h-[32px] cursor-pointer"
          >
            Done
          </button>
        </div>
      )}

      {/* Floating Pin-Drop Mode Banner */}
      {isPlacingPin && (
        <div className="absolute top-3 left-1/2 -translate-x-1/2 z-[1000] w-[calc(100vw-2rem)] max-w-md bg-indigo-950/95 border border-indigo-400/60 shadow-2xl text-white px-3 py-2 rounded-xl flex items-center justify-between gap-2 backdrop-blur-md animate-pulse">
          <div className="flex items-center gap-2 min-w-0">
            <span className="text-base shrink-0">📍</span>
            <span className="text-xs font-semibold truncate">Click on map to drop pin</span>
          </div>
          {onCancelPlacePin && (
            <button
              type="button"
              onClick={onCancelPlacePin}
              className="text-xs bg-white/20 hover:bg-white/30 px-2.5 py-1 rounded text-white font-bold transition shrink-0 min-h-[32px] cursor-pointer"
            >
              Cancel
            </button>
          )}
        </div>
      )}

      {/* Floating Map Overlay Legend / Info */}
      <div className="absolute top-3 left-3 z-[400] flex flex-col gap-1 bg-gray-950/85 backdrop-blur-md px-2.5 py-1.5 sm:px-3 sm:py-2 rounded-lg border border-white/10 text-xs shadow-lg pointer-events-auto">
        <div className="flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
          <span className="font-semibold text-white text-[11px] sm:text-xs">Live Incident Map</span>
        </div>
        <div className="flex items-center gap-2 text-[10px] sm:text-[11px] text-gray-400">
          <span>{mappedEvents.length} Plotted</span>
          <span>·</span>
          <span>{events.length - mappedEvents.length} Unmapped</span>
        </div>
      </div>
    </div>
  )
}
