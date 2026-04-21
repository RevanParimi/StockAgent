import { z } from 'zod'

export const JobStatusSchema = z.object({
  jobName: z.string(),
  isRunning: z.boolean(),
  nextFireTime: z.string().nullable(),
  tickers: z.array(z.string()),
})

export const SchedulerStatusSchema = z.object({
  isRunning: z.boolean(),
  nextFireTime: z.string().nullable(),
  tickers: z.array(z.string()),
  jobName: z.string(),
})

export const RunNowResponseSchema = z.object({
  triggered: z.boolean(),
  tickers: z.array(z.string()),
  message: z.string(),
})

export type JobStatus = z.infer<typeof JobStatusSchema>
export type SchedulerStatus = z.infer<typeof SchedulerStatusSchema>
export type RunNowResponse = z.infer<typeof RunNowResponseSchema>
