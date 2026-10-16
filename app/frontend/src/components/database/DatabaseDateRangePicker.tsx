import { useCallback, useEffect, useId, useMemo, useRef, useState } from 'react'

import { RangeCalendar } from '@/components/ui/RangeCalendar'
import { localZoneAbbr } from '@/components/ui/timeRange'

const pad = (n: number): string => String(n).padStart(2, '0')

function toYmd(d: Date): string {
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}

function parseYmd(s: string): Date | null {
  if (!s || !/^\d{4}-\d{2}-\d{2}$/.test(s.trim())) return null
  const [y, m, d] = s.trim().split('-').map(Number)
  const date = new Date(y, m - 1, d, 0, 0, 0, 0)
  if (date.getFullYear() === y && date.getMonth() === m - 1 && date.getDate() === d) {
    return date
  }
  return null
}

interface DatePreset {
  id: string
  label: string
  getRange: (now: Date) => { from: string; to: string }
}

const DATE_PRESETS: DatePreset[] = [
  {
    id: 'today',
    label: 'Today',
    getRange: (now) => {
      const todayStr = toYmd(now)
      return { from: todayStr, to: todayStr }
    },
  },
  {
    id: 'yesterday',
    label: 'Yesterday',
    getRange: (now) => {
      const y = new Date(now)
      y.setDate(y.getDate() - 1)
      const yStr = toYmd(y)
      return { from: yStr, to: yStr }
    },
  },
  {
    id: 'last3d',
    label: 'Last 3 days',
    getRange: (now) => {
      const past = new Date(now)
      past.setDate(past.getDate() - 3)
      return { from: toYmd(past), to: toYmd(now) }
    },
  },
  {
    id: 'last7d',
    label: 'Last 7 days',
    getRange: (now) => {
      const past = new Date(now)
      past.setDate(past.getDate() - 7)
      return { from: toYmd(past), to: toYmd(now) }
    },
  },
  {
    id: 'last14d',
    label: 'Last 2 weeks',
    getRange: (now) => {
      const past = new Date(now)
      past.setDate(past.getDate() - 14)
      return { from: toYmd(past), to: toYmd(now) }
    },
  },
  {
    id: 'last30d',
    label: 'Last 30 days',
    getRange: (now) => {
      const past = new Date(now)
      past.setDate(past.getDate() - 30)
      return { from: toYmd(past), to: toYmd(now) }
    },
  },
  {
    id: 'all',
    label: 'All dates',
    getRange: () => ({ from: '', to: '' }),
  },
]

function formatButtonLabel(from: string, to: string) {
  if (!from && !to) return 'All dates'
  if (from && !to) return `From ${from}`
  if (!from && to) return `Until ${to}`
  if (from === to) return from
  return `${from} → ${to}`
}

function CalendarIcon({ className = 'h-4 w-4' }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 16 16"
      className={className}
      fill="none"
      stroke="currentColor"
      strokeWidth="1.3"
      aria-hidden="true"
    >
      <rect x="2" y="3" width="12" height="11" rx="1.5" />
      <path d="M2 6.5h12M5.5 1.5v3M10.5 1.5v3" strokeLinecap="round" />
    </svg>
  )
}

export interface DatabaseDateRangePickerProps {
  from: string
  to: string
  onChange: (from: string, to: string) => void
  activeDates: string[] | undefined
  disabled?: boolean
}

