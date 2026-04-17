import axios, { AxiosInstance } from "axios";
import type { FinalReport, HistoryEntry, SchedulerStatus } from "../types/stockAgent";

const PYTHON_API = process.env.PYTHON_API_URL ?? "http://localhost:8000";
const CSHARP_API = process.env.CSHARP_API_URL ?? "http://localhost:5000";

// 180s: Python agent timeout (120s) + headroom
const ANALYSE_TIMEOUT_MS = 180_000;

function makePythonAxios(): AxiosInstance {
  return axios.create({ baseURL: PYTHON_API, timeout: 30_000 });
}

function makeCSharpAxios(): AxiosInstance {
  return axios.create({ baseURL: CSHARP_API, timeout: 5_000 });
}

export async function postAnalyse(ticker: string): Promise<FinalReport> {
  const client = axios.create({ baseURL: PYTHON_API, timeout: ANALYSE_TIMEOUT_MS });
  const res = await client.post<FinalReport>("/analyse", { ticker });
  return res.data;
}

export async function getHistory(ticker: string): Promise<HistoryEntry[]> {
  const res = await makePythonAxios().get<HistoryEntry[]>(`/history/${ticker}`);
  return res.data;
}

export async function getLatestHistory(ticker: string): Promise<HistoryEntry> {
  const res = await makePythonAxios().get<HistoryEntry>(`/history/${ticker}/latest`);
  return res.data;
}

export async function getSchedulerStatus(): Promise<SchedulerStatus> {
  const res = await makeCSharpAxios().get<SchedulerStatus>("/scheduler/status");
  return res.data;
}

export const PYTHON_WS_URL =
  (process.env.PYTHON_API_URL ?? "http://localhost:8000")
    .replace(/^http/, "ws") + "/ws/stream";
