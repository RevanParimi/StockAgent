import { Hono } from 'hono'
import { postAnalyse } from '../client/python.js'

const app = new Hono()

app.post('/', async (c) => {
  const body = await c.req.json().catch(() => null)
  const ticker: string | undefined = body?.ticker
  if (!ticker || typeof ticker !== 'string') {
    return c.json({ error: 'ticker is required' }, 400)
  }
  try {
    const report = await postAnalyse(ticker.trim().toUpperCase())
    return c.json(report)
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err)
    return c.json({ error: message }, 502)
  }
})

export default app
