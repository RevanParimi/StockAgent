/* Inbox — notification landing screen. Each tab fetches the latest content of
 * one notification type from its structured JSON endpoint and renders it with
 * a native view component (BriefView, DigestView, WeeklyView, or the inline
 * alerts list) — the same card/fold vocabulary throughout, no ASCII. The
 * `?format=text` variants of these endpoints still exist and are still used
 * by push notifications and email; this screen no longer requests them. */
const { useState: useStateInbox, useEffect: useEffectInbox } = React;

/* `render` picks the view component for the dispatch below — data-driven, not
 * a parallel switch on `key`, so adding/renaming a tab only means one line. */
const INBOX_TABS = [
  { key: 'brief',  label: 'Brief',  url: '/delivery/brief/latest',    render: 'brief'  },
  { key: 'digest', label: 'Digest', url: '/portfolio/digest/latest',  render: 'digest' },
  { key: 'weekly', label: 'Weekly', url: '/delivery/weekly/latest',   render: 'weekly' },
  { key: 'alerts', label: 'Alerts', url: '/delivery/alerts?limit=20', render: 'alerts' },
];

const INBOX_EMPTY = {
  brief:  'No morning brief yet — it builds at 08:50 IST on trading days.',
  digest: 'No EOD digest yet — the advisor runs after 16:30 IST on trading days.',
  weekly: 'No weekly review yet — it builds on Sunday evenings.',
  alerts: 'No alerts recorded yet.',
};

const SEV_COLOR = { critical: '#dc2626', warning: '#d97706', info: 'var(--ink-3)' };

function InboxPage({ onNav, tab, setTab }) {
  const active = INBOX_TABS.some(t => t.key === tab) ? tab : 'brief';
  const activeSpec = INBOX_TABS.find(t => t.key === active) || INBOX_TABS[0];
  const [state, setState] = useStateInbox({ status: 'loading' });
  const [nonce, setNonce] = useStateInbox(0);          // retry trigger

  useEffectInbox(() => {
    let alive = true;
    setState({ status: 'loading' });
    fetch(activeSpec.url)
      .then(async (r) => {
        if (r.status === 404) return { status: 'empty' };
        if (!r.ok) throw new Error('HTTP ' + r.status);
        return { status: 'ok', data: await r.json() };
      })
      .catch((e) => ({ status: 'error', message: String((e && e.message) || e) }))
      .then((s) => { if (alive) setState(s); });
    return () => { alive = false; };
  }, [active, nonce]);

  const card = {
    background: 'var(--bg-surface)', border: '1px solid var(--border)',
    borderRadius: 16, padding: '18px 16px',
  };

  const renderAlerts = (data) => {
    const alerts = (data && data.alerts) || [];
    if (!alerts.length) return <div style={{ color: 'var(--ink-3)' }}>{INBOX_EMPTY.alerts}</div>;
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        {alerts.map((a, i) => (
          <div key={i} style={card}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
              <span style={{ fontSize: 11, fontWeight: 800, textTransform: 'uppercase',
                color: SEV_COLOR[a.severity] || 'var(--ink-3)' }}>{a.severity || 'info'}</span>
              {a.symbol ? <span style={{ fontSize: 12, fontWeight: 700,
                color: 'var(--ink-1)' }}>{a.symbol}</span> : null}
              <span style={{ marginLeft: 'auto', fontSize: 11, color: 'var(--ink-3)' }}>{a.date}</span>
            </div>
            <div style={{ fontSize: 13, color: 'var(--ink-2)' }}>{a.message}</div>
          </div>
        ))}
      </div>
    );
  };

  return (
    <div style={{ minHeight: '100vh', background: 'var(--bg-base)', padding: '18px 16px 90px' }}>
      <div style={{ maxWidth: 640, margin: '0 auto' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 18 }}>
          <button onClick={() => onNav?.('home')} style={{ width: 36, height: 36, borderRadius: 10,
            border: '1px solid var(--border)', background: 'var(--bg-surface)',
            display: 'grid', placeItems: 'center', cursor: 'pointer' }}>
            <Icon.ChevronL size={16}/>
          </button>
          <div style={{ fontSize: 20, fontWeight: 800, color: 'var(--ink-1)' }}>Inbox</div>
        </div>

        <div style={{ display: 'flex', gap: 6, marginBottom: 16 }}>
          {INBOX_TABS.map(t => (
            <button key={t.key} onClick={() => setTab(t.key)} style={{
              flex: 1, padding: '9px 0', borderRadius: 999, fontSize: 12, fontWeight: 700,
              border: '1px solid var(--border)', cursor: 'pointer',
              background: active === t.key ? 'var(--bg-tinted)' : 'transparent',
              color: active === t.key ? 'var(--cyan)' : 'var(--ink-2)',
            }}>{t.label}</button>
          ))}
        </div>

        {state.status === 'loading' && <div style={{ color: 'var(--ink-3)' }}>Loading…</div>}
        {state.status === 'empty'   && <div style={{ ...card, color: 'var(--ink-3)' }}>{INBOX_EMPTY[active]}</div>}
        {state.status === 'error'   && (
          <div style={{ ...card, color: 'var(--ink-2)' }}>
            Couldn't load this — {state.message}.
            <button onClick={() => setNonce(n => n + 1)} style={{ marginLeft: 10, padding: '6px 14px',
              borderRadius: 999, border: '1px solid var(--border)', background: 'var(--bg-tinted)',
              color: 'var(--cyan)', fontSize: 12, fontWeight: 700, cursor: 'pointer' }}>Retry</button>
          </div>
        )}
        {state.status === 'ok' && (
          activeSpec.render === 'alerts' ? renderAlerts(state.data)
          : activeSpec.render === 'brief'  ? <BriefView  data={state.data} onNav={onNav}/>
          : activeSpec.render === 'digest' ? <DigestView data={state.data}/>
          : activeSpec.render === 'weekly' ? <WeeklyView data={state.data}/>
          : null
        )}
      </div>
    </div>
  );
}

window.InboxPage = InboxPage;
