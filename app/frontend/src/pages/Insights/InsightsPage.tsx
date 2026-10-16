import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { insights } from '@/lib/insights'
import type { InsightsView } from '@/types/insights'
import { StatsPanel } from './components/StatsPanel'
import { DiurnalHeatmap } from './components/DiurnalHeatmap'

function todayIso() {
  return new Date().toISOString().split('T')[0]
}

export function InsightsPage() {
  const navigate = useNavigate()
  const [dateFrom, setDateFrom] = useState(todayIso())
  const [dateTo, setDateTo] = useState(todayIso())
  const isMultiDay = dateFrom !== dateTo && !!dateFrom && !!dateTo

  const view: InsightsView = useMemo(() => {
    if (!isMultiDay) return 'hourly'
    const d1 = new Date(dateFrom).getTime()
    const d2 = new Date(dateTo).getTime()
    const diffDays = Math.round(Math.abs(d2 - d1) / (1000 * 3600 * 24)) + 1
    return diffDays > 35 ? 'weekly' : 'daily'
  }, [dateFrom, dateTo, isMultiDay])

  const [liveCpm, setLiveCpm] = useState<number | null>(null)
  const cpmTimerRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const { data: datesData } = useQuery({
    queryKey: ['active-dates'],
    queryFn: () => insights.activeDates(),
    staleTime: 5 * 60 * 1000,
  })

  const activeDates = datesData?.dates ?? []

  useEffect(() => {
    if (activeDates.length > 0) {
      const last = activeDates[activeDates.length - 1]
      setDateFrom(last)
      setDateTo(last)
    }
  }, [activeDates.length]) // eslint-disable-line react-hooks/exhaustive-deps

  const { data: statsData } = useQuery({
    queryKey: ['insights-stats', dateFrom, dateTo, view],
    queryFn: () => insights.stats(dateFrom, view, dateTo),
    staleTime: 30_000,
    refetchInterval: 5_000,
    refetchIntervalInBackground: true,
    enabled: !!dateFrom,
  })

  useEffect(() => {
    const poll = async () => {
      try {
        const data = await insights.liveCpm()
        setLiveCpm(data.calls_per_minute)
      } catch {
        /* ignore */
      }
    }
    poll()
    cpmTimerRef.current = setInterval(poll, 10_000)
    return () => {
      if (cpmTimerRef.current) clearInterval(cpmTimerRef.current)
    }
  }, [])

  function onHourClick(hour: number) {
    const params = new URLSearchParams()
    if (dateFrom) params.set('date_from', dateFrom)
    if (dateTo) params.set('date_to', dateTo)
    params.set('hour', String(hour))
    navigate(`/search?${params.toString()}`)
  }

  const handleDateRangeChange = (from: string, to: string) => {
    setDateFrom(from)
    setDateTo(to)
  }

  const summary = statsData?.summary ?? null
  const activity = statsData?.activity ?? []
  const heatmap = statsData?.heatmap

  return (
    <div className="w-full space-y-4">
      <StatsPanel
        summary={summary}
        liveCpm={liveCpm}
        activity={activity}
        view={view}
        dateFrom={dateFrom}
        dateTo={dateTo}
        activeDates={activeDates}
        onDateRangeChange={handleDateRangeChange}
        onHourClick={onHourClick}
      />

      <DiurnalHeatmap
        data={heatmap}
        dateFrom={dateFrom}
        dateTo={dateTo}
      />
    </div>
  )
}
