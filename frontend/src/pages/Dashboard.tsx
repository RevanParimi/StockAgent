import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Search, Bell, Plus, TrendingUp, TrendingDown, ChevronRight, Layers, Clock, Zap, AlertCircle } from 'lucide-react'
import { OracleOrb, type OrbState } from '@/sphere/OracleOrb'
import {
  WATCHLIST, SUGGESTED, MARKET_ITEMS, SPARKLINES,
  NIFTY_AUTO_WEEK, SECTORS, TOP_MOVERS, MARKET_MOOD,
  KPIS, BRIEFING, ALERTS,
  verdictPillClass, scoreFillClass, changeColor, changePrefix, scoreTrend,
} from '@/data/mockData'
import type { WatchlistStock, SuggestedStock } from '@/types'

/* ══ Portfolio stats ══ */
function useStats() {
  const c = { buy:0, neutral:0, sell:0 }
  WATCHLIST.forEach(s => {
    if (s.verdict==='STRONG BUY'||s.verdict==='BUY') c.buy++
    else if (s.verdict==='NEUTRAL') c.neutral++
    else c.sell++
  })
  return c
}

/* ══════════════════════════════════════
   REUSABLE: Inline SVG sparkline
══════════════════════════════════════ */
function Sparkline({ data, color, width=62, height=26 }: { data:number[]; color:string; width?:number; height?:number }) {
  if (!data || data.length < 2) return null
  const min = Math.min(...data), max = Math.max(...data)
  const range = max - min || 1
  const pts = data.map((v, i) => {
    const x = (i / (data.length - 1)) * width
    const y = height - ((v - min) / range) * (height - 4) - 2
    return `${x.toFixed(1)},${y.toFixed(1)}`
  }).join(' ')
  const firstY = parseFloat(pts.split(' ')[0].split(',')[1])
  const lastY  = parseFloat(pts.split(' ').slice(-1)[0].split(',')[1])
  const fill   = `${pts} ${width},${height} 0,${height}`
  return (
    <svg width={width} height={height} style={{ overflow:'visible' }}>
      <defs>
        <linearGradient id={`sg-${color.replace('#','')}`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.25"/>
          <stop offset="100%" stopColor={color} stopOpacity="0"/>
        </linearGradient>
      </defs>
      <polygon points={fill} fill={`url(#sg-${color.replace('#','')})`}/>
      <polyline points={pts} fill="none" stroke={color} strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"/>
      <circle cx={(data.length-1)/(data.length-1)*width} cy={lastY} r="2.5" fill={color}/>
    </svg>
  )
}

/* ══ MARKET TICKER ══ */
function MarketTicker() {
  const doubled = [...MARKET_ITEMS, ...MARKET_ITEMS]
  return (
    <div className="w-full bg-white/80 backdrop-blur border-b border-slate-100 py-2 overflow-hidden">
      <div className="ticker-track inline-flex">
        {doubled.map((item,i) => (
          <span key={i} className="inline-flex items-center gap-1.5 px-5 text-[11px] whitespace-nowrap border-r border-slate-100 text-slate-500 font-medium">
            <span className="text-slate-700 font-semibold">{item.label}</span>
            <span className="font-mono">{item.value}</span>
            <span className={`font-mono font-bold text-[10px] ${changeColor(item.change)}`}>{changePrefix(item.change)}{Math.abs(item.change)}%</span>
          </span>
        ))}
      </div>
    </div>
  )
}

/* ══ TOP BAR ══ */
function TopBar() {
  const navigate = useNavigate()
  return (
    <header className="topbar sticky top-0 z-50 px-6 h-14 flex items-center gap-4">
      <button onClick={()=>navigate('/')} className="flex items-center gap-2.5 shrink-0 mr-2">
        <div className="w-8 h-8 rounded-xl flex items-center justify-center shadow-sm" style={{background:'linear-gradient(135deg,#2563EB,#06B6D4)'}}>
          <span className="text-white font-black text-sm">S</span>
        </div>
        <span className="font-bold text-slate-800 tracking-tight">StockOracle</span>
      </button>
      <div className="flex-1 max-w-md relative">
        <Search size={13} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400"/>
        <input placeholder="Search stocks…  MARUTI, Tata Motors" className="w-full pl-8 pr-4 py-2 text-sm rounded-xl bg-slate-50 border border-slate-200 text-slate-700 focus:outline-none focus:border-blue-400 focus:ring-2 focus:ring-blue-100 placeholder:text-slate-400 transition-all"/>
      </div>
      <div className="ml-auto flex items-center gap-2.5">
        <button onClick={()=>navigate('/lenses')} className="hidden sm:flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold text-blue-600 bg-blue-50 hover:bg-blue-100 border border-blue-200 transition-all">
          <Layers size={13}/> Configure Lenses
        </button>
        <button onClick={()=>navigate('/stock/MARUTI')} className="flex items-center gap-1.5 px-4 py-1.5 rounded-lg text-xs font-semibold text-white shadow-sm transition-all hover:opacity-90" style={{background:'linear-gradient(135deg,#2563EB,#06B6D4)'}}>
          <TrendingUp size={13}/> Analyse
        </button>
        <button className="relative w-8 h-8 flex items-center justify-center rounded-lg hover:bg-slate-100 text-slate-500 transition-colors">
          <Bell size={15}/>
          <span className="absolute top-1.5 right-1.5 w-1.5 h-1.5 rounded-full bg-blue-500"/>
        </button>
        <div className="w-8 h-8 rounded-full flex items-center justify-center text-white text-xs font-bold cursor-pointer shadow-sm" style={{background:'linear-gradient(135deg,#7B5CF6,#2563EB)'}}>R</div>
      </div>
    </header>
  )
}

/* ══ MORNING BRIEFING ══ */
function BriefingCard() {
  return (
    <div className="card px-5 py-3.5 flex items-start gap-3" style={{background:'linear-gradient(135deg,rgba(37,99,235,0.06),rgba(6,182,212,0.04))'}}>
      <span className="text-xl shrink-0 mt-0.5">🧠</span>
      <div>
        <p className="text-[10px] font-bold text-blue-500 uppercase tracking-widest mb-1">Oracle Morning Briefing</p>
        <p className="text-sm text-slate-700 leading-relaxed">{BRIEFING}</p>
      </div>
    </div>
  )
}

/* ══ KPI STRIP ══ */
function KpiStrip() {
  return (
    <div className="grid grid-cols-4 gap-3">
      {KPIS.map(k => (
        <div key={k.label} className="card px-4 py-3 flex items-center gap-3">
          <span className="text-xl shrink-0">{k.icon}</span>
          <div>
            <p className="text-[10px] text-slate-400 font-medium uppercase tracking-wide">{k.label}</p>
            <p className="text-lg font-black leading-tight" style={{color:k.color}}>{k.value}</p>
            <p className="text-[10px] text-slate-400 mt-0.5">{k.sub}</p>
          </div>
        </div>
      ))}
    </div>
  )
}

/* ══ WATCHLIST ITEM — with sparkline + trend + alert ══ */
function WatchItem({ stock, onClick }: { stock:WatchlistStock; onClick:()=>void }) {
  const spark = SPARKLINES[stock.ticker]
  const trend = stock.prevScore != null ? scoreTrend(stock.score, stock.prevScore) : null
  const alert = ALERTS[stock.ticker]
  const sparkColor = (stock.verdict==='STRONG BUY'||stock.verdict==='BUY') ? '#16A34A' : stock.verdict==='NEUTRAL' ? '#D97706' : '#DC2626'

  return (
    <button onClick={onClick} className="card w-full text-left px-4 py-3 flex flex-col gap-2 group hover:border-blue-200">
      {/* Row 1: ticker + verdict + alert */}
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-1.5">
          <span className="font-bold font-mono text-slate-800 text-sm">{stock.ticker}</span>
          {alert && (
            <span title={alert} className="text-amber-500">
              <AlertCircle size={11}/>
            </span>
          )}
        </div>
        <div className="flex items-center gap-1.5">
          {trend && (
            <span className={`text-[10px] font-bold ${trend.up ? 'text-green-600' : 'text-red-500'}`}>
              {trend.up ? '↑' : '↓'}{Math.abs(trend.delta)}pts
            </span>
          )}
          <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full shrink-0 ${verdictPillClass(stock.verdict)}`}>
            {stock.verdict}
          </span>
        </div>
      </div>
      {/* Row 2: score bar + sparkline */}
      <div className="flex items-end gap-3">
        <div className="flex-1">
          <div className="flex items-center gap-2 mb-1.5">
            <div className="score-track flex-1">
              <div className={`score-fill ${scoreFillClass(stock.verdict)}`} style={{width:`${stock.score*100}%`}}/>
            </div>
            <span className="text-[10px] font-mono text-slate-400 w-4 text-right shrink-0">{Math.round(stock.score*100)}</span>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-[11px] font-semibold text-slate-700">₹{stock.price.toLocaleString()}</span>
            <span className={`text-[10px] font-mono font-bold ${changeColor(stock.change)}`}>{changePrefix(stock.change)}{Math.abs(stock.change)}%</span>
          </div>
        </div>
        {spark && <Sparkline data={spark} color={sparkColor}/>}
      </div>
    </button>
  )
}

/* ══ SUGGESTED ITEM ══ */
function SuggestItem({ s }: { s:SuggestedStock }) {
  return (
    <div className="card-flat px-3.5 py-3 flex items-center gap-3">
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 mb-1">
          <span className="font-bold font-mono text-slate-800 text-xs">{s.ticker}</span>
          <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded-full ${verdictPillClass(s.verdict)}`}>{s.verdict}</span>
        </div>
        <div className="score-track"><div className={`score-fill ${scoreFillClass(s.verdict)}`} style={{width:`${s.score*100}%`}}/></div>
        <p className="text-[10px] text-slate-400 mt-1 truncate">{s.headline}</p>
      </div>
      <button className="btn-cyan shrink-0 w-6 h-6 rounded-full flex items-center justify-center"><Plus size={11}/></button>
    </div>
  )
}

