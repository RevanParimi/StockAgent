// Analytics Dashboard — 4 SVG chart panels backed by /analytics/* endpoints
// No external charting library — all charts are inline SVG React components.
const { useState: useAnState, useEffect: useAnEffect } = React;

// ---------------------------------------------------------------------------
// Palette — matches app CSS variables where possible
// ---------------------------------------------------------------------------
const PAL = {
  green:  '#22c55e',
  red:    '#ef4444',
  amber:  '#f59e0b',
  blue:   '#6366f1',
  cyan:   '#22d3ee',
  purple: '#a78bfa',
  slate:  '#94a3b8',
  agents: ['#6366f1','#22d3ee','#4ade80','#fb923c','#f472b6','#a78bfa','#34d399','#fbbf24','#e879f9'],
};

const MISS_COLORS = {
  direction_flip: '#ef4444',
  model_bias:     '#f97316',
  timing:         '#f59e0b',
  magnitude:      '#84cc16',
  data_gap:       '#94a3b8',
  data_stale:     '#94a3b8',
  external_shock: '#64748b',
  '':             '#cbd5e1',
};

// ---------------------------------------------------------------------------
// Inline SVG chart primitives
// ---------------------------------------------------------------------------

/** Horizontal bar chart — data = [{label, value (0-1), color?}] */
function HBarChart({ data, width = 420, rowH = 30 }) {
  if (!data || !data.length) return <EmptyChart label="No accuracy data yet"/>;
  const maxVal = Math.max(...data.map(d => d.value), 0.01);
  const labelW = 130;
  const barAreaW = width - labelW - 56;

  return (
    <svg width={width} height={data.length * rowH + 8} style={{ overflow: 'visible' }}>
      {data.map((d, i) => {
        const y = i * rowH;
        const barW = Math.max(4, (d.value / maxVal) * barAreaW);
        const pct = (d.value * 100).toFixed(1);
        const color = d.color || PAL.agents[i % PAL.agents.length];
        return (
          <g key={d.label} transform={`translate(0,${y})`}>
            <text x={labelW - 6} y={rowH/2 + 4} textAnchor="end" fontSize={11}
                  fill="var(--ink-2)" fontFamily="inherit"
                  style={{ overflow: 'hidden', textOverflow: 'ellipsis' }}>
              {d.label.replace(/_/g, ' ')}
            </text>
            <rect x={labelW} y={4} width={barW} height={rowH - 10}
                  rx={3} fill={color} opacity={0.85}/>
            <text x={labelW + barW + 5} y={rowH/2 + 4} fontSize={11}
                  fill="var(--ink-3)" fontFamily="inherit">
              {pct}%
            </text>
          </g>
        );
      })}
    </svg>
  );
}

/** Multi-series line chart — series = [{label, points:[{x,y}], color}] */
function LineChart({ series, width = 460, height = 120, yMin = 0, yMax = 0.3, yLabel = 'Weight' }) {
  if (!series || !series.length || !series.some(s => s.points && s.points.length > 1))
    return <EmptyChart label="No weight history yet"/>;

  const pad = { top: 8, right: 12, bottom: 24, left: 36 };
  const W = width - pad.left - pad.right;
  const H = height - pad.top - pad.bottom;

  const allX = series.flatMap(s => s.points.map(p => p.x));
  const minX = Math.min(...allX);
  const maxX = Math.max(...allX, minX + 1);

  const sx = x => pad.left + ((x - minX) / (maxX - minX)) * W;
  const sy = y => pad.top + H - ((y - yMin) / (yMax - yMin)) * H;

  // Y grid lines at 0, 0.1, 0.2, 0.3
  const gridY = [0, 0.1, 0.2, 0.3].filter(v => v >= yMin && v <= yMax);

  return (
    <svg width={width} height={height}>
      {/* Grid */}
      {gridY.map(v => (
        <g key={v}>
          <line x1={pad.left} y1={sy(v)} x2={pad.left + W} y2={sy(v)}
                stroke="var(--border)" strokeWidth={1} strokeDasharray="3,3"/>
          <text x={pad.left - 4} y={sy(v) + 4} fontSize={9} textAnchor="end"
                fill="var(--ink-3)" fontFamily="inherit">{v.toFixed(1)}</text>
        </g>
      ))}
      {/* Series */}
      {series.map(s => {
        if (!s.points || s.points.length < 2) return null;
        const pts = s.points.map(p => `${sx(p.x)},${sy(p.y)}`).join(' ');
        return (
          <g key={s.label}>
            <polyline points={pts} fill="none" stroke={s.color} strokeWidth={2}
                      strokeLinejoin="round" strokeLinecap="round"/>
            {s.points.map((p, i) => (
              <circle key={i} cx={sx(p.x)} cy={sy(p.y)} r={2.5}
                      fill={s.color} stroke="var(--bg-surface)" strokeWidth={1}/>
            ))}
          </g>
        );
      })}
      {/* X axis label: version numbers */}
      <line x1={pad.left} y1={pad.top + H} x2={pad.left + W} y2={pad.top + H}
            stroke="var(--border)" strokeWidth={1}/>
    </svg>
  );
}

