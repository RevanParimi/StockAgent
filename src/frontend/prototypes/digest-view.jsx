/* digest-view.jsx — EOD digest, native (spec 2026-07-31 §3.3 / D5).
 * Reuses BriefView's card + fold vocabulary. Holdings are grouped so the ones
 * carrying a non-HOLD verdict lead. */
function DigestView({ data }) {
  const d = data || {};
  const holdings = d.holdings || [];
  const esc = d.escalations || [];
  const flagged = holdings.filter(h => h.verdict && h.verdict !== 'HOLD' && h.verdict !== 'NO_DATA');
  const steady = holdings.filter(h => !flagged.includes(h));
  const pnl = typeof d.total_pnl_pct === 'number' ? d.total_pnl_pct : null;

  const row = (h, i) => (
    <div key={i} style={{ padding: '9px 0', borderTop: '1px solid var(--border)' }}>
      <span style={{ fontWeight: 800, color: 'var(--ink-1)', fontSize: 13 }}>{h.symbol}</span>
      {h.verdict ? <BVChip verdict={h.verdict} label={h.verdict}/> : null}
      {typeof h.pnl_pct === 'number' ? (
        <span style={{ float: 'right', font: '700 12px "JetBrains Mono", monospace',
          color: h.pnl_pct >= 0 ? '#15803d' : '#b91c1c' }}>
          {h.pnl_pct >= 0 ? '+' : ''}{h.pnl_pct.toFixed(1)}%
        </span>
      ) : null}
      {h.reason ? <div style={{ color: 'var(--ink-3)', fontSize: 12, marginTop: 3 }}>{h.reason}</div> : null}
    </div>
  );

  return (
    <div>
      <div style={{ background: 'var(--bg-surface)', border: '1px solid var(--border)',
        borderRadius: 14, marginBottom: 10, padding: '16px 14px' }}>
        <div style={{ font: '700 10px Inter, sans-serif', letterSpacing: '.1em',
          textTransform: 'uppercase', color: 'var(--ink-3)', marginBottom: 8 }}>
          EOD digest · {bvLongDate(d.date)}
        </div>
        <div style={{ font: '800 22px/1 Inter, sans-serif', color: 'var(--ink-1)' }}>
          {bvINR(d.portfolio_value)}
          {pnl !== null ? (
            <span style={{ fontSize: 15, marginLeft: 10, color: pnl >= 0 ? '#15803d' : '#b91c1c' }}>
              {pnl >= 0 ? '▲' : '▼'} {Math.abs(pnl).toFixed(1)}%
            </span>
          ) : null}
        </div>
        <div style={{ color: 'var(--ink-3)', fontSize: 12, marginTop: 4 }}>
          {holdings.length} holding{holdings.length === 1 ? '' : 's'} · total P&amp;L
        </div>
      </div>

      {flagged.length > 0 && (
        <div style={{ background: 'var(--bg-surface)', border: '1px solid var(--border)',
          borderLeft: '3px solid #f59e0b', borderRadius: 14, marginBottom: 10 }}>
          <div style={{ font: '700 10px Inter, sans-serif', letterSpacing: '.13em',
            textTransform: 'uppercase', color: '#b45309', padding: '13px 14px 0' }}>
            Flagged · {flagged.length}
          </div>
          <div style={{ padding: '8px 14px 13px' }}>{flagged.map(row)}</div>
        </div>
      )}

      {steady.length > 0 && (
        <BVFold title="Holding steady" summary={steady.length}>{steady.map(row)}</BVFold>
      )}

      {esc.length > 0 && (
        <BVFold title="Escalations" summary={esc.length}>
          {esc.map((s, i) => (
            <div key={i} style={{ padding: '9px 0', borderTop: '1px solid var(--border)',
              fontWeight: 700, color: 'var(--ink-1)' }}>{s}</div>
          ))}
        </BVFold>
      )}

      <div style={{ textAlign: 'center', fontSize: 10.5, color: 'var(--ink-3)', padding: '10px 0 4px' }}>
        Research tool — information only, never advice.
      </div>
    </div>
  );
}

window.DigestView = DigestView;
