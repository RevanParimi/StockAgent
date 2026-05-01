// HistoryLine — score trend over time (sparkline-style).

const HistoryLine = ({ history = [], width = 640, height = 180 }) => {
  if (!history.length) return null;
  const pad = { l: 36, r: 16, t: 16, b: 26 };
  const W = width - pad.l - pad.r;
  const H = height - pad.t - pad.b;
  const n = history.length;
  const x = (i) => pad.l + (i / (n - 1)) * W;
  const y = (v) => pad.t + (1 - v) * H;

  const points = history.map((h, i) => [x(i), y(h.score)]);
  const path = 'M ' + points.map(p => p.join(',')).join(' L ');
  const fill = `${path} L ${x(n - 1)},${pad.t + H} L ${x(0)},${pad.t + H} Z`;

  const latest = history[history.length - 1];
  const first  = history[0];
  const delta  = latest.score - first.score;
  const deltaPct = (delta / first.score) * 100;

  return (
    <GlassCard>
      <div className="flex items-start justify-between mb-3">
        <div>
          <div className="text-[10px] font-bold tracking-[0.15em] text-text-muted uppercase">Score History</div>
          <div className="flex items-baseline gap-3 mt-0.5">
            <span className="text-[15px] font-semibold text-text-primary">90-day trend</span>
            <span className="font-mono text-[11px] text-text-muted">{n} data points</span>
          </div>
        </div>
        <div className="text-right">
          <div className="font-mono text-xl font-bold tabular-nums" style={{ color: scoreColor(latest.score) }}>
            {latest.score.toFixed(2)}
          </div>
          <div className={`font-mono text-[11px] font-semibold flex items-center gap-1 justify-end ${delta >= 0 ? 'text-buy' : 'text-sell'}`}>
            {delta >= 0 ? <IconTrendUp size={11}/> : <IconTrendDn size={11}/>}
            {delta >= 0 ? '+' : ''}{delta.toFixed(2)} ({deltaPct >= 0 ? '+' : ''}{deltaPct.toFixed(1)}%)
          </div>
        </div>
      </div>

      <svg width="100%" height={height} viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none">
        <defs>
          <linearGradient id="hist-fill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#06b6d4" stopOpacity="0.25"/>
            <stop offset="100%" stopColor="#06b6d4" stopOpacity="0"/>
          </linearGradient>
        </defs>
        {/* Horizontal guide lines */}
        {[0.30, 0.45, 0.60, 0.75].map(lv => (
          <g key={lv}>
            <line x1={pad.l} x2={pad.l + W} y1={y(lv)} y2={y(lv)} stroke="#1e293b" strokeDasharray="2 4"/>
            <text x={4} y={y(lv) + 3} fontSize="9" fontFamily="JetBrains Mono, monospace" fill="#475569">{lv.toFixed(2)}</text>
          </g>
        ))}
        {/* Zone tint — strong buy band */}
        <rect x={pad.l} y={y(1.0)} width={W} height={y(0.75) - y(1.0)} fill="rgba(34,197,94,0.04)"/>
        {/* Area */}
        <path d={fill} fill="url(#hist-fill)"/>
        {/* Line */}
        <path d={path} fill="none" stroke="#06b6d4" strokeWidth="2" strokeLinejoin="round"
              style={{ filter: 'drop-shadow(0 0 4px rgba(6,182,212,0.6))' }}/>
        {/* End point */}
        <circle cx={points[points.length - 1][0]} cy={points[points.length - 1][1]} r="4"
                fill={scoreColor(latest.score)} stroke="#050810" strokeWidth="2"
                style={{ filter: `drop-shadow(0 0 6px ${scoreColor(latest.score)})` }}/>
        {/* X-axis dates (first, mid, last) */}
        {[0, Math.floor(n/2), n - 1].map(i => (
          <text key={i} x={x(i)} y={height - 6} fontSize="9" fontFamily="JetBrains Mono, monospace" fill="#475569"
                textAnchor={i === 0 ? 'start' : i === n - 1 ? 'end' : 'middle'}>
            {history[i].date.slice(5)}
          </text>
        ))}
      </svg>
    </GlassCard>
  );
};

window.HistoryLine = HistoryLine;
