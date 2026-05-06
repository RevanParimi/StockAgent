/**
 * TypeScript mirror of backend Pydantic schemas.
 * Source of truth: src/backend/shared/schemas/pipeline.py + feedback.py
 * Keep in sync when backend schemas change.
 */

// ── Analysis Pipeline ─────────────────────────────────────────────────────

export type Verdict =
  | 'STRONG BUY'
  | 'BUY'
  | 'NEUTRAL'
  | 'SELL'
  | 'STRONG SELL'

export type Sector =
  | 'automobile'
  | 'banking_bfsi'
  | 'it_sector'
  | 'renewable_energy'

export interface WeightedAgentScore {
  raw:      number   // 0.0–1.0
  weight:   number   // 0.0–1.0
  weighted: number   // raw × weight
}

export interface AgentOutput {
  agent:         string
  ticker:        string
  overall_score: number
  key_positives: string[]
  key_risks:     string[]
  summary:       string
  data_freshness: string
  error?:        string | null
}

export interface FinalReport {
  ticker:          string
  company_name:    string
  final_score:     number   // 0.0–1.0
  verdict:         Verdict

  weighted_agent_scores: Record<string, WeightedAgentScore>
  conflicts_resolved:    string[]
  conviction_drivers:    string[]
  top_risks:             string[]

  /** 1-2 plain-English sentences for beginners */
  executive_summary:   string
  investment_thesis:   string
  report_date:         string

  // Valuation fields (from valuation_catalyst agent)
  price_target?:                  number | null
  recovery_timeline_quarters?:    number | null
  undervalued_by_pct?:            number | null
  discount_reason?:               string | null
  recovery_catalysts:             string[]

  agent_outputs: Record<string, Record<string, unknown>>
}

// ── WebSocket stream events ───────────────────────────────────────────────

export type StreamEvent =
  | { event: 'agent_progress'; agent: string; score: number }
  | { event: 'complete';       report: FinalReport }
  | { event: 'error';          detail: string }

// ── Analyse request ───────────────────────────────────────────────────────

export interface AnalyseRequest {
  ticker:        string
  sector?:       Sector   // optional override; auto-detected if omitted
  output_format?: 'json'
}

// ── UI data endpoints ─────────────────────────────────────────────────────

export interface TickerRow {
  sym:     string
  name:    string
  price:   number
  change:  number   // day % change
  score:   number   // latest composite score
  verdict: Verdict
  trend:   'up' | 'down' | 'flat'
  hasData: boolean  // true if at least one analysis run exists
}

export interface AgentMeta {
  key:      string
  name:     string
  icon:     string
  beginner: string   // plain-English description
  desc:     string   // technical description
  weight:   number
  enabled:  boolean
  sources:  string[]
}

export interface CategoryItem {
  key:     string
  icon:    string
  label:   string
  count:   number
  color:   string
  tickers: string[]
}

export interface TrendingItem {
  sym:       string
  name:      string
  score:     number
  delta:     number
  verdict:   Verdict
  direction: 'up' | 'down' | 'flat'
  why:       string
  runAt:     string
}

export interface SuggestionItem {
  sym:    string
  reason: string
  score:  number
  why:    string
}

export interface MarketPulse {
  pulse:       string
  oneLiner:    string
  autoChange:  number
  drivers:     DriverCard[]
  sectorChange: SectorChange[]
  freshness:   Freshness
}

export interface DriverCard {
  kind:    'good' | 'bad' | 'mid'
  label:   string
  impact:  string
  tickers: string[]
}

export interface SectorChange {
  name: string
  pct:  number
}

export interface Freshness {
  label: string
  runAt: string | null
  isStale: boolean
}

export interface BootstrapData {
  AGENTS:           AgentMeta[]
  TICKERS:          TickerRow[]
  WATCHLIST:        string[]
  MARKET_TODAY:     MarketPulse
  MARKET_MONTH:     MarketPulse
  NIFTY_AUTO_HISTORY: number[]
  TRENDING:         TrendingItem[]
  SUGGESTIONS:      SuggestionItem[]
  CATEGORIES:       CategoryItem[]
  CHAT_SEEDS:       string[]
  AGENT_TASK_FLAGS: Record<string, Record<string, boolean>>
  _liveData:        boolean
  _fetchedAt:       string
}

// ── History ───────────────────────────────────────────────────────────────

export interface HistoryEntry {
  id:               number
  ticker:           string
  company_name:     string
  run_at:           string
  final_score:      number
  verdict:          Verdict
  investment_thesis: string
  agent_scores?:    Record<string, number>
}

// ── Chat ──────────────────────────────────────────────────────────────────

export interface ChatMessage {
  role:    'user' | 'assistant'
  content: string
}

export interface ChatRequest {
  message: string
  history: ChatMessage[]
}

export interface ChatResponse {
  reply: string
}

// ── Sector registry ───────────────────────────────────────────────────────

export const SECTOR_TICKERS: Record<Sector, string[]> = {
  automobile:       ['MARUTI','TATAMOTORS','M&M','BAJAJ-AUTO','HEROMOTOCO','EICHERMOT','TVSMOTORS','ASHOKLEY'],
  banking_bfsi:     ['HDFCBANK','ICICIBANK','SBIN','KOTAKBANK','AXISBANK','INDUSINDBK','BANKBARODA'],
  it_sector:        ['TCS','INFY','WIPRO','HCLTECH','TECHM','LTIM','COFORGE','MPHASIS'],
  renewable_energy: ['ADANIGREEN','TATAPOWER','TORNTPOWER','CESC','SJVN','NHPC'],
}

export function detectSector(ticker: string): Sector {
  const t = ticker.toUpperCase()
  for (const [sector, tickers] of Object.entries(SECTOR_TICKERS)) {
    if (tickers.includes(t)) return sector as Sector
  }
  return 'automobile'
}
