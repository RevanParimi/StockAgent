// VerdictReveal — hero card with score gauge + verdict badge + animated counter
// In the original product, it flips 180° on reveal. Here it scales + fades in.

const VerdictReveal = ({ ticker, companyName, score, reportDate, elapsedSeconds, agentsCount = 8, conflicts = 0, revealed = true }) => {
  const [visible, setVisible] = useState(false);
  useEffect(() => {
    if (revealed) {
      const t = setTimeout(() => setVisible(true), 80);
      return () => clearTimeout(t);
    } else {
      setVisible(false);
    }
  }, [revealed]);

  const color = scoreColor(score);
  const verdict = scoreToVerdict(score);

  return (
    <div
      className="relative rounded-[20px] p-6 md:p-8 overflow-hidden"
      style={{
        background:
          'radial-gradient(ellipse at top, rgba(6,182,212,0.08), transparent 60%), rgba(12,17,32,0.85)',
        border: `1px solid ${color}40`,
        boxShadow: `0 0 40px ${color}33, inset 0 0 80px rgba(6,182,212,0.04)`,
        backdropFilter: 'blur(20px)',
        transform: visible ? 'scale(1) translateY(0)' : 'scale(0.95) translateY(12px)',
        opacity: visible ? 1 : 0,
        transition: 'transform 700ms cubic-bezier(0.4,0,0.2,1), opacity 700ms',
      }}
    >
      {/* Decorative corner crosshairs */}
      {['top-3 left-3', 'top-3 right-3', 'bottom-3 left-3', 'bottom-3 right-3'].map((pos, i) => (
        <div key={i} className={`absolute ${pos} w-3 h-3 pointer-events-none`}
             style={{
               borderTop:  pos.includes('top')    ? `1px solid ${color}60` : 'none',
               borderBottom: pos.includes('bottom') ? `1px solid ${color}60` : 'none',
               borderLeft:  pos.includes('left')   ? `1px solid ${color}60` : 'none',
               borderRight: pos.includes('right')  ? `1px solid ${color}60` : 'none',
             }}/>
      ))}

      <div className="grid grid-cols-1 lg:grid-cols-[1fr_auto] gap-8 items-center">
        <div className="min-w-0">
          {/* Ticker line */}
          <div className="flex items-center gap-2 mb-2">
            <span className="text-[10px] font-bold tracking-[0.2em] text-text-muted uppercase">NSE</span>
            <span className="text-text-muted">·</span>
            <span className="text-[10px] font-bold tracking-[0.2em] text-text-muted uppercase">Report</span>
            <span className="text-text-muted">·</span>
            <span className="text-[10px] font-mono text-text-muted">{reportDate}</span>
          </div>
          <div className="flex items-baseline gap-3 flex-wrap">
            <h1 className="font-mono font-extrabold tracking-wide text-4xl md:text-5xl text-text-primary">
              {ticker}
            </h1>
            <div className="text-text-secondary text-base md:text-lg font-medium">{companyName}</div>
          </div>
          <div className="mt-5 flex items-center gap-3 flex-wrap">
            <VerdictBadge verdict={verdict} size="lg" glow />
            <div className="text-[13px] text-text-secondary leading-snug max-w-md">
              Composite score synthesized from <span className="font-mono text-text-primary">{agentsCount}</span> specialist agents.
              Conviction weighted, conflicts LLM-resolved.
            </div>
          </div>

          {/* Meta strip */}
          <div className="mt-6 flex items-center gap-5 flex-wrap text-[11px] font-mono text-text-muted">
            <div className="flex items-center gap-1.5">
              <IconClock size={12}/> <span className="text-text-secondary">{elapsedSeconds}s</span>
            </div>
            <div className="flex items-center gap-1.5">
              <IconSparkle size={12}/> <span className="text-text-secondary">{agentsCount} agents</span>
            </div>
            <div className="flex items-center gap-1.5">
              <IconRefresh size={12}/> <span className="text-text-secondary">{conflicts} conflicts resolved</span>
            </div>
          </div>
        </div>

        {/* Gauge on the right */}
        <div className="flex-shrink-0 self-center lg:self-start">
          <ScoreGauge score={score} size={240} label="FINAL SCORE" animate={visible}/>
        </div>
      </div>

      {/* Action row */}
      <div className="mt-6 pt-5 border-t border-[rgba(30,41,59,0.9)] flex items-center gap-2 flex-wrap">
        <GlowButton variant="cyan" size="sm">
          <IconDownload size={14}/> Download report
        </GlowButton>
        <GlowButton variant="outline" size="sm">
          <IconClipboard size={14}/> Copy thesis
        </GlowButton>
        <GlowButton variant="outline" size="sm">
          <IconRefresh size={14}/> Re-run analysis
        </GlowButton>
        <div className="ml-auto text-[11px] font-mono text-text-muted">
          agent report · generated in <span className="text-text-secondary">{elapsedSeconds}s</span>
        </div>
      </div>
    </div>
  );
};

window.VerdictReveal = VerdictReveal;
