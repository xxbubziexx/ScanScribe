/** Transcription log row from GET /api/logs (see app/routes/logs.py). */
export interface LogListEntry {
  id: number
  timestamp: string
  filename: string
  talkgroup: string
  transcript: string
  duration: number
  file_size: number
  confidence: number
  audio_path: string
  log_date: string | null
  created_at: string | null
}

export interface LogsListResponse {
  logs: LogListEntry[]
  total: number
  page: number
  page_size: number
  total_pages: number
}

export type LogsSortBy = 'timestamp_desc' | 'timestamp_asc' | 'filename' | 'talkgroup'
