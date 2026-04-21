import { z } from 'zod'

export const VerdictSchema = z.enum([
  'STRONG BUY',
  'BUY',
  'NEUTRAL',
  'SELL',
  'STRONG SELL',
])

export const AgentScoreDetailSchema = z.object({
  raw: z.number().min(0).max(1),
  weight: z.number().min(0).max(1),
  weighted: z.number().min(0).max(1),
})

export const FinalReportSchema = z.object({
  ticker: z.string(),
  company_name: z.string(),
  final_score: z.number().min(0).max(1),
  verdict: z.string(),
  weighted_agent_scores: z.record(z.string(), AgentScoreDetailSchema),
  conviction_drivers: z.array(z.string()),
  top_risks: z.array(z.string()),
  conflicts_resolved: z.array(z.string()).default([]),
  investment_thesis: z.string().default(''),
  report_date: z.string().default(''),
  price_target: z.number().nullable().optional(),
  recovery_timeline_quarters: z.number().int().nullable().optional(),
  undervalued_by_pct: z.number().nullable().optional(),
  discount_reason: z.string().nullable().optional(),
  recovery_catalysts: z.array(z.string()).default([]),
  agent_outputs: z.record(z.string(), z.unknown()).default({}),
})

export type Verdict = z.infer<typeof VerdictSchema>
export type AgentScoreDetail = z.infer<typeof AgentScoreDetailSchema>
export type FinalReport = z.infer<typeof FinalReportSchema>
