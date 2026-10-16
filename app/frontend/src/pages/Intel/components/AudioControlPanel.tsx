import { useEffect, useRef, useState } from 'react'
import type { TransmissionLookup } from '@/types/chat'

interface AudioControlPanelProps {
  transmissions: TransmissionLookup[]
  activeTxId: number | null
  isOpen: boolean
  onClose: () => void
  onSelectTx: (txId: number) => void
}

function formatTime(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds < 0) return '00:00'
  const m = Math.floor(seconds / 60)
  const s = Math.floor(seconds % 60)
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
}

const SPEED_OPTIONS = [1.0, 1.25, 1.5, 2.0]

export function AudioControlPanel({
  transmissions,
  activeTxId,
  isOpen,
  onClose,
  onSelectTx,
}: AudioControlPanelProps) {
  const audioRef = useRef<HTMLAudioElement | null>(null)
  const [isPlaying, setIsPlaying] = useState(false)
  const [currentTime, setCurrentTime] = useState(0)
  const [duration, setDuration] = useState(0)
  const [playbackSpeed, setPlaybackSpeed] = useState(1.0)
  const [volume, setVolume] = useState(0.85)
  const [isMuted, setIsMuted] = useState(false)
  const [autoAdvance, setAutoAdvance] = useState(true)

  const activeTx = transmissions.find((t) => t.id === activeTxId) || null
  const activeIndex = activeTx ? transmissions.findIndex((t) => t.id === activeTx.id) : -1

  // Handle track changing & audio lifecycle safely per audio-web-apis guidelines
  useEffect(() => {
    if (!activeTx?.audio_url) {
      if (audioRef.current) {
        audioRef.current.pause()
        audioRef.current.removeAttribute('src')
        audioRef.current.load()
      }
      setIsPlaying(false)
      setCurrentTime(0)
      setDuration(activeTx?.duration || 0)
      return
    }

    const audio = new Audio(activeTx.audio_url)
    audio.preload = 'metadata'
    audio.playbackRate = playbackSpeed
    audio.volume = isMuted ? 0 : volume
    audioRef.current = audio

    const onLoadedMetadata = () => {
      setDuration(audio.duration || activeTx.duration || 0)
    }

    const onTimeUpdate = () => {
      setCurrentTime(audio.currentTime || 0)
    }

    const onPlay = () => setIsPlaying(true)
    const onPause = () => setIsPlaying(false)

    const onEnded = () => {
      setIsPlaying(false)
      setCurrentTime(0)
      // Auto-advance to next transmission in sequence
      if (autoAdvance && activeIndex >= 0 && activeIndex < transmissions.length - 1) {
        const nextTx = transmissions[activeIndex + 1]
        if (nextTx) {
          onSelectTx(nextTx.id)
        }
      }
    }

    audio.addEventListener('loadedmetadata', onLoadedMetadata)
    audio.addEventListener('timeupdate', onTimeUpdate)
    audio.addEventListener('play', onPlay)
    audio.addEventListener('pause', onPause)
    audio.addEventListener('ended', onEnded)

    // Attempt playback
    const playPromise = audio.play()
    if (playPromise !== undefined) {
      playPromise.catch((err) => {
        if (err.name !== 'AbortError') {
          console.warn('Audio auto-play prevented or failed:', err)
        }
        setIsPlaying(false)
      })
    }

    return () => {
      audio.removeEventListener('loadedmetadata', onLoadedMetadata)
      audio.removeEventListener('timeupdate', onTimeUpdate)
      audio.removeEventListener('play', onPlay)
      audio.removeEventListener('pause', onPause)
      audio.removeEventListener('ended', onEnded)
      audio.pause()
      audio.removeAttribute('src')
      audio.load()
    }
  }, [activeTx?.id, activeTx?.audio_url])

  // Speed changes
  const handleToggleSpeed = () => {
    const nextIdx = (SPEED_OPTIONS.indexOf(playbackSpeed) + 1) % SPEED_OPTIONS.length
    const nextSpeed = SPEED_OPTIONS[nextIdx]
    setPlaybackSpeed(nextSpeed)
    if (audioRef.current) {
      audioRef.current.playbackRate = nextSpeed
    }
  }

  // Play / Pause toggle
  const handleTogglePlay = () => {
    const audio = audioRef.current
    if (!audio) return

    if (audio.paused) {
      const p = audio.play()
      if (p !== undefined) {
        p.catch((err) => {
          if (err.name !== 'AbortError') console.error('Play error:', err)
        })
      }
    } else {
      audio.pause()
    }
  }

  // Seek / Scrub
  const handleSeek = (e: React.ChangeEvent<HTMLInputElement>) => {
    const newTime = parseFloat(e.target.value)
    setCurrentTime(newTime)
    if (audioRef.current) {
      audioRef.current.currentTime = newTime
    }
  }

  // Jump +/- 5s
  const handleSkip = (seconds: number) => {
    const audio = audioRef.current
    if (!audio) return
    const target = Math.max(0, Math.min(duration, (audio.currentTime || 0) + seconds))
    audio.currentTime = target
    setCurrentTime(target)
  }

  // Volume
  const handleVolumeChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const v = parseFloat(e.target.value)
    setVolume(v)
    setIsMuted(v === 0)
    if (audioRef.current) {
      audioRef.current.volume = v
      audioRef.current.muted = v === 0
    }
  }

  const handleToggleMute = () => {
    const nextMuted = !isMuted
    setIsMuted(nextMuted)
    if (audioRef.current) {
      audioRef.current.muted = nextMuted
      if (!nextMuted && volume === 0) {
        setVolume(0.5)
        audioRef.current.volume = 0.5
      }
    }
  }

  if (!isOpen) return null

  const progressPercent = duration > 0 ? (currentTime / duration) * 100 : 0

  return (
    <div className="w-88 xl:w-96 bg-[#11131c] border-l border-[#222533] flex flex-col h-full z-30 shrink-0 select-none shadow-2xl">
      {/* Top Header */}
      <div className="px-3.5 py-2.5 border-b border-[#222533] bg-[#141724] flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="text-sm font-semibold text-gray-200">Transmission Audio</span>
          <span className="px-1.5 py-0.5 rounded text-[11px] font-mono font-medium bg-indigo-950 text-indigo-300 border border-indigo-800/60">
            {transmissions.length} cited
          </span>
        </div>

        <div className="flex items-center gap-2">
          {/* Auto-Advance Toggle */}
          <button
            type="button"
            onClick={() => setAutoAdvance(!autoAdvance)}
            className={`px-2 py-0.5 rounded text-[10px] font-medium transition-colors cursor-pointer border ${
              autoAdvance
                ? 'bg-emerald-950/70 border-emerald-700/60 text-emerald-300'
                : 'bg-[#181a24] border-[#292e42] text-gray-400 hover:text-gray-200'
            }`}
            title="Automatically play the next cited transmission when current clip finishes"
          >
            Auto-Advance
          </button>

          {/* Close Panel Button */}
          <button
            type="button"
            onClick={onClose}
            className="p-1 text-gray-400 hover:text-gray-100 hover:bg-[#202538] rounded transition-colors cursor-pointer"
            title="Close audio panel"
          >
            ✕
          </button>
        </div>
      </div>

      {/* Active Audio Playback Deck */}
      <div className="p-3.5 border-b border-[#222533] bg-[#161928] space-y-3">
        {activeTx ? (
          <>
            {/* Active Transmission Info Header */}
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-1.5 truncate">
                <span className="px-1.5 py-0.5 bg-indigo-600 text-white font-mono text-[11px] font-bold rounded">
                  TX #{activeTx.id}
                </span>
                <span className="text-xs font-semibold text-gray-200 truncate">
                  {activeTx.talkgroup || 'Unknown Channel'}
                </span>
              </div>
              <span className="text-[11px] text-gray-400 font-mono shrink-0">
                {activeTx.timestamp
                  ? new Date(activeTx.timestamp).toLocaleTimeString([], {
                      hour: '2-digit',
                      minute: '2-digit',
                      second: '2-digit',
                    })
                  : 'N/A'}
              </span>
            </div>

            {/* Custom Tactical Scrubber Bar */}
            <div className="space-y-1">
              <div className="relative w-full flex items-center">
                <input
                  type="range"
                  min={0}
                  max={duration || 1}
                  step={0.05}
                  value={currentTime}
                  onChange={handleSeek}
                  disabled={!activeTx?.audio_url}
                  className="w-full h-1.5 bg-[#252a3d] rounded-lg appearance-none cursor-pointer accent-indigo-500 hover:accent-indigo-400 transition-all focus:outline-none"
                  style={{
                    background: `linear-gradient(to right, #6366f1 ${progressPercent}%, #252a3d ${progressPercent}%)`,
                  }}
                />
              </div>

              <div className="flex justify-between text-[10px] font-mono text-gray-400">
                <span>{formatTime(currentTime)}</span>
                <span>{formatTime(duration)}</span>
              </div>
            </div>

            {/* Transport & Control Buttons */}
            <div className="flex items-center justify-between pt-1">
              {/* Skip Back 5s */}
              <button
                type="button"
                onClick={() => handleSkip(-5)}
                disabled={!activeTx?.audio_url}
                className="p-1.5 text-gray-400 hover:text-gray-100 hover:bg-[#202438] rounded font-mono text-[11px] transition-colors cursor-pointer disabled:opacity-40"
                title="Rewind 5 seconds"
              >
                -5s
              </button>

              {/* Central Play/Pause Tactical Button */}
              <button
                type="button"
                onClick={handleTogglePlay}
                disabled={!activeTx?.audio_url}
                className="w-10 h-10 rounded-full bg-indigo-600 hover:bg-indigo-500 active:scale-95 text-white flex items-center justify-center shadow-lg transition-all cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed"
                title={isPlaying ? 'Pause' : 'Play'}
              >
                {isPlaying ? (
                  <svg className="w-5 h-5 fill-current" viewBox="0 0 24 24">
                    <path d="M6 19h4V5H6v14zm8-14v14h4V5h-4z" />
                  </svg>
                ) : (
                  <svg className="w-5 h-5 fill-current ml-0.5" viewBox="0 0 24 24">
                    <path d="M8 5v14l11-7z" />
                  </svg>
                )}
              </button>

              {/* Skip Forward 5s */}
              <button
                type="button"
                onClick={() => handleSkip(5)}
                disabled={!activeTx?.audio_url}
                className="p-1.5 text-gray-400 hover:text-gray-100 hover:bg-[#202438] rounded font-mono text-[11px] transition-colors cursor-pointer disabled:opacity-40"
                title="Forward 5 seconds"
              >
                +5s
              </button>

              {/* Playback Speed Pill */}
              <button
                type="button"
                onClick={handleToggleSpeed}
                className="px-2 py-1 bg-[#1e2235] hover:bg-[#282d46] border border-[#2b3149] rounded font-mono text-[11px] font-semibold text-indigo-300 transition-colors cursor-pointer"
                title="Change playback speed"
              >
                {playbackSpeed.toFixed(2).replace(/\.00$/, '')}x
              </button>

              {/* Volume / Mute Control */}
              <div className="flex items-center gap-1">
                <button
                  type="button"
                  onClick={handleToggleMute}
                  className="p-1 text-gray-400 hover:text-gray-200 transition-colors cursor-pointer text-xs"
                  title={isMuted ? 'Unmute' : 'Mute'}
                >
                  {isMuted || volume === 0 ? '🔇' : '🔊'}
                </button>
                <input
                  type="range"
                  min={0}
                  max={1}
                  step={0.05}
                  value={isMuted ? 0 : volume}
                  onChange={handleVolumeChange}
                  className="w-14 h-1 bg-[#252a3d] rounded appearance-none cursor-pointer accent-indigo-500"
                  title={`Volume: ${Math.round((isMuted ? 0 : volume) * 100)}%`}
                />
              </div>
            </div>

            {/* Active Transcript Preview */}
            <div className="p-2 rounded bg-[#0f1118] border border-[#232738] text-[11px] font-mono text-gray-300 leading-relaxed max-h-24 overflow-y-auto select-text">
              {activeTx.transcript || <span className="italic text-gray-500">No transcript recorded</span>}
            </div>
          </>
        ) : (
          <div className="py-4 text-center text-xs text-gray-400 space-y-1">
            <div className="text-lg">📻</div>
            <div className="font-medium text-gray-300">No Transmission Selected</div>
            <div className="text-[11px] text-gray-500">
              Select any transmission below or click a [TX #...] badge to listen.
            </div>
          </div>
        )}
      </div>

      {/* Cited Transmissions Queue List */}
      <div className="flex-1 overflow-y-auto p-2 space-y-1.5">
        <div className="px-1.5 py-1 text-[11px] font-semibold text-gray-400 uppercase tracking-wider flex items-center justify-between">
          <span>Cited Recordings ({transmissions.length})</span>
          {transmissions.length > 0 && activeIndex >= 0 && (
            <span className="font-mono text-[10px] text-indigo-400">
              Playing {activeIndex + 1} of {transmissions.length}
            </span>
          )}
        </div>

        {transmissions.length === 0 ? (
          <div className="p-4 text-center text-xs text-gray-500 italic">
            No transmissions cited in this conversation yet. Transmissions will appear here automatically when mentioned by Scanner Intelligence.
          </div>
        ) : (
          transmissions.map((tx, idx) => {
            const isSelected = tx.id === activeTxId
            const isCardPlaying = isSelected && isPlaying

            return (
              <div
                key={tx.id}
                onClick={() => onSelectTx(tx.id)}
                className={`p-2.5 rounded-lg border transition-all cursor-pointer ${
                  isSelected
                    ? 'bg-indigo-950/40 border-indigo-600/70 shadow-sm ring-1 ring-indigo-500/30'
                    : 'bg-[#151824] hover:bg-[#1a1f30] border-[#252a3c] hover:border-gray-600'
                }`}
              >
                {/* Card Top Row */}
                <div className="flex items-center justify-between gap-1 mb-1.5">
                  <div className="flex items-center gap-1.5">
                    {/* Equalizer Wave Icon when playing */}
                    {isCardPlaying ? (
                      <div className="flex items-end gap-0.5 h-3 w-3 shrink-0">
                        <span className="w-0.5 bg-indigo-400 animate-pulse h-full" />
                        <span className="w-0.5 bg-indigo-400 animate-pulse h-2/3" />
                        <span className="w-0.5 bg-indigo-400 animate-pulse h-4/5" />
                      </div>
                    ) : (
                      <span className="text-[10px] text-gray-500 font-mono">#{idx + 1}</span>
                    )}

                    <span
                      className={`font-mono text-[11px] font-bold px-1.5 py-0.2 rounded ${
                        isSelected ? 'bg-indigo-600 text-white' : 'bg-[#22273a] text-indigo-300'
                      }`}
                    >
                      TX #{tx.id}
                    </span>

                    <span className="text-xs font-medium text-gray-200 truncate max-w-[120px]">
                      {tx.talkgroup || 'Unknown TG'}
                    </span>
                  </div>

                  <div className="flex items-center gap-1.5 text-[10px] font-mono text-gray-400 shrink-0">
                    {tx.duration && <span>{tx.duration.toFixed(1)}s</span>}
                    <span>
                      {tx.timestamp
                        ? new Date(tx.timestamp).toLocaleTimeString([], {
                            hour: '2-digit',
                            minute: '2-digit',
                          })
                        : ''}
                    </span>
                  </div>
                </div>

                {/* Card Transcript Snippet */}
                <p className="text-[11px] text-gray-300 line-clamp-2 leading-relaxed font-mono">
                  {tx.transcript || <span className="text-gray-500 italic">No transcript recorded</span>}
                </p>
              </div>
            )
          })
        )}
      </div>
    </div>
  )
}
