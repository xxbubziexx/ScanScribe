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
  }

  return (
    <div className="p-3 bg-[#131620] border-t border-[#252836]">
      <div className="flex items-end gap-2 max-w-4xl mx-auto bg-[#181b26] border border-[#2d3246] rounded-lg p-2 focus-within:border-indigo-500 transition-colors">
        <textarea
          ref={textareaRef}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Ask about incidents, units, talkgroups, or activity (e.g., 'What occurred around 6pm?')..."
          rows={1}
          disabled={disabled || isStreaming}
          className="flex-1 bg-transparent resize-none outline-none text-xs text-gray-200 placeholder-gray-500 max-h-32 min-h-[38px] py-2 px-1"
        />

        {isStreaming ? (
          <button
            type="button"
            onClick={onStop}
            className="px-3 py-2 bg-red-600 hover:bg-red-500 text-white rounded font-medium text-xs transition-colors cursor-pointer select-none"
          >
            Stop
          </button>
        ) : (
          <button
            type="button"
            onClick={handleSend}
            disabled={disabled || !text.trim()}
            className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 disabled:bg-[#252838] disabled:text-gray-500 text-white rounded font-medium text-xs transition-colors cursor-pointer disabled:cursor-not-allowed select-none"
          >
            Send
          </button>
        )}
      </div>
      <div className="flex items-center justify-between text-[11px] text-gray-500 max-w-4xl mx-auto mt-1 px-1">
        <span>Press <kbd className="px-1 py-0.5 bg-[#1e2230] rounded text-[10px] text-gray-400">Enter</kbd> to query, <kbd className="px-1 py-0.5 bg-[#1e2230] rounded text-[10px] text-gray-400">Shift+Enter</kbd> for newline</span>
        <span>Citations cite indexed transmission IDs</span>
      </div>
    </div>
  )
}
