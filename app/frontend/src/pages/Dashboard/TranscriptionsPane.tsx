import { useCallback, useLayoutEffect, useRef, useState } from 'react'
import type { TranscriptionCard } from '@/types/watcher'

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function confidenceClass(c: number): string {
  if (c >= 0.85) return 'ss-badge-ok'
  if (c >= 0.6) return 'ss-badge-mid'
  return 'ss-badge-bad'
}

function truncate(s: string, max: number): string {
  return s.length > max ? `${s.slice(0, max)}…` : s
}

interface TranscriptionsPaneProps {
  cards: TranscriptionCard[]
  onClear: () => void
  /** Hide list controls; audio `<audio controls>` stays interactive. */
  viewOnly?: boolean
}

function TranscriptionItem({
  card,
  pinned,
  onPin,
  viewOnly,
}: {
  card: TranscriptionCard
  pinned: boolean
  onPin: (id: TranscriptionCard['id']) => void
  viewOnly?: boolean
}) {
  const [expanded, setExpanded] = useState(false)
  const [canToggle, setCanToggle] = useState(false)
  const transcriptRef = useRef<HTMLParagraphElement>(null)
  const t = (card.transcript || '').trim()

  useLayoutEffect(() => {
    const el = transcriptRef.current
    if (!t || !el) {
      setCanToggle(false)
      return
    }
    if (expanded) return
    setCanToggle(el.scrollHeight > el.clientHeight + 2)
  }, [t, expanded, card.id, card.transcript])

  return (
    <article
      className={`ss-tcard ${pinned && !viewOnly ? 'ring-1 ring-amber-400/70' : ''}`}
      onClick={viewOnly ? undefined : () => onPin(card.id)}
      role={viewOnly ? undefined : 'button'}
      tabIndex={viewOnly ? undefined : 0}
      onKeyDown={
        viewOnly
          ? undefined
          : (e) => {
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault()
                onPin(card.id)
              }
            }
      }
    >
      <div className="ss-tcard-h">
        <span className="ss-tname" title={card.filename}>
          {truncate(card.filename, 50)}
        </span>
        <time className="ss-ttime">
          {card.timestamp ? new Date(card.timestamp).toLocaleTimeString() : ''}
        </time>
      </div>

      {card.duration > 0 && (
        <p className="ss-tmeta">
          <span>Duration: {card.duration.toFixed(1)}s</span>
          <span>Size: {formatBytes(card.file_size)}</span>
        </p>
      )}

      <div className="ss-tbar">
        {card.talkgroup && <span className="ss-pill-tg">{card.talkgroup}</span>}
        <span className={confidenceClass(card.confidence)}>
          {(card.confidence * 100).toFixed(0)}% confidence
        </span>
      </div>

      {t && (
        <div className="ss-tbody">
          <p
            ref={transcriptRef}
            className={`ss-transcript ${!expanded && !viewOnly ? 'line-clamp-4' : viewOnly ? 'line-clamp-6' : ''}`}
          >
            {t}
          </p>
          {canToggle && !viewOnly && (
            <button
              type="button"
              onClick={() => setExpanded((e) => !e)}
              className="ss-text-link mt-2 block w-full text-left"
            >
              {expanded ? 'Show less' : 'Show more'}
            </button>
          )}
        </div>
      )}

      {card.audio_path && card.audio_path !== 'file not saved' && (
        <div className="ss-audio-wrap">
          <audio controls preload="none" className="h-8 w-full max-w-full">
            <source src={`/${card.audio_path}`} type="audio/mpeg" />
          </audio>
        </div>
      )}
    </article>
  )
}

const FOLLOW_TOP_THRESHOLD_PX = 48

export function TranscriptionsPane({ cards, onClear, viewOnly = false }: TranscriptionsPaneProps) {
  const [autoScroll, setAutoScroll] = useState(true)
  const [pinnedCardId, setPinnedCardId] = useState<TranscriptionCard['id'] | null>(null)
  const scrollRef = useRef<HTMLDivElement>(null)
  /** User turned off auto-follow via checkbox; don't re-enable from scroll alone. */
  const pausedByUserRef = useRef(false)

  // Newest cards are at the top — keep the viewport pinned there when following live.
  useLayoutEffect(() => {
    if (!autoScroll || !scrollRef.current || cards.length === 0) return
    scrollRef.current.scrollTo({ top: 0, behavior: 'auto' })
  }, [cards, autoScroll])

  const handlePin = useCallback((id: TranscriptionCard['id']) => {
    setPinnedCardId(id)
    setAutoScroll(false)
    pausedByUserRef.current = true
  }, [])

  const handleScroll = useCallback((e: React.UIEvent<HTMLDivElement>) => {
    const el = e.currentTarget
    const atTop = el.scrollTop <= FOLLOW_TOP_THRESHOLD_PX
    if (atTop && !pausedByUserRef.current) {
      setAutoScroll(true)
    } else if (!atTop) {
      setAutoScroll(false)
    }
  }, [])

  const onAutoScrollCheckbox = useCallback((checked: boolean) => {
    pausedByUserRef.current = !checked
    setAutoScroll(checked)
    if (checked) {
      scrollRef.current?.scrollTo({ top: 0, behavior: 'auto' })
    }
  }, [])

  const handleClearClick = useCallback(() => {
    setPinnedCardId(null)
    pausedByUserRef.current = false
    setAutoScroll(true)
    onClear()
  }, [onClear])

  return (
    <div className="flex h-full flex-col p-4">
      <div className="mb-3 flex shrink-0 flex-wrap items-center justify-between gap-2">
        <h2 className="ss-page-h2">
          Transcriptions
          <span className="ss-page-h2-sub">{cards.length} items</span>
        </h2>
        <div className="flex flex-wrap items-center gap-3">
          {!viewOnly && (
            <>
              <label className="ss-check">
                <input
                  type="checkbox"
                  checked={autoScroll}
                  onChange={(e) => onAutoScrollCheckbox(e.target.checked)}
                  className="accent-indigo-500"
                />
                Follow newest
              </label>
              <button onClick={handleClearClick} className="ss-ghost-sm" type="button">
                Clear
              </button>
            </>
          )}
        </div>
      </div>

      <div ref={scrollRef} onScroll={handleScroll} className="ss-scroll">
        {cards.length === 0 && <p className="ss-empty">Waiting for transcriptions…</p>}
        {cards.map((card) => (
          <TranscriptionItem
            key={card.id}
            card={card}
            pinned={!viewOnly && card.id === pinnedCardId}
            onPin={handlePin}
            viewOnly={viewOnly}
          />
        ))}
      </div>
    </div>
  )
}
