import { downloadAudioFile } from '@/lib/logs'
import type { LogListEntry } from '@/types/logs'
import { formatBytes } from '../utils/formatBytes'

export function LogRow({
  row,
  isAdmin,
  selected,
  onToggleSelect,
  onDelete,
  deleting,
  expanded,
  onToggleExpand,
}: {
  row: LogListEntry
  isAdmin: boolean
  selected: boolean
  onToggleSelect: () => void
  onDelete: (id: number) => void
  deleting: boolean
  expanded: boolean
  onToggleExpand: () => void
}) {
  const hasAudio = row.audio_path && row.audio_path !== 'file not saved'
  const transcriptText = row.corrected_transcript || row.transcript || '—'
  const isVadRejected = transcriptText.trim().toUpperCase() === 'VAD_REJECTED'
  const confPct = row.confidence != null ? Math.round(row.confidence * 100) : null
  const confClass =
    confPct == null
      ? 'text-slate-500'
      : confPct >= 85
        ? 'font-bold text-emerald-400'
        : confPct >= 65
          ? 'font-semibold text-amber-300'
          : 'font-semibold text-rose-400'

  return (
    <tr
      className={`ss-db-row ${expanded ? 'ss-db-row--expanded' : ''} ${
        selected ? 'bg-indigo-500/[0.08]' : ''
      }`}
      onClick={onToggleExpand}
      aria-expanded={expanded}
    >
      <td
        className="w-9 text-center"
        onClick={(e) => {
          e.stopPropagation()
        }}
      >
        <input
          type="checkbox"
          className="h-4 w-4 accent-indigo-500 cursor-pointer"
          checked={selected}
          onChange={onToggleSelect}
          aria-label={`Select log entry ${row.id}`}
        />
      </td>
      <td className="whitespace-nowrap font-mono text-xs text-slate-300">
        <span className={`ss-db-expand-icon ${expanded ? 'ss-db-expand-icon--open' : ''}`}>▶</span>{' '}
        {row.timestamp
          ? new Date(row.timestamp).toLocaleString(undefined, {
              dateStyle: 'short',
              timeStyle: 'short',
            })
          : '—'}
      </td>
      <td>
        <span
          className="inline-block max-w-[13rem] truncate font-semibold text-sky-300"
          title={row.talkgroup ?? ''}
        >
          {row.talkgroup || '—'}
        </span>
      </td>
      <td title={row.filename}>
        <span className="block max-w-[18rem] truncate font-mono text-[11px] text-slate-500">
          {row.filename || '—'}
        </span>
      </td>
      <td>
        <span
          className={`ss-db-td-clip block ${
            isVadRejected ? 'font-mono text-[11px] italic text-zinc-500' : 'font-medium text-slate-100'
          }`}
        >
          {row.is_reviewed && (
            <span className="text-emerald-400 font-bold mr-1" title="Reviewed">
              ✓
            </span>
          )}
          {transcriptText}
        </span>
      </td>
      <td className="whitespace-nowrap font-mono font-medium tabular-nums text-amber-300/90">
        {typeof row.duration === 'number' ? `${row.duration.toFixed(1)}s` : '—'}
      </td>
      <td className="whitespace-nowrap font-mono tabular-nums text-slate-400">
        {formatBytes(row.file_size || 0)}
      </td>
      <td className={`whitespace-nowrap font-mono tabular-nums ${confClass}`}>
        {confPct != null ? `${confPct}%` : '—'}
      </td>
      <td className="text-right">
        <div className="ss-db-actions">
          {hasAudio && (
            <button
              type="button"
              className="rounded px-2 py-0.5 text-[11px] font-medium text-sky-300 transition hover:bg-sky-500/15 hover:text-sky-200 cursor-pointer"
              onClick={(e) => {
                e.stopPropagation()
                void downloadAudioFile(row.audio_path!, row.filename || undefined).catch((err) => {
                  console.error('Download failed:', err)
                })
              }}
              title="Download audio file directly"
              aria-label="Download audio file directly"
            >
              Audio
            </button>
          )}
          {isAdmin && (
            <button
              type="button"
              className="rounded px-2 py-0.5 text-[11px] font-medium text-rose-400 transition hover:bg-rose-500/15 hover:text-rose-300 cursor-pointer disabled:opacity-40"
              onClick={(e) => {
                e.stopPropagation()
                onDelete(row.id)
              }}
              disabled={deleting}
              title="Remove log entry"
              aria-label="Remove log entry"
            >
              Delete
            </button>
          )}
        </div>
      </td>
    </tr>
  )
}
