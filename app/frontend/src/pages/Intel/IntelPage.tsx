import { useState, useEffect, useRef } from 'react'

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { chatApi } from '@/lib/chat'
import type {
  ChatThread,
  ChatTimeScope,
  TransmissionLookup,
  ChatStreamMeta,
  ChatMessage,
} from '@/types/chat'
import { TimeScopeBar } from './components/TimeScopeBar'
import { ChatMessageList } from './components/ChatMessageList'
import { ChatInputBox } from './components/ChatInputBox'
import { TransmissionAudioModal } from './components/TransmissionAudioModal'

export function IntelPage() {
  const queryClient = useQueryClient()

  // Selected thread state
  const [activeThreadId, setActiveThreadId] = useState<number | null>(null)
  const [timeScope, setTimeScope] = useState<ChatTimeScope>({ preset: 'today' })
  const [selectedTalkgroups, setSelectedTalkgroups] = useState<string[]>([])

  // Streaming state
  const [isStreaming, setIsStreaming] = useState(false)
  const [streamingToken, setStreamingToken] = useState('')
  const [streamMeta, setStreamMeta] = useState<ChatStreamMeta | null>(null)
  const [streamError, setStreamError] = useState<string | null>(null)
  const abortControllerRef = useRef<AbortController | null>(null)

  // Audio modal state
  const [selectedTx, setSelectedTx] = useState<TransmissionLookup | null>(null)

  // Mobile sidebar toggle
  const [sidebarOpen, setSidebarOpen] = useState(false)

  // Fetch threads
  const { data: threads = [], isLoading: loadingThreads } = useQuery({
    queryKey: ['chat-threads'],
    queryFn: () => chatApi.listThreads(),
  })

  // Fetch available talkgroups
  const { data: availableTalkgroups = [] } = useQuery({
    queryKey: ['chat-talkgroups'],
    queryFn: () => chatApi.listTalkgroups(),
  })

  // Auto-select latest thread or create initial
  useEffect(() => {
    if (!activeThreadId && threads.length > 0) {
      setActiveThreadId(threads[0].id)
      setTimeScope({
        preset: (threads[0].time_scope_preset as ChatTimeScope['preset']) || 'today',
        start_time: threads[0].start_time,
        end_time: threads[0].end_time,
      })
      setSelectedTalkgroups(threads[0].talkgroups || [])
    }
  }, [threads, activeThreadId])

  // Fetch active thread details
  const { data: activeThreadDetail } = useQuery({
    queryKey: ['chat-thread', activeThreadId],
    queryFn: () => (activeThreadId ? chatApi.getThread(activeThreadId) : null),
    enabled: Boolean(activeThreadId),
  })

  // Create new thread mutation
  const createThreadMutation = useMutation({
    mutationFn: () =>
      chatApi.createThread({
        title: 'New Query',
        time_scope_preset: timeScope.preset,
        start_time: timeScope.start_time,
        end_time: timeScope.end_time,
        talkgroups: selectedTalkgroups,
      }),
    onSuccess: (newThread) => {
      queryClient.invalidateQueries({ queryKey: ['chat-threads'] })
      setActiveThreadId(newThread.id)
      setSidebarOpen(false)
    },
  })

  // Delete thread mutation
  const deleteThreadMutation = useMutation({
    mutationFn: (threadId: number) => chatApi.deleteThread(threadId),
    onSuccess: (_, deletedId) => {
      queryClient.invalidateQueries({ queryKey: ['chat-threads'] })
      if (activeThreadId === deletedId) {
        const remaining = threads.filter((t) => t.id !== deletedId)
        setActiveThreadId(remaining.length > 0 ? remaining[0].id : null)
      }
    },
  })

  const handleSelectThread = (thread: ChatThread) => {
    if (isStreaming) handleStopStream()
    setActiveThreadId(thread.id)
    setTimeScope({
      preset: (thread.time_scope_preset as ChatTimeScope['preset']) || 'today',
      start_time: thread.start_time,
      end_time: thread.end_time,
    })
    setSelectedTalkgroups(thread.talkgroups || [])
    setSidebarOpen(false)
  }

  const handleTimeScopeChange = (newScope: ChatTimeScope) => {
    setTimeScope(newScope)
    if (activeThreadId) {
      void chatApi.updateThread(activeThreadId, {
        time_scope_preset: newScope.preset,
        start_time: newScope.start_time,
        end_time: newScope.end_time,
      })
    }
  }

  const handleTalkgroupsChange = (newTgs: string[]) => {
    setSelectedTalkgroups(newTgs)
    if (activeThreadId) {
      void chatApi.updateThread(activeThreadId, {
        talkgroups: newTgs,
      })
    }
  }

  const handleSendPrompt = async (promptText: string) => {
    if (!promptText.trim()) return

    let currentThreadId = activeThreadId
    if (!currentThreadId) {
      try {
        const created = await createThreadMutation.mutateAsync()
        currentThreadId = created.id
      } catch (e) {
        setStreamError('Failed to initialize conversation thread.')
        return
      }
    }

    setIsStreaming(true)
    setStreamingToken('')
    setStreamMeta(null)
    setStreamError(null)

    // Optimistically update message list in query cache
    const optimisticUserMsg: ChatMessage = {
      id: Date.now(),
      thread_id: currentThreadId,
      role: 'user',
      content: promptText,
      created_at: new Date().toISOString(),
    }

    queryClient.setQueryData(['chat-thread', currentThreadId], (old: any) => {
      if (!old) return old
      return {
        ...old,
        messages: [...(old.messages || []), optimisticUserMsg],
      }
    })

    const abortController = new AbortController()
    abortControllerRef.current = abortController

    await chatApi.streamQuery(
      currentThreadId,
      {
        prompt: promptText,
        time_scope: timeScope,
        talkgroups: selectedTalkgroups,
      },
      {
        onEvent: (event) => {
          if (event.type === 'meta') {
            setStreamMeta(event)
          } else if (event.type === 'token') {
            setStreamingToken((prev) => prev + event.content)
          } else if (event.type === 'error') {
            setStreamError(event.error)
          } else if (event.type === 'done') {
            // Completed
          }
        },
        onError: (err) => {
          setStreamError(err.message || 'Stream connection interrupted.')
          setIsStreaming(false)
        },
        onDone: () => {
          setIsStreaming(false)
          setStreamingToken('')
          queryClient.invalidateQueries({ queryKey: ['chat-thread', currentThreadId] })
          queryClient.invalidateQueries({ queryKey: ['chat-threads'] })
        },
      },
      abortController.signal,
    )
  }

  const handleStopStream = () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort()
      abortControllerRef.current = null
    }
    setIsStreaming(false)
    setStreamingToken('')
  }

  const handleSelectTx = async (txId: number) => {
    try {
      const tx = await chatApi.getTransmission(txId)
      setSelectedTx(tx)
    } catch (err) {
      setStreamError(`Failed to load transmission #${txId} details.`)
    }
  }

  const messages: ChatMessage[] = activeThreadDetail?.messages || []

  return (
    <div className="flex h-[calc(100dvh-56px)] bg-[#0c0e14] text-gray-100 overflow-hidden select-none">
      {/* Thread Sidebar (Desktop + Mobile Drawer) */}
      <div
        className={`${
          sidebarOpen ? 'translate-x-0' : '-translate-x-full md:translate-x-0'
        } fixed md:static inset-y-0 left-0 z-40 w-64 bg-[#11131c] border-r border-[#222533] flex flex-col transition-transform duration-200 ease-in-out md:translate-x-0`}
      >
        <div className="p-3 border-b border-[#222533] flex items-center justify-between">
          <button
            type="button"
            onClick={() => createThreadMutation.mutate()}
            disabled={createThreadMutation.isPending}
            className="flex-1 flex items-center justify-center gap-2 px-3 py-1.5 bg-indigo-600 hover:bg-indigo-500 text-white rounded font-medium text-xs shadow transition-colors cursor-pointer"
          >
            <span>+</span>
            <span>New Intel Query</span>
          </button>
          <button
            type="button"
            onClick={() => setSidebarOpen(false)}
            className="md:hidden ml-2 p-1 text-gray-400 hover:text-gray-200"
          >
            ✕
          </button>
        </div>

        {/* Thread List */}
        <div className="flex-1 overflow-y-auto p-2 space-y-1">
          {loadingThreads && (
            <div className="text-gray-500 text-xs p-3 text-center">Loading threads...</div>
          )}
          {!loadingThreads && threads.length === 0 && (
            <div className="text-gray-500 text-xs p-3 text-center">No past queries</div>
          )}
          {threads.map((t) => {
            const isSelected = t.id === activeThreadId
            const dateStr = t.updated_at
              ? new Date(t.updated_at).toLocaleDateString([], {
                  month: 'short',
                  day: 'numeric',
                })
              : ''

            return (
              <div
                key={t.id}
                onClick={() => handleSelectThread(t)}
                className={`group flex items-center justify-between px-3 py-2 rounded text-xs cursor-pointer transition-colors ${
                  isSelected
                    ? 'bg-[#1e2333] border border-indigo-600/40 text-white'
                    : 'hover:bg-[#161924] text-gray-400'
                }`}
              >
                <div className="flex-1 min-w-0 pr-2">
                  <div className="font-medium truncate text-gray-200">{t.title}</div>
                  <div className="text-[10px] text-gray-500 flex items-center gap-2">
                    <span>{t.time_scope_preset}</span>
                    <span>•</span>
                    <span>{dateStr}</span>
                  </div>
                </div>

                <button
                  type="button"
                  title="Delete query thread"
                  onClick={(e) => {
                    e.stopPropagation()
                    deleteThreadMutation.mutate(t.id)
                  }}
                  className="opacity-0 group-hover:opacity-100 hover:text-red-400 text-gray-500 p-1 transition-opacity"
                >
                  ✕
                </button>
              </div>
            )
          })}
        </div>
      </div>

      {/* Main Chat Area */}
      <div className="flex-1 flex flex-col min-w-0 bg-[#0f1118]">
        {/* Top Header / Scope Bar */}
        <div className="flex items-center justify-between px-4 py-2 bg-[#141721] border-b border-[#222533]">
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => setSidebarOpen(true)}
              className="md:hidden p-1 text-gray-400 hover:text-gray-100 mr-1"
            >
              ☰
            </button>
            <h1 className="text-sm font-semibold text-gray-200 truncate">
              {activeThreadDetail?.title || 'Scanner Intelligence'}
            </h1>
          </div>
          <div className="text-xs text-gray-500 font-mono">
            {threads.length} Threads Stored
          </div>
        </div>

        {/* Time Scope & Filter Controls */}
        <TimeScopeBar
          timeScope={timeScope}
          onChangeTimeScope={handleTimeScopeChange}
          availableTalkgroups={availableTalkgroups}
          selectedTalkgroups={selectedTalkgroups}
          onChangeTalkgroups={handleTalkgroupsChange}
          disabled={isStreaming}
        />

        {/* Conversation Message List */}
        <ChatMessageList
          messages={messages}
          streamingToken={streamingToken}
          streamMeta={streamMeta}
          isStreaming={isStreaming}
          streamError={streamError}
          onSelectTx={handleSelectTx}
          onPromptSuggestion={handleSendPrompt}
        />

        {/* Bottom Input Area */}
        <ChatInputBox
          onSend={handleSendPrompt}
          onStop={handleStopStream}
          isStreaming={isStreaming}
        />
      </div>

      {/* Ground-truth Audio Playback Modal */}
      {selectedTx && (
        <TransmissionAudioModal
          transmission={selectedTx}
          onClose={() => setSelectedTx(null)}
        />
      )}
    </div>
  )
}
export default IntelPage