export function DatabaseDateRangePicker({
  from,
  to,
  onChange,
  activeDates,
  disabled = false,
}: DatabaseDateRangePickerProps) {
  const uid = useId()
  const [open, setOpen] = useState(false)
  const popRef = useRef<HTMLDivElement>(null)
  const btnRef = useRef<HTMLButtonElement>(null)
  const zone = useMemo(() => localZoneAbbr(), [])

  const [fromInput, setFromInput] = useState(from)
  const [toInput, setToInput] = useState(to)
  const [error, setError] = useState<string | null>(null)

  const activeSet = useMemo(() => new Set(activeDates ?? []), [activeDates])

  const syncInputsFromProps = useCallback(() => {
    setFromInput(from)
    setToInput(to)
    setError(null)
  }, [from, to])

  useEffect(() => {
    if (!open) return
    const onDoc = (e: MouseEvent) => {
      const path = e.composedPath ? e.composedPath() : []
      const t = e.target
      if (
        (popRef.current && (popRef.current.contains(t as Node) || path.includes(popRef.current))) ||
        (btnRef.current && (btnRef.current.contains(t as Node) || path.includes(btnRef.current)))
      ) {
        return
      }
      setOpen(false)
    }
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false)
    }
    document.addEventListener('mousedown', onDoc)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onDoc)
      document.removeEventListener('keydown', onKey)
    }
  }, [open])

  const draftFromDate = useMemo(() => parseYmd(fromInput), [fromInput])
  const draftToDate = useMemo(() => parseYmd(toInput), [toInput])

  // Direct calendar range pick (User clicked day 1 then day 2)
  const handleCalendarRangeSelect = (start: Date, end: Date) => {
    const fromYmd = toYmd(start)
    const toYmdStr = toYmd(end)
    setFromInput(fromYmd)
    setToInput(toYmdStr)
    setError(null)
    onChange(fromYmd, toYmdStr)
  }

  // Individual day pick (visual feedback for start of range)
  const handleCalendarDayPick = (day: Date) => {
    setError(null)
    setFromInput(toYmd(day))
    setToInput('')
  }

  const handleApply = () => {
    setError(null)
    const trimmedFrom = fromInput.trim()
    const trimmedTo = toInput.trim()

    if (!trimmedFrom && !trimmedTo) {
      onChange('', '')
      setOpen(false)
      return
    }

    if (trimmedFrom && !parseYmd(trimmedFrom)) {
      setError('Invalid "From" date (format: YYYY-MM-DD)')
      return
    }
    if (trimmedTo && !parseYmd(trimmedTo)) {
      setError('Invalid "To" date (format: YYYY-MM-DD)')
      return
    }

    if (trimmedFrom && trimmedTo && trimmedFrom > trimmedTo) {
      // Auto-correct order if inverted
      setFromInput(trimmedTo)
      setToInput(trimmedFrom)
      onChange(trimmedTo, trimmedFrom)
      setOpen(false)
      return
    }

    onChange(trimmedFrom, trimmedTo)
    setOpen(false)
  }

  const handlePresetSelect = (preset: DatePreset) => {
    const range = preset.getRange(new Date())
    setFromInput(range.from)
    setToInput(range.to)
    setError(null)
    onChange(range.from, range.to)
    setOpen(false)
  }

  const handleClear = () => {
    setFromInput('')
    setToInput('')
    setError(null)
    onChange('', '')
    setOpen(false)
  }

  const activePresetId = useMemo(() => {
    const now = new Date()
    for (const p of DATE_PRESETS) {
      const r = p.getRange(now)
      if (r.from === from && r.to === to) return p.id
    }
    return null
  }, [from, to])

  const inputClass =
    'w-full rounded-md border bg-[#0c0e14] px-2.5 py-1.5 font-mono text-xs text-gray-100 outline-none transition-colors focus:border-indigo-500'

  return (
    <div className="relative inline-block">
      <label className="ss-form-label mb-1 block" id={`${uid}-lbl`} htmlFor={`${uid}-btn`}>
        Date range
      </label>

      {/* Trigger Button */}
      <button
        ref={btnRef}
        id={`${uid}-btn`}
        type="button"
        disabled={disabled}
        aria-expanded={open}
        aria-haspopup="dialog"
        onClick={() => {
          if (disabled) return
          if (!open) syncInputsFromProps()
          setOpen((prev) => !prev)
        }}
        className="flex items-center gap-2 rounded-md border border-[#2b2f42] bg-[#11131c] px-3 py-1.5 text-xs text-gray-200 transition-colors hover:border-indigo-500/60 disabled:cursor-not-allowed disabled:opacity-50 cursor-pointer"
      >
        <span className="font-medium truncate max-w-[160px] sm:max-w-none">
          {formatButtonLabel(from, to)}
        </span>
        <span className="text-gray-500">({zone})</span>
        <CalendarIcon className="h-3.5 w-3.5 text-gray-400" />
      </button>

      {/* Popover */}
      {open && (
        <div
          ref={popRef}
          role="dialog"
          aria-labelledby={`${uid}-lbl`}
          className="absolute left-0 sm:left-auto right-auto sm:right-0 z-50 mt-2 flex max-w-[calc(100vw-1.5rem)] flex-col overflow-hidden rounded-xl border border-[#2b2f42] bg-[#141722] shadow-2xl shadow-black/60 sm:flex-row"
        >
          {/* Left Column: Presets */}
          <ul className="flex shrink-0 flex-row gap-0.5 overflow-x-auto border-b border-[#222533] p-2 sm:w-44 sm:flex-col sm:overflow-visible sm:border-b-0 sm:border-r">
            {DATE_PRESETS.map((p) => {
              const selected = activePresetId === p.id
              return (
                <li key={p.id} className="shrink-0">
                  <button
                    type="button"
                    onClick={() => handlePresetSelect(p)}
                    className={`flex min-h-9 w-full items-center justify-between gap-3 rounded-md px-3 text-left text-xs transition-colors cursor-pointer ${
                      selected
                        ? 'bg-indigo-500/15 text-white font-medium'
                        : 'text-gray-300 hover:bg-[#1e2333]'
                    }`}
                  >
                    <span className="whitespace-nowrap">{p.label}</span>
                    {selected && <span aria-hidden="true">&#10003;</span>}
                  </button>
                </li>
              )
            })}
          </ul>

          {/* Middle Column: Absolute Date Range */}
          <div className="w-full p-3 sm:w-72 border-b border-[#222533] sm:border-b-0 sm:border-r">
            <div className="mb-2 text-xs font-semibold text-gray-200">Absolute date range</div>

            {/* From Input */}
            <div className="mb-2.5">
              <label
                htmlFor={`${uid}-from`}
                className="mb-1 block text-xs text-gray-400"
              >
                From
              </label>
              <div className="flex gap-2">
                <input
                  id={`${uid}-from`}
                  value={fromInput}
                  onChange={(e) => {
                    setError(null)
                    setFromInput(e.target.value)
                  }}
                  placeholder="YYYY-MM-DD"
                  spellCheck={false}
                  className={`${inputClass} ${
                    fromInput && !parseYmd(fromInput) ? 'border-red-500/70' : 'border-[#2b2f42]'
                  }`}
                />
              </div>
            </div>

            {/* To Input */}
            <div className="mb-2.5">
              <label
                htmlFor={`${uid}-to`}
                className="mb-1 block text-xs text-gray-400"
              >
                To
              </label>
              <div className="flex gap-2">
                <input
                  id={`${uid}-to`}
                  value={toInput}
                  onChange={(e) => {
                    setError(null)
                    setToInput(e.target.value)
                  }}
                  placeholder="YYYY-MM-DD"
                  spellCheck={false}
                  className={`${inputClass} ${
                    toInput && !parseYmd(toInput) ? 'border-red-500/70' : 'border-[#2b2f42]'
                  }`}
                />
              </div>
            </div>

            {error && (
              <div role="alert" className="mb-2 text-xs text-red-400">
                {error}
              </div>
            )}

            <div className="mt-3 flex gap-2">
              <button
                type="button"
                onClick={handleApply}
                className="flex-1 rounded-md bg-indigo-600 py-1.5 text-xs font-medium text-white transition-colors hover:bg-indigo-500 cursor-pointer"
              >
                Apply
              </button>
              <button
                type="button"
                onClick={handleClear}
                className="rounded-md border border-[#2b2f42] px-3 py-1.5 text-xs font-medium text-gray-300 transition-colors hover:bg-[#1e2333] cursor-pointer"
              >
                Clear
              </button>
            </div>

            {/* Hint & Legend */}
            <div className="mt-3 text-[11px] text-gray-400 space-y-1">
              <p>Click two days on the calendar to select a range.</p>
              <div className="flex items-center gap-1.5 pt-1 border-t border-[#222533]">
                <span className="h-1.5 w-1.5 rounded-full bg-indigo-400 shrink-0" aria-hidden />
                <span>Day has recorded transmissions</span>
              </div>
            </div>
          </div>

          {/* Right Column: Month Range Calendar */}
          <div className="p-1">
            <RangeCalendar
              mode="range"
              from={draftFromDate}
              to={draftToDate}
              maxDate={new Date()}
              activeDateStrings={activeSet}
              onPick={handleCalendarDayPick}
              onRangeSelect={handleCalendarRangeSelect}
            />
          </div>
        </div>
      )}
    </div>
  )
}
