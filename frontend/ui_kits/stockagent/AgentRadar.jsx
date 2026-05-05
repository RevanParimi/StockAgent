// AgentRadar — 8-axis radar chart showing all agent scores simultaneously.

const AgentRadar = ({ scores = {}, size = 340 }) => {
  const { AGENT_KEYS, AGENT_LABELS } = window.StockData;
  const cx = size / 2;
  const cy = size / 2;
  const r  = size * 0.36;
  const n  = AGENT_KEYS.length;

  const [reveal, setReveal] = useState(0);
  useEffect(() => {
    setReveal(0);
    const t0 = performance.now();
    const dur = 1200;
    let raf = 0;
    const step = (now) => {
      const t = Math.min((now - t0) / dur, 1);
      setReveal(1 - Math.pow(1 - t, 3));
      if (t < 1) raf = requestAnimationFrame(step);
    };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, []);

  const pointAt = (i, v) => {
    const a = -Math.PI / 2 + (i / n) * Math.PI * 2;
    return { x: cx + Math.cos(a) * r * v, y: cy + Math.sin(a) * r * v, a };
  };

  const ringLevels = [0.25, 0.50, 0.75, 1.00];

  const poly = AGENT_KEYS.map((k, i) => {
    const s = (scores[k]?.raw ?? 0) * reveal;
    const p = pointAt(i, s);
    return `${p.x},${p.y}`;
  }).join(' ');

  return (
    <GlassCard>
      <div className="flex items-center justify-between mb-2">
        <div>
          <div className="text-[10px] font-bold tracking-[0.15em] text-text-muted uppercase">Agent Radar</div>
          <div className="text-[15px] font-semibold text-text-primary mt-0.5">8-axis conviction shape</div>
        </div>
        <div className="flex items-center gap-3 text-[10px] font-mono text-text-muted">
          <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-sm" style={{background:'#06b6d4'}}/>score</span>
          <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-sm" style={{background:'#334155'}}/>grid</span>
        </div>
      </div>

      <div className="flex justify-center">
        <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
          {/* Rings */}
          {ringLevels.map((lv, idx) => {
            const pts = AGENT_KEYS.map((_, i) => {
              const p = pointAt(i, lv);
              return `${p.x},${p.y}`;
            }).join(' ');
            return <polygon key={idx} points={pts} fill="none" stroke="#1e293b" strokeWidth="1"/>;
          })}
          {/* Axes */}
          {AGENT_KEYS.map((k, i) => {
            const end = pointAt(i, 1);
            return <line key={k} x1={cx} y1={cy} x2={end.x} y2={end.y} stroke="#1e293b" strokeWidth="1"/>;
          })}
          {/* Score polygon — filled */}
          <polygon
            points={poly}
            fill="rgba(6,182,212,0.18)"
            stroke="#06b6d4"
            strokeWidth="2"
            strokeLinejoin="round"
            style={{ filter: 'drop-shadow(0 0 8px rgba(6,182,212,0.5))' }}
          />
          {/* Score dots */}
          {AGENT_KEYS.map((k, i) => {
            const s = (scores[k]?.raw ?? 0) * reveal;
            const p = pointAt(i, s);
            const c = scoreColor(scores[k]?.raw ?? 0);
            return <circle key={k} cx={p.x} cy={p.y} r="4" fill={c} stroke="#050810" strokeWidth="1.5"
                           style={{ filter: `drop-shadow(0 0 4px ${c})` }}/>;
          })}
          {/* Axis labels */}
          {AGENT_KEYS.map((k, i) => {
            const lblPt = pointAt(i, 1.22);
            const short = AGENT_LABELS[k].split(' ')[0];
            return (
              <text key={k}
                x={lblPt.x} y={lblPt.y}
                fontSize="10" fontWeight="700"
                fill="#94a3b8" textAnchor="middle" dominantBaseline="middle"
                style={{ letterSpacing: '0.05em', textTransform: 'uppercase' }}>
                {short}
              </text>
            );
          })}
          {/* Ring ticks (0.25, 0.5, 0.75, 1.0) on vertical axis */}
          {ringLevels.map((lv, idx) => (
            <text key={idx}
              x={cx + 4} y={cy - r * lv + 3}
              fontSize="8" fill="#475569" fontFamily="JetBrains Mono, monospace">
              {lv.toFixed(2)}
            </text>
          ))}
        </svg>
      </div>
    </GlassCard>
  );
};

window.AgentRadar = AgentRadar;
