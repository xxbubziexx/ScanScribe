import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { EventsIncidentsPage } from '../pages/Events/IncidentsPage'
import { eventsApi } from '../lib/events'

const mockEvents = [
  {
    id: 1,
    event_id: 'EVT-001',
    monitor_id: 1,
    status: 'open',
    event_type: 'Structure Fire',
    broadcast_type: null,
    location: '123 Main St',
    latitude: 40.7,
    longitude: -74.0,
    resolved_address: '123 Main St, New York, NY',
    units: 'E1, L2',
    status_detail: 'Active on scene',
    talkgroup: 'FIRE-DISP',
    original_transcription: 'Working structure fire at 123 Main St',
    summary: 'Structure fire reported at 123 Main St',
    created_at: '2026-09-11T12:00:00Z',
    incident_at: '2026-09-11T12:00:00Z',
    closed_at: null,
    spans_attached: 2,
    audio_path: '/audio/1.mp3',
  },
  {
    id: 2,
    event_id: 'EVT-002',
    monitor_id: 1,
    status: 'open',
    event_type: 'Traffic Collision',
    broadcast_type: null,
    location: '456 Oak Ave',
    latitude: 40.8,
    longitude: -74.1,
    resolved_address: '456 Oak Ave, New York, NY',
    units: 'M1',
    status_detail: 'En route',
    talkgroup: 'EMS-DISP',
    original_transcription: 'Two car collision at 456 Oak Ave',
    summary: 'Two vehicle collision with injuries',
    created_at: '2026-09-11T12:30:00Z',
    incident_at: '2026-09-11T12:30:00Z',
    closed_at: null,
    spans_attached: 1,
    audio_path: '/audio/2.mp3',
  },
]

import { ToastProvider } from '../context/ToastContext'

function renderPage(initialEntries = ['/events']) {
  const client = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
    },
  })

  return render(
    <QueryClientProvider client={client}>
      <ToastProvider>
        <MemoryRouter initialEntries={initialEntries}>
          <EventsIncidentsPage />
        </MemoryRouter>
      </ToastProvider>
    </QueryClientProvider>,
  )
}

describe('EventsIncidentsPage mobile thread navigation', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.spyOn(eventsApi, 'monitors').mockResolvedValue([{ id: 1, name: 'Main Dispatch' }] as any)
    vi.spyOn(eventsApi, 'list').mockResolvedValue({ items: mockEvents, total: 2 } as any)
    vi.spyOn(eventsApi, 'rateLimitStatus').mockResolvedValue({ is_rate_limited: false } as any)
    vi.spyOn(eventsApi, 'detail').mockImplementation(async (id: string) => {
      const found = mockEvents.find((e) => e.event_id === id) || mockEvents[0]
      return { event: found, transcripts: [] } as any
    })
  })

  it('does not force open the first thread on mobile, allows selecting any thread and going back', async () => {
    // Mock mobile viewport (< 1024px)
    window.matchMedia = vi.fn().mockImplementation((query: string) => ({
      matches: false, // < 1024px
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }))

    renderPage(['/events'])

    // The incident list should appear
    await waitFor(() => {
      expect(screen.getAllByText(/Structure Fire/i).length).toBeGreaterThan(0)
      expect(screen.getByText('Traffic Collision')).toBeInTheDocument()
    })

    // Mobile sheet dialog should NOT be open yet
    expect(screen.queryByRole('dialog', { name: /incident details/i })).not.toBeInTheDocument()

    // Click the SECOND incident card (EVT-002)
    const secondCard = screen.getByText('Traffic Collision')
    fireEvent.click(secondCard)

    // Mobile sheet should now be open for EVT-002
    await waitFor(() => {
      const sheet = screen.getByRole('dialog', { name: /incident details/i })
      expect(sheet).toBeInTheDocument()
      expect(sheet).toHaveTextContent('EVT-002')
    })

    // Click "Back to Incidents"
    const backBtn = screen.getByRole('button', { name: /back to incidents/i })
    fireEvent.click(backBtn)

    // Mobile sheet must dismiss and NOT re-open
    await waitFor(() => {
      expect(screen.queryByRole('dialog', { name: /incident details/i })).not.toBeInTheDocument()
    })

    // Both cards should still be present in the list
    expect(screen.getAllByText(/Structure Fire/i).length).toBeGreaterThan(0)
    expect(screen.getByText('Traffic Collision')).toBeInTheDocument()

    // Now click the FIRST incident card (EVT-001)
    const firstCard = screen.getAllByText(/Structure Fire/i)[0]
    fireEvent.click(firstCard)

    // Mobile sheet should now open for EVT-001
    await waitFor(() => {
      const sheet2 = screen.getByRole('dialog', { name: /incident details/i })
      expect(sheet2).toBeInTheDocument()
      expect(sheet2).toHaveTextContent('EVT-001')
    })
  })

  it('automatically selects the first event on desktop viewports', async () => {
    // Mock desktop viewport (>= 1024px)
    window.matchMedia = vi.fn().mockImplementation((query: string) => ({
      matches: true, // >= 1024px
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }))

    renderPage(['/events'])

    // On desktop, the first event (EVT-001) should automatically be populated in the detail pane
    await waitFor(() => {
      expect(screen.getByRole('region', { name: /event detail/i })).toHaveTextContent('EVT-001')
    })

    // And mobile sheet dialog should not be rendered
    expect(screen.queryByRole('dialog', { name: /incident details/i })).not.toBeInTheDocument()
  })
})
