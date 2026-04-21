import { Hono } from 'hono'
import { cors } from 'hono/cors'
import { requestLogger } from './middleware/logger.js'
import analyseRoute from './routes/analyse.js'
import historyRoute from './routes/history.js'
import healthRoute from './routes/health.js'
import schedulerRoute from './routes/scheduler.js'
import { streamHandler } from './ws/stream.js'
import { startAnalysisCron } from './jobs/analysis-cron.js'

const app = new Hono()

app.use('*', cors({ origin: ['http://localhost:5173', 'http://localhost:3000'] }))
app.use('*', requestLogger)

// HTTP routes
app.route('/health', healthRoute)
app.route('/api/analyse', analyseRoute)
app.route('/api/history', historyRoute)
app.route('/api/scheduler', schedulerRoute)

// WebSocket proxy
app.get('/ws/stream', streamHandler)

const PORT = parseInt(process.env.PORT ?? '3000', 10)

startAnalysisCron()

export default {
  port: PORT,
  fetch: app.fetch,
}

console.log(`[Gateway] StockAI TypeScript gateway listening on port ${PORT}`)
