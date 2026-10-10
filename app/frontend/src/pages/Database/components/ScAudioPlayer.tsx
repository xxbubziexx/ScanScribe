import { useEffect, useRef, useState } from 'react'

function fmtMmSs(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds < 0) return '00:00'
  const m = Math.floor(seconds / 60)
  const s = Math.floor(seconds % 60)
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
}

function buildWavePeaks(channel: Float32Array, points = 220): number[] {
  if (!channel.length || points <= 0) return []
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

function drawWave(canvas: HTMLCanvasElement, pct: number, peaks: number[]): void {
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

  ctx.save()
  ctx.beginPath()
  ctx.rect(0, 0, w, h)
  ctx.clip()

  ctx.fillStyle = 'rgba(255,255,255,0.14)'
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

export function ScAudioPlayer({ src }: { src: string }) {
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
          <button
            type="button"
            className="sc-audio-player__btn sc-audio-player__btn--mute"
            onClick={onMute}
          >
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
