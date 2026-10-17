import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { insights } from '@/lib/insights'
import type { InsightsView } from '@/types/insights'
import { StatsPanel } from './components/StatsPanel'
import { DiurnalHeatmap } from './components/DiurnalHeatmap'
import { RtfThroughputWidget } from './components/RtfThroughputWidget'
import { TacticalNerWidget } from './components/TacticalNerWidget'
import { TrafficAnomalyWidget } from './components/TrafficAnomalyWidget'
import { TalkgroupShareWidget } from './components/TalkgroupShareWidget'
import { AsrConfidenceWidget } from './components/AsrConfidenceWidget'

function todayIso() {
  const d = new Date()
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
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

  const defaultRangeAppliedRef = useRef(false)
  useEffect(() => {
    if (defaultRangeAppliedRef.current || activeDates.length === 0) return
    defaultRangeAppliedRef.current = true
    const last = activeDates[activeDates.length - 1]
    setDateFrom(last)
    setDateTo(last)
  }, [activeDates])

  const { data: statsData } = useQuery({
    queryKey: ['insights-stats', dateFrom, dateTo, view],
    queryFn: () => insights.stats(dateFrom, view, dateTo),
    staleTime: 15_000,
    refetchInterval: 20_000,
    refetchIntervalInBackground: false,
    enabled: !!dateFrom,
  })

  useEffect(() => {
    const poll = async () => {
      if (document.hidden) return
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
  const rtf = statsData?.rtf
  const ner = statsData?.ner
  const anomaly = statsData?.anomaly
  const talkgroups = statsData?.talkgroups ?? []
  const asrQuality = statsData?.asr_quality

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

      {/* Traffic Anomaly & Spike Detector */}
      <TrafficAnomalyWidget data={anomaly} onHourClick={onHourClick} />

      {/* Talkgroup Share of Voice & ASR Quality Spectrum */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <TalkgroupShareWidget data={talkgroups} dateFrom={dateFrom} dateTo={dateTo} />
        <AsrConfidenceWidget data={asrQuality} />
      </div>

      {/* Real-Time Factor & Tactical Semantics Intelligence Widgets */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <RtfThroughputWidget data={rtf} />
        <TacticalNerWidget data={ner} />
      </div>

      <DiurnalHeatmap
        data={heatmap}
        dateFrom={dateFrom}
        dateTo={dateTo}
      />
    </div>
  )
}
