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

export function ActivityChart({ data, view, onHourClick }: ActivityChartProps) {
  const canClick = view === 'hourly' && !!onHourClick

  return (
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
            allowDecimals={false}
            tick={{ fill: 'rgba(255,255,255,0.5)', fontSize: 11 }}
            axisLine={false}
            tickLine={false}
            width={28}
          />
          <Tooltip
            contentStyle={{
              background: '#1a1d27',
              border: '1px solid rgba(255,255,255,0.1)',
              borderRadius: 8,
              color: '#e5e7eb',
              fontSize: 12,
            }}
            cursor={{ stroke: 'rgba(99,102,241,0.4)', strokeWidth: 1 }}
            formatter={(v) => [v, 'Transcriptions']}
            labelFormatter={(l) =>
              canClick ? `${l} — click to filter` : String(l)
            }
          />
          <Line
            type="monotone"
            dataKey="count"
            stroke="rgb(99,102,241)"
            strokeWidth={2}
            dot={{ fill: 'rgb(99,102,241)', r: 3 }}
            activeDot={{
              r: 6,
              fill: canClick ? 'rgb(234,179,8)' : 'rgb(99,102,241)',
              cursor: canClick ? 'pointer' : 'default',
            }}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}
