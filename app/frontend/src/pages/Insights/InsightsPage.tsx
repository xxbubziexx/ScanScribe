import { useEffect, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { insights } from '@/lib/insights'
import type { InsightsTab, InsightsView, SearchFilters, TalkgroupEntry } from '@/types/insights'
import { StatsPanel } from './components/StatsPanel'
import { SearchTab } from './tabs/SearchTab'
import { TalkgroupTab } from './tabs/TalkgroupTab'
import { SummariesTab } from './tabs/SummariesTab'
import { RecentTab } from './tabs/RecentTab'

const TABS: { id: InsightsTab; label: string }[] = [
  { id: 'search', label: '🔍 Search & Filter' },
  { id: 'talkgroup', label: '📡 Talkgroup Activity' },
  { id: 'summaries', label: '📝 Summaries' },
  { id: 'recent', label: '🕐 Live Activity' },
]

const DEFAULT_FILTERS: SearchFilters = {
  keyword: '',
  talkgroups: [],
  hour: '',
  sort: 'newest',
}

function todayIso() {
  return new Date().toISOString().split('T')[0]
}

export function InsightsPage() {
  const [date, setDate] = useState(todayIso())
  const [view, setView] = useState<InsightsView>('hourly')
  const [activeTab, setActiveTab] = useState<InsightsTab>(() => {
    const saved = localStorage.getItem('insights_active_tab')
    return (saved as InsightsTab) ?? 'search'
  })
  const [searchFilters, setSearchFilters] = useState<SearchFilters>(DEFAULT_FILTERS)
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
      setDate(activeDates[activeDates.length - 1])
    }
  }, [activeDates.length]) // eslint-disable-line react-hooks/exhaustive-deps

  const { data: statsData } = useQuery({
    queryKey: ['insights-stats', date, view],
    queryFn: () => insights.stats(date, view),
    staleTime: 30_000,
    refetchInterval: 5_000,
    refetchIntervalInBackground: true,
    enabled: !!date,
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

  function switchTab(tab: InsightsTab) {
    setActiveTab(tab)
    localStorage.setItem('insights_active_tab', tab)
  }

  function onHourClick(hour: number) {
    setSearchFilters((f) => ({ ...f, hour: String(hour) }))
    switchTab('search')
  }

  function onTalkgroupClick(tg: string) {
    setSearchFilters((f) => ({
      ...f,
      talkgroups: f.talkgroups.includes(tg) ? f.talkgroups : [...f.talkgroups, tg],
    }))
    switchTab('search')
  }

  const summary = statsData?.summary ?? null
  const activity = statsData?.activity ?? []
  const talkgroups: TalkgroupEntry[] = statsData?.talkgroups ?? []
  const allTalkgroups: TalkgroupEntry[] = statsData?.talkgroups_all ?? []
  const recent = statsData?.recent ?? []

  return (
    <div className="w-full">
      <StatsPanel
        summary={summary}
        liveCpm={liveCpm}
        activity={activity}
        view={view}
        date={date}
        activeDates={activeDates}
        onViewChange={setView}
        onDateChange={setDate}
        onHourClick={onHourClick}
      />

      <div className="ss-insights-tabs">
        <div className="ss-insights-tabrow" role="tablist">
          {TABS.map(({ id, label }) => (
            <button
              key={id}
              type="button"
              role="tab"
              aria-selected={activeTab === id}
              onClick={() => switchTab(id)}
              className={
                activeTab === id
                  ? 'ss-insights-tab ss-insights-tab--active'
                  : 'ss-insights-tab'
              }
            >
              {label}
            </button>
          ))}
        </div>

        <div className="ss-insights-tabpanel">
          {activeTab === 'search' && (
            <SearchTab
              date={date}
              allTalkgroups={allTalkgroups}
              filters={searchFilters}
              onFiltersChange={setSearchFilters}
              onTalkgroupFilter={() => switchTab('search')}
            />
          )}
          {activeTab === 'talkgroup' && (
            <TalkgroupTab talkgroups={talkgroups} onTalkgroupClick={onTalkgroupClick} />
          )}
          {activeTab === 'summaries' && <SummariesTab date={date} />}
          {activeTab === 'recent' && <RecentTab recent={recent} />}
        </div>
      </div>
    </div>
  )
}
