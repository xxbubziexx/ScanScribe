import { Link } from 'react-router-dom'
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
          {entry.attached_events && entry.attached_events.length > 0 && (
            <div className="flex flex-shrink-0 flex-wrap items-center gap-1.5">
              {entry.attached_events.map((ev) => {
                const isOpen = ev.status === 'open'
                return (
                  <Link
                    key={ev.id || ev.event_id}
                    to={`/events?incident_id=${encodeURIComponent(ev.event_id)}${isOpen ? '' : '&status=all'}`}
                    onClick={(e) => e.stopPropagation()}
                    className={`ss-attached-badge ${
                      isOpen ? 'ss-attached-badge--open' : 'ss-attached-badge--closed'
                    }`}
                    title={`Attached to ${isOpen ? 'open' : 'closed'} event: ${ev.event_type || ev.event_id} (${ev.event_id})`}
                  >
                    <span
                      className={`h-1.5 w-1.5 rounded-full ${
                        isOpen ? 'bg-amber-400 animate-pulse' : 'bg-gray-400'
                      }`}
                    />
                    <span className="whitespace-nowrap">attached to event</span>
                    <span className="text-[10px] opacity-75 font-mono uppercase">
                      ({ev.status || 'open'})
                    </span>
                  </Link>
                )
              })}
            </div>
          )}
          <span className="min-w-0 flex-1 text-gray-300 sm:truncate">
            {entry.transcript || '—'}
          </span>
          <span className="flex-shrink-0 text-xs text-gray-600">{(entry.duration || 0).toFixed(1)}s</span>
        </div>
      ))}
    </div>
  )
}
