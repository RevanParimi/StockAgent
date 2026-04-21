import { FinalReport, FinalReportSchema } from '../types/report.js'
import { ScoreRecord, ScoreRecordSchema } from '../types/history.js'

const BASE_URL = process.env.PYTHON_INTERNAL_URL ?? 'http://localhost:8001'

async function request<T>(path: string, opts?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    headers: { 'Content-Type': 'application/json', ...opts?.headers },
    ...opts,
  })
  if (!res.ok) {
    const body = await res.text().catch(() => '')
    throw new Error(`Python API ${opts?.method ?? 'GET'} ${path} → ${res.status}: ${body}`)
  }
  return res.json() as Promise<T>
}

export async function postAnalyse(ticker: string): Promise<FinalReport> {
  const raw = await request<unknown>('/analyse', {
    method: 'POST',
    body: JSON.stringify({ ticker }),
  })
  return FinalReportSchema.parse(raw)
}

export async function getHistory(ticker: string, limit = 30): Promise<ScoreRecord[]> {
  const raw = await request<unknown[]>(`/history/${encodeURIComponent(ticker)}?limit=${limit}`)
  return raw.map((r) => ScoreRecordSchema.parse(r))
}

export async function getLatest(ticker: string): Promise<ScoreRecord> {
  const raw = await request<unknown>(`/history/${encodeURIComponent(ticker)}/latest`)
  return ScoreRecordSchema.parse(raw)
}

export async function getHealth(): Promise<{ status: string }> {
  return request<{ status: string }>('/health')
}
