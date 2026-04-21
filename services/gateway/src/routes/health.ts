import { Hono } from 'hono'
import { getHealth } from '../client/python.js'

const app = new Hono()

app.get('/', async (c) => {
  let pythonStatus: string
  let pythonOk: boolean
  try {
    const h = await getHealth()
    pythonStatus = h.status
    pythonOk = true
  } catch {
    pythonStatus = 'unreachable'
    pythonOk = false
  }

  return c.json(
    {
      status: pythonOk ? 'ok' : 'degraded',
      gateway: 'ok',
      python: pythonStatus,
      timestamp: new Date().toISOString(),
    },
    pythonOk ? 200 : 503,
  )
})

export default app
