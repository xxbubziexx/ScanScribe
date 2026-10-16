import { useEffect, useId, useMemo, useRef, useState } from 'react'

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

function formatButtonLabel(value: string) {
  if (!value) return 'Select date'
  const d = parseYmd(value)
  if (!d) return value
  return d.toLocaleDateString(undefined, {
    weekday: 'short',
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  })
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

export interface DatabaseDateSinglePickerProps {
  value: string
  onChange: (ymd: string) => void
  activeDates: string[]
  /** If true, only days in `activeDates` can be selected (when the list is non-empty). */
  restrictToActive?: boolean
  disabled?: boolean
  'aria-label'?: string
}

export function DatabaseDateSinglePicker({
  value,
  onChange,
  activeDates,
  restrictToActive = false,
  disabled = false,
  'aria-label': ariaLabel = 'Select date',
}: DatabaseDateSinglePickerProps) {
  const uid = useId()
  const [open, setOpen] = useState(false)
  const popRef = useRef<HTMLDivElement>(null)
  const btnRef = useRef<HTMLButtonElement>(null)
  const zone = useMemo(() => localZoneAbbr(), [])

  const activeSet = useMemo(() => new Set(activeDates ?? []), [activeDates])
  const selectedDate = useMemo(() => parseYmd(value), [value])

  useEffect(() => {
    if (!open) return
    const onDoc = (e: MouseEvent) => {
      const t = e.target
      if (t instanceof Node && !popRef.current?.contains(t) && !btnRef.current?.contains(t)) {
        setOpen(false)
      }
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

  const handlePick = (day: Date) => {
    const ymd = toYmd(day)
    if (restrictToActive && activeSet.size > 0 && !activeSet.has(ymd)) {
      return
    }
    onChange(ymd)
    setOpen(false)
  }

  const handleSelectToday = () => {
    const todayYmd = toYmd(new Date())
    if (restrictToActive && activeSet.size > 0 && !activeSet.has(todayYmd)) {
      return
    }
    onChange(todayYmd)
    setOpen(false)
  }

  return (
    <div className="relative inline-block">
      {/* Trigger Button */}
      <button
        ref={btnRef}
        id={`${uid}-btn`}
        type="button"
        disabled={disabled}
        aria-label={ariaLabel}
        aria-expanded={open}
        aria-haspopup="dialog"
        onClick={() => {
          if (disabled) return
          setOpen((prev) => !prev)
        }}
        className="flex items-center gap-2 rounded-md border border-[#2b2f42] bg-[#11131c] px-3 py-1.5 text-xs text-gray-200 transition-colors hover:border-indigo-500/60 disabled:cursor-not-allowed disabled:opacity-50 cursor-pointer"
      >
        <span className="font-medium truncate">{formatButtonLabel(value)}</span>
        <span className="text-gray-500">({zone})</span>
        <CalendarIcon className="h-3.5 w-3.5 text-gray-400" />
      </button>

      {/* Popover */}
      {open && (
        <div
          ref={popRef}
          role="dialog"
          aria-label={ariaLabel}
          className="absolute left-0 sm:left-auto right-auto sm:right-0 z-50 mt-2 overflow-hidden rounded-xl border border-[#2b2f42] bg-[#141722] p-1 shadow-2xl shadow-black/60"
        >
          <RangeCalendar
            mode="single"
            selected={selectedDate}
            maxDate={new Date()}
            activeDateStrings={activeSet}
            restrictToActive={restrictToActive}
            onPick={handlePick}
          />

          {/* Footer with Today Shortcut & DB Legend */}
          <div className="flex items-center justify-between border-t border-[#222533] px-3 py-2 text-xs text-gray-400">
            <div className="flex items-center gap-1.5 text-[11px]">
              <span className="h-1.5 w-1.5 rounded-full bg-indigo-400 shrink-0" aria-hidden />
              <span>Transmissions recorded</span>
            </div>
            <button
              type="button"
              onClick={handleSelectToday}
              className="text-indigo-400 hover:text-indigo-300 font-medium cursor-pointer"
            >
              Today
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
