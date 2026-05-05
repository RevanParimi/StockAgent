import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ReferenceLine,
  ReferenceArea,
  ResponsiveContainer,
  Dot,
} from 'recharts'
import { format, parseISO } from 'date-fns'
import type { ScoreRecord } from '@/types'

interface HistoryLineProps {
  ticker: string
  records: ScoreRecord[]
}

function verdictForScore(score: number): string {
  if (score >= 0.75) return 'STRONG BUY'
  if (score >= 0.60) return 'BUY'
  if (score >= 0.45) return 'NEUTRAL'
  if (score >= 0.30) return 'SELL'
  return 'STRONG SELL'
}

function scoreStroke(score: number): string {
  if (score >= 0.75) return '#22c55e'
  if (score >= 0.60) return '#06b6d4'
  if (score >= 0.45) return '#f59e0b'
  if (score >= 0.30) return '#f97316'
  return '#ef4444'
}

interface TooltipPayloadItem {
  payload: ScoreRecord
  value: number
}

function CustomTooltip({
  active,
  payload,
}: {
  active?: boolean
  payload?: TooltipPayloadItem[]
}) {
  if (!active || !payload?.length) return null
  const d = payload[0].payload
  const score = payload[0].value
  const dateStr = d.report_date
    ? format(parseISO(d.report_date), 'MMM dd, yyyy')
    : d.report_date
  const verdict = verdictForScore(score)
  return (
    <div className="glass-card p-3 text-xs space-y-1">
      <p className="text-[var(--text-muted)]">{dateStr}</p>
      <p className="font-mono font-bold text-base" style={{ color: scoreStroke(score) }}>
        {score.toFixed(2)}
      </p>
      <p className="font-semibold" style={{ color: scoreStroke(score) }}>
        {verdict}
      </p>
    </div>
  )
}

// Custom dot colored by score
// eslint-disable-next-line @typescript-eslint/no-explicit-any
function ScoreDot(props: any) {
  const { cx, cy, payload } = props
  const color = scoreStroke(payload.final_score)
  return <Dot cx={cx} cy={cy} r={4} fill={color} stroke="var(--bg-card)" strokeWidth={1.5} />
}

export function HistoryLine({ ticker, records }: HistoryLineProps) {
  // Sort ascending by date
  const sorted = [...records].sort(
    (a, b) => new Date(a.report_date).getTime() - new Date(b.report_date).getTime()
  )

  const data = sorted.map((r) => ({
    ...r,
    dateLabel: format(parseISO(r.report_date), 'MMM dd'),
  }))

  return (
    <div className="glass-card p-5">
      <h3 className="text-lg font-semibold text-[var(--text-primary)] mb-5">
        Score History —{' '}
        <span className="text-[var(--accent-cyan)] font-mono">{ticker}</span>
        {' · '}
        <span className="text-[var(--text-muted)] text-sm font-normal">Last 90 Days</span>
      </h3>

      <div style={{ height: 260 }}>
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ top: 10, right: 16, bottom: 0, left: 0 }}>
            {/* Verdict zone bands */}
            <ReferenceArea y1={0.75} y2={1.00} fill="#22c55e" fillOpacity={0.05} />
            <ReferenceArea y1={0.60} y2={0.75} fill="#06b6d4" fillOpacity={0.05} />
            <ReferenceArea y1={0.45} y2={0.60} fill="#f59e0b" fillOpacity={0.05} />
            <ReferenceArea y1={0.30} y2={0.45} fill="#f97316" fillOpacity={0.05} />
            <ReferenceArea y1={0.00} y2={0.30} fill="#ef4444" fillOpacity={0.05} />

            {/* Zone reference lines */}
            {[0.75, 0.60, 0.45, 0.30].map((y) => (
              <ReferenceLine
                key={y}
                y={y}
                stroke="rgba(255,255,255,0.12)"
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
            <Line
              type="monotone"
              dataKey="final_score"
              stroke="#06b6d4"
              strokeWidth={2}
              dot={<ScoreDot />}
              activeDot={{ r: 6, fill: '#06b6d4', stroke: 'var(--bg-card)', strokeWidth: 2 }}
              isAnimationActive={true}
              animationDuration={1000}
              animationEasing="ease-out"
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}