/* ══ PORTFOLIO DONUT ══ */
function PortfolioDonut({ buy, neutral, sell }: { buy:number; neutral:number; sell:number }) {
  const total=buy+neutral+sell||1, C=226
  const bA=(buy/total)*C, nA=(neutral/total)*C, sA=(sell/total)*C
  return (
    <div className="flex items-center gap-4">
      <svg width="76" height="76" viewBox="0 0 80 80">
        <circle cx="40" cy="40" r="36" fill="none" stroke="#E2E8F0" strokeWidth="8"/>
        <circle cx="40" cy="40" r="36" fill="none" stroke="#16A34A" strokeWidth="8" strokeDasharray={`${bA} ${C-bA}`} strokeDashoffset={C*0.25}/>
        <circle cx="40" cy="40" r="36" fill="none" stroke="#D97706" strokeWidth="8" strokeDasharray={`${nA} ${C-nA}`} strokeDashoffset={C*0.25-bA}/>
        <circle cx="40" cy="40" r="36" fill="none" stroke="#DC2626" strokeWidth="8" strokeDasharray={`${sA} ${C-sA}`} strokeDashoffset={C*0.25-bA-nA}/>
        <text x="40" y="44" textAnchor="middle" fontSize="13" fontWeight="800" fill="#1E293B">{total}</text>
      </svg>
      <div className="space-y-1.5 text-xs">
        <div className="flex items-center gap-2"><span className="w-2 h-2 rounded-full bg-green-600"/><span className="text-slate-600">{buy} BUY</span></div>
        <div className="flex items-center gap-2"><span className="w-2 h-2 rounded-full bg-amber-500"/><span className="text-slate-600">{neutral} NEUTRAL</span></div>
        <div className="flex items-center gap-2"><span className="w-2 h-2 rounded-full bg-red-600"/><span className="text-slate-600">{sell} SELL</span></div>
      </div>
    </div>
  )
}

