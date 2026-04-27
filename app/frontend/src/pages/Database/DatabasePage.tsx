import { Fragment, useCallback, useEffect, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useAuth } from '@/context/AuthContext'
import { useToast } from '@/context/ToastContext'
import { buildListParams, downloadLogsExport, logsApi } from '@/lib/logs'
import { DatabaseDateRangePicker } from '@/components/database/DatabaseDateRangePicker'
import { errorMessage } from '@/types/api'
import type { LogListEntry, LogsSortBy } from '@/types/logs'

function formatBytes(bytes: number) {
  if (!bytes) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return `${parseFloat((bytes / k ** i).toFixed(1))} ${sizes[i]}`
}

const SORT_OPTIONS: { value: LogsSortBy; label: string }[] = [
  { value: 'timestamp_desc', label: 'Newest first' },
  { value: 'timestamp_asc', label: 'Oldest first' },
  { value: 'filename', label: 'Filename' },
  { value: 'talkgroup', label: 'Talkgroup' },
]

const PAGE_SIZES = [25, 50, 100] as const

export function DatabasePage() {
  const { user } = useAuth()
  const { addToast } = useToast()
  const queryClient = useQueryClient()
  const isAdmin = user?.is_admin === true

  const [searchInput, setSearchInput] = useState('')
  const [debouncedSearch, setDebouncedSearch] = useState('')

  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')

  const activeDatesQuery = useQuery({
    queryKey: ['database-active-dates'],
    queryFn: () => logsApi.activeDates(),
    staleTime: 5 * 60_000,
  })
  const activeDateList = activeDatesQuery.data?.dates
  const [sortBy, setSortBy] = useState<LogsSortBy>('timestamp_desc')
  const [pageSize, setPageSize] = useState(50)
  const [page, setPage] = useState(1)
  const [expandedId, setExpandedId] = useState<number | null>(null)

  useEffect(() => {
    const t = window.setTimeout(() => setDebouncedSearch(searchInput), 400)
    return () => window.clearTimeout(t)
  }, [searchInput])

  useEffect(() => {
    setPage(1)
  }, [debouncedSearch, dateFrom, dateTo, sortBy, pageSize])

  useEffect(() => {
    setExpandedId(null)
  }, [page, pageSize, debouncedSearch, dateFrom, dateTo, sortBy])

  const query = useQuery({
    queryKey: [
      'database-logs',
      page,
      pageSize,
      debouncedSearch,
      dateFrom,
      dateTo,
      sortBy,
    ],
    queryFn: () =>
      logsApi.list(
        buildListParams({
          page,
          pageSize,
          search: debouncedSearch,
          dateFrom,
          dateTo,
          sortBy,
        }),
      ),
  })

  const data = query.data
  const rows = data?.logs ?? []
  const total = data?.total ?? 0
  const totalPages = data?.total_pages ?? 0

  const delMutation = useMutation({
    mutationFn: (id: number) => logsApi.delete(id),
    onSuccess: () => {
      addToast('Log entry removed', 'success')
      void queryClient.invalidateQueries({ queryKey: ['database-logs'] })
    },
    onError: (e: unknown) => addToast(errorMessage(e, 'Delete failed'), 'error'),
  })

  const onDelete = useCallback(
    (id: number) => {
      if (!isAdmin) return
      if (!window.confirm('Delete this log entry?')) return
      delMutation.mutate(id)
    },
    [delMutation, isAdmin],
  )

  const onExport = async () => {
    try {
      await downloadLogsExport({ search: debouncedSearch, dateFrom, dateTo })
      addToast('Export started', 'success')
    } catch (e) {
      addToast(errorMessage(e, 'Export failed'), 'error')
    }
  }

  return (
    <div className="ss-db-page">
      <h1 className="ss-db-title">Database</h1>
      <p className="mb-4 text-sm text-gray-500">Browse and search transcription log entries.</p>

      <div className="ss-db-filters">
        <div className="min-w-0 flex-1">
          <label className="ss-form-label" htmlFor="db-search">
            Search
          </label>
          <input
            id="db-search"
            type="search"
            className="ss-input"
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            placeholder="Transcript, filename, talkgroup…"
            autoComplete="off"
          />
        </div>
        <DatabaseDateRangePicker
          from={dateFrom}
          to={dateTo}
          onChange={(a, b) => {
            setDateFrom(a)
            setDateTo(b)
          }}
          activeDates={activeDateList}
        />
        <div>
          <label className="ss-form-label" htmlFor="db-sort">
            Sort
          </label>
          <select
            id="db-sort"
            className="ss-select min-w-[10rem]"
            value={sortBy}
            onChange={(e) => setSortBy(e.target.value as LogsSortBy)}
          >
            {SORT_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="ss-form-label" htmlFor="db-ps">
            Per page
          </label>
          <select
            id="db-ps"
            className="ss-select w-[4.5rem]"
            value={String(pageSize)}
            onChange={(e) => setPageSize(Number(e.target.value))}
          >
            {PAGE_SIZES.map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </select>
        </div>
        <div className="flex items-end">
          <button
            type="button"
            className="ss-btn-ghost"
            onClick={onExport}
            disabled={query.isFetching}
          >
            Export CSV
          </button>
        </div>
      </div>

      {query.isError && (
        <p className="ss-form-error mb-4" role="alert">
          {errorMessage(query.error, 'Failed to load logs')}
        </p>
      )}

      {query.isLoading && <p className="text-sm text-gray-500">Loading…</p>}

      {!query.isLoading && !query.isError && rows.length === 0 && (
        <p className="ss-empty not-italic">No log entries for these filters.</p>
      )}

      {!query.isLoading && !query.isError && rows.length > 0 && (
        <>
          <div className="ss-db-table-wrap">
            <table className="ss-db-table">
              <thead>
                <tr>
                  <th className="ss-db-th">Time</th>
                  <th className="ss-db-th">Talkgroup</th>
                  <th className="ss-db-th">Filename</th>
                  <th className="ss-db-th">Transcript</th>
                  <th className="ss-db-th">Dur</th>
                  <th className="ss-db-th">Size</th>
                  <th className="ss-db-th">Conf.</th>
                  <th className="ss-db-th text-right"> </th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <Fragment key={row.id}>
                    <LogRow
                      row={row}
                      isAdmin={isAdmin}
                      onDelete={onDelete}
                      deleting={delMutation.isPending}
                      expanded={expandedId === row.id}
                      onToggleExpand={() =>
                        setExpandedId((cur) => (cur === row.id ? null : row.id))
                      }
                    />
                    {expandedId === row.id && (
                      <tr>
                        <td className="ss-db-td p-0" colSpan={8}>
                          <LogExpandedRow row={row} />
                        </td>
                      </tr>
                    )}
                  </Fragment>
                ))}
              </tbody>
            </table>
          </div>

          <div className="ss-db-pager">
            <span>
              {total} entries
              {query.isFetching && !query.isLoading ? ' · …' : ''}
            </span>
            <div className="flex items-center gap-2">
              <button
                type="button"
                className="ss-btn-ghost"
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page <= 1 || query.isFetching}
              >
                Previous
              </button>
              <span className="text-gray-400">
                Page {page}
                {totalPages > 0 ? ` of ${totalPages}` : ''}
              </span>
              <button
                type="button"
                className="ss-btn-ghost"
                onClick={() => setPage((p) => p + 1)}
                disabled={totalPages === 0 || page >= totalPages || query.isFetching}
              >
                Next
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  )
}

