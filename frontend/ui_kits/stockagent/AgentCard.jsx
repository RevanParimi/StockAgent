// AgentCard — tile representing one agent in the 2x4 grid.
// States: pending · analyzing (shimmer) · complete (spring-pop + verdict glow)

const AgentCard = ({ agentKey, label, icon, state = 'pending', score = 0, weight = 0, elapsed = 0 }) => {
  const prev = useRef(state);
  const [pop, setPop] = useState(false);

  useEffect(() => {
    if (prev.current !== 'complete' && state === 'complete') {
      setPop(true);
      const t = setTimeout(() => setPop(false), 420);
      return () => clearTimeout(t);
    }
    prev.current = state;
  }, [state]);

  const done = state === 'complete';
  const running = state === 'analyzing';
  const color = done ? scoreColor(score) : '#334155';
  const verdict = done ? scoreToVerdict(score) : null;

  const borderColor = running ? '#06b6d4' : done ? `${color}66` : 'rgba(30,41,59,0.8)';
  const glow = done ? `0 0 14px ${color}55` : running ? '0 0 14px rgba(6,182,212,0.35)' : 'none';

  return (
    <div
      className="relative overflow-hidden rounded-[12px] p-4 transition-all duration-300"
      style={{
        background: 'rgba(12,17,32,0.6)',
        border: `1px solid ${borderColor}`,
        boxShadow: glow,
        transform: pop ? 'scale(1.04)' : 'scale(1)',
      }}
    >
      {/* Shimmer bar on analyzing */}
      {running && (
        <div className="absolute inset-x-0 top-0 h-[2px] overflow-hidden">
          <div className="h-full w-1/3 shimmer-bar"
               style={{ background: 'linear-gradient(90deg, transparent, #06b6d4, transparent)' }}/>
        </div>
      )}

      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-3 min-w-0">
          <div
            className="shrink-0 w-9 h-9 rounded-lg flex items-center justify-center text-lg"
            style={{
              background: done ? `${color}1a` : running ? 'rgba(6,182,212,0.12)' : 'rgba(255,255,255,0.03)',
              border: `1px solid ${done ? `${color}55` : running ? 'rgba(6,182,212,0.35)' : 'rgba(30,41,59,0.8)'}`,
            }}
          >
            {icon}
          </div>
          <div className="min-w-0">
            <div className="text-[11px] text-text-muted uppercase tracking-wider font-semibold truncate">
              {agentKey}
            </div>
            <div className="text-[13px] text-text-primary font-semibold truncate">{label}</div>
          </div>
        </div>
        {/* Status pill */}
        <div className="shrink-0">
          {state === 'pending' && (
            <span className="text-[9px] font-bold tracking-wider text-text-muted uppercase">Queued</span>
          )}
          {running && (
            <span className="inline-flex items-center gap-1.5 text-[9px] font-bold tracking-wider text-accent-cyan uppercase">
              <span className="w-1.5 h-1.5 rounded-full bg-accent-cyan pulse-ring"/>
              Running
            </span>
          )}
          {done && <VerdictBadge verdict={verdict} size="sm" />}
        </div>
      </div>

      {/* Footer row */}
      <div className="mt-4 flex items-end justify-between gap-3">
        <div>
          <div className="text-[9px] text-text-muted uppercase tracking-wider font-semibold mb-0.5">Score</div>
          <div className="font-mono font-bold tabular-nums text-xl" style={{ color: done ? color : '#334155' }}>
            {done ? score.toFixed(2) : running ? <span className="text-text-muted">——</span> : '0.00'}
          </div>
        </div>
        <div className="text-right">
          <div className="text-[9px] text-text-muted uppercase tracking-wider font-semibold mb-0.5">Weight</div>
          <div className="font-mono text-[13px] text-text-secondary tabular-nums">{(weight * 100).toFixed(0)}%</div>
        </div>
      </div>

      {/* Mini progress bar */}
      <div className="mt-3 h-1 rounded-full overflow-hidden bg-[rgba(30,41,59,0.8)]">
        <div
          className="h-full transition-all duration-700 ease-out"
          style={{
            width: done ? `${Math.round(score * 100)}%` : running ? '40%' : '0%',
            background: done
              ? `linear-gradient(90deg, ${color}55, ${color})`
              : 'linear-gradient(90deg, #06b6d4, #3b82f6)',
            filter: done ? `drop-shadow(0 0 4px ${color})` : 'none',
          }}
        />
      </div>
    </div>
  );
};

window.AgentCard = AgentCard;
