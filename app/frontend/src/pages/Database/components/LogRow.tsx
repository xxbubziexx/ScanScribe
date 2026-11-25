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
  return (
    <tr
      className={`ss-db-row ${expanded ? 'ss-db-row--expanded' : ''} ${
        selected ? 'bg-indigo-500/[0.08]' : ''
      }`}
      onClick={onToggleExpand}
      aria-expanded={expanded}
    >
      <td
        className="ss-db-td w-9 text-center"
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
      <td className="ss-db-td font-mono text-xs text-gray-400">
        <span className={`ss-db-expand-icon ${expanded ? 'ss-db-expand-icon--open' : ''}`}>▶</span>{' '}
        {row.timestamp
          ? new Date(row.timestamp).toLocaleString(undefined, {
              dateStyle: 'short',
              timeStyle: 'short',
            })
          : '—'}
      </td>
      <td className="ss-db-td">
        <span
          className="inline-block max-w-[12rem] truncate text-indigo-200"
          title={row.talkgroup ?? ''}
        >
          {row.talkgroup || '—'}
        </span>
      </td>
      <td className="ss-db-td" title={row.filename}>
        <span className="ss-db-filename-clip block">{row.filename || '—'}</span>
      </td>
      <td className="ss-db-td">
        <span className="ss-db-td-clip block text-gray-400">
          {row.is_reviewed && (
            <span className="text-green-500 mr-1" title="Reviewed">
              ✓
            </span>
          )}
          {row.corrected_transcript || row.transcript || '—'}
        </span>
      </td>
      <td className="ss-db-td tabular-nums text-gray-500">
        {typeof row.duration === 'number' ? row.duration.toFixed(1) : '—'}
      </td>
      <td className="ss-db-td text-gray-500">{formatBytes(row.file_size || 0)}</td>
      <td className="ss-db-td tabular-nums text-gray-500">
        {row.confidence != null ? `${Math.round(row.confidence * 100)}%` : '—'}
      </td>
      <td className="ss-db-td text-right">
        <div className="ss-db-actions">
          {hasAudio && (
            <button
              type="button"
              className="ss-text-link cursor-pointer"
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
              className="ss-btn-filter-clear cursor-pointer"
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