/** Donut chart — data = [{label, value, color}] */
function DonutChart({ data, size = 140 }) {
  if (!data || !data.length || data.every(d => !d.value))
    return <EmptyChart label="No miss data yet" size={size}/>;

  const total = data.reduce((s, d) => s + d.value, 0);
  if (!total) return <EmptyChart label="No misses recorded" size={size}/>;

  const cx = size / 2, cy = size / 2;
  const r = size * 0.38, ir = size * 0.22;

  let angle = -Math.PI / 2;
  const arcs = data.filter(d => d.value > 0).map(d => {
    const sweep = (d.value / total) * 2 * Math.PI;
    const start = angle;
    angle += sweep;
    return { ...d, start, end: angle, sweep };
  });

  function arcPath(s, e, or_, ir_) {
    const x1 = cx + or_ * Math.cos(s),  y1 = cy + or_ * Math.sin(s);
    const x2 = cx + or_ * Math.cos(e),  y2 = cy + or_ * Math.sin(e);
    const xi1 = cx + ir_ * Math.cos(e), yi1 = cy + ir_ * Math.sin(e);
    const xi2 = cx + ir_ * Math.cos(s), yi2 = cy + ir_ * Math.sin(s);
    const lg = (e - s) > Math.PI ? 1 : 0;
    return `M${x1},${y1} A${or_},${or_} 0 ${lg} 1 ${x2},${y2} L${xi1},${yi1} A${ir_},${ir_} 0 ${lg} 0 ${xi2},${yi2}Z`;
  }

  return (
    <svg width={size} height={size}>
      {arcs.map((arc, i) => (
        <path key={arc.label || i}
              d={arcPath(arc.start, arc.end, r, ir)}
              fill={arc.color || PAL.slate}
              stroke="var(--bg-surface)" strokeWidth={1.5}/>
      ))}
      <text x={cx} y={cy + 4} textAnchor="middle" fontSize={11} fontWeight={700}
            fill="var(--ink-1)" fontFamily="inherit">{total}</text>
      <text x={cx} y={cy + 16} textAnchor="middle" fontSize={9}
            fill="var(--ink-3)" fontFamily="inherit">total</text>
    </svg>
  );
}

