import { useMemo } from 'react'
import type { AsrQualitySpectrum } from '@/types/insights'
import { WidgetInfoTooltip } from './WidgetInfoTooltip'

interface AsrConfidenceWidgetProps {
  data?: AsrQualitySpectrum
}

function SignalQualityIcon({ className = '' }: { className?: string }) {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" className={`h-4 w-4 shrink-0 ${className}`} fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
      <path d="M2 13h1.5M5 10h1.5M8 7h1.5M11 4h1.5M14 1.5h.5" strokeLinecap="round" strokeWidth="2" />
    </svg>
  )
}

function SparkleIcon({ className = '' }: { className?: string }) {
  return (
    <svg width="14" height="14" viewBox="0 0 16 16" className={`h-3.5 w-3.5 shrink-0 ${className}`} fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
      <path d="M8 1v14M1 8h14M3 3l10 10M13 3L3 13" strokeLinecap="round" />
    </svg>
  )
}

export function AsrConfidenceWidget({ data }: AsrConfidenceWidgetProps) {
  // Unconditional hook resolution
  const spectrum = useMemo(() => {
    if (!data) return null
    return data
  }, [data])

  if (!spectrum) {
    return (
      <div className="ss-glass-panel relative flex min-h-[300px] flex-col items-center justify-center p-8 text-center text-sm text-gray-500">
        <SignalQualityIcon className="mb-2 h-6 w-6 text-gray-600" />
        <p>Analyzing speech recognition confidence metrics...</p>
      </div>
    )
  }

  if (spectrum.total_evaluated === 0) {
    return (
      <div className="ss-glass-panel relative flex min-h-[300px] flex-col items-center justify-center p-8 text-center text-sm text-gray-500">
        <SignalQualityIcon className="mb-2 h-6 w-6 text-gray-600" />
        <p className="font-medium text-gray-300">ASR Signal Quality Spectrum</p>
        <p className="mt-1 text-xs">No transcriptions with confidence scores in the selected range.</p>
      </div>
    )
  }

  const {
    high_count,
    high_percentage,
    moderate_count,
    moderate_percentage,
    low_count,
    low_percentage,
    mean_confidence,
    total_evaluated,
    insufficient_data,
  } = spectrum

  const getConfidenceRating = (score: number) => {
    if (score >= 85) {
      return {
        label: 'Optimal Fidelity',
        color: 'text-emerald-400 bg-emerald-500/10 border-emerald-500/30',
        dot: 'bg-emerald-400',
      }
    }
    if (score >= 75) {
      return {
        label: 'Moderate Clarity',
        color: 'text-amber-400 bg-amber-500/10 border-amber-500/30',
        dot: 'bg-amber-400',
      }
    }
    return {
      label: 'Degraded RF',
      color: 'text-rose-400 bg-rose-500/10 border-rose-500/30',
      dot: 'bg-rose-400',
    }
  }

  const rating = getConfidenceRating(mean_confidence)

  return (
    <div className="ss-glass-panel relative flex flex-col justify-between overflow-hidden p-5">
      <div>
        {/* Header */}
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-gray-800/80 pb-3">
          <div className="flex items-center gap-2.5">
            <div className="flex h-7 w-7 items-center justify-center rounded-lg border border-emerald-500/30 bg-emerald-500/10 text-emerald-400">
              <SignalQualityIcon className="h-4 w-4" />
            </div>
            <div>
              <div className="flex items-center gap-1.5">
                <h3 className="text-sm font-semibold text-gray-100">ASR Signal Quality Spectrum</h3>
                <WidgetInfoTooltip
                  title="ASR Signal Quality Spectrum"
                  description="Evaluates Whisper speech-to-text token transition logit probabilities across radio transmissions to gauge RF clarity and transcription fidelity."
                  bullets={[
                    'High Fidelity (≥ 85%): Clean RF signal with optimal word accuracy.',
                    'Marginal RF (70–84%): Slight background noise, squelch, or sirens.',
                    'Weak RF (< 70%): Heavy static, multipath distortion, or clipping.',
                  ]}
                />
              </div>
              <p className="text-xs text-gray-400">Whisper token transition logit confidence and RF clarity tiers</p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            {insufficient_data && (
              <span
                className="rounded border border-amber-500/30 bg-amber-500/10 px-1.5 py-0.5 text-[10px] font-medium text-amber-400"
                title="Fewer than 10 scored transmissions; percentages are not yet representative."
              >
                Low sample ({total_evaluated})
              </span>
            )}
            <div className={`flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium ${rating.color}`}>
              <span className={`h-1.5 w-1.5 rounded-full ${rating.dot}`} />
              {rating.label}
            </div>
          </div>
        </div>

        {/* Top Metric Highlights */}
        <div className="mt-3 grid grid-cols-2 gap-2.5 sm:grid-cols-3">
          <div className="rounded-lg border border-gray-800/80 bg-gray-950/40 p-2.5">
            <span className="block text-[10px] font-medium uppercase tracking-wider text-gray-400">Mean Confidence</span>
            <span className="font-mono text-base font-semibold text-emerald-400">
              {mean_confidence.toFixed(1)}%
            </span>
            <span className="ml-1 text-[11px] text-gray-400">avg logit</span>
          </div>

          <div className="rounded-lg border border-gray-800/80 bg-gray-950/40 p-2.5">
            <span className="block text-[10px] font-medium uppercase tracking-wider text-gray-400">High Fidelity Share</span>
            <span className="font-mono text-base font-semibold text-emerald-300">
              {high_percentage.toFixed(1)}%
            </span>
            <span className="ml-1 text-[11px] text-gray-400">(&ge; 85% conf)</span>
          </div>

          <div className="col-span-2 rounded-lg border border-gray-800/80 bg-gray-950/40 p-2.5 sm:col-span-1">
            <span className="block text-[10px] font-medium uppercase tracking-wider text-gray-400">Transmissions Audited</span>
            <span className="font-mono text-base font-semibold text-gray-100">
              {total_evaluated.toLocaleString()}
            </span>
            <span className="ml-1 text-[11px] text-gray-400">calls</span>
          </div>
        </div>

        {/* Stacked Quality Bar */}
        <div className="mt-4">
          <div className="mb-1.5 flex items-center justify-between text-xs text-gray-400">
            <span className="font-medium text-gray-300">Confidence Distribution</span>
            <span className="font-mono text-[11px]">
              {high_percentage.toFixed(0)}% / {moderate_percentage.toFixed(0)}% / {low_percentage.toFixed(0)}%
            </span>
          </div>
          <div className="flex h-3 w-full overflow-hidden rounded-full bg-gray-800/80 p-0.5">
            <div
              style={{ width: `${high_percentage}%` }}
              className="h-full rounded-l-full bg-emerald-500 transition-all duration-300 hover:brightness-125"
              title={`High Fidelity: ${high_count} (${high_percentage}%)`}
            />
            <div
              style={{ width: `${moderate_percentage}%` }}
              className="h-full bg-amber-500 transition-all duration-300 hover:brightness-125"
              title={`Moderate Quality: ${moderate_count} (${moderate_percentage}%)`}
            />
            <div
              style={{ width: `${low_percentage}%` }}
              className="h-full rounded-r-full bg-rose-500 transition-all duration-300 hover:brightness-125"
              title={`Weak Signal: ${low_count} (${low_percentage}%)`}
            />
          </div>
        </div>

        {/* Detailed Tiers Cards */}
        <div className="mt-4 grid grid-cols-1 gap-2.5 sm:grid-cols-3">
          {/* High Fidelity Tier */}
          <div className="rounded-lg border border-emerald-500/20 bg-emerald-500/5 p-3">
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold text-emerald-300">High Fidelity</span>
              <span className="font-mono text-xs font-bold text-emerald-400">{high_percentage.toFixed(1)}%</span>
            </div>
            <div className="mt-1 flex items-baseline gap-1">
              <span className="font-mono text-sm font-semibold text-gray-100">{high_count.toLocaleString()}</span>
              <span className="text-[10px] text-gray-400">calls</span>
            </div>
            <p className="mt-1.5 text-[11px] leading-tight text-gray-400">
              Optimal audio SNR; flawless token confidence and word clarity.
            </p>
          </div>

          {/* Moderate Tier */}
          <div className="rounded-lg border border-amber-500/20 bg-amber-500/5 p-3">
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold text-amber-300">Marginal RF</span>
              <span className="font-mono text-xs font-bold text-amber-400">{moderate_percentage.toFixed(1)}%</span>
            </div>
            <div className="mt-1 flex items-baseline gap-1">
              <span className="font-mono text-sm font-semibold text-gray-100">{moderate_count.toLocaleString()}</span>
              <span className="text-[10px] text-gray-400">calls</span>
            </div>
            <p className="mt-1.5 text-[11px] leading-tight text-gray-400">
              Minor background squelch or siren interference; fully legible.
            </p>
          </div>

          {/* Weak / Degraded Tier */}
          <div className="rounded-lg border border-rose-500/20 bg-rose-500/5 p-3">
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold text-rose-300">Weak / Noisy</span>
              <span className="font-mono text-xs font-bold text-rose-400">{low_percentage.toFixed(1)}%</span>
            </div>
            <div className="mt-1 flex items-baseline gap-1">
              <span className="font-mono text-sm font-semibold text-gray-100">{low_count.toLocaleString()}</span>
              <span className="text-[10px] text-gray-400">calls</span>
            </div>
            <p className="mt-1.5 text-[11px] leading-tight text-gray-400">
              Low signal strength, multipath distortion, or radio clipping.
            </p>
          </div>
        </div>
      </div>

      {/* Footer Info */}
      <div className="mt-4 flex items-center justify-between border-t border-gray-800/60 pt-3 text-[11px] text-gray-400">
        <div className="flex items-center gap-1.5">
          <SparkleIcon className="h-3 w-3 text-emerald-400" />
          <span>Whisper token probabilities calibrated via log-mel spectrogram</span>
        </div>
        <span className="font-mono text-gray-400">Score &gt; 85% = High</span>
      </div>
    </div>
  )
}