function LogRow({
  row,
  isAdmin,
  onDelete,
  deleting,
  expanded,
  onToggleExpand,
}: {
  row: LogListEntry
  isAdmin: boolean
  onDelete: (id: number) => void
  deleting: boolean
  expanded: boolean
  onToggleExpand: () => void
}) {
  const hasAudio = row.audio_path && row.audio_path !== 'file not saved'
  return (
    <tr
      className={`ss-db-row ${expanded ? 'ss-db-row--expanded' : ''}`}
      onClick={onToggleExpand}
      aria-expanded={expanded}
    >
      <td className="ss-db-td font-mono text-xs text-gray-400">
        <span className={`ss-db-expand-icon ${expanded ? 'ss-db-expand-icon--open' : ''}`}>▶</span>{' '}
        {row.timestamp
          ? new Date(row.timestamp).toLocaleString(undefined, { dateStyle: 'short', timeStyle: 'short' })
          : '—'}
      </td>
      <td className="ss-db-td">
        <span className="inline-block max-w-[12rem] truncate text-indigo-200" title={row.talkgroup ?? ''}>
          {row.talkgroup || '—'}
        </span>
      </td>
      <td className="ss-db-td" title={row.filename}>
        <span className="ss-db-filename-clip block">{row.filename || '—'}</span>
      </td>
      <td className="ss-db-td" title={row.transcript || ''}>
        <span className="ss-db-td-clip block text-gray-400">
          {row.transcript || '—'}
        </span>
      </td>
      <td className="ss-db-td tabular-nums text-gray-500">
        {typeof row.duration === 'number' ? row.duration.toFixed(1) : '—'}
      </td>
      <td className="ss-db-td text-gray-500">{formatBytes(row.file_size || 0)}</td>
      <td className="ss-db-td tabular-nums text-gray-500">
        {row.confidence != null ? `${Math.round(row.confidence * 100)}%` : '—'}
      </td>
      <td className="ss-db-td text-right">
        <div className="ss-db-actions">
          {hasAudio && (
            <a
              className="ss-text-link"
              href={`/${row.audio_path}`}
              target="_blank"
              rel="noreferrer"
              onClick={(e) => e.stopPropagation()}
              title="Download audio"
              aria-label="Download audio"
            >
              ⬇️
            </a>
          )}
          {isAdmin && (
            <button
              type="button"
              className="ss-btn-filter-clear"
              onClick={(e) => {
                e.stopPropagation()
                onDelete(row.id)
              }}
              disabled={deleting}
              title="Remove log entry"
              aria-label="Remove log entry"
            >
              🗑️
            </button>
          )}
        </div>
      </td>
    </tr>
  )
}