/** Scatter plot — points = [{x, y, correct, label}] */
function ScatterPlot({ points, width = 380, height = 160 }) {
  if (!points || !points.length) return <EmptyChart label="No conviction data yet"/>;

  const pad = { top: 8, right: 12, bottom: 28, left: 40 };
  const W = width - pad.left - pad.right;
  const H = height - pad.top - pad.bottom;

  const maxX = Math.max(...points.map(p => p.x), 5);
  const maxY = Math.max(...points.map(p => Math.abs(p.y)), 2);
  const sx = x => pad.left + (x / maxX) * W;
  const sy = y => pad.top + H / 2 - (y / maxY) * (H / 2);

  // Grid
  const gridX = [0, Math.round(maxX * 0.5), maxX];
  const gridY = [-maxY, 0, maxY];

  return (
    <svg width={width} height={height}>
      {/* Y grid */}
      {gridY.map(v => (
        <g key={v}>
          <line x1={pad.left} y1={sy(v)} x2={pad.left + W} y2={sy(v)}
                stroke="var(--border)" strokeWidth={1} strokeDasharray="3,3"/>
          <text x={pad.left - 4} y={sy(v) + 4} fontSize={9} textAnchor="end"
                fill="var(--ink-3)" fontFamily="inherit">{v > 0 ? '+' : ''}{v.toFixed(0)}%</text>
        </g>
      ))}
      {/* X axis */}
      <line x1={pad.left} y1={pad.top + H} x2={pad.left + W} y2={pad.top + H}
            stroke="var(--border)" strokeWidth={1}/>
      {gridX.map(v => (
        <text key={v} x={sx(v)} y={pad.top + H + 14} fontSize={9} textAnchor="middle"
              fill="var(--ink-3)" fontFamily="inherit">{v}</text>
      ))}
      {/* Axis labels */}
      <text x={pad.left + W / 2} y={height - 2} fontSize={9} textAnchor="middle"
            fill="var(--ink-3)" fontFamily="inherit">Conviction streak (days)</text>
      {/* Points */}
      {points.map((p, i) => (
        <circle key={i} cx={sx(p.x)} cy={sy(p.y)} r={3.5}
                fill={p.correct ? PAL.green : PAL.red} opacity={0.65}
                stroke="var(--bg-surface)" strokeWidth={0.5}/>
      ))}
    </svg>
  );
}

function EmptyChart({ label = 'No data', size }) {
  return (
    <div style={{
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      height: size || 80, color: 'var(--ink-3)', fontSize: 13,
      border: '1px dashed var(--border)', borderRadius: 8,
    }}>{label}</div>
  );
}

