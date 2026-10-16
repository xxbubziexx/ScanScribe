import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

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

import { RangeCalendar } from './RangeCalendar'

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

type CalendarTarget = 'from' | 'to' | null

export function TimeRangePicker({ value, onChange, className = '', disabled }: TimeRangePickerProps) {
  const [open, setOpen] = useState(false)
  const rootRef = useRef<HTMLDivElement>(null)
  const zone = useMemo(() => localZoneAbbr(), [])

  const [fromText, setFromText] = useState('')
  const [toText, setToText] = useState('')
  const [calendar, setCalendar] = useState<CalendarTarget>(null)
  const [error, setError] = useState<string | null>(null)

  const seedDrafts = useCallback(() => {
    const { start, end } = resolveTimeRange(value)
    setFromText(formatLocal(start))
    setToText(formatLocal(end))
    setCalendar(null)
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
      if (e.key !== 'Escape') return
      if (calendar) setCalendar(null)
      else setOpen(false)
    }
    document.addEventListener('mousedown', onDown)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onDown)
      document.removeEventListener('keydown', onKey)
    }
  }, [open, calendar])

  const draftFrom = parseLocal(fromText)
  const draftTo = parseLocal(toText)

  const pickDay = (day: Date) => {
    setError(null)
    if (calendar === 'from') {
      const time = draftFrom ?? startOfDay(day)
      const next = new Date(day.getFullYear(), day.getMonth(), day.getDate(), time.getHours(), time.getMinutes(), time.getSeconds())
      setFromText(formatLocal(next))
      setCalendar('to')
    } else if (calendar === 'to') {
      const time = draftTo ?? endOfDay(day)
      const next = new Date(day.getFullYear(), day.getMonth(), day.getDate(), time.getHours(), time.getMinutes(), time.getSeconds())
      setToText(formatLocal(next))
      setCalendar(null)
    }
  }

  const apply = () => {
    if (!draftFrom || !draftTo) {
      setError('Use the format YYYY-MM-DD HH:mm:ss')
      return
    }
    if (draftFrom > draftTo) {
      setError('"From" must be before "To"')
      return
    }
    if (draftTo > new Date()) {
      setError('"To" cannot be in the future')
      return
    }
    onChange({ kind: 'absolute', from: draftFrom, to: draftTo })
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
          className="absolute right-0 z-50 mt-2 flex max-w-[calc(100vw-1rem)] flex-col overflow-hidden rounded-lg border border-[#2b2f42] bg-[#141722] shadow-2xl shadow-black/50 sm:flex-row"
        >
          <ul className="flex shrink-0 flex-row gap-0.5 overflow-x-auto border-b border-[#222533] p-2 sm:w-48 sm:flex-col sm:overflow-visible sm:border-b-0 sm:border-r">
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
                        ? 'bg-indigo-500/15 text-white'
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

          <div className="w-full p-3 sm:w-72">
            <div className="mb-2 text-xs font-semibold text-gray-200">Absolute time range</div>

            {(['from', 'to'] as const).map((field) => {
              const text = field === 'from' ? fromText : toText
              const invalid = text !== '' && parseLocal(text) === null
              return (
                <div key={field} className="mb-2.5">
                  <label
                    htmlFor={`time-range-${field}`}
                    className="mb-1 block text-xs text-gray-400"
                  >
                    {field === 'from' ? 'From' : 'To'}
                  </label>
                  <div className="flex gap-2">
                    <input
                      id={`time-range-${field}`}
                      value={text}
                      onChange={(e) => {
                        setError(null)
                        if (field === 'from') setFromText(e.target.value)
                        else setToText(e.target.value)
                      }}
                      onFocus={() => setCalendar(null)}
                      placeholder="YYYY-MM-DD HH:mm:ss"
                      spellCheck={false}
                      className={`${inputClass} ${invalid ? 'border-red-500/70' : 'border-[#2b2f42]'}`}
                    />
                    <button
                      type="button"
                      aria-label={`Pick ${field} date`}
                      onClick={() => setCalendar(calendar === field ? null : field)}
                      className={`flex h-[30px] w-9 shrink-0 items-center justify-center rounded-md border text-gray-300 transition-colors cursor-pointer ${
                        calendar === field
                          ? 'border-indigo-500 bg-indigo-500/15'
                          : 'border-[#2b2f42] hover:bg-[#1e2333]'
                      }`}
                    >
                      <CalendarIcon />
                    </button>
                  </div>
                </div>
              )
            })}

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
          </div>

          {calendar && (
            <div className="border-t border-[#222533] sm:border-l sm:border-t-0">
              <RangeCalendar
                key={calendar}
                from={draftFrom}
                to={draftTo}
                maxDate={new Date()}
                onPick={pickDay}
              />
            </div>
          )}
        </div>
      )}
    </div>
  )
}
