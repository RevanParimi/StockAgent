import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer } from 'recharts'

const VERDICT_COLORS: Record<string, string> = {
  'STRONG BUY':  '#22c55e',
  'BUY':         '#4ade80',
  'NEUTRAL':     '#f59e0b',
  'SELL':        '#f97316',
  'STRONG SELL': '#ef4444',
}

interface VerdictDonutProps {
  reports: Record<string, { score: number; verdict: string }>
}

export function VerdictDonut({ reports }: VerdictDonutProps) {
  const counts: Record<string, number> = {}
  Object.values(reports).forEach(({ verdict }) => {
    counts[verdict] = (counts[verdict] ?? 0) + 1
  })

  const data = Object.entries(counts).map(([verdict, count]) => ({ verdict, count }))

  if (data.length === 0) {
    return (
      <div className="flex items-center justify-center" style={{ height: 180 }}>
        <p className="text-sm text-[var(--text-muted)]">No data yet</p>
      </div>
    )
  }

  const dominant = data.reduce((a, b) => (a.count > b.count ? a : b))

  return (
    <div className="relative" style={{ height: 180 }}>
      <ResponsiveContainer width="100%" height="100%">
        <PieChart>
          <Pie
            data={data}
            dataKey="count"
            nameKey="verdict"
            innerRadius={52}
            outerRadius={76}
            paddingAngle={3}
            startAngle={90}
            endAngle={-270}
            isAnimationActive
          >
            {data.map((entry) => (
              <Cell
                key={entry.verdict}
                fill={VERDICT_COLORS[entry.verdict] ?? '#475569'}
                opacity={0.9}
              />
            ))}
          </Pie>
          <Tooltip
            contentStyle={{
              background: 'rgba(12,17,32,0.97)',
              border: '1px solid rgba(30,41,59,0.8)',
              borderRadius: 8,
              color: '#f1f5f9',
              fontSize: 12,
            }}
            formatter={(value, name) => [`${value} stock${value !== 1 ? 's' : ''}`, String(name)]}
          />
        </PieChart>
      </ResponsiveContainer>

      {/* Center label */}
      <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none">
        <span className="text-[9px] text-[var(--text-muted)] font-semibold tracking-[0.12em]">PORTFOLIO</span>
        <span className="text-[9px] text-[var(--text-muted)] font-semibold tracking-[0.12em] mb-1">BIAS</span>
        <span
          className="text-xs font-bold text-center leading-tight"
          style={{ color: VERDICT_COLORS[dominant.verdict] ?? '#f59e0b', maxWidth: 72 }}
        >
          {dominant.verdict}
        </span>
      </div>
    </div>
  )
}
