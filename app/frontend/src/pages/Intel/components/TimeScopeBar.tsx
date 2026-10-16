import { useState } from 'react'

import type { ChatTimeScope } from '@/types/chat'

interface TimeScopeBarProps {
  timeScope: ChatTimeScope
  onChangeTimeScope: (scope: ChatTimeScope) => void
  showTools: boolean
  onChangeShowTools: (value: boolean) => void
  showThinking: boolean
  onChangeShowThinking: (value: boolean) => void
  disabled?: boolean
  audioCount?: number
  audioPanelOpen?: boolean
  onToggleAudioPanel?: () => void
}

const PRESETS: { id: ChatTimeScope['preset']; label: string }[] = [
  { id: '1h', label: 'Past 1h' },
  { id: '4h', label: 'Past 4h' },
  { id: '12h', label: 'Past 12h' },
  { id: 'today', label: 'Today' },
  { id: 'yesterday', label: 'Yesterday' },
  { id: 'custom', label: 'Custom' },
]

interface ViewToggleProps {
  id: string
  label: string
  checked: boolean
  onChange: (value: boolean) => void
}

function ViewToggle({ id, label, checked, onChange }: ViewToggleProps) {
  return (
    <button
      id={id}
      type="button"
      role="switch"
      aria-checked={checked}
      onClick={() => onChange(!checked)}
      className="flex items-center gap-2 px-2 py-1 rounded text-gray-300 hover:bg-[#1e2230] transition-colors cursor-pointer"
    >
      <span
        className={`relative inline-block w-7 h-4 rounded-full transition-colors ${
          checked ? 'bg-indigo-600' : 'bg-[#2b3045]'
        }`}
      >
        <span
          className={`absolute top-0.5 left-0.5 w-3 h-3 rounded-full bg-white transition-transform ${
            checked ? 'translate-x-3' : 'translate-x-0'
          }`}
        />
      </span>
      <span className="font-medium">{label}</span>
    </button>
  )
}

export function TimeScopeBar({
  timeScope,
  onChangeTimeScope,
  showTools,
  onChangeShowTools,
  showThinking,
  onChangeShowThinking,
  disabled = false,
  audioCount = 0,
  audioPanelOpen = false,
  onToggleAudioPanel,
}: TimeScopeBarProps) {
  const [customStart, setCustomStart] = useState(timeScope.start_time || '')
  const [customEnd, setCustomEnd] = useState(timeScope.end_time || '')

  const handlePresetClick = (preset: ChatTimeScope['preset']) => {
    if (disabled) return
    if (preset === 'custom') {
      onChangeTimeScope({
        preset: 'custom',
        start_time: customStart || new Date(Date.now() - 3600000 * 2).toISOString().slice(0, 16),
        end_time: customEnd || new Date().toISOString().slice(0, 16),
      })
    } else {
      onChangeTimeScope({ preset })
    }
  }

  const handleCustomApply = () => {
    if (disabled || !customStart) return
    onChangeTimeScope({
      preset: 'custom',
      start_time: customStart,
      end_time: customEnd || null,
    })
  }

  return (
    <div className="flex flex-wrap items-center justify-between gap-3 px-4 py-2 bg-[#141721] border-b border-[#252836] text-xs shrink-0">
      {/* Time Range Presets */}
      <div className="flex items-center gap-1.5 flex-wrap">
        <span className="text-gray-400 font-medium mr-1 uppercase tracking-wider text-[11px]">
          Time Scope:
        </span>
        {PRESETS.map((p) => {
          const isActive = timeScope.preset === p.id
          return (
            <button
              key={p.id}
              type="button"
              disabled={disabled}
              onClick={() => handlePresetClick(p.id)}
              className={`px-2.5 py-1 rounded transition-colors font-medium cursor-pointer disabled:opacity-50 ${
                isActive
                  ? 'bg-indigo-600 text-white shadow-sm'
                  : 'bg-[#1e2230] hover:bg-[#282d3f] text-gray-300'
              }`}
            >
              {p.label}
            </button>
          )
        })}

        {/* Custom Datetime Picker */}
        {timeScope.preset === 'custom' && (
          <div className="flex items-center gap-1.5 ml-2 bg-[#1a1d28] p-1 rounded border border-[#2b2f42]">
            <input
              type="datetime-local"
              value={customStart}
              onChange={(e) => setCustomStart(e.target.value)}
              className="bg-[#10121a] text-gray-200 px-1.5 py-0.5 rounded border border-[#33384c] text-[11px]"
              disabled={disabled}
            />
            <span className="text-gray-500">to</span>
            <input
              type="datetime-local"
              value={customEnd}
              onChange={(e) => setCustomEnd(e.target.value)}
              className="bg-[#10121a] text-gray-200 px-1.5 py-0.5 rounded border border-[#33384c] text-[11px]"
              disabled={disabled}
            />
            <button
              type="button"
              onClick={handleCustomApply}
              disabled={disabled || !customStart}
              className="px-2 py-0.5 bg-indigo-700 hover:bg-indigo-600 text-white rounded font-medium text-[11px]"
            >
              Apply
            </button>
          </div>
        )}
      </div>

      {/* Response detail toggles & Audio Panel Toggle */}
      <div className="flex items-center gap-2" role="group" aria-label="Response detail options">
        <ViewToggle id="intel-toggle-tools" label="Show tool calls" checked={showTools} onChange={onChangeShowTools} />
        <ViewToggle
          id="intel-toggle-thinking"
          label="Show thinking"
          checked={showThinking}
          onChange={onChangeShowThinking}
        />

        {onToggleAudioPanel && (
          <button
            type="button"
            onClick={onToggleAudioPanel}
            className={`flex items-center gap-1.5 px-2.5 py-1 rounded border text-xs font-medium transition-colors cursor-pointer ${
              audioPanelOpen
                ? 'bg-indigo-600 border-indigo-500 text-white shadow-xs'
                : 'bg-[#1e2230] hover:bg-[#282d3f] border-[#2b3045] text-gray-300'
            }`}
            title="Toggle Right-Side Audio Control Panel"
          >
            <span>📻</span>
            <span>Audio Deck</span>
            {audioCount > 0 && (
              <span
                className={`px-1.5 py-0.2 rounded-full text-[10px] font-mono font-bold ${
                  audioPanelOpen ? 'bg-indigo-800 text-white' : 'bg-[#2a3045] text-indigo-300'
                }`}
              >
                {audioCount}
              </span>
            )}
          </button>
        )}
      </div>
    </div>
  )
}
