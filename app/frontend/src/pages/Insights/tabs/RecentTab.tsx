import type { LogEntry } from '@/types/insights'

function formatTime(ts: string) {
  return new Date(ts).toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' })
}

interface RecentTabProps {
  recent: LogEntry[]
}

export function RecentTab({ recent }: RecentTabProps) {
  if (recent.length === 0) {
    return <p className="ss-empty not-italic">No recent activity.</p>
  }

  return (
    <div className="ss-rec-scroll">
      {recent.map((entry) => (
        <div key={entry.id} className="ss-recent-row">
          <span className="w-16 flex-shrink-0 text-xs text-gray-500">
            {formatTime(entry.timestamp)}
          </span>
          <span className="flex-shrink-0 rounded bg-indigo-500/20 px-2 py-0.5 text-xs text-indigo-300">
            {entry.talkgroup || 'N/A'}
          </span>
          <span className="min-w-0 flex-1 truncate text-gray-300">
            {entry.transcript || '—'}
          </span>
          <span className="flex-shrink-0 text-xs text-gray-600">{(entry.duration || 0).toFixed(1)}s</span>
        </div>
      ))}
    </div>
  )
}
