# Portfolio Page Live Wiring Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire the prototype Portfolio page to the real `/portfolio` API so real multi-sector holdings (with live P&L, advisor verdicts, add/remove) replace the hardcoded 5-automobile mock.

**Architecture:** The FastAPI backend already exposes `GET /portfolio` (mark-to-market holdings), `POST/DELETE /portfolio/holdings`, and `GET /portfolio/digest/latest` (per-holding advisor verdicts). The only backend change is making `sector` optional on the POST bodies (resolved server-side via `SectorRegistry.resolve`). The frontend work is all in `src/frontend/prototypes/portfolio.jsx`: a fetch hook with four render states (loading / live / live-empty / demo-fallback), client-side hero totals, a working Add-holding modal with `/ui/search` autocomplete, per-row delete, digest-driven alerts, and hiding sections that have no real data source.

**Tech Stack:** FastAPI + Pydantic (backend), pytest + TestClient (tests), plain React-via-Babel JSX prototype (`window.*` globals, no build step, no JS test harness — frontend verified by driving the app).

**Spec:** `docs/superpowers/specs/2026-07-10-portfolio-page-live-wiring-design.md`

## Global Constraints

- Prototype JSX files use per-file React hook aliases (e.g. `const { useState: useStatePf } = React;`) because all files share one global scope — follow this pattern for any new hook import in `portfolio.jsx`.
- Never flash mock ₹ values before live data: loading state shows a skeleton, not `window.PORTFOLIO`.
- Demo/mock data may render ONLY in the demo-fallback state, and must be labeled with a visible "Demo data" pill.
- Holdings with `last_close: null` render "—" for price/value/P&L and are excluded from hero totals.
- All P&L/value math uses `adj_qty` / `adj_avg_price` (corp-action-adjusted), never raw `qty`/`avg_buy_price`.
- Backward compatibility: explicit `sector` in POST bodies must keep working unchanged.
- The app serves the prototype at `http://localhost:8001/app` via `python -m services.api.server` from the repo root.
- Frontend inline-style idiom: keep the existing single-quote inline `style={{ }}` conventions of the file; CSS vars like `var(--ink-2)`, `var(--buy-strong)` for colors.

---

### Task 1: Backend — optional `sector` resolved via SectorRegistry

**Files:**
- Modify: `services/api/routes/portfolio_api.py` (models at lines 59–70; handlers `add_holding` ~99–139, `add_watchlist` ~159–182)
- Test: `tests/unit/test_portfolio_api.py`

**Interfaces:**
- Consumes: `SectorRegistry.resolve(ticker: str) -> str` from `backend.sectors.registry` (maps ~200 tickers; unknown symbols fall back to `"automobile"`).
- Produces: `POST /portfolio/holdings` and `POST /portfolio/watchlist` accept bodies **without** `sector`. Task 4's modal relies on this (it never sends `sector`).

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_portfolio_api.py`:

```python
def test_add_holding_sector_omitted_resolves_via_registry(client):
    resp = client.post("/portfolio/holdings", json={
        "symbol": "TCS", "qty": 5, "buy_date": "2026-07-01", "price": 3500.0,
    })
    assert resp.status_code == 200
    assert resp.json()["holding"]["sector"] == "it_sector"


def test_add_holding_unknown_symbol_sector_defaults_to_automobile(client):
    resp = client.post("/portfolio/holdings", json={
        "symbol": "ZZZUNKNOWN", "qty": 1, "buy_date": "2026-07-01", "price": 10.0,
    })
    assert resp.status_code == 200
    assert resp.json()["holding"]["sector"] == "automobile"


def test_watchlist_sector_omitted_resolves_via_registry(client):
    resp = client.post("/portfolio/watchlist", json={
        "symbol": "HDFCBANK", "reason": "quality bank",
    })
    assert resp.status_code == 200
    assert resp.json()["watchlist_item"]["sector"] == "banking_bfsi"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/unit/test_portfolio_api.py -v -k "sector_omitted or unknown_symbol"`
Expected: 3 FAILED — Pydantic 422 "Field required" for missing `sector` (the request never reaches the handler).

- [ ] **Step 3: Implement — optional sector + shared resolver**

In `services/api/routes/portfolio_api.py`:

Add import (with the other project imports, after `from core.config import settings`):

```python
from backend.sectors.registry import SectorRegistry
```

Change both models:

```python
class HoldingIn(BaseModel):
    symbol: str
    sector: str | None = None          # omitted -> SectorRegistry.resolve(symbol)
    qty: float
    buy_date: str                      # ISO date
    price: float | None = None         # omitted -> real NSE close on buy_date