/* ══ MARKET MOOD GAUGE ══ */
function MoodGauge() {
  const { score, label, prev } = MARKET_MOOD
  const delta = score - prev
  const pct   = score   // 0-100
  const color = score < 30 ? '#DC2626' : score < 45 ? '#F97316' : score < 55 ? '#D97706' : score < 70 ? '#16A34A' : '#059669'
  const bg    = `linear-gradient(90deg, #DC2626 0%, #F97316 20%, #D97706 40%, #16A34A 65%, #059669 100%)`
  return (
    <div>
      <div className="flex items-center justify-between mb-2">
        <h3 className="text-xs font-bold text-slate-600">Market Mood</h3>
        <span className="text-[10px] font-semibold" style={{color}}>
          {label} · {delta>0?'+':''}{delta} vs yesterday
        </span>
      </div>
      <div className="relative h-2.5 rounded-full overflow-hidden" style={{background:bg}}>
        <div className="absolute top-0 bottom-0 w-0.5 bg-white/90 rounded-full transition-all duration-700"
          style={{left:`calc(${pct}% - 1px)`}}/>
      </div>
      <div className="flex justify-between mt-1">
        <span className="text-[9px] text-slate-400">Fear</span>
        <span className="text-[9px] font-bold text-slate-700">{score}/100</span>
        <span className="text-[9px] text-slate-400">Greed</span>
      </div>
    </div>
  )
}

