interface IntelHeaderProps {
  title: string
  threadCount: number
  showTools: boolean
  onChangeShowTools: (value: boolean) => void
  showThinking: boolean
  onChangeShowThinking: (value: boolean) => void
  audioCount: number
  audioPanelOpen: boolean
  onToggleAudioPanel: () => void
  isStreaming?: boolean
  onOpenSidebar: () => void
}

export function IntelHeader({
  title,
  threadCount,
  showTools,
  onChangeShowTools,
  showThinking,
  onChangeShowThinking,
  audioCount,
  audioPanelOpen,
  onToggleAudioPanel,
  isStreaming = false,
  onOpenSidebar,
}: IntelHeaderProps) {
  return (
    <header className="px-4 py-2.5 bg-[#11131d]/95 backdrop-blur-md border-b border-[#222738] text-xs shrink-0 select-none shadow-xs">
      <div className="flex flex-wrap items-center justify-between gap-y-2 gap-x-4">
        {/* Left Side: Brand Indicator & Active Query Details */}
        <div className="flex items-center gap-3 min-w-0">
          {/* Mobile Drawer Trigger */}
          <button
            type="button"
            onClick={onOpenSidebar}
            className="md:hidden p-1.5 text-gray-400 hover:text-white bg-[#1a1d2c] hover:bg-[#252a3d] border border-[#282d42] rounded-lg transition-colors cursor-pointer"
            title="Open past queries"
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
            </svg>
          </button>

          {/* Instrument Icon Badge */}
          <div className="relative flex items-center justify-center w-8 h-8 rounded-lg bg-gradient-to-br from-indigo-950 via-[#181b2e] to-indigo-900/60 border border-indigo-500/30 text-indigo-400 shadow-inner shrink-0">
            <svg className="w-4 h-4 text-indigo-300" viewBox="0 0 24 24" fill="none" stroke="currentColor">
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={1.8}
                d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 100-6 3 3 0 000 6z"
              />
            </svg>
            <span className="absolute -top-0.5 -right-0.5 flex h-2 w-2">
              <span className={`absolute inline-flex h-full w-full rounded-full opacity-75 ${isStreaming ? 'animate-ping bg-indigo-400' : 'bg-emerald-400'}`} />
              <span className={`relative inline-flex rounded-full h-2 w-2 ${isStreaming ? 'bg-indigo-500' : 'bg-emerald-500'}`} />
            </span>
          </div>

          {/* Active Query Title & Operational Subtitle */}
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <h1 className="text-sm font-bold text-gray-100 truncate tracking-tight max-w-[240px] sm:max-w-md md:max-w-lg">
                {title || 'Scanner Intelligence'}
              </h1>
              <span className="hidden sm:inline-flex px-1.5 py-0.2 rounded font-mono text-[10px] font-semibold bg-indigo-950/70 border border-indigo-700/50 text-indigo-300">
                INTEL CORE
              </span>
            </div>

            <div className="flex items-center gap-2 text-[11px] text-gray-400 mt-0.5">
              <span className="inline-flex items-center gap-1.5 text-gray-400 font-mono">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 inline-block" />
                <span>Autonomous Scope Engine</span>
              </span>
              <span className="text-gray-600 hidden sm:inline">•</span>
              <span className="text-gray-500 hidden sm:inline font-mono">
                Natural-language time bounds enforced
              </span>
            </div>
          </div>
        </div>

        {/* Center / Mode Pill (Desktop Telemetry) */}
        <div className="hidden xl:flex items-center gap-2 px-3 py-1 rounded-full bg-[#161928] border border-[#252b40] text-[11px] font-mono text-gray-400 shadow-inner">
          {isStreaming ? (
            <div className="flex items-center gap-2 text-indigo-300">
              <span className="w-2 h-2 rounded-full bg-indigo-400 animate-ping" />
              <span className="font-semibold">Synthesizing Radio Intelligence...</span>
            </div>
          ) : (
            <div className="flex items-center gap-2">
              <span className="text-gray-500">Pipeline:</span>
              <span className="text-indigo-300 font-medium">Whisper ASR</span>
              <span className="text-gray-600">→</span>
              <span className="text-indigo-300 font-medium">Named Entity Recognition</span>
              <span className="text-gray-600">→</span>
              <span className="text-indigo-300 font-medium">LLM Reasoning</span>
            </div>
          )}
        </div>

        {/* Right Side: Tactical Controls & Audio Deck Toggle */}
        <div className="flex items-center gap-2 ml-auto">
          {/* View Toggles Container */}
          <div className="flex items-center gap-1.5 bg-[#151724] p-1 rounded-lg border border-[#252a3d]">
            {/* Show Tool Calls Toggle */}
            <button
              type="button"
              role="switch"
              aria-checked={showTools}
              onClick={() => onChangeShowTools(!showTools)}
              className={`flex items-center gap-1.5 px-2 py-1 rounded-md text-[11px] font-medium transition-all cursor-pointer ${
                showTools
                  ? 'bg-indigo-950/80 text-indigo-300 border border-indigo-700/60 shadow-xs'
                  : 'text-gray-400 hover:text-gray-200 hover:bg-[#1f2334] border border-transparent'
              }`}
              title="Toggle agent tool invocation cards in message history"
            >
              <svg className="w-3.5 h-3.5 opacity-80" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z"
                />
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
              </svg>
              <span>Tools</span>
            </button>

            {/* Show Thinking Toggle */}
            <button
              type="button"
              role="switch"
              aria-checked={showThinking}
              onClick={() => onChangeShowThinking(!showThinking)}
              className={`flex items-center gap-1.5 px-2 py-1 rounded-md text-[11px] font-medium transition-all cursor-pointer ${
                showThinking
                  ? 'bg-purple-950/80 text-purple-300 border border-purple-700/60 shadow-xs'
                  : 'text-gray-400 hover:text-gray-200 hover:bg-[#1f2334] border border-transparent'
              }`}
              title="Toggle chain-of-thought reasoning accordions"
            >
              <svg className="w-3.5 h-3.5 opacity-80" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z"
                />
              </svg>
              <span>Thinking</span>
            </button>
          </div>

          {/* Divider */}
          <div className="h-5 w-px bg-[#262b3f] hidden sm:block" />

          {/* Audio Deck Toggle Button */}
          <button
            type="button"
            onClick={onToggleAudioPanel}
            aria-expanded={audioPanelOpen}
            aria-controls="ss-audio-deck"
            className={`flex items-center gap-2 px-3 py-1.5 min-h-[40px] sm:min-h-[36px] rounded-lg border text-xs font-semibold transition-all cursor-pointer shadow-xs select-none ${
              audioPanelOpen
                ? 'bg-gradient-to-r from-indigo-600 to-indigo-700 border-indigo-400/60 text-white shadow-indigo-600/30'
                : 'bg-[#181c2b] hover:bg-[#22273c] border-[#292f45] hover:border-indigo-500/50 text-gray-200 hover:text-white'
            }`}
            title="Toggle Original Radio Transmission Audio Deck"
            aria-label="Toggle Original Radio Transmission Audio Deck"
          >
            <span className="text-sm">📻</span>
            <span>Audio Deck</span>
            {audioCount > 0 ? (
              <span
                className={`px-1.5 py-0.5 rounded-full text-[10px] font-mono font-bold transition-colors ${
                  audioPanelOpen ? 'bg-indigo-900/90 text-white' : 'bg-indigo-950 text-indigo-300 border border-indigo-700/50'
                }`}
              >
                {audioCount}
              </span>
            ) : (
              <span className="w-1.5 h-1.5 rounded-full bg-gray-500 opacity-60" />
            )}
          </button>

          {/* Query Archive Count */}
          <div
            className="hidden 2xl:flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg bg-[#151825] border border-[#252b40] text-[11px] font-mono text-gray-400"
            title="Total saved query threads"
          >
            <span className="text-gray-500">Threads:</span>
            <span className="text-gray-200 font-semibold">{threadCount}</span>
          </div>
        </div>
      </div>
    </header>
  )
}
