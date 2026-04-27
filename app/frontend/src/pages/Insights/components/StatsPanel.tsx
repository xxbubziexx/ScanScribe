import type { InsightsSummary, InsightsView, TrendData, ActivityPoint } from '@/types/insights'
import { OdometerValue } from '@/components/ui/OdometerValue'
import { DatabaseDateSinglePicker } from '@/components/database/DatabaseDateSinglePicker'
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

const VIEW_OPTIONS: { value: InsightsView; label: string }[] = [
  { value: 'hourly', label: 'Hourly' },
  { value: 'daily', label: 'Daily' },
  { value: 'weekly', label: 'Weekly' },
]

interface StatsPanelProps {
  summary: InsightsSummary | null
  liveCpm: number | null
  activity: ActivityPoint[]
  view: InsightsView
  date: string
  activeDates: string[]
  onViewChange: (v: InsightsView) => void
  onDateChange: (d: string) => void
  onHourClick: (hour: number) => void
}

export function StatsPanel({
  summary,
  liveCpm,
  activity,
  view,
  date,
  activeDates,
  onViewChange,
  onDateChange,
  onHourClick,
}: StatsPanelProps) {
  const s = summary
  const cpm = liveCpm ?? s?.calls_per_minute ?? 0

  return (
    <div className="ss-glass-panel">
      <div className="ss-insights-head">
        <h2 className="ss-insights-title">
          📈 Activity Statistics
          {date && (
            <span className="ss-insights-date">
              {new Date(date + 'T00:00:00').toLocaleDateString('en-US', {
                weekday: 'short',
                month: 'short',
                day: 'numeric',
                year: 'numeric',
              })}
            </span>
          )}
        </h2>
        <div className="flex items-center gap-3">
          <DatabaseDateSinglePicker
            value={date}
            onChange={onDateChange}
            activeDates={activeDates}
            restrictToActive={activeDates.length > 0}
            aria-label="Insights date"
          />

          <div className="ss-seg">
            {VIEW_OPTIONS.map(({ value, label }) => (
              <button
                key={value}
                type="button"
                onClick={() => onViewChange(value)}
                className={
                  view === value ? 'ss-seg-btn ss-seg-btn--on' : 'ss-seg-btn'
                }
              >
                {label}
              </button>
            ))}
          </div>
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
            { label: 'Peak Hour', value: s?.peak_hour, decimals: 0 },
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

      <ActivityChart data={activity} view={view} onHourClick={onHourClick} />
    </div>
  )
}
