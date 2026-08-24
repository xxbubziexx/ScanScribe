import { request } from '@/lib/api'
import { ApiError } from '@/types/api'

const BASE = import.meta.env.VITE_API_BASE ?? ''

function getToken(): string | null {
  return localStorage.getItem('access_token')
}

export interface ConfigPayload {
  content: string
}

export interface AudioStorageStats {
  total_files: number
  total_size_bytes: number
  total_size_mb: number
  total_size_gb: number
  file_types: Record<string, { count: number; size: number }>
  directory: string
}

export interface AudioPurgeResult {
  success: boolean
  deleted_files: number
  deleted_size_mb: number
  database_updated: number
  errors: string[]
}

export const settingsApi = {
  getConfig: () => request<ConfigPayload>('/api/settings/config'),

  saveConfig: (content: string) =>
    request<{ message: string }>('/api/settings/config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ content }),
    }),

  restart: () => request<{ message: string }>('/api/settings/restart', { method: 'POST' }),

  audioStorageStats: () => request<AudioStorageStats>('/api/settings/audio-storage/stats'),

  purgeAudio: () =>
    request<AudioPurgeResult>('/api/settings/audio-storage/purge', { method: 'POST' }),
}

/** ZIP download — uses fetch so we can read the binary body with Bearer auth. */
export async function downloadAudioZip(): Promise<void> {
  const token = getToken()
  const res = await fetch(`${BASE}/api/settings/audio-storage/download-zip`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  })
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`
    try {
      const body: unknown = await res.json()
      if (body && typeof body === 'object' && 'detail' in body) {
        const d = (body as { detail: unknown }).detail
        detail = typeof d === 'string' ? d : String(d)
      }
    } catch {
      // ignore
    }
    if (res.status === 401) {
      localStorage.removeItem('access_token')
      localStorage.removeItem('username')
    }
    throw new ApiError(detail, res.status)
  }
  const blob = await res.blob()
  const disposition = res.headers.get('Content-Disposition')
  let filename = 'scanscribe_audio.zip'
  if (disposition?.includes('filename=')) {
    filename = disposition.split('filename=')[1].replace(/"/g, '').trim()
  }
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}