/* ══ NIFTY AUTO MINI CHART ══ */
function NiftyMiniChart() {
  const data  = NIFTY_AUTO_WEEK
  const first = data[0], last = data[data.length - 1]
  const up    = last >= first
  return (
    <div>
      <div className="flex items-center justify-between mb-2">
        <h3 className="text-xs font-bold text-slate-600">Nifty Auto — 7 days</h3>
        <span className={`text-[10px] font-bold ${up ? 'text-green-600':'text-red-500'}`}>
          {up?'▲':'▼'} {Math.abs(((last-first)/first)*100).toFixed(1)}%
        </span>
      </div>
      <Sparkline data={data} color={up?'#16A34A':'#DC2626'} width={220} height={38}/>
      <div className="flex justify-between mt-1">
        <span className="text-[9px] text-slate-400">Mon</span>
        <span className="text-[9px] text-slate-400">Today · {last.toLocaleString()}</span>
      </div>
    </div>
  )
}

/* ══ SECTOR HEATMAP ══ */
function SectorHeatmap() {
  return (
    <div>
      <h3 className="text-xs font-bold text-slate-600 mb-2.5">Sector Performance Today</h3>
      <div className="grid grid-cols-3 gap-1.5">
        {SECTORS.map(s => {
          const abs = Math.abs(s.change)
          const intensity = Math.min(abs / 2.5, 1)
          const bg = s.change >= 0
            ? `rgba(22,163,74,${0.08 + intensity * 0.22})`
            : `rgba(220,38,38,${0.08 + intensity * 0.22})`
          const border = s.change >= 0
            ? `rgba(22,163,74,${0.2 + intensity * 0.3})`
            : `rgba(220,38,38,${0.2 + intensity * 0.3})`
          return (
            <div key={s.name}
              className="rounded-xl px-2 py-2 text-center cursor-default transition-all hover:scale-105"
              style={{background:bg, border:`1px solid ${border}`, outline: s.focus ? '2px solid #2563EB' : undefined}}>
              <p className={`text-[10px] font-bold ${s.focus ? 'text-blue-600' : 'text-slate-600'}`}>{s.name}</p>
              <p className={`text-[11px] font-black mt-0.5 ${s.change>=0?'text-green-700':'text-red-600'}`}>
                {s.change>=0?'+':''}{s.change}%
              </p>
            </div>
          )
        })}
      </div>
    </div>
  )
}

