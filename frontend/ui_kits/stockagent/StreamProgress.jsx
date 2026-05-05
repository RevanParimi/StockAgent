// StreamProgress — strip above agent grid showing N/8 agents complete + elapsed.

const StreamProgress = ({ total = 8, complete = 0, elapsed = 0, running = false, currentAgent = null }) => {
  const pct = Math.round((complete / total) * 100);
  return (
    <GlassCard className="!p-4">
      <div className="flex items-center justify-between gap-4 flex-wrap">
        <div className="flex items-center gap-3">
          <div className={`w-2.5 h-2.5 rounded-full ${running ? 'bg-accent-cyan pulse-ring' : complete === total ? 'bg-buy-strong' : 'bg-text-muted'}`}/>
          <div>
            <div className="text-[13px] font-semibold text-text-primary">
              {running
                ? <>Analyzing <span className="font-mono text-accent-cyan">{currentAgent || '…'}</span></>
                : complete === total
                  ? 'Analysis complete'
                  : 'Stream idle'}
            </div>
            <div className="text-[11px] text-text-muted mt-0.5">
              <span className="font-mono">{complete}</span> / <span className="font-mono">{total}</span> agents
              <span className="mx-1.5">·</span>
              <span className="font-mono">{elapsed}s</span> elapsed
              <span className="mx-1.5">·</span>
              <span className="font-mono">/ws/stream</span>
            </div>
          </div>
        </div>
        <div className="font-mono text-[11px] text-text-muted tabular-nums">
          <span className="text-accent-cyan font-bold">{pct}%</span>
        </div>
      </div>
      <div className="mt-3 h-[3px] rounded-full overflow-hidden bg-[rgba(30,41,59,0.9)]">
        <div className="h-full transition-all duration-500 ease-out"
             style={{
               width: `${pct}%`,
               background: 'linear-gradient(90deg, #06b6d4, #3b82f6)',
               boxShadow: '0 0 8px rgba(6,182,212,0.5)',
             }}/>
      </div>
    </GlassCard>
  );
};

window.StreamProgress = StreamProgress;
