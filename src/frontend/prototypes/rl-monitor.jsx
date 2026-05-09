// RL Monitor screen — Reinforcement Learning feedback loop visualiser
const { useState: useStateRL, useEffect: useEffectRL } = React;

// ── Color helpers ────────────────────────────────────────────────────────────
function scoreColorRL(pct) {
  if (pct >= 80) return 'var(--buy-strong)';
  if (pct >= 65) return 'var(--buy)';
  if (pct >= 50) return 'var(--neutral)';
  return 'var(--sell-strong)';
}

const MISS_COLORS = {
  direction_flip:  '#dc2626',
  external_shock:  '#64748b',
  model_bias:      '#f97316',
  timing:          '#d97706',
  magnitude:       '#0891b2',
  macro_surprise:  '#7c3aed',
  data_gap:        '#94a3b8',
  data_stale:      '#cbd5e1',
};

const MISS_DESCRIPTIONS = {
  direction_flip:  'Predicted up, closed down (or vice versa)',
  external_shock:  'News/policy event the model could not see',
  model_bias:      'Persistent over/under-shoot pattern',
  timing:          'Move happened, but a day early/late',
  magnitude:       'Direction right, but size badly off',
  macro_surprise:  'Macro event the model couldn\'t anticipate',
  data_gap:        'Missing data prevented a reliable signal',
  data_stale:      'Price data was too old to be reliable',
};

const AGENT_LABELS_RL = {
  sales_demand:'Sales & Demand', fundamentals:'Fundamentals',
  pattern_analysis:'Pattern Analysis', raw_materials:'Raw Materials',
  sentiment:'Sentiment', policy_regulatory:'Policy & Regulatory',
  competitive_intel:'Competitive Intel', risk_macro:'Risk & Macro',
};

// ── FIX 1: Ticker chip cards with direction hit % ───────────────────────────
function TickerChip({ t, active, onClick }) {
  const initials = t.sym.replace(/[^A-Z&]/g, '').slice(0, 2);
  const chipSummary = window.RL_SUMMARIES?.[t.sym];
  const pct = chipSummary?.direction_accuracy_pct;
  const hasData = t.has_envelope && pct != null;

  return (
    <button onClick={onClick} style={{
      flexShrink:0, minWidth:160, padding:'12px 14px', borderRadius:14, cursor:'pointer',
      border: `1.5px solid ${active ? t.color : 'var(--border)'}`,
      background: active ? `${t.color}14` : 'var(--bg-surface)',
      textAlign:'left', transition:'all .15s',
      boxShadow: active ? `0 0 0 3px ${t.color}22` : 'var(--shadow-sm)',
    }}>
      <div style={{ display:'flex', alignItems:'center', gap:10, marginBottom:8 }}>
        {/* Avatar */}
        <div style={{
          width:32, height:32, borderRadius:10, display:'flex', alignItems:'center', justifyContent:'center',
          background: active ? t.color : `${t.color}22`,
          color: active ? '#fff' : t.color,
          fontSize:10, fontWeight:800, fontFamily:'JetBrains Mono, monospace', letterSpacing:'0.04em', flexShrink:0,
        }}>{initials}</div>
        <div style={{ minWidth:0 }}>
          <div style={{ fontSize:12, fontWeight:800, color:'var(--ink-1)', fontFamily:'JetBrains Mono, monospace', letterSpacing:'0.03em' }}>{t.sym}</div>
          <div style={{ fontSize:10, color:'var(--ink-3)', marginTop:1, whiteSpace:'nowrap', overflow:'hidden', textOverflow:'ellipsis', maxWidth:100 }}>{t.name}</div>
        </div>
      </div>
      {/* Direction hit */}
      {hasData
        ? <div style={{ display:'flex', alignItems:'baseline', gap:4 }}>
            <span style={{ fontSize:20, fontWeight:800, fontFamily:'JetBrains Mono, monospace', color: scoreColorRL(pct) }}>{pct?.toFixed(0)}%</span>
            <span style={{ fontSize:10, color:'var(--ink-3)' }}>direction hit</span>
          </div>
        : <div style={{ display:'flex', alignItems:'center', gap:6 }}>
            <span style={{ fontSize:14, color:'var(--ink-3)' }}>—</span>
            <span style={{ fontSize:10, color:'var(--ink-3)' }}>direction hit</span>
          </div>
      }
    </button>
  );
}

