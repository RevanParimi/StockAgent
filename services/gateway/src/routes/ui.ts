/**
 * Gateway proxy routes for /api/ui/*
 *
 * Forwards all /api/ui/* requests straight to the Python API (:8001/ui/*).
 * Also proxies /api/chat → /ui/chat for the chat assistant.
 *
 * The prototype HTML is served directly from :8001/app/ — these routes
 * allow the TypeScript gateway (:3000) path to work as well for any
 * consumers that go through the gateway.
 */

import { Hono } from 'hono'

const BASE_URL = process.env.PYTHON_INTERNAL_URL ?? 'http://localhost:8001'

const app = new Hono()

/** Passthrough proxy: forward request body + query to Python and relay response. */
async function proxy(
  pythonPath: string,
  method: string,
  body?: string,
  contentType?: string,
): Promise<Response> {
  const opts: RequestInit = {
    method,
    headers: { 'Content-Type': contentType ?? 'application/json' },
  }
  if (body) opts.body = body
  const res = await fetch(`${BASE_URL}${pythonPath}`, opts)
  const data = await res.json().catch(() => ({}))
  return new Response(JSON.stringify(data), {
    status: res.status,
    headers: { 'Content-Type': 'application/json' },
  })
}

// GET /api/ui/bootstrap
app.get('/bootstrap', (c) => proxy('/ui/bootstrap', 'GET'))

// GET /api/ui/agents
app.get('/agents', (c) => proxy('/ui/agents', 'GET'))

// GET /api/ui/tickers
app.get('/tickers', (c) => proxy('/ui/tickers', 'GET'))

// GET /api/ui/market/summary
app.get('/market/summary', (c) => proxy('/ui/market/summary', 'GET'))

// POST /api/ui/chat
app.post('/chat', async (c) => {
  const body = await c.req.text()
  return proxy('/ui/chat', 'POST', body)
})

export default app
