// RL Monitor screen — Reinforcement Learning feedback loop visualiser
// Follows the exact same patterns as home.jsx / agents-page.jsx

const { useState: useStateRL, useEffect: useEffectRL, useRef: useRefRL } = React;

// ── Helpers ─────────────────────────────────────────────────────────────────
function scoreColorRL(pct) {
  if (pct >= 80) return 'var(--buy-strong)';
  if (pct >= 65) return 'var(--buy)';
  if (pct >= 50) return 'var(--neutral)';
  return 'var(--sell-strong)';
}

const MISS_COLORS = {
  direction_flip:  '#dc2626',
  macro_surprise:  '#7c3aed',
  timing:          '#d97706',
  magnitude:       '#0891b2',
  data_gap:        '#64748b',
  data_stale:      '#94a3b8',
  external_shock:  '#475569',
};

const AGENT_LABELS_RL = {
  sales_demand:       'Sales & Demand',
  fundamentals:       'Fundamentals',
  pattern_analysis:   'Pattern Analysis',
  raw_materials:      'Raw Materials',
  sentiment:          'Sentiment',
  policy_regulatory:  'Policy & Regulatory',
  competitive_intel:  'Competitive Intel',
  risk_macro:         'Risk & Macro',
};

// ── Tiny SVG line chart (predictions vs actual) ──────────────────────────────
function PredictionChart({ predictions }) {
  if (!predictions || predictions.length < 2) return (
    <div style={{ height:200, display:'flex', alignItems:'center', justifyContent:'center' }}>
      <p style={{ color:'var(--ink-3)', fontSize:13 }}>No prediction data yet.</p>
    </div>
  );

  const W = 640, H = 160, pad = { l:48, r:16, t:12, b:28 };
  const iW = W - pad.l - pad.r, iH = H - pad.t - pad.b;
  const actuals = predictions.filter(p => p.actual != null).map(p => p.actual);
  const preds   = predictions.map(p => p.predicted);
  const all     = [...actuals, ...preds].filter(Boolean);
  const minV = Math.min(...all) * 0.998;
  const maxV = Math.max(...all) * 1.002;
  const n = predictions.length;
  const xp = i => pad.l + (i / (n - 1)) * iW;
  const yp = v => pad.t + (1 - (v - minV) / (maxV - minV)) * iH;

  const predPath = 'M ' + predictions.map((p, i) => `${xp(i).toFixed(1)},${yp(p.predicted).toFixed(1)}`).join(' L ');
  const actPoints = predictions.filter(p => p.actual != null);
  const actPath = actPoints.length > 1
    ? 'M ' + actPoints.map((p, i) => {
        const origIdx = predictions.indexOf(p);
        return `${xp(origIdx).toFixed(1)},${yp(p.actual).toFixed(1)}`;
      }).join(' L ')
    : null;

  const ticks = [0, Math.floor(n / 2), n - 1];

  return (
    <svg width="100%" viewBox={`0 0 ${W} ${H}`} style={{ display:'block' }}>
      {/* Y-axis grid lines */}
      {[0, 0.5, 1].map(t => {
        const yv = pad.t + (1 - t) * iH;
        const val = (minV + t * (maxV - minV)).toFixed(0);
        return (
          <g key={t}>
            <line x1={pad.l} x2={pad.l + iW} y1={yv} y2={yv} stroke="var(--border)" strokeDasharray="3 4"/>
            <text x={pad.l - 4} y={yv + 4} fontSize="9" textAnchor="end" fill="var(--ink-3)" fontFamily="JetBrains Mono, monospace">{val}</text>
          </g>
        );
      })}
      {/* Miss markers */}
      {predictions.map((p, i) => p.miss_type && (
        <rect key={i} x={xp(i) - 3} y={pad.t} width={6} height={iH}
              fill={MISS_COLORS[p.miss_type] || '#94a3b8'} opacity={0.12} rx={1}/>
      ))}
      {/* Prediction line */}
      <path d={predPath} fill="none" stroke="var(--cyan)" strokeWidth="2" strokeLinejoin="round" strokeDasharray="5 3" opacity={0.8}/>
      {/* Actual line */}
      {actPath && <path d={actPath} fill="none" stroke="var(--buy-strong)" strokeWidth="2" strokeLinejoin="round"/>}
      {/* Hit/miss dots on predicted */}
      {predictions.map((p, i) => p.direction_hit != null && (
        <circle key={i} cx={xp(i)} cy={yp(p.predicted)} r={3.5}
                fill={p.direction_hit ? 'var(--buy)' : 'var(--sell-strong)'}
                stroke="var(--bg-surface)" strokeWidth={1.5}/>
      ))}
      {/* X-axis dates */}
      {ticks.map(i => (
        <text key={i} x={xp(i)} y={H - 6} fontSize="9" textAnchor={i === 0 ? 'start' : i === n - 1 ? 'end' : 'middle'}
              fill="var(--ink-3)" fontFamily="JetBrains Mono, monospace">
          {predictions[i]?.date?.slice(5) || ''}
        </text>
      ))}
      {/* Legend */}
      <g transform={`translate(${pad.l}, ${pad.t - 2})`}>
        <line x1={0} y1={0} x2={18} y2={0} stroke="var(--cyan)" strokeWidth={2} strokeDasharray="5 3"/>
        <text x={22} y={4} fontSize="9" fill="var(--ink-2)" fontFamily="JetBrains Mono, monospace">Predicted</text>
        <line x1={80} y1={0} x2={98} y2={0} stroke="var(--buy-strong)" strokeWidth={2}/>
        <text x={102} y={4} fontSize="9" fill="var(--ink-2)" fontFamily="JetBrains Mono, monospace">Actual</text>
        <circle cx={170} cy={0} r={3.5} fill="var(--buy)"/>
        <text x={177} y={4} fontSize="9" fill="var(--ink-2)" fontFamily="JetBrains Mono, monospace">Hit</text>
        <circle cx={200} cy={0} r={3.5} fill="var(--sell-strong)"/>
        <text x={207} y={4} fontSize="9" fill="var(--ink-2)" fontFamily="JetBrains Mono, monospace">Miss</text>
      </g>
    </svg>
  );
}

