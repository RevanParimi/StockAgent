// Portfolio page — beginner-friendly view of holdings, P/L, agent take, recent activity, learnings
const { useState: useStatePf } = React;

function PortfolioPage({ onNav, openChat }) {
  const [search, setSearch] = useStatePf('');
  const [range, setRange] = useStatePf('1M');
  const p = window.PORTFOLIO;
  const ranges = window.PORTFOLIO_RANGES;
  const r = ranges[range];
  const totalReturn = p.totalValue - p.totalCost;
  const totalReturnPct = (totalReturn / p.totalCost) * 100;

  return (
    <div style={{ minHeight:'100vh', background:'var(--bg-base)' }}>
      <TopNav active="portfolio" onNav={onNav} search={search} setSearch={setSearch}/>

      <main style={{ maxWidth:1280, margin:'0 auto', padding:'var(--main-py) var(--main-px) 96px' }}>
        {/* Hero strip */}
        <section style={{
          position:'relative', overflow:'hidden', borderRadius:24, marginBottom:24,
          background:'linear-gradient(135deg, #0a1628 0%, #134e5c 50%, #1a4a73 100%)',
          color:'#f1f5f9', padding:'28px var(--main-px)',
          display:'grid', gridTemplateColumns:'var(--hero-cols)', gap:32, alignItems:'center'
        }}>
          <div style={{ position:'absolute', top:'-30%', right:'-10%', width:520, height:520, borderRadius:'50%',
            background:'radial-gradient(circle, rgba(124,58,237,.32), transparent 65%)', filter:'blur(40px)' }}/>
          <div style={{ position:'absolute', bottom:'-40%', left:'-10%', width:480, height:480, borderRadius:'50%',
            background:'radial-gradient(circle, rgba(8,145,178,.4), transparent 65%)', filter:'blur(40px)' }}/>

          <div style={{ position:'relative', zIndex:2 }}>
            <div style={{ fontSize:11, fontWeight:700, letterSpacing:'.18em', color:'#94a3b8', textTransform:'uppercase', marginBottom:8 }}>
              Portfolio · Live
            </div>
            <div style={{ display:'flex', alignItems:'baseline', gap:14, marginBottom:12 }}>
              <span className="mono" style={{ fontSize:44, fontWeight:800, letterSpacing:'-0.02em' }}>
                ₹{p.totalValue.toLocaleString('en-IN')}
              </span>
              <span style={{
                fontSize:14, fontWeight:700, padding:'4px 10px', borderRadius:8,
                background: p.dayChange >= 0 ? 'rgba(34,197,94,.18)' : 'rgba(239,68,68,.18)',
                color: p.dayChange >= 0 ? '#86efac' : '#fca5a5'
              }}>
                {p.dayChange >= 0 ? '+' : ''}₹{Math.abs(p.dayChange).toLocaleString('en-IN')} ({p.dayChangePct >= 0 ? '+':''}{p.dayChangePct.toFixed(2)}%) today
              </span>
            </div>
            <div className="pf-hero-stats" style={{ display:'flex', gap:24, color:'#cbd5e1', fontSize:13 }}>
              <Stat2 label="Invested"      value={'₹'+p.totalCost.toLocaleString('en-IN')}/>
              <Stat2 label="Total return"  value={(totalReturn>=0?'+':'')+'₹'+totalReturn.toLocaleString('en-IN')} pct={totalReturnPct}/>
              <Stat2 label="Cash"          value={'₹'+p.cash.toLocaleString('en-IN')}/>
              <Stat2 label="Holdings"      value={p.holdings.length+' stocks'}/>
            </div>
          </div>

          <div style={{ position:'relative', zIndex:2 }}>
            <div style={{
              display:'flex', alignItems:'center', justifyContent:'space-between', gap:10, marginBottom:8
            }}>
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
        </section>

        <div style={{ display:'grid', gridTemplateColumns:'var(--grid-portfolio)', gap:20 }}>
          {/* Holdings + activity column */}
          <div style={{ display:'flex', flexDirection:'column', gap:20 }}>
            <HoldingsTable holdings={p.holdings}/>
            <LearningsSection learnings={window.PORTFOLIO_LEARNINGS} openChat={openChat}/>
            <ActivityCard items={p.recentActivity}/>
          </div>

          {/* Right rail */}
          <div style={{ display:'flex', flexDirection:'column', gap:20 }}>
            <AlertsCard alerts={p.alerts}/>
            <AllocationCard holdings={p.holdings}/>
            <AskAssistantCard openChat={openChat}/>
          </div>
        </div>
      </main>
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

function HoldingsTable({ holdings }) {
  return (
    <div className="card">
      <div style={{ padding:'18px 24px', borderBottom:'1px solid var(--border)', display:'flex', alignItems:'center', gap:12 }}>
        <div className="eyebrow">Your holdings · {holdings.length}</div>
        <button style={{ marginLeft:'auto', padding:'6px 12px', border:'1px dashed var(--border-strong)', borderRadius:8,
          background:'transparent', fontSize:12, fontWeight:600, color:'var(--ink-2)', display:'flex', alignItems:'center', gap:6 }}>
          <Icon.Plus size={13}/> Add holding
        </button>
      </div>
      <div className="holdings-table-scroll">
      <table style={{ width:'100%', borderCollapse:'collapse', minWidth:600 }}>
        <thead>
          <tr style={{ fontSize:11, textTransform:'uppercase', color:'var(--ink-3)', letterSpacing:'.1em' }}>
            <th style={pfTh}>Ticker</th>
            <th style={pfTh}>Qty</th>
            <th style={pfTh}>Avg buy</th>
            <th style={pfTh}>Current</th>
            <th style={pfTh}>Value</th>
            <th style={pfTh}>P/L</th>
            <th style={pfTh}>Agent take</th>
          </tr>
        </thead>
        <tbody>
          {holdings.map(h => {
            const value = h.qty * h.currentPrice;
            const pl = h.qty * (h.currentPrice - h.avgPrice);
            const plPct = ((h.currentPrice - h.avgPrice) / h.avgPrice) * 100;
            const verdictColor = {
              'STRONG BUY':'var(--buy-strong)','BUY':'var(--buy)','NEUTRAL':'var(--neutral)','SELL':'var(--sell)','STRONG SELL':'var(--sell-strong)'
            }[h.verdict];
            return (
              <tr key={h.sym} style={{ transition:'background .15s' }}
                onMouseEnter={e=>e.currentTarget.style.background='var(--bg-tinted)'}
                onMouseLeave={e=>e.currentTarget.style.background=''}>
                <td style={pfTd}>
                  <div style={{ display:'flex', alignItems:'center', gap:10 }}>
                    <div style={{ width:32, height:32, borderRadius:8,
                      background:'linear-gradient(135deg, var(--cyan-soft), var(--violet-soft))',
                      display:'grid', placeItems:'center', fontWeight:800, color:'var(--cyan)', fontSize:13 }}>{h.sym[0]}</div>
                    <div className="mono" style={{ fontWeight:700 }}>{h.sym}</div>
                  </div>
                </td>
                <td style={pfTd}><span className="mono">{h.qty}</span></td>
                <td style={pfTd}><span className="mono">₹{h.avgPrice.toLocaleString('en-IN', {minimumFractionDigits:2})}</span></td>
                <td style={pfTd}><span className="mono">₹{h.currentPrice.toLocaleString('en-IN', {minimumFractionDigits:2})}</span></td>
                <td style={pfTd}><span className="mono" style={{ fontWeight:700 }}>₹{value.toLocaleString('en-IN', {maximumFractionDigits:0})}</span></td>
                <td style={pfTd}>
                  <div style={{ color: pl>=0 ? 'var(--buy-strong)':'var(--sell-strong)', fontWeight:700 }}>
                    <span className="mono">{pl>=0?'+':''}₹{Math.abs(pl).toLocaleString('en-IN', {maximumFractionDigits:0})}</span>
                    <div className="mono" style={{ fontSize:11, fontWeight:600 }}>{plPct>=0?'+':''}{plPct.toFixed(2)}%</div>
                  </div>
                </td>
                <td style={pfTd}>
                  <div style={{ display:'flex', alignItems:'center', gap:8 }}>
                    <span className="mono" style={{ fontWeight:700 }}>{h.agentScore.toFixed(2)}</span>
                    <span style={{ display:'inline-block', padding:'3px 8px', borderRadius:999, fontSize:10, fontWeight:700,
                      background:`color-mix(in oklab, ${verdictColor} 14%, transparent)`, color: verdictColor, letterSpacing:'.04em' }}>
                      {h.verdict}
                    </span>
                  </div>
                </td>
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
  const iconMap = {
    buy:   { icon:<Icon.Plus size={14}/>,   bg:'var(--buy-soft)',     fg:'var(--buy-strong)',  label:'Bought' },
    sell:  { icon:<Icon.TrendDown size={14}/>, bg:'var(--sell-soft)', fg:'var(--sell-strong)', label:'Sold' },
    agent: { icon:<Icon.Sparkles size={14}/>, bg:'var(--violet-soft)', fg:'var(--violet)',     label:'Agent' },
  };
  return (
    <div className="card" style={{ padding:24 }}>
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
                  {it.qty && <span style={{ color:'var(--ink-3)', fontWeight:500 }}> · {it.qty} @ ₹{it.price.toLocaleString('en-IN', {minimumFractionDigits:2})}</span>}
                </div>
                {it.text && <div style={{ fontSize:12, color:'var(--ink-3)', marginTop:2 }}>{it.text}</div>}
              </div>
              <span style={{ fontSize:11, color:'var(--ink-3)', whiteSpace:'nowrap' }}>{it.t}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function AlertsCard({ alerts }) {
  return (
    <div className="card" style={{ padding:20 }}>
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
  const total = holdings.reduce((s,h) => s + h.qty * h.currentPrice, 0);
  const segments = holdings.map(h => ({
    sym: h.sym,
    pct: ((h.qty * h.currentPrice) / total) * 100,
  }));
  const colors = ['#0891b2','#7c3aed','#16a34a','#d97706','#dc2626','#475569'];

  return (
    <div className="card" style={{ padding:20 }}>
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
