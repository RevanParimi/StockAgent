/**
 * useAgentProgress — derives per-agent display state from the analysisStore.
 * Returns a sorted list of agents with their completion status and score.
 */

import { useMemo } from 'react'
import { useAnalysisStore } from '@/stores/analysisStore'

export interface AgentDisplayState {
  key:       string
  label:     string
  icon:      string
  weight:    number
  done:      boolean
  score:     number | null
  isRunning: boolean   // true only for the 'current' in-flight agent (best-effort)
}

// Default agent metadata — kept in sync with backend AGENT_META
const AGENT_META: Omit<AgentDisplayState, 'done' | 'score' | 'isRunning'>[] = [
  { key: 'sales_demand',       label: 'Sales & Demand',      icon: '📊', weight: 0.15 },
  { key: 'fundamentals',       label: 'Fundamentals',         icon: '📈', weight: 0.18 },
  { key: 'pattern_analysis',   label: 'Pattern Analysis',     icon: '🔍', weight: 0.11 },
  { key: 'raw_materials',      label: 'Raw Materials',        icon: '⚙️', weight: 0.09 },
  { key: 'sentiment',          label: 'Sentiment',            icon: '💬', weight: 0.04 },
  { key: 'policy_regulatory',  label: 'Policy & Regulatory',  icon: '📋', weight: 0.09 },
  { key: 'competitive_intel',  label: 'Competitive Intel',    icon: '🎯', weight: 0.09 },
  { key: 'risk_macro',         label: 'Risk & Macro',         icon: '⚠️', weight: 0.13 },
  { key: 'valuation_catalyst', label: 'Valuation & Catalyst', icon: '💎', weight: 0.12 },
]

export function useAgentProgress() {
  const { agentProgress, phase } = useAnalysisStore()
  const completedKeys = Object.keys(agentProgress)

  return useMemo<AgentDisplayState[]>(() =>
    AGENT_META.map(meta => ({
      ...meta,
      done:      completedKeys.includes(meta.key),
      score:     agentProgress[meta.key] ?? null,
      isRunning: phase === 'running' && !completedKeys.includes(meta.key),
    })),
    [agentProgress, phase, completedKeys.length]
  )
}
