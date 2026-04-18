import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ReferenceLine,
  ReferenceArea,
  ResponsiveContainer,
  Legend,
} from 'recharts'
import { format, parseISO } from 'date-fns'
import type { ScoreRecord } from '@/types'

// Up to 3 tickers, distinct colors
const TICKER_COLORS = ['#06b6d4', '#8b5cf6', '#f59e0b']

interface CompareChartProps {
  tickerRecords: { ticker: string; records: ScoreRecord[] }[]
}

// Merge records from multiple tickers onto shared date axis
function mergeRecords(
  tickerRecords: { ticker: string; records: ScoreRecord[] }[]
): Record<string, string | number>[] {
  const dateMap = new Map<string, Record<string, string | number>>()

  for (const { ticker, records } of tickerRecords) {
    for (const r of records) {
      const key = r.report_date
      if (!dateMap.has(key)) {
        dateMap.set(key, {
          date: key,
          dateLabel: format(parseISO(key), 'MMM dd'),
        })
      }
      const row = dateMap.get(key)!
      row[ticker] = r.final_score
    }
  }

  return Array.from(dateMap.values()).sort((a, b) =>
    String(a.date).localeCompare(String(b.date))
  )
}

interface TooltipPayload {
  name: string
  value: number
  color: string
}

function CustomTooltip({
  active,
  payload,
  label,
}: {
  active?: boolean
  payload?: TooltipPayload[]
  label?: string
}) {
  if (!active || !payload?.length) return null
  return (
    <div className="glass-card p-3 text-xs space-y-2">
      <p className="text-[var(--text-muted)] mb-1">{label}</p>
      {payload.map((p) => (
        <div key={p.name} className="flex items-center gap-2">
          <span
            className="inline-block w-2 h-2 rounded-full"
            style={{ background: p.color }}
          />
          <span className="font-mono font-bold" style={{ color: p.color }}>
            {p.name}:
          </span>
          <span className="font-mono text-[var(--text-primary)]">
            {typeof p.value === 'number' ? p.value.toFixed(2) : '—'}
          </span>
        </div>
      ))}
    </div>
  )
}

export function CompareChart({ tickerRecords }: CompareChartProps) {
  const data = mergeRecords(tickerRecords)

  return (
    <div style={{ height: 360 }}>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 10, right: 16, bottom: 0, left: 0 }}>
          {/* Verdict zone bands */}
          <ReferenceArea y1={0.75} y2={1.00} fill="#22c55e" fillOpacity={0.04} />
          <ReferenceArea y1={0.60} y2={0.75} fill="#06b6d4" fillOpacity={0.04} />
          <ReferenceArea y1={0.45} y2={0.60} fill="#f59e0b" fillOpacity={0.04} />
          <ReferenceArea y1={0.30} y2={0.45} fill="#f97316" fillOpacity={0.04} />
          <ReferenceArea y1={0.00} y2={0.30} fill="#ef4444" fillOpacity={0.04} />

          {[0.75, 0.60, 0.45, 0.30].map((y) => (
            <ReferenceLine
              key={y}
              y={y}
              stroke="rgba(255,255,255,0.10)"
              strokeDasharray="4 4"
            />
          ))}

          <XAxis
            dataKey="dateLabel"
            tick={{ fill: 'var(--text-muted)', fontSize: 11 }}
            axisLine={false}
            tickLine={false}
            interval="preserveStartEnd"
          />
          <YAxis
            domain={[0.2, 1]}
            tick={{ fill: 'var(--text-muted)', fontSize: 11 }}
            axisLine={false}
            tickLine={false}
            tickFormatter={(v) => v.toFixed(2)}
            width={42}
          />
          <Tooltip content={<CustomTooltip />} />
          <Legend
            wrapperStyle={{ paddingTop: 12 }}
            formatter={(value) => (
              <span style={{ color: 'var(--text-secondary)', fontSize: 12 }}>{value}</span>
            )}
          />

          {tickerRecords.map(({ ticker }, i) => (
            <Line
              key={ticker}
              type="monotone"
              dataKey={ticker}
              stroke={TICKER_COLORS[i % TICKER_COLORS.length]}
              strokeWidth={2}
              dot={false}
              activeDot={{ r: 5, strokeWidth: 0 }}
              connectNulls
              isAnimationActive={true}
              animationDuration={900}
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}
