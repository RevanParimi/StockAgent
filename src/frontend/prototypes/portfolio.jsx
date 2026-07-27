// Portfolio page — beginner-friendly view of holdings, P/L, agent take, recent activity, learnings
const { useState: useStatePf, useEffect: useEffectPf, useRef: useRefPf } = React;

// ── Live data ──────────────────────────────────────────────────────────────
// GET /portfolio (+ digest). status: 'loading' | 'live' | 'demo'.
// Demo (mock) data renders ONLY when the API is unreachable, or with ?demo=1.

function fmtIST(ts, dateStr) {
  try {
    if (ts) {
      const d = new Date(ts);
      if (!isNaN(d)) return d.toLocaleString('en-IN', {
        timeZone: 'Asia/Kolkata', day: '2-digit', month: 'short',
        hour: '2-digit', minute: '2-digit', hour12: false });
    }
  } catch (e) { /* fall through */ }
  return dateStr || '';
}

function adaptHolding(h) {
  return {
    sym: h.symbol,
    sector: h.sector,
    qty: h.adj_qty,               // corp-action-adjusted — all math uses adj_*
    avgPrice: h.adj_avg_price,
    currentPrice: h.last_close,   // null when mark-to-market failed
    pnlPct: h.pnl_pct,            // null when mark-to-market failed
    buyDate: h.buy_date,
  };
}

function digestAlerts(digest) {
  if (!digest?.holdings?.length) return [];
  const esc = new Set(digest.escalations || []);
  return digest.holdings
    .filter(r => r.verdict && r.verdict !== 'NO_DATA' && r.reason)
    .sort((a, b) => (esc.has(b.symbol) ? 1 : 0) - (esc.has(a.symbol) ? 1 : 0))
    .slice(0, 4)
    .map(r => ({
      sym:  r.symbol,
      kind: esc.has(r.symbol) ? 'warn' : 'good',
      text: r.reason,
    }));
}

function usePortfolioLive() {
  const [state, setState] = useStatePf({ status: 'loading', holdings: [], digest: null, perf: null, txns: [] });
  const aliveRef = useRefPf(false);
  const wasLiveRef = useRefPf(false); // once true, a later reload failure must not downgrade live -> demo

  const load = async () => {
    if (new URLSearchParams(location.search).get('demo') === '1') {
      if (aliveRef.current) setState({ status: 'demo', forced: true, holdings: window.PORTFOLIO.holdings, digest: null });
      return;
    }
    try {
      const res = await fetch('/portfolio');
      if (!res.ok) throw new Error('portfolio HTTP ' + res.status);
      const p = await res.json();
      let digest = null;
      try {
        const dr = await fetch('/portfolio/digest/latest');
        if (dr.ok) digest = await dr.json();
      } catch {} // digest is optional — 404 until first advisor run
      let perf = null, txns = [];
      try {
        const pr = await fetch('/portfolio/performance');
        if (pr.ok) perf = await pr.json();
      } catch {} // performance is optional — absent until cash accounting is on
      try {
        const tr = await fetch('/portfolio/transactions?limit=500');
        if (tr.ok) txns = (await tr.json()).transactions || [];
      } catch {}
      wasLiveRef.current = true;
      if (aliveRef.current) setState({ status: 'live', holdings: (p.holdings || []).map(adaptHolding), digest, perf, txns });
    } catch (e) {
      if (wasLiveRef.current) {
        console.warn('[Portfolio] reload failed — keeping last live data.', e);
        return;
      }
      console.warn('[Portfolio] live fetch failed — demo fallback.', e);
      if (aliveRef.current) setState({ status: 'demo', forced: false, holdings: window.PORTFOLIO.holdings, digest: null });
    }
  };

  useEffectPf(() => { aliveRef.current = true; load(); return () => { aliveRef.current = false; }; }, []);
  return { ...state, reload: load };
}

