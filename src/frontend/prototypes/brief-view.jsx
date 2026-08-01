/* brief-view.jsx — native Brief renderer (spec 2026-07-31 §3.3).
 *
 * Priority feed: hero + "Needs attention" open; every other section folded
 * behind a tap with a count in the header. Renders from the STRUCTURED dict
 * (GET /delivery/brief/latest), never from ?format=text — the ASCII bars and
 * bullets that used to leak into the UI were text-renderer artifacts.
 *
 * Plain-English verdict/regime strings arrive pre-translated from the server
 * (enrich_brief_for_api); never translate enums here.
 */
const { useState: useStateBV } = React;

function bvINR(v) {
  if (typeof v !== 'number' || !isFinite(v)) return '—';
  return '₹' + Math.round(v).toLocaleString('en-IN');
}

function bvLongDate(iso) {
  const d = new Date(String(iso) + 'T00:00:00');
  if (isNaN(d.getTime())) return String(iso || '');
  return d.toLocaleDateString('en-IN',
    { weekday: 'long', day: '2-digit', month: 'long', year: 'numeric' });
}

function bvShortDate(iso) {
  const d = new Date(String(iso) + 'T00:00:00');
  if (isNaN(d.getTime())) return String(iso || '');
  return d.toLocaleDateString('en-IN', { weekday: 'short', day: '2-digit', month: 'short' });
}

const BV_CARD = {
  background: 'var(--bg-surface)', border: '1px solid var(--border)',
  borderRadius: 14, marginBottom: 10,
};
const BV_LABEL = {
  font: '700 10px Inter, sans-serif', letterSpacing: '.13em',
  textTransform: 'uppercase', color: 'var(--cyan)', padding: '13px 14px 0',
};
const BV_ROW = { padding: '9px 0', borderTop: '1px solid var(--border)' };
const BV_WHY = { color: 'var(--ink-3)', fontSize: 12, marginTop: 3, lineHeight: 1.45 };

/* Verdict → chip colour. Keyed on the RAW enum (stable); the label shown is
 * always verdict_plain from the server. */
const BV_CHIP = {
  EXIT:  { background: '#fee2e2', color: '#b91c1c' },
  TRIM:  { background: '#fef3c7', color: '#b45309' },
  SWITCH:{ background: '#fef3c7', color: '#b45309' },
  ADD:   { background: '#dcfce7', color: '#15803d' },
  BUY:   { background: '#dcfce7', color: '#15803d' },
  HOLD:  { background: '#f1f5f9', color: '#475569' },
};

function BVChip({ verdict, label }) {
  const s = BV_CHIP[verdict] || { background: 'var(--bg-tinted)', color: 'var(--ink-2)' };
  return <span style={{
    display: 'inline-block', font: '700 10px Inter, sans-serif', padding: '2px 7px',
    borderRadius: 999, marginLeft: 6, verticalAlign: 1, ...s,
  }}>{label || verdict}</span>;
}

/* Collapsible section. `summary` shows in the collapsed header (a count, or the
 * regime word) so the fold is informative before you open it. */
function BVFold({ title, summary, children }) {
  const [open, setOpen] = useStateBV(false);
  return (
    <div style={BV_CARD}>
      <button onClick={() => setOpen(o => !o)} aria-expanded={open} style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        width: '100%', padding: '13px 14px', border: 'none', background: 'transparent',
        cursor: 'pointer', textAlign: 'left',
      }}>
        <span style={{ font: '700 12.5px Inter, sans-serif', color: 'var(--ink-1)' }}>{title}</span>
        <span style={{ font: '600 11px Inter, sans-serif', color: 'var(--ink-3)' }}>
          {summary} {open ? '⌃' : '⌄'}
        </span>
      </button>
      {open && <div style={{ padding: '0 14px 13px', fontSize: 12.5, color: 'var(--ink-2)' }}>
        {children}
      </div>}
    </div>
  );
}

function BVAttentionRow({ flag, onNav }) {
  return (
    <div role="button" tabIndex={0}
      onClick={() => onNav && onNav('portfolio')}
      onKeyDown={e => { if (e.key === 'Enter' && onNav) onNav('portfolio'); }}
      style={{ ...BV_ROW, cursor: onNav ? 'pointer' : 'default' }}>
      <span style={{ fontWeight: 800, color: 'var(--ink-1)', fontSize: 13 }}>{flag.symbol}</span>
      <BVChip verdict={flag.verdict} label={flag.verdict_plain}/>
      {flag.reason ? <div style={BV_WHY}>{flag.reason}
        {onNav ? <span style={{ color: 'var(--cyan)', fontWeight: 700 }}> ›</span> : null}</div> : null}
    </div>
  );
}

