import { z } from 'zod'
import { FinalReportSchema } from './report.js'

export const StreamEventSchema = z.discriminatedUnion('event', [
  z.object({
    event: z.literal('agent_progress'),
    agent: z.string(),
    score: z.number(),
  }),
  z.object({
    event: z.literal('complete'),
    report: FinalReportSchema,
  }),
  z.object({
    event: z.literal('error'),
    detail: z.string(),
  }),
])

export type StreamEvent = z.infer<typeof StreamEventSchema>
