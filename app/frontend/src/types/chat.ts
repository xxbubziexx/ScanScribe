/**
 * Type definitions for Scanner Intelligence conversational queries.
 */

export interface ChatTimeScope {
  preset: '1h' | '4h' | '12h' | 'today' | 'yesterday' | 'custom'
  start_time?: string | null
  end_time?: string | null
}

export interface ChatThread {
  id: number
  user_id: number
  title: string
  time_scope_preset: string
  start_time: string | null
  end_time: string | null
  talkgroups: string[]
  created_at: string
  updated_at: string
  message_count?: number
}

export type ToolCallStatus = 'running' | 'ok' | 'error'

export interface ToolCallRecord {
  call_id: string
  tool: string
  arguments: Record<string, unknown>
  status: ToolCallStatus
  summary?: string | null
  count?: number | null
  duration_ms?: number | null
}

export interface ChatMessage {
  id: number
  thread_id: number
  role: 'user' | 'assistant' | 'system'
  content: string
  cited_log_ids?: number[] | null
  thought?: string | null
  tool_calls?: ToolCallRecord[] | null
  created_at: string
}

export interface ChatThreadDetail extends ChatThread {
  messages: ChatMessage[]
}

export interface ChatPromptInput {
  prompt: string
  time_scope?: ChatTimeScope
}

export interface TransmissionLookup {
  id: number
  filename: string
  timestamp: string
  log_date: string | null
  duration: number
  audio_path: string | null
  transcript: string
  talkgroup: string | null
  audio_url: string
  audio_available?: boolean
}

export interface ChatStreamMeta {
  type: 'meta'
  transmissions_count: number
  time_desc: string
  start_time?: string | null
  end_time?: string | null
  talkgroups: string[]
  model: string
  agentic?: boolean
}

export interface ChatStreamToken {
  type: 'token'
  content: string
}

export interface ChatStreamThinking {
  type: 'thinking'
  content: string
}

export interface ChatStreamToolCall {
  type: 'tool_call'
  call_id: string
  tool: string
  arguments: Record<string, unknown>
}

export interface ChatStreamToolResult {
  type: 'tool_result'
  call_id: string
  tool: string
  status: 'ok' | 'error'
  summary?: string | null
  count?: number | null
  duration_ms?: number | null
}

export interface ChatStreamDone {
  type: 'done'
  content: string
  cited_log_ids: number[]
}

export interface ChatStreamError {
  type: 'error'
  error: string
}

export type ChatStreamEvent =
  | ChatStreamMeta
  | ChatStreamToken
  | ChatStreamThinking
  | ChatStreamToolCall
  | ChatStreamToolResult
  | ChatStreamDone
  | ChatStreamError
