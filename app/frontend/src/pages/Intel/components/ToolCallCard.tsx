import { useState } from 'react'

import type { ToolCallRecord } from '@/types/chat'

interface ToolCallCardProps {
  calls: ToolCallRecord[]
}

const TOOL_LABELS: Record<string, string> = {
  search_transcripts: 'Search transcripts',
  get_surrounding_transmissions: 'Surrounding transmissions',
  get_incident_records: 'Incident records',
  get_talkgroup_activity: 'Talkgroup activity',
}

function formatArgs(args: Record<string, unknown>): string {
  const parts = Object.entries(args)
    .filter(([, v]) => v !== null && v !== undefined && v !== '')
    .map(([k, v]) => `${k}: ${typeof v === 'string' ? `"${v}"` : JSON.stringify(v)}`)
  return parts.length ? parts.join(', ') : 'no arguments'
}

function StatusBadge({ status }: { status: ToolCallRecord['status'] }) {
  if (status === 'running') {
    return (
      <span className="flex items-center gap-1 text-indigo-300">
        <span className="inline-block w-1.5 h-1.5 rounded-full bg-indigo-400 animate-pulse" />
        Running
      </span>
    )
  }
  if (status === 'error') return <span className="text-red-400">Failed</span>
  return <span className="text-emerald-400">Done</span>
}

function ToolCallRow({ call }: { call: ToolCallRecord }) {
  const [open, setOpen] = useState(false)
  const label = TOOL_LABELS[call.tool] ?? call.tool

  return (
    <div className="border-b border-[#262c3f] last:border-b-0">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="w-full flex items-center justify-between gap-3 px-2.5 py-1.5 text-left hover:bg-[#1c2030] transition-colors cursor-pointer"
      >
        <div className="min-w-0 flex-1">
          <div className="text-[11px] font-semibold text-gray-200">{label}</div>
          <div className="text-[11px] font-mono text-gray-500 truncate">{formatArgs(call.arguments)}</div>
        </div>
        <div className="shrink-0 text-right text-[11px] font-mono">
          <StatusBadge status={call.status} />
          {call.status !== 'running' && (
            <div className="text-gray-500">
              {call.summary}
              {typeof call.duration_ms === 'number' && call.duration_ms > 0 ? ` · ${call.duration_ms} ms` : ''}
            </div>
          )}
        </div>
      </button>
      {open && (
        <pre className="mx-2.5 mb-2 p-2 rounded bg-[#10121a] border border-[#232738] text-[11px] text-gray-400 overflow-x-auto select-text">
          {JSON.stringify({ tool: call.tool, arguments: call.arguments }, null, 2)}
        </pre>
      )}
    </div>
  )
}

export function ToolCallCard({ calls }: ToolCallCardProps) {
  if (calls.length === 0) return null
  return (
    <div className="mb-2.5 rounded border border-[#2b3147] bg-[#141722] overflow-hidden">
      <div className="px-2.5 py-1 text-[10px] font-semibold uppercase tracking-wider text-gray-500 bg-[#161a26] border-b border-[#262c3f]">
        Tool calls ({calls.length})
      </div>
      {calls.map((call) => (
        <ToolCallRow key={call.call_id} call={call} />
      ))}
    </div>
  )
}
