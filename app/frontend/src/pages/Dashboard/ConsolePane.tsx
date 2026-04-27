import { useCallback, useEffect, useRef, useState } from 'react'
import type { ConsoleEntry } from '@/types/watcher'

const LEVEL_CLASS: Record<ConsoleEntry['level'], string> = {
  info: 'ss-log--info',
  success: 'ss-log--success',
  warning: 'ss-log--warning',
  error: 'ss-log--error',
}

function formatTime(iso: string | null): string {
  if (!iso) return new Date().toLocaleTimeString()
  const d = new Date(iso)
  return isNaN(d.getTime()) ? new Date().toLocaleTimeString() : d.toLocaleTimeString()
}

interface ConsolePaneProps {
  entries: ConsoleEntry[]
  onClear: () => void
}

export function ConsolePane({ entries, onClear }: ConsolePaneProps) {
  const [autoScroll, setAutoScroll] = useState(true)
  const scrollRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!autoScroll || !scrollRef.current) return
    const el = scrollRef.current
    el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' })
  }, [entries, autoScroll])

  const handleScroll = useCallback((e: React.UIEvent<HTMLDivElement>) => {
    const el = e.currentTarget
    const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 40
    setAutoScroll(atBottom)
  }, [])

  return (
    <div className="ss-console-root">
      <div className="mb-3 flex shrink-0 items-center justify-between">
        <h2 className="ss-console-title">Console</h2>
        <div className="flex items-center gap-3">
          <label className="ss-check-sm">
            <input
              type="checkbox"
              checked={autoScroll}
              onChange={(e) => setAutoScroll(e.target.checked)}
              className="accent-indigo-500"
            />
            Auto-scroll
          </label>
          <button onClick={onClear} className="ss-ghost-sm" type="button">
            Clear
          </button>
        </div>
      </div>

      <div ref={scrollRef} onScroll={handleScroll} className="ss-console-stream">
        {entries.length === 0 && <p className="ss-empty">No log entries yet…</p>}
        {entries.map((e) => (
          <div key={e.id} className={LEVEL_CLASS[e.level]}>
            <span className="ss-log-time">[{formatTime(e.timestamp)}]</span> {e.message}
          </div>
        ))}
      </div>
    </div>
  )
}
