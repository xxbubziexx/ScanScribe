import { useState } from 'react'

interface ThinkingAccordionProps {
  thought: string
  isLive?: boolean
}

export function ThinkingAccordion({ thought, isLive = false }: ThinkingAccordionProps) {
  const [open, setOpen] = useState(isLive)
  const trimmed = thought.trim()
  if (!trimmed) return null

  const lineCount = trimmed.split('\n').filter((l) => l.trim()).length

  return (
    <div className="mb-2.5 rounded border border-amber-700/30 bg-amber-950/10">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="w-full flex items-center justify-between gap-2 px-2.5 py-1.5 text-[11px] text-amber-300/90 hover:bg-amber-950/20 transition-colors cursor-pointer"
      >
        <span className="flex items-center gap-2 font-medium uppercase tracking-wider">
          {isLive && <span className="inline-block w-1.5 h-1.5 rounded-full bg-amber-400 animate-pulse" />}
          <span>{isLive ? 'Thinking' : `Thought process (${lineCount} ${lineCount === 1 ? 'line' : 'lines'})`}</span>
        </span>
        <span className="text-[10px] text-amber-500/70">{open ? 'Hide' : 'Show'}</span>
      </button>
      {open && (
        <div className="px-2.5 pb-2 pt-1 text-[11px] leading-relaxed text-gray-400 whitespace-pre-wrap max-h-56 overflow-y-auto select-text border-t border-amber-700/20">
          {trimmed}
        </div>
      )}
    </div>
  )
}
