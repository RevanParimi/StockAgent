import { Hono } from 'hono'
import { getHistory, getLatest } from '../client/python.js'

const app = new Hono()

app.get('/:ticker', async (c) => {
  const ticker = c.req.param('ticker')
  const limitStr = c.req.query('limit') ?? '30'
  const limit = Math.min(Math.max(parseInt(limitStr, 10) || 30, 1), 200)
  try {
    const records = await getHistory(ticker, limit)
    return c.json(records)
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err)
    return c.json({ error: message }, 502)
  }
})

app.get('/:ticker/latest', async (c) => {
  const ticker = c.req.param('ticker')
  try {
    const record = await getLatest(ticker)
    return c.json(record)
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err)
    const status = message.includes('404') ? 404 : 502
    return c.json({ error: message }, status)
  }
})

export default app
