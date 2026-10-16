/**
 * Time range model and helpers shared by TimeRangePicker.
 * All values are interpreted in the browser's local time zone.
 */

export interface RelativePreset {
  id: string
  label: string
  /** Rolling window length in milliseconds, ending at "now". */
  durationMs: number | null
}

const MIN = 60_000
const HOUR = 60 * MIN
const DAY = 24 * HOUR

export const TIME_RANGE_PRESETS: readonly RelativePreset[] = [
  { id: '30m', label: 'Last 30 minutes', durationMs: 30 * MIN },
  { id: '6h', label: 'Last 6 hours', durationMs: 6 * HOUR },
  { id: '12h', label: 'Last 12 hours', durationMs: 12 * HOUR },
  { id: '24h', label: 'Last 24 hours', durationMs: DAY },
  { id: '3d', label: 'Last 3 days', durationMs: 3 * DAY },
  { id: '7d', label: 'Last 7 days', durationMs: 7 * DAY },
  { id: '14d', label: 'Last 2 weeks', durationMs: 14 * DAY },
  { id: '21d', label: 'Last 21 days', durationMs: 21 * DAY },
  { id: '30d', label: 'Last 30 days', durationMs: 30 * DAY },
  { id: 'today', label: 'Today', durationMs: null },
] as const

export type TimeRangeValue =
  | { kind: 'preset'; presetId: string }
  | { kind: 'absolute'; from: Date; to: Date }

export interface ResolvedRange {
  start: Date
  end: Date
}

export const DEFAULT_TIME_RANGE: TimeRangeValue = { kind: 'preset', presetId: 'today' }

export function startOfDay(d: Date): Date {
  return new Date(d.getFullYear(), d.getMonth(), d.getDate(), 0, 0, 0, 0)
}

export function endOfDay(d: Date): Date {
  return new Date(d.getFullYear(), d.getMonth(), d.getDate(), 23, 59, 59, 0)
}

export function isSameDay(a: Date, b: Date): boolean {
  return (
    a.getFullYear() === b.getFullYear() &&
    a.getMonth() === b.getMonth() &&
    a.getDate() === b.getDate()
  )
}

/** Resolve a picker value into concrete start/end instants. Call at query time so rolling presets stay fresh. */
export function resolveTimeRange(value: TimeRangeValue, now: Date = new Date()): ResolvedRange {
  if (value.kind === 'absolute') {
    return { start: value.from, end: value.to }
  }
  const preset = TIME_RANGE_PRESETS.find((p) => p.id === value.presetId)
  if (!preset || preset.durationMs === null) {
    return { start: startOfDay(now), end: now }
  }
  return { start: new Date(now.getTime() - preset.durationMs), end: now }
}

const pad = (n: number): string => String(n).padStart(2, '0')

/** Format as `YYYY-MM-DD HH:mm:ss` (local). */
export function formatLocal(d: Date): string {
  return (
    `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ` +
    `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
  )
}

const LOCAL_PATTERN = /^(\d{4})-(\d{2})-(\d{2})(?:[ T](\d{2}):(\d{2})(?::(\d{2}))?)?$/

/** Parse `YYYY-MM-DD[ HH:mm[:ss]]` as local time. Returns null for invalid input. */
export function parseLocal(text: string): Date | null {
  const m = LOCAL_PATTERN.exec(text.trim())
  if (!m) return null
  const [y, mo, d, h = '0', mi = '0', s = '0'] = m.slice(1)
  const date = new Date(+y, +mo - 1, +d, +h, +mi, +s, 0)
  const roundTrips =
    date.getFullYear() === +y &&
    date.getMonth() === +mo - 1 &&
    date.getDate() === +d &&
    date.getHours() === +h &&
    date.getMinutes() === +mi
  return roundTrips ? date : null
}

/** Naive local ISO string (no zone suffix); matches how the backend stores LogEntry timestamps. */
export function toNaiveIso(d: Date): string {
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
}

/** Short zone abbreviation such as `CDT`, falling back to the IANA name. */
export function localZoneAbbr(now: Date = new Date()): string {
  const parts = new Intl.DateTimeFormat(undefined, { timeZoneName: 'short' }).formatToParts(now)
  return parts.find((p) => p.type === 'timeZoneName')?.value ?? ''
}

export function describeTimeRange(value: TimeRangeValue): string {
  if (value.kind === 'preset') {
    return TIME_RANGE_PRESETS.find((p) => p.id === value.presetId)?.label ?? 'Today'
  }
  const fmt = (d: Date) =>
    d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
  return isSameDay(value.from, value.to)
    ? fmt(value.from)
    : `${fmt(value.from)} \u2013 ${fmt(value.to)}`
}
