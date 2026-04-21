// ─────────────────────────────────────────────────────────────────────────────
// API types — inferred from gateway Zod schemas (services/gateway/src/types/)
// Do NOT maintain these manually. Edit the Zod schemas in the gateway instead.
// ─────────────────────────────────────────────────────────────────────────────

export type Verdict = 'STRONG BUY' | 'BUY' | 'NEUTRAL' | 'SELL' | 'STRONG SELL'

export interface AgentScoreDetail {
  raw: number
  weight: number
  weighted: number
}

export interface FinalReport {
  ticker: string
  company_name: string
  final_score: number
  verdict: string
  weighted_agent_scores: Record<string, AgentScoreDetail>
  conviction_drivers: string[]
  top_risks: string[]
  conflicts_resolved: string[]
  investment_thesis: string
  report_date: string
  price_target?: number | null
  recovery_timeline_quarters?: number | null
  undervalued_by_pct?: number | null
  discount_reason?: string | null
  recovery_catalysts: string[]
  agent_outputs: Record<string, unknown>
}

export interface ScoreRecord {
  id: number
  ticker: string
  company_name: string
  final_score: number
  verdict: string
  report_date: string
}

export type StreamEvent =
  | { event: 'agent_progress'; agent: string; score: number }
  | { event: 'complete'; report: FinalReport }
  | { event: 'error'; detail: string }

export interface SchedulerStatus {
  isRunning: boolean
  nextFireTime: string | null
  tickers: string[]
  jobName: string
}

// ─────────────────────────────────────────────────────────────────────────────
// UI-only types (not part of the API contract)
// ─────────────────────────────────────────────────────────────────────────────

export interface User {
  name: string
  email: string
  tickers: string[]
  preferences: {
    dailyAnalysis: boolean
    scoreDropAlerts: boolean
    darkMode: boolean
  }
}

export type AgentState = 'pending' | 'analyzing' | 'complete' | 'error'

export interface AgentStreamState {
  state: AgentState
  score?: number
}

export interface StreamState {
  status: 'idle' | 'streaming' | 'complete' | 'error'
  agentStates: Record<string, AgentStreamState>
  completedCount: number
  elapsedSeconds: number
  error?: string
}

export type WatchlistMap = Record<string, string[]>

export const TICKERS = [
  'MARUTI',
  'TATAMOTORS',
  'M&M',
  'HEROMOTOCO',
  'BAJAJ-AUTO',
  'EICHERMOT',
  'TVSMOTORS',
  'ASHOKLEY',
  'ESCORTS',
  'FORCEMOT',
] as const

export type Ticker = (typeof TICKERS)[number]

export const TICKER_NAMES: Record<string, string> = {
  MARUTI:       'Maruti Suzuki India Ltd',
  TATAMOTORS:   'Tata Motors Ltd',
  'M&M':        'Mahindra & Mahindra Ltd',
  HEROMOTOCO:   'Hero MotoCorp Ltd',
  'BAJAJ-AUTO': 'Bajaj Auto Ltd',
  EICHERMOT:    'Eicher Motors Ltd',
  TVSMOTORS:    'TVS Motor Company Ltd',
  ASHOKLEY:     'Ashok Leyland Ltd',
  ESCORTS:      'Escorts Kubota Ltd',
  FORCEMOT:     'Force Motors Ltd',
}

export const AGENT_LABELS: Record<string, string> = {
  sales_demand:      'Sales & Demand',
  fundamentals:      'Fundamentals',
  pattern_analysis:  'Pattern Analysis',
  raw_materials:     'Raw Materials',
  sentiment:         'Sentiment',
  policy_regulatory: 'Policy & Regulatory',
  competitive_intel: 'Competitive Intel',
  risk_macro:        'Risk & Macro',
}
