import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, within, fireEvent } from '@testing-library/react'
import { MemoryRouter, Routes, Route } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import * as AuthContextModule from '../context/AuthContext'
import { ToastProvider } from '../context/ToastContext'
import { useAdminCapability } from '../hooks/useAdminCapability'
import { RequireAdmin } from '../components/auth/RequireAdmin'
import { EventsLayout } from '../pages/Events/EventsLayout'
import { TopNav } from '../components/layout/TopNav'
import { DashboardPage } from '../pages/Dashboard/DashboardPage'
import { EventsIncidentsPage } from '../pages/Events/IncidentsPage'
import { eventsApi } from '../lib/events'

function setupMatchMedia(matches: boolean) {
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    value: vi.fn().mockImplementation((query: string) => ({
      matches,
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  })
}

function mockAuth(isAdmin: boolean) {
  vi.spyOn(AuthContextModule, 'useAuth').mockReturnValue({
    user: {
      id: 1,
      username: 'admin_test',
      email: 'admin@scanscribe.local',
      is_active: true,
      is_admin: isAdmin,
      created_at: '2026-01-01T00:00:00Z',
    },
    token: 'fake-token',
    isLoading: false,
    login: vi.fn(),
    logout: vi.fn(),
  })
}

describe('Admin mobile restrictions', () => {
  let queryClient: QueryClient

  beforeEach(() => {
    vi.clearAllMocks()
    queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
      },
    })
  })

  describe('useAdminCapability hook', () => {
    function CapabilityTester() {
      const cap = useAdminCapability()
      return (
        <div>
          <span data-testid="can-admin">{String(cap.canAdmin)}</span>
          <span data-testid="is-mobile">{String(cap.isMobile)}</span>
          <span data-testid="is-account-admin">{String(cap.isAccountAdmin)}</span>
        </div>
      )
    }

    it('grants admin capability to admin accounts on desktop', () => {
      setupMatchMedia(false) // desktop
      mockAuth(true)

      render(<CapabilityTester />)
      expect(screen.getByTestId('can-admin').textContent).toBe('true')
      expect(screen.getByTestId('is-mobile').textContent).toBe('false')
      expect(screen.getByTestId('is-account-admin').textContent).toBe('true')
    })

    it('restricts admin capability from mobile clients even if account is admin', () => {
      setupMatchMedia(true) // mobile
      mockAuth(true)

      render(<CapabilityTester />)
      expect(screen.getByTestId('can-admin').textContent).toBe('false')
      expect(screen.getByTestId('is-mobile').textContent).toBe('true')
      expect(screen.getByTestId('is-account-admin').textContent).toBe('true')
    })

    it('restricts admin capability for non-admin accounts on desktop', () => {
      setupMatchMedia(false) // desktop
      mockAuth(false)

      render(<CapabilityTester />)
      expect(screen.getByTestId('can-admin').textContent).toBe('false')
      expect(screen.getByTestId('is-mobile').textContent).toBe('false')
      expect(screen.getByTestId('is-account-admin').textContent).toBe('false')
    })
  })

  describe('RequireAdmin route guard on mobile', () => {
    it('redirects mobile admin client from /events/monitors to /events', () => {
      setupMatchMedia(true) // mobile
      mockAuth(true) // admin account

      render(
        <MemoryRouter initialEntries={['/events/monitors']}>
          <Routes>
            <Route path="/events" element={<div>Events Landing</div>} />
            <Route
              path="/events/monitors"
              element={
                <RequireAdmin>
                  <div>Monitors Config Secret</div>
                </RequireAdmin>
              }
            />
          </Routes>
        </MemoryRouter>,
      )

      expect(screen.getByText('Events Landing')).toBeInTheDocument()
      expect(screen.queryByText('Monitors Config Secret')).not.toBeInTheDocument()
    })

    it('redirects mobile admin client from /settings to /', () => {
      setupMatchMedia(true) // mobile
      mockAuth(true)

      render(
        <MemoryRouter initialEntries={['/settings']}>
          <Routes>
            <Route path="/" element={<div>Command Center Landing</div>} />
            <Route
              path="/settings"
              element={
                <RequireAdmin>
                  <div>Admin Settings Panel</div>
                </RequireAdmin>
              }
            />
          </Routes>
        </MemoryRouter>,
      )

      expect(screen.getByText('Command Center Landing')).toBeInTheDocument()
      expect(screen.queryByText('Admin Settings Panel')).not.toBeInTheDocument()
    })
  })

  describe('EventsLayout tabs on mobile', () => {
    it('does not render subnav tabs for monitor config or debug on mobile', () => {
      setupMatchMedia(true) // mobile
      mockAuth(true) // even with admin account

      render(
        <MemoryRouter initialEntries={['/events']}>
          <EventsLayout />
        </MemoryRouter>,
      )

      expect(screen.queryByRole('navigation', { name: /events section/i })).not.toBeInTheDocument()
      expect(screen.queryByText('Monitor config')).not.toBeInTheDocument()
      expect(screen.queryByText('Pipeline & LLM Debug')).not.toBeInTheDocument()
    })

    it('renders subnav tabs on desktop for admin users', () => {
      setupMatchMedia(false) // desktop
      mockAuth(true)

      render(
        <MemoryRouter initialEntries={['/events']}>
          <EventsLayout />
        </MemoryRouter>,
      )

      expect(screen.getByRole('navigation', { name: /events section/i })).toBeInTheDocument()
      expect(screen.getByText('Incidents')).toBeInTheDocument()
      expect(screen.getByText('Monitor config')).toBeInTheDocument()
      expect(screen.getByText('Pipeline & LLM Debug')).toBeInTheDocument()
    })
  })

  describe('TopNav mobile drawer admin restrictions', () => {
    it('shows Admin (Desktop Only) in user card and omits admin links in drawer on mobile', () => {
      setupMatchMedia(true) // mobile
      mockAuth(true)

      render(
        <MemoryRouter initialEntries={['/']}>
          <TopNav />
        </MemoryRouter>,
      )

      // Open drawer
      const menuBtn = screen.getByRole('button', { name: /open navigation drawer/i })
      fireEvent.click(menuBtn)

      const drawer = screen.getByRole('dialog', { name: /navigation drawer/i })
      expect(drawer).toBeInTheDocument()

      // User card displays "Admin (Desktop Only)"
      expect(within(drawer).getByText('Admin (Desktop Only)')).toBeInTheDocument()

      // Admin links are strictly omitted from the mobile drawer
      const nav = within(drawer).getByRole('navigation', { name: /mobile main navigation/i })
      expect(within(nav).queryByRole('link', { name: /database/i })).not.toBeInTheDocument()
      expect(within(nav).queryByRole('link', { name: /users/i })).not.toBeInTheDocument()
      expect(within(nav).queryByRole('link', { name: /settings/i })).not.toBeInTheDocument()
    })
  })

  describe('DashboardPage watcher controls on mobile', () => {
    it('hides Start/Stop/Pause watcher controls on mobile', () => {
      setupMatchMedia(true) // mobile
      mockAuth(true) // even for admin account

      render(
        <QueryClientProvider client={queryClient}>
          <ToastProvider>
            <MemoryRouter>
              <DashboardPage />
            </MemoryRouter>
          </ToastProvider>
        </QueryClientProvider>,
      )

      expect(screen.queryByRole('button', { name: /start watcher/i })).not.toBeInTheDocument()
      expect(screen.queryByRole('button', { name: /stop watcher/i })).not.toBeInTheDocument()
      expect(screen.queryByRole('button', { name: /pause/i })).not.toBeInTheDocument()
    })
  })

  describe('IncidentsPage admin actions on mobile', () => {
    it('renders detail view without Close, Delete, or Regenerate buttons when on mobile', async () => {
      setupMatchMedia(true) // mobile
      mockAuth(true) // admin account, but mobile

      const mockEventItem = {
        id: 1,
        event_id: 'EVT-20260911-001',
        monitor_id: 1,
        status: 'open' as const,
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
        spans_attached: 1,
        audio_path: '/audio/1.mp3',
      }

      vi.spyOn(eventsApi, 'monitors').mockResolvedValue([{ id: 1, name: 'Main Dispatch' }] as any)
      vi.spyOn(eventsApi, 'list').mockResolvedValue({ items: [mockEventItem], total: 1 } as any)
      vi.spyOn(eventsApi, 'rateLimitStatus').mockResolvedValue({ is_rate_limited: false } as any)
      vi.spyOn(eventsApi, 'detail').mockResolvedValue({
        event: mockEventItem,
        transcripts: [
          {
            log_entry_id: 101,
            timestamp: '2026-09-11T12:00:00Z',
            talkgroup: 'FIRE-DISP',
            transcript: 'Engine 1 on scene of working fire',
            entities: {},
            llm_reason: null,
            is_trigger: true,
            has_playback: false,
            audio_path: null,
          },
        ],
      } as any)

      render(
        <QueryClientProvider client={queryClient}>
          <ToastProvider>
            <MemoryRouter initialEntries={['/events?eventId=EVT-20260911-001']}>
              <EventsIncidentsPage />
            </MemoryRouter>
          </ToastProvider>
        </QueryClientProvider>,
      )

      // Incident feed loads, wait for the selected item
      const items = await screen.findAllByText('Structure Fire')
      expect(items.length).toBeGreaterThan(0)

      // In the detail pane/dialog, Close, Delete, and Regenerate buttons should not be present
      expect(screen.queryByRole('button', { name: /^close$/i })).not.toBeInTheDocument()
      expect(screen.queryByRole('button', { name: /^delete$/i })).not.toBeInTheDocument()
      expect(screen.queryByRole('button', { name: /regenerate|generate summary/i })).not.toBeInTheDocument()
      expect(screen.queryByRole('button', { name: /^edit$/i })).not.toBeInTheDocument()
    })
  })
})
