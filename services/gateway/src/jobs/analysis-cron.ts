import cron from 'node-cron'
import { postAnalyse } from '../client/python.js'

const CRON_EXPR = process.env.SCHEDULER_CRON ?? '30 8 * * 1-5'
const TICKERS_RAW = process.env.SCHEDULER_TICKERS ?? 'MARUTI,TATAMOTORS,M&M,HEROMOTOCO,BAJAJ-AUTO'
const ENABLED = (process.env.SCHEDULER_ENABLED ?? 'true') === 'true'

export const tickers: string[] = TICKERS_RAW.split(',')
  .map((t) => t.trim())
  .filter(Boolean)

let task: cron.ScheduledTask | null = null
let isRunning = false
let nextFireTime: string | null = null

async function runAnalysis(triggerSource: 'cron' | 'manual'): Promise<void> {
  if (isRunning) {
    console.log('[Cron] Analysis already in progress — skipping')
    return
  }
  isRunning = true
  console.log(`[Cron] Analysis triggered (${triggerSource}) for: ${tickers.join(', ')}`)

  for (const ticker of tickers) {
    try {
      const report = await postAnalyse(ticker)
      console.log(
        `[Cron] ${ticker} done — score=${report.final_score.toFixed(3)} verdict=${report.verdict}`,
      )
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err)
      console.error(`[Cron] ${ticker} failed: ${message}`)
    }
  }

  isRunning = false
  console.log('[Cron] Analysis run complete')
}

function updateNextFireTime(): void {
  if (!task) return
  // node-cron doesn't expose next fire time directly; compute from cron expression
  // We store a human-readable approximation: next weekday 08:30 IST
  const now = new Date()
  const next = new Date(now)
  next.setHours(8, 30, 0, 0)
  // If past 8:30 today, move to next day
  if (now >= next) next.setDate(next.getDate() + 1)
  // Skip weekends
  while (next.getDay() === 0 || next.getDay() === 6) next.setDate(next.getDate() + 1)
  nextFireTime = next.toISOString()
}

export function startAnalysisCron(): void {
  if (!ENABLED) {
    console.log('[Cron] SCHEDULER_ENABLED=false — analysis cron not started')
    return
  }

  if (!cron.validate(CRON_EXPR)) {
    console.error(`[Cron] Invalid SCHEDULER_CRON expression: "${CRON_EXPR}"`)
    return
  }

  task = cron.schedule(
    CRON_EXPR,
    () => {
      runAnalysis('cron')
      updateNextFireTime()
    },
    { timezone: 'Asia/Kolkata' },
  )

  updateNextFireTime()
  console.log(
    `[Cron] Analysis job scheduled: cron="${CRON_EXPR}" tickers=${tickers.join(',')} nextFire=${nextFireTime}`,
  )
}

export function getSchedulerStatus() {
  return {
    isRunning,
    nextFireTime,
    tickers,
    jobName: 'automobile_agent_run',
  }
}

export function triggerNow(): void {
  runAnalysis('manual')
}
