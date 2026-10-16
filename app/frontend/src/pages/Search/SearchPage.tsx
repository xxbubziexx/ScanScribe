import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { insights } from '@/lib/insights'
import type { LogEntry, SearchFilters, TalkgroupEntry } from '@/types/insights'
import { DatabaseDateRangePicker } from '@/components/database/DatabaseDateRangePicker'
import { useAdminCapability } from '@/hooks/useAdminCapability'

function todayIso(): string {
  const d = new Date()
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}

function formatTime(ts: string) {
  return new Date(ts).toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

function formatDateShort(ts: string) {
  return new Date(ts).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}

function hourLabel(h: number) {
  const h12 = h === 0 ? 12 : h > 12 ? h - 12 : h
  return `${h12}:00 ${h < 12 ? 'AM' : 'PM'}`
}

function highlight(text: string, kw: string) {
  if (!kw || !text) return text
  const parts = text.split(new RegExp(`(${kw.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')})`, 'gi'))
  return parts.map((p, i) =>
    p.toLowerCase() === kw.toLowerCase() ? (
      <mark key={i} className="ss-highlight">
        {p}
      </mark>
    ) : (
      p
    ),
  )
}

function SearchIcon({ className = 'h-4 w-4' }: { className?: string }) {
  return (
    <svg viewBox="0 0 16 16" className={className} fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
      <circle cx="7" cy="7" r="4.5" />
      <path d="M10.5 10.5L14 14" strokeLinecap="round" />
    </svg>
  )
}

function PlayIcon({ className = 'h-3.5 w-3.5' }: { className?: string }) {
  return (
    <svg viewBox="0 0 16 16" className={className} fill="currentColor" aria-hidden="true">
      <path d="M4 3.5v9l8-4.5-8-4.5z" />
    </svg>
  )
}

function StopIcon({ className = 'h-3.5 w-3.5' }: { className?: string }) {
  return (
    <svg viewBox="0 0 16 16" className={className} fill="currentColor" aria-hidden="true">
      <rect x="3.5" y="3.5" width="9" height="9" rx="1" />
    </svg>
  )
}

function DownloadIcon({ className = 'h-4 w-4' }: { className?: string }) {
  return (
    <svg viewBox="0 0 16 16" className={className} fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
      <path d="M8 2.5v8m0 0l-3-3m3 3l3-3M3 13.5h10" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

function FilterResetIcon({ className = 'h-3.5 w-3.5' }: { className?: string }) {
  return (
    <svg viewBox="0 0 16 16" className={className} fill="none" stroke="currentColor" strokeWidth="1.4" aria-hidden="true">
      <path d="M2.5 8a5.5 5.5 0 1 0 1.2-3.4M2.5 3.5v2.8h2.8" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

export function SearchPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const { canAdmin } = useAdminCapability()
  const viewOnly = !canAdmin

  const initialDate = searchParams.get('date') || todayIso()
  const [dateFrom, setDateFrom] = useState(searchParams.get('date_from') || initialDate)
  const [dateTo, setDateTo] = useState(searchParams.get('date_to') || initialDate)

  const [filters, setFilters] = useState<SearchFilters>({
    keyword: searchParams.get('keyword') || '',
    talkgroups: searchParams.getAll('talkgroup'),
    hour: searchParams.get('hour') || '',
    sort: (searchParams.get('sort') as SearchFilters['sort']) || 'newest',
    limit: Number(searchParams.get('limit')) || 50,
  })

  const [results, setResults] = useState<LogEntry[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(false)
  const [tgSearch, setTgSearch] = useState('')
  const [tgOpen, setTgOpen] = useState(false)
  const tgDropRef = useRef<HTMLDivElement>(null)
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const audioRef = useRef<HTMLAudioElement | null>(null)
  const [playingId, setPlayingId] = useState<number | null>(null)

  // Active dates for the calendar dots
  const { data: datesData } = useQuery({
    queryKey: ['active-dates'],
    queryFn: () => insights.activeDates(),
    staleTime: 5 * 60 * 1000,
  })
  const activeDates = datesData?.dates ?? []

  // Talkgroups for the dropdown
  const { data: statsData } = useQuery({
    queryKey: ['insights-stats', dateFrom, dateTo],
    queryFn: () => insights.stats(dateFrom, 'daily', dateTo),
    staleTime: 60_000,
  })
  const allTalkgroups: TalkgroupEntry[] = statsData?.talkgroups_all ?? []

  const doSearch = useCallback(
    async (f: SearchFilters, from: string, to: string) => {
      setLoading(true)
      try {
        const params = new URLSearchParams({
          date: from,
          keyword: f.keyword,
          hour: f.hour,
          sort: f.sort,
          limit: String(f.limit ?? 50),
        })
        if (from && to && from !== to) {
          params.set('date_from', from)
          params.set('date_to', to)
        }
        f.talkgroups.forEach((tg) => params.append('talkgroup', tg))
        const data = await insights.search(params)
        setResults(data.results ?? [])
        setTotal(data.total ?? 0)
      } catch {
        setResults([])
        setTotal(0)
      } finally {
        setLoading(false)
      }
    },
    [],
  )

  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(() => {
      doSearch(filters, dateFrom, dateTo)
    }, 250)
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current)
    }
  }, [filters, dateFrom, dateTo, doSearch])

  // Sync with searchParams
  useEffect(() => {
    const params = new URLSearchParams()
    if (dateFrom) params.set('date_from', dateFrom)
    if (dateTo) params.set('date_to', dateTo)
    if (filters.keyword) params.set('keyword', filters.keyword)
    if (filters.hour) params.set('hour', filters.hour)
    if (filters.sort && filters.sort !== 'newest') params.set('sort', filters.sort)
    if (filters.limit && filters.limit !== 50) params.set('limit', String(filters.limit))
    filters.talkgroups.forEach((tg) => params.append('talkgroup', tg))
    setSearchParams(params, { replace: true })
  }, [dateFrom, dateTo, filters, setSearchParams])

  // Close TG dropdown on outside click
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (tgDropRef.current && !tgDropRef.current.contains(e.target as Node)) {
        setTgOpen(false)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  function toggleTg(tg: string) {
    const has = filters.talkgroups.includes(tg)
    setFilters((prev) => ({
      ...prev,
      talkgroups: has ? prev.talkgroups.filter((t) => t !== tg) : [...prev.talkgroups, tg],
    }))
  }

  function clearFilters() {
    setFilters({
      keyword: '',
      talkgroups: [],
      hour: '',
      sort: 'newest',
      limit: 50,
    })
  }

  function toggleAudio(id: number, path: string) {
    if (!path || path === 'file not saved') return
    const url = '/' + path.replace(/^\/+/, '')
    if (playingId === id && audioRef.current) {
      audioRef.current.pause()
      audioRef.current.currentTime = 0
      audioRef.current = null
      setPlayingId(null)
      return
    }
    if (audioRef.current) {
      audioRef.current.pause()
      audioRef.current = null
    }
    const a = new Audio(url)
    a.play()
      .then(() => {
        audioRef.current = a
        setPlayingId(id)
        a.onended = () => {
          setPlayingId(null)
          audioRef.current = null
        }
      })
      .catch(() => {
        setPlayingId(null)
        audioRef.current = null
      })
  }

  function exportCsv() {
    if (results.length === 0) return
    const rows = [
      ['ID', 'Timestamp', 'Talkgroup', 'Duration (s)', 'Transcript'],
      ...results.map((r) => [
        String(r.id),
        r.timestamp ? new Date(r.timestamp).toISOString() : '',
        r.talkgroup ?? '',
        String(r.duration ?? ''),
        `"${(r.transcript ?? '').replace(/"/g, '""')}"`,
      ]),
    ]
    const csv = rows.map((r) => r.join(',')).join('\n')
    const blob = new Blob([csv], { type: 'text/csv' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `scanscribe_search_${dateFrom}_${dateTo}.csv`
    a.click()
    URL.revokeObjectURL(url)
  }

  const filteredTgList = allTalkgroups.filter((tg) =>
    (tg.talkgroup ?? '').toLowerCase().includes(tgSearch.toLowerCase()),
  )

  const activeFilterCount =
    (filters.keyword ? 1 : 0) +
    filters.talkgroups.length +
    (filters.hour ? 1 : 0) +
    (filters.sort !== 'newest' ? 1 : 0)

  return (
    <div className="w-full space-y-4">
      {/* Search Header & Toolbar */}
      <div className="ss-glass-panel relative z-30 flex flex-col gap-4">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-white/10 pb-4">
          <div className="flex items-center gap-2">
            <SearchIcon className="h-5 w-5 text-indigo-400" />
            <h1 className="text-base font-semibold text-gray-100">Transcriptions Search & Investigation</h1>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <DatabaseDateRangePicker
              from={dateFrom}
              to={dateTo}
              activeDates={activeDates}
              onChange={(f, t) => {
                setDateFrom(f)
                setDateTo(t)
              }}
            />
            {!viewOnly && (
              <button
                type="button"
                onClick={exportCsv}
                disabled={results.length === 0}
                className="ss-btn-secondary inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium disabled:opacity-40"
                title="Export results to CSV"
              >
                <DownloadIcon className="h-3.5 w-3.5" />
                Export CSV
              </button>
            )}
          </div>
        </div>

        {/* Filter Controls Row */}
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {/* Keyword Search */}
          <div className="relative">
            <span className="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-3 text-gray-500">
              <SearchIcon className="h-3.5 w-3.5" />
            </span>
            <input
              type="text"
              placeholder="Search transcript text…"
              value={filters.keyword}
              onChange={(e) => setFilters((prev) => ({ ...prev, keyword: e.target.value }))}
              className="w-full rounded-lg border border-white/10 bg-black/40 py-2 pl-9 pr-8 text-xs text-gray-200 placeholder-gray-500 transition-colors focus:border-indigo-500 focus:outline-none"
            />
            {filters.keyword && (
              <button
                type="button"
                onClick={() => setFilters((prev) => ({ ...prev, keyword: '' }))}
                className="absolute inset-y-0 right-0 flex items-center pr-2.5 text-gray-500 hover:text-gray-300"
              >
                ✕
              </button>
            )}
          </div>

          {/* Talkgroup Filter Dropdown */}
          <div className="relative" ref={tgDropRef}>
            <button
              type="button"
              onClick={() => setTgOpen((v) => !v)}
              className="flex w-full items-center justify-between rounded-lg border border-white/10 bg-black/40 px-3 py-2 text-xs text-gray-200 hover:border-white/20"
            >
              <span className="truncate">
                {filters.talkgroups.length === 0
                  ? 'All Talkgroups'
                  : `${filters.talkgroups.length} Talkgroup${filters.talkgroups.length > 1 ? 's' : ''}`}
              </span>
              <span className="ml-2 text-gray-500">▾</span>
            </button>

            {tgOpen && (
              <div className="absolute left-0 top-full z-30 mt-1 max-h-64 w-72 overflow-y-auto rounded-lg border border-white/10 bg-gray-950 p-2 shadow-2xl">
                <input
                  type="text"
                  placeholder="Filter talkgroups…"
                  value={tgSearch}
                  onChange={(e) => setTgSearch(e.target.value)}
                  className="mb-2 w-full rounded border border-white/10 bg-black/50 px-2 py-1 text-xs text-gray-200 placeholder-gray-500 focus:outline-none"
                />
                <div className="space-y-0.5">
                  {filteredTgList.length === 0 ? (
                    <p className="py-2 text-center text-xs text-gray-500">No talkgroups found</p>
                  ) : (
                    filteredTgList.map((tg) => {
                      const name = tg.talkgroup ?? 'N/A'
                      const checked = filters.talkgroups.includes(name)
                      return (
                        <label
                          key={name}
                          className="flex cursor-pointer items-center justify-between rounded px-2 py-1 text-xs text-gray-300 hover:bg-white/5"
                        >
                          <div className="flex items-center gap-2">
                            <input
                              type="checkbox"
                              checked={checked}
                              onChange={() => toggleTg(name)}
                              className="rounded border-white/20 bg-black/40 text-indigo-500"
                            />
                            <span className="font-mono">{name}</span>
                          </div>
                          <span className="text-[10px] text-gray-500">{tg.count}</span>
                        </label>
                      )
                    })
                  )}
                </div>
              </div>
            )}
          </div>

          {/* Hour Filter */}
          <div>
            <select
              value={filters.hour}
              onChange={(e) => setFilters((prev) => ({ ...prev, hour: e.target.value }))}
              className="w-full rounded-lg border border-white/10 bg-black/40 px-3 py-2 text-xs text-gray-200 transition-colors focus:border-indigo-500 focus:outline-none"
            >
              <option value="">All Hours</option>
              {Array.from({ length: 24 }, (_, i) => (
                <option key={i} value={String(i)}>
                  {hourLabel(i)}
                </option>
              ))}
            </select>
          </div>

          {/* Sort & Limit */}
          <div className="flex items-center gap-2">
            <select
              value={filters.sort}
              onChange={(e) =>
                setFilters((prev) => ({ ...prev, sort: e.target.value as SearchFilters['sort'] }))
              }
              className="w-1/2 rounded-lg border border-white/10 bg-black/40 px-2.5 py-2 text-xs text-gray-200 focus:border-indigo-500 focus:outline-none"
            >
              <option value="newest">Newest first</option>
              <option value="oldest">Oldest first</option>
              <option value="longest">Longest duration</option>
              <option value="shortest">Shortest duration</option>
            </select>
            <select
              value={filters.limit}
              onChange={(e) => setFilters((prev) => ({ ...prev, limit: Number(e.target.value) }))}
              className="w-1/2 rounded-lg border border-white/10 bg-black/40 px-2.5 py-2 text-xs text-gray-200 focus:border-indigo-500 focus:outline-none"
            >
              <option value="25">25 items</option>
              <option value="50">50 items</option>
              <option value="100">100 items</option>
              <option value="200">200 items</option>
            </select>
          </div>
        </div>

        {/* Active Filters Badges & Count */}
        <div className="flex flex-wrap items-center justify-between gap-2 border-t border-white/5 pt-2 text-xs">
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="text-gray-400">
              Showing <strong className="text-gray-200">{results.length}</strong> of{' '}
              <strong className="text-gray-200">{total}</strong> transmissions
            </span>

            {filters.talkgroups.map((tg) => (
              <span
                key={tg}
                className="inline-flex items-center gap-1 rounded bg-indigo-500/20 px-2 py-0.5 text-[11px] font-medium text-indigo-300"
              >
                TG: {tg}
                <button
                  type="button"
                  onClick={() => toggleTg(tg)}
                  className="hover:text-white"
                  title="Remove talkgroup filter"
                >
                  ✕
                </button>
              </span>
            ))}

            {filters.hour && (
              <span className="inline-flex items-center gap-1 rounded bg-indigo-500/20 px-2 py-0.5 text-[11px] font-medium text-indigo-300">
                {hourLabel(Number(filters.hour))}
                <button
                  type="button"
                  onClick={() => setFilters((prev) => ({ ...prev, hour: '' }))}
                  className="hover:text-white"
                >
                  ✕
                </button>
              </span>
            )}
          </div>

          {activeFilterCount > 0 && (
            <button
              type="button"
              onClick={clearFilters}
              className="inline-flex items-center gap-1 text-[11px] text-gray-400 hover:text-gray-200"
            >
              <FilterResetIcon className="h-3 w-3" />
              Reset filters
            </button>
          )}
        </div>
      </div>

      {/* Results Feed */}
      <div className="space-y-2">
        {loading ? (
          <div className="ss-glass-panel py-12 text-center text-xs text-gray-500">
            Searching transmissions…
          </div>
        ) : results.length === 0 ? (
          <div className="ss-glass-panel py-12 text-center text-xs text-gray-500">
            No transmissions match your search criteria.
          </div>
        ) : (
          results.map((entry) => {
            const hasAudio = entry.audio_path && entry.audio_path !== 'file not saved'
            const isPlaying = playingId === entry.id
            const attached = entry.attached_events ?? []

            return (
              <div
                key={entry.id}
                className="group rounded-lg border border-white/10 bg-white/[0.02] p-3 transition-colors hover:border-white/20 hover:bg-white/[0.04]"
              >
                <div className="flex flex-wrap items-center justify-between gap-2 pb-1.5">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="rounded bg-white/10 px-2 py-0.5 font-mono text-[11px] font-semibold text-gray-300">
                      {entry.talkgroup ?? 'N/A'}
                    </span>
                    <span className="text-xs text-gray-400">
                      {entry.timestamp ? formatDateShort(entry.timestamp) : ''}{' '}
                      <span className="font-mono text-gray-300">
                        {entry.timestamp ? formatTime(entry.timestamp) : ''}
                      </span>
                    </span>
                    {entry.duration !== undefined && entry.duration !== null && (
                      <span className="text-[11px] text-gray-500">
                        {entry.duration.toFixed(1)}s
                      </span>
                    )}
                  </div>

                  <div className="flex items-center gap-2">
                    {attached.map((ev) => (
                      <Link
                        key={ev.id}
                        to={`/events?incident=${ev.id}`}
                        className="rounded border border-indigo-500/30 bg-indigo-500/10 px-2 py-0.5 text-[10px] font-medium text-indigo-300 hover:bg-indigo-500/20"
                        title={`Attached Event: ${ev.event_id}`}
                      >
                        Incident #{ev.event_id}
                      </Link>
                    ))}

                    {hasAudio && (
                      <button
                        type="button"
                        onClick={() => toggleAudio(entry.id, entry.audio_path)}
                        className={`inline-flex items-center gap-1 rounded px-2.5 py-1 text-xs font-medium transition-colors ${isPlaying
                            ? 'bg-amber-600 text-white'
                            : 'bg-indigo-600/30 text-indigo-200 hover:bg-indigo-600/50'
                          }`}
                        title={isPlaying ? 'Stop audio' : 'Play transmission audio'}
                      >
                        {isPlaying ? <StopIcon className="h-3 w-3" /> : <PlayIcon className="h-3 w-3" />}
                        <span>{isPlaying ? 'Stop' : 'Play'}</span>
                      </button>
                    )}
                  </div>
                </div>

                <p className="mt-1 text-xs leading-relaxed text-gray-200">
                  {highlight(entry.transcript, filters.keyword)}
                </p>
              </div>
            )
          })
        )}
      </div>
    </div>
  )
}
