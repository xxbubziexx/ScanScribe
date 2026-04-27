import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { eventsApi } from '../../lib/events'
import { logsApi } from '../../lib/logs'
import { errorMessage } from '../../types/api'
import { useToast } from '../../context/ToastContext'
import type { MonitorResponse, MonitorUpdate } from '../../types/events'

function parseTokens(raw: string): string[] {
  return raw
    .split(/[\n,]+/)
    .map((s) => s.trim())
    .filter((s) => s.length > 0)
}

function tokensToLines(ids: string[]): string {
  return ids.join('\n')
}

export function EventsMonitorsPage() {
  const queryClient = useQueryClient()
  const { addToast } = useToast()

  const [createName, setCreateName] = useState('')
  const [createTg, setCreateTg] = useState('')
  const [createLabels, setCreateLabels] = useState('EVT_TYPE')

  const [editingId, setEditingId] = useState<number | null>(null)
  const [editName, setEditName] = useState('')
  const [editTg, setEditTg] = useState('')
  const [editLabels, setEditLabels] = useState('')

  const monitorsQuery = useQuery({
    queryKey: ['events-monitors'],
    queryFn: () => eventsApi.monitors(),
    staleTime: 30_000,
  })

  const nerLabelsQuery = useQuery({
    queryKey: ['events-ner-labels'],
    queryFn: () => eventsApi.nerLabels(),
    staleTime: 300_000,
  })

  const todayTalkgroupsQuery = useQuery({
    queryKey: ['logs-talkgroups-today'],
    queryFn: () => logsApi.talkgroups({ today: true }),
    staleTime: 60_000,
  })

  const nerOptions = useMemo(() => nerLabelsQuery.data?.labels ?? [], [nerLabelsQuery.data?.labels])

  const invalidate = () => void queryClient.invalidateQueries({ queryKey: ['events-monitors'] })

  const createMutation = useMutation({
    mutationFn: () =>
      eventsApi.createMonitor({
        name: createName.trim(),
        talkgroup_ids: parseTokens(createTg),
        start_event_labels: parseTokens(createLabels).length ? parseTokens(createLabels) : ['EVT_TYPE'],
      }),
    onSuccess: () => {
      addToast('Monitor created', 'success')
      setCreateName('')
      setCreateTg('')
      setCreateLabels('EVT_TYPE')
      invalidate()
    },
    onError: (e: unknown) => addToast(errorMessage(e, 'Failed to create monitor'), 'error'),
  })

  const updateMutation = useMutation({
    mutationFn: (args: { id: number; body: MonitorUpdate }) => eventsApi.updateMonitor(args.id, args.body),
    onSuccess: () => {
      addToast('Monitor updated', 'success')
      setEditingId(null)
      invalidate()
    },
    onError: (e: unknown) => addToast(errorMessage(e, 'Failed to update monitor'), 'error'),
  })

  const deleteMutation = useMutation({
    mutationFn: (id: number) => eventsApi.deleteMonitor(id),
    onSuccess: () => {
      addToast('Monitor deleted', 'success')
      invalidate()
      void queryClient.invalidateQueries({ queryKey: ['events-list'] })
    },
    onError: (e: unknown) => addToast(errorMessage(e, 'Failed to delete monitor'), 'error'),
  })

  const beginEdit = (m: MonitorResponse) => {
    setEditingId(m.id)
    setEditName(m.name)
    setEditTg(tokensToLines(m.talkgroup_ids))
    setEditLabels(tokensToLines(m.start_event_labels))
  }

  const cancelEdit = () => setEditingId(null)

  const copyTodayTalkgroup = async (text: string) => {
    try {
      await navigator.clipboard.writeText(text)
      addToast('Talkgroup copied', 'success')
    } catch {
      addToast('Could not copy talkgroup', 'error')
    }
  }

  const saveEdit = (id: number) => {
    updateMutation.mutate({
      id,
      body: {
        name: editName.trim(),
        talkgroup_ids: parseTokens(editTg),
        start_event_labels: parseTokens(editLabels).length ? parseTokens(editLabels) : ['EVT_TYPE'],
      },
    })
  }

  const toggleEnabled = (m: MonitorResponse) => {
    updateMutation.mutate({ id: m.id, body: { enabled: !m.enabled } })
  }

  const monitors = monitorsQuery.data ?? []

  return (
    <div className="ss-events-page">
      <div className="ss-events-topbar">
        <h1 className="ss-events-title">Monitor configuration</h1>
      </div>
      <p className="ss-events-sub">
        Departments map to monitors: talkgroups route traffic into the worker; start labels drive NER “start incident”
        extraction. Changes apply to new processing; existing events are unchanged unless you edit them elsewhere.
      </p>

      <section className="ss-events-monitor-create" aria-labelledby="monitor-create-heading">
        <h2 id="monitor-create-heading" className="ss-events-section-title">
          Add monitor
        </h2>
        <div className="ss-events-monitor-create-layout">
          <div className="ss-events-monitor-form-col">
            <div className="ss-events-monitor-form grid w-full max-w-full gap-3 md:grid-cols-[minmax(0,1fr)_auto] md:items-end">
              <div className="grid gap-2 md:col-span-2 md:grid-cols-1">
                <label className="block text-[11px] uppercase tracking-wide text-gray-500" htmlFor="new-monitor-name">
                  Name
                </label>
                <input
                  id="new-monitor-name"
                  className="ss-input"
                  value={createName}
                  onChange={(e) => setCreateName(e.target.value)}
                  placeholder="e.g. Fire dispatch"
                  autoComplete="off"
                />
              </div>
              <div className="grid gap-2 md:col-span-2">
                <label className="block text-[11px] uppercase tracking-wide text-gray-500" htmlFor="new-monitor-tg">
                  Talkgroup IDs (comma or newline)
                </label>
                <textarea
                  id="new-monitor-tg"
                  className="ss-input min-h-[5rem] resize-y font-mono text-xs"
                  value={createTg}
                  onChange={(e) => setCreateTg(e.target.value)}
                  placeholder="TG1&#10;TG2"
                />
              </div>
              <div className="grid gap-2 md:col-span-2">
                <label className="block text-[11px] uppercase tracking-wide text-gray-500" htmlFor="new-monitor-labels">
                  Start event labels (NER)
                </label>
                <textarea
                  id="new-monitor-labels"
                  className="ss-input min-h-[4rem] resize-y font-mono text-xs"
                  value={createLabels}
                  onChange={(e) => setCreateLabels(e.target.value)}
                  placeholder="EVT_TYPE"
                />
                {nerOptions.length > 0 ? (
                  <p className="text-[11px] text-gray-600">
                    Known label names include {nerOptions.slice(0, 16).join(', ')}
                    {nerOptions.length > 16 ? ' …' : ''}.
                  </p>
                ) : null}
              </div>
              <button
                type="button"
                className="ss-btn-ghost md:w-auto"
                disabled={createMutation.isPending || !createName.trim()}
                onClick={() => createMutation.mutate()}
              >
                Create monitor
              </button>
            </div>
          </div>

          <aside className="ss-events-monitor-today-tg" aria-label="Today's logged talkgroups">
            <div className="ss-events-monitor-today-tg-head">
              <p className="text-[11px] font-semibold uppercase tracking-wide text-indigo-200/90">
                Today&apos;s logged talkgroups
              </p>
              <p className="mt-0.5 font-mono text-[10px] text-gray-500">
                {new Date().toLocaleDateString(undefined, {
                  weekday: 'short',
                  month: 'short',
                  day: 'numeric',
                  year: 'numeric',
                })}
              </p>
            </div>
            <div className="ss-events-monitor-today-tg-scroll">
              {todayTalkgroupsQuery.isPending ? (
                <p className="text-xs text-gray-500">Loading…</p>
              ) : todayTalkgroupsQuery.isError ? (
                <p className="text-xs text-amber-200/90">{errorMessage(todayTalkgroupsQuery.error, 'Could not load')}</p>
              ) : (todayTalkgroupsQuery.data?.talkgroups ?? []).length === 0 ? (
                <p className="text-xs text-gray-500">None logged yet today.</p>
              ) : (
                <ul className="ss-events-monitor-today-tg-list">
                  {(todayTalkgroupsQuery.data?.talkgroups ?? []).map((tg) => (
                    <li key={tg} className="ss-events-monitor-today-tg-row">
                      <span className="ss-events-monitor-today-tg-text">{tg}</span>
                      <button
                        type="button"
                        className="ss-events-monitor-today-tg-copy"
                        onClick={() => void copyTodayTalkgroup(tg)}
                      >
                        Copy
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </aside>
        </div>
      </section>

      <section aria-label="Monitor list">
        <h2 className="ss-events-section-title">Monitors</h2>
        {monitorsQuery.isError && (
          <p className="ss-form-error">{errorMessage(monitorsQuery.error, 'Failed to load monitors')}</p>
        )}
        {!monitorsQuery.isError && monitors.length === 0 && !monitorsQuery.isPending ? (
          <p className="ss-empty not-italic">No monitors yet. Create one above.</p>
        ) : (
          <ul className="ss-events-monitor-board">
            {monitors.map((m) => (
              <li key={m.id} className="ss-events-monitor-card">
                {editingId === m.id ? (
                  <div className="grid gap-3">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <span className="font-mono text-[11px] text-gray-500">id {m.id}</span>
                      <div className="flex gap-2">
                        <button type="button" className="ss-btn-ghost text-xs" onClick={cancelEdit}>
                          Cancel
                        </button>
                        <button
                          type="button"
                          className="ss-btn-ghost text-xs"
                          disabled={updateMutation.isPending || !editName.trim()}
                          onClick={() => saveEdit(m.id)}
                        >
                          Save
                        </button>
                      </div>
                    </div>
                    <div className="grid gap-2">
                      <label className="text-[11px] uppercase tracking-wide text-gray-500">Name</label>
                      <input
                        className="ss-input"
                        value={editName}
                        onChange={(e) => setEditName(e.target.value)}
                      />
                    </div>
                    <div className="grid gap-2">
                      <label className="text-[11px] uppercase tracking-wide text-gray-500">
                        Talkgroup IDs (comma or newline)
                      </label>
                      <textarea
                        className="ss-input min-h-[5rem] resize-y font-mono text-xs"
                        value={editTg}
                        onChange={(e) => setEditTg(e.target.value)}
                      />
                    </div>
                    <div className="grid gap-2">
                      <label className="text-[11px] uppercase tracking-wide text-gray-500">Start event labels</label>
                      <textarea
                        className="ss-input min-h-[4rem] resize-y font-mono text-xs"
                        value={editLabels}
                        onChange={(e) => setEditLabels(e.target.value)}
                      />
                    </div>
                  </div>
                ) : (
                  <>
                    <div className="ss-events-monitor-head">
                      <div className="min-w-0">
                        <h3 className="truncate text-sm font-semibold text-gray-100">{m.name}</h3>
                        <p className="font-mono text-[11px] text-gray-500">id {m.id}</p>
                      </div>
                      <div className="flex flex-wrap items-center gap-1.5">
                        <label className="flex cursor-pointer items-center gap-1.5 text-[11px] text-gray-400">
                          <input
                            type="checkbox"
                            className="rounded border-white/20 bg-black/40"
                            checked={m.enabled}
                            disabled={updateMutation.isPending}
                            onChange={() => toggleEnabled(m)}
                          />
                          Enabled
                        </label>
                        <button type="button" className="ss-btn-ghost text-[11px]" onClick={() => beginEdit(m)}>
                          Edit
                        </button>
                        <button
                          type="button"
                          className="ss-btn-danger-soft text-[11px]"
                          disabled={deleteMutation.isPending}
                          onClick={() => {
                            if (
                              !window.confirm(
                                `Delete monitor “${m.name}”? This removes all events and transcript links for this monitor.`,
                              )
                            )
                              return
                            deleteMutation.mutate(m.id)
                          }}
                        >
                          Delete
                        </button>
                      </div>
                    </div>
                    <MonitorSummary m={m} />
                  </>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  )
}

function MonitorSummary({ m }: { m: MonitorResponse }) {
  return (
    <div className="ss-events-monitor-meta">
      <div className="min-w-0 flex-1">
        <p className="ss-events-monitor-meta-label">Talkgroups</p>
        <div className="flex flex-wrap gap-0.5">
          {m.talkgroup_ids.length === 0 ? (
            <span className="text-xs text-gray-500">None</span>
          ) : (
            m.talkgroup_ids.map((tg) => (
              <span key={tg} className="ss-events-chip-tg">
                {tg}
              </span>
            ))
          )}
        </div>
      </div>
      <div className="min-w-0 flex-1">
        <p className="ss-events-monitor-meta-label">Start labels</p>
        <div className="flex flex-wrap gap-0.5">
          {m.start_event_labels.map((lab) => (
            <span key={lab} className="ss-events-low-badge">
              {lab}
            </span>
          ))}
        </div>
      </div>
    </div>
  )
}
