/* weekly-view.jsx — weekly review, native (spec 2026-07-31 §3.3 / D5).
 * The old text renderer emitted flat "Laggard: X +1.2%" lines; this groups them. */
const WV_NOTE = { color: 'var(--ink-3)', fontSize: 12, marginBottom: 4 };
const WV_WHY = { marginTop: 5, fontSize: 12.5, lineHeight: 1.5, color: 'var(--ink-2)' };
const WV_LABEL = {
  font: '700 10px Inter, sans-serif', letterSpacing: '.09em',
  textTransform: 'uppercase', color: 'var(--ink-3)',
};

/* The week's results (core/portfolio/results.py). It renders the row's own
 * sentences, the same ones the email sends, so the two cannot disagree. Red
 * flags first, then flags that could not be checked: missing data is said. */
const WV_FLAG = { padding: '8px 10px', borderRadius: 8, marginBottom: 6,
  fontSize: 12.5, lineHeight: 1.45 };

function WVScorecard({ sc }) {
  if (sc === null) {
    return <div style={{ ...WV_NOTE, marginBottom: 10 }}>
      Results could not be computed this week.</div>;
  }
  const lines = (sc && sc.lines) || [];
  if (!lines.length) return null;
  const s = sc.sessions || {};
  const of = (kind) => lines.filter((l) => l.kind === kind);
  const checks = of('check');
  return (
    <div style={{ marginBottom: 12 }}>
      <div style={{ ...WV_LABEL, marginBottom: 6 }}>
        Results{s.first && s.last ? ` · ${bvShortDate(s.first)} – ${bvShortDate(s.last)}` : ''}
      </div>
      {of('red_flag').map((l, i) => (
        <div key={'f' + i} style={{ ...WV_FLAG, background: 'rgba(185,28,28,.08)',
          color: '#b91c1c' }}><b>Red flag · </b>{l.text}</div>
      ))}
      {of('unchecked').map((l, i) => (
        <div key={'u' + i} style={{ ...WV_FLAG, background: 'rgba(180,83,9,.08)',
          color: '#b45309' }}><b>Could not check · </b>{l.text}</div>
      ))}
      {of('line').map((l, i) => (
        <div key={'l' + i} style={{ ...WV_WHY, color: 'var(--ink-1)' }}>
          <span style={WV_LABEL}>{l.label} </span>{l.text}
        </div>
      ))}
      {checks.length > 0 && (
        <div style={{ ...WV_WHY, color: 'var(--ink-3)' }}>
          {checks.map((l, i) => <div key={'c' + i}>✓ {l.text}</div>)}
        </div>
      )}
      <div style={{ ...WV_NOTE, marginTop: 8 }}>
        A flag reports; it changes no decision. Figures are before costs and taxes.
      </div>
    </div>
  );
}

function WeeklyView({ data }) {
  const d = data || {};
  const alloc = d.allocation || [];
  const conc = d.concentration_flags || [];
  const laggards = d.laggards || [];
  const cands = d.switch_candidates || [];
  const sugg = d.switch_suggestions || [];

  return (
    <div>
      <div style={{ background: 'var(--bg-surface)', border: '1px solid var(--border)',
        borderRadius: 14, marginBottom: 10, padding: '16px 14px' }}>
        <div style={{ font: '700 10px Inter, sans-serif', letterSpacing: '.1em',
          textTransform: 'uppercase', color: 'var(--ink-3)', marginBottom: 8 }}>
          Weekly review · {bvLongDate(d.date)}
        </div>
        {'scorecard' in d ? <WVScorecard sc={d.scorecard} /> : null}
        {d.headline ? <div style={{ fontSize: 14, lineHeight: 1.5, color: 'var(--ink-1)' }}>
          {d.headline}</div> : null}
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
          {d.cash_pct != null ? (
            <div style={{ padding: '9px 0', borderTop: '1px solid var(--border)' }}>
              <span style={{ color: 'var(--ink-1)', fontWeight: 600 }}>cash</span>
              <span style={{ float: 'right', font: '700 12px "JetBrains Mono", monospace',
                color: 'var(--ink-2)' }}>{Number(d.cash_pct).toFixed(1)}%</span>
            </div>
          ) : null}
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

      {/* Two different claims, so two folds. These were one, and the shelf rows
        * read as if they annotated the arrows above them — they are tied to no
        * holding at all. */}
      {sugg.length > 0 && (
        <BVFold title="Switches called" summary={sugg.length}>
          <div style={WV_NOTE}>The tool's own view — not personal advice.</div>
          {sugg.map((s, i) => (
            <div key={'s' + i} style={{ padding: '11px 0', borderTop: '1px solid var(--border)' }}>
              <div>
                <b style={{ color: 'var(--ink-1)' }}>{s.symbol}</b>
                <span style={{ color: 'var(--cyan)' }}> → </span>
                <b style={{ color: 'var(--ink-1)' }}>{s.switch_candidate}</b>
                {s.date ? <span style={{ float: 'right', fontSize: 11,
                  color: 'var(--ink-3)' }}>{s.date}</span> : null}
              </div>
              {s.reason ? (
                <div style={WV_WHY}>
                  <span style={WV_LABEL}>Why leave </span>{s.reason}
                </div>
              ) : null}
              {s.candidate && s.candidate.thesis ? (
                <div style={WV_WHY}>
                  <span style={WV_LABEL}>Why {s.switch_candidate} </span>{s.candidate.thesis}
                </div>
              ) : null}
              <div style={{ ...WV_WHY, color: 'var(--ink-3)',
                font: '600 11px "JetBrains Mono", monospace' }}>
                {typeof s.pnl_pct === 'number'
                  ? `${s.pnl_pct >= 0 ? '+' : ''}${Number(s.pnl_pct).toFixed(1)}% vs a `
                    + `${Number(s.stop_pct || 0).toFixed(1)}% stop` : null}
                {s.candidate && typeof s.candidate.conviction === 'number'
                  ? ` · conviction ${Math.round(s.candidate.conviction * 100)}%` : null}
              </div>
            </div>
          ))}
        </BVFold>
      )}

      {cands.length > 0 && (
        <BVFold title="Shelf ideas · underweight sectors" summary={cands.length}>
          <div style={WV_NOTE}>
            Research candidates, not tied to any holding — and not personal advice.
          </div>
          {cands.map((c, i) => (
            <div key={'c' + i} style={{ padding: '11px 0', borderTop: '1px solid var(--border)' }}>
              <b style={{ color: 'var(--ink-1)' }}>{c.symbol}</b>
              <span style={{ color: 'var(--ink-3)', fontSize: 11.5 }}> · {c.sector}</span>
              {typeof c.conviction === 'number' ? (
                <span style={{ float: 'right', font: '700 12px "JetBrains Mono", monospace',
                  color: 'var(--ink-2)' }}>{Math.round(c.conviction * 100)}%</span>
              ) : null}
              {c.thesis ? <div style={WV_WHY}>{c.thesis}</div> : null}
              {c.entry_low && c.entry_high ? (
                <div style={{ ...WV_WHY, color: 'var(--ink-3)',
                  font: '600 11px "JetBrains Mono", monospace' }}>
                  entry {Number(c.entry_low).toFixed(0)}–{Number(c.entry_high).toFixed(0)}
                  {c.invalidation_level
                    ? ` · invalid below ${Number(c.invalidation_level).toFixed(0)}` : null}
                </div>
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
