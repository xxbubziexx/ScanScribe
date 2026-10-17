const STORAGE_KEY = 'scanscribe_active_date_range'

export interface PersistentDateRange {
  dateFrom: string
  dateTo: string
}

const DATE_REGEX = /^\d{4}-\d{2}-\d{2}$/

export function getSavedDateRange(): PersistentDateRange | null {
  if (typeof window === 'undefined') return null
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw)
    if (
      parsed &&
      typeof parsed.dateFrom === 'string' &&
      typeof parsed.dateTo === 'string' &&
      DATE_REGEX.test(parsed.dateFrom) &&
      DATE_REGEX.test(parsed.dateTo)
    ) {
      return { dateFrom: parsed.dateFrom, dateTo: parsed.dateTo }
    }
  } catch {
    /* ignore parse errors */
  }
  return null
}

export function saveDateRange(dateFrom: string, dateTo: string) {
  if (typeof window === 'undefined') return
  try {
    if (DATE_REGEX.test(dateFrom) && DATE_REGEX.test(dateTo)) {
      localStorage.setItem(STORAGE_KEY, JSON.stringify({ dateFrom, dateTo }))
      window.dispatchEvent(
        new CustomEvent('scanscribe:date_range_changed', {
          detail: { dateFrom, dateTo },
        }),
      )
    }
  } catch {
    /* ignore storage errors */
  }
}

export function clearSavedDateRange() {
  if (typeof window === 'undefined') return
  try {
    localStorage.removeItem(STORAGE_KEY)
  } catch {
    /* ignore */
  }
}