function kv(label: string, value: string) {
  return (
    <div className="ss-db-expand-field">
      <span className="ss-db-expand-label">{label}</span>
      <span className="ss-db-expand-value">{value}</span>
    </div>
  )
}

function LogExpandedRow({ row }: { row: LogListEntry }) {
  const hasAudio = !!row.audio_path && row.audio_path !== 'file not saved'
  const audioSrc = hasAudio ? `/${row.audio_path}` : ''
  const ts = row.timestamp
    ? new Date(row.timestamp).toLocaleString(undefined, {
        dateStyle: 'short',
        timeStyle: 'medium',
      })
    : '—'
  const confidence = row.confidence != null ? `${Math.round(row.confidence * 100)}%` : '—'

  return (
    <div className="ss-db-expand">
      <div className="ss-db-expand-grid">
        {kv('ID', String(row.id))}
        {kv('Filename', row.filename || '—')}
        {kv('Talkgroup', row.talkgroup || '—')}
        {kv('Date & time', ts)}
        {kv('Duration', typeof row.duration === 'number' ? `${row.duration.toFixed(2)} seconds` : '—')}
        {kv('File size', formatBytes(row.file_size || 0))}
        {kv('Confidence', confidence)}
        {kv('Audio path', row.audio_path || '—')}
      </div>

      <div className="ss-db-expand-field">
        <span className="ss-db-expand-label">Full transcript</span>
        <div className="ss-db-expand-transcript">{row.transcript || '[No transcript]'}</div>
      </div>

      {hasAudio && (
        <div className="ss-db-expand-audio">
          <span className="ss-db-expand-label">Audio playback</span>
          <ScAudioPlayer src={audioSrc} />
        </div>
      )}
    </div>
  )
}

function fmtMmSs(seconds: number) {
  if (!Number.isFinite(seconds) || seconds < 0) return '00:00'
  const m = Math.floor(seconds / 60)
  const s = Math.floor(seconds % 60)
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
}

function buildWavePeaks(channel: Float32Array, points = 220) {
  if (!channel.length || points <= 0) return [] as number[]
  const chunk = Math.max(1, Math.floor(channel.length / points))
  const out: number[] = []
  for (let i = 0; i < points; i += 1) {
    const start = i * chunk
    const end = Math.min(channel.length, start + chunk)
    let peak = 0
    for (let j = start; j < end; j += 1) {
      const v = Math.abs(channel[j] ?? 0)
      if (v > peak) peak = v
    }
    out.push(Math.min(1, peak))
  }
  return out
}