function AddHoldingModal({ onClose, onAdded }) {
  const [sym, setSym] = useStatePf('');
  const [results, setResults] = useStatePf([]);
  const [qty, setQty] = useStatePf('');
  const [buyDate, setBuyDate] = useStatePf(new Date().toISOString().slice(0,10));
  const [price, setPrice] = useStatePf('');
  const [err, setErr] = useStatePf('');
  const [saving, setSaving] = useStatePf(false);
  const timerRef = useRefPf(null);
  const aliveRef = useRefPf(true);
  useEffectPf(() => { aliveRef.current = true; return () => { aliveRef.current = false; clearTimeout(timerRef.current); }; }, []);

  const searchSym = (val) => {
    setSym(val.toUpperCase());
    setErr('');
    clearTimeout(timerRef.current);
    if (val.length < 2) { setResults([]); return; }
    timerRef.current = setTimeout(async () => {
      try {
        const res = await fetch(`/ui/search?q=${encodeURIComponent(val)}`);
        if (res.ok) {
          const d = await res.json();
          if (aliveRef.current) setResults(d.results || []);
        }
      } catch {}
    }, 350);
  };

  const submit = async () => {
    const q = parseFloat(qty);
    if (!sym.trim())        { setErr('Pick a stock symbol.'); return; }
    if (!(q > 0))           { setErr('Quantity must be a positive number.'); return; }
    setSaving(true); setErr('');
    const body = { symbol: sym.trim(), qty: q, buy_date: buyDate };
    if (price.trim() !== '') body.price = parseFloat(price);
    try {
      const res = await fetch('/portfolio/holdings', {
        method:'POST', headers:{ 'Content-Type':'application/json' }, body: JSON.stringify(body),
      });
      if (!res.ok) {
        const d = await res.json().catch(()=>({}));
        if (aliveRef.current) setErr(typeof d.detail === 'string' ? d.detail : `HTTP ${res.status}`);
        return;
      }
      onAdded();
    } catch (e) {
      if (aliveRef.current) setErr('Network error: ' + e.message);
    } finally {
      if (aliveRef.current) setSaving(false);
    }
  };

  const field = { width:'100%', padding:'10px 12px', borderRadius:9, border:'1px solid var(--border-strong)',
    background:'var(--bg-base)', color:'var(--ink-1)', fontSize:13, outline:'none', boxSizing:'border-box' };
  const label = { fontSize:11, fontWeight:700, color:'var(--ink-3)', textTransform:'uppercase',
    letterSpacing:'.1em', marginBottom:6, display:'block' };

  return (
    <>
      <div onClick={onClose} style={{ position:'fixed', inset:0, background:'rgba(15,23,42,.45)', backdropFilter:'blur(4px)', zIndex:60, animation:'fade-in .2s' }}/>
      <div style={{ position:'fixed', top:'50%', left:'50%', transform:'translate(-50%,-50%)', zIndex:65,
        width:'min(440px, calc(100vw - 32px))', background:'var(--bg-surface)', borderRadius:16,
        border:'1px solid var(--border)', boxShadow:'var(--shadow-lg, 0 24px 64px rgba(0,0,0,.35))', padding:24 }}>
        <div style={{ display:'flex', alignItems:'center', gap:12, marginBottom:18 }}>
          <div style={{ flex:1 }}>
            <div className="eyebrow" style={{ marginBottom:2 }}>Virtual holding</div>
            <div style={{ fontSize:16, fontWeight:700 }}>Add holding</div>
          </div>
          <button onClick={onClose} style={{ width:30, height:30, borderRadius:8, border:'1px solid var(--border)',
            background:'transparent', display:'grid', placeItems:'center', color:'var(--ink-2)', cursor:'pointer' }}>
            <Icon.X size={15}/>
          </button>
        </div>

        <div style={{ marginBottom:14, position:'relative' }}>
          <label style={label}>Symbol</label>
          <input value={sym} onChange={e=>searchSym(e.target.value)} placeholder="e.g. HDFCBANK, TCS, SUZLON"
            className="mono" style={field} autoFocus/>
          {results.length > 0 && (
            <div style={{ position:'absolute', top:'100%', left:0, right:0, zIndex:5, marginTop:4,
              background:'var(--bg-surface)', border:'1px solid var(--border)', borderRadius:10,
              boxShadow:'var(--shadow-md, 0 12px 32px rgba(0,0,0,.25))', overflow:'hidden', maxHeight:200, overflowY:'auto' }}>
              {results.map(r => (
                <button key={r.sym} onClick={()=>{ setSym(r.sym); setResults([]); }}
                  style={{ display:'flex', gap:10, alignItems:'center', width:'100%', padding:'9px 12px',
                    border:'none', background:'transparent', cursor:'pointer', textAlign:'left' }}
                  onMouseEnter={e=>e.currentTarget.style.background='var(--bg-tinted)'}
                  onMouseLeave={e=>e.currentTarget.style.background='transparent'}>
                  <span className="mono" style={{ fontWeight:700, fontSize:12, color:'var(--ink-1)' }}>{r.sym}</span>
                  <span style={{ fontSize:12, color:'var(--ink-3)', overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap' }}>{r.name}</span>
                </button>
              ))}
            </div>
          )}
          <div style={{ fontSize:11, color:'var(--ink-3)', marginTop:5 }}>
            Sector is detected automatically. Any NSE symbol works — new ones get the generic analysis graph.
          </div>
        </div>

        <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:12, marginBottom:14 }}>
          <div>
            <label style={label}>Quantity</label>
            <input value={qty} onChange={e=>{ setQty(e.target.value); setErr(''); }} type="number" min="0" step="any" placeholder="10" className="mono" style={field}/>
          </div>
          <div>
            <label style={label}>Buy date</label>
            <input value={buyDate} onChange={e=>{ setBuyDate(e.target.value); setErr(''); }} type="date" className="mono" style={field}/>
          </div>
        </div>

        <div style={{ marginBottom:18 }}>
          <label style={label}>Buy price (optional)</label>
          <input value={price} onChange={e=>{ setPrice(e.target.value); setErr(''); }} type="number" min="0" step="any"
            placeholder="Leave blank to use the real NSE close on the buy date" className="mono" style={field}/>
        </div>

        {err && (
          <div style={{ padding:'10px 12px', borderRadius:9, background:'var(--sell-soft)', color:'var(--sell-strong)',
            fontSize:12, lineHeight:1.5, marginBottom:14 }}>{err}</div>
        )}

        <button onClick={submit} disabled={saving} style={{ width:'100%', padding:'11px 14px', border:'none', borderRadius:10,
          background:'linear-gradient(135deg, var(--cyan), var(--violet))', color:'#fff', fontSize:13, fontWeight:700,
          cursor: saving ? 'wait' : 'pointer', opacity: saving ? .6 : 1,
          display:'flex', alignItems:'center', justifyContent:'center', gap:8 }}>
          <Icon.Plus size={14}/> {saving ? 'Adding…' : 'Add to portfolio'}
        </button>
      </div>
    </>
  );
}