class WatchlistIn(BaseModel):
    symbol: str
    sector: str | None = None          # omitted -> SectorRegistry.resolve(symbol)
    reason: str = ""
```

Add a module-level helper (below `_store`):

```python
def _resolve_sector(symbol: str, sector: str | None) -> str:
    """Explicit sector wins; otherwise the registry maps the symbol."""
    if sector and sector.strip():
        return sector.strip().lower()
    return SectorRegistry.resolve(symbol)
```

In `add_holding`, replace `sector = body.sector.strip().lower()` with:

```python
    sector = _resolve_sector(symbol, body.sector)
```

In `add_watchlist`, replace `sector = body.sector.strip().lower()` with the same line. Leave the existing `is_valid_sector(sector)` checks in both handlers untouched (registry output like `it_sector` passes it).

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/unit/test_portfolio_api.py -v`
Expected: ALL pass (the 3 new tests plus all pre-existing ones — explicit-sector tests prove backward compat).

- [ ] **Step 5: Commit**

```bash
git add services/api/routes/portfolio_api.py tests/unit/test_portfolio_api.py
git commit -m "feat(portfolio-api): sector optional on holdings/watchlist POST — resolved via SectorRegistry"
```

---

### Task 2: Frontend — live fetch hook, render states, hero

**Files:**
- Modify: `src/frontend/prototypes/portfolio.jsx` (top of file: hook alias line 2, `PortfolioPage` lines 4–88)

**Interfaces:**
- Consumes: `GET /portfolio` → `{ holdings: [{symbol, sector, adj_qty, adj_avg_price, buy_date, last_close, pnl_pct, ...}], watchlist, ... }`; `GET /portfolio/digest/latest` → `{ date, holdings: [{symbol, verdict, close, pnl_pct, reason, notes}], escalations: [sym], portfolio_value, ... }` (404 when no advisor run yet).
- Produces (used by Tasks 3–5): `usePortfolioLive()` returning `{ status: 'loading'|'live'|'demo', holdings: ViewHolding[], digest: object|null, reload: () => Promise<void> }` where `ViewHolding = { sym, sector?, qty, avgPrice, currentPrice|null, pnlPct|null, buyDate?, agentScore?, verdict? }` (mock rows already match this shape minus sector/pnlPct). Also `digestAlerts(digest) -> [{sym, kind:'warn'|'good', text}]`.

- [ ] **Step 1: Add the hook, adapter, and digest-alerts helper**

At the top of `portfolio.jsx`, replace line 2 with:

```jsx
const { useState: useStatePf, useEffect: useEffectPf, useRef: useRefPf } = React;
```

Insert above `function PortfolioPage`:

```jsx
// ── Live data ──────────────────────────────────────────────────────────────
// GET /portfolio (+ digest). status: 'loading' | 'live' | 'demo'.
// Demo (mock) data renders ONLY when the API is unreachable, or with ?demo=1.

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
  const [state, setState] = useStatePf({ status: 'loading', holdings: [], digest: null });

  const load = async () => {
    if (new URLSearchParams(location.search).get('demo') === '1') {
      setState({ status: 'demo', holdings: window.PORTFOLIO.holdings, digest: null });
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
      setState({ status: 'live', holdings: (p.holdings || []).map(adaptHolding), digest });
    } catch (e) {
      console.warn('[Portfolio] live fetch failed — demo fallback.', e);
      setState({ status: 'demo', holdings: window.PORTFOLIO.holdings, digest: null });
    }
  };

  useEffectPf(() => { load(); }, []);
  return { ...state, reload: load };
}
```

- [ ] **Step 2: Rewrite `PortfolioPage` around the three states**

Replace the whole `PortfolioPage` function with:

```jsx
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
          display:'grid', gridTemplateColumns: isDemo ? 'var(--hero-cols)' : '1fr', gap:32, alignItems:'center'
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
                  DEMO DATA — API UNREACHABLE
                </span>
              )}
            </div>
            <div className="pf-hero-value-row" style={{ display:'flex', alignItems:'baseline', gap:14, marginBottom:12, flexWrap:'wrap' }}>
              <span className="pf-hero-value mono" style={{ fontSize:44, fontWeight:800, letterSpacing:'-0.02em' }}>
                ₹{Math.round(totalValue).toLocaleString('en-IN')}
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
            </div>
            <div className="pf-hero-stats" style={{ display:'flex', gap:24, color:'#cbd5e1', fontSize:13, flexWrap:'wrap' }}>
              <Stat2 label="Invested"      value={'₹'+Math.round(invested).toLocaleString('en-IN')}/>
              <Stat2 label="Total return"  value={(totalReturn>=0?'+':'-')+'₹'+Math.abs(Math.round(totalReturn)).toLocaleString('en-IN')} pct={totalReturnPct}/>
              {isDemo && <Stat2 label="Cash" value={'₹'+demo.cash.toLocaleString('en-IN')}/>}
              <Stat2 label="Holdings"      value={holdings.length+' stocks'}/>
              {isLive && marked.length < holdings.length && (
                <Stat2 label="Unpriced" value={(holdings.length - marked.length)+' awaiting close'}/>
              )}
            </div>
          </div>

          {isDemo && (
            <div className="pf-hero-chart" style={{ position:'relative', zIndex:2 }}>
              <div style={{ display:'flex', alignItems:'center', justifyContent:'space-between', gap:10, marginBottom:8 }}>
                <div>
                  <div style={{ fontSize:11, color:'#94a3b8' }}>Value over {r.label}</div>
                  <div style={{ fontSize:13, fontWeight:700, color: r.change>=0 ? '#86efac' : '#fca5a5' }}>
                    {r.change>=0?'+':''}{r.change.toFixed(2)}%
                  </div>
                </div>
                <DarkRangeTabs value={range} onChange={setRange}/>
              </div>
              <Sparkline values={r.points} height={92} color="#22d3ee"/>
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
        Add your first holding — any tracked stock across automobile, banking, IT and
        renewable energy. Mock money, real prices, real agent analysis.
      </p>
      <button onClick={onAdd} style={{ padding:'10px 18px', border:'none', borderRadius:10,
        background:'linear-gradient(135deg, var(--cyan), var(--violet))', color:'#fff',
        fontSize:13, fontWeight:700, cursor:'pointer', display:'inline-flex', alignItems:'center', gap:8 }}>
        <Icon.Plus size={14}/> Add holding
      </button>
    </div>
  );
}
```

Note: `AllocationCard` needs one guard for null closes. In `AllocationCard`, change the two `h.qty * h.currentPrice` computations to `h.qty * (h.currentPrice || 0)` (both the `total` reduce at line ~260 and the `segments` map).

Note: `AddHoldingModal` does not exist until Task 4 — for this task's verification, temporarily stub it above `PortfolioPage`:

```jsx
function AddHoldingModal({ onClose, onAdded }) { return null; }  // Task 4 replaces this
```

`pulse` keyframes: check `styles.css` for an existing `@keyframes pulse`; if absent, add to `src/frontend/prototypes/styles.css`:

```css
@keyframes pulse { 0%,100% { opacity:.55; } 50% { opacity:1; } }
```

- [ ] **Step 3: Verify in the browser — live-empty, live-with-data, demo**

Start the server: `python -m services.api.server` (from repo root; port 8001).

