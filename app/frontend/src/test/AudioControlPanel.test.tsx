import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { AudioControlPanel } from '../pages/Intel/components/AudioControlPanel'
import type { TransmissionLookup } from '../types/chat'

const mockTransmissions: TransmissionLookup[] = [
  {
    id: 101,
    filename: '101.mp3',
    talkgroup: 'Dispatch North',
    timestamp: '2026-10-17T14:30:00Z',
    log_date: '2026-10-17',
    duration: 4.5,
    audio_path: '/audio/101.mp3',
    audio_url: '/audio/101.mp3',
    audio_available: true,
    transcript: 'Engine 4 responding to structure fire at 500 Oak St.',
  },
  {
    id: 102,
    filename: '102.mp3',
    talkgroup: 'Tac 2',
    timestamp: '2026-10-17T14:32:00Z',
    log_date: '2026-10-17',
    duration: 6.2,
    audio_path: '/audio/102.mp3',
    audio_url: '/audio/102.mp3',
    audio_available: true,
    transcript: 'Battalion 1 on scene with heavy smoke showing.',
  },
]

describe('AudioControlPanel mobile drawer and desktop docked behavior', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    // Mock HTMLMediaElement methods in jsdom
    window.HTMLMediaElement.prototype.play = vi.fn().mockResolvedValue(undefined)
    window.HTMLMediaElement.prototype.pause = vi.fn()
    window.HTMLMediaElement.prototype.load = vi.fn()
  })

  it('renders nothing when isOpen is false', () => {
    const { container } = render(
      <AudioControlPanel
        transmissions={mockTransmissions}
        activeTxId={null}
        isOpen={false}
        onClose={vi.fn()}
        onSelectTx={vi.fn()}
      />,
    )
    expect(container.firstChild).toBeNull()
  })

  it('renders backdrop and responsive drawer aside when isOpen is true', () => {
    render(
      <AudioControlPanel
        transmissions={mockTransmissions}
        activeTxId={101}
        isOpen={true}
        onClose={vi.fn()}
        onSelectTx={vi.fn()}
      />,
    )

    const deck = screen.getByRole('complementary', { name: /transmission audio deck/i })
    expect(deck).toBeInTheDocument()
    expect(deck).toHaveAttribute('id', 'ss-audio-deck')
    // Verify responsive styling classes
    expect(deck.className).toContain('fixed')
    expect(deck.className).toContain('lg:static')

    // Verify transmission items
    expect(screen.getAllByText('TX #101').length).toBeGreaterThan(0)
    expect(screen.getByText('TX #102')).toBeInTheDocument()
    expect(screen.getAllByText('Engine 4 responding to structure fire at 500 Oak St.').length).toBeGreaterThan(0)
  })

  it('calls onClose when close button is clicked', () => {
    const onClose = vi.fn()
    render(
      <AudioControlPanel
        transmissions={mockTransmissions}
        activeTxId={null}
        isOpen={true}
        onClose={onClose}
        onSelectTx={vi.fn()}
      />,
    )

    const closeBtn = screen.getByRole('button', { name: /close audio deck/i })
    fireEvent.click(closeBtn)
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('calls onClose when mobile backdrop is clicked', () => {
    const onClose = vi.fn()
    const { container } = render(
      <AudioControlPanel
        transmissions={mockTransmissions}
        activeTxId={null}
        isOpen={true}
        onClose={onClose}
        onSelectTx={vi.fn()}
      />,
    )

    // The backdrop has aria-hidden="true" and class lg:hidden
    const backdrop = container.querySelector('.fixed.inset-0.bg-black\\/75')
    expect(backdrop).toBeInTheDocument()
    if (backdrop) fireEvent.click(backdrop)
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('calls onClose when Escape key is pressed', () => {
    const onClose = vi.fn()
    render(
      <AudioControlPanel
        transmissions={mockTransmissions}
        activeTxId={null}
        isOpen={true}
        onClose={onClose}
        onSelectTx={vi.fn()}
      />,
    )

    fireEvent.keyDown(window, { key: 'Escape' })
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('calls onSelectTx when a transmission card in the queue is tapped', () => {
    const onSelectTx = vi.fn()
    render(
      <AudioControlPanel
        transmissions={mockTransmissions}
        activeTxId={null}
        isOpen={true}
        onClose={vi.fn()}
        onSelectTx={onSelectTx}
      />,
    )

    const cardTx102 = screen.getByText('TX #102').closest('div')
    expect(cardTx102).toBeInTheDocument()
    if (cardTx102) fireEvent.click(cardTx102)
    expect(onSelectTx).toHaveBeenCalledWith(102)
  })

  it('supports previous and next transmission track transport controls', () => {
    const onSelectTx = vi.fn()
    const { rerender } = render(
      <AudioControlPanel
        transmissions={mockTransmissions}
        activeTxId={101}
        isOpen={true}
        onClose={vi.fn()}
        onSelectTx={onSelectTx}
      />,
    )

    const prevBtn = screen.getByRole('button', { name: /previous transmission/i })
    const nextBtn = screen.getByRole('button', { name: /next transmission/i })

    // On track 1 (index 0), Previous is disabled and Next is enabled
    expect(prevBtn).toBeDisabled()
    expect(nextBtn).toBeEnabled()

    fireEvent.click(nextBtn)
    expect(onSelectTx).toHaveBeenCalledWith(102)

    // Re-render on track 2 (index 1)
    rerender(
      <AudioControlPanel
        transmissions={mockTransmissions}
        activeTxId={102}
        isOpen={true}
        onClose={vi.fn()}
        onSelectTx={onSelectTx}
      />,
    )

    expect(prevBtn).toBeEnabled()
    expect(nextBtn).toBeDisabled()

    fireEvent.click(prevBtn)
    expect(onSelectTx).toHaveBeenCalledWith(101)
  })

  it('supports [ and ] keyboard shortcuts for track skipping', () => {
    const onSelectTx = vi.fn()
    render(
      <AudioControlPanel
        transmissions={mockTransmissions}
        activeTxId={101}
        isOpen={true}
        onClose={vi.fn()}
        onSelectTx={onSelectTx}
      />,
    )

    // Press ] to advance to next
    fireEvent.keyDown(window, { key: ']' })
    expect(onSelectTx).toHaveBeenCalledWith(102)
  })

  it('renders scoped playlist header and calls onClearScope when Show All is clicked', () => {
    const onClearScope = vi.fn()
    render(
      <AudioControlPanel
        transmissions={mockTransmissions}
        activeTxId={101}
        isOpen={true}
        onClose={vi.fn()}
        onSelectTx={vi.fn()}
        scopedPlaylist={{ title: 'Pursuit Incident Timeline', txIds: [101, 102] }}
        onClearScope={onClearScope}
        allTransmissionsCount={15}
      />,
    )

    expect(screen.getByText('Pursuit Incident Timeline')).toBeInTheDocument()
    expect(screen.getByText('2 scoped')).toBeInTheDocument()

    const showAllBtn = screen.getByRole('button', { name: /show all/i })
    expect(showAllBtn).toBeInTheDocument()
    fireEvent.click(showAllBtn)
    expect(onClearScope).toHaveBeenCalledTimes(1)
  })
})

