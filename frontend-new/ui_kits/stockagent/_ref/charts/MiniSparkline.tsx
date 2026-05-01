import { useId } from 'react'
import { AreaChart, Area, ResponsiveContainer } from 'recharts'

const VERDICT_COLOR: Record<string, string> = {
  'STRONG BUY':  '#22c55e',
  'BUY':         '#4ade80',
  'NEUTRAL':     '#f59e0b',
  'SELL':        '#f97316',
  'STRONG SELL': '#ef4444',
}

interface MiniSparklineProps {
  data: { score: number }[]
  verdict?: string
  height?: number
}

export function MiniSparkline({ data, verdict = 'NEUTRAL', height = 40 }: MiniSparklineProps) {
  const uid   = useId()
  const color = VERDICT_COLOR[verdict] ?? '#06b6d4'
  const gradId = `spark-${uid.replace(/:/g, '')}`

  if (!data || data.length < 2) return <div style={{ height }} />

  return (
    <div style={{ height, width: '100%' }}>
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data} margin={{ top: 2, right: 0, bottom: 2, left: 0 }}>
          <defs>
            <linearGradient id={gradId} x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%"  stopColor={color} stopOpacity={0.45} />
              <stop offset="95%" stopColor={color} stopOpacity={0} />
            </linearGradient>
          </defs>
          <Area
            type="monotone"
            dataKey="score"
            stroke={color}
            strokeWidth={1.5}
            fill={`url(#${gradId})`}
            isAnimationActive={false}
            dot={false}
            activeDot={false}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  )
}
