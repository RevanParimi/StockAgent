// ConvictionPanel — two-column conviction drivers / top risks list.

const ConvictionPanel = ({ drivers = [], risks = [], conflicts = [] }) => {
  return (
    <GlassCard>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Drivers */}
        <div>
          <div className="flex items-center gap-2 mb-3">
            <div className="w-5 h-5 rounded-md flex items-center justify-center"
                 style={{ background: 'rgba(34,197,94,0.15)', border: '1px solid rgba(34,197,94,0.4)' }}>
              <IconCheck size={13} stroke="#22c55e"/>
            </div>
            <h3 className="text-[14px] font-bold text-text-primary">Conviction Drivers</h3>
            <span className="ml-auto font-mono text-[10px] text-text-muted">{drivers.length}</span>
          </div>
          <ul className="space-y-2.5">
            {drivers.map((d, i) => (
              <li key={i} className="flex items-start gap-2.5 text-[13px] text-text-secondary leading-[1.55]">
                <span className="font-mono text-[10px] font-bold text-buy-strong mt-1 w-4 shrink-0">{String(i + 1).padStart(2, '0')}</span>
                <span>{d}</span>
              </li>
            ))}
          </ul>
        </div>

        {/* Risks */}
        <div className="md:border-l md:border-[rgba(30,41,59,0.9)] md:pl-6">
          <div className="flex items-center gap-2 mb-3">
            <div className="w-5 h-5 rounded-md flex items-center justify-center"
                 style={{ background: 'rgba(239,68,68,0.15)', border: '1px solid rgba(239,68,68,0.4)' }}>
              <IconX size={13} stroke="#ef4444"/>
            </div>
            <h3 className="text-[14px] font-bold text-text-primary">Top Risks</h3>
            <span className="ml-auto font-mono text-[10px] text-text-muted">{risks.length}</span>
          </div>
          <ul className="space-y-2.5">
            {risks.map((r, i) => (
              <li key={i} className="flex items-start gap-2.5 text-[13px] text-text-secondary leading-[1.55]">
                <span className="font-mono text-[10px] font-bold text-sell-strong mt-1 w-4 shrink-0">{String(i + 1).padStart(2, '0')}</span>
                <span>{r}</span>
              </li>
            ))}
          </ul>
        </div>
      </div>

      {conflicts.length > 0 && (
        <div className="mt-5 pt-5 border-t border-[rgba(30,41,59,0.9)]">
          <div className="flex items-center gap-2 mb-2">
            <div className="w-5 h-5 rounded-md flex items-center justify-center"
                 style={{ background: 'rgba(139,92,246,0.15)', border: '1px solid rgba(139,92,246,0.4)' }}>
              <IconRefresh size={13} stroke="#8b5cf6"/>
            </div>
            <h3 className="text-[13px] font-bold text-text-primary">Conflicts resolved by LLM</h3>
            <span className="ml-auto font-mono text-[10px] text-text-muted">{conflicts.length}</span>
          </div>
          {conflicts.map((c, i) => (
            <div key={i}
              className="text-[12px] text-text-secondary leading-[1.6] p-3 rounded-lg"
              style={{ background: 'rgba(139,92,246,0.05)', border: '1px solid rgba(139,92,246,0.2)' }}>
              {c}
            </div>
          ))}
        </div>
      )}
    </GlassCard>
  );
};

window.ConvictionPanel = ConvictionPanel;
