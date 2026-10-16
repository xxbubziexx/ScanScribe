import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import { RangeCalendar } from './RangeCalendar'
import {
  TIME_RANGE_PRESETS,
  describeTimeRange,
  endOfDay,
  formatLocal,
  localZoneAbbr,
  parseLocal,
  resolveTimeRange,
  startOfDay,
  type TimeRangeValue,
} from './timeRange'

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

export interface TimeRangePickerProps {
  value: TimeRangeValue
  onChange: (next: TimeRangeValue) => void
  className?: string
  disabled?: boolean
}

export function TimeRangePicker({ value, onChange, className = '', disabled }: TimeRangePickerProps) {
  const [open, setOpen] = useState(false)
  const rootRef = useRef<HTMLDivElement>(null)
  const zone = useMemo(() => localZoneAbbr(), [])

  const [fromText, setFromText] = useState('')
  const [toText, setToText] = useState('')
  const [error, setError] = useState<string | null>(null)

  const seedDrafts = useCallback(() => {
    const { start, end } = resolveTimeRange(value)
    setFromText(formatLocal(start))
    setToText(formatLocal(end))
    setError(null)
  }, [value])

  const toggle = () => {
    if (disabled) return
    if (!open) seedDrafts()
    setOpen((o) => !o)
  }

  useEffect(() => {
    if (!open) return
    const onDown = (e: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) setOpen(false)
    }
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false)
    }
    document.addEventListener('mousedown', onDown)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onDown)
      document.removeEventListener('keydown', onKey)
    }
  }, [open])

  const draftFrom = useMemo(() => parseLocal(fromText), [fromText])
  const draftTo = useMemo(() => parseLocal(toText), [toText])

  const handleCalendarRangeSelect = (start: Date, end: Date) => {
    const fromDate = startOfDay(start)
    const toDate = endOfDay(end)
    setFromText(formatLocal(fromDate))
    setToText(formatLocal(toDate))
    setError(null)
    onChange({ kind: 'absolute', from: fromDate, to: toDate })
  }

  const handleCalendarDayPick = (day: Date) => {
    setError(null)
    setFromText(formatLocal(startOfDay(day)))
  }

  const apply = () => {
    if (!draftFrom || !draftTo) {
      setError('Use format YYYY-MM-DD HH:mm:ss')
      return
    }

    // Auto-swap if start > end
    const from = draftFrom <= draftTo ? draftFrom : draftTo
    const to = draftFrom <= draftTo ? draftTo : draftFrom

    if (to > new Date()) {
      setError('"To" cannot be in the future')
      return
    }

    onChange({ kind: 'absolute', from, to })
    setOpen(false)
  }

  const inputClass =
    'w-full rounded-md border bg-[#0c0e14] px-2.5 py-1.5 font-mono text-xs text-gray-100 outline-none transition-colors focus:border-indigo-500'

  return (
    <div ref={rootRef} className={`relative inline-block ${className}`}>
      <button
        type="button"
        onClick={toggle}
        disabled={disabled}
        aria-haspopup="dialog"
        aria-expanded={open}
        className="flex items-center gap-2 rounded-md border border-[#2b2f42] bg-[#11131c] px-3 py-1.5 text-xs text-gray-200 transition-colors hover:border-indigo-500/60 disabled:cursor-not-allowed disabled:opacity-50 cursor-pointer"
      >
        <span className="font-medium">{describeTimeRange(value)}</span>
        <span className="text-gray-500">({zone})</span>
        <CalendarIcon className="h-3.5 w-3.5 text-gray-400" />
      </button>

      {open && (
        <div
          role="dialog"
          aria-label="Select time range"
          className="absolute right-0 z-50 mt-2 flex max-w-[calc(100vw-1rem)] flex-col overflow-hidden rounded-xl border border-[#2b2f42] bg-[#141722] shadow-2xl shadow-black/60 sm:flex-row"
        >
          {/* Left Column: Presets */}
          <ul className="flex shrink-0 flex-row gap-0.5 overflow-x-auto border-b border-[#222533] p-2 sm:w-44 sm:flex-col sm:overflow-visible sm:border-b-0 sm:border-r">
            {TIME_RANGE_PRESETS.map((p) => {
              const selected = value.kind === 'preset' && value.presetId === p.id
              return (
                <li key={p.id} className="shrink-0">
                  <button
                    type="button"
                    onClick={() => {
                      onChange({ kind: 'preset', presetId: p.id })
                      setOpen(false)
                    }}
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

          {/* Middle Column: Absolute Date & Time Inputs */}
          <div className="w-full p-3 sm:w-72 border-b border-[#222533] sm:border-b-0 sm:border-r">
            <div className="mb-2 text-xs font-semibold text-gray-200">Absolute time range</div>

            <div className="mb-2.5">
              <label
                htmlFor="time-range-from"
                className="mb-1 block text-xs text-gray-400"
              >
                From
              </label>
              <input
                id="time-range-from"
                value={fromText}
                onChange={(e) => {
                  setError(null)
                  setFromText(e.target.value)
                }}
                placeholder="YYYY-MM-DD HH:mm:ss"
                spellCheck={false}
                className={`${inputClass} ${
                  fromText && parseLocal(fromText) === null
                    ? 'border-red-500/70'
                    : 'border-[#2b2f42]'
                }`}
              />
            </div>

            <div className="mb-2.5">
              <label
                htmlFor="time-range-to"
                className="mb-1 block text-xs text-gray-400"
              >
                To
              </label>
              <input
                id="time-range-to"
                value={toText}
                onChange={(e) => {
                  setError(null)
                  setToText(e.target.value)
                }}
                placeholder="YYYY-MM-DD HH:mm:ss"
                spellCheck={false}
                className={`${inputClass} ${
                  toText && parseLocal(toText) === null
                    ? 'border-red-500/70'
                    : 'border-[#2b2f42]'
                }`}
              />
            </div>

            {error && (
              <div role="alert" className="mb-2 text-xs text-red-400">
                {error}
              </div>
            )}

            <button
              type="button"
              onClick={apply}
              className="w-full rounded-md bg-indigo-600 py-1.5 text-xs font-medium text-white transition-colors hover:bg-indigo-500 cursor-pointer"
            >
              Apply
            </button>

            <p className="mt-3 text-[11px] text-gray-500">
              Pick 2 days on the calendar to set the range, or type local datetimes above.
            </p>
          </div>

          {/* Right Column: Month Range Calendar */}
          <div className="p-1">
            <RangeCalendar
              mode="range"
              from={draftFrom}
              to={draftTo}
              maxDate={new Date()}
              onPick={handleCalendarDayPick}
              onRangeSelect={handleCalendarRangeSelect}
            />
          </div>
        </div>
      )}
    </div>
  )
}