function drawWave(canvas: HTMLCanvasElement, pct: number, peaks: number[]) {
  const dpr = window.devicePixelRatio || 1
  const w = canvas.clientWidth
  const h = canvas.clientHeight
  if (!w || !h) return
  canvas.width = Math.floor(w * dpr)
  canvas.height = Math.floor(h * dpr)
  const ctx = canvas.getContext('2d')
  if (!ctx) return
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
  ctx.clearRect(0, 0, w, h)
  ctx.fillStyle = 'rgba(0,0,0,0.22)'
  ctx.fillRect(0, 0, w, h)
  if (pct > 0) {
    ctx.fillStyle = 'rgba(59,130,246,0.20)'
    ctx.fillRect(0, 0, w * (pct / 100), h)
  }
  const mid = h / 2
  ctx.strokeStyle = 'rgba(255,255,255,0.18)'
  ctx.beginPath()
  ctx.moveTo(0, mid)
  ctx.lineTo(w, mid)
  ctx.stroke()

  const samples = Math.max(120, Math.floor(w / 3))
  const step = w / Math.max(1, samples - 1)
  const amps = Array.from({ length: samples }, (_, i) => {
    const idx = Math.floor((i / Math.max(1, samples - 1)) * Math.max(0, peaks.length - 1))
    return Math.max(0, Math.min(1, peaks[idx] ?? 0))
  })

  const drawSmoothWave = (color: string, clipToX: number) => {
    ctx.save()
    ctx.beginPath()
    ctx.rect(0, 0, clipToX, h)
    ctx.clip()

    ctx.fillStyle = color
    ctx.beginPath()
    ctx.moveTo(0, mid)
    for (let i = 0; i < amps.length; i += 1) {
      const x = i * step
      const y = mid - Math.max(1.5, amps[i] * (h * 0.42))
      const prevX = (i - 1) * step
      const prevY = mid - Math.max(1.5, (amps[i - 1] ?? amps[i]) * (h * 0.42))
      const cx = i === 0 ? x : (prevX + x) / 2
      const cy = i === 0 ? y : (prevY + y) / 2
      if (i === 0) ctx.lineTo(x, y)
      else ctx.quadraticCurveTo(prevX, prevY, cx, cy)
    }
    for (let i = amps.length - 1; i >= 0; i -= 1) {
      const x = i * step
      const y = mid + Math.max(1.5, amps[i] * (h * 0.42))
      const nextX = (i + 1) * step
      const nextY = mid + Math.max(1.5, (amps[i + 1] ?? amps[i]) * (h * 0.42))
      const cx = i === amps.length - 1 ? x : (nextX + x) / 2
      const cy = i === amps.length - 1 ? y : (nextY + y) / 2
      if (i === amps.length - 1) ctx.lineTo(x, y)
      else ctx.quadraticCurveTo(nextX, nextY, cx, cy)
    }
    ctx.closePath()
    ctx.fill()
    ctx.restore()
  }

  drawSmoothWave('rgba(255,255,255,0.14)', w)
  drawSmoothWave('rgba(147,197,253,0.58)', (w * pct) / 100)
}

