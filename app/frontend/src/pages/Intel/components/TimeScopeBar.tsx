interface TimeScopeBarProps {
  showTools: boolean
  onChangeShowTools: (value: boolean) => void
  showThinking: boolean
  onChangeShowThinking: (value: boolean) => void
  disabled?: boolean
  audioCount?: number
  audioPanelOpen?: boolean
  onToggleAudioPanel?: () => void
}

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
      <span className="font-medium text-[11px]">{label}</span>
    </button>
  )
}

export function TimeScopeBar({
  showTools,
  onChangeShowTools,
  showThinking,
  onChangeShowThinking,
  audioCount = 0,
  audioPanelOpen = false,
  onToggleAudioPanel,
}: TimeScopeBarProps) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 px-4 py-2 bg-[#141721] border-b border-[#252836] text-xs shrink-0 select-none">
      {/* Intelligent Scoping Status Badge */}
      <div className="flex items-center gap-2">
        <span className="flex h-2 w-2 relative">
          <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
          <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
        </span>
        <span className="text-xs font-semibold text-gray-200">
          Agentic Time Scoping Active
        </span>
        <span className="text-[11px] text-gray-400 font-mono hidden sm:inline">
          (Specify time in query; e.g. "today around 3pm", "past 2 hours")
        </span>
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
