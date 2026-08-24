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

export const maintenanceApi = {
  retentionConfig: () => request<RetentionConfig>('/api/maintenance/retention-config'),

  purgeOldData: (retentionDays: number) =>
    request<PurgeOldDataResult>('/api/maintenance/purge', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ retention_days: retentionDays }),
    }),
}
