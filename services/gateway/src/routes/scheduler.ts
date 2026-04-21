import { Hono } from 'hono'
import { getSchedulerStatus, triggerNow, tickers } from '../jobs/analysis-cron.js'

const app = new Hono()

app.get('/status', (c) => {
  return c.json(getSchedulerStatus())
})

app.post('/run-now', (c) => {
  triggerNow()
  return c.json({
    triggered: true,
    tickers,
    message: `Analysis triggered for ${tickers.length} ticker(s)`,
  })
})

export default app
