import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { RangeCalendar } from '@/components/ui/RangeCalendar'
import { TimeRangePicker } from '@/components/ui/TimeRangePicker'
import { DatabaseDateRangePicker } from '@/components/database/DatabaseDateRangePicker'
import { DatabaseDateSinglePicker } from '@/components/database/DatabaseDateSinglePicker'
import type { TimeRangeValue } from '@/components/ui/timeRange'
import { clearSavedDateRange, getSavedDateRange, saveDateRange } from '@/lib/dateSelection'

describe('RangeCalendar component', () => {
  it('renders days and completes range selection across two clicks', async () => {
    const user = userEvent.setup()
    const handleRangeSelect = vi.fn()
    const testDate = new Date(2026, 9, 31) // October 31, 2026

    render(
      <RangeCalendar
        mode="range"
        from={new Date(2026, 9, 1)}
        to={new Date(2026, 9, 2)}
        maxDate={testDate}
        onRangeSelect={handleRangeSelect}
      />,
    )

    // Verify month and weekdays header
    expect(screen.getByText(/October 2026/i)).toBeInTheDocument()
    expect(screen.getByText('Su')).toBeInTheDocument()
    expect(screen.getByText('Mo')).toBeInTheDocument()

    // Click day 5 (start of new range)
    const day5 = screen.getByRole('button', { name: new RegExp(new Date(2026, 9, 5).toDateString(), 'i') })
    await user.click(day5)

    // Click day 12 (end of new range)
    const day12 = screen.getByRole('button', { name: new RegExp(new Date(2026, 9, 12).toDateString(), 'i') })
    await user.click(day12)

    expect(handleRangeSelect).toHaveBeenCalledWith(
      new Date(2026, 9, 5),
      new Date(2026, 9, 12),
    )
  })

  it('corrects inverted range selection when clicking later date then earlier date', async () => {
    const user = userEvent.setup()
    const handleRangeSelect = vi.fn()
    const testDate = new Date(2026, 9, 31)

    render(
      <RangeCalendar
        mode="range"
        from={null}
        to={null}
        maxDate={testDate}
        onRangeSelect={handleRangeSelect}
      />,
    )

    // Click day 20 first, then day 10
    const day20 = screen.getByRole('button', { name: new RegExp(new Date(2026, 9, 20).toDateString(), 'i') })
    const day10 = screen.getByRole('button', { name: new RegExp(new Date(2026, 9, 10).toDateString(), 'i') })
    await user.click(day20)
    await user.click(day10)

    expect(handleRangeSelect).toHaveBeenCalledWith(
      new Date(2026, 9, 10),
      new Date(2026, 9, 20),
    )
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

  it('allows clicking two days on calendar to immediately set absolute range', async () => {
    const user = userEvent.setup()
    const handleChange = vi.fn()
    const val: TimeRangeValue = { kind: 'preset', presetId: 'today' }

    render(<TimeRangePicker value={val} onChange={handleChange} />)

    await user.click(screen.getByRole('button', { name: /today/i }))

    // Click day 5 then day 10
    const day5 = screen.getByRole('button', { name: new RegExp(new Date(2026, 9, 5).toDateString(), 'i') })
    const day10 = screen.getByRole('button', { name: new RegExp(new Date(2026, 9, 10).toDateString(), 'i') })
    await user.click(day5)
    await user.click(day10)

    expect(handleChange).toHaveBeenCalled()
    const lastCall = handleChange.mock.calls[handleChange.mock.calls.length - 1][0]
    expect(lastCall.kind).toBe('absolute')
    expect(lastCall.from.getDate()).toBe(5)
    expect(lastCall.to.getDate()).toBe(10)
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

  it('immediately triggers onChange when two days are clicked on the calendar', async () => {
    const user = userEvent.setup()
    const handleChange = vi.fn()

    render(
      <DatabaseDateRangePicker
        from=""
        to=""
        onChange={handleChange}
        activeDates={[]}
      />,
    )

    await user.click(screen.getByRole('button', { name: /date range/i }))

    // Click day 3 then day 8
    const day3 = screen.getByRole('button', { name: new RegExp(new Date(2026, 9, 3).toDateString(), 'i') })
    const day8 = screen.getByRole('button', { name: new RegExp(new Date(2026, 9, 8).toDateString(), 'i') })
    await user.click(day3)
    await user.click(day8)

    expect(handleChange).toHaveBeenCalledWith('2026-10-03', '2026-10-08')
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

describe('Persistent Date Range logic', () => {
  it('saves, retrieves, and clears date range in localStorage', () => {
    localStorage.clear()
    expect(getSavedDateRange()).toBeNull()

    saveDateRange('2026-10-10', '2026-10-15')
    const saved = getSavedDateRange()
    expect(saved).toEqual({ dateFrom: '2026-10-10', dateTo: '2026-10-15' })

    clearSavedDateRange()
    expect(getSavedDateRange()).toBeNull()
  })
})