/* ══ TOP MOVERS ══ */
function TopMovers() {
  return (
    <div>
      <h3 className="text-xs font-bold text-slate-600 mb-2.5">Score Movers Today</h3>
      <div className="flex flex-col gap-1.5">
        {TOP_MOVERS.map(m => (
          <div key={m.ticker} className="flex items-center gap-2.5 px-2 py-1.5 rounded-xl hover:bg-slate-50 transition-colors">
            <span className={`text-[11px] font-black ${m.scoreDelta>=0?'text-green-600':'text-red-500'}`}>
              {m.scoreDelta>=0?'↑':'↓'}{Math.abs(m.scoreDelta)}
            </span>
            <span className="font-mono font-bold text-xs text-slate-800 flex-1">{m.ticker}</span>
            <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded-full ${verdictPillClass(m.verdict)}`}>{m.verdict}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

/* ══ RECENT ANALYSES ══ */
function RecentAnalyses() {
  const navigate = useNavigate()
  return (
    <div className="card p-5">
      <h2 className="text-sm font-bold text-slate-700 mb-3">Recent Analyses</h2>
      <div className="flex flex-col divide-y divide-slate-50">
        {WATCHLIST.map(stock => {
          const Ico = stock.change>=0 ? TrendingUp : TrendingDown
          return (
            <button key={stock.ticker} onClick={()=>navigate(`/stock/${stock.ticker}`)}
              className="w-full flex items-center gap-2.5 py-2.5 px-1 -mx-1 rounded-lg hover:bg-blue-50/60 transition-colors group text-left">
              <Ico size={12} className={stock.change>=0?'text-green-500':'text-red-400'}/>
              <span className="font-mono font-bold text-xs text-slate-800 w-24 truncate">{stock.ticker}</span>
              <div className="score-track flex-1">
                <div className={`score-fill ${scoreFillClass(stock.verdict)}`} style={{width:`${stock.score*100}%`}}/>
              </div>
              <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded-full shrink-0 ${verdictPillClass(stock.verdict)}`}>{stock.verdict}</span>
              <div className="flex items-center gap-0.5 text-[10px] text-slate-400 shrink-0">
                <Clock size={9}/>{stock.analysedAt}
              </div>
            </button>
          )
        })}
      </div>
      <button onClick={()=>navigate('/stock/MARUTI')}
        className="mt-3 w-full py-2 rounded-xl text-xs font-semibold btn-cyan transition-all">
        + Analyse a new stock
      </button>
    </div>
  )
}

