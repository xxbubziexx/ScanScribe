import { request } from '@/lib/api'

export interface RetentionConfig {
  retention_days: number
  cleanup_hour: number | null
}

export interface PurgeOldDataResult {
  message: string
  deleted_count: number
  audio_files_deleted: number
  cutoff_date?: string
}

export interface StorageHealthStats {
  db_bytes: number
  wal_bytes: number
  shm_bytes: number
  total_sqlite_bytes: number
  journal_mode: string
  page_size: number
  page_count: number
  freelist_count: number
  reclaimable_bytes: number
  audio_files_count: number
  audio_bytes: number
  audio_layout: string
  retention_days: number
}

export interface TableInventoryItem {
  key: string
  label: string
  route: string
  row_count: number
  secondary_label: string | null
  secondary_value: string | null
  oldest: string | null
  newest: string | null
}

export interface EntityLabelStat {
  label: string
  total_count: number
  unique_raw_count: number
  pct_of_total: number
}

export interface NerOverviewStats {
  pipeline_enabled: boolean
  ner_only: boolean
  ner_loaded: boolean
  ner_model_path: string
  covered_logs: number
  total_logs: number
  coverage_pct: number
  total_spans: number
  total_observations: number
  labels: EntityLabelStat[]
}

export interface DailyVolumePoint {
  date: string
  count: number
}

export interface TalkgroupVolumeItem {
  talkgroup: string
  count: number
  duration_seconds: number
}

export interface DatabaseOverviewResponse {
  generated_at: string
  storage: StorageHealthStats
  tables: TableInventoryItem[]
  ner: NerOverviewStats
  daily_volume: DailyVolumePoint[]
  top_talkgroups_24h: TalkgroupVolumeItem[]
  logs_last_24h: number
  total_audio_duration_seconds: number
}

export const maintenanceApi = {
  retentionConfig: () => request<RetentionConfig>('/api/maintenance/retention-config'),

  overview: () => request<DatabaseOverviewResponse>('/api/maintenance/overview'),

  purgeOldData: (retentionDays: number) =>
    request<PurgeOldDataResult>('/api/maintenance/purge', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ retention_days: retentionDays }),
    }),
}
