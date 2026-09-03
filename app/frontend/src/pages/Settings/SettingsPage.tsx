import './configureMonaco'
import { useCallback, useEffect, useState } from 'react'
import Editor from '@monaco-editor/react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useAuth } from '@/context/AuthContext'
import { useToast } from '@/context/ToastContext'
import { maintenanceApi } from '@/lib/maintenance'
import {
  downloadAudioZip,
  settingsApi,
  type AudioStorageStats,
} from '@/lib/settings'
import { errorMessage } from '@/types/api'

function formatStorageSize(stats: AudioStorageStats): string {
  if (stats.total_size_gb >= 1) return `${stats.total_size_gb} GB`
  return `${stats.total_size_mb} MB`
}

export function SettingsPage() {
  const { user } = useAuth()
  const { addToast } = useToast()
  const queryClient = useQueryClient()
  const isAdmin = user?.is_admin === true

  const [yaml, setYaml] = useState<string>('')
  const [needsRestart, setNeedsRestart] = useState(false)
  const [statusBanner, setStatusBanner] = useState<{
    message: string
    variant: 'success' | 'error' | 'warning'
  } | null>(null)

  const [storageInline, setStorageInline] = useState<{ text: string; tone: 'ok' | 'err' } | null>(
    null,
  )
  const [retentionFeedback, setRetentionFeedback] = useState<{
    text: string
    error: boolean
  } | null>(null)
  const [retentionDaysInput, setRetentionDaysInput] = useState('')
  const [zipLoading, setZipLoading] = useState(false)

  const configQuery = useQuery({
    queryKey: ['settings-config'],
    queryFn: () => settingsApi.getConfig(),
    staleTime: 60_000,
  })

  useEffect(() => {
    if (configQuery.data?.content != null) {
      setYaml(configQuery.data.content)
    }
  }, [configQuery.data?.content])

  useEffect(() => {
    if (!statusBanner) return
    const t = window.setTimeout(() => setStatusBanner(null), 5000)
    return () => window.clearTimeout(t)
  }, [statusBanner])

  useEffect(() => {
    if (!storageInline) return
    const t = window.setTimeout(() => setStorageInline(null), 5000)
    return () => window.clearTimeout(t)
  }, [storageInline])

  useEffect(() => {
    if (!retentionFeedback) return
    const t = window.setTimeout(() => setRetentionFeedback(null), 8000)
    return () => window.clearTimeout(t)
  }, [retentionFeedback])

  const retentionConfigQuery = useQuery({
    queryKey: ['maintenance-retention-config'],
    queryFn: () => maintenanceApi.retentionConfig(),
    staleTime: 60_000,
  })

  const storageQuery = useQuery({
    queryKey: ['settings-audio-storage-stats'],
    queryFn: () => settingsApi.audioStorageStats(),
    staleTime: 30_000,
  })

  const saveMutation = useMutation({
    mutationFn: () => settingsApi.saveConfig(yaml),
    onSuccess: (r) => {
      setStatusBanner({ message: r.message, variant: 'success' })
      setNeedsRestart(true)
      void queryClient.invalidateQueries({ queryKey: ['settings-config'] })
      addToast('Configuration saved', 'success')
    },
    onError: (e: unknown) => {
      const msg = errorMessage(e, 'Failed to save config')
      setStatusBanner({ message: msg, variant: 'error' })
      addToast(msg, 'error')
    },
  })

  const restartMutation = useMutation({
    mutationFn: () => settingsApi.restart(),
    onSuccess: () => {
      setStatusBanner({ message: 'Application is restarting…', variant: 'warning' })
      addToast('Restart signal sent', 'warning')
      window.setTimeout(() => window.location.reload(), 3000)
    },
    onError: (e: unknown) => {
      const msg = errorMessage(e, 'Restart failed')
      setStatusBanner({ message: msg, variant: 'error' })
      addToast(msg, 'error')
    },
  })

  const purgeMutation = useMutation({
    mutationFn: () => settingsApi.purgeAudio(),
    onSuccess: (r) => {
      const errPart = r.errors.length ? ` (${r.errors.length} errors)` : ''
      setStorageInline({
        text: `Purged ${r.deleted_files} files (${r.deleted_size_mb} MB)${errPart}`,
        tone: 'ok',
      })
      addToast('Audio storage purged', 'success')
      void storageQuery.refetch()
    },
    onError: (e: unknown) => {
      const msg = errorMessage(e, 'Purge failed')
      setStorageInline({ text: msg, tone: 'err' })
      addToast(msg, 'error')
    },
  })

  const retentionPurgeMutation = useMutation({
    mutationFn: (days: number) => maintenanceApi.purgeOldData(days),
    onSuccess: (r) => {
      setRetentionFeedback({
        text: `Removed ${r.deleted_count} entries and ${r.audio_files_deleted} audio files (older than ${r.cutoff_date ?? 'cutoff'}).`,
        error: false,
      })
      addToast('Retention cleanup finished', 'success')
      void storageQuery.refetch()
      void queryClient.invalidateQueries({ queryKey: ['database-logs'] })
      void queryClient.invalidateQueries({ queryKey: ['dataset-logs'] })
    },
    onError: (e: unknown) =>
      setRetentionFeedback({ text: errorMessage(e, 'Cleanup failed'), error: true }),
  })

  const reloadFromDisk = useCallback(async () => {
    if (!window.confirm('Reload config.yml from disk? Unsaved editor changes will be lost.')) return
    try {
      const fresh = await settingsApi.getConfig()
      setYaml(fresh.content)
      setNeedsRestart(false)
      setStatusBanner({ message: 'Config reloaded from disk', variant: 'success' })
    } catch (e) {
      setStatusBanner({
        message: errorMessage(e, 'Failed to reload config'),
        variant: 'error',
      })
    }
  }, [])

  const downloadBackup = useCallback(() => {
    const blob = new Blob([yaml], { type: 'text/yaml' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `config-backup-${new Date().toISOString().split('T')[0]}.yml`
    a.click()
    URL.revokeObjectURL(url)
    addToast('Config downloaded', 'success')
  }, [yaml, addToast])

  const onSave = () => {
    saveMutation.mutate()
  }

  const onRestart = () => {
    if (
      !window.confirm(
        'Restart ScanScribe to apply configuration changes?\n\nThe application will be unavailable for a few seconds.',
      )
    ) {
      return
    }
    restartMutation.mutate()
  }

  const onDownloadZip = async () => {
    setZipLoading(true)
    try {
      await downloadAudioZip()
      setStorageInline({ text: 'ZIP download started', tone: 'ok' })
    } catch (e) {
      setStorageInline({ text: errorMessage(e, 'Download failed'), tone: 'err' })
    } finally {
      setZipLoading(false)
    }
  }

  const onPurgeAudio = () => {
    if (
      !window.confirm(
        'WARNING: This will permanently delete ALL saved audio files.\n\nDatabase entries will remain but audio paths will be set to "file not saved".\n\nContinue?',
      )
    )
      return
    if (!window.confirm('Are you absolutely sure? This cannot be undone.')) return
    purgeMutation.mutate()
  }

  const onRetentionCleanup = () => {
    const days = Number.parseInt(retentionDaysInput, 10)
    if (Number.isNaN(days) || days < 0) {
      setRetentionFeedback({
        text: 'Enter a valid number of days (0 is not allowed for cleanup).',
        error: true,
      })
      return
    }
    if (days === 0) {
      setRetentionFeedback({
        text: 'Enter a positive number of days to purge by age.',
        error: true,
      })
      return
    }
    if (
      !window.confirm(
        `Delete all database entries and their audio files older than ${days} days? This cannot be undone.`,
      )
    )
      return
    retentionPurgeMutation.mutate(days)
  }

  const stats = storageQuery.data
  const retentionHint = retentionConfigQuery.data

  const bannerClass =
    statusBanner?.variant === 'success'
      ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-300'
      : statusBanner?.variant === 'error'
        ? 'border-red-500/30 bg-red-500/10 text-red-300'
        : 'border-amber-500/30 bg-amber-500/10 text-amber-200'

  return (
    <div className="ss-settings-page flex w-full flex-col gap-4">
      <section className="ss-settings-panel flex flex-col rounded-xl border border-white/10 bg-white/[0.02] p-4">
      <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="ss-db-title mb-0">Configuration editor</h1>
          <p className="mt-1 text-sm text-gray-500">Editing: config.yml</p>
        </div>
        <div className="flex flex-wrap gap-2">
          {needsRestart && (
            <button
              type="button"
              className="ss-btn-danger-soft"
              disabled={restartMutation.isPending}
              onClick={onRestart}
            >
              Restart to apply
            </button>
          )}
          <button
            type="button"
            className="ss-btn-primary"
            disabled={saveMutation.isPending || configQuery.isLoading}
            onClick={onSave}
          >
            {saveMutation.isPending ? 'Saving…' : 'Save config'}
          </button>
        </div>
      </div>

      {statusBanner && (
        <div
          className={`mb-4 rounded-lg border px-3 py-2 text-sm ${bannerClass}`}
          role="status"
        >
          {statusBanner.message}
        </div>
      )}

      {configQuery.isError && (
        <p className="ss-form-error mb-4" role="alert">
          {errorMessage(configQuery.error, 'Failed to load config.yml')}
        </p>
      )}

      <div className="ss-settings-editor-wrap min-h-[320px] overflow-hidden rounded-lg border border-white/10">
        {configQuery.isLoading ? (
          <p className="p-4 text-sm text-gray-500">Loading editor…</p>
        ) : (
          <Editor
            height="min(56vh, 520px)"
            language="yaml"
            theme="vs-dark"
            value={yaml}
            onChange={(v) => setYaml(v ?? '')}
            options={{
              fontSize: 14,
              minimap: { enabled: false },
              scrollBeyondLastLine: false,
              wordWrap: 'on',
              tabSize: 2,
              insertSpaces: true,
              automaticLayout: true,
            }}
          />
        )}
      </div>

      <div className="mt-4 rounded-lg border border-white/5 bg-white/[0.02] px-4 py-3">
        <div className="flex flex-wrap items-center justify-between gap-3 text-xs text-gray-500">
          <p>
            Use 2-space indentation · Changes apply after restart ·{' '}
            <kbd className="rounded border border-white/10 bg-black/30 px-1">Ctrl</kbd>+
            <kbd className="rounded border border-white/10 bg-black/30 px-1">F</kbd> to search
          </p>
          <div className="flex flex-wrap gap-2">
            <button type="button" className="ss-ghost-sm" onClick={downloadBackup}>
              Download backup
            </button>
            <button
              type="button"
              className="ss-ghost-sm"
              onClick={() => void reloadFromDisk()}
            >
              Reload from disk
            </button>
          </div>
        </div>
      </div>
      </section>

      <section className="ss-settings-panel rounded-xl border border-white/10 bg-white/[0.02] p-4">
        <h2 className="ss-page-h2 mb-4">Audio storage management</h2>
        <div className="mb-4 grid grid-cols-[repeat(auto-fit,minmax(180px,1fr))] gap-3">
          <div className="rounded-lg border border-white/10 bg-black/20 p-3">
            <div className="text-lg font-semibold tabular-nums text-gray-200">
              {storageQuery.isLoading
                ? '…'
                : storageQuery.isError
                  ? '—'
                  : (stats?.total_files ?? 0).toLocaleString()}
            </div>
            <div className="text-xs text-gray-500">Total files</div>
          </div>
          <div className="rounded-lg border border-white/10 bg-black/20 p-3">
            <div className="text-lg font-semibold tabular-nums text-gray-200">
              {storageQuery.isLoading
                ? '…'
                : storageQuery.isError
                  ? '—'
                  : stats
                    ? formatStorageSize(stats)
                    : '—'}
            </div>
            <div className="text-xs text-gray-500">Total size</div>
          </div>
          <div className="min-w-0 rounded-lg border border-white/10 bg-black/20 p-3">
            <div
              className="truncate font-mono text-sm text-gray-300"
              title={stats?.directory}
            >
              {storageQuery.isLoading
                ? '…'
                : storageQuery.isError
                  ? '—'
                  : stats?.directory ?? '—'}
            </div>
            <div className="text-xs text-gray-500">Directory</div>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-3">
          <button
            type="button"
            className="ss-btn-filter-clear"
            onClick={() => void storageQuery.refetch()}
          >
            Refresh stats
          </button>
          <button
            type="button"
            className="ss-btn-primary"
            disabled={zipLoading}
            onClick={() => void onDownloadZip()}
          >
            {zipLoading ? 'Creating ZIP…' : 'Download all as ZIP'}
          </button>
          <button
            type="button"
            className="ss-btn-danger-soft"
            disabled={!isAdmin || purgeMutation.isPending}
            title={!isAdmin ? 'Admin only' : undefined}
            onClick={onPurgeAudio}
          >
            {purgeMutation.isPending ? 'Purging…' : 'Purge saved audio'}
          </button>
          {storageInline && (
            <span
              className={
                storageInline.tone === 'ok' ? 'text-sm text-emerald-400' : 'text-sm text-red-400'
              }
            >
              {storageInline.text}
            </span>
          )}
        </div>
      </section>

      <section className="ss-settings-panel rounded-xl border border-white/10 bg-white/[0.02] p-4">
        <h2 className="ss-page-h2 mb-2">Data retention cleanup</h2>
        <p className="mb-4 text-sm text-gray-500">
          Remove database entries and their audio files older than a given number of days. Does not
          run automatically; use this to clean up by your retention policy.
        </p>
        <div className="flex flex-wrap items-end gap-3">
          <div>
            <label className="ss-form-label" htmlFor="retention-days">
              Delete data older than (days)
            </label>
            <input
              id="retention-days"
              type="number"
              min={1}
              step={1}
              className="ss-input w-24"
              placeholder={
                retentionHint != null ? String(retentionHint.retention_days) : '30'
              }
              value={retentionDaysInput}
              onChange={(e) => setRetentionDaysInput(e.target.value)}
            />
          </div>
          <button
            type="button"
            className="ss-btn-primary"
            disabled={retentionPurgeMutation.isPending}
            onClick={onRetentionCleanup}
          >
            {retentionPurgeMutation.isPending ? 'Running…' : 'Run cleanup'}
          </button>
        </div>
        <p className="mt-2 text-xs text-gray-600">
          Config:{' '}
          {retentionConfigQuery.isError
            ? 'could not load'
            : retentionHint == null
              ? '…'
              : retentionHint.retention_days === 0
                ? 'keep forever (0)'
                : `${retentionHint.retention_days} days`}
          {retentionHint != null && retentionHint.cleanup_hour != null
            ? ` · cleanup_hour: ${retentionHint.cleanup_hour}:00`
            : ''}
        </p>
        {retentionFeedback && (
          <p
            className={`mt-2 text-sm ${retentionFeedback.error ? 'text-red-400' : 'text-emerald-400'}`}
            role={retentionFeedback.error ? 'alert' : 'status'}
          >
            {retentionFeedback.text}
          </p>
        )}
      </section>
    </div>
  )
}
