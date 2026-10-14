import { useRef, useEffect } from 'react'
import type { ChatMessage, ChatStreamMeta } from '@/types/chat'

interface ChatMessageListProps {
  messages: ChatMessage[]
  streamingToken: string
  streamMeta: ChatStreamMeta | null
  isStreaming: boolean
  streamError: string | null
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

export function ChatMessageList({
  messages,
  streamingToken,
  streamMeta,
  isStreaming,
  streamError,
  onSelectTx,
  onPromptSuggestion,
}: ChatMessageListProps) {

  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages.length, streamingToken, isStreaming])

  const renderContentWithCitations = (content: string) => {
    const parts = content.split(/(\[TX-\d+\])/g)

    return parts.map((part, idx) => {
      const match = part.match(/\[TX-(\d+)\]/)
      if (match) {
        const txId = parseInt(match[1], 10)
        return (
          <button
            key={idx}
            type="button"
            onClick={() => onSelectTx(txId)}
            className="inline-flex items-center gap-1 mx-1 px-1.5 py-0.5 rounded font-mono text-[11px] font-semibold bg-indigo-950/80 hover:bg-indigo-800 text-indigo-300 border border-indigo-700/60 hover:border-indigo-400 transition-colors cursor-pointer select-none"
            title={`Listen to original radio transmission #${txId}`}
          >
            <span>TX #{txId}</span>
            <span className="text-[10px]">🔊</span>
          </button>
        )
      }
      return <span key={idx}>{part}</span>
    })
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
              className={`max-w-2xl px-4 py-3 rounded-lg text-xs leading-relaxed whitespace-pre-wrap select-text ${
                isUser
                  ? 'bg-indigo-600 text-white rounded-br-none'
                  : 'bg-[#181b26] border border-[#292e42] text-gray-200 rounded-bl-none shadow-sm'
              }`}
            >
              {isUser ? msg.content : renderContentWithCitations(msg.content)}
            </div>
          </div>
        )
      })}

      {/* Live Streaming Response Bubble */}
      {isStreaming && (
        <div className="flex flex-col items-start max-w-2xl">
          <div className="flex items-center gap-2 mb-1 text-[11px] text-gray-500">
            <span className="font-semibold text-indigo-400">ScanScribe Intel</span>
            <span className="animate-pulse text-indigo-400">● Analyzing logs...</span>
          </div>

          <div className="w-full bg-[#181b26] border border-[#2e344a] rounded-lg rounded-bl-none px-4 py-3 text-xs leading-relaxed text-gray-200 shadow-md">
            {/* Context Meta Header if available */}
            {streamMeta && (
              <div className="mb-2.5 pb-2 border-b border-[#262c3f] flex items-center justify-between text-[11px] text-gray-400 font-mono">
                <span>
                  Scanned: <strong className="text-indigo-300">{streamMeta.transmissions_count}</strong> transmissions
                </span>
                <span>{streamMeta.time_desc}</span>
              </div>
            )}

            <div className="whitespace-pre-wrap">
              {streamingToken ? (
                renderContentWithCitations(streamingToken)
              ) : (
                <span className="text-gray-500 italic">Reading transmissions and assembling intelligence...</span>
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
