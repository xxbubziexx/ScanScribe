import { request } from '@/lib/api'
import type {
  InsightsStats,
  InsightsView,
  LiveCpmResponse,
  HourActivityEntry,
  HourSummary,
  LogEntry,
} from '@/types/insights'

export const insights = {
  stats: (date: string, view: InsightsView) =>
    request<InsightsStats>(`/api/insights/stats?date=${date}&view=${view}`),

  liveCpm: () => request<LiveCpmResponse>('/api/insights/live-cpm'),

  search: (params: URLSearchParams) =>
    request<{ results: LogEntry[]; total: number }>(`/api/insights/search?${params}`),

  activeDates: () => request<{ dates: string[] }>('/api/logs/active-dates'),

  summaryHours: (date: string) =>
    request<{ hours: HourActivityEntry[] }>(`/api/insights/summaries/hours?date=${date}`),

  summaries: (date: string) =>
    request<{ summaries: HourSummary[] }>(`/api/insights/summaries?date=${date}`),

  generateSummary: (date: string, hour: number, force = false) =>
    request<HourSummary>('/api/insights/summaries/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ date, hour, force }),
    }),

  deleteSummary: (date: string, hour: number) =>
    request<{ success: boolean }>(`/api/insights/summaries?date=${date}&hour=${hour}`, {
      method: 'DELETE',
    }),
}