function PortfolioPage({ onNav, openChat }) {
  const [search, setSearch] = useStatePf('');
  const [range, setRange] = useStatePf('1M');
  const [addOpen, setAddOpen] = useStatePf(false);   // modal wired in Task 4
  const live = usePortfolioLive();
  const isDemo = live.status === 'demo';
  const isLive = live.status === 'live';
  const holdings = live.holdings;

  // Demo keeps the mock aggregates; live computes from marked rows only.
  const demo = window.PORTFOLIO;
  const marked = holdings.filter(h => h.currentPrice != null);
  const invested = isDemo ? demo.totalCost
    : marked.reduce((s, h) => s + h.qty * h.avgPrice, 0);
  const totalValue = isDemo ? demo.totalValue
    : marked.reduce((s, h) => s + h.qty * h.currentPrice, 0);
  const totalReturn = totalValue - invested;
  const totalReturnPct = invested > 0 ? (totalReturn / invested) * 100 : 0;
  const ranges = window.PORTFOLIO_RANGES;
  const r = ranges[range];
  const alerts = isDemo ? demo.alerts : digestAlerts(live.digest);
  const perf = isLive ? live.perf : null;
  const cashLive = perf && perf.cash != null;
  const heroValue = cashLive && perf.total_equity != null ? perf.total_equity : totalValue;
  const liveHist = (perf?.history || []).filter(pt => pt.total_equity != null);
  const showChart = isDemo || liveHist.length > 1;
  const histWindow = { '1W': 5, '1M': 22, '3M': 66, '6M': 132, '1Y': 252 }[range] || 22;
  const liveSlice = liveHist.slice(-histWindow);
  const liveChange = liveSlice.length > 1 && liveSlice[0].total_equity > 0
    ? (liveSlice[liveSlice.length - 1].total_equity / liveSlice[0].total_equity - 1) * 100 : 0;

  if (live.status === 'loading') {
    return (
      <div style={{ minHeight:'100vh', background:'var(--bg-base)' }}>
        <TopNav active="portfolio" onNav={onNav} search={search} setSearch={setSearch}/>
        <main style={{ maxWidth:1280, margin:'0 auto', padding:'var(--main-py) var(--main-px) 96px' }}>
          <div style={{ height:180, borderRadius:24, marginBottom:24, background:'var(--bg-tinted)', animation:'pulse 1.4s ease-in-out infinite' }}/>
          <div style={{ height:320, borderRadius:16, background:'var(--bg-tinted)', animation:'pulse 1.4s ease-in-out infinite' }}/>
        </main>
      </div>
    );
  }

  return (
    <div style={{ minHeight:'100vh', background:'var(--bg-base)' }}>
      <TopNav active="portfolio" onNav={onNav} search={search} setSearch={setSearch}/>

      <main style={{ maxWidth:1280, margin:'0 auto', padding:'var(--main-py) var(--main-px) 96px' }}>
        {/* Hero strip */}
        <section className="pf-hero-section" style={{
          position:'relative', overflow:'hidden', borderRadius:24, marginBottom:24,
          background:'linear-gradient(135deg, #0a1628 0%, #134e5c 50%, #1a4a73 100%)',
          color:'#f1f5f9', padding:'28px var(--main-px)',
          display:'grid', gridTemplateColumns: showChart ? 'var(--hero-cols)' : '1fr', gap:32, alignItems:'center'
        }}>
          <div style={{ position:'absolute', top:'-30%', right:'-10%', width:520, height:520, borderRadius:'50%',
            background:'radial-gradient(circle, rgba(124,58,237,.32), transparent 65%)', filter:'blur(40px)' }}/>
          <div style={{ position:'absolute', bottom:'-40%', left:'-10%', width:480, height:480, borderRadius:'50%',
            background:'radial-gradient(circle, rgba(8,145,178,.4), transparent 65%)', filter:'blur(40px)' }}/>

          <div style={{ position:'relative', zIndex:2 }}>
            <div style={{ display:'flex', alignItems:'center', gap:10, marginBottom:8 }}>
              <div style={{ fontSize:11, fontWeight:700, letterSpacing:'.18em', color:'#94a3b8', textTransform:'uppercase' }}>
                Portfolio · {isDemo ? 'Demo' : 'Live'}
              </div>
              {isDemo && (
                <span style={{ fontSize:10, fontWeight:700, padding:'3px 8px', borderRadius:999,
                  background:'rgba(217,119,6,.25)', color:'#fcd34d', letterSpacing:'.06em' }}>
                  {live.forced ? 'DEMO DATA' : 'DEMO DATA — API UNREACHABLE'}
                </span>
              )}
              {isLive && perf?.autopilot && (
                <span style={{ fontSize:10, fontWeight:700, padding:'3px 8px', borderRadius:999,
                  background:'rgba(34,211,238,.18)', color:'#67e8f9', letterSpacing:'.06em' }}>
                  AUTOPILOT
                </span>
              )}
            </div>
            <div className="pf-hero-value-row" style={{ display:'flex', alignItems:'baseline', gap:14, marginBottom:12, flexWrap:'wrap' }}>
              <span className="pf-hero-value mono" style={{ fontSize:44, fontWeight:800, letterSpacing:'-0.02em' }}>
                ₹{Math.round(heroValue).toLocaleString('en-IN')}
              </span>
              {isDemo && (
                <span className="pf-hero-badge" style={{
                  fontSize:14, fontWeight:700, padding:'4px 10px', borderRadius:8,
                  background: demo.dayChange >= 0 ? 'rgba(34,197,94,.18)' : 'rgba(239,68,68,.18)',
                  color: demo.dayChange >= 0 ? '#86efac' : '#fca5a5'
                }}>
                  {demo.dayChange >= 0 ? '+' : ''}₹{Math.abs(demo.dayChange).toLocaleString('en-IN')} ({demo.dayChangePct >= 0 ? '+':''}{demo.dayChangePct.toFixed(2)}%) today
                </span>
              )}
              {isLive && cashLive && perf.day_change_pct != null && (
                <span className="pf-hero-badge" style={{
                  fontSize:14, fontWeight:700, padding:'4px 10px', borderRadius:8,
                  background: perf.day_change_pct >= 0 ? 'rgba(34,197,94,.18)' : 'rgba(239,68,68,.18)',
                  color: perf.day_change_pct >= 0 ? '#86efac' : '#fca5a5'
                }}>
                  {perf.day_change_pct >= 0 ? '+' : ''}{perf.day_change_pct.toFixed(2)}% today
                </span>
              )}
            </div>
            <div className="pf-hero-stats" style={{ display:'flex', gap:24, color:'#cbd5e1', fontSize:13, flexWrap:'wrap' }}>
              <Stat2 label="Invested"      value={'₹'+Math.round(cashLive && perf.capital_in > 0 ? perf.capital_in : invested).toLocaleString('en-IN')}/>
              <Stat2 label="Total return"  value={((cashLive ? (perf.total_equity - perf.capital_in) : totalReturn)>=0?'+':'-')+'₹'+Math.abs(Math.round(cashLive ? (perf.total_equity - perf.capital_in) : totalReturn)).toLocaleString('en-IN')} pct={perf?.total_return_pct ?? totalReturnPct}/>
              {(isDemo || cashLive) && <Stat2 label="Cash" value={'₹'+(isDemo ? demo.cash : Math.round(perf.cash)).toLocaleString('en-IN')}/>}
              {cashLive && perf.realized_pnl != null && (
                <Stat2 label="Realized P&L"
                  value={(perf.realized_pnl>=0?'+':'-')+'₹'+Math.abs(Math.round(perf.realized_pnl)).toLocaleString('en-IN')}/>
              )}
              <Stat2 label="Holdings"      value={holdings.length+' stocks'}/>
              {isLive && marked.length < holdings.length && (
                <Stat2 label="Unpriced" value={(holdings.length - marked.length)+' awaiting close'}/>
              )}
            </div>
          </div>

          {showChart && (
            <div className="pf-hero-chart" style={{ position:'relative', zIndex:2 }}>
              <div style={{ display:'flex', alignItems:'center', justifyContent:'space-between', gap:10, marginBottom:8 }}>
                <div>
                  <div style={{ fontSize:11, color:'#94a3b8' }}>Value over {isDemo ? r.label : range}</div>
                  <div style={{ fontSize:13, fontWeight:700, color: (isDemo ? r.change : liveChange) >= 0 ? '#86efac' : '#fca5a5' }}>
                    {(isDemo ? r.change : liveChange) >= 0 ? '+' : ''}{(isDemo ? r.change : liveChange).toFixed(2)}%
                  </div>
                </div>
                <DarkRangeTabs value={range} onChange={setRange}/>
              </div>
              <Sparkline values={isDemo ? r.points : liveSlice.map(pt => pt.total_equity)} height={92} color="#22d3ee"/>
            </div>
          )}
        </section>

        <div style={{ display:'grid', gridTemplateColumns:'var(--grid-portfolio)', gap:20 }}>
          {/* Holdings + learnings column */}
          <div style={{ display:'flex', flexDirection:'column', gap:20 }}>
            {isLive && holdings.length === 0 ? (
              <EmptyPortfolio onAdd={()=>setAddOpen(true)}/>
            ) : (
              <HoldingsTable holdings={holdings} digest={live.digest} isLive={isLive}
                onAdd={()=>setAddOpen(true)} onRemoved={live.reload}/>
            )}
            {(isDemo || window.__learningsLive) && (
              <LearningsSection learnings={window.PORTFOLIO_LEARNINGS} openChat={openChat}/>
            )}
            {isDemo && <ActivityCard items={demo.recentActivity}/>}
            {isLive && live.txns.length > 0 && <LiveActivityCard txns={live.txns}/>}
          </div>

          {/* Right rail */}
          <div style={{ display:'flex', flexDirection:'column', gap:20 }}>
            {alerts.length > 0 && <AlertsCard alerts={alerts}/>}
            {holdings.length > 0 && <AllocationCard holdings={holdings}/>}
            <AskAssistantCard openChat={openChat}/>
          </div>
        </div>
      </main>

      {addOpen && <AddHoldingModal onClose={()=>setAddOpen(false)}
        onAdded={()=>{ setAddOpen(false); live.reload(); }}/>}
    </div>
  );
}

