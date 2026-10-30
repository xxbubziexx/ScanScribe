import { useCallback, useState } from 'react'
import { isPageReload, todayIso } from '@/lib/dateSelection'

/**
 * In-memory date range hook defaulting to the current day.
 * Cross-page persistence has been retired per operational requirement.
 */
export function usePersistentDateRange(defaultFrom?: string, defaultTo?: string) {
  const [range, setRange] = useState(() => {
    const today = todayIso()
    if (isPageReload()) {
      return { dateFrom: today, dateTo: today }
    }
    return {
      dateFrom: defaultFrom ?? today,
      dateTo: defaultTo ?? (defaultFrom ?? today),
    }
  })

  const setDateRange = useCallback((from: string, to: string) => {
    setRange({ dateFrom: from, dateTo: to })
  }, [])

  return {
    dateFrom: range.dateFrom,
    dateTo: range.dateTo,
    setDateRange,
  }
}
