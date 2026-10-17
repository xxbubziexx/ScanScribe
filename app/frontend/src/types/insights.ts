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
  total_airtime?: number | null
  peak_hour: string | null
  calls_last_minute?: number | null
  calls_per_minute_window?: number | null
  is_multi_day?: boolean | null
  range_days?: number | null
  trends?: {
    total_transcriptions?: TrendData
    calls_last_minute?: TrendData
    unique_talkgroups?: TrendData
  } | null
}

export interface ActivityPoint {
  label: string
  count: number
  events_count?: number
  hour?: number
}

export interface TalkgroupEntry {
  talkgroup: string
  count: number
  duration?: number
  avg_duration?: number
  percentage?: number
}

export interface AttachedEventInfo {
  id: number
  event_id: string
  status: 'open' | 'closed' | string
  event_type?: string | null
}

export interface TransmissionEntities {
  units?: string[]
  locations?: string[]
  call_types?: string[]
  status?: string[]
}

export interface LogEntry {
  id: number
  timestamp: string
  talkgroup: string
  transcript: string
  duration: number
  file_size: number
  audio_path: string
  confidence?: number
  attached_events?: AttachedEventInfo[]
  entities?: TransmissionEntities
}

export interface HeatmapHourCell {
  hour: number
  label: string
  count: number
  duration: number
}

export interface HeatmapDayRow {
  day: number // 0 = Sun .. 6 = Sat
  day_label: string
  hours: HeatmapHourCell[]
  day_total: number
}

export interface DiurnalHeatmapData {
  matrix: HeatmapDayRow[]
  max_count: number
  total_calls: number
  total_airtime: number
  peak_day: string
  peak_hour: string
  range_start: string
  range_end: string
}

export interface RtfHourlyPoint {
  hour: number
  label: string
  count: number
  rtf: number
  audio_s: number
  proc_s: number
}

export interface RtfTelemetry {
  rtf: number
  speedup: number
  total_audio_s: number
  total_proc_s: number
  avg_latency_ms: number
  avg_duration_s: number
  avg_confidence: number
  model_used: string
  status: 'nominal' | 'moderate' | 'saturated' | 'backlog'
  insufficient_data: boolean
  timeline: RtfHourlyPoint[]
}

export interface TacticalEntityItem {
  canonical: string
  label: 'UNIT' | 'EVT_TYPE' | 'LOC' | 'ADDRESS' | 'STATUS' | string
  freq: number
  first_seen?: string | null
  last_seen?: string | null
  sample_tx_id?: number | null
}

export interface TacticalNerSummary {
  all: TacticalEntityItem[]
  units: TacticalEntityItem[]
  call_types: TacticalEntityItem[]
  locations: TacticalEntityItem[]
  status: TacticalEntityItem[]
  total_entities_detected: number
  insufficient_data: boolean
}

export interface AnomalyTimelinePoint {
  hour: number
  label: string
  observed: number
  baseline: number
  upper_bound: number
  z_score: number
  is_anomaly: boolean
}

export interface AnomalyDriver {
  talkgroup: string
  count: number
  percentage: number
}

export interface AnomalyIncidentRecord {
  date?: string | null
  hour: number
  time_window: string
  z_score: number
  observed: number
  baseline: number
  primary_driver: string
  likely_incident?: string | null
}

export interface TrafficAnomalyTelemetry {
  current_hour_label: string
  observed: number
  baseline: number
  surge_percentage: number
  z_score: number
  severity: 'normal' | 'elevated' | 'high' | 'critical'
  status_label: string
  primary_driver: string
  drivers: AnomalyDriver[]
  timeline: AnomalyTimelinePoint[]
  recent_anomalies: AnomalyIncidentRecord[]
  insufficient_data: boolean
  is_multi_day?: boolean
  range_days?: number | null
}

export interface AsrQualitySpectrum {
  high_count: number
  high_percentage: number
  moderate_count: number
  moderate_percentage: number
  low_count: number
  low_percentage: number
  mean_confidence: number
  total_evaluated: number
  insufficient_data: boolean
}

export interface InsightsStats {
  summary: InsightsSummary
  activity: ActivityPoint[]
  talkgroups: TalkgroupEntry[]
  talkgroups_all: TalkgroupEntry[]
  recent: LogEntry[]
  heatmap?: DiurnalHeatmapData
  rtf?: RtfTelemetry
  ner?: TacticalNerSummary
  anomaly?: TrafficAnomalyTelemetry
  asr_quality?: AsrQualitySpectrum
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
  limit?: number
}

export type InsightsView = 'hourly' | 'daily' | 'weekly'
export type InsightsTab = 'search' | 'talkgroup' | 'summaries' | 'recent'
