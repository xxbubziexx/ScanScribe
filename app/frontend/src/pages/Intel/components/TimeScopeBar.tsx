import { useState } from 'react'

import type { ChatTimeScope } from '@/types/chat'

interface TimeScopeBarProps {
  timeScope: ChatTimeScope
  onChangeTimeScope: (scope: ChatTimeScope) => void
  availableTalkgroups: string[]
  selectedTalkgroups: string[]
  onChangeTalkgroups: (tgs: string[]) => void
  disabled?: boolean
}

const PRESETS: { id: ChatTimeScope['preset']; label: string }[] = [
  { id: '1h', label: 'Past 1h' },
  { id: '4h', label: 'Past 4h' },
  { id: '12h', label: 'Past 12h' },
  { id: 'today', label: 'Today' },
  { id: 'yesterday', label: 'Yesterday' },
  { id: 'custom', label: 'Custom' },
]

export function TimeScopeBar({
  timeScope,
  onChangeTimeScope,
  availableTalkgroups,
  selectedTalkgroups,
  onChangeTalkgroups,
  disabled = false,
}: TimeScopeBarProps) {

  const [showTgDropdown, setShowTgDropdown] = useState(false)
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

  const toggleTalkgroup = (tg: string) => {
    if (disabled) return
    if (selectedTalkgroups.includes(tg)) {
      onChangeTalkgroups(selectedTalkgroups.filter((item) => item !== tg))
    } else {
      onChangeTalkgroups([...selectedTalkgroups, tg])
    }
  }

  return (
    <div className="flex flex-wrap items-center justify-between gap-3 px-4 py-2.5 bg-[#141721] border-b border-[#252836] text-xs">
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

      {/* Talkgroups Dropdown */}
      <div className="relative">
        <button
          type="button"
          disabled={disabled}
          onClick={() => setShowTgDropdown(!showTgDropdown)}
          className="flex items-center gap-1.5 px-3 py-1 bg-[#1e2230] hover:bg-[#282d3f] text-gray-200 rounded border border-[#2e3347] transition-colors"
        >
          <span className="text-gray-400">Talkgroups:</span>
          <span className="font-semibold text-indigo-400">
            {selectedTalkgroups.length === 0
              ? 'All Channels'
              : `${selectedTalkgroups.length} Selected`}
          </span>
          <span className="text-[10px] text-gray-500">▼</span>
        </button>

        {showTgDropdown && (
          <div className="absolute right-0 mt-1 w-64 max-h-64 overflow-y-auto bg-[#181b26] border border-[#2e3347] rounded-md shadow-xl z-30 p-2 text-xs">
            <div className="flex items-center justify-between pb-1.5 mb-1.5 border-b border-[#252836]">
              <span className="text-gray-400 font-medium">Filter Channels</span>
              {selectedTalkgroups.length > 0 && (
                <button
                  type="button"
                  onClick={() => onChangeTalkgroups([])}
                  className="text-[11px] text-indigo-400 hover:underline"
                >
                  Clear All
                </button>
              )}
            </div>
            {availableTalkgroups.length === 0 ? (
              <p className="text-gray-500 text-center py-2">No talkgroups found</p>
            ) : (
              <div className="space-y-1">
                {availableTalkgroups.map((tg) => {
                  const checked = selectedTalkgroups.includes(tg)
                  return (
                    <label
                      key={tg}
                      className="flex items-center gap-2 px-1.5 py-1 rounded hover:bg-[#222636] cursor-pointer"
                    >
                      <input
                        type="checkbox"
                        checked={checked}
                        onChange={() => toggleTalkgroup(tg)}
                        className="rounded border-gray-600 text-indigo-600 focus:ring-0"
                      />
                      <span className="text-gray-200 truncate">{tg}</span>
                    </label>
                  )
                })}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
