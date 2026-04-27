import type { ReactNode } from 'react'
import type { WatcherStatus } from '@/types/watcher'
import { OdometerValue } from '@/components/ui/OdometerValue'

type WatcherState = 'running' | 'stopped' | 'paused'

interface ControlPanelProps {
  status: WatcherStatus | null
  watcherState: WatcherState
  onStart: () => void
  onStop: () => void
  onTogglePause: () => void
  loading: boolean
}

function ResourceBar({
  pct,
  label,
  value,
}: {
  pct: number
  label: string
  value: ReactNode
}) {
  const color =
    pct >= 90 ? 'bg-red-500' : pct >= 70 ? 'bg-yellow-400' : 'bg-indigo-500'

  return (
    <div className="ss-rbar">
      <div className="ss-resource-kv">
        <span>{label}</span>
        <span>{value}</span>
      </div>
      <div className="ss-resource-track">
        <div
          className={`h-full rounded-full transition-all duration-500 ${color}`}
          style={{ width: `${Math.min(pct, 100)}%` }}
        />
      </div>
    </div>
  )
}

const STATUS_CONFIG: Record<WatcherState, { label: string; dot: string; text: string }> = {
  running: { label: 'Status: Running', dot: 'bg-green-400', text: 'text-green-400' },
  stopped: { label: 'Status: Stopped', dot: 'bg-red-400', text: 'text-red-400' },
  paused: { label: 'Status: Paused', dot: 'bg-yellow-400', text: 'text-yellow-400' },
}

export function ControlPanel({
  status,
  watcherState,
  onStart,
  onStop,
  onTogglePause,
  loading,
}: ControlPanelProps) {
  const cfg = STATUS_CONFIG[watcherState]
  const isPaused = watcherState === 'paused'

  return (
    <div className="ss-control">
      <div className="mb-4 flex items-center justify-between">
        <div className="flex gap-2">
          <button
            onClick={onStart}
            disabled={loading || watcherState === 'running'}
            className="ss-btn-start"
            type="button"
          >
            Start Watcher
          </button>
          <button
            onClick={onStop}
            disabled={loading || watcherState === 'stopped'}
            className="ss-btn-stop"
            type="button"
          >
            Stop Watcher
          </button>
          <button
            onClick={onTogglePause}
            disabled={loading || watcherState === 'stopped'}
            className="ss-btn-ghost"
            type="button"
          >
            {isPaused ? 'Resume' : 'Pause'}
          </button>
        </div>
      </div>

      <div className="ss-control-inner">
        <div className="flex items-center gap-3">
          <span className={`ss-status-dot ${cfg.dot}`} />
          <div>
            <p className={`text-sm font-medium ${cfg.text}`}>{cfg.label}</p>
            <p className="ss-eng-caption">
              {status?.processor_running
                ? 'Transcription Engine: Running'
                : 'Transcription Engine: Not running'}
            </p>
          </div>
        </div>

        <ResourceBar
          label="Memory"
          pct={status?.memory_percent ?? 0}
          value={
            status ? (
              <>
                <OdometerValue value={status.memory_used_gb} decimals={1} /> /{' '}
                <OdometerValue value={status.memory_total_gb} decimals={1} suffix=" GB" />
              </>
            ) : (
              'Loading…'
            )
          }
        />

        <ResourceBar
          label="CPU"
          pct={status?.cpu_percent ?? 0}
          value={status ? <OdometerValue value={status.cpu_percent} decimals={1} suffix="%" /> : 'Loading…'}
        />
      </div>
    </div>
  )
}
