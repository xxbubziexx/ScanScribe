import { useState } from 'react'
import type { RtfTelemetry, RtfHourlyPoint } from '@/types/insights'
import { WidgetInfoTooltip } from './WidgetInfoTooltip'

interface RtfThroughputWidgetProps {
  data?: RtfTelemetry
  isMultiDay?: boolean
}

function CpuPulseIcon({ className = '' }: { className?: string }) {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" className={`h-4 w-4 shrink-0 ${className}`} fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
      <rect x="3" y="3" width="10" height="10" rx="2" />
      <path d="M6 1v2M10 1v2M6 13v2M10 13v2M1 6h2M1 10h2M13 6h2M13 10h2" strokeLinecap="round" />
      <circle cx="8" cy="8" r="1.5" fill="currentColor" />
    </svg>
  )
}

function GaugeSpeedIcon({ className = '' }: { className?: string }) {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" className={`h-4 w-4 shrink-0 ${className}`} fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
      <path d="M2.5 11.5a6 6 0 1 1 11 0" strokeLinecap="round" />
      <path d="M8 8l2.5-3" strokeLinecap="round" />
      <circle cx="8" cy="8" r="1" fill="currentColor" />
    </svg>
  )
}

export function RtfThroughputWidget({ data, isMultiDay }: RtfThroughputWidgetProps) {
  const [hoveredHour, setHoveredHour] = useState<RtfHourlyPoint | null>(null)

  if (!data) {
    return (
      <div className="ss-glass-panel relative flex items-center justify-center p-8 text-sm text-gray-500">
        Loading ingestion throughput telemetry...
      </div>
    )
  }

  if (data.insufficient_data) {
    return (
      <div className="ss-glass-panel relative flex min-h-[200px] flex-col items-center justify-center p-8 text-center">
        <p className="text-sm font-medium text-gray-300">Ingestion Throughput &amp; RTF</p>
        <p className="mt-1 text-xs text-gray-500">
          No transcriptions with recorded processing time in the selected range.
        </p>
      </div>
    )
  }

  const {
    rtf,
    speedup,
    total_audio_s,
    total_proc_s,
    avg_latency_ms,
    avg_duration_s,
    avg_confidence,
    model_used,
    status,
    timeline,
  } = data

  const statusConfig = {
    nominal: {
      label: 'Optimal Headroom',
      color: 'text-emerald-400 bg-emerald-500/10 border-emerald-500/20',
      dot: 'bg-emerald-400',
      desc: 'Processing far faster than real-time with zero queue accumulation.',
    },
    moderate: {
      label: 'Moderate Load',
      color: 'text-cyan-400 bg-cyan-500/10 border-cyan-500/20',
      dot: 'bg-cyan-400',
      desc: 'Processing comfortably within real-time thresholds.',
    },
    saturated: {
      label: 'Near Saturation',
      color: 'text-amber-400 bg-amber-500/10 border-amber-500/20',
      dot: 'bg-amber-400',
      desc: 'Audio throughput approaching 1:1 real-time processing rate.',
    },
    backlog: {
      label: 'Queue Backlog',
      color: 'text-rose-400 bg-rose-500/10 border-rose-500/20',
      dot: 'bg-rose-400',
      desc: 'Audio arriving faster than inference completion; buffer delay increasing.',
    },
  }[status] || {
    label: 'Nominal',
    color: 'text-gray-400 bg-gray-500/10 border-gray-500/20',
    dot: 'bg-gray-400',
    desc: 'Processing status nominal.',
  }

  const maxRtfInTimeline = Math.max(0.4, ...timeline.map((t) => t.rtf))
  const totalAudioHrs = (total_audio_s / 3600).toFixed(1)
  const totalProcMin = (total_proc_s / 60).toFixed(0)

  return (
    <div className="ss-glass-panel relative z-10 flex flex-col justify-between">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-white/5 pb-3">
        <div className="flex items-center gap-2">
          <CpuPulseIcon className="h-4 w-4 text-emerald-400" />
          <h3 className="text-sm font-semibold tracking-wide text-gray-200">
            Ingestion Throughput & Real-Time Factor (RTF)
          </h3>
          <WidgetInfoTooltip
            title="Ingestion Throughput & RTF"
            description="Tracks pipeline transcription speed relative to audio transmission length to ensure the scanner never accumulates a processing backlog."
            bullets={[
              'Real-Time Factor (RTF): Processing time divided by audio duration (e.g. 0.12x = 8.3x faster than real-time).',
              'Mean Latency: Elapsed milliseconds between audio arrival and database write.',
              'Pipeline Headroom: Monitors GPU/CPU capacity to prevent queue stalls.',
            ]}
          />
        </div>

        <div className="flex items-center gap-2">
          <span
            className={`inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-xs font-medium ${statusConfig.color}`}
            title={statusConfig.desc}
          >
            <span className={`h-1.5 w-1.5 rounded-full ${statusConfig.dot}`} />
            {statusConfig.label}
          </span>
          <span className="font-mono text-[11px] text-gray-500" title="Active ASR model checkpoint">
            {model_used}
          </span>
        </div>
      </div>

      {/* Hero Performance Indicators */}
      <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
        {/* RTF Card */}
        <div className="rounded-lg border border-white/5 bg-black/20 p-3">
          <div className="flex items-center justify-between">
            <span className="text-[11px] font-medium tracking-wide text-gray-400 uppercase">Real-Time Factor</span>
            <GaugeSpeedIcon className="h-3.5 w-3.5 text-gray-500" />
          </div>
          <div className="mt-1 flex items-baseline gap-2">
            <span className="font-mono text-2xl font-bold text-white tracking-tight">{rtf.toFixed(2)}x</span>
            <span className="text-xs text-emerald-400">{speedup}x speed</span>
          </div>
          <p className="mt-0.5 text-[10px] text-gray-500">Processing seconds / audio second</p>
        </div>

        {/* Latency Card */}
        <div className="rounded-lg border border-white/5 bg-black/20 p-3">
          <div className="flex items-center justify-between">
            <span className="text-[11px] font-medium tracking-wide text-gray-400 uppercase">Avg Ingest Latency</span>
          </div>
          <div className="mt-1 flex items-baseline gap-2">
            <span className="font-mono text-2xl font-bold text-white tracking-tight">{avg_latency_ms.toFixed(0)}</span>
            <span className="text-xs text-gray-400">ms / chunk</span>
          </div>
          <p className="mt-0.5 text-[10px] text-gray-500">Avg clip length: {avg_duration_s.toFixed(1)}s</p>
        </div>

        {/* Audio Processed */}
        <div className="rounded-lg border border-white/5 bg-black/20 p-3">
          <div className="flex items-center justify-between">
            <span className="text-[11px] font-medium tracking-wide text-gray-400 uppercase">Audio Processed</span>
          </div>
          <div className="mt-1 flex items-baseline gap-2">
            <span className="font-mono text-2xl font-bold text-white tracking-tight">{totalAudioHrs}</span>
            <span className="text-xs text-gray-400">hrs</span>
          </div>
          <p className="mt-0.5 text-[10px] text-gray-500">Wall time: {totalProcMin} min inference</p>
        </div>

        {/* Confidence Card */}
        <div className="rounded-lg border border-white/5 bg-black/20 p-3">
          <div className="flex items-center justify-between">
            <span className="text-[11px] font-medium tracking-wide text-gray-400 uppercase">Whisper Confidence</span>
          </div>
          <div className="mt-1 flex items-baseline gap-2">
            <span className="font-mono text-2xl font-bold text-white tracking-tight">{avg_confidence.toFixed(1)}%</span>
            <span className="text-xs text-cyan-400">calibrated</span>
          </div>
          <p className="mt-0.5 text-[10px] text-gray-500">Mean token transition log-prob</p>
        </div>
      </div>

      {/* Hourly RTF Profile & Timeline */}
      <div className="mt-4 rounded-lg border border-white/5 bg-black/10 p-3">
        <div className="flex items-center justify-between text-xs">
          <span className="font-medium text-gray-300">
            {isMultiDay ? 'Diurnal RTF Processing Profile (Aggregated Across Range)' : '24-Hour RTF Processing Curve'}
          </span>
          <div className="flex items-center gap-3 text-[11px] text-gray-500">
            <span className="inline-flex items-center gap-1">
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />
              Optimal (&lt; 0.35x)
            </span>
            <span className="inline-flex items-center gap-1">
              <span className="h-1.5 w-1.5 rounded-full bg-cyan-400" />
              Hourly Mean
            </span>
          </div>
        </div>

        {/* Timeline SVG Spark/Bar chart */}
        <div className="relative mt-3 h-20 w-full">
          <div className="flex h-full items-end gap-1">
            {timeline.map((point) => {
              const heightPct = Math.min(100, Math.max(8, (point.rtf / maxRtfInTimeline) * 100))
              const isHigh = point.rtf > 0.35
              return (
                <div
                  key={point.hour}
                  className="group relative flex h-full flex-1 cursor-pointer flex-col justify-end"
                  onMouseEnter={() => setHoveredHour(point)}
                  onMouseLeave={() => setHoveredHour(null)}
                >
                  <div
                    style={{ height: `${heightPct}%` }}
                    className={`w-full rounded-t transition-all ${
                      isHigh
                        ? 'bg-amber-400/80 group-hover:bg-amber-300'
                        : 'bg-emerald-500/50 group-hover:bg-emerald-400'
                    }`}
                  />
                </div>
              )
            })}
          </div>

          {/* Reference Line for 0.35x Target */}
          <div
            className="pointer-events-none absolute right-0 left-0 border-t border-dashed border-emerald-500/30"
            style={{ bottom: `${Math.min(100, (0.35 / maxRtfInTimeline) * 100)}%` }}
          >
            <span className="absolute -top-3 right-0 text-[9px] font-mono text-emerald-400/60">0.35x Target</span>
          </div>
        </div>

        {/* Hour Axis Labels */}
        <div className="mt-1 flex justify-between font-mono text-[9px] text-gray-500">
          <span>12 AM</span>
          <span>6 AM</span>
          <span>12 PM</span>
          <span>6 PM</span>
          <span>11 PM</span>
        </div>

        {/* Hover Readout */}
        <div className="mt-2 flex h-5 items-center justify-between font-mono text-[11px]">
          {hoveredHour ? (
            <span className="text-gray-300">
              <span className="font-semibold text-emerald-400">{hoveredHour.label}</span>: RTF{' '}
              <span className="font-bold text-white">{hoveredHour.rtf.toFixed(2)}x</span> (
              {hoveredHour.count} transmissions, {hoveredHour.audio_s.toFixed(0)}s audio,{' '}
              {hoveredHour.proc_s.toFixed(0)}s processing)
            </span>
          ) : (
            <span className="text-gray-500">Hover over any hour to inspect inference performance</span>
          )}
        </div>
      </div>
    </div>
  )
}
