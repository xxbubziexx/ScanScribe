import { request } from '@/lib/api'
import type { WatcherStatus, WatcherActionResponse } from '@/types/watcher'

export const watcher = {
  status: () => request<WatcherStatus>('/api/watcher/status'),
  start: () => request<WatcherActionResponse>('/api/watcher/start', { method: 'POST' }),
  stop: () => request<WatcherActionResponse>('/api/watcher/stop', { method: 'POST' }),
  pause: () => request<WatcherActionResponse>('/api/watcher/pause', { method: 'POST' }),
  resume: () => request<WatcherActionResponse>('/api/watcher/resume', { method: 'POST' }),
}
