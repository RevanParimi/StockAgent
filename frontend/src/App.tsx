import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { Dashboard }   from '@/pages/Dashboard'

/* Pages 2 & 3 — stubbed so routing doesn't crash; built next iteration */
function StockDetailStub() {
  return (
    <div className="min-h-screen flex items-center justify-center bg-brand-soft">
      <div className="card p-10 text-center">
        <div className="text-4xl mb-3">📈</div>
        <h1 className="text-lg font-bold text-slate-800 mb-1">Stock Detail</h1>
        <p className="text-sm text-slate-400">Coming next — Page 2</p>
      </div>
    </div>
  )
}
function AgentLensStub() {
  return (
    <div className="min-h-screen flex items-center justify-center bg-brand-soft">
      <div className="card p-10 text-center">
        <div className="text-4xl mb-3">⚙️</div>
        <h1 className="text-lg font-bold text-slate-800 mb-1">Agent Lenses</h1>
        <p className="text-sm text-slate-400">Coming next — Page 3</p>
      </div>
    </div>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/"              element={<Dashboard />} />
        <Route path="/stock/:ticker" element={<StockDetailStub />} />
        <Route path="/lenses"        element={<AgentLensStub />} />
        <Route path="*"              element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  )
}
