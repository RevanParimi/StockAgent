export type Verdict =
  | 'STRONG BUY'
  | 'BUY'
  | 'NEUTRAL'
  | 'SELL'
  | 'STRONG SELL'

export interface WatchlistStock {
  ticker:     string
  company:    string
  score:      number
  verdict:    Verdict
  price:      number
  change:     number
  analysedAt: string
  prevScore?: number           // previous analysis score for trend
}

export interface SuggestedStock {
  ticker:   string
  company:  string
  score:    number
  verdict:  Verdict
  headline: string            // one-line reason
}

export interface MarketItem {
  label:  string
  value:  string
  change: number              // positive = up, negative = down
}

export interface HistoryPoint {
  date:    string             // 'Nov', 'Dec' …
  score:   number
  verdict: Verdict
}

export interface AgentLens {
  id:       string
  icon:     string
  name:     string
  weight:   number            // 0–1
  tasks:    string[]
  active:   boolean
  color:    string            // tailwind color class stem
}
