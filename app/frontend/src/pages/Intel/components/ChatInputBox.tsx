import { useState, useRef, useEffect } from 'react'

interface ChatInputBoxProps {
  onSend: (text: string) => void
  onStop: () => void
  isStreaming: boolean
  disabled?: boolean
  initialPrompt?: string
}

export function ChatInputBox({
  onSend,
  onStop,
  isStreaming,
  disabled = false,
  initialPrompt = '',
}: ChatInputBoxProps) {
  const [text, setText] = useState(initialPrompt)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    if (initialPrompt) {
      setText(initialPrompt)
      textareaRef.current?.focus()
    }
  }, [initialPrompt])

  // Auto-resize textarea height
  useEffect(() => {
    const el = textareaRef.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${Math.min(el.scrollHeight, 180)}px`
  }, [text])

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  const handleSend = () => {
    const trimmed = text.trim()
    if (!trimmed || isStreaming || disabled) return
    onSend(trimmed)
    setText('')
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto'
    }
  }

  return (
    <div className="shrink-0 bg-transparent px-4 pb-4 pt-1">
      <div className="max-w-3xl mx-auto w-full">
        <div className="bg-[#141724] border border-[#282d42] focus-within:border-indigo-500/80 focus-within:ring-2 focus-within:ring-indigo-500/20 rounded-2xl shadow-xl p-3 flex flex-col gap-2 transition-all">
          <textarea
            ref={textareaRef}
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask about units, incidents, addresses, or activity (e.g., 'What did unit 112 do today?')..."
            rows={1}
            disabled={disabled || isStreaming}
            className="w-full bg-transparent resize-none outline-none text-sm text-gray-100 placeholder-gray-500 min-h-[44px] max-h-[180px] py-1 px-1 leading-relaxed"
          />

          <div className="flex items-center justify-between pt-1 border-t border-[#1e2336]/60">
            <span className="text-[11px] text-gray-500 select-none">
              <kbd className="px-1.5 py-0.5 bg-[#1b1f30] rounded text-[10px] text-gray-400 font-mono">Enter</kbd> to query, <kbd className="px-1.5 py-0.5 bg-[#1b1f30] rounded text-[10px] text-gray-400 font-mono">Shift+Enter</kbd> for newline
            </span>

            <div className="flex items-center gap-2">
              {isStreaming ? (
                <button
                  type="button"
                  onClick={onStop}
                  className="px-3.5 py-1.5 bg-rose-600 hover:bg-rose-500 text-white rounded-xl font-medium text-xs shadow transition-colors cursor-pointer select-none flex items-center gap-1.5"
                >
                  <span className="w-2 h-2 rounded-xs bg-white" />
                  <span>Stop</span>
                </button>
              ) : (
                <button
                  type="button"
                  onClick={handleSend}
                  disabled={disabled || !text.trim()}
                  className="px-4 py-1.5 bg-indigo-600 hover:bg-indigo-500 disabled:bg-[#1f2436] disabled:text-gray-500 text-white rounded-xl font-medium text-xs shadow-md transition-all cursor-pointer disabled:cursor-not-allowed select-none flex items-center gap-1.5"
                >
                  <span>Query</span>
                  <span className="text-xs">↑</span>
                </button>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