function BriefView({ data, onNav }) {
  const d = data || {};
  const p = d.portfolio;
  const flags = d.advisor_flags || [];
  const overnight = d.overnight || [];
  const earnings = d.earnings_soon || [];
  const ideas = d.discovery_adds || [];
  const ipos = d.ipo_watch || [];
  const lockin = d.lockin_flags || [];
  const regime = d.regime;
  const pnl = (p && typeof p.total_pnl_pct === 'number') ? p.total_pnl_pct : null;

  return (
    <div>
      {/* ── Hero: date, headline, portfolio ── */}
      <div style={BV_CARD}>
        <div style={{ padding: '16px 14px' }}>
          <div style={{ font: '700 10px Inter, sans-serif', letterSpacing: '.1em',
            textTransform: 'uppercase', color: 'var(--ink-3)', marginBottom: 8 }}>
            {bvLongDate(d.date)}
          </div>
          {d.headline ? <div style={{ fontSize: 14, lineHeight: 1.5, color: 'var(--ink-1)' }}>
            {d.headline}
          </div> : null}
          {p ? (
            <div style={{ display: 'flex', gap: 18, marginTop: 14, paddingTop: 12,
              borderTop: '1px solid var(--border)', flexWrap: 'wrap' }}>
              <div>
                <div style={{ font: '800 19px/1 Inter, sans-serif', color: 'var(--ink-1)' }}>
                  {bvINR(p.portfolio_value)}
                </div>
                <div style={BV_WHY}>portfolio</div>
              </div>
              {pnl !== null ? (
                <div>
                  <div style={{ font: '800 19px/1 Inter, sans-serif',
                    color: pnl >= 0 ? '#15803d' : '#b91c1c' }}>
                    {pnl >= 0 ? '▲' : '▼'} {Math.abs(pnl).toFixed(1)}%
                  </div>
                  <div style={BV_WHY}>since inception</div>
                </div>
              ) : null}
            </div>
          ) : null}
        </div>
      </div>

      {/* ── Needs attention — open, accented ── */}
      {flags.length > 0 && (
        <div style={{ ...BV_CARD, borderLeft: '3px solid #f59e0b' }}>
          <div style={{ ...BV_LABEL, color: '#b45309' }}>Needs attention · {flags.length}</div>
          <div style={{ padding: '8px 14px 13px' }}>
            {flags.map((f, i) => <BVAttentionRow key={i} flag={f} onNav={onNav}/>)}
          </div>
        </div>
      )}

      {/* ── Folded sections — each hidden entirely when empty ── */}
      {overnight.length > 0 && (
        <BVFold title="Overnight news" summary={overnight.length}>
          {overnight.map((o, i) => (
            <div key={i} style={BV_ROW}>
              {o.headline}
              {o.note ? <div style={BV_WHY}><b>Why it matters:</b> {o.note}</div> : null}
            </div>
          ))}
        </BVFold>
      )}

      {earnings.length > 0 && (
        <BVFold title="Earnings this week" summary={earnings.length}>
          {earnings.map((e, i) => (
            <div key={i} style={BV_ROW}>
              <b style={{ color: 'var(--ink-1)' }}>{e.symbol}</b> — {bvShortDate(e.date)}
              <div style={BV_WHY}>You hold this — {e.watch
                ? 'watch: ' + e.watch
                : 'results & guidance are the next catalyst.'}</div>
            </div>
          ))}
        </BVFold>
      )}

      {ideas.length > 0 && (
        <BVFold title="Ideas being researched" summary={ideas.length}>
          <div style={{ ...BV_WHY, marginBottom: 4 }}>
            The scanner flagged these; the tool rated each and is paper-testing the thesis.
            Its own view — not personal advice.
          </div>
          {ideas.map((a, i) => (
            <div key={i} style={BV_ROW}>
              <b style={{ color: 'var(--ink-1)' }}>{a.symbol}</b>
              {a.verdict ? <BVChip verdict={a.verdict} label={
                typeof a.conviction === 'number'
                  ? a.verdict + ' · ' + Math.round(a.conviction * 100) + '%'
                  : a.verdict
              }/> : null}
              {a.reason ? <div style={BV_WHY}>{a.reason}</div> : null}
            </div>
          ))}
        </BVFold>
      )}

      {regime && regime.label && (
        <BVFold title="Market conditions" summary={regime.label_plain || regime.label}>
          <div style={BV_ROW}>
            {regime.label_plain || regime.label}
            <span style={{ color: 'var(--ink-3)', fontSize: 11 }}> ({regime.label})</span>
            {regime.gloss ? <div style={BV_WHY}>{regime.gloss}</div> : null}
          </div>
        </BVFold>
      )}

      {ipos.length > 0 && (
        <BVFold title="IPOs open now" summary={ipos.length}>
          <div style={{ ...BV_WHY, marginBottom: 4 }}>The tool's research view — not advice.</div>
          {ipos.map((w, i) => (
            <div key={i} style={BV_ROW}>
              <b style={{ color: 'var(--ink-1)' }}>{w.symbol}</b>
              {w.company ? <span style={{ color: 'var(--ink-3)' }}> · {w.company}</span> : null}
            </div>
          ))}
        </BVFold>
      )}

      {lockin.length > 0 && (
        <BVFold title="Lock-in expiries" summary={lockin.length}>
          {lockin.map((lf, i) => (
            <div key={i} style={BV_ROW}>
              <b style={{ color: 'var(--ink-1)' }}>{lf.symbol}</b> {lf.kind} on {lf.expiry}
              <div style={BV_WHY}>Supply risk, not a signal.</div>
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

/* Export every helper Task 5 reuses. The codebase's convention is explicit
 * window assignment (icons.jsx, home.jsx) — do NOT rely on top-level const/
 * function declarations leaking across <script type="text/babel"> boundaries. */
window.BriefView = BriefView;
window.BVFold = BVFold;
window.BVChip = BVChip;
window.bvINR = bvINR;
window.bvLongDate = bvLongDate;
window.bvShortDate = bvShortDate;
