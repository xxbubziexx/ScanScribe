import { useEffect, useMemo, useState } from 'react'

import {
  endOfDay,
  isSameDay,
  startOfDay,
} from './timeRange'

export const WEEKDAYS = ['Su', 'Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa'] as const

export interface RangeCalendarProps {
  mode?: 'range' | 'single'
  from?: Date | null
  to?: Date | null
  selected?: Date | null
  /** Optional latest selectable day; later days are disabled */
  maxDate?: Date
  /** Set of YYYY-MM-DD dates that have activity/records in SQLite */
  activeDateStrings?: Set<string>
  /** If true, days not in activeDateStrings are disabled */
  restrictToActive?: boolean
  /** Single day pick or individual day click callback */
  onPick?: (day: Date) => void
  /** Range completion callback when 2 days are selected in range mode */
  onRangeSelect?: (from: Date, to: Date) => void
  className?: string
}

const pad = (n: number): string => String(n).padStart(2, '0')
const toYmd = (d: Date): string =>
  `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`

export function RangeCalendar({
  mode = 'range',
  from = null,
  to = null,
  selected = null,
  maxDate,
  activeDateStrings,
  restrictToActive = false,
  onPick,
  onRangeSelect,
  className = '',
}: RangeCalendarProps) {
  const anchor =
    mode === 'single'
      ? selected ?? maxDate ?? new Date()
      : to ?? from ?? maxDate ?? new Date()

  const [view, setView] = useState(() => new Date(anchor.getFullYear(), anchor.getMonth(), 1))
  const today = useMemo(() => startOfDay(new Date()), [])

  // Interactive range selection state
  const [pickingStart, setPickingStart] = useState<Date | null>(null)
  const [hoverDate, setHoverDate] = useState<Date | null>(null)

  // Sync view when anchor prop changes meaningfully
  useEffect(() => {
    if (mode === 'single' && selected) {
      setView(new Date(selected.getFullYear(), selected.getMonth(), 1))
    } else if (mode === 'range' && from) {
      setView(new Date(from.getFullYear(), from.getMonth(), 1))
    }
  }, [mode, selected, from])

  const cells = useMemo(() => {
    const first = new Date(view.getFullYear(), view.getMonth(), 1)
    const gridStart = new Date(first)
    gridStart.setDate(1 - first.getDay())
    return Array.from({ length: 42 }, (_, i) => {
      const d = new Date(gridStart)
      d.setDate(gridStart.getDate() + i)
      return d
    })
  }, [view])

  const lo = useMemo(() => {
    if (mode === 'single') return null
    if (pickingStart !== null) {
      const target = hoverDate ?? pickingStart
      return pickingStart <= target ? startOfDay(pickingStart) : startOfDay(target)
    }
    if (from && to) {
      return from <= to ? startOfDay(from) : startOfDay(to)
    }
    return from ? startOfDay(from) : null
  }, [mode, pickingStart, hoverDate, from, to])

  const hi = useMemo(() => {
    if (mode === 'single') return null
    if (pickingStart !== null) {
      const target = hoverDate ?? pickingStart
      return pickingStart <= target ? startOfDay(target) : startOfDay(pickingStart)
    }
    if (from && to) {
      return from <= to ? startOfDay(to) : startOfDay(from)
    }
    return from ? startOfDay(from) : null
  }, [mode, pickingStart, hoverDate, from, to])

  const nextDisabled = maxDate
    ? new Date(view.getFullYear(), view.getMonth() + 1, 1) > startOfDay(maxDate)
    : false

  const shift = (delta: number) =>
    setView((v) => new Date(v.getFullYear(), v.getMonth() + delta, 1))

  const handleDayClick = (day: Date) => {
    if (mode === 'single') {
      onPick?.(day)
      return
    }

    if (pickingStart === null) {
      // First click: initiate range selection
      setPickingStart(day)
      setHoverDate(null)
      onPick?.(day)
    } else {
      // Second click: complete range selection
      const start = pickingStart <= day ? pickingStart : day
      const end = pickingStart <= day ? day : pickingStart
      setPickingStart(null)
      setHoverDate(null)
      onRangeSelect?.(start, end)
      onPick?.(day)
    }
  }

  return (
    <div
      className={`w-[17.5rem] p-3 select-none ${className}`}
      role="group"
      aria-label="Calendar"
      onMouseLeave={() => {
        if (pickingStart !== null) setHoverDate(null)
      }}
    >
      {/* Month Year Header & Navigation */}
      <div className="mb-2.5 flex items-center justify-between">
        <span className="text-sm font-semibold tracking-tight text-gray-100">
          {view.toLocaleDateString(undefined, { month: 'long', year: 'numeric' })}
        </span>
        <div className="flex gap-1">
          <button
            type="button"
            aria-label="Previous month"
            onClick={() => shift(-1)}
            className="flex h-7 w-7 items-center justify-center rounded-md border border-[#2b2f42] text-xs text-gray-300 transition-colors hover:bg-[#1e2333] cursor-pointer"
          >
            &lsaquo;
          </button>
          <button
            type="button"
            aria-label="Next month"
            disabled={nextDisabled}
            onClick={() => shift(1)}
            className="flex h-7 w-7 items-center justify-center rounded-md border border-[#2b2f42] text-xs text-gray-300 transition-colors hover:bg-[#1e2333] disabled:cursor-not-allowed disabled:opacity-30 cursor-pointer"
          >
            &rsaquo;
          </button>
        </div>
      </div>

      {/* Weekday Labels (Su Mo Tu We Th Fr Sa) */}
      <div className="grid grid-cols-7 text-center text-[11px] font-medium text-gray-400 mb-1">
        {WEEKDAYS.map((w) => (
          <div key={w} className="py-1">
            {w}
          </div>
        ))}
      </div>

      {/* 42-day Calendar Grid */}
      <div className="grid grid-cols-7 gap-y-1 text-center text-xs">
        {cells.map((d, index) => {
          const dStart = startOfDay(d)
          const outside = d.getMonth() !== view.getMonth()
          const ymd = toYmd(d)
          const hasDbData = activeDateStrings ? activeDateStrings.has(ymd) : false
          const isBlockedByActive =
            restrictToActive && Boolean(activeDateStrings?.size) && !hasDbData
          const disabled = (maxDate ? dStart > endOfDay(maxDate) : false) || isBlockedByActive
          const isToday = isSameDay(d, today)

          let isStart = false
          let isEnd = false
          let isBetween = false
          let isSingleSelected = false

          if (mode === 'single') {
            isSingleSelected = selected ? isSameDay(d, selected) : false
          } else {
            if (lo && hi) {
              const loTime = lo.getTime()
              const hiTime = hi.getTime()
              const dTime = dStart.getTime()
              isStart = dTime === loTime
              isEnd = dTime === hiTime
              isBetween = dTime > loTime && dTime < hiTime
            } else if (lo) {
              isStart = isSameDay(d, lo)
            }
          }

          const isEdge = isStart || isEnd || isSingleSelected
          const dow = index % 7 // 0 = Sunday, 6 = Saturday

          return (
            <div key={d.toISOString()} className="relative flex h-8 items-center justify-center">
              {/* Continuous Range Band connecting start and end */}
              {mode === 'range' && lo && hi && lo.getTime() !== hi.getTime() && (
                <>
                  {isStart && (
                    <div className="absolute inset-y-1 left-1/2 right-0 bg-indigo-500/20" />
                  )}
                  {isEnd && (
                    <div className="absolute inset-y-1 left-0 right-1/2 bg-indigo-500/20" />
                  )}
                  {isBetween && (
                    <div
                      className={`absolute inset-y-1 left-0 right-0 bg-indigo-500/20 ${
                        dow === 0 ? 'rounded-l-md' : ''
                      } ${dow === 6 ? 'rounded-r-md' : ''}`}
                    />
                  )}
                </>
              )}

              {/* Day Cell Button */}
              <button
                type="button"
                disabled={disabled}
                aria-label={d.toDateString()}
                aria-pressed={isEdge}
                onClick={() => handleDayClick(d)}
                onMouseEnter={() => {
                  if (mode === 'range' && pickingStart !== null) {
                    setHoverDate(d)
                  }
                }}
                className={`relative z-10 flex h-7 w-7 sm:h-8 sm:w-8 items-center justify-center rounded-lg transition-colors cursor-pointer ${
                  isEdge
                    ? 'bg-neutral-900 border border-neutral-700 text-white font-bold shadow sm:bg-indigo-600 sm:border-indigo-500'
                    : isBetween
                    ? 'text-gray-100 font-medium hover:bg-indigo-500/30'
                    : outside || disabled
                    ? 'text-gray-600 hover:text-gray-400'
                    : isToday
                    ? 'text-sky-400 font-bold hover:bg-[#1e2333]'
                    : 'text-gray-200 hover:bg-[#1e2333] hover:text-white'
                } ${disabled ? 'cursor-not-allowed opacity-35 hover:bg-transparent' : ''}`}
              >
                <span>{d.getDate()}</span>

                {/* Activity dot for database log entries */}
                {hasDbData && (
                  <span
                    className={`absolute bottom-0.5 left-1/2 h-1 w-1 -translate-x-1/2 rounded-full ${
                      isEdge ? 'bg-white' : 'bg-indigo-400'
                    }`}
                    aria-hidden="true"
                  />
                )}
              </button>
            </div>
          )
        })}
      </div>
    </div>
  )
}
