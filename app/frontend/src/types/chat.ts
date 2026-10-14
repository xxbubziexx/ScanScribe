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

export interface ChatMessage {
  id: number
  thread_id: number
  role: 'user' | 'assistant' | 'system'
  content: string
  cited_log_ids?: number[] | null
  created_at: string
}

export interface ChatThreadDetail extends ChatThread {
  messages: ChatMessage[]
}

export interface ChatPromptInput {
  prompt: string
  time_scope?: ChatTimeScope
  talkgroups?: string[]
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
}

export interface ChatStreamMeta {
  type: 'meta'
  transmissions_count: number
  time_desc: string
  start_time: string
  end_time: string
  talkgroups: string[]
  model: string
}

export interface ChatStreamToken {
  type: 'token'
  content: string
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
  | ChatStreamDone
  | ChatStreamError
