import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import type { DiurnalHeatmapData, HeatmapHourCell } from '@/types/insights'
import { WidgetInfoTooltip } from './WidgetInfoTooltip'

interface DiurnalHeatmapProps {
  data?: DiurnalHeatmapData
  dateFrom?: string
  dateTo?: string
}

function MatrixIcon({ className = '' }: { className?: string }) {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" className={`h-4 w-4 shrink-0 ${className}`} fill="none" stroke="currentColor" strokeWidth="1.4" aria-hidden="true">
      <rect x="2" y="2" width="3" height="3" rx="0.5" />
      <rect x="6.5" y="2" width="3" height="3" rx="0.5" />
      <rect x="11" y="2" width="3" height="3" rx="0.5" />
      <rect x="2" y="6.5" width="3" height="3" rx="0.5" />
      <rect x="6.5" y="6.5" width="3" height="3" rx="0.5" />
      <rect x="11" y="6.5" width="3" height="3" rx="0.5" />
      <rect x="2" y="11" width="3" height="3" rx="0.5" />
      <rect x="6.5" y="11" width="3" height="3" rx="0.5" />
      <rect x="11" y="11" width="3" height="3" rx="0.5" />
    </svg>
  )
}

export function DiurnalHeatmap({ data, dateFrom, dateTo }: DiurnalHeatmapProps) {
  const navigate = useNavigate()
  const [hovered, setHovered] = useState<{
    day: string
    cell: HeatmapHourCell
    x: number
    y: number
  } | null>(null)

  if (!data || !data.matrix || data.matrix.length === 0) {
    return (
      <div className="ss-glass-panel py-8 text-center text-xs text-gray-500">
        No diurnal activity recorded for this period.
      </div>
    )
  }

  const { matrix, max_count, total_calls, total_airtime, peak_day, peak_hour, range_start, range_end } = data

  const getCellColor = (count: number) => {
    if (count === 0 || max_count === 0) {
      return 'rgba(255, 255, 255, 0.03)'
    }
    const ratio = count / max_count
    // Gradual indigo ramp from 0.18 to 0.95 opacity
    const alpha = (0.2 + ratio * 0.75).toFixed(2)
    return `rgba(99, 102, 241, ${alpha})`
  }

  const handleCellClick = (hour: number) => {
    const params = new URLSearchParams()
    if (dateFrom) params.set('date_from', dateFrom)
    if (dateTo) params.set('date_to', dateTo)
    params.set('hour', String(hour))
    navigate(`/search?${params.toString()}`)
  }

  return (
    <div className="ss-glass-panel space-y-4">
      {/* Header & Metric Badges */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-white/10 pb-3">
        <div>
          <div className="flex items-center gap-2">
            <MatrixIcon className="h-4 w-4 text-indigo-400" />
            <h2 className="text-sm font-semibold text-gray-200">Diurnal Activity Pattern</h2>
            <WidgetInfoTooltip
              title="Diurnal Activity Heatmap"
              description="Plots radio transmission density across a 7-day by 24-hour matrix to identify recurring peak shift hours and historical dispatch cycles."
              bullets={[
                'Cell Intensity: Color saturation corresponds to transmission volume.',
                'Day of Week Patterns: Exposes diurnal trends and shift transition spikes.',
                'Interactive Filter: Click any hourly cell to jump directly into Search.',
              ]}
            />
            <span className="text-xs text-gray-500">
              ({range_start} to {range_end})
            </span>
          </div>
          <p className="mt-0.5 text-xs text-gray-400">
            24-hour transmission intensity by day of week. Click any hour cell to inspect in Search.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-3 text-xs">
          <div className="rounded bg-white/5 px-2.5 py-1 text-gray-300">
            <span className="text-gray-500">Peak Day: </span>
            <strong className="text-indigo-300">{peak_day}</strong>
          </div>
          <div className="rounded bg-white/5 px-2.5 py-1 text-gray-300">
            <span className="text-gray-500">Peak Hour: </span>
            <strong className="text-indigo-300">{peak_hour}</strong>
          </div>
          <div className="rounded bg-white/5 px-2.5 py-1 text-gray-300">
            <span className="text-gray-500">Total Airtime: </span>
            <strong className="text-gray-200">{(total_airtime / 60).toFixed(1)}m</strong>
          </div>
        </div>
      </div>

      {/* Heatmap Grid Container */}
      <div className="relative overflow-x-auto">
        <div className="min-w-[680px]">
          {/* Hour Labels Header */}
          <div className="mb-1 flex items-center text-[10px] text-gray-500">
            <div className="w-12 shrink-0 text-right pr-2">Day</div>
            <div className="grid flex-1 grid-cols-[repeat(24,minmax(0,1fr))] gap-1">
              {Array.from({ length: 24 }, (_, h) => (
                <div key={h} className="text-center font-mono">
                  {h % 3 === 0 ? `${h}h` : ''}
                </div>
              ))}
            </div>
            <div className="w-14 shrink-0 text-right pl-2">Total</div>
          </div>

          {/* Matrix Rows */}
          <div className="space-y-1">
            {matrix.map((row) => (
              <div key={row.day} className="flex items-center">
                {/* Day Label */}
                <div className="w-12 shrink-0 text-right pr-2 text-xs font-medium text-gray-400">
                  {row.day_label}
                </div>

                {/* 24 Hour Cells */}
                <div className="grid flex-1 grid-cols-[repeat(24,minmax(0,1fr))] gap-1">
                  {row.hours.map((cell) => {
                    return (
                      <button
                        key={cell.hour}
                        type="button"
                        onClick={() => handleCellClick(cell.hour)}
                        onMouseEnter={(e) => {
                          const rect = e.currentTarget.getBoundingClientRect()
                          setHovered({
                            day: row.day_label,
                            cell,
                            x: rect.left + rect.width / 2,
                            y: rect.top,
                          })
                        }}
                        onMouseLeave={() => setHovered(null)}
                        style={{ backgroundColor: getCellColor(cell.count) }}
                        className="group relative h-6 rounded border border-white/5 transition-all hover:scale-110 hover:border-indigo-400 hover:z-20 focus:outline-none"
                        aria-label={`${row.day_label} ${cell.label}: ${cell.count} calls`}
                      />
                    )
                  })}
                </div>

                {/* Row Total */}
                <div className="w-14 shrink-0 text-right pl-2 font-mono text-xs text-gray-400">
                  {row.day_total}
                </div>
              </div>
            ))}
          </div>

          {/* Color Scale Legend */}
          <div className="mt-4 flex items-center justify-between border-t border-white/5 pt-3 text-[11px] text-gray-500">
            <div className="flex items-center gap-1.5">
              <span>Less</span>
              <div className="flex items-center gap-0.5">
                <div className="h-3 w-4 rounded-sm border border-white/5 bg-white/[0.03]" />
                <div className="h-3 w-4 rounded-sm border border-white/5 bg-indigo-500/20" />
                <div className="h-3 w-4 rounded-sm border border-white/5 bg-indigo-500/40" />
                <div className="h-3 w-4 rounded-sm border border-white/5 bg-indigo-500/65" />
                <div className="h-3 w-4 rounded-sm border border-white/5 bg-indigo-500/90" />
              </div>
              <span>More</span>
            </div>
            <div>
              <span>Peak call volume in period: </span>
              <strong className="font-mono text-gray-300">{max_count} calls/hr</strong>
            </div>
          </div>
        </div>
      </div>

      {/* Floating Hover Tooltip */}
      {hovered && (
        <div
          className="pointer-events-none fixed z-50 -translate-x-1/2 -translate-y-full rounded-md border border-white/15 bg-gray-950/95 px-3 py-2 text-xs shadow-2xl backdrop-blur-md transition-transform"
          style={{
            left: hovered.x,
            top: hovered.y - 8,
          }}
        >
          <div className="font-semibold text-gray-200">
            {hovered.day} at {hovered.cell.label}
          </div>
          <div className="mt-1 flex items-center gap-3 text-gray-400">
            <span>
              Calls: <strong className="font-mono text-indigo-300">{hovered.cell.count}</strong>
            </span>
            <span>
              Airtime: <strong className="font-mono text-gray-200">{hovered.cell.duration}s</strong>
            </span>
          </div>
          {total_calls > 0 && hovered.cell.count > 0 && (
            <div className="mt-0.5 text-[10px] text-gray-500">
              {((hovered.cell.count / total_calls) * 100).toFixed(1)}% of period traffic
            </div>
          )}
        </div>
      )}
    </div>
  )
}
