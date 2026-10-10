import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useToast } from '@/context/ToastContext'
import { logsApi } from '@/lib/logs'
import { errorMessage } from '@/types/api'
import type { LogListEntry } from '@/types/logs'
import { formatBytes } from '../utils/formatBytes'
import { ScAudioPlayer } from './ScAudioPlayer'

function kv(label: string, value: string) {
  return (
    <div className="ss-db-expand-field">
      <span className="ss-db-expand-label">{label}</span>
      <span className="ss-db-expand-value">{value}</span>
    </div>
  )
}

export function LogExpandedRow({ row }: { row: LogListEntry }) {
  const hasAudio = !!row.audio_path && row.audio_path !== 'file not saved'
  const audioSrc = hasAudio ? `/${row.audio_path}` : ''
  const ts = row.timestamp
    ? new Date(row.timestamp).toLocaleString(undefined, {
        dateStyle: 'short',
        timeStyle: 'medium',
      })
    : '—'
  const confidence = row.confidence != null ? `${Math.round(row.confidence * 100)}%` : '—'

  const [text, setText] = useState(row.corrected_transcript ?? row.transcript ?? '')
  const queryClient = useQueryClient()
  const { addToast } = useToast()
  const reviewMutation = useMutation({
    mutationFn: (newText: string) => logsApi.review(row.id, newText),
    onSuccess: () => {
      addToast('Transcript updated', 'success')
      void queryClient.invalidateQueries({ queryKey: ['database-logs'] })
      void queryClient.invalidateQueries({ queryKey: ['dataset-logs'] })
    },
    onError: (e: unknown) => addToast(errorMessage(e, 'Update failed'), 'error'),
  })

  return (
    <div className="ss-db-expand">
      <div className="ss-db-expand-grid">
        {kv('ID', String(row.id))}
        {kv('Filename', row.filename || '—')}
        {kv('Talkgroup', row.talkgroup || '—')}
        {kv('Date & time', ts)}
        {kv(
          'Duration',
          typeof row.duration === 'number' ? `${row.duration.toFixed(2)} seconds` : '—',
        )}
        {kv('File size', formatBytes(row.file_size || 0))}
        {kv('Confidence', confidence)}
        {kv('Audio path', row.audio_path || '—')}
      </div>

      <div className="ss-db-expand-field mt-4">
        <span className="ss-db-expand-label flex items-center gap-2">
          Full transcript{' '}
          {row.is_reviewed && <span className="text-green-500 text-sm">✓ Reviewed</span>}
        </span>
        <textarea
          className="ss-input mt-1 w-full min-h-[100px] font-mono text-sm"
          value={text}
          onChange={(e) => setText(e.target.value)}
        />
        <div className="mt-2 flex gap-2">
          <button
            type="button"
            className="ss-btn-primary"
            onClick={() => reviewMutation.mutate(text)}
            disabled={reviewMutation.isPending}
          >
            {reviewMutation.isPending ? 'Saving...' : 'Accept & Save'}
          </button>
        </div>
      </div>

      {hasAudio && (
        <div className="ss-db-expand-audio mt-4">
          <span className="ss-db-expand-label">Audio playback</span>
          <ScAudioPlayer src={audioSrc} />
        </div>
      )}
    </div>
  )
}
