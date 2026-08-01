/* weekly-view.jsx — weekly review, native (spec 2026-07-31 §3.3 / D5).
 * The old text renderer emitted flat "Laggard: X +1.2%" lines; this groups them. */
function WeeklyView({ data }) {
  const d = data || {};
  const alloc = d.allocation || [];
  const conc = d.concentration_flags || [];
  const laggards = d.laggards || [];
  const cands = d.switch_candidates || [];
  const sugg = d.switch_suggestions || [];
  const sb = d.scoreboard || {};

  return (
    <div>
      <div style={{ background: 'var(--bg-surface)', border: '1px solid var(--border)',
        borderRadius: 14, marginBottom: 10, padding: '16px 14px' }}>
        <div style={{ font: '700 10px Inter, sans-serif', letterSpacing: '.1em',
          textTransform: 'uppercase', color: 'var(--ink-3)', marginBottom: 8 }}>
          Weekly review · {bvLongDate(d.date)}
        </div>
        {d.headline ? <div style={{ fontSize: 14, lineHeight: 1.5, color: 'var(--ink-1)' }}>
          {d.headline}</div> : null}
        {typeof sb.checked === 'number' && sb.checked > 0 ? (
          <div style={{ marginTop: 12, paddingTop: 12, borderTop: '1px solid var(--border)' }}>
            <span style={{ font: '800 19px/1 Inter, sans-serif', color: 'var(--ink-1)' }}>
              {sb.correct}/{sb.checked}
            </span>
            <span style={{ color: 'var(--ink-3)', fontSize: 12, marginLeft: 8 }}>
              judged calls right
            </span>
          </div>
        ) : null}
      </div>

      {alloc.length > 0 && (
        <BVFold title="Sector allocation" summary={alloc.length}>
          {alloc.map((a, i) => {
            const over = conc.indexOf(a.sector) !== -1;
            return (
              <div key={i} style={{ padding: '9px 0', borderTop: '1px solid var(--border)' }}>
                <span style={{ color: 'var(--ink-1)', fontWeight: 600 }}>{a.sector}</span>
                <span style={{ float: 'right', font: '700 12px "JetBrains Mono", monospace',
                  color: over ? '#b45309' : 'var(--ink-2)' }}>
                  {Number(a.weight_pct).toFixed(1)}%
                </span>
                {over ? <div style={{ color: '#b45309', fontSize: 11.5, marginTop: 3 }}>
                  ⚠ over-concentrated</div> : null}
              </div>
            );
          })}
        </BVFold>
      )}

      {laggards.length > 0 && (
        <BVFold title="Laggards" summary={laggards.length}>
          {laggards.map((l, i) => (
            <div key={i} style={{ padding: '9px 0', borderTop: '1px solid var(--border)' }}>
              <span style={{ fontWeight: 800, color: 'var(--ink-1)' }}>{l.symbol}</span>
              <span style={{ float: 'right', font: '700 12px "JetBrains Mono", monospace',
                color: l.pnl_pct >= 0 ? '#15803d' : '#b91c1c' }}>
                {l.pnl_pct >= 0 ? '+' : ''}{Number(l.pnl_pct).toFixed(1)}%
              </span>
            </div>
          ))}
        </BVFold>
      )}

      {(cands.length > 0 || sugg.length > 0) && (
        <BVFold title="Switch ideas" summary={sugg.length || cands.length}>
          <div style={{ color: 'var(--ink-3)', fontSize: 12, marginBottom: 4 }}>
            The tool's own view — not personal advice.
          </div>
          {sugg.map((s, i) => (
            <div key={'s' + i} style={{ padding: '9px 0', borderTop: '1px solid var(--border)' }}>
              <b style={{ color: 'var(--ink-1)' }}>{s.symbol}</b>
              <span style={{ color: 'var(--cyan)' }}> → </span>
              <b style={{ color: 'var(--ink-1)' }}>{s.switch_candidate}</b>
            </div>
          ))}
          {cands.map((c, i) => (
            <div key={'c' + i} style={{ padding: '9px 0', borderTop: '1px solid var(--border)' }}>
              <b style={{ color: 'var(--ink-1)' }}>{c.symbol}</b>
              <span style={{ color: 'var(--ink-3)', fontSize: 11.5 }}> · {c.sector}</span>
              {typeof c.conviction === 'number' ? (
                <span style={{ float: 'right', font: '700 12px "JetBrains Mono", monospace',
                  color: 'var(--ink-2)' }}>{Math.round(c.conviction * 100)}%</span>
              ) : null}
            </div>
          ))}
        </BVFold>
      )}

      <div style={{ textAlign: 'center', fontSize: 10.5, color: 'var(--ink-3)', padding: '10px 0 4px' }}>
        Research tool — information only, never advice.
      </div>
    </div>
  );
}

window.WeeklyView = WeeklyView;
