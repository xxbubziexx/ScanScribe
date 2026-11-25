import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MonitorDeleteModal } from '@/pages/Events/components/MonitorDeleteModal'
import { eventsApi } from '@/lib/events'
import type { MonitorResponse } from '@/types/events'

vi.mock('@/lib/events', () => ({
  eventsApi: {
    monitorDeleteImpact: vi.fn(),
  },
}))

const sampleMonitor: MonitorResponse = {
  id: 7,
  name: 'County Fire',
  enabled: true,
  talkgroup_ids: ['FIRE-DISP'],
  start_event_labels: ['EVT_TYPE'],
  geo_region: 'St. Francois County, MO',
  known_units: null,
}

function renderModal(props: Partial<React.ComponentProps<typeof MonitorDeleteModal>> = {}) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const onClose = vi.fn()
  const onConfirmDelete = vi.fn()
  const onDisableInstead = vi.fn()

  render(
    <QueryClientProvider client={qc}>
      <MonitorDeleteModal
        monitor={sampleMonitor}
        onClose={onClose}
        onConfirmDelete={onConfirmDelete}
        onDisableInstead={onDisableInstead}
        isDeleting={false}
        isDisabling={false}
        {...props}
      />
    </QueryClientProvider>,
  )
  return { onClose, onConfirmDelete, onDisableInstead }
}

describe('MonitorDeleteModal', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(eventsApi.monitorDeleteImpact).mockResolvedValue({
      monitor_id: 7,
      monitor_name: 'County Fire',
      events_count: 14,
      event_links_count: 38,
      span_store_count: 420,
      entity_observations_count: 1050,
      total_dependent_rows: 1522,
    })
  })

  it('shows exact cascade row counts and requires typing the monitor name to unlock Delete', async () => {
    const { onConfirmDelete } = renderModal()

    expect(await screen.findByText('1,522 total rows')).toBeInTheDocument()
    expect(screen.getByText('14')).toBeInTheDocument()
    expect(screen.getByText('38')).toBeInTheDocument()
    expect(screen.getByText('420')).toBeInTheDocument()
    expect(screen.getByText('1,050')).toBeInTheDocument()

    const deleteBtn = screen.getByRole('button', { name: 'Delete Monitor & Data' })
    expect(deleteBtn).toBeDisabled()

    const input = screen.getByLabelText(/confirm permanent deletion/i)
    fireEvent.change(input, { target: { value: 'Wrong Name' } })
    expect(deleteBtn).toBeDisabled()

    fireEvent.change(input, { target: { value: 'County Fire' } })
    expect(deleteBtn).toBeEnabled()

    fireEvent.click(deleteBtn)
    expect(onConfirmDelete).toHaveBeenCalledWith(7)
  })

  it('offers Disable Monitor Instead when the monitor is currently enabled', async () => {
    const { onDisableInstead } = renderModal()
    const disableBtn = await screen.findByRole('button', { name: 'Disable Monitor Instead' })
    fireEvent.click(disableBtn)
    expect(onDisableInstead).toHaveBeenCalledWith(sampleMonitor)
  })
})
