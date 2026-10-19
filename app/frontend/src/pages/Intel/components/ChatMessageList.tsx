import { useRef, useEffect, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import type { ChatMessage, ChatStreamMeta, ToolCallRecord } from '@/types/chat'
import { ThinkingAccordion } from './ThinkingAccordion'
import { ToolCallCard } from './ToolCallCard'

interface ChatMessageListProps {
  messages: ChatMessage[]
  streamingToken: string
  streamThought: string
  streamToolCalls: ToolCallRecord[]
  streamMeta: ChatStreamMeta | null
  isStreaming: boolean
  streamError: string | null
  showTools: boolean
  showThinking: boolean
  onSelectTx: (txId: number, incidentTxIds?: number[]) => void
  onPromptSuggestion: (prompt: string) => void
  onOpenAudioPanel?: () => void
  onScopeIncident?: (txIds: number[], title?: string) => void
}

const STARTER_PROMPTS = [
  'Summarize active radio traffic from the past 2 hours.',
  'What did unit 112 do today?',
  'What incidents did the fire department respond to yesterday?',
  'What happened around 1155 Walton Dr this morning?',
  'List all pursuit calls or vehicle collisions from today.',
]

function preprocessMarkdownCitations(content: string): string {
  // 0. Intercept any markdown links where anchor text is TX ID: [TX #492983](http://...) -> [TX #492983](tx:492983)
  let text = content.replace(/\[TX[-#\s]*(\d+)\]\([^)]*\)/gi, (_match, id) => {
    return `[TX #${id}](tx:${id})`
  })

  // 1. Bracketed citations like [TX-490899, TX-490900] or [TX #490899] or [TX-490899]
  text = text.replace(/\[TX[-#\s]*([0-9,\sTX#\-]+)\]/gi, (match, inner) => {
    const numbers = inner.match(/\d+/g)
    if (!numbers || numbers.length === 0) return match
    return numbers.map((n: string) => `[TX #${n}](tx:${n})`).join(' ')
  })

  // 2. Bare unbracketed citations like TX #490899 or TX-490899 not already inside a link or bracket
  text = text.replace(/(^|[^[/\w])TX[-#\s]+(\d+)(?![\])])/gi, (_match, prefix, id) => {
    return `${prefix}[TX #${id}](tx:${id})`
  })

  return text
}

function extractCitedIds(content: string, explicitIds?: number[] | null): number[] {
  const ids = new Set<number>()
  if (explicitIds) {
    for (const id of explicitIds) ids.add(id)
  }
  const matches = content.matchAll(/TX[-#\s]*(\d+)/gi)
  for (const m of matches) {
    const num = parseInt(m[1], 10)
    if (!isNaN(num)) ids.add(num)
  }
  return Array.from(ids)
}

function findIncidentScopeForTx(txId: number, content: string, messageCitedIds: number[]): number[] {
  // Check if content has scope:tx: directives containing this txId
  const scopeMatches = content.matchAll(/scope:tx:([0-9,]+)/gi)
  for (const match of scopeMatches) {
    const ids = match[1]
      .split(',')
      .map((s) => parseInt(s.trim(), 10))
      .filter((n) => !isNaN(n) && n > 0)
    if (ids.includes(txId)) {
      return ids
    }
  }
  // Otherwise, return all cited IDs in this incident response
  if (messageCitedIds.includes(txId) && messageCitedIds.length > 0) {
    return messageCitedIds
  }
  return [txId]
}

export function ChatMessageList({
  messages,
  streamingToken,
  streamThought,
  streamToolCalls,
  streamMeta,
  isStreaming,
  streamError,
  showTools,
  showThinking,
  onSelectTx,
  onPromptSuggestion,
  onOpenAudioPanel,
  onScopeIncident,
}: ChatMessageListProps) {
  const bottomRef = useRef<HTMLDivElement>(null)
  const [copiedMsgId, setCopiedMsgId] = useState<number | null>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView?.({ behavior: 'smooth' })
  }, [messages.length, streamingToken, streamThought, streamToolCalls.length, isStreaming])

  const handleCopyText = async (msgId: number, text: string) => {
    try {
      await navigator.clipboard.writeText(text)
      setCopiedMsgId(msgId)
      setTimeout(() => setCopiedMsgId(null), 2000)
    } catch {
      // Fallback
    }
  }

  const runningCall = streamToolCalls.find((c) => c.status === 'running')
  const liveStatus = runningCall
    ? `Running ${runningCall.tool.replace(/_/g, ' ')}...`
    : streamThought && !streamingToken
      ? 'Reasoning over transcripts...'
      : 'Assembling intelligence...'

  const renderMarkdown = (content: string, messageCitedIds: number[] = []) => {
    return (
      <div className="text-[13px] leading-relaxed text-gray-200 select-text font-normal space-y-2">
        <ReactMarkdown
          urlTransform={(url) => url}
          components={{
            a: ({ href, children }) => {
              // Check for Incident Scope action link: scope:tx:123,456 or scope:incident
              if (href?.startsWith('scope:')) {
                let scopeIds: number[] = []
                if (href.startsWith('scope:tx:')) {
                  const raw = href.slice(9)
                  scopeIds = raw
                    .split(/[,+]/)
                    .map((s) => parseInt(s.trim(), 10))
                    .filter((n) => !isNaN(n) && n > 0)
                } else {
                  const m = href.match(/\d+/g)
                  if (m) {
                    scopeIds = m.map((s) => parseInt(s, 10)).filter((n) => !isNaN(n) && n > 0)
                  }
                }

                const label = typeof children === 'string' ? children : 'Scope Incident Audio'
                return (
                  <button
                    type="button"
                    onClick={(e) => {
                      e.preventDefault()
                      e.stopPropagation()
                      if (onScopeIncident && scopeIds.length > 0) {
                        onScopeIncident(scopeIds, label)
                      } else if (onSelectTx && scopeIds[0]) {
                        onSelectTx(scopeIds[0], scopeIds)
                        if (onOpenAudioPanel) onOpenAudioPanel()
                      }
                    }}
                    className="inline-flex items-center gap-1.5 mx-1 my-1 px-3 py-1.5 rounded-lg text-xs font-semibold bg-gradient-to-r from-indigo-950 via-indigo-900 to-indigo-950 hover:from-indigo-900 hover:to-indigo-800 text-indigo-200 hover:text-white border border-indigo-500/70 hover:border-indigo-400 transition-all cursor-pointer select-none shadow-md group align-middle active:scale-[0.98]"
                    title={`Load ${scopeIds.length > 0 ? `${scopeIds.length} ` : ''}incident transmissions into the audio deck for chronological playback`}
                  >
                    <span className="text-amber-400 text-xs group-hover:scale-110 transition-transform">⚡</span>
                    <span className="font-semibold">{children}</span>
                    {scopeIds.length > 0 && (
                      <span className="px-1.5 py-0.5 rounded text-[10px] font-mono font-bold bg-indigo-800/90 text-indigo-200 border border-indigo-600/50">
                        {scopeIds.length} TX
                      </span>
                    )}
                    <span className="text-[10px] text-indigo-400 group-hover:text-indigo-200">▶</span>
                  </button>
                )
              }

              // Extract target ID from href (tx:12345) or from child text
              let targetId: number | null = null
              if (href?.startsWith('tx:')) {
                const parsed = parseInt(href.slice(3), 10)
                if (!isNaN(parsed)) targetId = parsed
              }
              if (targetId === null && typeof children === 'string') {
                const m = children.match(/TX[-#\s]*(\d+)/i)
                if (m) {
                  const parsed = parseInt(m[1], 10)
                  if (!isNaN(parsed)) targetId = parsed
                }
              }

              if (targetId !== null) {
                const finalId = targetId
                const incidentIds = findIncidentScopeForTx(finalId, content, messageCitedIds)
                return (
                  <button
                    type="button"
                    onClick={(e) => {
                      e.preventDefault()
                      e.stopPropagation()
                      onSelectTx(finalId, incidentIds)
                      if (onOpenAudioPanel) onOpenAudioPanel()
                    }}
                    className="inline-flex items-center gap-1 mx-0.5 my-0.5 px-2 py-0.5 rounded font-mono text-[11px] font-semibold bg-indigo-950/80 hover:bg-indigo-700 text-indigo-300 hover:text-white border border-indigo-700/60 hover:border-indigo-400 transition-all cursor-pointer select-none align-baseline shadow-xs"
                    title={`Listen to original radio transmission #${finalId} in audio panel`}
                  >
                    <span>TX #{finalId}</span>
                    <span className="text-[10px]">🔊</span>
                  </button>
                )
              }

              if (!href || href.startsWith('file:') || href.startsWith('javascript:')) {
                return (
                  <span
                    className="font-mono text-xs text-gray-300 bg-[#161925] px-1.5 py-0.5 rounded border border-[#262c3e]"
                    title={href || undefined}
                  >
                    {children}
                  </span>
                )
              }

              return (
                <a
                  href={href}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-indigo-400 hover:text-indigo-300 underline underline-offset-2"
                >
                  {children}
                </a>
              )
            },
            p: ({ children }) => <p className="mb-2.5 last:mb-0 leading-relaxed text-gray-200">{children}</p>,
            ul: ({ children }) => <ul className="list-disc pl-5 mb-3 space-y-1 text-gray-200">{children}</ul>,
            ol: ({ children }) => <ol className="list-decimal pl-5 mb-3 space-y-1 text-gray-200">{children}</ol>,
            li: ({ children }) => <li className="leading-relaxed">{children}</li>,
            strong: ({ children }) => <strong className="font-semibold text-white">{children}</strong>,
            h1: ({ children }) => (
              <h1 className="text-base font-bold text-white mb-2 mt-4 first:mt-0 tracking-tight">{children}</h1>
            ),
            h2: ({ children }) => (
              <h2 className="text-sm font-bold text-white mb-1.5 mt-3.5 first:mt-0 tracking-tight">{children}</h2>
            ),
            h3: ({ children }) => (
              <h3 className="text-xs font-semibold text-gray-200 mb-1 mt-2.5 first:mt-0">{children}</h3>
            ),
            blockquote: ({ children }) => (
              <blockquote className="border-l-2 border-indigo-500/80 bg-[#141724]/60 rounded-r pl-3.5 py-1.5 my-2.5 text-gray-300 italic text-xs">
                {children}
              </blockquote>
            ),
            code: ({ children }) => (
              <code className="px-1.5 py-0.5 bg-[#12141f] rounded font-mono text-[11px] text-indigo-300 border border-[#232738]">
                {children}
              </code>
            ),
          }}
        >
          {preprocessMarkdownCitations(content)}
        </ReactMarkdown>
      </div>
    )
  }

  return (
    <div className="flex-1 overflow-y-auto">
      <div className="max-w-3xl mx-auto w-full px-4 py-6 space-y-6">
        {/* Empty State / Welcome Screen */}
        {messages.length === 0 && !isStreaming && (
          <div className="flex flex-col items-center justify-center text-center py-10 max-w-xl mx-auto">
            <div className="w-12 h-12 rounded-2xl bg-gradient-to-br from-indigo-600 to-indigo-800 border border-indigo-400/30 flex items-center justify-center text-lg text-white mb-3 shadow-lg font-bold font-mono">
              SS
            </div>
            <h2 className="text-base font-semibold text-gray-100 mb-1">
              Scanner Intelligence Console
            </h2>
            <p className="text-xs text-gray-400 mb-6 max-w-md leading-relaxed">
              Ask natural language questions across indexed public safety radio traffic, unit callouts, and incident records. All citations link directly to verified radio audio.
            </p>

            <div className="w-full space-y-2 text-left">
              <span className="text-[10px] font-semibold text-gray-500 uppercase tracking-wider block">
                Suggested Intel Queries:
              </span>
              <div className="grid grid-cols-1 gap-2">
                {STARTER_PROMPTS.map((prompt, idx) => (
                  <button
                    key={idx}
                    type="button"
                    onClick={() => onPromptSuggestion(prompt)}
                    className="px-3.5 py-2.5 bg-[#141724] hover:bg-[#1a1e2f] border border-[#262c3f] hover:border-indigo-500/50 rounded-xl text-left text-xs text-gray-300 hover:text-white transition-all flex items-center justify-between cursor-pointer group shadow-xs"
                  >
                    <span>"{prompt}"</span>
                    <span className="text-gray-500 group-hover:text-indigo-400 text-xs transition-transform group-hover:translate-x-0.5">
                      →
                    </span>
                  </button>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* Message Stream (ChatGPT Document Rows) */}
        {messages.map((msg) => {
          const isUser = msg.role === 'user'
          const timeStr = msg.created_at
            ? new Date(msg.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
            : ''
          const citedIds = extractCitedIds(msg.content, msg.cited_log_ids)

          return (
            <div
              key={msg.id}
              className={`flex gap-3.5 items-start group transition-colors ${
                isUser ? 'pt-1' : 'pt-2 pb-3 border-b border-[#1c202e]/60 last:border-b-0'
              }`}
            >
              {/* Avatar Icon */}
              {isUser ? (
                <div className="w-7 h-7 rounded-full bg-[#1e2335] border border-[#2c334d] flex items-center justify-center text-[11px] font-semibold text-gray-300 shrink-0 select-none shadow-xs mt-0.5">
                  OP
                </div>
              ) : (
                <div className="w-7 h-7 rounded-full bg-gradient-to-br from-indigo-600 to-indigo-800 border border-indigo-400/40 flex items-center justify-center text-[10px] font-bold text-white shrink-0 select-none shadow-md mt-0.5">
                  SS
                </div>
              )}

              {/* Message Content Container */}
              <div className="flex-1 min-w-0">
                {/* Meta Header */}
                <div className="flex items-center justify-between mb-1 text-[11px] text-gray-400">
                  <div className="flex items-center gap-2">
                    <span className={`font-semibold ${isUser ? 'text-gray-300' : 'text-indigo-300'}`}>
                      {isUser ? 'Operator' : 'ScanScribe Intel'}
                    </span>
                    <span className="text-gray-500 font-mono text-[10px]">{timeStr}</span>
                  </div>

                  {/* Message Action Utilities */}
                  {!isUser && (
                    <div className="flex items-center gap-1.5 opacity-0 group-hover:opacity-100 transition-opacity">
                      <button
                        type="button"
                        onClick={() => handleCopyText(msg.id, msg.content)}
                        className="px-1.5 py-0.5 rounded text-[10px] text-gray-400 hover:text-gray-200 hover:bg-[#202538] transition-colors cursor-pointer"
                        title="Copy response to clipboard"
                      >
                        {copiedMsgId === msg.id ? 'Copied!' : 'Copy'}
                      </button>
                    </div>
                  )}
                </div>

                {/* Body */}
                {isUser ? (
                  <div className="text-sm text-gray-100 font-normal leading-relaxed whitespace-pre-wrap select-text py-0.5">
                    {msg.content}
                  </div>
                ) : (
                  <div className="space-y-2.5">
                    {showThinking && msg.thought && <ThinkingAccordion thought={msg.thought} />}
                    {showTools && msg.tool_calls && msg.tool_calls.length > 0 && (
                      <ToolCallCard calls={msg.tool_calls} />
                    )}
                    {renderMarkdown(msg.content, citedIds)}

                    {/* Cited Audio Quick Bar */}
                    {citedIds.length > 0 && (
                      <div className="pt-2 flex items-center gap-2 flex-wrap">
                        {onScopeIncident && (
                          <button
                            type="button"
                            onClick={() => onScopeIncident(citedIds, 'Incident Audio')}
                            className="inline-flex items-center gap-1.5 px-3 py-1 rounded-md text-xs font-semibold bg-indigo-950/90 hover:bg-indigo-900 text-indigo-200 hover:text-white border border-indigo-700/70 hover:border-indigo-400 transition-all cursor-pointer shadow-xs active:scale-[0.98]"
                            title="Load all transmissions cited in this incident response into the audio deck for chronological playback"
                          >
                            <span className="text-amber-400 text-xs">⚡</span>
                            <span>Scope Incident Audio ({citedIds.length})</span>
                            <span className="text-[10px] text-indigo-400">▶</span>
                          </button>
                        )}
                        <button
                          type="button"
                          onClick={() => {
                            if (citedIds[0]) onSelectTx(citedIds[0], citedIds)
                            if (onOpenAudioPanel) onOpenAudioPanel()
                          }}
                          className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-[11px] font-medium bg-[#161a29] hover:bg-[#20263b] text-gray-400 hover:text-gray-200 border border-[#2b324a] hover:border-gray-500 transition-all cursor-pointer shadow-xs"
                          title="Open audio deck scoped to this incident"
                        >
                          <span>📻</span>
                          <span>Deck ({citedIds.length})</span>
                        </button>
                      </div>
                    )}
                  </div>
                )}
              </div>
            </div>
          )
        })}

        {/* Live Streaming Response Block */}
        {isStreaming && (
          <div className="flex gap-3.5 items-start pt-2">
            <div className="w-7 h-7 rounded-full bg-gradient-to-br from-indigo-600 to-indigo-800 border border-indigo-400/40 flex items-center justify-center text-[10px] font-bold text-white shrink-0 select-none shadow-md mt-0.5">
              SS
            </div>

            <div className="flex-1 min-w-0 space-y-2">
              <div className="flex items-center gap-2 mb-1 text-[11px] text-gray-400">
                <span className="font-semibold text-indigo-300">ScanScribe Intel</span>
                <span className="animate-pulse text-indigo-400 font-medium">● {liveStatus}</span>
              </div>

              {/* Streaming Context Meta Header */}
              {streamMeta && (
                <div className="p-2 bg-[#141724] rounded-lg border border-[#232738] flex items-center justify-between text-[11px] text-gray-400 font-mono">
                  <span>
                    {streamMeta.agentic ? 'In scope' : 'Scanned'}:{' '}
                    <strong className="text-indigo-300">{streamMeta.transmissions_count}</strong> transmissions
                  </span>
                  <span>{streamMeta.time_desc}</span>
                </div>
              )}

              {showThinking && streamThought && <ThinkingAccordion thought={streamThought} isLive />}
              {showTools && <ToolCallCard calls={streamToolCalls} />}

              <div>
                {streamingToken ? (
                  renderMarkdown(streamingToken, extractCitedIds(streamingToken))
                ) : (
                  <div className="text-gray-500 italic text-xs animate-pulse">
                    {streamMeta?.agentic
                      ? 'Querying the radio intelligence database...'
                      : 'Reading transmissions and assembling intelligence...'}
                  </div>
                )}
              </div>
            </div>
          </div>
        )}

        {/* Stream Error Banner */}
        {streamError && (
          <div className="p-3 bg-red-950/60 border border-red-800/80 rounded-xl text-xs text-red-200 flex items-center justify-between shadow-md">
            <span>{streamError}</span>
          </div>
        )}

        <div ref={bottomRef} />
      </div>
    </div>
  )
}
