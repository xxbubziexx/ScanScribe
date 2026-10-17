import { useState, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import type { TrafficAnomalyTelemetry, AnomalyTimelinePoint } from '@/types/insights'
import { WidgetInfoTooltip } from './WidgetInfoTooltip'

interface TrafficAnomalyWidgetProps {
  data?: TrafficAnomalyTelemetry
  onHourClick?: (hour: number) => void
}

function ActivityRadarIcon({ className = '' }: { className?: string }) {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" className={`h-4 w-4 shrink-0 ${className}`} fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
      <circle cx="8" cy="8" r="6.5" />
      <circle cx="8" cy="8" r="3.5" strokeDasharray="2 2" />
      <path d="M8 8l4.5-4.5" strokeLinecap="round" />
      <circle cx="8" cy="8" r="1.5" fill="currentColor" />
    </svg>
  )
}

function FlameIcon({ className = '' }: { className?: string }) {
  return (
    <svg width="14" height="14" viewBox="0 0 16 16" className={`h-3.5 w-3.5 shrink-0 ${className}`} fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
      <path d="M8 1.5c1 2.5 4 4 4 7.5a4 4 0 1 1-8 0c0-2 1-3.5 2-4.5.5 1.5 1 2 2 2 0-2-1-3.5 0-5z" strokeLinejoin="round" />
    </svg>
  )
}

