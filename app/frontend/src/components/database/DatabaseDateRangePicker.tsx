import { useCallback, useEffect, useId, useRef, useState } from 'react'
import {
  addMonths,
  buildMonthCells,
  CALENDAR_WEEKDAYS,
  monthStart,
  parseYmdLocal,
  pickMax,
  pickMin,
} from './calendarUtils'

function formatButtonLabel(from: string, to: string, picking: string | null) {
  if (picking) return `Select end (from ${picking})…`
  if (!from && !to) return 'All dates'
  if (from && to) {
    if (from === to) return from
    return `${from} → ${to}`
  }
  return 'All dates'
}

interface DatabaseDateRangePickerProps {
  from: string
  to: string
  onChange: (from: string, to: string) => void
  activeDates: string[] | undefined
  disabled?: boolean
}

/**
 * Date range: button uses `ss-select-sm` (shared trigger style) + the shared calendar popover.
 */
export function DatabaseDateRangePicker({
  from,
  to,
  onChange,
  activeDates,
  disabled = false,
}: DatabaseDateRangePickerProps) {
  const uid = useId()
  const [open, setOpen] = useState(false)
  const [viewMonth, setViewMonth] = useState(() => monthStart(new Date()))
  const [picking, setPicking] = useState<string | null>(null)
  const popRef = useRef<HTMLDivElement>(null)
  const btnRef = useRef<HTMLButtonElement>(null)

  const activeSet = new Set(activeDates ?? [])

  useEffect(() => {
    if (from) {
      setViewMonth(monthStart(parseYmdLocal(from)))
    }
  }, [from])

  useEffect(() => {
    if (from) return
    if (!activeDates || activeDates.length === 0) return
    const last = activeDates[activeDates.length - 1]
    setViewMonth(monthStart(parseYmdLocal(last)))
  }, [activeDates, from])

  useEffect(() => {
    if (!open) return
    function onDoc(e: MouseEvent) {
      const t = e.target
      if (t instanceof Node && !popRef.current?.contains(t) && !btnRef.current?.contains(t)) {
        setOpen(false)
        setPicking(null)
      }
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') {
        setOpen(false)
        setPicking(null)
      }
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

  const onPickDay = useCallback(
    (ymd: string) => {
      if (picking === null) {
        setPicking(ymd)
        return
      }
      onChange(pickMin(picking, ymd), pickMax(picking, ymd))
      setPicking(null)
      setOpen(false)
    },
    [picking, onChange],
  )

  const onClear = useCallback(() => {
    onChange('', '')
    setPicking(null)
    setOpen(false)
  }, [onChange])

  return (
    <div className="relative">
      <label className="ss-form-label" id={`${uid}-lbl`} htmlFor={`${uid}-btn`}>
        Date range
      </label>
      <button
        ref={btnRef}
        id={`${uid}-btn`}
        type="button"
        className="ss-select-sm"
        aria-expanded={open}
        aria-haspopup="dialog"
        disabled={disabled}
        onClick={() => {
          setOpen((prev) => {
            if (!prev) {
              setPicking(null)
              return true
            }
            setPicking(null)
            return false
          })
        }}
      >
        <span className="ss-db-daterange-btn-text">
          {formatButtonLabel(from, to, open ? picking : null)}
        </span>
        <span className="ss-db-daterange-chev" aria-hidden>
          {open ? '▲' : '▼'}
        </span>
      </button>

      {open && (
        <div
          ref={popRef}
          className="ss-db-daterange-pop"
          role="dialog"
          aria-labelledby={`${uid}-lbl`}
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
              const inRange = picking
                ? false
                : !!(from && to && ymd >= from && ymd <= to)
              const edge = picking
                ? ymd === picking
                : (!!from && ymd === from) || (!!to && ymd === to)

              return (
                <button
                  key={ymd}
                  type="button"
                  onClick={() => onPickDay(ymd)}
                  className={[
                    'ss-db-daterange-day',
                    inRange ? 'ss-db-daterange-day--inrange' : '',
                    edge ? 'ss-db-daterange-day--edge' : '',
                    hasDb ? 'ss-db-daterange-day--hasdata' : '',
                  ]
                    .filter(Boolean)
                    .join(' ')}
                >
                  {day}
                </button>
              )
            })}
          </div>

          <p className="ss-db-daterange-hint">Click two days to set the inclusive range.</p>

          <div className="ss-db-daterange-foot">
            <div className="ss-db-daterange-legend">
              <span className="ss-db-daterange-dot" aria-hidden />
              <span className="text-sm text-gray-500">Day has at least one log (from DB)</span>
            </div>
            <button type="button" className="ss-btn-ghost" onClick={onClear}>
              Clear
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