/* ══════════════════════════════════════════
   DASHBOARD — full layout
══════════════════════════════════════════ */
export function Dashboard() {
  const navigate = useNavigate()
  const stats    = useStats()

  const orbState: OrbState =
    stats.buy >= 3  ? 'complete' :
    stats.sell >= 2 ? 'scanning' : 'idle'

  return (
    <div className="min-h-screen" style={{background:'linear-gradient(150deg,#EEF4FF 0%,#F5F8FF 50%,#EFF6FF 100%)'}}>
      <TopBar/>
      <div className="sticky top-14 z-40"><MarketTicker/></div>

      <main className="relative z-10 px-5 py-5 max-w-[1440px] mx-auto space-y-4">

        {/* ── Row 0: Morning briefing ── */}
        <BriefingCard/>

        {/* ── Row 1: KPI strip ── */}
        <KpiStrip/>

        {/* ── Row 2: Main 3-column layout ── */}
        <div className="grid gap-4 items-start" style={{gridTemplateColumns:'272px 1fr 272px'}}>

          {/* ═══ COL 1: Watchlist + Suggestions ═══ */}
          <div className="flex flex-col gap-3">
            <div className="card p-4">
              <div className="flex items-center justify-between mb-3">
                <h2 className="text-sm font-bold text-slate-700">Your Watchlist</h2>
                <button className="w-6 h-6 rounded-full bg-blue-50 hover:bg-blue-100 flex items-center justify-center text-blue-600 border border-blue-200 transition-colors">
                  <Plus size={12}/>
                </button>
              </div>
              <div className="flex flex-col gap-2">
                {WATCHLIST.map(s=>(
                  <WatchItem key={s.ticker} stock={s} onClick={()=>navigate(`/stock/${s.ticker}`)}/>
                ))}
              </div>
            </div>

            <div className="card p-4">
              <h2 className="text-sm font-bold text-slate-700 mb-3">Suggested for You</h2>
              <div className="flex flex-col gap-2">
                {SUGGESTED.map(s=><SuggestItem key={s.ticker} s={s}/>)}
              </div>
            </div>
          </div>

          {/* ═══ COL 2: Oracle centrepiece ═══ */}
          <div className="flex flex-col items-center gap-4 py-2">
            <div className="text-center">
              <h1 className="text-2xl font-bold text-slate-800 mb-1">Good morning, Revan 👋</h1>
              <p className="text-sm text-slate-500">
                {stats.buy} of {WATCHLIST.length} stocks signalling{' '}
                <span className="font-semibold text-green-600">BUY</span> today
              </p>
            </div>

            <OracleOrb state={orbState} size={340}
              verdict={stats.buy>=3?'BUY':stats.sell>=2?'SELL':'NEUTRAL'}
              score={stats.buy>=3?0.78:stats.sell>=2?0.38:0.52}/>

            <div className="flex items-center gap-3">
              <button onClick={()=>navigate('/stock/MARUTI')}
                className="flex items-center gap-2 px-5 py-2.5 rounded-xl text-sm font-semibold text-white shadow-md hover:shadow-lg hover:opacity-90 transition-all"
                style={{background:'linear-gradient(135deg,#2563EB,#06B6D4)'}}>
                <Zap size={14}/> Run Analysis
              </button>
              <button onClick={()=>navigate('/lenses')}
                className="btn-cyan flex items-center gap-2 px-5 py-2.5 rounded-xl text-sm font-semibold">
                <Layers size={14}/> Configure Lenses
              </button>
            </div>

            {/* Market chips */}
            <div className="flex items-center gap-2 flex-wrap justify-center">
              {[{l:'Nifty Auto',v:'▲ 1.2%',p:true},{l:'INR/USD',v:'83.4',p:true},{l:'Crude',v:'$87.2',p:true},{l:'Nifty 50',v:'▲ 0.4%',p:true}].map(it=>(
                <span key={it.l} className="px-3 py-1 rounded-full text-[11px] font-medium bg-white/70 border border-slate-200 text-slate-500 shadow-sm">
                  {it.l} <span className={it.p?'text-green-600 font-semibold':'text-red-500 font-semibold'}>{it.v}</span>
                </span>
              ))}
            </div>
          </div>

          {/* ═══ COL 3: Rich right panel ═══ */}
          <div className="flex flex-col gap-3">

            {/* Portfolio donut */}
            <div className="card p-4">
              <h2 className="text-xs font-bold text-slate-600 uppercase tracking-wide mb-3">Portfolio Snapshot</h2>
              <PortfolioDonut buy={stats.buy} neutral={stats.neutral} sell={stats.sell}/>
            </div>

            {/* Market mood */}
            <div className="card p-4">
              <MoodGauge/>
            </div>

            {/* Nifty Auto chart */}
            <div className="card p-4">
              <NiftyMiniChart/>
            </div>

            {/* Sector heatmap */}
            <div className="card p-4">
              <SectorHeatmap/>
            </div>

            {/* Top movers */}
            <div className="card p-4">
              <TopMovers/>
            </div>

          </div>
        </div>

        {/* ── Row 3: Recent analyses (full width under the 3-col grid) ── */}
        <RecentAnalyses/>

      </main>
    </div>
  )
}
