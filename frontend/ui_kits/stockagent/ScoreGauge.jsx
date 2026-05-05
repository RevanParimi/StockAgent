// ScoreGauge — semi-circular gauge with RAF-eased needle sweep.
// Zones: 0.00–0.30 red · 0.30–0.45 orange · 0.45–0.60 amber · 0.60–0.75 lightgreen · 0.75–1.00 green.

const ScoreGauge = ({ score = 0, size = 220, label = 'COMPOSITE', animate = true, showNeedle = true }) => {
  const [swept, setSwept] = useState(animate ? 0 : score);
  const rafRef = useRef(0);

  useEffect(() => {
    if (!animate) { setSwept(score); return; }
    setSwept(0);
    const t0 = performance.now();
    const dur = 1500;
    const step = (now) => {
      const t = Math.min((now - t0) / dur, 1);
      const eased = 1 - Math.pow(1 - t, 3);
      setSwept(eased * score);
      if (t < 1) rafRef.current = requestAnimationFrame(step);
    };
    rafRef.current = requestAnimationFrame(step);
    return () => cancelAnimationFrame(rafRef.current);
  }, [score, animate]);

  const cx = size / 2;
  const cy = size * 0.58;
  const r  = size * 0.38;
  const stroke = Math.max(10, size * 0.065);

  // Arc from 180° to 360° (left to right across the top).
  const polar = (t) => {
    // t in 0..1 → angle in radians from π (left) to 2π (right)
    const a = Math.PI + t * Math.PI;
    return { x: cx + r * Math.cos(a), y: cy + r * Math.sin(a) };
  };
  const arc = (t0, t1) => {
    const s = polar(t0), e = polar(t1);
    const large = (t1 - t0) > 0.5 ? 1 : 0;
    return `M ${s.x} ${s.y} A ${r} ${r} 0 ${large} 1 ${e.x} ${e.y}`;
  };

  const zones = [
    { t0: 0.00, t1: 0.30, color: '#ef4444' },
    { t0: 0.30, t1: 0.45, color: '#f97316' },
    { t0: 0.45, t1: 0.60, color: '#f59e0b' },
    { t0: 0.60, t1: 0.75, color: '#4ade80' },
    { t0: 0.75, t1: 1.00, color: '#22c55e' },
  ];

  const displayed = Number(swept.toFixed(2));
  const color = scoreColor(displayed);
  const tip = polar(displayed);
  const verdict = scoreToVerdict(displayed);

  return (
    <div className="relative inline-flex flex-col items-center" style={{ width: size }}>
      <svg width={size} height={size * 0.72} viewBox={`0 0 ${size} ${size * 0.72}`}>
        {/* Background track */}
        <path
          d={arc(0, 1)}
          fill="none"
          stroke="#1e293b"
          strokeWidth={stroke}
          strokeLinecap="round"
        />
        {/* Colored zones (dim) */}
        {zones.map((z, i) => (
          <path key={i}
            d={arc(z.t0, z.t1)}
            fill="none"
            stroke={z.color}
            strokeWidth={stroke}
            strokeLinecap="butt"
            opacity={0.20}
          />
        ))}
        {/* Active arc, bright, with filter glow */}
        {displayed > 0.005 && (
          <path
            d={arc(0, displayed)}
            fill="none"
            stroke={color}
            strokeWidth={stroke}
            strokeLinecap="round"
            style={{ filter: `drop-shadow(0 0 8px ${color})` }}
          />
        )}
        {/* Tick marks at zone boundaries */}
        {[0.30, 0.45, 0.60, 0.75].map((t, i) => {
          const inner = {
            x: cx + (r - stroke / 2 - 2) * Math.cos(Math.PI + t * Math.PI),
            y: cy + (r - stroke / 2 - 2) * Math.sin(Math.PI + t * Math.PI),
          };
          const outer = {
            x: cx + (r + stroke / 2 + 2) * Math.cos(Math.PI + t * Math.PI),
            y: cy + (r + stroke / 2 + 2) * Math.sin(Math.PI + t * Math.PI),
          };
          return <line key={i} x1={inner.x} y1={inner.y} x2={outer.x} y2={outer.y} stroke="#334155" strokeWidth="1.5"/>;
        })}
        {/* Needle */}
        {showNeedle && (
          <>
            <line
              x1={cx} y1={cy}
              x2={tip.x} y2={tip.y}
              stroke={color}
              strokeWidth="2.5"
              strokeLinecap="round"
              style={{ filter: `drop-shadow(0 0 6px ${color})` }}
            />
            <circle cx={cx} cy={cy} r={stroke * 0.35} fill={color}
                    style={{ filter: `drop-shadow(0 0 6px ${color})` }} />
            <circle cx={cx} cy={cy} r={stroke * 0.16} fill="#050810"/>
          </>
        )}
      </svg>
      {/* Readout overlay */}
      <div
        className="absolute inset-x-0 flex flex-col items-center text-center"
        style={{ top: size * 0.32 }}
      >
        <div className="text-[10px] font-bold tracking-[0.15em] text-text-muted uppercase mb-1">{label}</div>
        <div className="font-mono font-extrabold tabular-nums leading-none"
             style={{ fontSize: size * 0.22, color }}>
          {displayed.toFixed(2)}
        </div>
      </div>
      {/* Zone labels below */}
      <div className="flex items-center justify-between w-full mt-2 px-1">
        <span className="font-mono text-[10px] text-text-muted">0.00</span>
        <span className="font-semibold text-[11px] tracking-wider" style={{ color }}>
          {verdict}
        </span>
        <span className="font-mono text-[10px] text-text-muted">1.00</span>
      </div>
    </div>
  );
};

window.ScoreGauge = ScoreGauge;
