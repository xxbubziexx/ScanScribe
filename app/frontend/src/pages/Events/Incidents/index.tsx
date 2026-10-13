import { useCallback, useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { downloadEventsExportHeaders, eventsApi } from '@/lib/events'
import { errorMessage } from '@/types/api'
import { useToast } from '@/context/ToastContext'
import { useAdminCapability } from '@/hooks/useAdminCapability'
import type { MonitorResponse } from '@/types/events'

import type { DetailTab } from './utils/incidentFormatters'
import {
  formatCountdown,
  toDetailEvent,
  toPipelineEvent,
  typeDisplayFor,
} from './utils/incidentFormatters'
import { EventListCard } from './components/EventListCard'
import { OpenRouterRateLimitBanner } from './components/OpenRouterRateLimitBanner'
import { EventDetailContent } from './components/EventDetailContent'

export function EventsIncidentsPage() {
  const queryClient = useQueryClient()
  const { addToast } = useToast()
  const { canAdmin } = useAdminCapability()
  const [searchParams, setSearchParams] = useSearchParams()
  const [query, setQuery] = useState('')
  const [monitor, setMonitor] = useState<number | 'all'>('all')
  const [status, setStatus] = useState<'all' | 'open' | 'closed'>(() => {
    const s = searchParams.get('status')
    if (s === 'all' || s === 'open' || s === 'closed') return s
    return 'open'
  })

  useEffect(() => {
    const s = searchParams.get('status')
    if (s === 'all' || s === 'open' || s === 'closed') {
      setStatus(s)
    }
  }, [searchParams])
  const [cardCount, setCardCount] = useState<number>(50)
  const [activeTab, setActiveTab] = useState<DetailTab>('event-thread')

  const [isDesktop, setIsDesktop] = useState(() =>
    typeof window !== 'undefined' ? window.matchMedia('(min-width: 1024px)').matches : false,
  )

  useEffect(() => {
    if (typeof window === 'undefined') return
    const mq = window.matchMedia('(min-width: 1024px)')
    const onChange = () => setIsDesktop(mq.matches)
    mq.addEventListener('change', onChange)
    return () => mq.removeEventListener('change', onChange)
  }, [])

  const monitorsQuery = useQuery({
    queryKey: ['events-monitors'],
    queryFn: () => eventsApi.monitors(),
    staleTime: 60_000,
  })

  const listQuery = useQuery({
    queryKey: ['events-list', monitor, status, cardCount],
    queryFn: () =>
      eventsApi.list({
        monitorId: monitor === 'all' ? undefined : monitor,
        status: status === 'all' ? undefined : status,
        limit: cardCount,
        offset: 0,
      }),
    refetchInterval: 10_000,
    refetchIntervalInBackground: true,
  })

  const rateLimitQuery = useQuery({
    queryKey: ['events-rate-limit-status'],
    queryFn: () => eventsApi.rateLimitStatus(),
    refetchInterval: 10_000,
    refetchIntervalInBackground: true,
  })

  const events = useMemo(() => {
    const items = listQuery.data?.items ?? []
    const byMonitor = new Map<number, string>((monitorsQuery.data ?? []).map((m) => [m.id, m.name]))
    return items.map((item) => {
      const e = toPipelineEvent(item)
      return { ...e, monitorName: byMonitor.get(e.monitorId) || `Monitor ${e.monitorId}` }
    })
  }, [listQuery.data?.items, monitorsQuery.data])

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!q.length) return events
    return events.filter((event) => {
      const hay = [
        event.eventId,
        typeDisplayFor(event),
        event.summary ?? '',
        event.location ?? '',
        event.units ?? '',
        event.talkgroup,
        event.statusDetail ?? '',
        event.eventType ?? '',
        event.originalTranscription ?? '',
        event.monitorName,
        String(event.spansAttached),
      ]
        .join('\n')
        .toLowerCase()
      return hay.includes(q)
    })
  }, [events, query])

  const urlEventId = searchParams.get('incident_id') || searchParams.get('event_id') || ''

  const selectedId = useMemo(() => {
    if (urlEventId) return urlEventId
    if (isDesktop && filtered.length > 0) return filtered[0].eventId
    return ''
  }, [urlEventId, isDesktop, filtered])

  const selectEvent = useCallback(
    (eventId: string) => {
      setSearchParams({ incident_id: eventId }, { replace: true })
    },
    [setSearchParams],
  )

  const clearSelectedEvent = useCallback(() => {
    setSearchParams({}, { replace: true })
  }, [setSearchParams])

  const selectedListEvent = useMemo(
    () => (selectedId ? filtered.find((e) => e.eventId === selectedId) ?? null : null),
    [filtered, selectedId],
  )

  const detailQuery = useQuery({
    queryKey: ['events-detail', selectedId],
    queryFn: () => eventsApi.detail(selectedId),
    enabled: !!selectedId,
    refetchInterval: 10_000,
    refetchIntervalInBackground: true,
  })

  const selected = useMemo(() => {
    if (!selectedId) return null
    if (!selectedListEvent) {
      if (detailQuery.data) return toDetailEvent(detailQuery.data, null)
      return null
    }
    if (!detailQuery.data) return selectedListEvent
    return toDetailEvent(detailQuery.data, selectedListEvent)
  }, [selectedListEvent, detailQuery.data, selectedId])

  useEffect(() => {
    if (!selected || isDesktop) return
    document.body.style.overflow = 'hidden'
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        clearSelectedEvent()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => {
      document.body.style.overflow = ''
      window.removeEventListener('keydown', onKey)
    }
  }, [selected, isDesktop, clearSelectedEvent])

  const openInView = useMemo(
    () => filtered.reduce((n, e) => n + (e.status === 'open' ? 1 : 0), 0),
    [filtered],
  )

  const downloadCsv = async () => {
    await downloadEventsExportHeaders({
      monitorId: monitor === 'all' ? undefined : monitor,
      status: status === 'all' ? undefined : status,
    })
  }

  const spanLinks = useMemo(
    () => detailQuery.data?.transcripts ?? [],
    [detailQuery.data?.transcripts],
  )

  const closeMutation = useMutation({
    mutationFn: (eventId: string) => eventsApi.close(eventId),
    onSuccess: () => {
      addToast('Event closed', 'success')
      void queryClient.invalidateQueries({ queryKey: ['events-list'] })
      void queryClient.invalidateQueries({ queryKey: ['events-detail', selectedId] })
    },
    onError: (e: unknown) => addToast(errorMessage(e, 'Failed to close event'), 'error'),
  })

  const deleteMutation = useMutation({
    mutationFn: (eventId: string) => eventsApi.remove(eventId),
    onSuccess: () => {
      addToast('Event deleted', 'success')
      clearSelectedEvent()
      void queryClient.invalidateQueries({ queryKey: ['events-list'] })
    },
    onError: (e: unknown) => addToast(errorMessage(e, 'Failed to delete event'), 'error'),
  })

  const summarizeMutation = useMutation({
    mutationFn: (eventId: string) => eventsApi.summarize(eventId),
    onSuccess: (data) => {
      addToast('Generated updated event summary from attachments', 'success')
      void queryClient.invalidateQueries({ queryKey: ['events-list'] })
      void queryClient.invalidateQueries({ queryKey: ['events-detail', data.event_id] })
    },
    onError: (e: unknown) => addToast(errorMessage(e, 'Failed to generate event summary'), 'error'),
  })

  return (
    <div className="ss-events-page">
      <div className="ss-events-topbar">
        <h1 className="ss-events-title">Incidents &amp; broadcasts</h1>
        <div className="ss-events-live">
          <span className="ss-events-rate">{listQuery.isFetching ? 'Refreshing…' : 'Live'}</span>
          <span className="ss-events-pill-tiny">{openInView} open in view</span>
          {rateLimitQuery.data?.is_paused_waiting_start ? (
            <span
              className="ss-events-pill-rate-limit cursor-pointer"
              title={
                rateLimitQuery.data.reason || 'Auto-start disabled: restart ScanScribe to resume'
              }
              onClick={() => void rateLimitQuery.refetch()}
            >
              ⏸️ Router Paused (Auto-Start Off)
            </span>
          ) : rateLimitQuery.data?.is_rate_limited ? (
            <span
              className="ss-events-pill-rate-limit cursor-pointer"
              title={
                rateLimitQuery.data.reason ||
                'OpenRouter rate limit timeout active — click to check now'
              }
              onClick={() => void rateLimitQuery.refetch()}
            >
              ⏳ Rate Limited (T-
              {formatCountdown(Math.ceil(rateLimitQuery.data.seconds_remaining ?? 0))})
            </span>
          ) : (
            <span className="ss-events-pill-ok" title="OpenRouter AI router is operational">
              ● Router Active
            </span>
          )}
          <button
            type="button"
            className="ss-btn-ghost"
            onClick={() => {
              void listQuery.refetch()
              if (selectedId) void detailQuery.refetch()
            }}
          >
            Refresh
          </button>
          <button type="button" className="ss-btn-ghost" onClick={() => void downloadCsv()}>
            Download CSV
          </button>
        </div>
      </div>
      <p className="ss-events-sub">
        Monitored radio / scanner pipeline: monitors (departments), span-linked transcripts, and
        event headers from the events service — not application error logs.
      </p>

      <OpenRouterRateLimitBanner />

      <div className="ss-events-filters">
        <input
          type="search"
          className="ss-input"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search id, type, talkgroup, location, units, summary…"
        />
        <select
          className="ss-select"
          value={monitor === 'all' ? 'all' : String(monitor)}
          onChange={(e) => {
            const v = e.target.value
            setMonitor(v === 'all' ? 'all' : Number(v))
          }}
        >
          <option value="all">All monitors (departments)</option>
          {(monitorsQuery.data ?? []).map((m: MonitorResponse) => (
            <option key={m.id} value={m.id}>
              {m.name}
            </option>
          ))}
        </select>
        <select
          className="ss-select"
          value={status}
          onChange={(e) => setStatus(e.target.value as 'all' | 'open' | 'closed')}
        >
          <option value="all">All statuses</option>
          <option value="open">Open</option>
          <option value="closed">Closed</option>
        </select>
        <button
          type="button"
          className="ss-btn-ghost"
          onClick={() => {
            setQuery('')
            setStatus('all')
            setMonitor('all')
          }}
        >
          Clear
        </button>
      </div>

      <div className="ss-events-shell">
        <section className="ss-events-list-pane" aria-label="Event list">
          <div className="ss-events-pane-head">
            <span>{filtered.length} shown</span>
            <div className="ss-events-pane-head-controls">
              <label className="ss-events-pane-head-label" htmlFor="events-card-count">
                Cards
              </label>
              <select
                id="events-card-count"
                className="ss-select h-8 min-w-[5rem] text-xs"
                value={String(cardCount)}
                onChange={(e) => setCardCount(Number(e.target.value))}
              >
                {[20, 50, 100, 200].map((n) => (
                  <option key={n} value={n}>
                    {n}
                  </option>
                ))}
              </select>
              <span className="text-gray-500">Newest (created) first</span>
            </div>
          </div>
          {listQuery.isError && (
            <p className="ss-form-error px-4 py-2">
              {errorMessage(listQuery.error, 'Failed to load events')}
            </p>
          )}
          {filtered.length === 0 ? (
            <p className="ss-empty not-italic">No events match current filters.</p>
          ) : (
            <ul className="ss-events-list">
              {filtered.map((event) => {
                const active = selectedId === event.eventId
                return (
                  <li
                    key={event.eventId}
                    className={
                      active
                        ? 'ss-events-row-item ss-events-row-item--active'
                        : 'ss-events-row-item'
                    }
                  >
                    <EventListCard
                      event={event}
                      active={active}
                      onSelect={() => selectEvent(event.eventId)}
                    />
                  </li>
                )
              })}
            </ul>
          )}
        </section>

        {/* Mobile Detail Modal / Sheet (< 1024px) */}
        {!isDesktop && selected && (
          <div
            className="lg:hidden fixed inset-0 z-50 flex flex-col bg-[#0f1117] pt-[env(safe-area-inset-top,0px)] pb-[env(safe-area-inset-bottom,0px)]"
            style={{ backgroundColor: '#0f1117' }}
            role="dialog"
            aria-modal="true"
            aria-label="Incident details"
          >
            <div className="flex items-center justify-between px-3 py-2.5 border-b border-white/10 bg-[#141821] shrink-0 min-h-[56px]">
              <button
                type="button"
                className="flex items-center gap-1.5 text-xs font-semibold text-indigo-300 hover:text-white transition py-2 px-3 rounded-lg hover:bg-white/10 bg-white/5 border border-white/10 min-h-[44px] cursor-pointer"
                onClick={clearSelectedEvent}
              >
                <span className="text-base">←</span>
                <span>Back to Incidents</span>
              </button>
              <div className="flex items-center gap-2 min-w-0">
                <span className="font-mono text-[11px] text-gray-400 truncate max-w-[120px]">
                  {selected.eventId}
                </span>
                <span
                  className={`capitalize px-2 py-0.5 rounded text-[11px] font-semibold ${
                    selected.status.toLowerCase() === 'open'
                      ? 'bg-green-500/20 text-green-400 border border-green-500/30'
                      : 'bg-red-500/20 text-red-400 border border-red-500/30'
                  }`}
                >
                  {selected.status}
                </span>
              </div>
            </div>

            <div className="flex-1 overflow-y-auto min-h-0">
              <EventDetailContent
                selected={selected}
                activeTab={activeTab}
                setActiveTab={setActiveTab}
                closeMutation={closeMutation}
                deleteMutation={deleteMutation}
                summarizeMutation={summarizeMutation}
                detailQuery={detailQuery}
                spanLinks={spanLinks}
                canAdmin={canAdmin}
              />
            </div>
          </div>
        )}

        {/* Desktop Detail Pane (>= 1024px) */}
        <section className="ss-events-detail-pane hidden lg:block" aria-label="Event detail">
          <div className="ss-events-pane-head">
            <span>Incident / broadcast</span>
            <span className="font-mono text-xs text-gray-500">{selected?.eventId ?? '—'}</span>
          </div>

          {!selected ? (
            <p className="ss-empty not-italic">Select an event on the left.</p>
          ) : (
            <EventDetailContent
              selected={selected}
              activeTab={activeTab}
              setActiveTab={setActiveTab}
              closeMutation={closeMutation}
              deleteMutation={deleteMutation}
              summarizeMutation={summarizeMutation}
              detailQuery={detailQuery}
              spanLinks={spanLinks}
              canAdmin={canAdmin}
            />
          )}
        </section>
      </div>
    </div>
  )
}
