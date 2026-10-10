import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { useToast } from '@/context/ToastContext'
import { logsApi } from '@/lib/logs'

export function EditableTranscript({
  logId,
  initialText,
  canEdit = true,
}: {
  logId: number
  initialText: string
  canEdit?: boolean
}) {
  const [editing, setEditing] = useState(false)
  const [text, setText] = useState(initialText)

  const { addToast } = useToast()

  const mutation = useMutation({
    mutationFn: (newText: string) => logsApi.review(logId, newText),
    onSuccess: () => setEditing(false),
    onError: (e: any) => addToast(e?.message || 'Failed to save transcript', 'error'),
  })

  if (!canEdit) {
    return (
      <p className="ss-events-kv-value min-w-0 flex-1 text-sm text-gray-300 whitespace-pre-wrap leading-relaxed">
        {text || '—'}
      </p>
    )
  }

  if (editing) {
    return (
      <div className="ss-events-kv-value min-w-0 flex-1 w-full flex flex-col gap-2 mt-0.5">
        <textarea
          className="ss-input text-sm w-full min-h-[5.5rem] resize-y leading-relaxed font-normal"
          rows={3}
          value={text}
          onChange={(e) => setText(e.target.value)}
          autoFocus
        />
        <div className="flex items-center gap-2">
          <button
            className="ss-btn-primary text-xs py-1 px-2.5"
            disabled={mutation.isPending}
            onClick={() => mutation.mutate(text)}
          >
            {mutation.isPending ? 'Saving...' : 'Save & Mark Reviewed'}
          </button>
          <button
            className="ss-btn-ghost text-xs py-1 px-2.5"
            disabled={mutation.isPending}
            onClick={() => {
              setEditing(false)
              setText(initialText)
            }}
          >
            Cancel
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="ss-events-kv-value group relative min-w-0 flex-1">
      <p className="text-sm text-gray-300 pr-8 whitespace-pre-wrap leading-relaxed">{text || '—'}</p>
      <button
        onClick={() => setEditing(true)}
        className="absolute top-0 right-0 opacity-0 group-hover:opacity-100 text-indigo-400 hover:text-indigo-300 text-xs transition underline cursor-pointer"
      >
        Edit
      </button>
    </div>
  )
}