function EmptyPortfolio({ onAdd }) {
  return (
    <div className="card" style={{ padding:'48px 24px', textAlign:'center' }}>
      <div style={{ width:56, height:56, borderRadius:16, margin:'0 auto 16px',
        background:'linear-gradient(135deg, var(--cyan-soft), var(--violet-soft))',
        display:'grid', placeItems:'center', color:'var(--cyan)' }}>
        <Icon.Briefcase size={24}/>
      </div>
      <div style={{ fontSize:17, fontWeight:700, marginBottom:6 }}>No holdings yet</div>
      <p style={{ fontSize:13, color:'var(--ink-3)', margin:'0 auto 18px', maxWidth:380, lineHeight:1.6 }}>
        Add your first holding — any NSE stock — automobile, banking, IT,
        renewable energy and beyond. Mock money, real prices, real agent analysis.
      </p>
      <button onClick={onAdd} style={{ padding:'10px 18px', border:'none', borderRadius:10,
        background:'linear-gradient(135deg, var(--cyan), var(--violet))', color:'#fff',
        fontSize:13, fontWeight:700, cursor:'pointer', display:'inline-flex', alignItems:'center', gap:8 }}>
        <Icon.Plus size={14}/> Add holding
      </button>
    </div>
  );
}

// Range tabs for the dark hero — same shape as Home's RangeTabs but inverted colors.
function DarkRangeTabs({ value, onChange, options=['1W','1M','3M','6M','1Y'] }) {
  return (
    <div style={{
      display:'flex', gap:2, padding:3, background:'rgba(255,255,255,.08)',
      borderRadius:8, border:'1px solid rgba(255,255,255,.08)'
    }}>
      {options.map(o => (
        <button key={o} onClick={()=>onChange(o)} style={{
          padding:'4px 9px', borderRadius:6, border:'none',
          fontSize:11, fontWeight:700, letterSpacing:'.02em',
          fontFamily:'var(--font-mono, ui-monospace, monospace)',
          background: value===o ? 'rgba(255,255,255,.16)' : 'transparent',
          color: value===o ? '#f1f5f9' : '#94a3b8',
          cursor:'pointer', transition:'all .15s'
        }}>{o}</button>
      ))}
    </div>
  );
}

function Stat2({ label, value, pct }) {
  return (
    <div>
      <div style={{ fontSize:10, color:'#94a3b8', textTransform:'uppercase', letterSpacing:'.12em', marginBottom:4 }}>{label}</div>
      <div className="mono" style={{ fontSize:15, fontWeight:700, color:'#f1f5f9' }}>
        {value} {pct !== undefined && (
          <span style={{ marginLeft:6, color: pct>=0 ? '#86efac' : '#fca5a5', fontSize:12 }}>
            ({pct>=0?'+':''}{pct.toFixed(1)}%)
          </span>
        )}
      </div>
    </div>
  );
}

// Advisor verdicts (digest) + composite verdicts (TICKERS) share one color map.
const PF_VERDICT_COLORS = {
  'STRONG BUY':'var(--buy-strong)', 'BUY':'var(--buy)', 'NEUTRAL':'var(--neutral)',
  'SELL':'var(--sell)', 'STRONG SELL':'var(--sell-strong)',
  'HOLD':'var(--neutral)', 'TRIM':'var(--sell)', 'EXIT':'var(--sell-strong)',
  'SWITCH':'var(--violet)', 'ADD':'var(--buy)',
};

// Digest advisor verdict first; composite window.TICKERS verdict as fallback.
function agentTake(h, digest) {
  const drow = (digest?.holdings || []).find(r => r.symbol === h.sym && r.verdict && r.verdict !== 'NO_DATA');
  if (drow) return { verdict: drow.verdict, reason: drow.reason, score: null };
  if (h.verdict) return { verdict: h.verdict, reason: null, score: h.agentScore }; // demo rows
  const t = (window.TICKERS || []).find(t => t.sym === h.sym && t.hasData);
  if (t) return { verdict: t.verdict, reason: 'Latest composite agent score', score: t.score };
  return null;
}