// ── Predictions chart ─────────────────────────────────────────────────────────
function PredictionChart({ predictions }) {
  if (!predictions || predictions.length < 2) return (
    <div style={{ height:200, display:'flex', alignItems:'center', justifyContent:'center' }}>
      <p style={{ color:'var(--ink-3)', fontSize:13 }}>No prediction data yet.</p>
    </div>
  );

  // Taller chart, more padding for breathing room
  const W = 700, H = 240, pad = { l:58, r:20, t:20, b:36 };
  const iW = W - pad.l - pad.r, iH = H - pad.t - pad.b;
  const n = predictions.length;

  const actuals = predictions.map(p => p.actual).filter(v => v != null);
  const preds   = predictions.map(p => p.predicted).filter(Boolean);
  const all     = [...actuals, ...preds];
  const minV = Math.min(...all) * 0.998;
  const maxV = Math.max(...all) * 1.002;

  const xp = i => pad.l + (i / (n - 1)) * iW;
  const yp = v => pad.t + (1 - (v - minV) / (maxV - minV)) * iH;

  const actPts = predictions
    .map((p, i) => p.actual != null ? `${xp(i).toFixed(1)},${yp(p.actual).toFixed(1)}` : null)
    .filter(Boolean);
  const actPath = actPts.length > 1 ? 'M ' + actPts.join(' L ') : null;

  // Area fill closes back to baseline of chart
  const firstActIdx = predictions.findIndex(p => p.actual != null);
  const lastActIdx  = [...predictions].reverse().findIndex(p => p.actual != null);
  const lastActI    = n - 1 - lastActIdx;
  const actFill = actPath
    ? `${actPath} L ${xp(lastActI).toFixed(1)},${(pad.t+iH).toFixed(1)} L ${xp(firstActIdx).toFixed(1)},${(pad.t+iH).toFixed(1)} Z`
    : null;

  const predPath = 'M ' + predictions.map((p,i) => `${xp(i).toFixed(1)},${yp(p.predicted).toFixed(1)}`).join(' L ');

  const yTicks = [0, 0.25, 0.5, 0.75, 1].map(t => ({
    val: minV + t * (maxV - minV),
    y:   pad.t + (1 - t) * iH,
  }));

  const VIOLET = '#7c3aed';

  return (
    <div>
      {/* Card wrapper matching Claude design */}
      <div style={{
        background:'var(--bg-surface)', border:'1px solid var(--border)',
        borderRadius:14, padding:'20px 20px 16px', marginBottom:24,
      }}>
        <svg width="100%" viewBox={`0 0 ${W} ${H}`} style={{ display:'block', overflow:'visible' }}>
          <defs>
            <linearGradient id="rl-grad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%"   stopColor={VIOLET} stopOpacity="0.28"/>
              <stop offset="70%"  stopColor={VIOLET} stopOpacity="0.10"/>
              <stop offset="100%" stopColor={VIOLET} stopOpacity="0.01"/>
            </linearGradient>
          </defs>

          {/* Grid + Y labels */}
          {yTicks.map((t, i) => (
            <g key={i}>
              <line x1={pad.l} x2={pad.l+iW} y1={t.y} y2={t.y}
                    stroke="var(--border)" strokeDasharray="4 6" strokeWidth={0.8}/>
              <text x={pad.l-8} y={t.y+4} fontSize="8" textAnchor="end"
                    fill="var(--ink-3)" fontFamily="JetBrains Mono,monospace">
                ₹{Math.round(t.val).toLocaleString('en-IN')}
              </text>
            </g>
          ))}

          {/* Area fill — richer violet gradient */}
          {actFill && <path d={actFill} fill="url(#rl-grad)"/>}

          {/* Model prediction — dashed, slightly transparent */}
          <path d={predPath} fill="none" stroke={VIOLET} strokeWidth="1.5"
                strokeLinejoin="round" strokeDasharray="6 4" opacity={0.55}/>

          {/* Actual close — solid, full opacity */}
          {actPath && (
            <path d={actPath} fill="none" stroke={VIOLET} strokeWidth="2.5" strokeLinejoin="round"/>
          )}

          {/* Hit/miss dots on ACTUAL close */}
          {predictions.map((p, i) => {
            if (p.actual == null || p.direction_hit == null) return null;
            return (
              <circle key={i} cx={xp(i)} cy={yp(p.actual)} r={3.5}
                      fill={p.direction_hit ? '#16a34a' : '#dc2626'}
                      stroke="var(--bg-surface)" strokeWidth={1.5}/>
            );
          })}

          {/* X-axis dates */}
          {[0, Math.floor(n/2), n-1].map(i => (
            <text key={i} x={xp(i)} y={H-8} fontSize="10"
                  textAnchor={i===0?'start':i===n-1?'end':'middle'}
                  fill="var(--ink-3)" fontFamily="JetBrains Mono,monospace">
              {predictions[i]?.date?.slice(5) || ''}
            </text>
          ))}
        </svg>

        {/* Legend inside the card */}
        <div style={{ display:'flex', gap:20, marginTop:14, flexWrap:'wrap', paddingLeft: pad.l }}>
          {[
            { color:VIOLET,    label:'Actual close',     line:'solid'  },
            { color:VIOLET,    label:'Model prediction', line:'dashed', opacity:0.55 },
            { color:'#16a34a', label:'Direction hit',    dot:true },
            { color:'#dc2626', label:'Direction miss',   dot:true },
          ].map(item => (
            <div key={item.label} style={{ display:'flex', alignItems:'center', gap:6 }}>
              {item.dot
                ? <span style={{ width:10, height:10, borderRadius:'50%', background:item.color, display:'inline-block', flexShrink:0 }}/>
                : <svg width="24" height="8" style={{ flexShrink:0 }}>
                    <line x1="0" y1="4" x2="24" y2="4" stroke={item.color}
                          strokeWidth={item.line==='solid'?2.5:1.5}
                          strokeDasharray={item.line==='dashed'?'6 4':undefined}
                          opacity={item.opacity || 1}/>
                  </svg>
              }
              <span style={{ fontSize:11, color:'var(--ink-2)' }}>{item.label}</span>
            </div>
          ))}
        </div>
      </div>

      <DailyLog predictions={predictions}/>
    </div>
  );
}

