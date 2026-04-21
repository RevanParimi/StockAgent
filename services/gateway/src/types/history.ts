import { z } from 'zod'

export const ScoreRecordSchema = z.object({
  id: z.number().int(),
  ticker: z.string(),
  company_name: z.string(),
  final_score: z.number().min(0).max(1),
  verdict: z.string(),
  report_date: z.string(),
})

export type ScoreRecord = z.infer<typeof ScoreRecordSchema>
