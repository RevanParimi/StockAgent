// ScoreTable — sortable-looking weighted score breakdown table.

const ScoreTable = ({ scores = {} }) => {
  const { AGENT_KEYS, AGENT_LABELS, AGENT_ICONS } = window.StockData;
  const rows = AGENT_KEYS.map(k => ({
    key: k, label: AGENT_LABELS[k], icon: AGENT_ICONS[k],
    raw: scores[k]?.raw ?? 0,
    weight: scores[k]?.weight ?? 0,
    weighted: scores[k]?.weighted ?? 0,
  })).sort((a, b) => b.weighted - a.weighted);

  const total = rows.reduce((s, r) => s + r.weighted, 0);

  return (
    <GlassCard>
      <div className="flex items-center justify-between mb-4">
        <div>
          <div className="text-[10px] font-bold tracking-[0.15em] text-text-muted uppercase">Score Breakdown</div>
          <div className="text-[15px] font-semibold text-text-primary mt-0.5">Weighted contribution</div>
        </div>
        <span className="text-[10px] font-mono text-text-muted">sorted by impact</span>
      </div>

      <div className="grid grid-cols-[auto_1fr_60px_60px_72px] gap-x-3 gap-y-0 text-[9px] font-bold tracking-wider text-text-muted uppercase pb-2 border-b border-[rgba(30,41,59,0.8)]">
        <div></div>
        <div>Agent</div>
        <div className="text-right">Raw</div>
        <div className="text-right">Wt</div>
        <div className="text-right">Contrib</div>
      </div>

      {rows.map((r, i) => {
        const c = scoreColor(r.raw);
        return (
          <div key={r.key}
               className="grid grid-cols-[auto_1fr_60px_60px_72px] gap-x-3 items-center py-2.5 border-b border-[rgba(30,41,59,0.5)] last:border-b-0 hover:bg-[rgba(255,255,255,0.03)] transition-colors rounded-sm">
            <div className="text-base w-6 text-center">{r.icon}</div>
            <div className="min-w-0">
              <div className="text-[13px] font-semibold text-text-primary truncate">{r.label}</div>
              <div className="text-[10px] font-mono text-text-muted truncate">{r.key}</div>
            </div>
            <div className="text-right font-mono tabular-nums text-[13px] font-bold" style={{ color: c }}>
              {r.raw.toFixed(2)}
            </div>
            <div className="text-right font-mono tabular-nums text-[12px] text-text-secondary">
              {(r.weight * 100).toFixed(0)}%
            </div>
            <div className="text-right">
              <div className="font-mono tabular-nums text-[13px] text-text-primary font-semibold">
                {r.weighted.toFixed(3)}
              </div>
              <div className="mt-1 h-[2px] rounded-full bg-[rgba(30,41,59,0.8)] overflow-hidden">
                <div className="h-full" style={{ width: `${(r.weighted / 0.2) * 100}%`, background: c, boxShadow: `0 0 4px ${c}` }}/>
              </div>
            </div>
          </div>
        );
      })}

      <div className="mt-3 pt-3 border-t border-[rgba(30,41,59,0.8)] flex items-center justify-between">
        <span className="text-[11px] font-bold tracking-wider text-text-muted uppercase">Composite</span>
        <span className="font-mono text-xl font-extrabold tabular-nums" style={{ color: scoreColor(total) }}>
          {total.toFixed(2)}
        </span>
      </div>
    </GlassCard>
  );
};

window.ScoreTable = ScoreTable;
