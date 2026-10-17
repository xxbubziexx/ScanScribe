import { useState, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import type { TacticalNerSummary } from '@/types/insights'
import { WidgetInfoTooltip } from './WidgetInfoTooltip'

interface TacticalNerWidgetProps {
  data?: TacticalNerSummary
}

type TabCategory = 'all' | 'units' | 'call_types' | 'locations' | 'status'

function TagIcon({ className = '' }: { className?: string }) {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" className={`h-4 w-4 shrink-0 ${className}`} fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
      <path d="M1.5 8.5L7 3h6.5v6.5L8 15l-6.5-6.5z" strokeLinejoin="round" />
      <circle cx="10.5" cy="5.5" r="1" fill="currentColor" />
    </svg>
  )
}

function SearchIcon({ className = '' }: { className?: string }) {
  return (
    <svg width="14" height="14" viewBox="0 0 16 16" className={`h-3.5 w-3.5 shrink-0 ${className}`} fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
      <circle cx="7" cy="7" r="4.5" />
      <path d="M10.5 10.5L14 14" strokeLinecap="round" />
    </svg>
  )
}

function ExternalJumpIcon({ className = '' }: { className?: string }) {
  return (
    <svg width="12" height="12" viewBox="0 0 16 16" className={`h-3 w-3 shrink-0 ${className}`} fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
      <path d="M6 3h7v7M13 3L6 10" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

export function TacticalNerWidget({ data }: TacticalNerWidgetProps) {
  const navigate = useNavigate()
  const [activeTab, setActiveTab] = useState<TabCategory>('all')
  const [searchQuery, setSearchQuery] = useState('')

  const all = data?.all ?? []
  const units = data?.units ?? []
  const call_types = data?.call_types ?? []
  const locations = data?.locations ?? []
  const status = data?.status ?? []
  const total_entities_detected = data?.total_entities_detected ?? 0
  const insufficient_data = data?.insufficient_data ?? false

  const currentList = useMemo(() => {
    switch (activeTab) {
      case 'units':
        return units
      case 'call_types':
        return call_types
      case 'locations':
        return locations
      case 'status':
        return status
      case 'all':
      default:
        return all
    }
  }, [activeTab, all, units, call_types, locations, status])

  const filteredItems = useMemo(() => {
    if (!searchQuery.trim()) return currentList
    const q = searchQuery.toLowerCase().trim()
    return currentList.filter(
      (item) => item.canonical.toLowerCase().includes(q) || item.label.toLowerCase().includes(q)
    )
  }, [currentList, searchQuery])

  const maxFreq = useMemo(() => {
    return Math.max(1, ...currentList.map((i) => i.freq))
  }, [currentList])

  if (!data) {
    return (
      <div className="ss-glass-panel relative flex min-h-[300px] items-center justify-center p-8 text-sm text-gray-500">
        Loading tactical NER intelligence...
      </div>
    )
  }

  if (insufficient_data) {
    return (
      <div className="ss-glass-panel relative flex min-h-[200px] flex-col items-center justify-center p-8 text-center">
        <p className="text-sm font-medium text-gray-300">NER Entity &amp; Tactical Semantics</p>
        <p className="mt-1 text-xs text-gray-500">No extracted entities in the selected range.</p>
      </div>
    )
  }

  const getLabelBadge = (label: string) => {
    switch (label.toUpperCase()) {
      case 'UNIT':
        return {
          text: 'UNIT',
          styles: 'bg-sky-500/15 text-sky-300 border-sky-500/30',
          barColor: 'bg-sky-500/50',
        }
      case 'EVT_TYPE':
        return {
          text: 'CALL TYPE',
          styles: 'bg-amber-500/15 text-amber-300 border-amber-500/30',
          barColor: 'bg-amber-500/50',
        }
      case 'LOC':
      case 'ADDRESS':
        return {
          text: 'LOCATION',
          styles: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30',
          barColor: 'bg-emerald-500/50',
        }
      case 'STATUS':
        return {
          text: 'STATUS',
          styles: 'bg-purple-500/15 text-purple-300 border-purple-500/30',
          barColor: 'bg-purple-500/50',
        }
      default:
        return {
          text: label,
          styles: 'bg-gray-500/15 text-gray-300 border-gray-500/30',
          barColor: 'bg-gray-500/50',
        }
    }
  }

  const handleEntityClick = (canonical: string) => {
    navigate(`/search?keyword=${encodeURIComponent(canonical)}`)
  }

  return (
    <div className="ss-glass-panel relative z-10 flex flex-col justify-between">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-white/5 pb-3">
        <div className="flex items-center gap-2">
          <TagIcon className="h-4 w-4 text-sky-400" />
          <h3 className="text-sm font-semibold tracking-wide text-gray-200">
            NER Entity & Tactical Semantics
          </h3>
          <WidgetInfoTooltip
            title="NER Entity & Tactical Semantics"
            description="Extracts tactical entities and operational terminology from radio transcripts using fine-tuned Named Entity Recognition models."
            bullets={[
              'Units: Responding apparatus, officer callsigns, and squad identifiers.',
              'Call Types & Locations: Incident classifications, highways, and street addresses.',
              'Status: Operational status markers (10-4, on-scene, in-service, en-route).',
            ]}
          />
        </div>

        <span className="font-mono text-xs text-gray-400">
          <span className="font-bold text-white">{total_entities_detected}</span> total observations
        </span>
      </div>

      {/* Tabs & Search Controls */}
      <div className="mt-3 flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-1 rounded-lg border border-white/5 bg-black/30 p-1 text-xs">
          {(
            [
              { id: 'all', label: 'All', count: all.length },
              { id: 'units', label: 'Units', count: units.length },
              { id: 'call_types', label: 'Call Types', count: call_types.length },
              { id: 'locations', label: 'Locations', count: locations.length },
              { id: 'status', label: 'Status', count: status.length },
            ] as const
          ).map((tab) => {
            const isActive = activeTab === tab.id
            return (
              <button
                key={tab.id}
                type="button"
                onClick={() => setActiveTab(tab.id)}
                className={`flex items-center gap-1.5 rounded-md px-2.5 py-1 font-medium transition-colors ${
                  isActive
                    ? 'bg-white/10 text-white shadow-xs'
                    : 'text-gray-400 hover:text-gray-200'
                }`}
              >
                <span>{tab.label}</span>
                <span
                  className={`rounded-full px-1.5 py-0.2 text-[10px] font-mono ${
                    isActive ? 'bg-sky-500/20 text-sky-300' : 'bg-white/5 text-gray-500'
                  }`}
                >
                  {tab.count}
                </span>
              </button>
            )
          })}
        </div>

        {/* Search input */}
        <div className="relative min-w-[140px] flex-1 sm:max-w-[200px]">
          <SearchIcon className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-gray-500" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Filter entities..."
            className="w-full rounded-md border border-white/10 bg-black/40 py-1 pr-2.5 pl-8 text-xs text-gray-200 placeholder:text-gray-500 focus:border-sky-500/50 focus:outline-hidden"
          />
        </div>
      </div>

      {/* Entity Cards / List */}
      <div className="mt-3 max-h-[260px] min-h-[220px] space-y-1.5 overflow-y-auto pr-1">
        {filteredItems.length === 0 ? (
          <div className="flex h-36 items-center justify-center text-xs text-gray-500">
            No entities found matching your search.
          </div>
        ) : (
          filteredItems.map((item, idx) => {
            const badge = getLabelBadge(item.label)
            const widthPct = Math.max(6, (item.freq / maxFreq) * 100)

            return (
              <div
                key={`${item.label}-${item.canonical}-${idx}`}
                onClick={() => handleEntityClick(item.canonical)}
                className="group flex cursor-pointer items-center justify-between gap-3 rounded-lg border border-white/5 bg-black/20 px-3 py-2 transition-all hover:border-sky-500/30 hover:bg-white/[0.04]"
                title={`Filter transcriptions mentioning ${item.canonical}`}
              >
                {/* Left: Badge + Name */}
                <div className="flex min-w-0 items-center gap-2.5">
                  <span
                    className={`shrink-0 rounded border px-1.5 py-0.5 text-[10px] font-semibold tracking-wider uppercase ${badge.styles}`}
                  >
                    {badge.text}
                  </span>
                  <span className="truncate text-xs font-medium text-gray-200 group-hover:text-white">
                    {item.canonical}
                  </span>
                </div>

                {/* Right: Frequency & Jump Icon */}
                <div className="flex shrink-0 items-center gap-3">
                  <div className="flex w-24 items-center gap-2">
                    <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-white/5">
                      <div
                        style={{ width: `${widthPct}%` }}
                        className={`h-full rounded-full transition-all ${badge.barColor}`}
                      />
                    </div>
                    <span className="font-mono text-xs font-semibold text-gray-300">
                      {item.freq}
                    </span>
                  </div>

                  <span className="text-gray-600 transition-colors group-hover:text-sky-400">
                    <ExternalJumpIcon className="h-3.5 w-3.5" />
                  </span>
                </div>
              </div>
            )
          })
        )}
      </div>

      {/* Footer hint */}
      <div className="mt-2 flex items-center justify-between border-t border-white/5 pt-2 text-[11px] text-gray-500">
        <span>Click any entity row to search and review related radio transmissions</span>
        <span className="font-mono text-[10px] text-gray-400">Incident NER v1</span>
      </div>
    </div>
  )
}