function JumpSearchIcon({ className = '' }: { className?: string }) {
  return (
    <svg width="12" height="12" viewBox="0 0 16 16" className={`h-3 w-3 shrink-0 ${className}`} fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
      <path d="M6 3h7v7M13 3L6 10" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

export function TrafficAnomalyWidget({ data, onHourClick }: TrafficAnomalyWidgetProps) {
  const navigate = useNavigate()
  const [hoveredPoint, setHoveredPoint] = useState<AnomalyTimelinePoint | null>(null)

  // Unconditional hook resolution
  const timeline = useMemo(() => data?.timeline ?? [], [data?.timeline])
  const recentAnomalies = useMemo(() => data?.recent_anomalies ?? [], [data?.recent_anomalies])
  const drivers = useMemo(() => data?.drivers ?? [], [data?.drivers])

  const maxTimelineVolume = useMemo(() => {
    if (!timeline.length) return 50
    return Math.max(40, ...timeline.map((p) => Math.max(p.observed, p.upper_bound)))
  }, [timeline])

  if (!data) {
    return (
      <div className="ss-glass-panel relative flex min-h-[300px] items-center justify-center p-8 text-sm text-gray-500">
        Analyzing radio traffic anomaly baseline...
      </div>
    )
  }

  if (data.insufficient_data && data.observed === 0 && (data.is_multi_day || timeline.every((p) => p.observed === 0))) {
    return (
      <div className="ss-glass-panel relative flex min-h-[200px] flex-col items-center justify-center p-8 text-center">
        <p className="text-sm font-medium text-gray-300">Traffic Anomaly &amp; Spike Detector</p>
        <p className="mt-1 text-xs text-gray-500">
          {data.is_multi_day ? 'No traffic recorded across the selected date range.' : 'No traffic recorded for the selected day.'}
        </p>
      </div>
    )
  }

  const {
    current_hour_label,
    observed,
    baseline,
    surge_percentage,
    z_score,
    severity,
    status_label,
    primary_driver,
    insufficient_data,
    is_multi_day,
    range_days,
  } = data

  const severityConfig = {
    critical: {
      border: 'border-rose-500/40 bg-rose-500/15 text-rose-300',
      dot: 'bg-rose-400 animate-ping',
      badgeText: 'Critical Anomaly',
    },
    high: {
      border: 'border-amber-500/40 bg-amber-500/15 text-amber-300',
      dot: 'bg-amber-400 animate-pulse',
      badgeText: 'High Surge Alert',
    },
    elevated: {
      border: 'border-cyan-500/40 bg-cyan-500/15 text-cyan-300',
      dot: 'bg-cyan-400',
      badgeText: 'Elevated Traffic',
    },
    normal: {
      border: 'border-emerald-500/40 bg-emerald-500/15 text-emerald-300',
      dot: 'bg-emerald-400',
      badgeText: 'Nominal Flow',
    },
  }[severity] || {
    border: 'border-gray-500/40 bg-gray-500/15 text-gray-300',
    dot: 'bg-gray-400',
    badgeText: 'Nominal',
  }

  const handleHourSelect = (hour: number) => {
    if (onHourClick) {
      onHourClick(hour)
    } else {
      navigate(`/search?hour=${hour}`)
    }
  }

  const handleAnomalySelect = (ano: (typeof recentAnomalies)[number]) => {
    if (ano.date) {
      navigate(`/search?date_from=${ano.date}&date_to=${ano.date}&hour=${ano.hour}`)
    } else if (onHourClick) {
      onHourClick(ano.hour)
    } else {
      navigate(`/search?hour=${ano.hour}`)
    }
  }

  return (
    <div className="ss-glass-panel relative z-10 flex flex-col justify-between">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-white/5 pb-3">
        <div className="flex items-center gap-2">
          <ActivityRadarIcon className="h-4 w-4 text-amber-400" />
          <h3 className="text-sm font-semibold tracking-wide text-gray-200">
            Traffic Anomaly & Spike Detector
          </h3>
          <WidgetInfoTooltip
            title="Traffic Anomaly & Spike Detector"
            description="Compares current hourly transmission volume against trailing 21-day diurnal Gaussian baselines for the same day of the week to detect public safety surges and active incidents."
            bullets={[
              'Z-Score (σ): Quantifies standard deviations above normal traffic volume.',
              'Spike Markers: Highlight hours where traffic exceeds statistical bounds (> 2.0σ).',
              'Driver Breakdown: Identifies dominant talkgroup channels driving the surge.',
            ]}
          />
          {insufficient_data && (
            <span
              className="rounded border border-amber-500/30 bg-amber-500/10 px-1.5 py-0.5 text-[10px] font-medium tracking-wider text-amber-300 uppercase"
              title="Fewer than 25 calls recorded; baseline is estimated from the same period."
            >
              Estimated Baseline
            </span>
          )}
        </div>

        <div className="flex items-center gap-2">
          <span
            className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-semibold ${severityConfig.border}`}
          >
            <span className={`h-1.5 w-1.5 rounded-full ${severityConfig.dot}`} />
            {status_label}
          </span>
        </div>
      </div>

      {/* KPI Metric Strip */}
      <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
        {/* Surge Multiplier */}
        <div className="rounded-lg border border-white/5 bg-black/20 p-3">
          <div className="flex items-center justify-between">
            <span className="text-[11px] font-medium tracking-wide text-gray-400 uppercase">Volume Surge</span>
            <FlameIcon className="h-3.5 w-3.5 text-amber-400" />
          </div>
          <div className="mt-1 flex items-baseline gap-2">
            <span className={`font-mono text-2xl font-bold tracking-tight ${surge_percentage > 50 ? 'text-amber-400' : 'text-white'}`}>
              {surge_percentage > 0 ? `+${surge_percentage}%` : `${surge_percentage}%`}
            </span>
          </div>
          <p className="mt-0.5 text-[10px] text-gray-500">vs diurnal expected baseline</p>
        </div>

        {/* Statistical Z-Score */}
        <div className="rounded-lg border border-white/5 bg-black/20 p-3">
          <div className="flex items-center justify-between">
            <span className="text-[11px] font-medium tracking-wide text-gray-400 uppercase">Statistical Z-Score</span>
          </div>
          <div className="mt-1 flex items-baseline gap-2">
            <span className={`font-mono text-2xl font-bold tracking-tight ${Math.abs(z_score) >= 2.0 ? 'text-rose-400' : 'text-white'}`}>
              {z_score > 0 ? `+${z_score.toFixed(2)}σ` : `${z_score.toFixed(2)}σ`}
            </span>
            <span className="text-xs text-gray-400">deviation</span>
          </div>
          <p className="mt-0.5 text-[10px] text-gray-500">Gaussian anomaly threshold: 2.0σ</p>
        </div>

        {/* Focus Hour Volume */}
        <div className="rounded-lg border border-white/5 bg-black/20 p-3">
          <div className="flex items-center justify-between">
            <span className="text-[11px] font-medium tracking-wide text-gray-400 uppercase">
              {is_multi_day ? 'Peak Surge Traffic' : `${current_hour_label} Traffic`}
            </span>
          </div>
          <div className="mt-1 flex items-baseline gap-2">
            <span className="font-mono text-2xl font-bold text-white tracking-tight">{observed}</span>
            <span className="text-xs text-gray-400">/ {baseline} expected</span>
          </div>
          <p className="mt-0.5 text-[10px] text-gray-500">
            {is_multi_day ? 'Highest anomalous hour density' : 'Peak hour call density'}
          </p>
        </div>

        {/* Primary Driver */}
        <div className="rounded-lg border border-white/5 bg-black/20 p-3">
          <div className="flex items-center justify-between">
            <span className="text-[11px] font-medium tracking-wide text-gray-400 uppercase">Primary Spike Channel</span>
          </div>
          <div className="mt-1 truncate font-mono text-xs font-semibold text-sky-300" title={primary_driver || 'None'}>
            {primary_driver || 'None'}
          </div>
          <p className="mt-1 text-[10px] text-gray-500">
            {drivers.length > 0 ? `${drivers[0].percentage}% of surge traffic` : 'Channel breakdown'}
          </p>
        </div>
      </div>

      {/* 24-Hour Dual-Layer Timeline or Multi-day Summary */}
      {is_multi_day ? (
        <div className="mt-4 rounded-lg border border-white/5 bg-black/10 p-3">
          <div className="flex items-center justify-between text-xs">
            <span className="font-medium text-gray-300">
              Multi-Day Surge Telemetry ({range_days ?? 2} Days Analyzed)
            </span>
            <span className="text-[11px] text-gray-500">Threshold: Gaussian Z &ge; 2.0&sigma;</span>
          </div>
          <p className="mt-2 text-xs text-gray-400 leading-relaxed">
            {recentAnomalies.length > 0
              ? `${recentAnomalies.length} anomalous volume surge${recentAnomalies.length === 1 ? '' : 's'} identified across the selected date range. Click any surge event below to inspect transmissions in search.`
              : 'No anomalous volume spikes detected across the selected date range. All hourly traffic volumes remained within expected diurnal 2.0σ Gaussian bounds.'}
          </p>
          <p className="mt-1 text-[10px] text-gray-500 italic">
            Select a single day from the date picker to inspect its 24-hour hourly baseline curve.
          </p>
        </div>
      ) : (
        <div className="mt-4 rounded-lg border border-white/5 bg-black/10 p-3">
          <div className="flex items-center justify-between text-xs">
            <span className="font-medium text-gray-300">24-Hour Observed Traffic vs Diurnal Baseline</span>
            <div className="flex items-center gap-3 text-[11px] text-gray-500">
              <span className="inline-flex items-center gap-1">
                <span className="h-1.5 w-1.5 rounded-full bg-amber-400" />
                Observed Spike (&gt; 2σ)
              </span>
              <span className="inline-flex items-center gap-1">
                <span className="h-1.5 w-1.5 rounded-full bg-indigo-500/70" />
                Observed Nominal
              </span>
              <span className="inline-flex items-center gap-1">
                <span className="h-0.5 w-3 border-t border-dashed border-gray-400" />
                Expected Baseline
              </span>
            </div>
          </div>

          {/* Interactive Bar & Threshold Chart */}
          <div className="relative mt-3 h-24 w-full min-w-0">
            <div className="flex h-full items-end gap-1">
              {timeline.map((point) => {
                const heightPct = Math.min(100, Math.max(6, (point.observed / maxTimelineVolume) * 100))
                const baselinePct = Math.min(100, Math.max(6, (point.baseline / maxTimelineVolume) * 100))

                return (
                  <div
                    key={point.hour}
                    onClick={() => handleHourSelect(point.hour)}
                    onMouseEnter={() => setHoveredPoint(point)}
                    onMouseLeave={() => setHoveredPoint(null)}
                    className="group relative flex h-full flex-1 cursor-pointer flex-col justify-end"
                    title={`Hour ${point.label}: ${point.observed} calls (${point.z_score > 0 ? '+' : ''}${point.z_score.toFixed(1)}σ)`}
                  >
                    {/* Baseline indicator mark */}
                    <div
                      style={{ bottom: `${baselinePct}%` }}
                      className="pointer-events-none absolute left-0 right-0 z-10 border-t border-dashed border-gray-400/50"
                    />

                    {/* Observed Bar */}
                    <div
                      style={{ height: `${heightPct}%` }}
                      className={`w-full rounded-t transition-all ${
                        point.is_anomaly
                          ? 'bg-amber-400 shadow-[0_0_8px_rgba(251,191,36,0.5)] group-hover:bg-amber-300'
                          : 'bg-indigo-500/40 group-hover:bg-indigo-400/70'
                      }`}
                    />
                  </div>
                )
              })}
            </div>
          </div>

          {/* Hour Axis Labels */}
          <div className="mt-1 flex justify-between font-mono text-[9px] text-gray-500">
            <span>12 AM</span>
            <span>4 AM</span>
            <span>8 AM</span>
            <span>12 PM</span>
            <span>4 PM</span>
            <span>8 PM</span>
            <span>11 PM</span>
          </div>

          {/* Hover Readout */}
          <div className="mt-2 flex h-5 items-center justify-between font-mono text-[11px]">
            {hoveredPoint ? (
              <span className="text-gray-300">
                <span className="font-semibold text-amber-400">{hoveredPoint.label}</span>: Observed{' '}
                <span className="font-bold text-white">{hoveredPoint.observed}</span> tx vs baseline{' '}
                <span className="text-gray-400">{hoveredPoint.baseline}</span> tx (
                <span className={hoveredPoint.is_anomaly ? 'text-amber-400 font-bold' : 'text-gray-400'}>
                  {hoveredPoint.z_score > 0 ? `+${hoveredPoint.z_score.toFixed(2)}σ` : `${hoveredPoint.z_score.toFixed(2)}σ`}
                </span>
                {hoveredPoint.is_anomaly ? ' — SURGE DETECTED' : ''})
              </span>
            ) : (
              <span className="text-gray-500">Click or hover any bar to inspect deviation and search transmissions</span>
            )}
          </div>
        </div>
      )}

      {/* Recent Spike Incidents Log */}
      {recentAnomalies.length > 0 && (
        <div className="mt-3 space-y-1.5 border-t border-white/5 pt-2">
          <div className="flex items-center justify-between text-[11px] font-semibold text-gray-400 uppercase tracking-wider">
            <span>{is_multi_day ? `Detected Traffic Surges (${range_days ?? 2} Days)` : 'Detected Traffic Surges Today'}</span>
            <span>Trigger Talkgroup</span>
          </div>

          <div className="max-h-[140px] space-y-1 overflow-y-auto pr-1">
            {recentAnomalies.map((ano, idx) => (
              <div
                key={`ano-${ano.date ?? ''}-${ano.hour}-${idx}`}
                onClick={() => handleAnomalySelect(ano)}
                className="group flex cursor-pointer items-center justify-between gap-2 rounded border border-white/5 bg-black/20 px-2.5 py-1.5 transition-all hover:border-amber-500/40 hover:bg-white/[0.04]"
                title={`Filter transcriptions for ${ano.time_window}`}
              >
                <div className="flex items-center gap-2">
                  <span className="rounded bg-amber-500/20 px-1.5 py-0.5 font-mono text-[10px] font-bold text-amber-300">
                    +{ano.z_score.toFixed(1)}σ
                  </span>
                  <span className="text-xs font-medium text-gray-200 group-hover:text-white">
                    {ano.time_window}
                  </span>
                  {ano.likely_incident && (
                    <span className="hidden text-[11px] text-gray-400 sm:inline">
                      • {ano.likely_incident}
                    </span>
                  )}
                </div>

                <div className="flex items-center gap-2">
                  <span className="max-w-[160px] truncate font-mono text-[11px] text-sky-300 sm:max-w-[220px]">
                    {ano.primary_driver}
                  </span>
                  <span className="text-gray-500 group-hover:text-amber-400">
                    <JumpSearchIcon className="h-3 w-3" />
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
