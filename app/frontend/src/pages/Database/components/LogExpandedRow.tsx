import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useToast } from '@/context/ToastContext'
import { logsApi } from '@/lib/logs'
import { errorMessage } from '@/types/api'
import type { LogListEntry } from '@/types/logs'
import { formatBytes } from '../utils/formatBytes'
import { ScAudioPlayer } from './ScAudioPlayer'

function confidenceTone(confidence: number | null | undefined): string {
  if (confidence == null || !Number.isFinite(confidence)) return 'text-slate-400'
  const pct = confidence * 100
  if (pct >= 85) return 'text-emerald-400'
  if (pct >= 65) return 'text-amber-300'
  return 'text-rose-400'
}

export interface LogExpandedRowProps {
  row: LogListEntry
  showUnreview?: boolean
}

export function LogExpandedRow({ row, showUnreview = false }: LogExpandedRowProps) {
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

  const unreviewMutation = useMutation({
    mutationFn: () => logsApi.unreview(row.id),
    onSuccess: () => {
      addToast('Removed from dataset', 'success')
      void queryClient.invalidateQueries({ queryKey: ['dataset-logs'] })
      void queryClient.invalidateQueries({ queryKey: ['database-logs'] })
      void queryClient.invalidateQueries({ queryKey: ['database-overview'] })
    },
    onError: (e: unknown) => addToast(errorMessage(e, 'Remove failed'), 'error'),
  })

  return (
    <div className="ss-db-expand">
      <div className="ss-db-expand-inner">
        <div className="ss-db-expand-meta">
          <div className="ss-db-expand-strip">
            <div className="ss-db-expand-field">
              <span className="ss-db-expand-label">ID</span>
              <span className="ss-db-expand-value font-mono font-semibold text-slate-300">#{row.id}</span>
            </div>
            <div className="ss-db-expand-field">
              <span className="ss-db-expand-label">Talkgroup</span>
              <span className="ss-db-expand-value font-semibold text-sky-300">
                {row.talkgroup || '—'}
              </span>
            </div>
            <div className="ss-db-expand-field">
              <span className="ss-db-expand-label">Date &amp; Time</span>
              <span className="ss-db-expand-value font-mono text-slate-200">{ts}</span>
            </div>
            <div className="ss-db-expand-field">
              <span className="ss-db-expand-label">Duration</span>
              <span className="ss-db-expand-value font-mono font-semibold text-amber-300">
                {typeof row.duration === 'number' ? `${row.duration.toFixed(2)}s` : '—'}
              </span>
            </div>
            <div className="ss-db-expand-field">
              <span className="ss-db-expand-label">File Size</span>
              <span className="ss-db-expand-value font-mono text-slate-300">
                {formatBytes(row.file_size || 0)}
              </span>
            </div>
            <div className="ss-db-expand-field">
              <span className="ss-db-expand-label">Confidence</span>
              <span className={`ss-db-expand-value font-mono font-semibold ${confidenceTone(row.confidence)}`}>
                {confidence}
              </span>
            </div>
          </div>

          <div className="ss-db-expand-files">
            <div className="ss-db-expand-field">
              <span className="ss-db-expand-label">Filename</span>
              <span className="ss-db-expand-value font-mono text-[11px] text-slate-300">
                {row.filename || '—'}
              </span>
            </div>
            <div className="ss-db-expand-field">
              <span className="ss-db-expand-label">Audio Path</span>
              <span className="ss-db-expand-value font-mono text-[11px] text-slate-500">
                {row.audio_path || '—'}
              </span>
            </div>
          </div>
        </div>

        <div className={hasAudio ? 'ss-db-expand-body' : ''}>
          <div className="ss-db-expand-card">
            <div className="mb-1.5 flex flex-wrap items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <span className="ss-db-expand-label mb-0">Full transcript</span>
                {row.is_reviewed && (
                  <span className="rounded-sm border border-emerald-500/30 bg-emerald-500/15 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-emerald-300">
                    Reviewed
                  </span>
                )}
              </div>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  className="ss-btn-primary h-7 px-2.5 text-xs cursor-pointer"
                  onClick={() => reviewMutation.mutate(text)}
                  disabled={reviewMutation.isPending}
                >
                  {reviewMutation.isPending ? 'Saving...' : 'Accept & Save'}
                </button>
                {showUnreview && (
                  <button
                    type="button"
                    className="ss-btn-ghost h-7 px-2.5 text-xs text-rose-400 hover:bg-rose-500/10 hover:text-rose-300 cursor-pointer"
                    onClick={() => unreviewMutation.mutate()}
                    disabled={unreviewMutation.isPending}
                  >
                    {unreviewMutation.isPending ? 'Removing...' : 'Remove from Dataset'}
                  </button>
                )}
              </div>
            </div>
            <textarea
              rows={3}
              className="min-h-[68px] w-full rounded-sm border border-[#242c3d] bg-[#090d16] px-2.5 py-1.5 font-mono text-xs leading-relaxed text-slate-100 focus:border-indigo-500 focus:outline-none"
              value={text}
              onChange={(e) => setText(e.target.value)}
            />
          </div>

          {hasAudio && (
            <div className="ss-db-expand-card">
              <span className="ss-db-expand-label mb-1.5">Audio playback</span>
              <ScAudioPlayer src={audioSrc} />
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
