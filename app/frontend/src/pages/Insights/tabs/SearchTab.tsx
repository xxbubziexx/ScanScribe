import { useEffect, useRef, useState, useCallback } from 'react'
import { Link } from 'react-router-dom'
import type { LogEntry, SearchFilters, TalkgroupEntry } from '@/types/insights'
import { insights } from '@/lib/insights'

function formatTime(ts: string) {
  return new Date(ts).toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' })
}

function formatDateShort(ts: string) {
  return new Date(ts).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
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

interface SearchTabProps {
  date: string
  allTalkgroups: TalkgroupEntry[]
  filters: SearchFilters
  onFiltersChange: (f: SearchFilters) => void
  onTalkgroupFilter: (tg: string) => void
  /** Hide copy / download / extra filters; keep play. */
  viewOnly?: boolean
}

export function SearchTab({
  date,
  allTalkgroups,
  filters,
  onFiltersChange,
  onTalkgroupFilter,
  viewOnly: _viewOnly = false,
}: SearchTabProps) {
  const [results, setResults] = useState<LogEntry[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(false)
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const [tgOpen, setTgOpen] = useState(false)
  const tgDropRef = useRef<HTMLDivElement>(null)
  const audioRef = useRef<HTMLAudioElement | null>(null)
  const [playingId, setPlayingId] = useState<number | null>(null)

  const doSearch = useCallback(
    async (f: SearchFilters) => {
      setLoading(true)
      try {
        const params = new URLSearchParams({
          date,
          keyword: f.keyword,
          hour: f.hour,
          sort: f.sort,
          limit: String(f.limit ?? 50),
        })
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
    [date],
  )

  // Re-run search when filters or date change (debounced for keyword)
  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(() => doSearch(filters), 300)
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current)
    }
  }, [filters, doSearch])

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

  function setKeyword(keyword: string) {
    onFiltersChange({ ...filters, keyword })
  }

  function toggleTg(tg: string) {
    const has = filters.talkgroups.includes(tg)
    onFiltersChange({
      ...filters,
      talkgroups: has ? filters.talkgroups.filter((t) => t !== tg) : [...filters.talkgroups, tg],
    })
  }

  function addTg(tg: string) {
    if (!filters.talkgroups.includes(tg)) {
      onFiltersChange({ ...filters, talkgroups: [...filters.talkgroups, tg] })
    }
    onTalkgroupFilter(tg)
  }

  function clearFilters() {
    onFiltersChange({ keyword: '', talkgroups: [], hour: '', sort: 'newest', limit: filters.limit ?? 50 })
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
    audioRef.current = a
    setPlayingId(id)
    a.onended = () => setPlayingId(null)
    a.onerror = () => setPlayingId(null)
    a.play().catch(() => setPlayingId(null))
  }

  function copyResult(tg: string, transcript: string) {
    const text = `[${tg}] "${transcript}"`
    navigator.clipboard?.writeText(text).catch(() => {
      const ta = document.createElement('textarea')
      ta.value = text
      ta.style.cssText = 'position:fixed;opacity:0'
      document.body.appendChild(ta)
      ta.select()
      document.execCommand('copy')
      document.body.removeChild(ta)
    })
  }

  function downloadAudio(path: string, id: number) {
    if (!path || path === 'file not saved') return
    const url = '/' + path.replace(/^\/+/, '')
    const name = path.split('/').pop() || `log_${id}`
    const a = document.createElement('a')
    a.href = url
    a.download = name
    a.rel = 'noopener'
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
  }

  const hasFilters = filters.keyword || filters.talkgroups.length > 0 || filters.hour

  const sortedTgs = [...allTalkgroups].sort((a, b) => b.count - a.count)

  return (
    <div>
      {/* Filter row - always available for all users */}
      <div className="mb-3 flex flex-col gap-2.5 sm:flex-row sm:flex-wrap sm:items-center sm:gap-3">
        {/* Keyword Search Input - Full width on mobile */}
        <div className="relative w-full sm:w-auto sm:flex-1 sm:max-w-md">
          <input
            type="text"
            value={filters.keyword}
            onChange={(e) => setKeyword(e.target.value)}
            placeholder="Search transcripts…"
            className="ss-input-search w-full min-h-[44px] text-sm pl-9 pr-9"
          />
          <span className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 text-sm pointer-events-none">
            🔍
          </span>
          {filters.keyword && (
            <button
              type="button"
              onClick={() => setKeyword('')}
              className="absolute right-2.5 top-1/2 -translate-y-1/2 text-gray-400 hover:text-white text-xs p-1 rounded min-h-[28px] min-w-[28px] flex items-center justify-center cursor-pointer"
              aria-label="Clear keyword"
            >
              ✕
            </button>
          )}
        </div>

        {/* Filter controls row */}
        <div className="flex flex-wrap items-center gap-2 w-full sm:w-auto">
          {/* Talkgroup multi-select */}
          <div ref={tgDropRef} className="relative flex-1 sm:flex-initial">
            <button
              type="button"
              onClick={() => setTgOpen((o) => !o)}
              className="ss-btn-bare min-h-[40px] w-full sm:w-auto justify-center"
            >
              Talkgroups {filters.talkgroups.length > 0 && `(${filters.talkgroups.length})`}
            </button>
            {tgOpen && (
              <div className="ss-dd-panel z-20 max-h-60 overflow-y-auto">
                {sortedTgs.length === 0 ? (
                  <p className="px-2 py-1 text-xs text-gray-500">No talkgroups</p>
                ) : (
                  sortedTgs.map(({ talkgroup, count }) => (
                    <label
                      key={talkgroup}
                      className="ss-dd-item min-h-[36px]"
                    >
                      <input
                        type="checkbox"
                        checked={filters.talkgroups.includes(talkgroup)}
                        onChange={() => toggleTg(talkgroup)}
                        className="accent-indigo-500 h-4 w-4"
                      />
                      <span className="flex-1 truncate">{talkgroup}</span>
                      <span className="text-gray-600 text-xs">({count})</span>
                    </label>
                  ))
                )}
              </div>
            )}
          </div>

          {/* Hour filter */}
          <select
            value={filters.hour}
            onChange={(e) => onFiltersChange({ ...filters, hour: e.target.value })}
            className="ss-select min-h-[40px] flex-1 sm:flex-initial"
            aria-label="Filter by hour"
          >
            <option value="">All Hours</option>
            {Array.from({ length: 24 }, (_, i) => (
              <option key={i} value={i}>
                {hourLabel(i)}
              </option>
            ))}
          </select>

          {/* Sort */}
          <select
            value={filters.sort}
            onChange={(e) => onFiltersChange({ ...filters, sort: e.target.value })}
            className="ss-select min-h-[40px] flex-1 sm:flex-initial"
            aria-label="Sort order"
          >
            <option value="newest">Newest First</option>
            <option value="oldest">Oldest First</option>
            <option value="largest">Largest First</option>
            <option value="smallest">Smallest First</option>
            <option value="longest">Longest First</option>
            <option value="shortest">Shortest First</option>
          </select>

          {/* Limiter */}
          <select
            value={filters.limit ?? 50}
            onChange={(e) => onFiltersChange({ ...filters, limit: Number(e.target.value) })}
            className="ss-select min-h-[40px]"
            title="Result limit"
            aria-label="Result limit"
          >
            {[20, 50, 100, 500].map((n) => (
              <option key={n} value={n}>
                {n} / page
              </option>
            ))}
          </select>

          {hasFilters && (
            <button
              type="button"
              onClick={clearFilters}
              className="ss-btn-filter-clear min-h-[40px] px-3 ml-auto sm:ml-0"
            >
              Clear
            </button>
          )}
        </div>
      </div>

      {/* Active filter chips */}
      {hasFilters && (
        <div className="mb-3 flex flex-wrap items-center gap-2">
          <span className="text-xs text-gray-500">Active:</span>
          {filters.keyword && (
            <span className="ss-chip ss-chip-kw inline-flex items-center gap-1">
              <span>Keyword: &quot;{filters.keyword}&quot;</span>
              <button
                type="button"
                onClick={() => setKeyword('')}
                className="text-gray-400 hover:text-white text-xs ml-0.5"
                title="Remove keyword filter"
              >
                ✕
              </button>
            </span>
          )}
          {filters.talkgroups.length > 0 && (
            <span className="ss-chip ss-chip-tg inline-flex items-center gap-1">
              <span>TG: {filters.talkgroups.join(', ')}</span>
              <button
                type="button"
                onClick={() => onFiltersChange({ ...filters, talkgroups: [] })}
                className="text-gray-400 hover:text-white text-xs ml-0.5"
                title="Remove talkgroup filter"
              >
                ✕
              </button>
            </span>
          )}
          {filters.hour !== '' && (
            <span className="ss-chip ss-chip-hr inline-flex items-center gap-1">
              <span>Hour: {hourLabel(parseInt(filters.hour))}</span>
              <button
                type="button"
                onClick={() => onFiltersChange({ ...filters, hour: '' })}
                className="text-gray-400 hover:text-white text-xs ml-0.5"
                title="Remove hour filter"
              >
                ✕
              </button>
            </span>
          )}
        </div>
      )}

      {/* Results count */}
      <p className="mb-2 text-xs text-gray-500">
        {loading
          ? 'Searching…'
          : total > results.length
            ? `Showing ${results.length} of ${total.toLocaleString()} results`
            : `${total.toLocaleString()} results`}
      </p>

      {/* Results list */}
      <div className="ss-search-scroll">
        {results.length === 0 && !loading && (
          <p className="text-sm text-gray-500 py-6 text-center">
            {hasFilters
              ? 'No results found matching your criteria.'
              : 'Enter search keywords or select filters above…'}
          </p>
        )}
        {results.map((entry) => {
          const hasAudio = !!entry.audio_path && entry.audio_path !== 'file not saved'
          const isPlaying = playingId === entry.id

          return (
            <div
              key={entry.id}
              className="ss-search-result"
            >
              {/* Card Header Row: Controls, Metadata, Badges, and Actions */}
              <div className="flex flex-wrap items-center justify-between gap-2 w-full">
                <div className="flex items-center gap-2 min-w-0 flex-wrap">
                  {/* Play / Stop Button */}
                  <button
                    type="button"
                    disabled={!hasAudio}
                    onClick={() => toggleAudio(entry.id, entry.audio_path)}
                    title={hasAudio ? (isPlaying ? 'Stop' : 'Play audio') : 'No audio saved'}
                    className={`ss-play min-h-[36px] min-w-[36px] cursor-pointer ${
                      hasAudio
                        ? isPlaying
                          ? 'ss-play--on'
                          : 'ss-play--idle'
                        : 'ss-play--off'
                    }`}
                  >
                    <span className="text-xs text-white">{isPlaying ? '■' : '▶'}</span>
                  </button>

                  {/* Timestamp */}
                  <div className="min-w-[52px] flex-shrink-0 text-left">
                    <p className="text-xs font-medium text-gray-300">{formatTime(entry.timestamp)}</p>
                    <p className="text-[10px] text-gray-500">{formatDateShort(entry.timestamp)}</p>
                  </div>

                  {/* Talkgroup Badge */}
                  <button
                    type="button"
                    onClick={() => addTg(entry.talkgroup || 'N/A')}
                    title="Click to filter by talkgroup"
                    className="ss-tg-btn text-xs py-1 px-2.5 max-w-[170px] truncate cursor-pointer"
                  >
                    {entry.talkgroup || 'N/A'}
                  </button>

                  {/* Attached Event Badges */}
                  {entry.attached_events && entry.attached_events.length > 0 && (
                    <div className="flex flex-shrink-0 flex-wrap items-center gap-1.5">
                      {entry.attached_events.map((ev) => {
                        const isOpen = ev.status === 'open'
                        return (
                          <Link
                            key={ev.id || ev.event_id}
                            to={`/events?incident_id=${encodeURIComponent(ev.event_id)}${isOpen ? '' : '&status=all'}`}
                            onClick={(e) => e.stopPropagation()}
                            className={`ss-attached-badge ${
                              isOpen ? 'ss-attached-badge--open' : 'ss-attached-badge--closed'
                            }`}
                            title={`Attached to ${isOpen ? 'open' : 'closed'} event: ${ev.event_type || ev.event_id}`}
                          >
                            <span
                              className={`h-1.5 w-1.5 rounded-full ${
                                isOpen ? 'bg-amber-400 animate-pulse' : 'bg-gray-400'
                              }`}
                            />
                            <span className="whitespace-nowrap">attached</span>
                            <span className="text-[10px] opacity-75 font-mono uppercase">
                              ({ev.status || 'open'})
                            </span>
                          </Link>
                        )
                      })}
                    </div>
                  )}
                </div>

                {/* Right side actions and audio duration */}
                <div className="flex items-center gap-2 flex-shrink-0 ml-auto">
                  <button
                    type="button"
                    onClick={() => copyResult(entry.talkgroup || 'N/A', entry.transcript || '')}
                    title="Copy transcript"
                    className="ss-icon-btn p-1.5 min-h-[32px] min-w-[32px] flex items-center justify-center rounded hover:bg-white/5 cursor-pointer"
                  >
                    📋
                  </button>
                  {hasAudio && (
                    <button
                      type="button"
                      onClick={() => downloadAudio(entry.audio_path, entry.id)}
                      title="Download audio"
                      className="ss-icon-btn p-1.5 min-h-[32px] min-w-[32px] flex items-center justify-center rounded hover:bg-white/5 cursor-pointer"
                    >
                      💾
                    </button>
                  )}
                  <span className="text-xs font-mono text-gray-400">
                    {(entry.duration || 0).toFixed(1)}s
                  </span>
                </div>
              </div>

              {/* Full-width transcript body */}
              <p className="text-[13px] sm:text-sm text-gray-200 leading-relaxed break-words font-normal mt-1 pl-1">
                {highlight(entry.transcript || '', filters.keyword)}
              </p>
            </div>
          )
        })}
      </div>
    </div>
  )
}
