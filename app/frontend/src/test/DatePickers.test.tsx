import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { RangeCalendar } from '@/components/ui/RangeCalendar'
import { TimeRangePicker } from '@/components/ui/TimeRangePicker'
import { DatabaseDateRangePicker } from '@/components/database/DatabaseDateRangePicker'
import { DatabaseDateSinglePicker } from '@/components/database/DatabaseDateSinglePicker'
import type { TimeRangeValue } from '@/components/ui/timeRange'

describe('RangeCalendar component', () => {
  it('renders days and fires onPick callback when clicking a day', async () => {
    const user = userEvent.setup()
    const handlePick = vi.fn()
    const testDate = new Date(2026, 9, 15) // October 15, 2026

    render(
      <RangeCalendar
        mode="range"
        from={new Date(2026, 9, 5)}
        to={new Date(2026, 9, 10)}
        maxDate={testDate}
        onPick={handlePick}
      />,
    )

    // Verify month and weekdays header
    expect(screen.getByText(/October 2026/i)).toBeInTheDocument()
    expect(screen.getByText('Su')).toBeInTheDocument()
    expect(screen.getByText('Mo')).toBeInTheDocument()

    // Find day button for Oct 5
    const dayBtn = screen.getByRole('button', { name: new RegExp(new Date(2026, 9, 5).toDateString(), 'i') })
    expect(dayBtn).toBeInTheDocument()
    await user.click(dayBtn)
    expect(handlePick).toHaveBeenCalled()
  })

  it('renders SQLite active dots for days with data', () => {
    const activeDates = new Set(['2026-10-05', '2026-10-12'])
    render(
      <RangeCalendar
        mode="single"
        selected={new Date(2026, 9, 5)}
        activeDateStrings={activeDates}
        onPick={() => {}}
      />,
    )

    expect(screen.getByText(/October 2026/i)).toBeInTheDocument()
  })
})

describe('TimeRangePicker component', () => {
  it('renders with default preset and opens popover', async () => {
    const user = userEvent.setup()
    const handleChange = vi.fn()
    const val: TimeRangeValue = { kind: 'preset', presetId: 'today' }

    render(<TimeRangePicker value={val} onChange={handleChange} />)

    // Trigger button should show "Today"
    const trigger = screen.getByRole('button', { name: /today/i })
    expect(trigger).toBeInTheDocument()

    // Click trigger to open popover
    await user.click(trigger)

    // Popover dialog should appear with presets
    expect(screen.getByRole('dialog', { name: /select time range/i })).toBeInTheDocument()
    expect(screen.getByText('Last 30 minutes')).toBeInTheDocument()
    expect(screen.getByText('Last 24 hours')).toBeInTheDocument()
    expect(screen.getByText('Absolute time range')).toBeInTheDocument()

    // Select a preset
    const presetBtn = screen.getByRole('button', { name: /last 6 hours/i })
    await user.click(presetBtn)
    expect(handleChange).toHaveBeenCalledWith({ kind: 'preset', presetId: '6h' })
  })
})

describe('DatabaseDateRangePicker component', () => {
  it('renders date range and allows selecting quick presets', async () => {
    const user = userEvent.setup()
    const handleChange = vi.fn()

    render(
      <DatabaseDateRangePicker
        from="2026-10-01"
        to="2026-10-07"
        onChange={handleChange}
        activeDates={['2026-10-01', '2026-10-02']}
      />,
    )

    // Trigger shows date range label and text
    const trigger = screen.getByRole('button', { name: /date range/i })
    expect(trigger).toBeInTheDocument()
    expect(screen.getByText(/2026-10-01 → 2026-10-07/i)).toBeInTheDocument()

    // Open popover
    await user.click(trigger)
    expect(screen.getByRole('dialog')).toBeInTheDocument()
    expect(screen.getByText('Today')).toBeInTheDocument()
    expect(screen.getByText('Last 7 days')).toBeInTheDocument()

    // Clear dates
    const clearBtn = screen.getByRole('button', { name: /^clear$/i })
    await user.click(clearBtn)
    expect(handleChange).toHaveBeenCalledWith('', '')
  })
})

describe('DatabaseDateSinglePicker component', () => {
  it('renders selected single date and opens calendar', async () => {
    const user = userEvent.setup()
    const handleChange = vi.fn()

    render(
      <DatabaseDateSinglePicker
        value="2026-10-15"
        onChange={handleChange}
        activeDates={['2026-10-15']}
      />,
    )

    const trigger = screen.getByRole('button', { name: /select date/i })
    expect(trigger).toBeInTheDocument()
    expect(screen.getByText(/Oct 15, 2026/i)).toBeInTheDocument()

    await user.click(trigger)
    expect(screen.getByRole('dialog')).toBeInTheDocument()

    // Today quick button exists in footer
    const todayBtn = screen.getByRole('button', { name: /^today$/i })
    expect(todayBtn).toBeInTheDocument()
    await user.click(todayBtn)
    expect(handleChange).toHaveBeenCalled()
  })
})
