import type { EventTranscript } from '@/types/events'
import type { DetailTab, PipelineEvent } from '../utils/incidentFormatters'
import {
  formatTimeLong,
  formatTimeOnly,
  nerEntityChips,
  splitBadgeEntries,
  typeDisplayFor,
} from '../utils/incidentFormatters'
import { EditableTranscript } from './EditableTranscript'

export function EventDetailContent({
  selected,
  activeTab,
  setActiveTab,
  closeMutation,
  deleteMutation,
  summarizeMutation,
  detailQuery,
  spanLinks,
  canAdmin = true,
}: {
  selected: PipelineEvent
  activeTab: DetailTab
  setActiveTab: (tab: DetailTab) => void
  closeMutation: { mutate: (id: string) => void; isPending: boolean }
  deleteMutation: { mutate: (id: string) => void; isPending: boolean }
  summarizeMutation: { mutate: (id: string) => void; isPending: boolean }
  detailQuery: { data?: unknown; isFetching: boolean }
  spanLinks: EventTranscript[]
  canAdmin?: boolean
}) {
  return (
    <>
      <div className="ss-events-tabs flex-wrap gap-2">
        <div className="ss-events-tabs-left" role="tablist">
          {(
            [
              { id: 'event-thread' as const, label: 'Event Thread' },
              { id: 'transcription' as const, label: 'Transcription' },
              { id: 'raw' as const, label: 'Raw' },
            ] as const
          ).map((tab) => (
            <button
              key={tab.id}
              type="button"
              role="tab"
              aria-selected={activeTab === tab.id}
              className={`min-h-[38px] px-3 py-1.5 cursor-pointer rounded-lg text-xs font-medium transition ${
                activeTab === tab.id ? 'ss-events-tab ss-events-tab--active' : 'ss-events-tab'
              }`}
              onClick={() => setActiveTab(tab.id)}
            >
              {tab.label}
            </button>
          ))}
        </div>
        {canAdmin && (
          <div className="ss-events-tabs-actions">
            <button
              type="button"
              className="ss-btn-ghost min-h-[38px] px-3 cursor-pointer"
              disabled={selected.status === 'closed' || closeMutation.isPending}
              onClick={() => closeMutation.mutate(selected.eventId)}
            >
              Close
            </button>
            <button
              type="button"
              className="ss-btn-danger-soft min-h-[38px] px-3 cursor-pointer"
              disabled={deleteMutation.isPending}
              onClick={() => {
                if (!window.confirm(`Delete ${selected.eventId}?`)) return
                deleteMutation.mutate(selected.eventId)
              }}
            >
              Delete
            </button>
          </div>
        )}
      </div>

      {activeTab === 'event-thread' ? (
        <div className="ss-events-thread-wrap">
          <h3 className="ss-events-section-title">HEADER</h3>
          <div className="grid grid-cols-1 sm:grid-cols-[140px_1fr] gap-y-3 sm:gap-y-4 text-[13px] md:text-sm mb-8 mt-2">
            <div className="font-semibold text-gray-200">Created</div>
            <div className="text-gray-300 font-mono">{formatTimeOnly(selected.createdAt)}</div>

            {selected.closedAt && (
              <>
                <div className="font-semibold text-gray-200">Closed</div>
                <div className="text-gray-300 font-mono">{formatTimeOnly(selected.closedAt)}</div>
              </>
            )}

            <div className="font-semibold text-gray-200">Event ID</div>
            <div className="text-gray-300 font-mono break-all">{selected.eventId}</div>

            <div className="font-semibold text-gray-200">Type</div>
            <div className="flex">
              <span className="px-2 py-0.5 rounded text-xs font-bold bg-orange-500/20 text-orange-100 border border-orange-500/30">
                {typeDisplayFor(selected)}
              </span>
            </div>

            <div className="font-semibold text-gray-200">Monitor</div>
            <div className="text-gray-300">{selected.monitorName}</div>

            <div className="font-semibold text-gray-200">Status</div>
            <div className="flex items-center gap-2">
              <span
                className={`capitalize px-2 py-0.5 rounded text-xs font-semibold ${
                  selected.status.toLowerCase() === 'open'
                    ? 'bg-green-500/20 text-green-400 border border-green-500/30'
                    : 'bg-red-500/20 text-red-400 border border-red-500/30'
                }`}
              >
                {selected.status}
              </span>
              {selected.statusDetail ? (
                <span className="ss-events-low-badge !mt-0">{selected.statusDetail}</span>
              ) : null}
            </div>

            <div className="font-semibold text-gray-200">Location</div>
            <div className="flex flex-wrap gap-1.5">
              {selected.location ? (
                <span className="ss-events-kv-badge">{selected.location}</span>
              ) : (
                <span className="text-gray-500">—</span>
              )}
            </div>

            <div className="font-semibold text-gray-200">Units</div>
            <div className="flex flex-wrap gap-1.5">
              {splitBadgeEntries(selected.units).length > 0 ? (
                splitBadgeEntries(selected.units).map((unit) => (
                  <span key={unit} className="ss-events-kv-badge">
                    {unit}
                  </span>
                ))
              ) : (
                <span className="text-gray-500">—</span>
              )}
            </div>

            <div className="font-semibold text-gray-200">Talkgroups</div>
            <div className="flex flex-wrap gap-1.5">
              {splitBadgeEntries(selected.talkgroup).length > 0 ? (
                splitBadgeEntries(selected.talkgroup).map((tg) => (
                  <span key={tg} className="ss-events-kv-badge">
                    {tg}
                  </span>
                ))
              ) : (
                <span className="text-gray-500">—</span>
              )}
            </div>

            <div className="font-semibold text-gray-200">Spans</div>
            <div className="text-gray-300">{selected.spansAttached}</div>

            <div className="flex flex-wrap items-center justify-between col-span-1 sm:col-span-2 pt-2 border-t border-white/10 gap-2">
              <div className="font-semibold text-gray-200 flex items-center gap-2">
                <span>Summary</span>
              </div>
              {canAdmin && (
                <button
                  type="button"
                  onClick={() => summarizeMutation.mutate(selected.eventId)}
                  className="text-xs text-indigo-400 hover:text-indigo-300 transition flex items-center gap-1.5 bg-white/5 hover:bg-white/10 px-2.5 py-1.5 rounded border border-white/10 min-h-[36px] cursor-pointer"
                  disabled={summarizeMutation.isPending}
                  title="Generate or update the summary using the router LLM based on all attached transcripts"
                >
                  <span>🔄</span>{' '}
                  {summarizeMutation.isPending
                    ? 'Generating…'
                    : selected.summary
                      ? 'Regenerate'
                      : 'Generate Summary'}
                </button>
              )}
            </div>
            <div className="col-span-1 sm:col-span-2 text-gray-300 leading-relaxed max-w-3xl bg-black/20 p-2.5 rounded-lg border border-white/5 text-sm">
              {selected.summary ? (
                <p className="m-0">{selected.summary}</p>
              ) : (
                <span className="text-gray-500 italic">
                  No summary generated yet. Click Generate Summary to synthesize all attachments.
                </span>
              )}
            </div>
          </div>

          <h3 className="ss-events-section-title mt-6">SPAN LINKS</h3>
          <div className="ss-events-spans-list-wrap">
            {detailQuery.isFetching && !detailQuery.data ? (
              <p className="ss-empty not-italic">Loading span links…</p>
            ) : spanLinks.length === 0 ? (
              <p className="ss-events-placeholder">No span links attached.</p>
            ) : (
              <ul className="ss-events-spans-list">
                {spanLinks.map((span, idx) => (
                  <li
                    key={span.log_entry_id ?? `${selected?.eventId}-span-${idx + 1}`}
                    className="ss-events-span-item"
                  >
                    <div className="ss-events-span-item-head">
                      <p className="ss-events-k mb-0">Span #{idx + 1}</p>
                      <p className="text-sm text-gray-300">{formatTimeLong(span.timestamp)}</p>
                    </div>
                    <p className="ss-events-talkgroup-badge mt-1">{span.talkgroup || 'N/A'}</p>

                    <div className="ss-events-span-section mt-2">
                      <div className="ss-events-kv">
                        <p className="ss-events-k mb-0.5">NER extractions</p>
                        <div className="ss-events-kv-value ss-events-ner-list">
                          {nerEntityChips(span.entities).length === 0 ? (
                            <span className="text-xs text-gray-500">None</span>
                          ) : (
                            nerEntityChips(span.entities).map((entity) => (
                              <span key={entity} className="ss-events-ner-chip">
                                {entity}
                              </span>
                            ))
                          )}
                        </div>
                      </div>
                    </div>

                    <div className="ss-events-span-section ss-events-span-section--transcript mt-2">
                      <div className="ss-events-kv">
                        <p className="ss-events-k mb-0.5">Transcript</p>
                        {span.log_entry_id ? (
                          <EditableTranscript
                            logId={span.log_entry_id}
                            initialText={span.transcript || ''}
                            canEdit={canAdmin}
                          />
                        ) : (
                          <p className="ss-events-kv-value text-sm text-gray-300">
                            {span.transcript || '—'}
                          </p>
                        )}
                      </div>
                    </div>

                    <div className="ss-events-span-section ss-events-span-section--attach mt-2">
                      <div className="ss-events-kv">
                        <p className="ss-events-k mb-0.5">Attach reason</p>
                        <p className="ss-events-kv-value text-sm text-indigo-200/90">
                          {span.llm_reason ||
                            (span.is_trigger
                              ? 'Trigger span matched event header extraction'
                              : 'Linked context span')}
                        </p>
                      </div>
                    </div>

                    {span.has_playback && span.audio_path ? (
                      <div className="mt-2">
                        <p className="ss-events-k mb-0.5">Audio</p>
                        <audio
                          className="ss-events-span-audio"
                          controls
                          preload="none"
                          src={`/${span.audio_path}`}
                        >
                          Your browser does not support audio playback.
                        </audio>
                      </div>
                    ) : null}
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      ) : activeTab === 'transcription' ? (
        <div className="ss-events-txt-block">
          <p className="ss-events-hint">
            Trigger / header text stored on the event (first span is highlighted in API responses).
          </p>
          <p className="ss-events-body">{selected.originalTranscription || '—'}</p>
        </div>
      ) : (
        <pre className="ss-events-pre">{JSON.stringify(selected, null, 2)}</pre>
      )}
    </>
  )
}
