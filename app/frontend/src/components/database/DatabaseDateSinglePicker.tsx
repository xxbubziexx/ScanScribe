import { useCallback, useEffect, useRef, useState } from 'react'
import {
  addMonths,
  buildMonthCells,
  CALENDAR_WEEKDAYS,
  monthStart,
  parseYmdLocal,
} from './calendarUtils'

function formatButtonLabel(value: string) {
  if (!value) return 'Select date'
  const d = parseYmdLocal(value)
  if (isNaN(d.getTime())) return value
  return d.toLocaleDateString(undefined, {
    weekday: 'short',
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  })
}

interface DatabaseDateSinglePickerProps {
  value: string
  onChange: (ymd: string) => void
  activeDates: string[]
  /** If true, only days in `activeDates` can be selected (when the list is non-empty). */
  restrictToActive?: boolean
  disabled?: boolean
  'aria-label'?: string
}

/**
 * Single-day picker: same calendar popover as the Database date range control.
 * The trigger uses `ss-select-sm` (aligned with the shared “calendar button” look).
 */
export function DatabaseDateSinglePicker({
  value,
  onChange,
  activeDates,
  restrictToActive = true,
  disabled = false,
  'aria-label': ariaLabel = 'Select date',
}: DatabaseDateSinglePickerProps) {
  const [open, setOpen] = useState(false)
  const [viewMonth, setViewMonth] = useState(() => monthStart(new Date()))
  const popRef = useRef<HTMLDivElement>(null)
  const btnRef = useRef<HTMLButtonElement>(null)

  const activeSet = new Set(activeDates)

  useEffect(() => {
    if (value) {
      setViewMonth(monthStart(parseYmdLocal(value)))
    }
  }, [value])

  useEffect(() => {
    if (value) return
    if (activeDates.length === 0) return
    const last = activeDates[activeDates.length - 1]
    setViewMonth(monthStart(parseYmdLocal(last)))
  }, [activeDates, value])

  useEffect(() => {
    if (!open) return
    function onDoc(e: MouseEvent) {
      const t = e.target
      if (t instanceof Node && !popRef.current?.contains(t) && !btnRef.current?.contains(t)) {
        setOpen(false)
      }
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') setOpen(false)
    }
    document.addEventListener('mousedown', onDoc)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onDoc)
      document.removeEventListener('keydown', onKey)
    }
  }, [open])

  const cells = buildMonthCells(viewMonth)
  const label = viewMonth.toLocaleString(undefined, { month: 'long', year: 'numeric' })

  const canPick = useCallback(
    (ymd: string) => {
      if (!restrictToActive || activeSet.size === 0) return true
      return activeSet.has(ymd)
    },
    [activeSet, restrictToActive],
  )

  const onPickDay = useCallback(
    (ymd: string) => {
      if (!canPick(ymd)) return
      onChange(ymd)
      setOpen(false)
    },
    [canPick, onChange],
  )

  return (
    <div className="relative min-w-0">
      <button
        ref={btnRef}
        type="button"
        className="ss-select-sm"
        aria-label={ariaLabel}
        aria-expanded={open}
        aria-haspopup="dialog"
        disabled={disabled}
        onClick={() => setOpen((o) => !o)}
      >
        <span className="ss-db-daterange-btn-text">{formatButtonLabel(value)}</span>
        <span className="ss-db-daterange-chev" aria-hidden>
          {open ? '▲' : '▼'}
        </span>
      </button>

      {open && (
        <div
          ref={popRef}
          className="ss-db-daterange-pop"
          role="dialog"
          aria-label={ariaLabel}
        >
          <div className="ss-db-daterange-nav">
            <button
              type="button"
              className="ss-btn-bare"
              onClick={() => setViewMonth((m) => addMonths(m, -1))}
            >
              ‹
            </button>
            <span className="shrink-0 text-sm font-medium text-gray-200">{label}</span>
            <button
              type="button"
              className="ss-btn-bare"
              onClick={() => setViewMonth((m) => addMonths(m, 1))}
            >
              ›
            </button>
          </div>

          <div className="ss-db-daterange-dow" aria-hidden>
            {CALENDAR_WEEKDAYS.map((w) => (
              <div key={w} className="ss-db-daterange-dow-c">
                {w}
              </div>
            ))}
          </div>

          <div className="ss-db-daterange-grid">
            {cells.map((c, i) => {
              if (c.kind === 'pad') {
                return <div key={`pad-${i}`} className="ss-db-daterange-pad" />
              }
              const { ymd, day } = c
              const hasDb = activeSet.size > 0 && activeSet.has(ymd)
              const selected = value && ymd === value
              const pickable = canPick(ymd)
              return (
                <button
                  key={ymd}
                  type="button"
                  onClick={() => onPickDay(ymd)}
                  disabled={!pickable}
                  className={[
                    'ss-db-daterange-day',
                    selected ? 'ss-db-daterange-day--edge' : '',
                    hasDb ? 'ss-db-daterange-day--hasdata' : '',
                    !pickable ? 'ss-db-daterange-day--blocked' : '',
                  ]
                    .filter(Boolean)
                    .join(' ')}
                >
                  {day}
                </button>
              )
            })}
          </div>

          {restrictToActive && activeDates.length > 0 && (
            <p className="ss-db-daterange-hint">Only days with data can be selected.</p>
          )}

          <div className="ss-db-daterange-foot">
            <div className="ss-db-daterange-legend">
              <span className="ss-db-daterange-dot" aria-hidden />
              <span className="text-sm text-gray-500">Day has at least one log (from DB)</span>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
