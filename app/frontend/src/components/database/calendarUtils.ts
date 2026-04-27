export const CALENDAR_WEEKDAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']

export function toYmdLocal(d: Date): string {
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}

export function parseYmdLocal(ymd: string): Date {
  const [y, m, d] = ymd.split('-').map((x) => parseInt(x, 10))
  return new Date(y, m - 1, d)
}

export function monthStart(d: Date) {
  return new Date(d.getFullYear(), d.getMonth(), 1)
}

export function addMonths(d: Date, n: number) {
  return new Date(d.getFullYear(), d.getMonth() + n, 1)
}

export function buildMonthCells(viewMonth: Date) {
  const first = monthStart(viewMonth)
  const startDow = first.getDay()
  const daysInMonth = new Date(first.getFullYear(), first.getMonth() + 1, 0).getDate()
  const cells: ({ kind: 'pad' } | { kind: 'day'; ymd: string; day: number })[] = []
  for (let i = 0; i < startDow; i += 1) {
    cells.push({ kind: 'pad' })
  }
  for (let day = 1; day <= daysInMonth; day += 1) {
    const d = new Date(first.getFullYear(), first.getMonth(), day)
    cells.push({ kind: 'day', ymd: toYmdLocal(d), day })
  }
  return cells
}

export function pickMin(a: string, b: string) {
  return a <= b ? a : b
}

export function pickMax(a: string, b: string) {
  return a >= b ? a : b
}
