import type { InsightsSummary, InsightsView, TrendData, ActivityPoint } from '@/types/insights'
import { OdometerValue } from '@/components/ui/OdometerValue'
import { DatabaseDateRangePicker } from '@/components/database/DatabaseDateRangePicker'
import { ActivityChart } from './ActivityChart'

function TrendBadge({ trend }: { trend?: TrendData }) {
  if (!trend) return <span className="text-xs text-gray-600">—</span>
  const d = Math.round(trend.delta ?? 0)
  const up = d > 0
  const flat = d === 0
  const t = flat ? 'ss-trend--flat' : up ? 'ss-trend--up' : 'ss-trend--down'
  return (
    <span className={`ss-trend ${t}`}>
      {flat ? '→' : up ? '▲' : '▼'} {Math.abs(d)}
      {trend.basis ? ` ${trend.basis}` : ''}
    </span>
  )
}

function ChartIcon({ className = 'h-4 w-4' }: { className?: string }) {
  return (
    <svg viewBox="0 0 16 16" className={className} fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
      <path d="M2 13.5h12M4 10.5v-3M8 10.5v-6M12 10.5v-8" strokeLinecap="round" />
    </svg>
  )
}

interface StatsPanelProps {
  summary: InsightsSummary | null
  liveCpm: number | null
  activity: ActivityPoint[]
  view: InsightsView
  dateFrom: string
  dateTo: string
  activeDates: string[]
  onDateRangeChange: (from: string, to: string) => void
  /** When omitted, chart hour clicks do nothing. */
  onHourClick?: (hour: number) => void
}

export function StatsPanel({
  summary,
  liveCpm,
  activity,
  view,
  dateFrom,
  dateTo,
  activeDates,
  onDateRangeChange,
  onHourClick,
}: StatsPanelProps) {
  const s = summary
  const cpm = liveCpm ?? s?.calls_per_minute ?? 0
  const activeDateLabel = dateTo || dateFrom

  return (
    <div className="ss-glass-panel">
      <div className="ss-insights-head">
        <h2 className="ss-insights-title flex items-center gap-2">
          <ChartIcon className="h-4 w-4 text-indigo-400" />
          <span>Activity Statistics</span>
          {activeDateLabel && (
            <span className="ss-insights-date">
              {dateFrom === dateTo || !dateTo
                ? new Date(activeDateLabel + 'T00:00:00').toLocaleDateString('en-US', {
                  weekday: 'short',
                  month: 'short',
                  day: 'numeric',
                  year: 'numeric',
                })
                : `${dateFrom} → ${dateTo}`}
            </span>
          )}
        </h2>
        <div className="ss-insights-controls">
          <DatabaseDateRangePicker
            from={dateFrom}
            to={dateTo}
            onChange={onDateRangeChange}
            activeDates={activeDates}
          />
        </div>
      </div>

      <div className="ss-metric-grid">
        {(
          [
            {
              label: 'Total Transcriptions',
              value: s?.total,
              decimals: 0,
            },
            {
              label: 'Transcriptions Last Hour',
              value: s?.trends?.total_transcriptions?.current,
              trend: s?.trends?.total_transcriptions,
              title: 'Transcriptions in previous full hour vs the hour before',
              decimals: 0,
            },
            {
              label: 'Calls Last Minute',
              value: cpm,
              trend: s?.trends?.calls_last_minute,
              title: 'Count of transcriptions in the previous complete minute',
              decimals: 0,
            },
            {
              label: 'Unique Talkgroups',
              value: s?.unique_talkgroups,
              trend: s?.trends?.unique_talkgroups,
              decimals: 0,
            },
            {
              label: 'Avg Duration',
              value: s?.avg_duration,
              suffix: 's',
              decimals: 1,
            },
            {
              label: dateFrom && dateTo && dateFrom !== dateTo ? 'Peak Day' : 'Peak Hour',
              value: s?.peak_hour,
              decimals: 0,
            },
          ] satisfies {
            label: string
            value: number | string | null | undefined
            trend?: TrendData
            title?: string
            suffix?: string
            decimals?: number
          }[]
        ).map(({ label, value, trend, title, suffix, decimals }) => (
          <div
            key={String(label)}
            className="ss-metric-card"
            title={title}
          >
            <p className="ss-metric-label">{label}</p>
            <p className="ss-metric-value">
              {typeof value === 'number' ? (
                <OdometerValue value={value} suffix={suffix} decimals={decimals ?? 0} />
              ) : (
                value ?? '—'
              )}
            </p>
            {trend !== undefined && <TrendBadge trend={trend} />}
          </div>
        ))}
      </div>

      <ActivityChart
        data={activity}
        view={view}
        onHourClick={onHourClick}
        isMultiDay={dateFrom !== dateTo && !!dateFrom && !!dateTo}
      />
    </div>
  )
}
