import type { TalkgroupEntry } from '@/types/insights'

interface TalkgroupTabProps {
  talkgroups: TalkgroupEntry[]
  onTalkgroupClick: (tg: string) => void
}

export function TalkgroupTab({ talkgroups, onTalkgroupClick }: TalkgroupTabProps) {
  if (talkgroups.length === 0) {
    return <p className="ss-empty not-italic">No data for selected period.</p>
  }

  const max = Math.max(...talkgroups.map((t) => t.count))

  return (
    <div className="space-y-3">
      {talkgroups.slice(0, 10).map((tg) => (
        <button
          key={tg.talkgroup}
          type="button"
          onClick={() => onTalkgroupClick(tg.talkgroup)}
          className="ss-tg-row"
          title="Click to filter by this talkgroup"
        >
          <span className="ss-tg-name" title={tg.talkgroup}>
            {tg.talkgroup}
          </span>
          <div className="ss-tg-bar-track">
            <div
              className="ss-tg-bar"
              style={{ width: `${(tg.count / max) * 100}%` }}
            />
          </div>
          <span className="ss-tg-count">{tg.count}</span>
        </button>
      ))}
    </div>
  )
}
