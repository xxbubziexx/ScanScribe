interface WidgetInfoTooltipProps {
  title: string
  description: string
  bullets?: string[]
  align?: 'left' | 'right'
}

function InfoCircleIcon({ className = '' }: { className?: string }) {
  return (
    <svg
      width="14"
      height="14"
      viewBox="0 0 16 16"
      className={`h-3.5 w-3.5 shrink-0 ${className}`}
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      aria-hidden="true"
    >
      <circle cx="8" cy="8" r="6.5" />
      <path d="M8 7v4.5M8 4.75v.5" strokeLinecap="round" />
    </svg>
  )
}

export function WidgetInfoTooltip({
  title,
  description,
  bullets = [],
  align = 'left',
}: WidgetInfoTooltipProps) {
  return (
    <div className="group/tooltip relative inline-flex items-center">
      <button
        type="button"
        aria-label={`About ${title}`}
        className="flex h-5 w-5 items-center justify-center rounded-full text-gray-500 transition-colors hover:bg-white/5 hover:text-sky-300 focus:outline-hidden"
      >
        <InfoCircleIcon />
      </button>

      {/* Tooltip Card */}
      <div
        className={`pointer-events-none absolute top-full z-50 mt-1.5 w-72 origin-top rounded-lg border border-sky-500/25 bg-[#0b0f17]/95 p-3 text-xs shadow-2xl shadow-black/80 backdrop-blur-md transition-all duration-150 ${
          align === 'right' ? 'right-0' : 'left-0'
        } invisible opacity-0 scale-95 group-hover/tooltip:visible group-hover/tooltip:opacity-100 group-hover/tooltip:scale-100`}
      >
        <div className="flex items-center gap-1.5 border-b border-gray-800/80 pb-1.5">
          <span className="h-1.5 w-1.5 rounded-full bg-sky-400" />
          <h4 className="font-semibold tracking-wide text-sky-200">{title}</h4>
        </div>

        <p className="mt-2 leading-relaxed text-gray-300">{description}</p>

        {bullets.length > 0 && (
          <ul className="mt-2 space-y-1.5 border-t border-gray-800/60 pt-2 text-[11px] text-gray-400">
            {bullets.map((b, i) => (
              <li key={i} className="flex items-start gap-1.5 leading-snug">
                <span className="mt-1 h-1 w-1 shrink-0 rounded-full bg-sky-500/60" />
                <span>{b}</span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  )
}