function ScAudioPlayer({ src }: { src: string }) {
  const audioRef = useRef<HTMLAudioElement | null>(null)
  const canvasRef = useRef<HTMLCanvasElement | null>(null)
  const rafRef = useRef<number | null>(null)
  const [duration, setDuration] = useState(0)
  const [time, setTime] = useState(0)
  const [playing, setPlaying] = useState(false)
  const [volume, setVolume] = useState(70)
  const [muted, setMuted] = useState(false)
  const [peaks, setPeaks] = useState<number[]>([])

  useEffect(() => {
    const audio = new Audio(src)
    audio.preload = 'metadata'
    audio.volume = 0.7
    audioRef.current = audio

    const update = () => {
      setTime(audio.currentTime || 0)
      setDuration(audio.duration || 0)
      const pct = audio.duration ? (audio.currentTime / audio.duration) * 100 : 0
      if (canvasRef.current) drawWave(canvasRef.current, pct, peaks)
    }

    const tick = () => {
      update()
      if (!audio.paused) rafRef.current = requestAnimationFrame(tick)
    }

    const onResize = () => update()
    audio.addEventListener('loadedmetadata', update)
    audio.addEventListener('timeupdate', update)
    audio.addEventListener('play', () => {
      setPlaying(true)
      if (rafRef.current == null) rafRef.current = requestAnimationFrame(tick)
    })
    audio.addEventListener('pause', () => setPlaying(false))
    audio.addEventListener('ended', () => {
      setPlaying(false)
      setTime(0)
    })
    window.addEventListener('resize', onResize)
    update()

    return () => {
      if (rafRef.current != null) cancelAnimationFrame(rafRef.current)
      window.removeEventListener('resize', onResize)
      audio.pause()
      audio.src = ''
    }
  }, [src, peaks])

  useEffect(() => {
    let cancelled = false
    const controller = new AbortController()
    const ctx = new AudioContext()

    const load = async () => {
      try {
        const res = await fetch(src, { signal: controller.signal })
        const buf = await res.arrayBuffer()
        const decoded = await ctx.decodeAudioData(buf)
        if (cancelled) return
        const channel = decoded.getChannelData(0)
        setPeaks(buildWavePeaks(channel, 220))
      } catch {
        if (!cancelled) setPeaks([])
      }
    }

    void load()
    return () => {
      cancelled = true
      controller.abort()
      void ctx.close()
    }
  }, [src])

  useEffect(() => {
    const audio = audioRef.current
    if (!audio || !canvasRef.current) return
    const pct = audio.duration ? (audio.currentTime / audio.duration) * 100 : 0
    drawWave(canvasRef.current, pct, peaks)
  }, [peaks])

  const onPlay = async () => {
    const audio = audioRef.current
    if (!audio || !audio.paused) return
    try {
      await audio.play()
    } catch {
      setPlaying(false)
    }
  }

  const onStop = () => {
    const audio = audioRef.current
    if (!audio) return
    audio.pause()
    audio.currentTime = 0
    setTime(0)
    setPlaying(false)
    if (canvasRef.current) drawWave(canvasRef.current, 0, peaks)
  }

  const onMute = () => {
    const audio = audioRef.current
    if (!audio) return
    const next = !muted
    setMuted(next)
    audio.muted = next
  }

  const onVolume = (n: number) => {
    setVolume(n)
    const audio = audioRef.current
    if (!audio) return
    audio.volume = n / 100
    if (n > 0 && muted) {
      setMuted(false)
      audio.muted = false
    }
  }

  return (
    <div className="sc-audio-player-container">
      <div className="sc-audio-player">
        <div className="sc-audio-player__header">Audio</div>
        <div className="sc-audio-player__waveform">
          <canvas ref={canvasRef} />
        </div>
        <div className="sc-audio-player__controls">
          <button
            type="button"
            className={`sc-audio-player__btn sc-audio-player__btn--play ${playing ? 'playing' : ''}`}
            onClick={onPlay}
          >
            Play
          </button>
          <button
            type="button"
            className="sc-audio-player__btn sc-audio-player__btn--stop"
            onClick={onStop}
            disabled={!playing && time <= 0}
          >
            Stop
          </button>
          <button type="button" className="sc-audio-player__btn sc-audio-player__btn--mute" onClick={onMute}>
            {muted ? 'Unmute' : 'Mute'}
          </button>
          <span className="sc-audio-player__vol-label">Vol</span>
          <div className="sc-audio-player__vol-wrap">
            <div className="sc-audio-player__vol-fill" style={{ width: `${volume}%` }} />
            <input
              type="range"
              className="sc-audio-player__vol"
              min={0}
              max={100}
              value={volume}
              onChange={(e) => onVolume(Number(e.target.value))}
            />
          </div>
          <span className="sc-audio-player__time">
            {fmtMmSs(time)} / {fmtMmSs(duration)}
          </span>
          <a className="sc-audio-player__open" href={src} target="_blank" rel="noreferrer">
            Open audio
          </a>
        </div>
      </div>
    </div>
  )
}
