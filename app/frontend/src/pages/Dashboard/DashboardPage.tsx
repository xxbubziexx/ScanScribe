import { useCallback, useEffect, useRef, useState } from 'react'
import { useWebSocket } from '@/hooks/useWebSocket'
import { watcher } from '@/lib/watcher'
import { useToast } from '@/context/ToastContext'
import type { ConsoleEntry, TranscriptionCard, WatcherStatus, WsMessage } from '@/types/watcher'
import { StatsGrid } from './StatsGrid'
import { ControlPanel } from './ControlPanel'
import { ConsolePane } from './ConsolePane'
import { TranscriptionsPane } from './TranscriptionsPane'
import { ResizableSplit } from './ResizableSplit'

type WatcherState = 'running' | 'stopped' | 'paused'

const MAX_CONSOLE_ENTRIES = 200
let entryCounter = 0

function makeEntry(
  message: string,
  level: ConsoleEntry['level'],
  timestamp: string | null = null,
): ConsoleEntry {
  return { id: `e-${++entryCounter}`, message, level, timestamp }
}

function statusFromWatcher(s: WatcherStatus): WatcherState {
  if (s.paused) return 'paused'
  return s.is_running ? 'running' : 'stopped'
}

const WS_URL = (() => {
  const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${proto}//${window.location.host}/api/watcher/ws`
})()

export function DashboardPage() {
  const { addToast } = useToast()
  const [watcherStatus, setWatcherStatus] = useState<WatcherStatus | null>(null)
  const [watcherState, setWatcherState] = useState<WatcherState>('stopped')
  const [model, setModel] = useState('')
  const [actionLoading, setActionLoading] = useState(false)
  const [consoleEntries, setConsoleEntries] = useState<ConsoleEntry[]>([
    makeEntry('Dashboard initialized', 'info'),
  ])
  const [transcriptions, setTranscriptions] = useState<TranscriptionCard[]>([])

  const addConsole = useCallback((entry: ConsoleEntry) => {
    setConsoleEntries((prev) => {
      const next = [...prev, entry]
      return next.length > MAX_CONSOLE_ENTRIES ? next.slice(next.length - MAX_CONSOLE_ENTRIES) : next
    })
  }, [])

  // WebSocket
  const handleWsMessage = useCallback(
    (msg: WsMessage) => {
      if (msg.type === 'log') {
        const level = (['info', 'success', 'warning', 'error'] as const).includes(
          msg.level as ConsoleEntry['level'],
        )
          ? (msg.level as ConsoleEntry['level'])
          : 'info'
        addConsole(makeEntry(`[${msg.tag ?? 'system'}] ${msg.message}`, level, msg.timestamp))
      } else if (msg.type === 'status') {
        if (msg.data) {
          setWatcherStatus((prev) => ({ ...(prev ?? ({} as WatcherStatus)), ...msg.data }))
          const merged = { ...(watcherStatus ?? ({} as WatcherStatus)), ...msg.data }
          setWatcherState(statusFromWatcher(merged as WatcherStatus))
        }
      } else if (msg.type === 'transcription') {
        setTranscriptions((prev) => [msg.data, ...prev])
      }
    },
    [addConsole, watcherStatus],
  )

  useWebSocket(WS_URL, handleWsMessage, {
    onOpen: () => addConsole(makeEntry('Connected to server', 'success')),
    onClose: () => addConsole(makeEntry('Disconnected — reconnecting…', 'warning')),
  })

  // Initial load + poll every 5 s
  const loadStatus = useCallback(async () => {
    try {
      const s = await watcher.status()
      setWatcherStatus(s)
      setWatcherState(statusFromWatcher(s))
    } catch {
      // silently fail on poll; WS will catch transitions
    }
  }, [])

  useEffect(() => {
    // Health check → model name
    fetch('/health')
      .then((r) => r.json())
      .then((d) => {
        if (d.model) setModel((d.model as string).split('/').pop() ?? d.model)
        addConsole(makeEntry('System health check: OK', 'success'))
      })
      .catch(() => addConsole(makeEntry('Health check failed', 'error')))

    loadStatus()
    const poll = setInterval(loadStatus, 5000)
    return () => clearInterval(poll)
  }, [loadStatus, addConsole])

  // Watcher actions
  const paused = useRef(false)
  paused.current = watcherState === 'paused'

  async function handleStart() {
    setActionLoading(true)
    try {
      const res = await watcher.start()
      addConsole(makeEntry(res.message, res.success ? 'success' : 'error'))
      if (res.success) setWatcherState('running')
    } catch (e) {
      addConsole(makeEntry('Failed to start watcher', 'error'))
      addToast('Failed to start watcher', 'error')
    } finally {
      setActionLoading(false)
    }
  }

  async function handleStop() {
    setActionLoading(true)
    try {
      const res = await watcher.stop()
      addConsole(makeEntry(res.message, res.success ? 'warning' : 'error'))
      if (res.success) setWatcherState('stopped')
    } catch {
      addConsole(makeEntry('Failed to stop watcher', 'error'))
      addToast('Failed to stop watcher', 'error')
    } finally {
      setActionLoading(false)
    }
  }

  async function handleTogglePause() {
    setActionLoading(true)
    try {
      const res = paused.current ? await watcher.resume() : await watcher.pause()
      addConsole(makeEntry(res.message, res.success ? 'info' : 'error'))
      if (res.success) setWatcherState(paused.current ? 'running' : 'paused')
    } catch {
      addConsole(makeEntry('Failed to toggle pause', 'error'))
    } finally {
      setActionLoading(false)
    }
  }

  return (
    <div className="flex flex-col gap-0">
      <StatsGrid status={watcherStatus} model={model} />

      <ControlPanel
        status={watcherStatus}
        watcherState={watcherState}
        onStart={handleStart}
        onStop={handleStop}
        onTogglePause={handleTogglePause}
        loading={actionLoading}
      />

      <ResizableSplit
        left={
          <TranscriptionsPane
            cards={transcriptions}
            onClear={() => setTranscriptions([])}
          />
        }
        right={
          <ConsolePane
            entries={consoleEntries}
            onClear={() =>
              setConsoleEntries([makeEntry('Console cleared', 'info')])
            }
          />
        }
      />
    </div>
  )
}