function HoldingsTable({ holdings, digest, isLive, onAdd, onRemoved }) {
  const [busy, setBusy] = useStatePf('');
  const remove = async (sym) => {
    if (!window.confirm(`Remove ${sym} from your portfolio?`)) return;
    setBusy(sym);
    try {
      const res = await fetch(`/portfolio/holdings/${encodeURIComponent(sym)}`, { method:'DELETE' });
      if (!res.ok) alert(`Could not remove ${sym}: HTTP ${res.status}`);
      await onRemoved();
    } catch (e) {
      alert(`Could not remove ${sym}: ${e.message}`);
    } finally {
      setBusy('');
    }
  };

  const fmt = (v, digits=2) => v == null ? '—'
    : '₹' + v.toLocaleString('en-IN', digits === 0 ? {maximumFractionDigits:0} : {minimumFractionDigits:digits});

  return (
    <div className="card">
      <div className="pf-card-header" style={{ padding:'18px 24px', borderBottom:'1px solid var(--border)', display:'flex', alignItems:'center', gap:12 }}>
        <div className="eyebrow">Your holdings · {holdings.length}</div>
        <button onClick={isLive ? onAdd : undefined} disabled={!isLive}
          title={isLive ? 'Add a virtual holding' : 'Unavailable in demo mode'}
          style={{ marginLeft:'auto', padding:'6px 12px', border:'1px dashed var(--border-strong)', borderRadius:8,
          background:'transparent', fontSize:12, fontWeight:600, color:'var(--ink-2)', display:'flex', alignItems:'center', gap:6,
          cursor: isLive ? 'pointer' : 'not-allowed', opacity: isLive ? 1 : .5 }}>
          <Icon.Plus size={13}/> Add holding
        </button>
      </div>
      <div className="holdings-table-scroll">
      <table style={{ width:'100%', borderCollapse:'collapse', minWidth:640 }}>
        <thead>
          <tr style={{ fontSize:11, textTransform:'uppercase', color:'var(--ink-3)', letterSpacing:'.1em' }}>
            <th style={pfTh}>Ticker</th>
            <th style={pfTh}>Qty</th>
            <th style={pfTh}>Avg buy</th>
            <th style={pfTh}>Current</th>
            <th style={pfTh}>Value</th>
            <th style={pfTh}>P/L</th>
            <th style={pfTh}>Agent take</th>
            {isLive && <th style={pfTh}></th>}
          </tr>
        </thead>
        <tbody>
          {holdings.map(h => {
            const value = h.currentPrice != null ? h.qty * h.currentPrice : null;
            const pl    = h.currentPrice != null ? h.qty * (h.currentPrice - h.avgPrice) : null;
            const plPct = h.pnlPct != null ? h.pnlPct
              : (h.currentPrice != null ? ((h.currentPrice - h.avgPrice) / h.avgPrice) * 100 : null);
            const take  = agentTake(h, digest);
            const verdictColor = take ? (PF_VERDICT_COLORS[take.verdict] || 'var(--neutral)') : null;
            return (
              <tr key={h.sym} style={{ transition:'background .15s' }}
                onMouseEnter={e=>e.currentTarget.style.background='var(--bg-tinted)'}
                onMouseLeave={e=>e.currentTarget.style.background=''}>
                <td style={pfTd}>
                  <div style={{ display:'flex', alignItems:'center', gap:10 }}>
                    <div style={{ width:32, height:32, borderRadius:8,
                      background:'linear-gradient(135deg, var(--cyan-soft), var(--violet-soft))',
                      display:'grid', placeItems:'center', fontWeight:800, color:'var(--cyan)', fontSize:13 }}>{h.sym[0]}</div>
                    <div>
                      <div className="mono" style={{ fontWeight:700 }}>{h.sym}</div>
                      {h.sector && <div style={{ fontSize:10, color:'var(--ink-3)', letterSpacing:'.04em' }}>{h.sector.replace(/_/g,' ')}</div>}
                    </div>
                  </div>
                </td>
                <td style={pfTd}><span className="mono">{h.qty}</span></td>
                <td style={pfTd}><span className="mono">{fmt(h.avgPrice)}</span></td>
                <td style={pfTd}><span className="mono">{fmt(h.currentPrice)}</span></td>
                <td style={pfTd}><span className="mono" style={{ fontWeight:700 }}>{fmt(value, 0)}</span></td>
                <td style={pfTd}>
                  {pl == null ? <span className="mono" style={{ color:'var(--ink-3)' }}>—</span> : (
                    <div style={{ color: pl>=0 ? 'var(--buy-strong)':'var(--sell-strong)', fontWeight:700 }}>
                      <span className="mono">{pl>=0?'+':'-'}₹{Math.abs(pl).toLocaleString('en-IN', {maximumFractionDigits:0})}</span>
                      <div className="mono" style={{ fontSize:11, fontWeight:600 }}>{plPct>=0?'+':''}{plPct.toFixed(2)}%</div>
                    </div>
                  )}
                </td>
                <td style={pfTd}>
                  {take ? (
                    <div style={{ display:'flex', alignItems:'center', gap:8 }} title={take.reason || undefined}>
                      {take.score != null && <span className="mono" style={{ fontWeight:700 }}>{take.score.toFixed(2)}</span>}
                      <span style={{ display:'inline-block', padding:'3px 8px', borderRadius:999, fontSize:10, fontWeight:700,
                        background:`color-mix(in oklab, ${verdictColor} 14%, transparent)`, color: verdictColor, letterSpacing:'.04em' }}>
                        {take.verdict}
                      </span>
                    </div>
                  ) : <span className="mono" style={{ color:'var(--ink-3)' }}>—</span>}
                </td>
                {isLive && (
                  <td style={{ ...pfTd, textAlign:'right' }}>
                    <button onClick={()=>remove(h.sym)} disabled={busy===h.sym}
                      title={`Remove ${h.sym}`}
                      style={{ width:28, height:28, borderRadius:7, border:'1px solid var(--border)',
                        background:'transparent', color:'var(--ink-3)', cursor:'pointer',
                        display:'inline-grid', placeItems:'center', opacity: busy===h.sym ? .4 : 1 }}>
                      <Icon.X size={13}/>
                    </button>
                  </td>
                )}
              </tr>
            );
          })}
        </tbody>
      </table>
      </div>
    </div>
  );
}

const pfTh = { textAlign:'left', padding:'12px 24px', fontSize:11, fontWeight:600, borderBottom:'1px solid var(--border)' };
const pfTd = { padding:'14px 24px', fontSize:13, borderBottom:'1px solid var(--border)' };

