import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { ChatMessageList } from '../pages/Intel/components/ChatMessageList'
import type { ChatMessage } from '../types/chat'

const mockMessages: ChatMessage[] = [
  {
    id: 1,
    thread_id: 1,
    role: 'user',
    content: 'What happened at the structure fire today?',
    created_at: '2026-10-18T14:00:00Z',
  },
  {
    id: 2,
    thread_id: 1,
    role: 'assistant',
    content: `### Structure Fire Timeline
- 14:02: Engine 4 dispatched to 500 Oak St [TX-101].
- 14:05: Battalion 1 arrives on scene [TX-102].

[⚡ Scope Incident Audio (2 Transmissions)](scope:tx:101,102)`,
    cited_log_ids: [101, 102],
    created_at: '2026-10-18T14:00:05Z',
  },
]

describe('ChatMessageList Incident Scoping and Citations', () => {
  it('renders inline incident scope markdown action button and fires onScopeIncident', () => {
    const onScopeIncident = vi.fn()
    const onSelectTx = vi.fn()

    render(
      <ChatMessageList
        messages={mockMessages}
        streamingToken=""
        streamThought=""
        streamToolCalls={[]}
        streamMeta={null}
        isStreaming={false}
        streamError={null}
        showTools={true}
        showThinking={false}
        onSelectTx={onSelectTx}
        onPromptSuggestion={vi.fn()}
        onScopeIncident={onScopeIncident}
      />,
    )

    // Inline button rendered from [⚡ Scope Incident Audio (2 Transmissions)](scope:tx:101,102)
    const scopeBtn = screen.getByTitle(/load 2 incident transmissions into the audio deck/i)
    expect(scopeBtn).toBeInTheDocument()
    fireEvent.click(scopeBtn)

    expect(onScopeIncident).toHaveBeenCalledTimes(1)
    expect(onScopeIncident).toHaveBeenCalledWith([101, 102], expect.anything())
  })

  it('renders footer Scope Incident Audio quick button and calls onScopeIncident', () => {
    const onScopeIncident = vi.fn()
    render(
      <ChatMessageList
        messages={mockMessages}
        streamingToken=""
        streamThought=""
        streamToolCalls={[]}
        streamMeta={null}
        isStreaming={false}
        streamError={null}
        showTools={true}
        showThinking={false}
        onSelectTx={vi.fn()}
        onPromptSuggestion={vi.fn()}
        onScopeIncident={onScopeIncident}
      />,
    )

    const footerScopeBtn = screen.getByRole('button', {
      name: /scope incident audio \(2\)/i,
    })
    expect(footerScopeBtn).toBeInTheDocument()
    fireEvent.click(footerScopeBtn)

    expect(onScopeIncident).toHaveBeenCalledWith([101, 102], 'Incident Audio')
  })

  it('triggers onSelectTx when individual TX badge is clicked', () => {
    const onSelectTx = vi.fn()
    render(
      <ChatMessageList
        messages={mockMessages}
        streamingToken=""
        streamThought=""
        streamToolCalls={[]}
        streamMeta={null}
        isStreaming={false}
        streamError={null}
        showTools={true}
        showThinking={false}
        onSelectTx={onSelectTx}
        onPromptSuggestion={vi.fn()}
        onScopeIncident={vi.fn()}
      />,
    )

    const tx101Badge = screen.getByTitle(/listen to original radio transmission #101/i)
    expect(tx101Badge).toBeInTheDocument()
    fireEvent.click(tx101Badge)
    expect(onSelectTx).toHaveBeenCalledWith(101, [101, 102])
  })
})
