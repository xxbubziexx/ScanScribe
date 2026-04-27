export interface TrendData {
  delta: number
  basis?: string
  current?: number
  previous?: number
  direction?: 'up' | 'down' | 'flat'
}

export interface InsightsSummary {
  total: number
  calls_per_minute: number
  unique_talkgroups: number
  avg_duration: number
  peak_hour: string | null
  trends?: {
    total_transcriptions?: TrendData
    calls_last_minute?: TrendData
    unique_talkgroups?: TrendData
  }
}

export interface ActivityPoint {
  label: string
  count: number
  hour?: number
}

export interface TalkgroupEntry {
  talkgroup: string
  count: number
}

export interface LogEntry {
  id: number
  timestamp: string
  talkgroup: string
  transcript: string
  duration: number
  file_size: number
  audio_path: string
}

export interface InsightsStats {
  summary: InsightsSummary
  activity: ActivityPoint[]
  talkgroups: TalkgroupEntry[]
  talkgroups_all: TalkgroupEntry[]
  recent: LogEntry[]
}

export interface HourActivityEntry {
  hour: number
  count: number
}

export interface HourSummary {
  hour: number
  text: string
  created_at: string
  updated_at?: string
}

export interface LiveCpmResponse {
  calls_per_minute: number
  trend?: TrendData
}

export interface SearchFilters {
  keyword: string
  talkgroups: string[]
  hour: string
  sort: string
}

export type InsightsView = 'hourly' | 'daily' | 'weekly'
export type InsightsTab = 'search' | 'talkgroup' | 'summaries' | 'recent'
