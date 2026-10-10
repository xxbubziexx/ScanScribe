import { downloadAudioFile } from '@/lib/logs'
import type { LogListEntry } from '@/types/logs'
import { formatBytes } from '../utils/formatBytes'
import { LogExpandedRow } from './LogExpandedRow'

export function MobileLogCard({
  row,
  isAdmin,
  onDelete,
  deleting,
  expanded,
  onToggleExpand,
}: {
  row: LogListEntry
  isAdmin: boolean
  onDelete: (id: number) => void
  deleting: boolean
  expanded: boolean
  onToggleExpand: () => void
}) {
  const hasAudio = row.audio_path && row.audio_path !== 'file not saved'
  const confidencePercent = row.confidence != null ? Math.round(row.confidence * 100) : null
  const confidenceColor =
    confidencePercent != null
      ? confidencePercent >= 85
        ? 'bg-emerald-500/20 text-emerald-300 border-emerald-500/30'
        : confidencePercent >= 60
          ? 'bg-amber-500/20 text-amber-300 border-amber-500/30'
          : 'bg-red-500/20 text-red-300 border-red-500/30'
      : 'bg-white/10 text-gray-400 border-white/10'

  return (
    <article
      className={`p-3.5 rounded-xl border transition flex flex-col gap-2.5 ${
        expanded
          ? 'bg-indigo-950/30 border-indigo-500/40 shadow-lg'
          : 'bg-white/[0.02] border-white/10 hover:border-white/20'
      }`}
    >
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0">
          <span className="px-2 py-0.5 rounded-md bg-indigo-500/20 border border-indigo-400/30 text-indigo-200 text-xs font-semibold font-mono truncate max-w-[140px]">
            {row.talkgroup || 'No Talkgroup'}
          </span>
          {confidencePercent != null && (
            <span
              className={`px-1.5 py-0.5 rounded text-[10px] font-semibold border ${confidenceColor}`}
            >
              {confidencePercent}%
            </span>
          )}
        </div>
        <time className="text-xs font-mono text-gray-400 shrink-0">
          {row.timestamp
            ? new Date(row.timestamp).toLocaleString(undefined, {
                dateStyle: 'short',
                timeStyle: 'short',
              })
            : '—'}
        </time>
      </div>

      <div className="text-sm text-gray-200 leading-relaxed break-words bg-black/20 p-2.5 rounded-lg border border-white/5">
        {row.is_reviewed && (
          <span className="text-green-400 font-bold mr-1.5" title="Reviewed">
            ✓
          </span>
        )}
        <span className={expanded ? '' : 'line-clamp-3'}>
          {row.corrected_transcript || row.transcript || (
            <span className="text-gray-500 italic">No transcript</span>
          )}
        </span>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1 text-xs text-gray-400">
        <span
          className="truncate max-w-[200px] font-mono text-[11px] text-gray-400"
          title={row.filename}
        >
          📄 {row.filename || '—'}
        </span>
        <div className="flex items-center gap-2 text-[11px] font-mono shrink-0 text-gray-400">
          <span>⏱️ {typeof row.duration === 'number' ? `${row.duration.toFixed(1)}s` : '—'}</span>
          <span>·</span>
          <span>💾 {formatBytes(row.file_size || 0)}</span>
        </div>
      </div>

      <div className="flex items-center justify-between gap-2 pt-2 border-t border-white/5">
        <button
          type="button"
          onClick={onToggleExpand}
          className="text-xs text-indigo-400 hover:text-indigo-300 font-medium flex items-center gap-1.5 min-h-[38px] px-2 py-1 rounded hover:bg-white/5 cursor-pointer"
          aria-expanded={expanded}
        >
          <span>{expanded ? '▲ Hide Details & Edit' : '▼ Details & Audio'}</span>
        </button>

        <div className="flex items-center gap-2">
          {hasAudio && (
            <button
              type="button"
              className="w-10 h-10 flex items-center justify-center rounded-lg border border-white/10 bg-white/5 hover:bg-white/10 text-gray-200 transition text-sm cursor-pointer"
              onClick={() => {
                void downloadAudioFile(row.audio_path!, row.filename || undefined).catch((err) => {
                  console.error('Download failed:', err)
                })
              }}
              title="Download audio file directly"
              aria-label="Download audio file"
            >
              ⬇️
            </button>
          )}

          {isAdmin && (
            <button
              type="button"
              className="w-10 h-10 flex items-center justify-center rounded-lg border border-red-500/20 bg-red-500/10 hover:bg-red-500/20 text-red-300 transition text-sm cursor-pointer disabled:opacity-40"
              onClick={() => onDelete(row.id)}
              disabled={deleting}
              title="Remove log entry"
              aria-label="Remove log entry"
            >
              🗑️
            </button>
          )}
        </div>
      </div>

      {expanded && (
        <div className="pt-2 border-t border-white/10">
          <LogExpandedRow row={row} />
        </div>
      )}
    </article>
  )
}