// Rendered outside PredictionChart so it can reference MISS_COLORS defined above
function DirArrow({ up }) {
  return (
    <svg width="14" height="14" viewBox="0 0 14 14" style={{ display:'inline-block', verticalAlign:'middle' }}>
      {up
        ? <polyline points="7,2 12,9 2,9" fill="none" stroke="var(--buy-strong)" strokeWidth="2" strokeLinejoin="round" strokeLinecap="round"/>
        : <polyline points="7,12 12,5 2,5" fill="none" stroke="var(--sell-strong)" strokeWidth="2" strokeLinejoin="round" strokeLinecap="round"/>
      }
    </svg>
  );
}

const MISS_PILL_STYLE = {
  display:'inline-block', padding:'2px 8px', borderRadius:999,
  fontSize:10, fontWeight:700, fontFamily:'inherit', whiteSpace:'nowrap',
};

function DailyLog({ predictions }) {
  if (!predictions || !predictions.length) return null;

  // Derive predicted direction and actual direction for each row
  const rows = [...predictions].reverse().map((p, i, arr) => {
    const prev = arr[i + 1]; // previous in reversed array = next day's data
    // predDir: true=up, false=down — infer from direction_hit and actual dir
    let actualDir = null;
    if (p.actual != null && prev?.actual != null) actualDir = p.actual >= prev.actual;
    // If direction hit, predDir = actualDir; if miss, predDir = opposite
    let predDir = null;
    if (actualDir !== null && p.direction_hit === true)  predDir = actualDir;
    if (actualDir !== null && p.direction_hit === false) predDir = !actualDir;
    // Fallback: derive from predicted vs prev predicted
    if (predDir === null && prev?.predicted != null) predDir = p.predicted >= prev.predicted;
    return { ...p, predDir, actualDir };
  });

  const cols = ['Date','Predicted ₹','Actual ₹','Error %','Pred Dir','Actual Dir','Hit','Miss Type','Confidence'];

  return (
    <div style={{ marginTop:28 }}>
      <p style={{ fontSize:14, fontWeight:700, color:'var(--ink-1)', marginBottom:4 }}>Daily log</p>
      <p style={{ fontSize:12, color:'var(--ink-3)', marginBottom:12 }}>
        Most recent first · click any row to see the agent snapshot for that prediction (not wired in this prototype)
      </p>
      <div style={{ overflowX:'auto', borderRadius:12, border:'1px solid var(--border)' }}>
        <table style={{ width:'100%', borderCollapse:'collapse', fontSize:12, fontFamily:'JetBrains Mono, monospace', minWidth:780 }}>
          <thead>
            <tr style={{ borderBottom:'1px solid var(--border)', background:'var(--bg-elevated)' }}>
              {cols.map(h => (
                <th key={h} style={{
                  textAlign:'left', padding:'10px 12px', color:'var(--ink-3)',
                  fontWeight:700, fontSize:10, letterSpacing:'0.08em', textTransform:'uppercase',
                  whiteSpace:'nowrap',
                }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((p, i) => {
              const isHit     = p.direction_hit === true;
              const isMiss    = p.direction_hit === false;
              const isPending = p.direction_hit === null;
              const missColor = MISS_COLORS[p.miss_type] || '#94a3b8';
              const missLabel = p.miss_type
                ? p.miss_type.split('_').map(w => w.charAt(0).toUpperCase()+w.slice(1)).join(' ')
                : null;

              // Signed error: (actual - predicted) / predicted * 100
              // Negative = model over-predicted, Positive = model under-predicted
              const signedErr = (p.actual != null && p.predicted != null)
                ? (p.actual - p.predicted) / p.predicted * 100
                : null;
              const errDisplay = signedErr != null
                ? `${signedErr >= 0 ? '+' : ''}${signedErr.toFixed(2)}%`
                : '—';
              const errColor = signedErr == null
                ? 'var(--ink-3)'
                : Math.abs(signedErr) > 0.5
                  ? 'var(--sell)'
                  : 'var(--ink-2)';

              // Row background: subtle tint for miss rows
              const rowBg = isMiss ? 'rgba(239,68,68,0.03)' : 'transparent';

              return (
                <tr key={i}
                    style={{ borderBottom:'1px solid var(--border)', cursor:'pointer',
                             background: rowBg, transition:'background .1s' }}
                    onMouseEnter={e => e.currentTarget.style.background = 'var(--bg-tinted)'}
                    onMouseLeave={e => e.currentTarget.style.background = rowBg}>

                  {/* Date — muted, monospace */}
                  <td style={{ padding:'9px 14px', color:'var(--ink-2)', fontWeight:400 }}>{p.date}</td>

                  {/* Predicted ₹ — bold, primary */}
                  <td style={{ padding:'9px 14px', color:'var(--ink-1)', fontWeight:700 }}>
                    {p.predicted != null ? p.predicted.toLocaleString('en-IN',{minimumFractionDigits:2,maximumFractionDigits:2}) : '—'}
                  </td>

                  {/* Actual ₹ — bold when available */}
                  <td style={{ padding:'9px 14px', color: p.actual != null ? 'var(--ink-1)' : 'var(--ink-3)', fontWeight: p.actual ? 700 : 400 }}>
                    {p.actual != null ? p.actual.toLocaleString('en-IN',{minimumFractionDigits:2,maximumFractionDigits:2}) : '—'}
                  </td>

                  {/* Error % — signed, colored when large */}
                  <td style={{ padding:'9px 14px', color: errColor, fontWeight: Math.abs(signedErr||0)>0.5 ? 600 : 400 }}>
                    {errDisplay}
                  </td>

                  {/* Pred Dir */}
                  <td style={{ padding:'9px 12px' }}>
                    {p.predDir !== null ? <DirArrow up={p.predDir}/> : <span style={{ color:'var(--ink-3)' }}>—</span>}
                  </td>

                  {/* Actual Dir */}
                  <td style={{ padding:'9px 12px' }}>
                    {p.actualDir !== null ? <DirArrow up={p.actualDir}/> : <span style={{ color:'var(--ink-3)' }}>—</span>}
                  </td>

                  {/* Hit */}
                  <td style={{ padding:'9px 12px' }}>
                    {isHit    && <span style={{ color:'var(--buy-strong)', fontWeight:700 }}>✓ hit</span>}
                    {isMiss   && <span style={{ color:'var(--sell-strong)', fontWeight:700 }}>✗ miss</span>}
                    {isPending && <span style={{ color:'var(--ink-3)' }}>—</span>}
                  </td>

                  {/* Miss Type pill */}
                  <td style={{ padding:'9px 12px' }}>
                    {missLabel
                      ? <span style={{ ...MISS_PILL_STYLE, background:`${missColor}22`, color:missColor, border:`1px solid ${missColor}55` }}>
                          {missLabel}
                        </span>
                      : <span style={{ color:'var(--ink-3)' }}>—</span>
                    }
                  </td>

                  {/* Confidence */}
                  <td style={{ padding:'9px 12px', color:'var(--ink-2)' }}>
                    {p.confidence != null ? `${Math.round(p.confidence * 100)}%` : '—'}
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

// ── FIX 3: Direction calendar with hits / misses / longest streak ─────────────
function DirectionCalendar({ predictions }) {
  if (!predictions || !predictions.length) return (
    <p style={{ color:'var(--ink-3)', fontSize:13 }}>No prediction data yet.</p>
  );

  const reviewed = predictions.filter(p => p.direction_hit != null);
  const hits     = reviewed.filter(p => p.direction_hit).length;
  const misses   = reviewed.length - hits;

  // Longest hit streak
  let longest = 0, cur = 0;
  reviewed.forEach(p => {
    if (p.direction_hit) { cur++; longest = Math.max(longest, cur); }
    else cur = 0;
  });

  // Current streak
  let currentStreak = 0;
  for (let i = reviewed.length - 1; i >= 0; i--) {
    if (reviewed[i].direction_hit) currentStreak++;
    else break;
  }

  return (
    <div>
      {/* Stats strip */}
      <div style={{ display:'flex', gap:12, marginBottom:20, flexWrap:'wrap' }}>
        {[
          { label:'Hits',           value:hits,           color:'var(--buy-strong)',  bg:'var(--buy-soft)' },
          { label:'Misses',         value:misses,         color:'var(--sell-strong)', bg:'var(--sell-soft)' },
          { label:'Longest streak', value:`${longest}d`,  color:'var(--cyan)',        bg:'var(--cyan-soft)' },
          { label:'Current streak', value:`${currentStreak}d`, color:'var(--neutral)', bg:'var(--neutral-soft)' },
        ].map(s => (
          <div key={s.label} style={{
            display:'flex', alignItems:'center', gap:10, padding:'10px 16px',
            borderRadius:12, background:s.bg, border:`1px solid ${s.color}44`, minWidth:130,
          }}>
            <span className="mono" style={{ fontSize:20, fontWeight:800, color:s.color, lineHeight:1 }}>{s.value}</span>
            <span style={{ fontSize:11, color:'var(--ink-2)', lineHeight:1.3 }}>{s.label}</span>
          </div>
        ))}
        <div style={{ display:'flex', alignItems:'center', gap:8, marginLeft:'auto' }}>
          <span style={{ width:12, height:12, borderRadius:3, background:'var(--buy-soft)', border:'1px solid var(--buy)', display:'inline-block' }}/>
          <span style={{ fontSize:11, color:'var(--ink-2)' }}>Hit</span>
          <span style={{ width:12, height:12, borderRadius:3, background:'var(--sell-soft)', border:'1px solid var(--sell-strong)', display:'inline-block', marginLeft:8 }}/>
          <span style={{ fontSize:11, color:'var(--ink-2)' }}>Miss</span>
          <span style={{ width:12, height:12, borderRadius:3, background:'var(--bg-tinted)', border:'1px solid var(--border)', display:'inline-block', marginLeft:8 }}/>
          <span style={{ fontSize:11, color:'var(--ink-2)' }}>Pending</span>
        </div>
      </div>

      {/* Calendar grid */}
      <p className="eyebrow" style={{ marginBottom:10 }}>Each cell = one trading day</p>
      <div style={{ display:'flex', flexWrap:'wrap', gap:6 }}>
        {[...reviewed, ...predictions.filter(p => p.direction_hit === null)].map((p, i) => {
          const isHit  = p.direction_hit === true;
          const isMiss = p.direction_hit === false;
          return (
            <div key={i}
                 title={`${p.date}  ${isHit ? '✓ Hit' : isMiss ? '✗ Miss' : '⏳ Pending'} · predicted ₹${p.predicted?.toFixed(0)}`}
                 style={{
                   width:38, height:38, borderRadius:9, display:'flex', alignItems:'center', justifyContent:'center',
                   fontSize:10, fontFamily:'JetBrains Mono, monospace', fontWeight:700, cursor:'default',
                   background: isHit ? 'var(--buy-soft)' : isMiss ? 'var(--sell-soft)' : 'var(--bg-tinted)',
                   color:       isHit ? 'var(--buy-strong)' : isMiss ? 'var(--sell-strong)' : 'var(--ink-3)',
                   border:     `1px solid ${isHit ? 'var(--buy)' : isMiss ? 'var(--sell-strong)' : 'var(--border)'}`,
                   transition:'transform .1s',
                 }}>
              {p.date?.slice(8)}
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ── FIX 4: Miss attribution — donut ring + per-type descriptions ──────────────
function DonutChart({ entries, total, size = 140 }) {
  const cx = size / 2, cy = size / 2, r = size * 0.38, stroke = size * 0.14;
  let offset = 0;
  const circ = 2 * Math.PI * r;

  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} style={{ flexShrink:0, display:'block' }}>
      {/* Background track */}
      <circle cx={cx} cy={cy} r={r} fill="none" stroke="var(--border)" strokeWidth={stroke}/>
      {/* Segments */}
      {entries.map(([type, count]) => {
        const frac = count / total;
        const dash = frac * circ;
        const seg = (
          <circle key={type} cx={cx} cy={cy} r={r} fill="none"
                  stroke={MISS_COLORS[type] || '#94a3b8'}
                  strokeWidth={stroke}
                  strokeDasharray={`${dash} ${circ}`}
                  strokeDashoffset={-offset}
                  strokeLinecap="butt"
                  transform={`rotate(-90 ${cx} ${cy})`}/>
        );
        offset += dash;
        return seg;
      })}
      {/* Center count */}
      <text x={cx} y={cy - 6} textAnchor="middle" fontSize={size * 0.18} fontWeight="800" fill="var(--ink-1)" fontFamily="JetBrains Mono,monospace">{total}</text>
      <text x={cx} y={cy + 10} textAnchor="middle" fontSize={size * 0.075} fill="var(--ink-3)" fontFamily="inherit">miss events</text>
    </svg>
  );
}

function MissAttribution({ misses }) {
  if (!misses) return <p style={{ color:'var(--ink-3)', fontSize:13 }}>No miss data yet.</p>;

  const entries = Object.entries(misses.miss_type_counts || {}).filter(([,v]) => v > 0)
    .sort((a,b) => b[1] - a[1]);
  const total = entries.reduce((s,[,v]) => s + v, 0) || 1;

  if (!entries.length) return (
    <div style={{ textAlign:'center', padding:'32px 0' }}>
      <p style={{ color:'var(--ink-3)', fontSize:14, margin:0 }}>No miss events recorded yet — model is performing perfectly.</p>
    </div>
  );

  return (
    <div>
      <p style={{ fontSize:13, color:'var(--ink-3)', marginBottom:20 }}>
        When the model misses, what category does it fall into? <strong style={{ color:'var(--ink-1)' }}>{total} miss event{total>1?'s':''}</strong> across the 30-day window.
      </p>
      <div style={{ display:'flex', gap:32, alignItems:'flex-start', flexWrap:'wrap' }}>
        {/* Donut */}
        <DonutChart entries={entries} total={total} size={140}/>

        {/* Per-type rows */}
        <div style={{ flex:1, minWidth:280 }}>
          {entries.map(([type, count]) => {
            const pct = Math.round((count / total) * 100);
            const color = MISS_COLORS[type] || '#94a3b8';
            const desc = MISS_DESCRIPTIONS[type] || '';
            const label = type.split('_').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' ');
            return (
              <div key={type} style={{ paddingBottom:14, marginBottom:14, borderBottom:'1px solid var(--border)' }}>
                <div style={{ display:'flex', alignItems:'center', justifyContent:'space-between', marginBottom:6 }}>
                  <div style={{ display:'flex', alignItems:'center', gap:8 }}>
                    <span style={{ width:12, height:12, borderRadius:3, background:color, flexShrink:0, display:'inline-block' }}/>
                    <span style={{ fontSize:14, fontWeight:700, color:'var(--ink-1)' }}>{label}</span>
                  </div>
                  <span className="mono" style={{ fontSize:13, color:'var(--ink-2)' }}>
                    {count} <span style={{ color:'var(--ink-3)', fontWeight:400 }}>({pct}%)</span>
                  </span>
                </div>
                {desc && <p style={{ fontSize:12, color:'var(--ink-3)', margin:'0 0 8px 20px', lineHeight:1.4 }}>{desc}</p>}
                <div style={{ height:5, background:'var(--border)', borderRadius:999, marginLeft:20 }}>
                  <div style={{ height:'100%', borderRadius:999, width:`${pct}%`, background:color, transition:'width .4s ease' }}/>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

// ── Agent Weight Drift ────────────────────────────────────────────────────────
function WeightDrift({ weights, ticker }) {
  if (!weights) return <p style={{ color:'var(--ink-3)', fontSize:13 }}>No weight data yet for this ticker.</p>;

  const agentColors = window.RL_AGENT_COLORS || {};
  const agents = Object.keys(weights.current_weights);
  // Sort history by version ascending for the chart
  const history = [...(weights.weight_history || [])].sort((a,b) => a.version - b.version);
  const numV = history.length;

  // ── Multi-line drift chart ──────────────────────────────────────────────
  const W = 700, H = 240, pad = { l:44, r:16, t:16, b:52 };
  const iW = W - pad.l - pad.r, iH = H - pad.t - pad.b;
  const xV = i => pad.l + (numV > 1 ? (i / (numV-1)) * iW : iW/2);
  const yW = w => pad.t + (1 - w / 0.30) * iH;  // max 30%

  const yTicks = [0, 0.05, 0.10, 0.15, 0.20, 0.25, 0.30];

  return (
    <div>
      {/* Chart 1: Agent weight drift across versions */}
      <div style={{ marginBottom:32 }}>
        <p style={{ fontSize:15, fontWeight:700, color:'var(--ink-1)', marginBottom:4 }}>Agent weight drift across versions</p>
        <p style={{ fontSize:12, color:'var(--ink-3)', marginBottom:16 }}>
          How RL has reweighted each agent's voice in <strong style={{color:'var(--ink-1)'}}>{ticker}</strong>'s composite score over {numV} model versions.
        </p>
        <div style={{ background:'var(--bg-surface)', border:'1px solid var(--border)', borderRadius:14, padding:'20px 20px 16px' }}>
          {numV < 2
            ? <p style={{ color:'var(--ink-3)', fontSize:13, textAlign:'center', padding:32 }}>Need ≥ 2 versions to show drift chart.</p>
            : <>
              <svg width="100%" viewBox={`0 0 ${W} ${H}`} style={{ display:'block', overflow:'visible' }}>
                {/* Y grid + labels */}
                {yTicks.map((t, i) => (
                  <g key={i}>
                    <line x1={pad.l} x2={pad.l+iW} y1={yW(t)} y2={yW(t)} stroke="var(--border)" strokeDasharray="4 6" strokeWidth={0.8}/>
                    <text x={pad.l-6} y={yW(t)+4} fontSize="9" textAnchor="end" fill="var(--ink-3)" fontFamily="JetBrains Mono,monospace">
                      {(t*100).toFixed(0)}%
                    </text>
                  </g>
                ))}
                {/* One line per agent */}
                {agents.map(k => {
                  const color = agentColors[k] || '#94a3b8';
                  const pts = history.map((h, i) => `${xV(i).toFixed(1)},${yW(h.weights[k] ?? 0).toFixed(1)}`);
                  return (
                    <g key={k}>
                      <path d={'M ' + pts.join(' L ')} fill="none" stroke={color} strokeWidth="2"
                            strokeLinejoin="round" strokeLinecap="round"/>
                      {history.map((h, i) => (
                        <circle key={i} cx={xV(i)} cy={yW(h.weights[k] ?? 0)} r="3.5"
                                fill={color} stroke="var(--bg-surface)" strokeWidth="1.5"/>
                      ))}
                    </g>
                  );
                })}
                {/* X axis: version + date */}
                {history.map((h, i) => (
                  <g key={i}>
                    <text x={xV(i)} y={pad.t+iH+14} fontSize="9" textAnchor="middle"
                          fill="var(--ink-1)" fontFamily="JetBrains Mono,monospace" fontWeight="700">
                      v{h.version}
                    </text>
                    <text x={xV(i)} y={pad.t+iH+26} fontSize="8" textAnchor="middle"
                          fill="var(--ink-3)" fontFamily="JetBrains Mono,monospace">
                      {h.date?.slice(5)}
                    </text>
                  </g>
                ))}
              </svg>
              {/* Legend */}
              <div style={{ display:'flex', flexWrap:'wrap', gap:'8px 20px', marginTop:10, paddingLeft:pad.l }}>
                {agents.map(k => (
                  <div key={k} style={{ display:'flex', alignItems:'center', gap:6 }}>
                    <span style={{ width:10, height:10, borderRadius:3, background:agentColors[k]||'#94a3b8', display:'inline-block', flexShrink:0 }}/>
                    <span style={{ fontSize:11, color:'var(--ink-2)' }}>{AGENT_LABELS_RL[k]||k}</span>
                  </div>
                ))}
              </div>
            </>
          }
        </div>
      </div>

      {/* Chart 2: Current vs base weights (redesigned) */}
      <div>
        <p style={{ fontSize:15, fontWeight:700, color:'var(--ink-1)', marginBottom:4 }}>Current vs base weights</p>
        <p style={{ fontSize:12, color:'var(--ink-3)', marginBottom:16 }}>
          Δ shows where RL has learned the most. Positive = RL trusts this agent more than the configured baseline.
        </p>
        <div style={{ background:'var(--bg-surface)', border:'1px solid var(--border)', borderRadius:14, padding:'8px 0' }}>
          {agents.map((k, idx) => {
            const cur  = weights.current_weights[k] ?? 0;
            const base = weights.base_weights[k] ?? 0;
            const diff = cur - base;
            const color = agentColors[k] || '#94a3b8';
            const BAR_MAX = 0.30; // 30% = full bar
            return (
              <div key={k} style={{
                display:'grid', gridTemplateColumns:'180px 1fr 60px 70px 60px',
                alignItems:'center', gap:'0 16px',
                padding:'10px 20px',
                borderBottom: idx < agents.length-1 ? '1px solid var(--border)' : 'none',
              }}>
                {/* Name + colored dot */}
                <div style={{ display:'flex', alignItems:'center', gap:8 }}>
                  <span style={{ width:10, height:10, borderRadius:'50%', background:color, flexShrink:0, display:'inline-block' }}/>
                  <span style={{ fontSize:13, color:'var(--ink-1)', fontWeight:500 }}>{AGENT_LABELS_RL[k]||k}</span>
                </div>
                {/* Bar track */}
                <div style={{ position:'relative', height:10, background:'var(--bg-elevated)', borderRadius:999 }}>
                  {/* Colored fill = current weight */}
                  <div style={{
                    position:'absolute', top:0, left:0, height:'100%', borderRadius:999,
                    width:`${(cur/BAR_MAX)*100}%`, background:color,
                    transition:'width .4s ease',
                  }}/>
                  {/* Base marker — vertical dark line */}
                  <div style={{
                    position:'absolute', top:-3, bottom:-3,
                    left:`${(base/BAR_MAX)*100}%`,
                    width:2, background:'var(--ink-2)',
                    borderRadius:1, transform:'translateX(-50%)',
                  }}/>
                </div>
                {/* Base % */}
                <span className="mono" style={{ fontSize:12, color:'var(--ink-3)', textAlign:'right' }}>
                  {(base*100).toFixed(1)}%
                </span>
                {/* Current % */}
                <span className="mono" style={{ fontSize:13, fontWeight:700, color:'var(--ink-1)', textAlign:'right' }}>
                  {(cur*100).toFixed(1)}%
                </span>
                {/* Delta */}
                <span className="mono" style={{
                  fontSize:12, fontWeight:600, textAlign:'right',
                  color: diff > 0.005 ? 'var(--buy-strong)' : diff < -0.005 ? 'var(--sell-strong)' : 'var(--ink-3)',
                }}>
                  {diff >= 0 ? '+' : ''}{(diff*100).toFixed(1)}%
                </span>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

// ── KPI card ──────────────────────────────────────────────────────────────────
function KpiCard({ label, value, sub, color }) {
  return (
    <div className="card" style={{ padding:'14px 16px' }}>
      <p className="eyebrow" style={{ marginBottom:6 }}>{label}</p>
      <p className="mono" style={{ fontSize:22, fontWeight:800, color:color||'var(--ink-1)', margin:0, lineHeight:1 }}>{value}</p>
      {sub && <p style={{ fontSize:11, color:'var(--ink-3)', marginTop:4, marginBottom:0 }}>{sub}</p>}
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────
function RLMonitorPage({ onNav }) {
  const [activeTicker, setActiveTicker] = useStateRL(window.RL_TICKERS[0]?.sym || 'MARUTI');
  const [activeTab, setActiveTab] = useStateRL('predictions');
  const [data, setData] = useStateRL({ summary:null, predictions:[], weights:null, misses:null });
  const [loading, setLoading] = useStateRL(false);

  useEffectRL(() => {
    const sym = activeTicker;
    setData({
      summary:     window.RL_SUMMARIES?.[sym]   || null,
      predictions: window.RL_PREDICTIONS?.[sym] || [],
      weights:     window.RL_WEIGHTS?.[sym]     || null,
      misses:      window.RL_MISSES?.[sym]      || null,
    });
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
    { k:'calendar',    label:'Direction calendar',     icon:<Icon.Calendar size={14}/> },
    { k:'misses',      label:'Miss attribution',       icon:<Icon.AlertTriangle size={14}/> },
    { k:'weights',     label:'Agent weight drift',     icon:<Icon.BarChart size={14}/> },
  ];

  return (
    <div style={{ minHeight:'100vh', background:'var(--bg-base)' }}>
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

        {/* FIX 1: Ticker chip cards */}
        <div style={{ display:'flex', gap:10, marginBottom:24, overflowX:'auto', paddingBottom:4 }}>
          {tickers.map(t => (
            <TickerChip key={t.sym} t={t} active={activeTicker===t.sym} onClick={()=>setActiveTicker(t.sym)}/>
          ))}
        </div>

        {/* No data */}
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
          <div style={{ display:'grid', gridTemplateColumns:'repeat(auto-fit, minmax(155px, 1fr))', gap:12, marginBottom:24 }}>
            <KpiCard label="Direction Hit Rate"
              value={`${summary.direction_accuracy_pct?.toFixed(1)}%`}
              sub={`${summary.direction_hits ?? '—'} of ${summary.total_days ?? summary.total_entries} days`}
              color={scoreColorRL(summary.direction_accuracy_pct)}/>
            <KpiCard label="Avg Price Error"
              value={`±${(summary.avg_price_error_pct ?? 0).toFixed(2)}%`}
              sub="30-day window"/>
            <KpiCard label="Total Miss Events"
              value={String(summary.total_entries - Math.round(summary.total_entries * summary.direction_accuracy_pct / 100) || 0)}
              sub="requires attribution"
              color="var(--sell-strong)"/>
            <KpiCard label="Model Version"
              value={`v${summary.weight_version}`}
              sub={`${summary.total_entries} reviewed days`}/>
            <KpiCard label="Last RL Run"
              value="Today"
              sub={`${now} IST`}
              color="var(--buy-strong)"/>
            <KpiCard label="Current Verdict"
              value={summary.current_verdict || '—'}
              sub={`${summary.streak_days} day streak`}/>
          </div>
        )}

        {/* Tabs + content */}
        {summary && (
          <>
            <div style={{ display:'flex', gap:0, borderBottom:'1px solid var(--border)', marginBottom:20 }}>
              {tabs.map(t => (
                <button key={t.k} onClick={()=>setActiveTab(t.k)} style={{
                  display:'flex', alignItems:'center', gap:7, padding:'10px 18px',
                  border:'none', background:'transparent', cursor:'pointer', fontSize:13, fontWeight:600,
                  color: activeTab===t.k ? 'var(--cyan)' : 'var(--ink-3)',
                  borderBottom: activeTab===t.k ? '2px solid var(--cyan)' : '2px solid transparent',
                  marginBottom:-1, transition:'color .15s',
                }}>{t.icon} {t.label}</button>
              ))}
            </div>

            <div className="card" style={{ padding:24 }}>
              {activeTab === 'predictions' && (
                <div>
                  <p style={{ fontSize:15, fontWeight:700, color:'var(--ink-1)', marginBottom:4 }}>Daily prediction vs actual close</p>
                  <p style={{ fontSize:12, color:'var(--ink-3)', marginBottom:20 }}>
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
                  <p style={{ fontSize:15, fontWeight:700, color:'var(--ink-1)', marginBottom:4 }}>Miss attribution</p>
                  <MissAttribution misses={misses}/>
                </div>
              )}
              {activeTab === 'weights' && (
                <WeightDrift weights={weights} ticker={activeTicker}/>
              )}
            </div>
          </>
        )}
      </main>
    </div>
  );
}

window.RLMonitorPage = RLMonitorPage;
