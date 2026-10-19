import { useEffect, useRef, useState } from 'react'
import type { TransmissionLookup } from '@/types/chat'

interface AudioControlPanelProps {
  transmissions: TransmissionLookup[]
  activeTxId: number | null
  isOpen: boolean
  onClose: () => void
  onSelectTx: (txId: number) => void
  scopedPlaylist?: { title: string; txIds: number[] } | null
  onClearScope?: () => void
  allTransmissionsCount?: number
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
  scopedPlaylist,
  onClearScope,
  allTransmissionsCount,
}: AudioControlPanelProps) {
  const audioRef = useRef<HTMLAudioElement | null>(null)
  const [isPlaying, setIsPlaying] = useState(false)
  const [currentTime, setCurrentTime] = useState(0)
  const [duration, setDuration] = useState(0)
  const [playbackSpeed, setPlaybackSpeed] = useState(1.0)
  const [volume, setVolume] = useState(0.85)
  const [isMuted, setIsMuted] = useState(false)
  const [autoAdvance, setAutoAdvance] = useState(true)
  const [playbackError, setPlaybackError] = useState<string | null>(null)

  const activeTx = transmissions.find((t) => t.id === activeTxId) || null
  const activeIndex = activeTx ? transmissions.findIndex((t) => t.id === activeTx.id) : -1

  // Handle track changing & audio lifecycle safely per audio-web-apis guidelines
  useEffect(() => {
    setPlaybackError(null)
    if (!activeTx?.audio_url || activeTx.audio_available === false) {
      if (audioRef.current) {
        audioRef.current.pause()
        audioRef.current.removeAttribute('src')
        audioRef.current.load()
      }
      setIsPlaying(false)
      setCurrentTime(0)
      setDuration(activeTx?.duration || 0)
      if (activeTx) {
        setPlaybackError('Original audio recording file is not retained in local storage for this transmission.')
      }
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

    const onPlay = () => {
      setIsPlaying(true)
      setPlaybackError(null)
    }
    const onPause = () => setIsPlaying(false)

    const onError = () => {
      setIsPlaying(false)
      setPlaybackError('Audio recording is missing from disk or could not be decoded.')
    }

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
    audio.addEventListener('error', onError)
    audio.addEventListener('ended', onEnded)

    // Attempt playback
    const playPromise = audio.play()
    if (playPromise !== undefined) {
      playPromise.catch((err) => {
        if (err.name !== 'AbortError') {
          setPlaybackError('Playback prevented: audio resource not available or blocked by browser.')
        }
        setIsPlaying(false)
      })
    }

    return () => {
      audio.removeEventListener('loadedmetadata', onLoadedMetadata)
      audio.removeEventListener('timeupdate', onTimeUpdate)
      audio.removeEventListener('play', onPlay)
      audio.removeEventListener('pause', onPause)
      audio.removeEventListener('error', onError)
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
    if (!audio || !activeTx?.audio_url || activeTx.audio_available === false) return

    if (audio.paused) {
      setPlaybackError(null)
      const p = audio.play()
      if (p !== undefined) {
        p.catch((err) => {
          if (err.name !== 'AbortError') {
            setPlaybackError('Playback failed: audio resource missing or invalid.')
          }
          setIsPlaying(false)
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

  // Track skip (Next) and back (Previous) in queue
  const handlePreviousTx = () => {
    if (activeIndex > 0) {
      onSelectTx(transmissions[activeIndex - 1].id)
    }
  }

  const handleNextTx = () => {
    if (activeIndex >= 0 && activeIndex < transmissions.length - 1) {
      onSelectTx(transmissions[activeIndex + 1].id)
    }
  }

  // Keyboard navigation & Escape listener
  useEffect(() => {
    if (!isOpen) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onClose()
        return
      }

      // Don't intercept if user is typing in an input or textarea
      const el = e.target as HTMLElement | null
      if (el && (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA' || el.isContentEditable)) {
        return
      }

      if (e.key === '[' || (e.shiftKey && e.key === 'ArrowLeft')) {
        e.preventDefault()
        handlePreviousTx()
      } else if (e.key === ']' || (e.shiftKey && e.key === 'ArrowRight')) {
        e.preventDefault()
        handleNextTx()
      } else if (e.key === ' ' && activeTx) {
        e.preventDefault()
        handleTogglePlay()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [isOpen, onClose, activeIndex, transmissions, activeTx, isPlaying])

  if (!isOpen) return null

  const progressPercent = duration > 0 ? (currentTime / duration) * 100 : 0

  return (
    <>
      {/* Mobile Backdrop Overlay (< lg) */}
      <div
        className="fixed inset-0 bg-black/75 backdrop-blur-xs z-40 lg:hidden transition-opacity cursor-pointer animate-fade-in"
        onClick={onClose}
        aria-hidden="true"
      />

      {/* Audio Deck Container: Responsive Slide-over on Mobile (< lg), Docked Sidebar on Desktop (>= lg) */}
      <aside
        id="ss-audio-deck"
        aria-label="Transmission Audio Deck"
        className="fixed inset-y-0 right-0 z-50 w-full sm:w-[420px] max-w-full h-full h-dvh bg-[#11131c] border-l border-[#222533] flex flex-col select-none shadow-2xl animate-slide-in lg:static lg:z-30 lg:w-88 xl:w-96 lg:h-full lg:shadow-none lg:animate-none shrink-0"
      >
        {/* Top Header */}
        <div className="px-4 py-3 pt-[max(0.75rem,env(safe-area-inset-top))] border-b border-[#222533] bg-[#141724] flex items-center justify-between shrink-0">
          <div className="flex items-center gap-2 min-w-0">
            <span className="text-sm font-semibold text-gray-200 truncate">
              {scopedPlaylist ? scopedPlaylist.title : 'Transmission Audio'}
            </span>
            <span className="px-1.5 py-0.5 rounded text-[11px] font-mono font-medium bg-indigo-950 text-indigo-300 border border-indigo-800/60 shrink-0">
              {transmissions.length} {scopedPlaylist ? 'scoped' : 'cited'}
            </span>
            {scopedPlaylist && onClearScope && (
              <button
                type="button"
                onClick={onClearScope}
                className="text-[11px] text-indigo-400 hover:text-indigo-200 underline cursor-pointer shrink-0 ml-1"
                title="Return to full conversation audio deck"
              >
                Show All{allTransmissionsCount ? ` (${allTransmissionsCount})` : ''}
              </button>
            )}
          </div>

          <div className="flex items-center gap-2">
            {/* Auto-Advance Toggle */}
            <button
              type="button"
              onClick={() => setAutoAdvance(!autoAdvance)}
              className={`min-h-[38px] px-2.5 py-1 rounded-lg text-xs font-medium transition-colors cursor-pointer border flex items-center ${
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
              className="w-11 h-11 flex items-center justify-center text-gray-400 hover:text-white hover:bg-[#202538] active:bg-[#282f48] rounded-xl text-lg transition-colors cursor-pointer"
              title="Close audio panel (Esc)"
              aria-label="Close audio deck"
            >
              ✕
            </button>
          </div>
        </div>

        {/* Active Audio Playback Deck */}
        <div className="p-3.5 sm:p-4 border-b border-[#222533] bg-[#161928] space-y-3 shrink-0">
          {activeTx ? (
            <>
              {/* Active Transmission Info Header */}
              <div className="flex items-center justify-between gap-2">
                <div className="flex items-center gap-2 truncate">
                  <span className="px-2 py-0.5 bg-indigo-600 text-white font-mono text-xs font-bold rounded-md shadow-xs">
                    TX #{activeTx.id}
                  </span>
                  <span className="text-xs sm:text-sm font-semibold text-gray-200 truncate">
                    {activeTx.talkgroup || 'Unknown Channel'}
                  </span>
                </div>
                <span className="text-xs text-gray-400 font-mono shrink-0">
                  {activeTx.timestamp
                    ? new Date(activeTx.timestamp).toLocaleTimeString([], {
                        hour: '2-digit',
                        minute: '2-digit',
                        second: '2-digit',
                      })
                    : 'N/A'}
                </span>
              </div>

              {/* Error Notification Banner */}
              {playbackError && (
                <div className="px-3 py-2 rounded-lg bg-amber-950/60 border border-amber-600/40 text-amber-300 text-xs flex items-center gap-2">
                  <span className="shrink-0 text-sm">⚠️</span>
                  <span>{playbackError}</span>
                </div>
              )}

              {/* Custom Tactical Scrubber Bar */}
              <div className="space-y-1.5 pt-1">
                <div className="relative w-full flex items-center">
                  <input
                    type="range"
                    min={0}
                    max={duration || 1}
                    step={0.05}
                    value={currentTime}
                    onChange={handleSeek}
                    disabled={!activeTx?.audio_url}
                    aria-label="Audio playback seek position"
                    className="w-full h-2.5 sm:h-2 bg-[#252a3d] rounded-lg appearance-none cursor-pointer accent-indigo-500 hover:accent-indigo-400 transition-all focus:outline-none"
                    style={{
                      background: `linear-gradient(to right, #6366f1 ${progressPercent}%, #252a3d ${progressPercent}%)`,
                    }}
                  />
                </div>

                <div className="flex justify-between text-xs font-mono text-gray-400">
                  <span>{formatTime(currentTime)}</span>
                  <span>{formatTime(duration)}</span>
                </div>
              </div>

              {/* Transport & Control Buttons */}
              <div className="flex items-center justify-between gap-1 pt-1">
                {/* Previous Transmission (Track Back) */}
                <button
                  type="button"
                  onClick={handlePreviousTx}
                  disabled={activeIndex <= 0}
                  className="min-w-[40px] sm:min-w-[44px] min-h-[44px] flex items-center justify-center text-gray-300 hover:text-white hover:bg-[#202438] active:bg-[#252a42] rounded-lg transition-colors cursor-pointer disabled:opacity-30 disabled:cursor-not-allowed group"
                  title="Previous transmission in sequence ([)"
                  aria-label="Previous transmission"
                >
                  <svg className="w-4 h-4 fill-current group-hover:scale-110 transition-transform" viewBox="0 0 24 24">
                    <path d="M6 6h2v12H6zm3.5 6l8.5 6V6z" />
                  </svg>
                </button>

                {/* Skip Back 5s */}
                <button
                  type="button"
                  onClick={() => handleSkip(-5)}
                  disabled={!activeTx?.audio_url || activeTx.audio_available === false}
                  className="min-w-[40px] sm:min-w-[44px] min-h-[44px] flex items-center justify-center text-gray-300 hover:text-white hover:bg-[#202438] active:bg-[#252a42] rounded-lg font-mono text-xs transition-colors cursor-pointer disabled:opacity-40"
                  title="Rewind 5 seconds"
                  aria-label="Rewind 5 seconds"
                >
                  -5s
                </button>

                {/* Central Play/Pause Tactical Button */}
                <button
                  type="button"
                  onClick={handleTogglePlay}
                  disabled={!activeTx?.audio_url || activeTx.audio_available === false}
                  className="w-12 h-12 rounded-full bg-indigo-600 hover:bg-indigo-500 active:scale-95 text-white flex items-center justify-center shadow-lg transition-all cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed shrink-0"
                  title={isPlaying ? 'Pause' : 'Play'}
                  aria-label={isPlaying ? 'Pause' : 'Play'}
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
                  className="min-w-[40px] sm:min-w-[44px] min-h-[44px] flex items-center justify-center text-gray-300 hover:text-white hover:bg-[#202438] active:bg-[#252a42] rounded-lg font-mono text-xs transition-colors cursor-pointer disabled:opacity-40"
                  title="Forward 5 seconds"
                  aria-label="Forward 5 seconds"
                >
                  +5s
                </button>

                {/* Next Transmission (Track Skip) */}
                <button
                  type="button"
                  onClick={handleNextTx}
                  disabled={activeIndex < 0 || activeIndex >= transmissions.length - 1}
                  className="min-w-[40px] sm:min-w-[44px] min-h-[44px] flex items-center justify-center text-gray-300 hover:text-white hover:bg-[#202438] active:bg-[#252a42] rounded-lg transition-colors cursor-pointer disabled:opacity-30 disabled:cursor-not-allowed group"
                  title="Next transmission in sequence (])"
                  aria-label="Next transmission"
                >
                  <svg className="w-4 h-4 fill-current group-hover:scale-110 transition-transform" viewBox="0 0 24 24">
                    <path d="M6 18l8.5-6L6 6v12zM16 6v12h2V6h-2z" />
                  </svg>
                </button>
              </div>

              {/* Secondary Playback Bar: Speed Pill + Scoped Tag + Volume Slider */}
              <div className="flex items-center justify-between pt-1.5 border-t border-[#22273c]/60">
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={handleToggleSpeed}
                    className="min-h-[36px] px-2.5 bg-[#1e2235] hover:bg-[#282d46] active:bg-[#2c334e] border border-[#2b3149] rounded-lg font-mono text-xs font-semibold text-indigo-300 transition-colors cursor-pointer flex items-center justify-center"
                    title="Change playback speed"
                    aria-label="Change playback speed"
                  >
                    {playbackSpeed.toFixed(2).replace(/\.00$/, '')}x
                  </button>
                  {scopedPlaylist && onClearScope && (
                    <span className="text-[10px] font-mono text-amber-300 bg-amber-950/70 border border-amber-600/40 px-2 py-0.5 rounded-md flex items-center gap-1">
                      <span>⚡</span>
                      <span>Scoped</span>
                    </span>
                  )}
                </div>

                {/* Volume / Mute Control */}
                <div className="flex items-center gap-1">
                  <button
                    type="button"
                    onClick={handleToggleMute}
                    className="min-w-[36px] min-h-[36px] flex items-center justify-center text-gray-400 hover:text-gray-200 active:bg-white/5 rounded-lg transition-colors cursor-pointer text-base"
                    title={isMuted ? 'Unmute' : 'Mute'}
                    aria-label={isMuted ? 'Unmute' : 'Mute'}
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
                    aria-label="Volume level"
                    className="w-16 sm:w-20 h-2 bg-[#252a3d] rounded appearance-none cursor-pointer accent-indigo-500"
                    title={`Volume: ${Math.round((isMuted ? 0 : volume) * 100)}%`}
                  />
                </div>
              </div>

              {/* Active Transcript Preview */}
              <div className="p-2.5 rounded-lg bg-[#0f1118] border border-[#232738] text-xs font-mono text-gray-300 leading-relaxed max-h-24 overflow-y-auto select-text">
                {activeTx.transcript || <span className="italic text-gray-500">No transcript recorded</span>}
              </div>
            </>
          ) : (
            <div className="py-6 text-center text-xs text-gray-400 space-y-1.5">
              <div className="text-2xl">📻</div>
              <div className="font-semibold text-gray-200">No Transmission Selected</div>
              <div className="text-[11px] text-gray-500 max-w-xs mx-auto">
                Select any transmission below or click a [TX #...] badge to listen.
              </div>
            </div>
          )}
        </div>

        {/* Cited Transmissions Queue List */}
        <div className="flex-1 overflow-y-auto p-2 sm:p-2.5 pb-[max(1rem,env(safe-area-inset-bottom))] space-y-2">
          <div className="px-2 py-1 text-xs font-semibold text-gray-400 uppercase tracking-wider flex items-center justify-between">
            <div className="flex items-center gap-1.5">
              <span>{scopedPlaylist ? 'Incident Queue' : 'Cited Recordings'} ({transmissions.length})</span>
              <span className="text-[10px] text-gray-500 lowercase font-normal">(chronological)</span>
            </div>
            {transmissions.length > 0 && activeIndex >= 0 && (
              <span className="font-mono text-xs text-indigo-400">
                Playing {activeIndex + 1} of {transmissions.length}
              </span>
            )}
          </div>

          {transmissions.length === 0 ? (
            <div className="p-6 text-center text-xs text-gray-500 italic">
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
                  className={`p-3 rounded-xl border transition-all cursor-pointer min-h-[52px] active:scale-[0.99] ${
                    isSelected
                      ? 'bg-indigo-950/50 border-indigo-500/80 shadow-md ring-1 ring-indigo-500/30'
                      : 'bg-[#151824] hover:bg-[#1a1f30] border-[#252a3c] hover:border-gray-500'
                  }`}
                >
                  {/* Card Top Row */}
                  <div className="flex items-center justify-between gap-1 mb-1.5">
                    <div className="flex items-center gap-1.5 min-w-0">
                      {/* Equalizer Wave Icon when playing */}
                      {isCardPlaying ? (
                        <div className="flex items-end gap-0.5 h-3.5 w-3.5 shrink-0" aria-label="Now playing">
                          <span className="w-0.5 bg-indigo-400 animate-pulse h-full" />
                          <span className="w-0.5 bg-indigo-400 animate-pulse h-2/3" />
                          <span className="w-0.5 bg-indigo-400 animate-pulse h-4/5" />
                        </div>
                      ) : (
                        <span className="text-[11px] text-gray-500 font-mono">#{idx + 1}</span>
                      )}

                      <span
                        className={`font-mono text-xs font-bold px-1.5 py-0.5 rounded ${
                          isSelected ? 'bg-indigo-600 text-white' : 'bg-[#22273a] text-indigo-300'
                        }`}
                      >
                        TX #{tx.id}
                      </span>

                      <span className="text-xs font-semibold text-gray-200 truncate">
                        {tx.talkgroup || 'Unknown TG'}
                      </span>
                    </div>

                    <div className="flex items-center gap-1.5 text-xs font-mono text-gray-400 shrink-0">
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
                  <p className="text-xs text-gray-300 line-clamp-2 leading-relaxed font-mono">
                    {tx.transcript || <span className="text-gray-500 italic">No transcript recorded</span>}
                  </p>
                </div>
              )
            })
          )}
        </div>
      </aside>
    </>
  )
}
