/** TypeScript interfaces mirroring Python models/schemas.py (snake_case, matching model_dump()). */

export type Verdict = "STRONG BUY" | "BUY" | "NEUTRAL" | "SELL" | "STRONG SELL";

export interface WeightedAgentScore {
  raw: number;
  weight: number;
  weighted: number;
}

export interface FinalReport {
  ticker: string;
  company_name: string;
  final_score: number;          // [0.0, 1.0]
  verdict: Verdict;
  weighted_agent_scores: Record<string, WeightedAgentScore>;
  conflicts_resolved?: string[];
  conviction_drivers: string[];
  top_risks: string[];
  investment_thesis: string;
  report_date: string;          // ISO date string
}

export interface HistoryEntry {
  ticker: string;
  score: number;
  verdict: Verdict;
  report_date: string;
}

// ---------------------------------------------------------------------------
// WebSocket event shapes (emitted by api/routes/stream.py)
// ---------------------------------------------------------------------------

export interface ProgressEvent {
  event: "agent_progress";
  agent: string;
  score: number;
}

export interface CompleteEvent {
  event: "complete";
  report: FinalReport;
}

export interface ErrorEvent {
  event: "error";
  detail: string;
}

export type StreamEvent = ProgressEvent | CompleteEvent | ErrorEvent;

// ---------------------------------------------------------------------------
// C# scheduler status (Phase 4 — GET :5000/scheduler/status)
// ---------------------------------------------------------------------------

export interface SchedulerStatus {
  enabled: boolean;
  next_run?: string;   // ISO datetime
  last_run?: string;
  tickers: string[];
}
