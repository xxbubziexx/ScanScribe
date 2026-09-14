import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
} from 'recharts'
import type { ActivityPoint, InsightsView } from '@/types/insights'

interface ActivityChartProps {
  data: ActivityPoint[]
  view: InsightsView
  onHourClick?: (hour: number) => void
}

function parseHourLabel(label: string): number | null {
  const m = label.match(/(\d+)\s*(AM|PM)/i)
  if (!m) return null
  let h = parseInt(m[1])
  const pm = m[2].toUpperCase() === 'PM'
  if (h === 12) h = pm ? 12 : 0
  else if (pm) h += 12
  return h
}

interface CustomTooltipProps {
  active?: boolean
  payload?: readonly any[]
  label?: string | number
  canClick?: boolean
}

function CustomTooltip({ active, payload, label, canClick }: CustomTooltipProps) {
  if (!active || !payload || !payload.length) return null
  const trans = payload.find((p) => p.dataKey === 'count')
  const evts = payload.find((p) => p.dataKey === 'events_count')

  return (
    <div
      style={{
        background: '#1a1d27',
        border: '1px solid rgba(255,255,255,0.1)',
        borderRadius: 8,
        color: '#e5e7eb',
        fontSize: 12,
        padding: '8px 12px',
        boxShadow: '0 10px 25px -5px rgba(0, 0, 0, 0.5)',
      }}
    >
      <div style={{ fontWeight: 600, color: '#d1d5db', marginBottom: 6, paddingBottom: 4, borderBottom: '1px solid rgba(255,255,255,0.08)' }}>
        {canClick ? `${label} — click to filter` : String(label)}
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 14 }}>
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, color: '#9ca3af' }}>
            <span style={{ width: 8, height: 8, borderRadius: '50%', backgroundColor: 'rgb(99,102,241)', display: 'inline-block' }} />
            Transcriptions:
          </span>
          <span style={{ fontWeight: 600, color: '#ffffff', fontVariantNumeric: 'tabular-nums' }}>
            {trans?.value ?? 0}
          </span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 14 }}>
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, color: '#fb923c', fontWeight: 500 }}>
            <span style={{ width: 8, height: 8, borderRadius: '50%', backgroundColor: '#f97316', display: 'inline-block' }} />
            Events:
          </span>
          <span style={{ fontWeight: 700, color: '#f97316', fontVariantNumeric: 'tabular-nums' }}>
            {evts?.value ?? 0}
          </span>
        </div>
      </div>
    </div>
  )
}

export function ActivityChart({ data, view, onHourClick }: ActivityChartProps) {
  const canClick = view === 'hourly' && !!onHourClick

  return (
    <div className="w-full">
      <div className="flex items-center justify-end gap-4 mb-2 pr-2 text-xs">
        <span className="inline-flex items-center gap-1.5 text-gray-400">
          <span className="h-2 w-2 rounded-full bg-indigo-500" />
          Transcriptions
        </span>
        <span className="inline-flex items-center gap-1.5 text-orange-400 font-medium">
          <span className="h-2 w-2 rounded-full bg-orange-500" />
          Events
        </span>
      </div>

      <div className="ss-chart">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart
            data={data}
            onClick={
              canClick
                ? (payload: { activeLabel?: string | number }) => {
                    if (payload?.activeLabel) {
                      const h = parseHourLabel(String(payload.activeLabel))
                      if (h !== null) onHourClick!(h)
                    }
                  }
                : undefined
            }
          >
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
            <XAxis
              dataKey="label"
              tick={{ fill: 'rgba(255,255,255,0.5)', fontSize: 11 }}
              axisLine={false}
              tickLine={false}
              interval="preserveStartEnd"
            />
            <YAxis
              yAxisId="left"
              allowDecimals={false}
              tick={{ fill: 'rgba(255,255,255,0.5)', fontSize: 11 }}
              axisLine={false}
              tickLine={false}
              width={28}
            />
            <YAxis
              yAxisId="right"
              orientation="right"
              allowDecimals={false}
              domain={[0, (dataMax: number) => Math.max(5, Math.ceil(dataMax * 1.15))]}
              tick={{ fill: 'rgba(249,115,22,0.85)', fontSize: 11 }}
              axisLine={false}
              tickLine={false}
              width={28}
            />
            <Tooltip
              content={(props) => <CustomTooltip {...props} canClick={canClick} />}
              cursor={{ stroke: 'rgba(99,102,241,0.4)', strokeWidth: 1 }}
            />
            <Line
              yAxisId="left"
              type="monotone"
              dataKey="count"
              name="Transcriptions"
              stroke="rgb(99,102,241)"
              strokeWidth={2}
              dot={{ fill: 'rgb(99,102,241)', r: 3 }}
              activeDot={{
                r: 6,
                fill: canClick ? 'rgb(234,179,8)' : 'rgb(99,102,241)',
                cursor: canClick ? 'pointer' : 'default',
              }}
            />
            <Line
              yAxisId="right"
              type="monotone"
              dataKey="events_count"
              name="Events"
              stroke="#f97316"
              strokeWidth={2}
              dot={{ fill: '#f97316', r: 3 }}
              activeDot={{
                r: 6,
                fill: '#ea580c',
                stroke: '#ffedd5',
                strokeWidth: 2,
                cursor: canClick ? 'pointer' : 'default',
              }}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}

