import type { WatcherStatus } from '@/types/watcher'
import { OdometerValue } from '@/components/ui/OdometerValue'

const CARDS = [
  { key: 'ingest_count', label: '📥 Ingest' },
  { key: 'queue_count', label: '📋 Queue' },
  { key: 'files_processed', label: '✅ Processed' },
  { key: 'files_rejected', label: '❌ Rejected' },
  { key: 'engine_device', label: '⚡ Engine' },
] as const

interface StatsGridProps {
  status: WatcherStatus | null
  model: string
}

export function StatsGrid({ status, model }: StatsGridProps) {
  const values: Record<string, string | number> = {
    ingest_count: status?.ingest_count ?? '—',
    queue_count: status?.queue_count ?? '—',
    files_processed: status?.files_processed ?? '—',
    files_rejected: status?.files_rejected ?? '—',
    engine_device: status?.engine_device ?? '—',
  }

  return (
    <div className="ss-stat-grid">
      {CARDS.map(({ key, label }) => (
        <div key={key} className="ss-stat-card">
          <p className="ss-stat-label">{label}</p>
          <p className="ss-stat-value">
            {typeof values[key] === 'number' ? (
              <OdometerValue value={values[key] as number} />
            ) : (
              values[key]
            )}
          </p>
        </div>
      ))}
      <div className="ss-stat-card">
        <p className="ss-stat-label">🎯 Model</p>
        <p className="ss-stat-value-text" title={model}>
          {model || '—'}
        </p>
      </div>
    </div>
  )
}
