import { useEffect, useRef, useState, useCallback } from 'react'
import type { LogEntry, SearchFilters, TalkgroupEntry } from '@/types/insights'
import { insights } from '@/lib/insights'

function formatTime(ts: string) {
  return new Date(ts).toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' })
}

function formatDateShort(ts: string) {
  return new Date(ts).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
}

function formatBytes(bytes: number) {
  if (!bytes) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`
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
}

export function SearchTab({
  date,
  allTalkgroups,
  filters,
  onFiltersChange,
  onTalkgroupFilter,
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
          limit: f.hour ? '10000' : '100',
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
    onFiltersChange({ keyword: '', talkgroups: [], hour: '', sort: 'newest' })
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
      {/* Filter row */}
      <div className="mb-3 flex flex-wrap items-center gap-3">
        {/* Keyword */}
        <input
          type="text"
          value={filters.keyword}
          onChange={(e) => setKeyword(e.target.value)}
          placeholder="Search transcripts…"
          className="ss-input-search"
        />

        {/* Talkgroup multi-select */}
        <div ref={tgDropRef} className="relative">
          <button
            onClick={() => setTgOpen((o) => !o)}
            className="ss-btn-bare"
          >
            Talkgroups {filters.talkgroups.length > 0 && `(${filters.talkgroups.length})`}
          </button>
          {tgOpen && (
            <div className="ss-dd-panel">
              {sortedTgs.length === 0 ? (
                <p className="px-2 py-1 text-xs text-gray-500">No talkgroups</p>
              ) : (
                sortedTgs.map(({ talkgroup, count }) => (
                  <label
                    key={talkgroup}
                    className="ss-dd-item"
                  >
                    <input
                      type="checkbox"
                      checked={filters.talkgroups.includes(talkgroup)}
                      onChange={() => toggleTg(talkgroup)}
                      className="accent-indigo-500"
                    />
                    <span className="flex-1 truncate">{talkgroup}</span>
                    <span className="text-gray-600">({count})</span>
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
          className="ss-select"
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
          className="ss-select"
        >
          <option value="newest">Newest First</option>
          <option value="oldest">Oldest First</option>
          <option value="largest">Largest First</option>
          <option value="smallest">Smallest First</option>
          <option value="longest">Longest First</option>
          <option value="shortest">Shortest First</option>
        </select>

        <button
          onClick={clearFilters}
          className="ss-btn-filter-clear"
        >
          Clear
        </button>
      </div>

      {/* Active filter chips */}
      {hasFilters && (
        <div className="mb-3 flex flex-wrap items-center gap-2">
          <span className="text-xs text-gray-500">Active:</span>
          {filters.keyword && (
            <span className="ss-chip ss-chip-kw">
              Keyword: &quot;{filters.keyword}&quot;
            </span>
          )}
          {filters.talkgroups.length > 0 && (
            <span className="ss-chip ss-chip-tg">
              TG: {filters.talkgroups.join(', ')}
            </span>
          )}
          {filters.hour !== '' && (
            <span className="ss-chip ss-chip-hr">
              Hour: {hourLabel(parseInt(filters.hour))}
            </span>
          )}
        </div>
      )}

      {/* Results count */}
      <p className="mb-2 text-xs text-gray-500">
        {loading ? 'Searching…' : `${total} results`}
      </p>

      {/* Results list */}
      <div className="ss-rec-scroll">
        {results.length === 0 && !loading && (
          <p className="text-sm text-gray-500">
            {hasFilters ? 'No results found.' : 'Enter search criteria or click a chart bar to filter…'}
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
              {/* Play btn */}
              <button
                disabled={!hasAudio}
                onClick={() => toggleAudio(entry.id, entry.audio_path)}
                title={hasAudio ? (isPlaying ? 'Stop' : 'Play') : 'No audio saved'}
                className={`ss-play ${
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
              <div className="min-w-[60px] flex-shrink-0">
                <p className="text-xs text-gray-500">{formatTime(entry.timestamp)}</p>
                <p className="text-xs text-gray-700">{formatDateShort(entry.timestamp)}</p>
              </div>

              {/* Talkgroup chip */}
              <button
                onClick={() => addTg(entry.talkgroup || 'N/A')}
                title="Add as filter"
                className="ss-tg-btn"
              >
                {entry.talkgroup || 'N/A'}
              </button>

              {/* Transcript */}
              <p className="min-w-0 flex-1 leading-snug text-gray-300">
                {highlight(entry.transcript || '', filters.keyword)}
              </p>

              {/* Meta + actions */}
              <div className="flex flex-shrink-0 flex-col items-end gap-1 text-right">
                <div className="flex gap-1">
                  <button
                    onClick={() => copyResult(entry.talkgroup || 'N/A', entry.transcript || '')}
                    title="Copy"
                    className="ss-icon-btn"
                  >
                    📋
                  </button>
                  <button
                    disabled={!hasAudio}
                    onClick={() => downloadAudio(entry.audio_path, entry.id)}
                    title={hasAudio ? 'Download audio' : 'No audio'}
                    className={hasAudio ? 'ss-icon-btn' : 'ss-icon-btn--off'}
                  >
                    💾
                  </button>
                </div>
                <span className="text-xs text-gray-500">{(entry.duration || 0).toFixed(1)}s</span>
                <span className="text-xs text-gray-600">{formatBytes(entry.file_size || 0)}</span>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
