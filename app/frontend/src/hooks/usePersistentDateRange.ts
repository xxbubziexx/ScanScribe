import { useCallback, useEffect, useState } from 'react'
import { getSavedDateRange, saveDateRange } from '@/lib/dateSelection'

export function usePersistentDateRange(defaultFrom?: string, defaultTo?: string) {
  const [range, setRange] = useState(() => {
    const saved = getSavedDateRange()
    if (saved) return saved
    return {
      dateFrom: defaultFrom ?? '',
      dateTo: defaultTo ?? (defaultFrom ?? ''),
    }
  })

  useEffect(() => {
    if (typeof window === 'undefined') return
    const handler = (e: Event) => {
      const customEvent = e as CustomEvent<{ dateFrom: string; dateTo: string }>
      if (customEvent.detail) {
        setRange(customEvent.detail)
      }
    }
    window.addEventListener('scanscribe:date_range_changed', handler)
    return () => window.removeEventListener('scanscribe:date_range_changed', handler)
  }, [])

  const setDateRange = useCallback((from: string, to: string) => {
    setRange({ dateFrom: from, dateTo: to })
    saveDateRange(from, to)
  }, [])

  return {
    dateFrom: range.dateFrom,
    dateTo: range.dateTo,
    setDateRange,
  }
}
