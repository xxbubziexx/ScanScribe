import { useRef, useEffect } from 'react'
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
  onSelectTx: (txId: number) => void
  onPromptSuggestion: (prompt: string) => void
}

const STARTER_PROMPTS = [
  'Summarize scanner activity over the selected time scope.',
  'What calls or incidents did the fire department respond to?',
  'List all traffic stops, pursuit calls, or vehicle collisions.',
  'Why was unit 112 responding code 3 down the highway?',
  'Were there any calls or activity near Walmart?',
]

function preprocessMarkdownCitations(content: string): string {
  // 1. Bracketed citations like [TX-490899, TX-490900] or [TX #490899] or [TX-490899]
  let text = content.replace(/\[TX[-#\s]*([0-9,\sTX#\-]+)\]/gi, (match, inner) => {
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
}: ChatMessageListProps) {
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages.length, streamingToken, streamThought, streamToolCalls.length, isStreaming])

  const runningCall = streamToolCalls.find((c) => c.status === 'running')
  const liveStatus = runningCall
    ? `Running ${runningCall.tool.replace(/_/g, ' ')}...`
    : streamThought && !streamingToken
      ? 'Thinking...'
      : 'Analyzing logs...'

  const renderMarkdown = (content: string) => {
    return (
      <div className="text-xs leading-relaxed text-gray-200 select-text">
        <ReactMarkdown
          components={{
            a: ({ href, children }) => {
              if (href?.startsWith('tx:')) {
                const txId = parseInt(href.slice(3), 10)
                return (
                  <button
                    type="button"
                    onClick={() => onSelectTx(txId)}
                    className="inline-flex items-center gap-1 mx-0.5 my-0.5 px-1.5 py-0.5 rounded font-mono text-[11px] font-semibold bg-indigo-950/90 hover:bg-indigo-800 text-indigo-300 border border-indigo-700/60 hover:border-indigo-400 transition-colors cursor-pointer select-none align-baseline shadow-xs"
                    title={`Listen to original radio transmission #${txId}`}
                  >
                    <span>{children}</span>
                    <span className="text-[10px]">🔊</span>
                  </button>
                )
              }
              return (
                <a
                  href={href}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-indigo-400 hover:underline"
                >
                  {children}
                </a>
              )
            },
            p: ({ children }) => <p className="mb-2 last:mb-0 leading-relaxed">{children}</p>,
            ul: ({ children }) => <ul className="list-disc pl-5 mb-2 space-y-1.5">{children}</ul>,
            ol: ({ children }) => <ol className="list-decimal pl-5 mb-2 space-y-1.5">{children}</ol>,
            li: ({ children }) => <li className="leading-relaxed">{children}</li>,
            strong: ({ children }) => <strong className="font-semibold text-white">{children}</strong>,
            h1: ({ children }) => (
              <h1 className="text-sm font-bold text-white mb-2 mt-3 first:mt-0">{children}</h1>
            ),
            h2: ({ children }) => (
              <h2 className="text-xs font-bold text-white mb-1.5 mt-2.5 first:mt-0">{children}</h2>
            ),
            h3: ({ children }) => (
              <h3 className="text-xs font-semibold text-gray-200 mb-1 mt-2 first:mt-0">{children}</h3>
            ),
            blockquote: ({ children }) => (
              <blockquote className="border-l-2 border-indigo-500 pl-3 my-2 text-gray-400 italic">
                {children}
              </blockquote>
            ),
            code: ({ children }) => (
              <code className="px-1 py-0.5 bg-[#11131c] rounded font-mono text-[11px] text-indigo-300 border border-[#232738]">
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
    <div className="flex-1 overflow-y-auto p-4 space-y-4">
      {/* Empty State with Suggested Prompts */}
      {messages.length === 0 && !isStreaming && (
        <div className="flex flex-col items-center justify-center h-full max-w-xl mx-auto text-center py-12">
          <div className="w-12 h-12 rounded-full bg-[#1e2333] border border-[#2b3147] flex items-center justify-center text-xl text-indigo-400 mb-3 font-mono font-bold">
            SS
          </div>
          <h2 className="text-base font-semibold text-gray-200 mb-1">
            Scanner Intelligence Console
          </h2>
          <p className="text-xs text-gray-400 mb-6 max-w-md">
            Query across indexed public safety, mutual aid, and scanner talkgroup transmissions.
            Citations can be clicked to play the original radio audio.
          </p>

          <div className="w-full space-y-2 text-left">
            <span className="text-[11px] font-semibold text-gray-500 uppercase tracking-wider block">
              Suggested Radio Queries:
            </span>
            <div className="grid grid-cols-1 gap-2">
              {STARTER_PROMPTS.map((prompt, idx) => (
                <button
                  key={idx}
                  type="button"
                  onClick={() => onPromptSuggestion(prompt)}
                  className="px-3 py-2 bg-[#171a25] hover:bg-[#202535] border border-[#262c3f] hover:border-indigo-500/50 rounded text-left text-xs text-gray-300 transition-colors flex items-center justify-between cursor-pointer group"
                >
                  <span>"{prompt}"</span>
                  <span className="text-gray-500 group-hover:text-indigo-400 text-xs">→</span>
                </button>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Render Conversation Messages */}
      {messages.map((msg) => {
        const isUser = msg.role === 'user'
        const timeStr = msg.created_at
          ? new Date(msg.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
          : ''

        return (
          <div
            key={msg.id}
            className={`flex flex-col ${isUser ? 'items-end' : 'items-start'}`}
          >
            <div className="flex items-center gap-2 mb-1 text-[11px] text-gray-500">
              <span className="font-semibold">{isUser ? 'Operator' : 'ScanScribe Intel'}</span>
              <span>{timeStr}</span>
            </div>

            <div
              className={`max-w-3xl px-4 py-3 rounded-lg text-xs leading-relaxed select-text ${
                isUser
                  ? 'bg-indigo-600 text-white rounded-br-none whitespace-pre-wrap'
                  : 'bg-[#181b26] border border-[#292e42] text-gray-200 rounded-bl-none shadow-sm'
              }`}
            >
              {isUser ? (
                msg.content
              ) : (
                <>
                  {showThinking && msg.thought && <ThinkingAccordion thought={msg.thought} />}
                  {showTools && msg.tool_calls && msg.tool_calls.length > 0 && (
                    <ToolCallCard calls={msg.tool_calls} />
                  )}
                  {renderMarkdown(msg.content)}
                </>
              )}
            </div>
          </div>
        )
      })}

      {/* Live Streaming Response Bubble */}
      {isStreaming && (
        <div className="flex flex-col items-start max-w-3xl">
          <div className="flex items-center gap-2 mb-1 text-[11px] text-gray-500">
            <span className="font-semibold text-indigo-400">ScanScribe Intel</span>
            <span className="animate-pulse text-indigo-400">● {liveStatus}</span>
          </div>

          <div className="w-full bg-[#181b26] border border-[#2e344a] rounded-lg rounded-bl-none px-4 py-3 text-xs leading-relaxed text-gray-200 shadow-md">
            {/* Context Meta Header if available */}
            {streamMeta && (
              <div className="mb-2.5 pb-2 border-b border-[#262c3f] flex items-center justify-between text-[11px] text-gray-400 font-mono">
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
                renderMarkdown(streamingToken)
              ) : (
                <span className="text-gray-500 italic">
                  {streamMeta?.agentic
                    ? 'Querying the transmission database and assembling intelligence...'
                    : 'Reading transmissions and assembling intelligence...'}
                </span>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Stream Error Banner */}
      {streamError && (
        <div className="p-3 bg-red-950/50 border border-red-800 rounded-md text-xs text-red-200 flex items-center justify-between">
          <span>{streamError}</span>
        </div>
      )}

      <div ref={bottomRef} />
    </div>
  )
}