// ── Direction Calendar ───────────────────────────────────────────────────────
function DirectionCalendar({ predictions }) {
  if (!predictions || !predictions.length) return (
    <p style={{ color:'var(--ink-3)', fontSize:13 }}>No prediction data yet.</p>
  );
  return (
    <div>
      <p className="eyebrow" style={{ marginBottom:12 }}>Each cell = one trading day · green = direction correct · red = miss</p>
      <div style={{ display:'flex', flexWrap:'wrap', gap:6 }}>
        {predictions.filter(p => p.direction_hit != null).map((p, i) => (
          <div key={i} title={`${p.date} — ${p.direction_hit ? 'Hit' : 'Miss'} (predicted ₹${p.predicted?.toFixed(0)})`}
               style={{
                 width:36, height:36, borderRadius:8, display:'flex', alignItems:'center', justifyContent:'center',
                 fontSize:10, fontFamily:'JetBrains Mono, monospace', fontWeight:700,
                 background: p.direction_hit ? 'var(--buy-soft)' : 'var(--sell-soft)',
                 color: p.direction_hit ? 'var(--buy-strong)' : 'var(--sell-strong)',
                 border: `1px solid ${p.direction_hit ? 'var(--buy)' : 'var(--sell-strong)'}`,
               }}>
            {p.date?.slice(8)}
          </div>
        ))}
        {/* pending days */}
        {predictions.filter(p => p.direction_hit === null).map((p, i) => (
          <div key={`p-${i}`} title={`${p.date} — Pending`}
               style={{
                 width:36, height:36, borderRadius:8, display:'flex', alignItems:'center', justifyContent:'center',
                 fontSize:10, fontFamily:'JetBrains Mono, monospace', fontWeight:700,
                 background:'var(--bg-tinted)', color:'var(--ink-3)',
                 border:'1px solid var(--border)',
               }}>
            {p.date?.slice(8)}
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Miss Attribution chart ───────────────────────────────────────────────────
function MissAttribution({ misses }) {
  if (!misses) return <p style={{ color:'var(--ink-3)', fontSize:13 }}>No miss data yet.</p>;

  const entries = Object.entries(misses.miss_type_counts || {}).filter(([,v]) => v > 0);
  const total = entries.reduce((s,[,v]) => s + v, 0) || 1;
  const factors = Object.entries(misses.top_missed_factors || {}).sort((a,b) => b[1]-a[1]);

  return (
    <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:24 }}>
      <div>
        <p style={{ fontSize:13, fontWeight:700, color:'var(--ink-1)', marginBottom:12 }}>Miss type breakdown</p>
        {entries.length === 0
          ? <p style={{ color:'var(--ink-3)', fontSize:13 }}>No misses recorded.</p>
          : entries.map(([type, count]) => (
            <div key={type} style={{ marginBottom:10 }}>
              <div style={{ display:'flex', justifyContent:'space-between', marginBottom:4 }}>
                <span style={{ fontSize:12, color:'var(--ink-2)' }}>{type.replace(/_/g,' ')}</span>
                <span className="mono" style={{ fontSize:12, color:'var(--ink-1)' }}>{count}×</span>
              </div>
              <div style={{ height:6, background:'var(--border)', borderRadius:999 }}>
                <div style={{
                  height:'100%', borderRadius:999,
                  width:`${(count/total)*100}%`,
                  background: MISS_COLORS[type] || 'var(--cyan)',
                }}/>
              </div>
            </div>
          ))
        }
      </div>
      <div>
        <p style={{ fontSize:13, fontWeight:700, color:'var(--ink-1)', marginBottom:12 }}>
          Top missed factors
          <span className="mono" style={{ fontSize:10, color:'var(--ink-3)', marginLeft:8 }}>
            {misses.lesson_count} lessons in ledger
          </span>
        </p>
        {factors.length === 0
          ? <p style={{ color:'var(--ink-3)', fontSize:13 }}>No miss factors yet.</p>
          : factors.map(([factor, count]) => (
            <div key={factor} style={{
              display:'flex', justifyContent:'space-between', alignItems:'center',
              padding:'8px 0', borderBottom:'1px solid var(--border)',
            }}>
              <span style={{ fontSize:13, color:'var(--ink-2)' }}>{factor.replace(/_/g,' ')}</span>
              <span className="mono" style={{ fontSize:13, fontWeight:700, color:'var(--cyan)' }}>{count}×</span>
            </div>
          ))
        }
      </div>
    </div>
  );
}

// ── Agent Weight Drift chart ─────────────────────────────────────────────────
function WeightDrift({ weights }) {
  if (!weights) return <p style={{ color:'var(--ink-3)', fontSize:13 }}>No weight data yet for this ticker.</p>;

  const agents = Object.keys(weights.current_weights);
  const maxW = Math.max(...Object.values(weights.current_weights), ...Object.values(weights.base_weights), 0.25);

  return (
    <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:24 }}>
      {/* Bar chart */}
      <div>
        <p style={{ fontSize:13, fontWeight:700, color:'var(--ink-1)', marginBottom:12 }}>Current vs base weights</p>
        {agents.map(k => {
          const cur  = weights.current_weights[k] ?? 0;
          const base = weights.base_weights[k] ?? 0;
          const diff = cur - base;
          return (
            <div key={k} style={{ marginBottom:10 }}>
              <div style={{ display:'flex', justifyContent:'space-between', marginBottom:3 }}>
                <span style={{ fontSize:11, color:'var(--ink-2)' }}>{AGENT_LABELS_RL[k] || k}</span>
                <span className="mono" style={{ fontSize:11, color: diff > 0.005 ? 'var(--buy-strong)' : diff < -0.005 ? 'var(--sell-strong)' : 'var(--ink-3)' }}>
                  {diff >= 0 ? '+' : ''}{(diff*100).toFixed(1)}%
                </span>
              </div>
              <div style={{ position:'relative', height:12, background:'var(--border)', borderRadius:999 }}>
                {/* base */}
                <div style={{ position:'absolute', top:0, left:0, height:'100%', borderRadius:999, width:`${(base/maxW)*100}%`, background:'var(--bg-tinted)' }}/>
                {/* current */}
                <div style={{ position:'absolute', top:2, left:0, height:8, borderRadius:999, width:`${(cur/maxW)*100}%`, background:'var(--cyan)' }}/>
              </div>
            </div>
          );
        })}
      </div>
      {/* History log */}
      <div>
        <p style={{ fontSize:13, fontWeight:700, color:'var(--ink-1)', marginBottom:12 }}>Weight history</p>
        <div style={{ maxHeight:280, overflowY:'auto' }}>
          {!weights.weight_history?.length
            ? <p style={{ color:'var(--ink-3)', fontSize:13 }}>No weight adjustments yet.</p>
            : [...weights.weight_history].reverse().map(h => (
              <div key={h.version} style={{ marginBottom:12, paddingBottom:12, borderBottom:'1px solid var(--border)' }}>
                <div style={{ display:'flex', gap:8, marginBottom:4 }}>
                  <span className="mono" style={{ fontSize:11, color:'var(--cyan)' }}>v{h.version}</span>
                  <span className="mono" style={{ fontSize:11, color:'var(--ink-3)' }}>{h.date}</span>
                </div>
                <p style={{ fontSize:12, color:'var(--ink-2)', margin:0, lineHeight:1.5 }}>{h.reason}</p>
              </div>
            ))
          }
        </div>
      </div>
    </div>
  );
}

// ── KPI card ─────────────────────────────────────────────────────────────────
function KpiCard({ label, value, sub, color }) {
  return (
    <div className="card" style={{ padding:'14px 16px' }}>
      <p className="eyebrow" style={{ marginBottom:6 }}>{label}</p>
      <p className="mono" style={{ fontSize:22, fontWeight:800, color: color || 'var(--ink-1)', margin:0, lineHeight:1 }}>{value}</p>
      {sub && <p style={{ fontSize:11, color:'var(--ink-3)', marginTop:4, marginBottom:0 }}>{sub}</p>}
    </div>
  );
}

// ── Main screen ──────────────────────────────────────────────────────────────
function RLMonitorPage({ onNav }) {
  const [activeTicker, setActiveTicker] = useStateRL(window.RL_TICKERS[0]?.sym || 'MARUTI');
  const [activeTab, setActiveTab] = useStateRL('predictions');
  const [data, setData] = useStateRL({ summary:null, predictions:[], weights:null, misses:null });
  const [loading, setLoading] = useStateRL(false);

  // Load mock data immediately, then try API
  useEffectRL(() => {
    const sym = activeTicker;
    // Apply mock data instantly
    setData({
      summary:     window.RL_SUMMARIES?.[sym]     || null,
      predictions: window.RL_PREDICTIONS?.[sym]   || [],
      weights:     window.RL_WEIGHTS?.[sym]        || null,
      misses:      window.RL_MISSES?.[sym]         || null,
    });
    // Try live API
    setLoading(true);
    window.rlFetch(sym).then(live => {
      setData(prev => ({
        summary:     live.summary     ?? prev.summary,
        predictions: live.predictions?.length ? live.predictions : prev.predictions,
        weights:     live.weights     ?? prev.weights,
        misses:      live.misses      ?? prev.misses,
      }));
      setLoading(false);
    });
  }, [activeTicker]);

  const tickers = window.RL_TICKERS || [];
  const { summary, predictions, weights, misses } = data;

  const now = new Date().toLocaleTimeString('en-IN', { hour:'2-digit', minute:'2-digit', timeZone:'Asia/Kolkata' });

  const tabs = [
    { k:'predictions', label:'Predictions vs actual',  icon:<Icon.Target size={14}/> },
    { k:'calendar',    label:'Direction calendar',      icon:<Icon.Calendar size={14}/> },
    { k:'misses',      label:'Miss attribution',        icon:<Icon.AlertTriangle size={14}/> },
    { k:'weights',     label:'Agent weight drift',      icon:<Icon.BarChart size={14}/> },
  ];

  return (
    <div style={{ minHeight:'100vh', background:'var(--bg-base)' }}>
      {/* TopNav — reuses home.jsx TopNav */}
      <TopNav active="rl-monitor" onNav={onNav} search="" setSearch={()=>{}}/>

      <main style={{ maxWidth:1280, margin:'0 auto', padding:'var(--main-py) var(--main-px) 96px' }}>
        {/* Header */}
        <div style={{ marginBottom:24 }}>
          <div style={{ display:'flex', alignItems:'center', gap:12, marginBottom:4 }}>
            <p className="eyebrow">RL · Monitor</p>
            <div style={{ display:'flex', alignItems:'center', gap:6 }}>
              <span style={{ width:8, height:8, borderRadius:'50%', background:'var(--buy-strong)', display:'inline-block', animation:'pulse-soft 1.5s ease-in-out infinite' }}/>
              <span style={{ fontSize:11, color:'var(--buy-strong)', fontWeight:700 }}>Scheduler live · {now} IST</span>
            </div>
          </div>
          <h1 style={{ fontSize:28, fontWeight:800, color:'var(--ink-1)', margin:'0 0 4px', letterSpacing:'-0.01em' }}>
            Reinforcement Learning Monitor
          </h1>
          <p style={{ fontSize:14, color:'var(--ink-2)', margin:0 }}>
            Daily prediction vs close, direction accuracy, miss attribution, and how RL has nudged each agent's weight
            across <strong style={{ color:'var(--ink-1)' }}>{tickers.length} Indian auto names</strong>.
          </p>
        </div>

        {/* Ticker chip rail */}
        <div style={{ display:'flex', gap:8, marginBottom:24, overflowX:'auto', paddingBottom:4 }}>
          {tickers.map(t => (
            <button key={t.sym} onClick={() => setActiveTicker(t.sym)}
                    style={{
                      flexShrink:0, padding:'8px 16px', borderRadius:999, fontSize:13, fontWeight:700,
                      fontFamily:'JetBrains Mono, monospace', letterSpacing:'0.02em', cursor:'pointer',
                      border: `1.5px solid ${activeTicker === t.sym ? t.color : 'var(--border)'}`,
                      background: activeTicker === t.sym ? `${t.color}18` : 'transparent',
                      color: activeTicker === t.sym ? t.color : 'var(--ink-2)',
                      transition:'all .15s',
                    }}>
              {t.sym}
              {!t.has_envelope && (
                <span style={{ marginLeft:6, fontSize:10, opacity:0.6 }}>no data</span>
              )}
            </button>
          ))}
        </div>

        {/* No data state */}
        {!loading && !summary && (
          <div className="card" style={{ padding:32, textAlign:'center' }}>
            <p style={{ color:'var(--ink-3)', fontSize:13 }}>
              No RL data yet for <span className="mono" style={{ color:'var(--ink-1)' }}>{activeTicker}</span>.
              Run <code style={{ background:'var(--bg-tinted)', padding:'2px 6px', borderRadius:4, fontSize:12 }}>POST /scheduler/forecast</code> to generate a prediction envelope.
            </p>
          </div>
        )}

        {/* KPI strip */}
        {summary && (
          <div style={{ display:'grid', gridTemplateColumns:'repeat(auto-fit, minmax(160px, 1fr))', gap:12, marginBottom:24 }}>
            <KpiCard
              label="Direction Hit Rate"
              value={`${summary.direction_accuracy_pct?.toFixed(1)}%`}
              sub={`${summary.direction_hits ?? '—'} of ${summary.total_days ?? summary.total_entries} days`}
              color={scoreColorRL(summary.direction_accuracy_pct)}
            />
            <KpiCard
              label="Avg Price Error"
              value={`±${(summary.avg_price_error_pct ?? 0).toFixed(2)}%`}
              sub="30-day window"
            />
            <KpiCard
              label="Total Miss Events"
              value={summary.total_entries - Math.round(summary.total_entries * summary.direction_accuracy_pct / 100) || '—'}
              sub="requires attribution"
              color="var(--sell-strong)"
            />
            <KpiCard
              label="Model Version"
              value={`v${summary.weight_version}`}
              sub={`${summary.total_entries} reviewed days`}
            />
            <KpiCard
              label="Last RL Run"
              value="Today"
              sub={`${new Date().toLocaleTimeString('en-IN',{hour:'2-digit',minute:'2-digit',timeZone:'Asia/Kolkata'})} IST`}
              color="var(--buy-strong)"
            />
            <KpiCard
              label="Current Verdict"
              value={summary.current_verdict || '—'}
              sub={`${summary.streak_days} day streak`}
            />
          </div>
        )}

        {/* Tab bar */}
        {summary && (
          <>
            <div style={{ display:'flex', gap:0, borderBottom:'1px solid var(--border)', marginBottom:20 }}>
              {tabs.map(t => (
                <button key={t.k} onClick={() => setActiveTab(t.k)}
                        style={{
                          display:'flex', alignItems:'center', gap:7, padding:'10px 18px',
                          border:'none', background:'transparent', cursor:'pointer', fontSize:13, fontWeight:600,
                          color: activeTab === t.k ? 'var(--cyan)' : 'var(--ink-3)',
                          borderBottom: activeTab === t.k ? '2px solid var(--cyan)' : '2px solid transparent',
                          marginBottom:-1, transition:'color .15s',
                        }}>
                  {t.icon} {t.label}
                </button>
              ))}
            </div>

            {/* Tab content */}
            <div className="card" style={{ padding:24 }}>
              {activeTab === 'predictions' && (
                <div>
                  <p style={{ fontSize:15, fontWeight:700, color:'var(--ink-1)', marginBottom:4 }}>Daily prediction vs actual close (₹)</p>
                  <p style={{ fontSize:12, color:'var(--ink-3)', marginBottom:16 }}>
                    {predictions.length} trading days · prediction emitted at 4:30 PM IST, reviewed against next-day close
                  </p>
                  <PredictionChart predictions={predictions}/>
                </div>
              )}

              {activeTab === 'calendar' && (
                <div>
                  <p style={{ fontSize:15, fontWeight:700, color:'var(--ink-1)', marginBottom:16 }}>Direction hit calendar</p>
                  <DirectionCalendar predictions={predictions}/>
                </div>
              )}

              {activeTab === 'misses' && (
                <div>
                  <p style={{ fontSize:15, fontWeight:700, color:'var(--ink-1)', marginBottom:16 }}>Miss attribution</p>
                  <MissAttribution misses={misses}/>
                </div>
              )}

              {activeTab === 'weights' && (
                <div>
                  <p style={{ fontSize:15, fontWeight:700, color:'var(--ink-1)', marginBottom:16 }}>Agent weight drift</p>
                  <WeightDrift weights={weights}/>
                </div>
              )}
            </div>
          </>
        )}
      </main>
    </div>
  );
}

window.RLMonitorPage = RLMonitorPage;
