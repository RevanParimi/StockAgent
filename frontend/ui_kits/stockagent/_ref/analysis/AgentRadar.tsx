import { useState, useEffect } from 'react'
import {
  RadarChart,
  Radar,
  PolarGrid,
  PolarAngleAxis,
  PolarRadiusAxis,
  Tooltip,
  ResponsiveContainer,
} from 'recharts'
import type { FinalReport } from '@/types'
import { AGENT_LABELS } from '@/types'

interface AgentRadarProps {
  report: FinalReport
}

interface RadarDatum {
  agent: string
  label: string
  weighted: number
  raw: number
  weight: number
}

// Custom tooltip
function CustomTooltip({ active, payload }: { active?: boolean; payload?: { payload: RadarDatum }[] }) {
  if (!active || !payload?.length) return null
  const d = payload[0].payload
  return (
    <div className="glass-card p-3 text-xs space-y-1 min-w-[160px]">
      <p className="font-semibold text-[var(--text-primary)] mb-2">{d.label}</p>
      <div className="flex justify-between gap-4">
        <span className="text-[var(--text-muted)]">Raw</span>
        <span className="font-mono text-[var(--text-secondary)]">{d.raw.toFixed(2)}</span>
      </div>
      <div className="flex justify-between gap-4">
        <span className="text-[var(--text-muted)]">Weight</span>
        <span className="font-mono text-[var(--text-secondary)]">{(d.weight * 100).toFixed(0)}%</span>
      </div>
      <div className="flex justify-between gap-4">
        <span className="text-[var(--text-muted)]">Weighted</span>
        <span className="font-mono text-[var(--accent-cyan)]">{d.weighted.toFixed(3)}</span>
      </div>
    </div>
  )
}

export function AgentRadar({ report }: AgentRadarProps) {
  const [animated, setAnimated] = useState(false)

  useEffect(() => {
    const t = setTimeout(() => setAnimated(true), 100)
    return () => clearTimeout(t)
  }, [])

  const data: RadarDatum[] = Object.entries(report.weighted_agent_scores).map(
    ([key, detail]) => ({
      agent: key,
      label: AGENT_LABELS[key] ?? key,
      weighted: animated ? detail.weighted : 0,
      raw: detail.raw,
      weight: detail.weight,
    })
  )

  return (
    <div className="w-full" style={{ height: 340 }}>
      <ResponsiveContainer width="100%" height="100%">
        <RadarChart data={data} margin={{ top: 20, right: 30, bottom: 20, left: 30 }}>
          <PolarGrid
            stroke="rgba(255,255,255,0.08)"
            gridType="polygon"
          />
          <PolarAngleAxis
            dataKey="label"
            tick={{
              fill: 'var(--text-muted)',
              fontSize: 11,
              fontWeight: 500,
            }}
          />
          <PolarRadiusAxis
            angle={90}
            domain={[0, 0.25]}
            tick={false}
            axisLine={false}
          />
          <Radar
            name="Weighted Score"
            dataKey="weighted"
            stroke="#06b6d4"
            fill="rgba(6,182,212,0.15)"
            strokeWidth={2}
            dot={{ fill: '#06b6d4', r: 3, strokeWidth: 0 }}
            isAnimationActive={true}
            animationBegin={0}
            animationDuration={1000}
            animationEasing="ease-out"
          />
          <Tooltip content={<CustomTooltip />} />
        </RadarChart>
      </ResponsiveContainer>
    </div>
  )
}
