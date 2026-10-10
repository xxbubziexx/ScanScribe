import type { PipelineEvent } from '../utils/incidentFormatters'
import {
  formatTime,
  formatTimeLong,
  splitBadgeEntries,
  typeDisplayFor,
} from '../utils/incidentFormatters'

export function EventListCard({
  event,
  active,
  onSelect,
}: {
  event: PipelineEvent
  active: boolean
  onSelect: () => void
}) {
  return (
    <button
      type="button"
      className={active ? 'ss-events-row ss-events-row--active' : 'ss-events-row'}
      onClick={onSelect}
    >
      <div className="ss-events-row-head">
        <span
          className={
            event.status === 'open'
              ? 'ss-events-status ss-events-status--open'
              : 'ss-events-status ss-events-status--closed'
          }
        >
          {event.status}
        </span>
        <span className="ss-events-eyebrow">
          {event.monitorName} · {event.spansAttached} span{event.spansAttached === 1 ? '' : 's'}
        </span>
        <span
          className="ss-events-time"
          title={
            event.incidentAt || event.createdAt
              ? `Initial: ${formatTimeLong(event.incidentAt ?? event.createdAt)}${event.lastSpanAt || event.updatedAt ? `\nLast updated: ${formatTimeLong(event.lastSpanAt ?? event.updatedAt)}` : ''}`
              : undefined
          }
        >
          {formatTime(
            event.lastSpanAt ?? event.updatedAt ?? event.incidentAt ?? event.createdAt,
            event.incidentAt || event.createdAt,
          )}
        </span>
      </div>
      <p className="ss-events-row-title">{typeDisplayFor(event)}</p>
      <p className="ss-events-row-meta">
        {splitBadgeEntries(event.talkgroup).map((tg) => (
          <span key={`${event.eventId}-tg-${tg}`} className="ss-events-chip-tg">
            {tg}
          </span>
        ))}
        {event.statusDetail ? <span className="text-gray-500">· {event.statusDetail}</span> : null}
      </p>
      {splitBadgeEntries(event.location).length > 0 ? (
        <div className="ss-events-row-locations">
          {splitBadgeEntries(event.location).map((loc) => (
            <span key={`${event.eventId}-loc-${loc}`} className="ss-events-chip-loc">
              {loc}
            </span>
          ))}
        </div>
      ) : null}
      {splitBadgeEntries(event.units).length > 0 ? (
        <div className="ss-events-row-units">
          {splitBadgeEntries(event.units).map((unit) => (
            <span key={`${event.eventId}-unit-${unit}`} className="ss-events-chip-loc">
              {unit}
            </span>
          ))}
        </div>
      ) : null}
      <p className="ss-events-type">{event.summary || event.originalTranscription || '—'}</p>
    </button>
  )
}