function ActivityCard({ items }) {
  const [openIdx, setOpenIdx] = useStatePf(null);
  const iconMap = {
    buy:   { icon:<Icon.Plus size={14}/>,   bg:'var(--buy-soft)',     fg:'var(--buy-strong)',  label:'Bought' },
    sell:  { icon:<Icon.TrendDown size={14}/>, bg:'var(--sell-soft)', fg:'var(--sell-strong)', label:'Sold' },
    agent: { icon:<Icon.Sparkles size={14}/>, bg:'var(--violet-soft)', fg:'var(--violet)',     label:'Agent' },
  };
  return (
    <div className="card pf-card-body">
      <div className="eyebrow" style={{ marginBottom:14 }}>Recent activity</div>
      <div style={{ display:'flex', flexDirection:'column', gap:8 }}>
        {items.map((it, i) => {
          const m = iconMap[it.kind];
          return (
            <div key={i} style={{
              display:'grid', gridTemplateColumns:'auto 1fr auto', gap:14, alignItems:'center',
              padding:'12px 14px', background:'var(--bg-base)', borderRadius:10
            }}>
              <span style={{ width:30, height:30, borderRadius:8, background:m.bg, color:m.fg,
                display:'grid', placeItems:'center' }}>{m.icon}</span>
              <div style={{ minWidth:0 }}>
                <div style={{ fontSize:13, fontWeight:600 }}>
                  {m.label} <span className="mono">{it.sym}</span>
                  {it.qty && <span style={{ color:'var(--ink-3)', fontWeight:500 }}>
                    {' · '}{it.qty} @ ₹{it.price.toLocaleString('en-IN', {minimumFractionDigits:2})}
                    {it.buyPx != null && ` (bought @ ${it.approx ? '≈' : ''}₹${it.buyPx.toLocaleString('en-IN', {maximumFractionDigits:2})})`}
                  </span>}
                </div>
                {it.text && <div style={{ fontSize:12, color:'var(--ink-3)', marginTop:2 }}>{it.text}</div>}
                {it.reason && (
                  <div style={{ marginTop:4 }}>
                    <button onClick={()=>setOpenIdx(openIdx===i?null:i)}
                      style={{ background:'none', border:'none', padding:0, cursor:'pointer',
                               fontSize:11, fontWeight:600, color:'var(--violet)' }}>
                      {openIdx===i ? 'hide why' : 'why?'}
                    </button>
                    {openIdx===i && (
                      <div style={{ fontSize:12, color:'var(--ink-2)', marginTop:4,
                                    padding:'8px 10px', background:'var(--violet-soft)',
                                    borderRadius:8 }}>{it.reason}</div>
                    )}
                  </div>
                )}
              </div>
              <span className="pf-activity-time" style={{ fontSize:11, color:'var(--ink-3)', whiteSpace:'nowrap' }}>{it.t}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function LiveActivityCard({ txns }) {
  const [showAll, setShowAll] = useStatePf(false);
  const items = (showAll ? txns : txns.slice(0, 10)).map(t => {
    const isSell = t.side === 'SELL';
    const buyPx = isSell
      ? (t.cost_basis != null ? t.cost_basis
         : (t.realized_pnl != null && t.qty ? t.price - t.realized_pnl / t.qty : null))
      : null;
    const approx = isSell && t.cost_basis == null && buyPx != null;
    const pnlPct = isSell
      ? (t.pnl_pct != null ? t.pnl_pct
         : (buyPx ? (t.price / buyPx - 1) * 100 : null))
      : null;
    return {
      kind: isSell ? 'sell' : 'buy',
      sym: t.symbol, qty: t.qty, price: t.price,
      buyPx, approx,
      text: [t.verdict || t.source,
             isSell && t.realized_pnl != null
               ? `realized ${t.realized_pnl >= 0 ? '+' : ''}₹${Math.abs(t.realized_pnl).toLocaleString('en-IN')}`
                 + (pnlPct != null ? ` (${pnlPct >= 0 ? '+' : ''}${pnlPct.toFixed(1)}%)` : '')
               : '',
             t.note].filter(Boolean).join(' · '),
      reason: t.reason || '',
      t: fmtIST(t.ts, t.date),
    };
  });
  return (
    <div>
      <ActivityCard items={items}/>
      {txns.length > 10 && (
        <button onClick={()=>setShowAll(v=>!v)} style={{ marginTop:8, padding:'8px 14px',
          borderRadius:9, border:'1px solid var(--border)', background:'transparent',
          color:'var(--ink-2)', fontSize:12, fontWeight:600, cursor:'pointer' }}>
          {showAll ? 'Show recent only' : `View all ${txns.length} transactions`}
        </button>
      )}
    </div>
  );
}

function AlertsCard({ alerts }) {
  return (
    <div className="card pf-card-body">
      <div className="eyebrow" style={{ marginBottom:14 }}>What your agents are flagging</div>
      <div style={{ display:'flex', flexDirection:'column', gap:10 }}>
        {alerts.map((a, i) => {
          const colors = a.kind === 'good'
            ? { bg:'var(--buy-soft)', fg:'var(--buy-strong)' }
            : { bg:'var(--neutral-soft)', fg:'var(--neutral)' };
          return (
            <div key={i} style={{ padding:'12px 14px', borderRadius:10, background:colors.bg, borderLeft:`3px solid ${colors.fg}` }}>
              <div style={{ fontSize:12, fontWeight:700, color: colors.fg, letterSpacing:'.04em', marginBottom:4 }} className="mono">
                {a.sym}
              </div>
              <div style={{ fontSize:13, color:'var(--ink-1)', lineHeight:1.5 }}>{a.text}</div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function AllocationCard({ holdings }) {
  const total = holdings.reduce((s,h) => s + h.qty * (h.currentPrice || 0), 0);
  const segments = holdings.map(h => ({
    sym: h.sym,
    pct: total > 0 ? ((h.qty * (h.currentPrice || 0)) / total) * 100 : 0,
  }));
  const colors = ['#0891b2','#7c3aed','#16a34a','#d97706','#dc2626','#475569'];

  return (
    <div className="card pf-card-body">
      <div className="eyebrow" style={{ marginBottom:14 }}>Allocation</div>
      <div style={{ display:'flex', height:8, borderRadius:999, overflow:'hidden', marginBottom:14 }}>
        {segments.map((s, i) => (
          <span key={s.sym} style={{ width: s.pct + '%', background: colors[i % colors.length] }}/>
        ))}
      </div>
      <div style={{ display:'flex', flexDirection:'column', gap:8 }}>
        {segments.map((s, i) => (
          <div key={s.sym} style={{ display:'grid', gridTemplateColumns:'10px 1fr auto', gap:10, alignItems:'center', fontSize:13 }}>
            <span style={{ width:10, height:10, borderRadius:3, background: colors[i % colors.length] }}/>
            <span className="mono" style={{ color:'var(--ink-2)' }}>{s.sym}</span>
            <span className="mono" style={{ fontWeight:700, color:'var(--ink-1)' }}>{s.pct.toFixed(1)}%</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function AskAssistantCard({ openChat }) {
  return (
    <div style={{
      padding:20, borderRadius:16, color:'#f1f5f9', position:'relative', overflow:'hidden',
      background:'linear-gradient(135deg, #0a1628, #134e5c)'
    }}>
      <div style={{ position:'absolute', top:'-40%', right:'-30%', width:280, height:280, borderRadius:'50%',
        background:'radial-gradient(circle, rgba(124,58,237,.45), transparent 65%)', filter:'blur(20px)' }}/>
      <div style={{ position:'relative' }}>
        <div style={{ display:'flex', alignItems:'center', gap:10, marginBottom:10 }}>
          <Sphere size={36} mode="wireframe"/>
          <div style={{ fontSize:13, fontWeight:700 }}>Need a second opinion?</div>
        </div>
        <p style={{ fontSize:12, color:'#cbd5e1', lineHeight:1.5, margin:'0 0 14px' }}>
          Ask the assistant to review your portfolio, compare two holdings, or flag concentration risk.
        </p>
        <button onClick={openChat} style={{
          width:'100%', padding:'10px 14px', borderRadius:10, border:'1px solid rgba(255,255,255,.18)',
          background:'rgba(255,255,255,.08)', color:'#f1f5f9', fontSize:12, fontWeight:600,
          display:'flex', alignItems:'center', justifyContent:'center', gap:8
        }}><Icon.Sparkles size={14}/> Open assistant</button>
      </div>
    </div>
  );
}

// ============================================================
// LearningsSection — what the user can learn from their own history.
// Grounded in actual holdings + activity, not theory. Filterable.
// ============================================================

function LearningsSection({ learnings, openChat }) {
  const [filter, setFilter] = useStatePf('all');
  const items = learnings.items.filter(it => {
    if (filter === 'all')      return true;
    if (filter === 'mistakes') return ['missed-buy','missed-sell','sold-too-early','sizing'].includes(it.kind);
    if (filter === 'wins')     return ['good-call','avoided-loss'].includes(it.kind);
    return true;
  });

  return (
    <div className="card" style={{ overflow:'hidden' }}>
      {/* Header — title + summary stats + filter */}
      <div style={{
        padding:'20px 24px',
        background:'linear-gradient(180deg, var(--bg-tinted) 0%, transparent 100%)',
        borderBottom:'1px solid var(--border)'
      }}>
        <div className="learnings-header" style={{ display:'flex', alignItems:'center', gap:12, marginBottom:14 }}>
          <span style={{
            width:34, height:34, borderRadius:10,
            background:'linear-gradient(135deg, var(--violet-soft), var(--cyan-soft))',
            color:'var(--violet)', display:'grid', placeItems:'center', flexShrink:0
          }}><Icon.Sparkles size={16}/></span>
          <div style={{ flex:1, minWidth:0 }}>
            <div className="eyebrow" style={{ marginBottom:2 }}>Lessons from your history</div>
            <div style={{ fontSize:18, fontWeight:700, letterSpacing:'-0.01em' }}>
              {learnings.summary.actionsReviewed} actions reviewed · agent agreement {(learnings.summary.accuracyVsAgent*100).toFixed(0)}%
            </div>
          </div>
          <FilterTabs value={filter} onChange={setFilter}/>
        </div>

        <div style={{ display:'grid', gridTemplateColumns:'var(--grid-agents)', gap:10 }}>
          <SummaryStat
            label="Missed gain"
            value={'+₹'+learnings.summary.missedGain.toLocaleString('en-IN')}
            sub="Trades you didn't take"
            tone="warn"
          />
          <SummaryStat
            label="Avoided loss"
            value={'+₹'+learnings.summary.avoidedLoss.toLocaleString('en-IN')}
            sub="Smart skips & exits"
            tone="good"
          />
          <SummaryStat
            label="Realized loss"
            value={'-₹'+Math.abs(learnings.summary.realizedLoss).toLocaleString('en-IN')}
            sub="Booked drawdowns"
            tone="bad"
          />
        </div>
      </div>

      {/* Pattern strip — short rules derived from full history */}
      <div style={{
        padding:'16px 24px', borderBottom:'1px solid var(--border)',
        background:'var(--bg-base)'
      }}>
        <div className="eyebrow" style={{ marginBottom:10 }}>Your patterns</div>
        <div style={{ display:'grid', gridTemplateColumns:'var(--grid-suggestions)', gap:10 }}>
          {learnings.patterns.map(p => <PatternChip key={p.id} p={p}/>)}
        </div>
      </div>

      {/* Lesson cards */}
      <div style={{ padding:'20px 24px', display:'flex', flexDirection:'column', gap:12 }}>
        {items.length === 0 && (
          <div style={{ textAlign:'center', padding:'40px 0', color:'var(--ink-3)', fontSize:13 }}>
            No lessons in this filter yet.
          </div>
        )}
        {items.map(it => <LessonCard key={it.id} it={it} openChat={openChat}/>)}
      </div>
    </div>
  );
}

function FilterTabs({ value, onChange }) {
  const opts = [
    { k:'all',      label:'All' },
    { k:'mistakes', label:'Mistakes' },
    { k:'wins',     label:'Wins' },
  ];
  return (
    <div className="learnings-filter" style={{ display:'flex', gap:2, padding:3, background:'var(--bg-base)', borderRadius:9, border:'1px solid var(--border)' }}>
      {opts.map(o => (
        <button key={o.k} onClick={()=>onChange(o.k)} style={{
          padding:'5px 11px', borderRadius:6, border:'none',
          fontSize:12, fontWeight:600,
          background: value===o.k ? 'var(--bg-surface)' : 'transparent',
          color: value===o.k ? 'var(--ink-1)' : 'var(--ink-3)',
          boxShadow: value===o.k ? 'var(--shadow-sm)' : 'none',
          cursor:'pointer', transition:'all .15s'
        }}>{o.label}</button>
      ))}
    </div>
  );
}

function SummaryStat({ label, value, sub, tone }) {
  const fg = tone==='good' ? 'var(--buy-strong)' : tone==='bad' ? 'var(--sell-strong)' : 'var(--neutral)';
  const bg = tone==='good' ? 'var(--buy-soft)'   : tone==='bad' ? 'var(--sell-soft)'   : 'var(--neutral-soft)';
  return (
    <div style={{ padding:'12px 14px', borderRadius:10, background: bg, borderLeft:`3px solid ${fg}` }}>
      <div style={{ fontSize:10, color:'var(--ink-3)', textTransform:'uppercase', letterSpacing:'.12em', fontWeight:700, marginBottom:4 }}>{label}</div>
      <div className="mono" style={{ fontSize:18, fontWeight:800, color: fg, letterSpacing:'-0.01em' }}>{value}</div>
      <div style={{ fontSize:11, color:'var(--ink-3)', marginTop:2 }}>{sub}</div>
    </div>
  );
}

function PatternChip({ p }) {
  const fg = p.kind==='good' ? 'var(--buy-strong)' : 'var(--sell-strong)';
  return (
    <div style={{
      padding:'10px 12px', borderRadius:9, background:'var(--bg-surface)',
      border:'1px solid var(--border)', display:'flex', alignItems:'center', gap:10
    }} title={p.detail}>
      <span style={{
        width:30, height:30, flexShrink:0, borderRadius:8,
        background: p.kind==='good' ? 'var(--buy-soft)' : 'var(--sell-soft)',
        color: fg, display:'grid', placeItems:'center'
      }}>
        {p.kind==='good' ? <Icon.Trend size={14}/> : <Icon.TrendDown size={14}/>}
      </span>
      <div style={{ flex:1, minWidth:0 }}>
        <div style={{ fontSize:12, fontWeight:600, color:'var(--ink-1)', whiteSpace:'nowrap', overflow:'hidden', textOverflow:'ellipsis' }}>{p.label}</div>
        <div style={{ display:'flex', alignItems:'center', gap:6, marginTop:3 }}>
          <div style={{ flex:1, height:4, background:'var(--bg-tinted)', borderRadius:999, overflow:'hidden' }}>
            <div style={{ width:(p.rate*100)+'%', height:'100%', background: fg, borderRadius:999 }}/>
          </div>
          <span className="mono" style={{ fontSize:11, fontWeight:700, color: fg, minWidth:32, textAlign:'right' }}>
            {(p.rate*100).toFixed(0)}%
          </span>
        </div>
      </div>
    </div>
  );
}

function LessonCard({ it, openChat }) {
  const kindMeta = {
    'missed-buy':     { label:'Missed buy',       fg:'var(--sell-strong)', bg:'var(--sell-soft)',     icon:<Icon.TrendDown size={13}/> },
    'missed-sell':    { label:'Missed sell',      fg:'var(--sell-strong)', bg:'var(--sell-soft)',     icon:<Icon.TrendDown size={13}/> },
    'sold-too-early': { label:'Sold too early',   fg:'var(--neutral)',     bg:'var(--neutral-soft)',  icon:<Icon.Compass size={13}/> },
    'sizing':         { label:'Concentration',    fg:'var(--neutral)',     bg:'var(--neutral-soft)',  icon:<Icon.Compass size={13}/> },
    'good-call':      { label:'Good call',        fg:'var(--buy-strong)',  bg:'var(--buy-soft)',      icon:<Icon.Trend size={13}/> },
    'avoided-loss':   { label:'Avoided loss',     fg:'var(--buy-strong)',  bg:'var(--buy-soft)',      icon:<Icon.Trend size={13}/> },
  }[it.kind];

  const isPositive = it.costValue > 0 && (it.kind==='good-call' || it.kind==='avoided-loss');
  const costColor = isPositive ? 'var(--buy-strong)'
                  : it.costValue < 0 ? 'var(--sell-strong)'
                  : it.kind==='missed-buy' ? 'var(--sell-strong)'
                  : it.kind==='sold-too-early' ? 'var(--neutral)'
                  : 'var(--ink-2)';

  return (
    <div style={{
      padding:'16px 18px', borderRadius:12,
      background:'var(--bg-base)',
      border:'1px solid var(--border)',
      display:'grid', gridTemplateColumns:'auto 1fr', gap:14
    }}>
      {/* Left rail — ticker + kind chip */}
      <div style={{ display:'flex', flexDirection:'column', alignItems:'center', gap:8, paddingTop:2 }}>
        <div style={{
          width:44, height:44, borderRadius:10,
          background:'linear-gradient(135deg, var(--cyan-soft), var(--violet-soft))',
          display:'grid', placeItems:'center', fontWeight:800, color:'var(--cyan)', fontSize:15
        }}>{it.sym[0]}</div>
        <span className="mono" style={{ fontSize:10, fontWeight:700, color:'var(--ink-2)' }}>{it.sym}</span>
      </div>

      <div style={{ minWidth:0 }}>
        {/* Header line */}
        <div style={{ display:'flex', alignItems:'center', gap:8, flexWrap:'wrap', marginBottom:6 }}>
          <span style={{
            display:'inline-flex', alignItems:'center', gap:5,
            padding:'3px 9px', borderRadius:999,
            background: kindMeta.bg, color: kindMeta.fg,
            fontSize:10, fontWeight:700, letterSpacing:'.04em', textTransform:'uppercase'
          }}>{kindMeta.icon} {kindMeta.label}</span>
          <span style={{ fontSize:11, color:'var(--ink-3)' }}>{it.when}</span>
          {it.severity==='high' && (
            <span style={{ fontSize:10, fontWeight:700, padding:'2px 7px', borderRadius:5,
              background:'var(--sell-soft)', color:'var(--sell-strong)', letterSpacing:'.06em' }}>HIGH</span>
          )}
        </div>

        <div style={{ fontSize:14, fontWeight:700, color:'var(--ink-1)', lineHeight:1.4, marginBottom:6 }}>
          {it.title}
        </div>

        <div style={{ fontSize:13, color:'var(--ink-2)', lineHeight:1.55, marginBottom:10 }}>
          {it.what}
        </div>

        <div style={{ display:'flex', alignItems:'center', gap:6, marginBottom:12, fontSize:12 }}>
          <span style={{ color:'var(--ink-3)' }}>Impact:</span>
          <span className="mono" style={{ fontWeight:700, color: costColor }}>{it.cost}</span>
        </div>

        {/* Agent snapshot — what the agents looked like at decision time */}
        {it.agentSnapshot && it.agentSnapshot.length > 0 && (
          <div style={{
            padding:'10px 12px', background:'var(--bg-tinted)', borderRadius:9,
            display:'flex', alignItems:'center', gap:14, flexWrap:'wrap', marginBottom:12
          }}>
            <span style={{ fontSize:10, color:'var(--ink-3)', textTransform:'uppercase', letterSpacing:'.1em', fontWeight:700 }}>
              At decision
            </span>
            {it.agentSnapshot.map((a,i) => (
              <span key={i} style={{ display:'flex', alignItems:'center', gap:6, fontSize:11 }}>
                <span style={{ color:'var(--ink-2)' }}>{a.n}</span>
                <span className="mono" style={{
                  fontWeight:700,
                  color: a.v >= 0.65 ? 'var(--buy-strong)' : a.v >= 0.5 ? 'var(--neutral)' : 'var(--sell-strong)'
                }}>{a.v.toFixed(2)}</span>
              </span>
            ))}
          </div>
        )}

        {/* Lesson body */}
        <div style={{
          padding:'12px 14px', borderRadius:10,
          background:'linear-gradient(135deg, var(--violet-soft) 0%, var(--cyan-soft) 100%)',
          borderLeft:'3px solid var(--violet)',
          display:'flex', alignItems:'flex-start', gap:10, marginBottom:12
        }}>
          <Icon.Sparkles size={14} c="var(--violet)" style={{ flexShrink:0, marginTop:3 }}/>
          <div style={{ fontSize:13, color:'var(--ink-1)', lineHeight:1.55 }}>{it.lesson}</div>
        </div>

        {/* Actions */}
        <div style={{ display:'flex', gap:8, flexWrap:'wrap' }}>
          <button style={{
            padding:'7px 12px', borderRadius:8,
            border:'1px solid var(--border-strong)', background:'var(--bg-surface)',
            fontSize:12, fontWeight:600, color:'var(--ink-1)',
            display:'flex', alignItems:'center', gap:6, cursor:'pointer'
          }}>
            <Icon.Compass size={13}/> {it.action}
          </button>
          <button onClick={openChat} style={{
            padding:'7px 12px', borderRadius:8,
            border:'1px solid var(--border)', background:'transparent',
            fontSize:12, fontWeight:600, color:'var(--ink-2)',
            display:'flex', alignItems:'center', gap:6, cursor:'pointer'
          }}>
            <Icon.Sparkles size={13}/> Ask why
          </button>
        </div>
      </div>
    </div>
  );
}

window.PortfolioPage = PortfolioPage;
