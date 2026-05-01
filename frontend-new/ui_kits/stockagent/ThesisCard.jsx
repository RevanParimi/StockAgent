// ThesisCard — long-form investment thesis paragraph

const ThesisCard = ({ ticker, thesis }) => (
  <GlassCard>
    <div className="flex items-center justify-between mb-4">
      <div className="flex items-center gap-2">
        <IconSparkle size={16} stroke="#06b6d4"/>
        <div>
          <div className="text-[10px] font-bold tracking-[0.15em] text-text-muted uppercase">Investment Thesis</div>
          <div className="text-[15px] font-semibold text-text-primary">{ticker} · LLM synthesis</div>
        </div>
      </div>
      <div className="flex items-center gap-1.5">
        <button className="w-8 h-8 rounded-lg flex items-center justify-center text-text-muted hover:text-text-primary hover:bg-[rgba(255,255,255,0.04)] transition-all">
          <IconCopy size={14}/>
        </button>
        <button className="w-8 h-8 rounded-lg flex items-center justify-center text-text-muted hover:text-text-primary hover:bg-[rgba(255,255,255,0.04)] transition-all">
          <IconDownload size={14}/>
        </button>
        <button className="w-8 h-8 rounded-lg flex items-center justify-center text-text-muted hover:text-text-primary hover:bg-[rgba(255,255,255,0.04)] transition-all">
          <IconPrinter size={14}/>
        </button>
      </div>
    </div>

    <div className="space-y-4">
      {thesis.split('\n\n').map((para, i) => (
        <p key={i} className="text-[14px] text-text-secondary" style={{ lineHeight: 1.8 }}>
          {para}
        </p>
      ))}
    </div>

    <div className="mt-5 pt-4 border-t border-[rgba(30,41,59,0.9)] flex items-center gap-4 text-[10px] font-mono text-text-muted">
      <span>model: claude-sonnet-4.5</span>
      <span className="text-text-muted">·</span>
      <span>temperature: 0.2</span>
      <span className="text-text-muted">·</span>
      <span>sources: 8 agents</span>
    </div>
  </GlassCard>
);

window.ThesisCard = ThesisCard;