1. Open `http://localhost:8001/app` → Portfolio tab. Local store is empty → expect brief skeleton, then **empty state** with "Add holding" CTA. No fake ₹4.8L anywhere, no cash tile, no range chart, no Recent activity.
2. Seed two holdings across sectors (explicit price avoids live NSE dependency):
```bash
curl -s -X POST http://localhost:8001/portfolio/holdings -H "Content-Type: application/json" -d '{"symbol":"TCS","qty":5,"buy_date":"2026-07-01","price":3500}'
curl -s -X POST http://localhost:8001/portfolio/holdings -H "Content-Type: application/json" -d '{"symbol":"MARUTI","qty":2,"buy_date":"2026-07-01","price":12000}'
```
3. Reload → expect hero "Portfolio · Live", Invested ₹41,500, holdings table with TCS + MARUTI (current/P&L may be "—" offline — fine), Allocation card with both.
4. Demo fallback: open `http://localhost:8001/app?demo=1` → expect the old mock page plus amber "DEMO DATA" pill, cash tile, chart, activity all back.
5. Clean up: `curl -s -X DELETE http://localhost:8001/portfolio/holdings/TCS` and same for `MARUTI` (or leave for later tasks' testing).

- [ ] **Step 4: Commit**

```bash
git add src/frontend/prototypes/portfolio.jsx src/frontend/prototypes/styles.css
git commit -m "feat(portfolio-ui): live /portfolio fetch with loading/live/empty/demo states + real hero totals"
```

---

### Task 3: Holdings table — live columns, digest verdicts, per-row remove

**Files:**
- Modify: `src/frontend/prototypes/portfolio.jsx` (`HoldingsTable`, lines ~126–196 pre-Task-2)

**Interfaces:**
- Consumes: `holdings: ViewHolding[]`, `digest`, `isLive`, `onAdd()`, `onRemoved()` props (wired by Task 2). `window.TICKERS` (live-hydrated by bootstrap) for verdict fallback.
- Produces: `DELETE /portfolio/holdings/{sym}` calls followed by `onRemoved()`.

- [ ] **Step 1: Replace `HoldingsTable` with the live-aware version**

```jsx
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
  const t = (window.TICKERS || []).find(t => t.sym === h.sym);
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
                  {pl == null ? <span style={{ color:'var(--ink-3)' }}>—</span> : (
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
                  ) : <span style={{ color:'var(--ink-3)' }}>—</span>}
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
```

(This fully replaces the old `HoldingsTable`; the old inline `verdictColor` map is superseded by `PF_VERDICT_COLORS`. Demo rows still render because `agentTake` returns their embedded `verdict`/`agentScore`, and `h.pnlPct` is undefined for them so the computed fallback kicks in.)

- [ ] **Step 2: Verify in the browser**

With the server running and the two seeded holdings from Task 2 (re-seed if cleaned up):

1. `http://localhost:8001/app` → table shows TCS (sector subtext "it sector") and MARUTI ("automobile"); Current/P&L show real numbers or "—" (offline); Agent take shows composite verdict chip for MARUTI if bootstrap TICKERS include it, "—" otherwise. No digest exists locally → no advisor verdicts; that's expected.
2. Click the ✕ on TCS → confirm dialog → row disappears, holdings count and hero totals update.
3. `?demo=1` → 5 mock rows render exactly as before (scores + verdict chips, no ✕ column, Add button disabled).

- [ ] **Step 3: Commit**

```bash
git add src/frontend/prototypes/portfolio.jsx
git commit -m "feat(portfolio-ui): live holdings table — digest/composite agent take, sector tags, row delete"
```

---

### Task 4: Add-holding modal with symbol autocomplete

**Files:**
- Modify: `src/frontend/prototypes/portfolio.jsx` (replace the Task-2 stub `AddHoldingModal`)

**Interfaces:**
- Consumes: `GET /ui/search?q=` → `{ results: [{sym, name, type}] }`; `POST /portfolio/holdings` with `{symbol, qty, buy_date, price?}` — **no `sector`** (Task 1). 422 responses carry `detail` string.
- Produces: `AddHoldingModal({ onClose, onAdded })` — calls `onAdded()` after a successful POST.

- [ ] **Step 1: Implement the modal**

Replace the stub with (modal pattern mirrors home.jsx's fixed backdrop + panel; autocomplete mirrors TopNav's 350 ms debounce):

```jsx
function AddHoldingModal({ onClose, onAdded }) {
  const [sym, setSym] = useStatePf('');
  const [results, setResults] = useStatePf([]);
  const [qty, setQty] = useStatePf('');
  const [buyDate, setBuyDate] = useStatePf(new Date().toISOString().slice(0,10));
  const [price, setPrice] = useStatePf('');
  const [err, setErr] = useStatePf('');
  const [saving, setSaving] = useStatePf(false);
  const timerRef = useRefPf(null);

  const searchSym = (val) => {
    setSym(val.toUpperCase());
    setErr('');
    clearTimeout(timerRef.current);
    if (val.length < 2) { setResults([]); return; }
    timerRef.current = setTimeout(async () => {
      try {
        const res = await fetch(`/ui/search?q=${encodeURIComponent(val)}`);
        if (res.ok) setResults((await res.json()).results || []);
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
        setErr(typeof d.detail === 'string' ? d.detail : `HTTP ${res.status}`);
        return;
      }
      onAdded();
    } catch (e) {
      setErr('Network error: ' + e.message);
    } finally {
      setSaving(false);
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
            <input value={qty} onChange={e=>setQty(e.target.value)} type="number" min="0" step="any" placeholder="10" className="mono" style={field}/>
          </div>
          <div>
            <label style={label}>Buy date</label>
            <input value={buyDate} onChange={e=>setBuyDate(e.target.value)} type="date" className="mono" style={field}/>
          </div>
        </div>

        <div style={{ marginBottom:18 }}>
          <label style={label}>Buy price (optional)</label>
          <input value={price} onChange={e=>setPrice(e.target.value)} type="number" min="0" step="any"
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
```

- [ ] **Step 2: Verify in the browser**

Server running, `http://localhost:8001/app`:

1. Click "Add holding" (header button or empty-state CTA) → modal opens.
2. Type `hdfc` → autocomplete lists HDFCBANK etc.; pick it; qty `10`, keep today's date, price `1650` (explicit price avoids the live NSE lookup offline) → "Add to portfolio" → modal closes, table now shows HDFCBANK with sector subtext "banking bfsi", hero totals updated. **This is a non-auto stock appearing on the page — the original ask.**
3. Error path: reopen, symbol `TCS`, qty `5`, date `2026-13-40` → inline red error with the API's "Invalid buy_date" detail; modal stays open.
4. Blank-price path (only if online): add `SUZLON` qty `100` with price blank → priced at real close.

- [ ] **Step 3: Commit**

```bash
git add src/frontend/prototypes/portfolio.jsx
git commit -m "feat(portfolio-ui): Add-holding modal — /ui/search autocomplete, optional price, sector auto-resolved"
```

---

### Task 5: Full-suite run, digest-alerts spot-check, docs

**Files:**
- Modify: `src/frontend/prototypes/UI_SPEC.md` (Portfolio page section), `CODEBASE.md` (if it describes the portfolio page as mock)

**Interfaces:**
- Consumes: everything above.
- Produces: green test suite + updated docs; branch ready for review/merge.

- [ ] **Step 1: Digest-alerts spot-check (no advisor run needed)**

`digestAlerts` + digest verdict join can be exercised by dropping a fixture digest where the store reads it (`PortfolioStore.load_latest_digest` reads the lexically-latest `data/portfolio/primary/digests/<YYYY-MM-DD>.json`). Create `data/portfolio/primary/digests/2026-07-10.json` with this minimal `build_digest`-shaped content:

```json
{
  "date": "2026-07-10",
  "user_id": "primary",
  "portfolio_value": 100000,
  "cost_basis": 90000,
  "total_pnl_pct": 11.1,
  "holdings": [
    {"symbol": "HDFCBANK", "verdict": "HOLD", "close": 1700, "pnl_pct": 3.0, "reason": "Stable NIMs; no action needed.", "notes": []},
    {"symbol": "MARUTI",   "verdict": "TRIM", "close": 12400, "pnl_pct": 3.3, "reason": "Extended vs envelope; consider trimming.", "notes": []}
  ],
  "escalations": ["MARUTI"]
}
```

Reload the page → "What your agents are flagging" shows MARUTI first (warn tone) then HDFCBANK (good tone); the table's Agent take column shows TRIM/HOLD chips with reasons on hover. Delete the fixture file afterwards.

- [ ] **Step 2: Run the full test suite**

Run: `python -m pytest tests/ -q`
Expected: baseline all-green (285+ passed / 7 skipped as of 2026-07) plus the 3 new Task-1 tests. Any new failure = fix before proceeding.

- [ ] **Step 3: Update docs**

In `src/frontend/prototypes/UI_SPEC.md`: update the Portfolio page row/section — data source is now `GET /portfolio` + `GET /portfolio/digest/latest` with mock fallback (`?demo=1` forces it); "Add holding" posts to `/portfolio/holdings`; hidden-when-live sections listed. In `CODEBASE.md`: if the prototype/portfolio description mentions mock-only, add one line noting the live wiring.

- [ ] **Step 4: Commit**

```bash
git add src/frontend/prototypes/UI_SPEC.md CODEBASE.md
git commit -m "docs(portfolio): UI_SPEC + CODEBASE — portfolio page now live-wired to /portfolio API"
```

---

## Out of scope (per spec)

Value-history endpoint/range chart, cash & day-change tiles, activity feed from advice ledger, auth lockdown, React web app.
