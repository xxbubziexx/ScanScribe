export interface MonitorResponse {
  id: number
  name: string
  enabled: boolean
  talkgroup_ids: string[]
  start_event_labels: string[]
  geo_region?: string | null
}

export interface MonitorCreate {
  name: string
  talkgroup_ids: string[]
  start_event_labels: string[]
  geo_region?: string | null
}

export interface MonitorUpdate {
  name?: string
  enabled?: boolean
  talkgroup_ids?: string[]
  start_event_labels?: string[]
  geo_region?: string | null
}

export interface NerLabelsResponse {
  labels: string[]
}

/** One row from GET /api/events/debug (pipeline NER / LLM debug log). */
export interface PipelineDebugEntry {
  ts?: number
  llm_model?: string
  monitor_id?: number
  log_entry_id?: number
  action?: string
  event_id?: string
  duration_ms?: number
  transcript?: string
  /** Often a JSON string from the pipeline */
  entities?: string
  raw_output?: string
  llm_output?: string
  error?: string
}

export interface EventListItem {
  id: number
  event_id: string
  monitor_id: number
  status: string
  event_type: string | null
  broadcast_type: string | null
  location: string | null
  latitude: number | null
  longitude: number | null
  resolved_address: string | null
  units: string | null
  status_detail: string | null
  original_transcription: string | null
  summary: string | null
  created_at: string | null
  incident_at: string | null
  closed_at: string | null
  spans_attached: number
  talkgroup: string
}

export interface EventsListResponse {
  items: EventListItem[]
  total: number
}

export interface EventDetailHeader {
  event_id: string
  monitor_id: number
  monitor_name: string
  status: string
  event_type: string | null
  broadcast_type: string | null
  location: string | null
  latitude: number | null
  longitude: number | null
  resolved_address: string | null
  units: string | null
  status_detail: string | null
  original_transcription: string | null
  summary: string | null
  created_at: string | null
  incident_at: string | null
  closed_at: string | null
}

export interface EventTranscript {
  log_entry_id: number
  timestamp: string | null
  talkgroup: string | null
  transcript: string | null
  entities: Record<string, string[]> | null
  audio_path: string
  has_playback: boolean
  is_trigger: boolean
  llm_reason: string
}

export interface EventDetailResponse {
  event: EventDetailHeader
  transcripts: EventTranscript[]
}

export interface SpanStoreRow {
  id: number
  monitor_id: number
  talkgroup: string | null
  log_entry_id: number | null
  transcript: string | null
  evt_type: string | null
  units: string | null
  locations: string | null
  addresses: string | null
  status: string | null
  time_mentions: string | null
  created_at: string | null
  attached_event_ids: string[]
}

export interface SpanStoreListResponse {
  items: SpanStoreRow[]
  total: number
}
