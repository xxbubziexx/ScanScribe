import { useMemo, useState } from 'react'

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
  onPick: (day: Date) => void
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
  onPick,
  className = '',
}: RangeCalendarProps) {
  const anchor =
    mode === 'single'
      ? selected ?? maxDate ?? new Date()
      : to ?? from ?? maxDate ?? new Date()

  const [view, setView] = useState(() => new Date(anchor.getFullYear(), anchor.getMonth(), 1))
  const today = useMemo(() => startOfDay(new Date()), [])

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

  const lo =
    mode === 'single'
      ? null
      : from && to
      ? from <= to
        ? startOfDay(from)
        : startOfDay(to)
      : from
      ? startOfDay(from)
      : null

  const hi =
    mode === 'single'
      ? null
      : from && to
      ? from <= to
        ? startOfDay(to)
        : startOfDay(from)
      : from
      ? startOfDay(from)
      : null

  const nextDisabled = maxDate
    ? new Date(view.getFullYear(), view.getMonth() + 1, 1) > startOfDay(maxDate)
    : false

  const shift = (delta: number) =>
    setView((v) => new Date(v.getFullYear(), v.getMonth() + delta, 1))

  return (
    <div className={`w-[17.5rem] p-3 select-none ${className}`} role="group" aria-label="Calendar">
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
          const disabled = maxDate ? dStart > endOfDay(maxDate) : false
          const isToday = isSameDay(d, today)
          const ymd = toYmd(d)
          const hasDbData = activeDateStrings ? activeDateStrings.has(ymd) : false

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
                onClick={() => onPick(d)}
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