// ---------------------------------------------------------------------------
// Chart panel wrapper
// ---------------------------------------------------------------------------
function ChartPanel({ title, subtitle, children, action }) {
  return (
    <div style={{
      background: 'var(--bg-surface)', border: '1px solid var(--border)',
      borderRadius: 12, padding: '16px 18px',
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 12 }}>
        <div>
          <div style={{ fontWeight: 700, fontSize: 14 }}>{title}</div>
          {subtitle && <div style={{ fontSize: 12, color: 'var(--ink-3)', marginTop: 2 }}>{subtitle}</div>}
        </div>
        {action}
      </div>
      {children}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Legend row
// ---------------------------------------------------------------------------
function Legend({ items }) {
  return (
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px 14px', marginTop: 10 }}>
      {items.map(it => (
        <div key={it.label} style={{ display: 'flex', alignItems: 'center', gap: 5, fontSize: 11, color: 'var(--ink-2)' }}>
          <span style={{ width: 10, height: 10, borderRadius: 2, background: it.color, display: 'inline-block' }}/>
          {it.label}
        </div>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main AnalyticsPage
// ---------------------------------------------------------------------------
function AnalyticsPage({ onNav }) {
  const [accuracy,    setAccuracy]    = useAnState(null);
  const [weightDrift, setWeightDrift] = useAnState(null);
  const [missData,    setMissData]    = useAnState(null);
  const [conviction,  setConviction]  = useAnState(null);
  const [sector,      setSectorData]  = useAnState(null);
  const [loading,     setLoading]     = useAnState(true);
  const [error,       setError]       = useAnState(null);
  const [activeTab,   setActiveTab]   = useAnState('overview');

  useAnEffect(() => {
    let cancelled = false;
    setLoading(true);

    Promise.all([
      fetch('/analytics/agent-accuracy').then(r => r.json()).catch(() => null),
      fetch('/analytics/weight-drift').then(r => r.json()).catch(() => null),
      fetch('/analytics/miss-breakdown').then(r => r.json()).catch(() => null),
      fetch('/analytics/conviction-outcomes').then(r => r.json()).catch(() => null),
      fetch('/analytics/sector-comparison').then(r => r.json()).catch(() => null),
    ]).then(([acc, wd, miss, conv, sec]) => {
      if (cancelled) return;
      setAccuracy(acc);
      setWeightDrift(wd);
      setMissData(miss);
      setConviction(conv);
      setSectorData(sec);
      setLoading(false);
    }).catch(e => {
      if (!cancelled) { setError(String(e)); setLoading(false); }
    });

    return () => { cancelled = true; };
  }, []);

  // Prepare bar chart data from accuracy aggregate
  const barData = (accuracy?.aggregate || []).map((a, i) => ({
    label: a.agent,
    value: a.hit_rate || 0,
    color: PAL.agents[i % PAL.agents.length],
  }));

  // Prepare line chart series from weight drift (use first ticker with history)
  const wdTicker = (weightDrift?.tickers || []).find(t => t.weight_history && t.weight_history.length > 1);
  const agentColors = weightDrift?.agent_colors || {};
  const lineSeries = wdTicker ? (() => {
    const agentNames = Object.keys(wdTicker.current_weights || {});
    return agentNames.map((agent, i) => ({
      label: agent,
      color: agentColors[agent] || PAL.agents[i % PAL.agents.length],
      points: wdTicker.weight_history.map((h, idx) => ({
        x: idx,
        y: h.weights[agent] || 0,
      })),
    }));
  })() : [];

  // Prepare donut data from miss aggregate
  const missAgg = missData?.aggregate || {};
  const missColors = missData?.colors || MISS_COLORS;
  const donutData = Object.entries(missAgg)
    .filter(([, v]) => v > 0)
    .map(([k, v]) => ({ label: k || 'none', value: v, color: missColors[k] || PAL.slate }));

  // Prepare scatter data from conviction outcomes
  const scatterPts = (conviction?.scatter || []).map(p => ({
    x: p.streak,
    y: p.price_error_pct,
    correct: p.direction_correct,
  }));

  const tabs = ['overview', 'weights', 'sector'];

  return (
    <div style={{ minHeight: '100vh', background: 'var(--bg-base)', color: 'var(--ink-1)', paddingBottom: 100 }}>
      {/* Header */}
      <div style={{
        padding: '18px 24px', borderBottom: '1px solid var(--border)',
        background: 'var(--bg-surface)',
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <button onClick={() => onNav('home')} style={{
            background: 'transparent', border: 'none', cursor: 'pointer', color: 'var(--ink-3)',
          }}>
            <Icon.ChevronL size={18}/>
          </button>
          <Icon.Trend size={20} c="var(--accent)"/>
          <div>
            <div style={{ fontWeight: 700, fontSize: 16 }}>RL Analytics</div>
            <div style={{ fontSize: 12, color: 'var(--ink-3)' }}>Agent accuracy · weight drift · miss patterns · conviction</div>
          </div>
        </div>
        <a href="/analytics/rl-export?format=csv" download="rl_export.csv" style={{
          padding: '7px 14px', borderRadius: 8, border: '1px solid var(--border)',
          background: 'var(--bg-tinted)', color: 'var(--ink-1)', fontSize: 12,
          fontWeight: 600, textDecoration: 'none', display: 'flex', alignItems: 'center', gap: 5,
        }}>
          ↓ CSV Export
        </a>
      </div>

      {/* Tabs */}
      <div style={{
        display: 'flex', gap: 4, padding: '12px 24px 0',
        borderBottom: '1px solid var(--border)', background: 'var(--bg-surface)',
      }}>
        {tabs.map(t => (
          <button key={t} onClick={() => setActiveTab(t)} style={{
            padding: '7px 16px', borderRadius: '8px 8px 0 0',
            border: '1px solid var(--border)', borderBottom: t === activeTab ? '1px solid var(--bg-surface)' : '1px solid var(--border)',
            background: t === activeTab ? 'var(--bg-base)' : 'transparent',
            color: t === activeTab ? 'var(--ink-1)' : 'var(--ink-3)',
            fontSize: 13, fontWeight: t === activeTab ? 700 : 400, cursor: 'pointer',
            textTransform: 'capitalize',
          }}>{t}</button>
        ))}
      </div>

      <div style={{ maxWidth: 960, margin: '0 auto', padding: '20px 16px' }}>

        {loading && (
          <div style={{ textAlign: 'center', padding: '80px 0', color: 'var(--ink-3)', fontSize: 14 }}>
            Loading analytics data…
          </div>
        )}

        {error && (
          <div style={{ padding: 16, borderRadius: 10, background: '#fef2f2', border: '1px solid #fecaca', color: '#991b1b', fontSize: 13 }}>
            Failed to load analytics: {error}
          </div>
        )}

        {!loading && !error && activeTab === 'overview' && (
          <OverviewTab
            barData={barData}
            donutData={donutData}
            missColors={missColors}
            scatterPts={scatterPts}
            conviction={conviction}
            accuracy={accuracy}
          />
        )}

        {!loading && !error && activeTab === 'weights' && (
          <WeightsTab
            lineSeries={lineSeries}
            wdTicker={wdTicker}
            weightDrift={weightDrift}
            agentColors={agentColors}
          />
        )}

        {!loading && !error && activeTab === 'sector' && (
          <SectorTab sector={sector}/>
        )}

      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Tab: Overview — 2x2 grid
// ---------------------------------------------------------------------------
function OverviewTab({ barData, donutData, missColors, scatterPts, conviction, accuracy }) {
  const overallHitRate = accuracy?.aggregate?.length
    ? (accuracy.aggregate.reduce((s, a) => s + a.hit_rate, 0) / accuracy.aggregate.length * 100).toFixed(1)
    : null;

  return (
    <>
      {/* Stats row */}
      {overallHitRate && (
        <div style={{ display: 'flex', gap: 12, marginBottom: 20, flexWrap: 'wrap' }}>
          <StatChip label="Avg Agent Accuracy" value={`${overallHitRate}%`}
                    color={parseFloat(overallHitRate) >= 55 ? PAL.green : PAL.amber}/>
          <StatChip label="Miss Events" value={donutData.reduce((s, d) => s + d.value, 0)}/>
          <StatChip label="Scatter Points" value={scatterPts.length}/>
          {conviction?.buckets?.find(b => b.label === '6–10') && (
            <StatChip
              label="Accuracy @ 6–10 day streak"
              value={`${(conviction.buckets.find(b => b.label === '6–10').accuracy * 100).toFixed(0)}%`}
              color={PAL.blue}
            />
          )}
        </div>
      )}

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>

        {/* Panel 1: Agent Accuracy Bar */}
        <div style={{ gridColumn: '1 / -1' }}>
          <ChartPanel
            title="Agent Direction Accuracy"
            subtitle="Hit rate (direction correct %) per agent — aggregated across all reviewed tickers"
          >
            <HBarChart data={barData} width={Math.min(880, window.innerWidth - 80)}/>
          </ChartPanel>
        </div>

        {/* Panel 2: Miss Type Donut */}
        <ChartPanel
          title="Miss Type Breakdown"
          subtitle="Distribution of miss categories across all RL reviews"
        >
          <div style={{ display: 'flex', gap: 20, alignItems: 'flex-start', flexWrap: 'wrap' }}>
            <DonutChart data={donutData} size={150}/>
            <div style={{ flex: 1, minWidth: 140 }}>
              {donutData.map(d => (
                <div key={d.label} style={{
                  display: 'flex', justifyContent: 'space-between',
                  alignItems: 'center', marginBottom: 6,
                }}>
                  <span style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, color: 'var(--ink-2)' }}>
                    <span style={{ width: 8, height: 8, borderRadius: 2, background: d.color, display: 'inline-block' }}/>
                    {d.label.replace(/_/g, ' ')}
                  </span>
                  <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--ink-1)' }}>{d.value}</span>
                </div>
              ))}
            </div>
          </div>
        </ChartPanel>

        {/* Panel 3: Conviction Scatter */}
        <ChartPanel
          title="Conviction vs Price Error"
          subtitle="Each dot = one reviewed day. X = streak length, Y = price error %. Green = correct direction."
        >
          <ScatterPlot points={scatterPts} width={340} height={160}/>
          <Legend items={[
            { label: 'Direction correct', color: PAL.green },
            { label: 'Direction wrong',   color: PAL.red },
          ]}/>
          {conviction?.buckets && (
            <ConvictionBucketTable buckets={conviction.buckets}/>
          )}
        </ChartPanel>

      </div>
    </>
  );
}

function ConvictionBucketTable({ buckets }) {
  return (
    <table style={{ width: '100%', marginTop: 14, borderCollapse: 'collapse', fontSize: 12 }}>
      <thead>
        <tr style={{ borderBottom: '1px solid var(--border)' }}>
          {['Streak', 'Days', 'Accuracy', 'Avg error'].map(h => (
            <th key={h} style={{ padding: '4px 8px', textAlign: h === 'Streak' ? 'left' : 'right',
                                  color: 'var(--ink-3)', fontWeight: 600 }}>{h}</th>
          ))}
        </tr>
      </thead>
      <tbody>
        {buckets.map(b => (
          <tr key={b.label} style={{ borderBottom: '1px solid var(--border)' }}>
            <td style={{ padding: '4px 8px', color: 'var(--ink-2)' }}>{b.label}</td>
            <td style={{ padding: '4px 8px', textAlign: 'right', color: 'var(--ink-3)' }}>{b.total}</td>
            <td style={{ padding: '4px 8px', textAlign: 'right', fontWeight: 600,
                          color: b.accuracy >= 0.55 ? PAL.green : b.accuracy >= 0.45 ? PAL.amber : PAL.red }}>
              {(b.accuracy * 100).toFixed(0)}%
            </td>
            <td style={{ padding: '4px 8px', textAlign: 'right', color: 'var(--ink-3)' }}>
              ±{b.avg_error_pct.toFixed(1)}%
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

// ---------------------------------------------------------------------------
// Tab: Weights
// ---------------------------------------------------------------------------
function WeightsTab({ lineSeries, wdTicker, weightDrift, agentColors }) {
  const [selectedTicker, setSelectedTicker] = useAnState(wdTicker?.ticker || '');

  const tickers = weightDrift?.tickers || [];
  const displayTicker = tickers.find(t => t.ticker === selectedTicker) || wdTicker;

  const seriesForTicker = displayTicker ? (() => {
    const agentNames = Object.keys(displayTicker.current_weights || {});
    return agentNames.map((agent, i) => ({
      label: agent,
      color: agentColors[agent] || PAL.agents[i % PAL.agents.length],
      points: (displayTicker.weight_history || []).map((h, idx) => ({
        x: idx,
        y: h.weights[agent] || 0,
      })),
    }));
  })() : [];

  return (
    <>
      {/* Ticker selector */}
      {tickers.length > 0 && (
        <div style={{ marginBottom: 16 }}>
          <select value={selectedTicker} onChange={e => setSelectedTicker(e.target.value)} style={{
            padding: '7px 12px', borderRadius: 8, border: '1px solid var(--border)',
            background: 'var(--bg-surface)', color: 'var(--ink-1)', fontSize: 13,
          }}>
            {tickers.map(t => (
              <option key={t.ticker} value={t.ticker}>{t.ticker} ({t.sector})</option>
            ))}
          </select>
        </div>
      )}

      <ChartPanel
        title="Agent Weight Drift"
        subtitle={displayTicker ? `${displayTicker.ticker} — how RL has shifted each agent's influence over ${(displayTicker.weight_history || []).length} weight versions` : 'Select a ticker above'}
      >
        <LineChart series={seriesForTicker} width={860} height={140} yMin={0} yMax={0.35}/>
        {seriesForTicker.length > 0 && (
          <Legend items={seriesForTicker.map(s => ({ label: s.label.replace(/_/g, ' '), color: s.color }))}/>
        )}
      </ChartPanel>

      {/* Current vs base weights table */}
      {displayTicker && (
        <div style={{ marginTop: 16 }}>
          <ChartPanel title="Current vs Base Weights" subtitle="Divergence shows where RL has learned the most">
            <WeightDiffTable ticker={displayTicker} agentColors={agentColors}/>
          </ChartPanel>
        </div>
      )}
    </>
  );
}

function WeightDiffTable({ ticker, agentColors }) {
  const current = ticker.current_weights || {};
  const base    = ticker.base_weights || {};
  const agents  = Object.keys({ ...current, ...base });

  return (
    <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
      <thead>
        <tr style={{ borderBottom: '1px solid var(--border)' }}>
          {['Agent', 'Base', 'Learned', 'Δ'].map(h => (
            <th key={h} style={{ padding: '5px 8px', textAlign: h === 'Agent' ? 'left' : 'right',
                                  color: 'var(--ink-3)', fontWeight: 600 }}>{h}</th>
          ))}
        </tr>
      </thead>
      <tbody>
        {agents.sort().map(agent => {
          const cur  = current[agent] || 0;
          const bas  = base[agent]    || 0;
          const diff = cur - bas;
          const col  = agentColors[agent] || PAL.slate;
          return (
            <tr key={agent} style={{ borderBottom: '1px solid var(--border)' }}>
              <td style={{ padding: '5px 8px', display: 'flex', alignItems: 'center', gap: 6 }}>
                <span style={{ width: 8, height: 8, borderRadius: 2, background: col, display: 'inline-block', flexShrink: 0 }}/>
                <span style={{ color: 'var(--ink-2)' }}>{agent.replace(/_/g, ' ')}</span>
              </td>
              <td style={{ padding: '5px 8px', textAlign: 'right', color: 'var(--ink-3)', fontFamily: 'monospace' }}>{(bas * 100).toFixed(1)}%</td>
              <td style={{ padding: '5px 8px', textAlign: 'right', fontWeight: 600, fontFamily: 'monospace', color: 'var(--ink-1)' }}>{(cur * 100).toFixed(1)}%</td>
              <td style={{ padding: '5px 8px', textAlign: 'right', fontFamily: 'monospace',
                            color: diff > 0.005 ? PAL.green : diff < -0.005 ? PAL.red : 'var(--ink-3)' }}>
                {diff >= 0 ? '+' : ''}{(diff * 100).toFixed(1)}%
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

// ---------------------------------------------------------------------------
// Tab: Sector comparison
// ---------------------------------------------------------------------------
function SectorTab({ sector }) {
  if (!sector || !sector.sectors || !sector.sectors.length) {
    return (
      <div style={{ textAlign: 'center', padding: '60px 0', color: 'var(--ink-3)', fontSize: 14 }}>
        No cross-sector data yet. Run analyses on BFSI, IT, and RE tickers to see comparisons.
      </div>
    );
  }

  const verdicts = ['STRONG BUY', 'BUY', 'NEUTRAL', 'SELL', 'STRONG SELL'];
  const vColors  = [PAL.green, '#4ade80', PAL.slate, PAL.amber, PAL.red];

  return (
    <>
      <div style={{ marginBottom: 8, fontSize: 12, color: 'var(--ink-3)' }}>
        {sector.total_tickers} tickers across {sector.sectors.length} sectors · as of {sector.as_of?.slice(0,16)}
      </div>

      <div style={{ display: 'grid', gap: 12 }}>
        {sector.sectors.map(s => (
          <div key={s.sector} style={{
            background: 'var(--bg-surface)', border: '1px solid var(--border)',
            borderRadius: 12, padding: '14px 18px',
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 10 }}>
              <div>
                <span style={{ fontWeight: 700, fontSize: 15, textTransform: 'capitalize' }}>
                  {s.sector.replace(/_/g, ' ')}
                </span>
                <span style={{ marginLeft: 10, fontSize: 12, color: 'var(--ink-3)' }}>
                  {s.ticker_count} ticker{s.ticker_count !== 1 ? 's' : ''}
                </span>
              </div>
              <div style={{ textAlign: 'right' }}>
                <div style={{ fontWeight: 700, fontSize: 18, color: s.avg_score >= 0.6 ? PAL.green : s.avg_score < 0.45 ? PAL.red : 'var(--ink-1)' }}>
                  {(s.avg_score * 100).toFixed(1)}
                  <span style={{ fontSize: 11, fontWeight: 400, color: 'var(--ink-3)', marginLeft: 4 }}>avg score</span>
                </div>
                {s.rl_direction_accuracy != null && (
                  <div style={{ fontSize: 11, color: 'var(--ink-3)' }}>
                    RL: {(s.rl_direction_accuracy * 100).toFixed(0)}% direction accuracy
                  </div>
                )}
              </div>
            </div>

            {/* Verdict mini-bars */}
            <div style={{ display: 'flex', gap: 6, marginBottom: 8 }}>
              {verdicts.map((v, i) => {
                const n = s.verdict_dist?.[v] || 0;
                const pct = s.ticker_count ? Math.round(n / s.ticker_count * 100) : 0;
                return (
                  <div key={v} title={`${v}: ${n}`} style={{
                    flex: `${Math.max(pct, 5)} 0 0`,
                    height: 6, borderRadius: 3,
                    background: vColors[i], opacity: n ? 1 : 0.15,
                  }}/>
                );
              })}
            </div>
            <div style={{ display: 'flex', gap: 10, fontSize: 11, color: 'var(--ink-3)' }}>
              {verdicts.map((v, i) => {
                const n = s.verdict_dist?.[v] || 0;
                return n > 0 ? (
                  <span key={v} style={{ color: vColors[i], fontWeight: 600 }}>{n} {v}</span>
                ) : null;
              })}
            </div>

            <div style={{ display: 'flex', gap: 16, marginTop: 10, fontSize: 12 }}>
              <div>
                <span style={{ color: 'var(--ink-3)' }}>Best: </span>
                <span style={{ fontWeight: 600 }}>{s.best_ticker?.ticker}</span>
                <span style={{ color: PAL.green, marginLeft: 4 }}>{(s.best_ticker?.score * 100 || 0).toFixed(0)}</span>
              </div>
              <div>
                <span style={{ color: 'var(--ink-3)' }}>Weakest: </span>
                <span style={{ fontWeight: 600 }}>{s.worst_ticker?.ticker}</span>
                <span style={{ color: PAL.amber, marginLeft: 4 }}>{(s.worst_ticker?.score * 100 || 0).toFixed(0)}</span>
              </div>
              <div style={{ color: 'var(--ink-3)' }}>±{(s.score_stddev * 100).toFixed(1)} stddev</div>
            </div>
          </div>
        ))}
      </div>
    </>
  );
}

// ---------------------------------------------------------------------------
// Stat chip
// ---------------------------------------------------------------------------
function StatChip({ label, value, color }) {
  return (
    <div style={{
      padding: '10px 16px', borderRadius: 10,
      background: 'var(--bg-surface)', border: '1px solid var(--border)',
      minWidth: 100,
    }}>
      <div style={{ fontSize: 11, color: 'var(--ink-3)', marginBottom: 3 }}>{label}</div>
      <div style={{ fontWeight: 700, fontSize: 20, color: color || 'var(--ink-1)' }}>{value}</div>
    </div>
  );
}

window.AnalyticsPage = AnalyticsPage;
