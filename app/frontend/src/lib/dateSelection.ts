const STORAGE_KEY = 'scanscribe_active_date_range'

export interface PersistentDateRange {
  dateFrom: string
  dateTo: string
}

/**
 * Get today's local date as YYYY-MM-DD.
 */
export function todayIso(): string {
  const now = new Date()
  const y = now.getFullYear()
  const m = String(now.getMonth() + 1).padStart(2, '0')
  const d = String(now.getDate()).padStart(2, '0')
  return `${y}-${m}-${d}`
}

/**
 * Detect whether the current page load was triggered by a browser refresh/reload.
 */
export function isPageReload(): boolean {
  if (typeof window === 'undefined') return false
  try {
    const entries = performance.getEntriesByType('navigation')
    if (entries.length > 0) {
      return (entries[0] as PerformanceNavigationTiming).type === 'reload'
    }
    return (performance as any)?.navigation?.type === 1
  } catch {
    return false
  }
}

/**
 * Resolves the initial date range for page loads.
 * On browser reload/refresh, ALWAYS resets to only the current day (todayIso()).
 * On fresh navigation, defaults to todayIso() unless explicit URL query parameters specify dates.
 */
export function getInitialDateRange(searchParams?: URLSearchParams): { from: string; to: string } {
  const today = todayIso()
  if (isPageReload() || !searchParams) {
    return { from: today, to: today }
  }

  const pFrom = searchParams.get('date_from') || searchParams.get('date')
  const pTo = searchParams.get('date_to') || searchParams.get('date')

  if (!pFrom && !pTo) {
    return { from: today, to: today }
  }

  const from = pFrom || today
  const to = pTo || from
  return { from, to }
}

/**
 * Cross-page date range persistence has been retired per operational requirement.
 * Every page defaults independently to today on load/reload.
 */
export function getSavedDateRange(): PersistentDateRange | null {
  return null
}

export function saveDateRange(_dateFrom: string, _dateTo: string) {
  // Retired: date ranges do not persist across pages.
}

export function clearSavedDateRange() {
  if (typeof window === 'undefined') return
  try {
    localStorage.removeItem(STORAGE_KEY)
  } catch {
    /* ignore */
  }
}

// Clean up any legacy localStorage key on load
if (typeof window !== 'undefined') {
  clearSavedDateRange()
}
