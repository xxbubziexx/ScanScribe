export interface WatcherStatus {
  is_running: boolean
  paused: boolean
  ingest_count: number
  queue_count: number
  files_processed: number
  files_rejected: number
  engine_device: string
  processor_running: boolean
  memory_used_gb: number
  memory_total_gb: number
  memory_percent: number
  cpu_percent: number
}

export interface TranscriptionCard {
  id: string | number
  filename: string
  timestamp: string
  duration: number
  file_size: number
  talkgroup: string
  confidence: number
  transcript: string
  audio_path: string
}

export interface ConsoleEntry {
  id: string
  message: string
  level: 'info' | 'success' | 'warning' | 'error'
  /** ISO timestamp from server (null = use client time, for UI-only messages) */
  timestamp: string | null
}

export type WsMessage =
  | { type: 'log'; level: string; message: string; tag?: string; timestamp: string }
  | { type: 'status'; status: string; data?: Partial<WatcherStatus> }
  | { type: 'transcription'; data: TranscriptionCard }

export interface WatcherActionResponse {
  success: boolean
  message: string
}
