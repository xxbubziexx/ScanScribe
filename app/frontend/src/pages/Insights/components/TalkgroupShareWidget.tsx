import type { TalkgroupEntry, TalkgroupTrackerTelemetry } from '@/types/insights'
import { TalkgroupTrackerWidget } from './TalkgroupTrackerWidget'

interface TalkgroupShareWidgetProps {
  data?: TalkgroupEntry[]
  trackerData?: TalkgroupTrackerTelemetry
  dateFrom?: string
  dateTo?: string
}

/**
 * TalkgroupShareWidget has been retired and merged into TalkgroupTrackerWidget.
 * Maintained as a backward-compatible adapter.
 */
export function TalkgroupShareWidget({ data, trackerData, dateFrom, dateTo }: TalkgroupShareWidgetProps) {
  return (
    <TalkgroupTrackerWidget
      data={trackerData}
      fallbackTalkgroups={data}
      dateFrom={dateFrom}
      dateTo={dateTo}
    />
  )
}

export { TalkgroupTrackerWidget }
