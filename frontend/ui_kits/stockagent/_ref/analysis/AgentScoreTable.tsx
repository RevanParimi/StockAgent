import { useState } from 'react'
import { ChevronUp, ChevronDown, ChevronsUpDown } from 'lucide-react'
import type { FinalReport } from '@/types'
import { AGENT_LABELS } from '@/types'

type SortKey = 'agent' | 'raw' | 'weight' | 'weighted'
type SortDir = 'asc' | 'desc'

interface Row {
  key: string
  label: string
  raw: number
  weight: number
  weighted: number
}

function rawColor(raw: number): string {
  if (raw >= 0.70) return '#22c55e'
  if (raw >= 0.45) return '#f59e0b'
  return '#ef4444'
}

function SortIcon({ col, sortKey, sortDir }: { col: SortKey; sortKey: SortKey; sortDir: SortDir }) {
  if (col !== sortKey) return <ChevronsUpDown size={13} className="opacity-40" />
  return sortDir === 'asc'
    ? <ChevronUp size={13} className="text-[var(--accent-cyan)]" />
    : <ChevronDown size={13} className="text-[var(--accent-cyan)]" />
}

interface AgentScoreTableProps {
  report: FinalReport
}

export function AgentScoreTable({ report }: AgentScoreTableProps) {
  const [sortKey, setSortKey] = useState<SortKey>('weighted')
  const [sortDir, setSortDir] = useState<SortDir>('desc')

  const rows: Row[] = Object.entries(report.weighted_agent_scores).map(([key, d]) => ({
    key,
    label: AGENT_LABELS[key] ?? key,
    raw: d.raw,
    weight: d.weight,
    weighted: d.weighted,
  }))

  function toggleSort(col: SortKey) {
    if (col === sortKey) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'))
    } else {
      setSortKey(col)
      setSortDir('desc')
    }
  }

  const sorted = [...rows].sort((a, b) => {
    const va: string | number = sortKey === 'agent' ? a.label : a[sortKey]
    const vb: string | number = sortKey === 'agent' ? b.label : b[sortKey]
    const la = typeof va === 'string' ? va.toLowerCase() : va
    const lb = typeof vb === 'string' ? vb.toLowerCase() : vb
    if (la < lb) return sortDir === 'asc' ? -1 : 1
    if (la > lb) return sortDir === 'asc' ? 1 : -1
    return 0
  })

  function Header({ col, label }: { col: SortKey; label: string }) {
    return (
      <th
        className="px-4 py-3 text-left text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wider cursor-pointer select-none hover:text-[var(--text-secondary)] transition-colors"
        onClick={() => toggleSort(col)}
      >
        <span className="flex items-center gap-1.5">
          {label}
          <SortIcon col={col} sortKey={sortKey} sortDir={sortDir} />
        </span>
      </th>
    )
  }

  return (
    <div className="glass-card overflow-hidden">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-[var(--border-color)]">
            <Header col="agent" label="Agent" />
            <Header col="raw" label="Raw Score" />
            <Header col="weight" label="Weight" />
            <Header col="weighted" label="Weighted" />
          </tr>
        </thead>
        <tbody>
          {sorted.map((row, i) => (
            <tr
              key={row.key}
              className={`border-b border-[rgba(255,255,255,0.04)] transition-colors hover:bg-[rgba(255,255,255,0.03)] ${
                i % 2 === 0 ? '' : 'bg-[rgba(255,255,255,0.02)]'
              }`}
            >
              <td className="px-4 py-3 text-[var(--text-secondary)] font-medium">
                {row.label}
              </td>
              <td
                className="px-4 py-3 font-mono font-semibold tabular-nums"
                style={{ color: rawColor(row.raw) }}
              >
                {row.raw.toFixed(2)}
              </td>
              <td className="px-4 py-3 font-mono text-[var(--text-muted)] tabular-nums">
                {(row.weight * 100).toFixed(0)}%
              </td>
              <td className="px-4 py-3 font-mono text-[var(--accent-cyan)] tabular-nums font-semibold">
                {row.weighted.toFixed(3)}
              </td>
            </tr>
          ))}
          {/* Totals row */}
          <tr className="border-t-2 border-[var(--border-color)] bg-[rgba(6,182,212,0.05)]">
            <td className="px-4 py-3 font-semibold text-[var(--text-primary)]">
              Composite
            </td>
            <td className="px-4 py-3" />
            <td className="px-4 py-3 font-mono text-[var(--text-muted)]">100%</td>
            <td
              className="px-4 py-3 font-mono font-bold tabular-nums text-lg"
              style={{ color: rawColor(report.final_score) }}
            >
              {report.final_score.toFixed(2)}
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  )
}
