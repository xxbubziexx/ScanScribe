import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { TalkgroupTrackerWidget } from '@/pages/Insights/components/TalkgroupTrackerWidget'
import { TalkgroupShareWidget } from '@/pages/Insights/components/TalkgroupShareWidget'
import type { TalkgroupTrackerTelemetry } from '@/types/insights'

const mockNavigate = vi.fn()
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom')
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  }
})

describe('TalkgroupTrackerWidget', () => {
  const mockTelemetry: TalkgroupTrackerTelemetry = {
    total_talkgroups: 3,
    total_calls: 150,
    total_airtime: 1200,
    busiest_talkgroup: {
      talkgroup: 'DISPATCH_NORTH',
      count: 90,
      duration: 720,
      percentage: 60,
      is_new: false,
      is_new_vs_yesterday: false,
    },
    new_talkgroups_count: 1,
    new_talkgroups: [
      {
        talkgroup: 'TAC_SPECIAL_OPS',
        count: 15,
        duration: 180,
        percentage: 15,
        is_new: true,
        is_new_vs_yesterday: true,
        first_seen: '2026-10-23T10:00:00',
      },
    ],
    new_vs_yesterday: [
      {
        talkgroup: 'TAC_SPECIAL_OPS',
        count: 15,
        duration: 180,
        percentage: 15,
        is_new: true,
        is_new_vs_yesterday: true,
      },
      {
        talkgroup: 'FIRE_RESERVE',
        count: 45,
        duration: 300,
        percentage: 25,
        is_new: false,
        is_new_vs_yesterday: true,
      },
    ],
    ranked_talkgroups: [
      {
        talkgroup: 'DISPATCH_NORTH',
        count: 90,
        duration: 720,
        percentage: 60,
        is_new: false,
        is_new_vs_yesterday: false,
      },
      {
        talkgroup: 'FIRE_RESERVE',
        count: 45,
        duration: 300,
        percentage: 25,
        is_new: false,
        is_new_vs_yesterday: true,
      },
      {
        talkgroup: 'TAC_SPECIAL_OPS',
        count: 15,
        duration: 180,
        percentage: 15,
        is_new: true,
        is_new_vs_yesterday: true,
      },
    ],
  }

  it('renders ranking for every talkgroup observed from scoped date selection', () => {
    render(
      <MemoryRouter>
        <TalkgroupTrackerWidget
          data={mockTelemetry}
          dateFrom="2026-10-23"
          dateTo="2026-10-23"
        />
      </MemoryRouter>
    )

    expect(screen.getByRole('heading', { level: 3, name: 'Talkgroup Intelligence & Tracker' })).toBeInTheDocument()
    expect(screen.getAllByText('DISPATCH_NORTH').length).toBeGreaterThan(0)
    expect(screen.getByText('FIRE_RESERVE')).toBeInTheDocument()
    expect(screen.getByText('TAC_SPECIAL_OPS')).toBeInTheDocument()

    // Rank badges
    expect(screen.getAllByText('1').length).toBeGreaterThan(0)
    expect(screen.getAllByText('2').length).toBeGreaterThan(0)
    expect(screen.getAllByText('3').length).toBeGreaterThan(0)

    // Busiest hero card
    expect(screen.getByText(/Busiest Channel/i)).toBeInTheDocument()
  })

  it('renders new seen talkgroups badges and supports sub-tab filtering', async () => {
    const user = userEvent.setup()
    render(
      <MemoryRouter>
        <TalkgroupTrackerWidget
          data={mockTelemetry}
          dateFrom="2026-10-23"
          dateTo="2026-10-23"
        />
      </MemoryRouter>
    )

    // Check badges
    expect(screen.getByText('New')).toBeInTheDocument()
    expect(screen.getByText('vs Yest')).toBeInTheDocument()

    // Filter to "New to System"
    const newTabBtn = screen.getByRole('button', { name: /New to System/i })
    await user.click(newTabBtn)

    expect(screen.getByText('TAC_SPECIAL_OPS')).toBeInTheDocument()
    expect(screen.queryByText('FIRE_RESERVE')).not.toBeInTheDocument()
  })

  it('filters talkgroups via search input', async () => {
    const user = userEvent.setup()
    render(
      <MemoryRouter>
        <TalkgroupTrackerWidget
          data={mockTelemetry}
          dateFrom="2026-10-23"
          dateTo="2026-10-23"
        />
      </MemoryRouter>
    )

    const searchInput = screen.getByPlaceholderText('Filter channels...')
    await user.type(searchInput, 'SPECIAL')

    expect(screen.getByText('TAC_SPECIAL_OPS')).toBeInTheDocument()
    expect(screen.queryByText('FIRE_RESERVE')).not.toBeInTheDocument()
  })

  it('navigates to /search with filtered talkgroup and date range on click', async () => {
    mockNavigate.mockClear()
    const user = userEvent.setup()
    render(
      <MemoryRouter>
        <TalkgroupTrackerWidget
          data={mockTelemetry}
          dateFrom="2026-10-20"
          dateTo="2026-10-23"
        />
      </MemoryRouter>
    )

    const dispatchElements = screen.getAllByText('DISPATCH_NORTH')
    await user.click(dispatchElements[0])

    expect(mockNavigate).toHaveBeenCalledWith(
      '/search?date_from=2026-10-20&date_to=2026-10-23&talkgroup=DISPATCH_NORTH'
    )
  })

  it('works seamlessly through legacy TalkgroupShareWidget alias', () => {
    render(
      <MemoryRouter>
        <TalkgroupShareWidget
          trackerData={mockTelemetry}
          dateFrom="2026-10-23"
          dateTo="2026-10-23"
        />
      </MemoryRouter>
    )

    expect(screen.getByRole('heading', { level: 3, name: 'Talkgroup Intelligence & Tracker' })).toBeInTheDocument()
    expect(screen.getAllByText('DISPATCH_NORTH').length).toBeGreaterThan(0)
  })
})
