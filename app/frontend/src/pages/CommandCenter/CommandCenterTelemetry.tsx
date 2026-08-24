import { useState } from 'react'
import { Link } from 'react-router-dom'
import { OdometerValue } from '@/components/ui/OdometerValue'
import type { PipelineEvent } from '@/pages/Events/IncidentsPage'
import type { InsightsSummary } from '@/types/insights'

interface CommandCenterTelemetryProps {
  events: PipelineEvent[]
  liveCpm: number | null
  insightsSummary: InsightsSummary | null
}

export function CommandCenterTelemetry({
  events,
  liveCpm,
  insightsSummary,
}: CommandCenterTelemetryProps) {
  const [isOpen, setIsOpen] = useState(false)

  const openIncidentsCount = events.filter((e) => e.status === 'open').length
  const mappedCount = events.filter((e) => typeof e.latitude === 'number' && typeof e.longitude === 'number').length
  const mappingRate = events.length > 0 ? Math.round((mappedCount / events.length) * 100) : 0

  return (
    <div className="ss-cc-drawer">
      {/* Drawer Handle Bar */}
      <div
        className="ss-cc-drawer-bar"
        onClick={() => setIsOpen((prev) => !prev)}
        role="button"
        tabIndex={0}
        aria-expanded={isOpen}
        aria-label="Toggle Insights Telemetry"
      >
        <div className="flex items-center gap-6">
          <div className="flex items-center gap-2">
            <span className="text-sm">📈</span>
            <span className="text-xs font-bold uppercase tracking-wider text-gray-200">
              Live Telemetry & Insights
            </span>
          </div>

          {/* Quick inline metric ticker when collapsed */}
          <div className="hidden sm:flex items-center gap-4 text-xs">
            <div className="flex items-center gap-1.5 bg-black/30 px-2 py-0.5 rounded border border-white/5">
              <span className="text-gray-400">Calls / min:</span>
              <span className="font-bold text-emerald-400">
                <OdometerValue value={liveCpm ?? 0} decimals={0} />
              </span>
            </div>
            <div className="flex items-center gap-1.5 bg-black/30 px-2 py-0.5 rounded border border-white/5">
              <span className="text-gray-400">Active Incidents:</span>
              <span className="font-bold text-indigo-400">{openIncidentsCount}</span>
            </div>
            <div className="flex items-center gap-1.5 bg-black/30 px-2 py-0.5 rounded border border-white/5">
              <span className="text-gray-400">Geocoded:</span>
              <span className="font-bold text-cyan-400">{mappingRate}%</span>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <span className="text-xs text-indigo-300 hover:text-indigo-200 transition">
            {isOpen ? 'Minimize ▼' : 'Expand Insights ▲'}
          </span>
        </div>
      </div>

      {/* Expanded Metrics Drawer Content */}
      {isOpen && (
        <div className="ss-cc-drawer-content">
          <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3">
            {/* Calls Per Minute */}
            <div className="ss-metric-card bg-black/40 border-white/10">
              <p className="ss-metric-label">Calls / Min</p>
              <p className="ss-metric-value text-emerald-400">
                <OdometerValue value={liveCpm ?? 0} decimals={0} />
              </p>
            </div>

            {/* Active Open Incidents */}
            <div className="ss-metric-card bg-black/40 border-white/10">
              <p className="ss-metric-label">Open Incidents</p>
              <p className="ss-metric-value text-indigo-300">{openIncidentsCount}</p>
            </div>

            {/* Map Geocode Coverage */}
            <div className="ss-metric-card bg-black/40 border-white/10">
              <p className="ss-metric-label">Map Resolution</p>
              <p className="ss-metric-value text-cyan-400">
                {mappedCount} <span className="text-xs text-gray-500 font-normal">/ {events.length}</span>
              </p>
            </div>

            {/* Total Transcriptions Today */}
            <div className="ss-metric-card bg-black/40 border-white/10">
              <p className="ss-metric-label">Today Transcriptions</p>
              <p className="ss-metric-value text-white">
                <OdometerValue value={insightsSummary?.total ?? 0} decimals={0} />
              </p>
            </div>

            {/* Unique Talkgroups */}
            <div className="ss-metric-card bg-black/40 border-white/10">
              <p className="ss-metric-label">Active Talkgroups</p>
              <p className="ss-metric-value text-amber-300">
                {insightsSummary?.unique_talkgroups ?? 0}
              </p>
            </div>

            {/* Full Hub Link Card */}
            <div className="ss-metric-card bg-indigo-950/30 border-indigo-500/20 flex flex-col justify-center gap-1.5">
              <p className="text-[11px] font-semibold text-indigo-300">Full Analytics Hub</p>
              <div className="flex gap-2 text-xs">
                <Link
                  to="/insights"
                  className="text-white hover:text-indigo-200 underline font-medium"
                >
                  Insights →
                </Link>
                <Link
                  to="/events"
                  className="text-white hover:text-indigo-200 underline font-medium"
                >
                  Events →
                </Link>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
