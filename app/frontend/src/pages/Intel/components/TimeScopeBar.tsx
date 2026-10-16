import { TimeRangePicker } from '@/components/ui/TimeRangePicker'
import type { TimeRangeValue } from '@/components/ui/timeRange'

interface TimeScopeBarProps {
  value: TimeRangeValue
  onChange: (next: TimeRangeValue) => void
  disabled?: boolean
}

export function TimeScopeBar({ value, onChange, disabled }: TimeScopeBarProps) {
  return (
    <div className="flex items-center justify-between gap-3 border-b border-[#222533] bg-[#0f111a] px-4 py-2">
      <span className="text-[11px] font-medium uppercase tracking-wider text-gray-500">
        Time scope
      </span>
      <TimeRangePicker value={value} onChange={onChange} disabled={disabled} />
    </div>
  )
}
