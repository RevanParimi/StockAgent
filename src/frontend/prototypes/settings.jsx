/* settings.jsx — the real Settings screen (spec 2026-07-31 §5).
 *
 * Theme moves here out of TweaksPanel, which is prototyping scaffolding
 * (__activate_edit_mode host protocol) and unreachable for a real user.
 * Preferences persist to localStorage only — no schema change (spec D6).
 */
const { useState: useStateSet, useEffect: useEffectSet } = React;

const SET_CARD = {
  background: 'var(--bg-surface)', border: '1px solid var(--border)',
  borderRadius: 13, overflow: 'hidden', marginBottom: 4,
};
const SET_GROUP = {
  font: '700 10px Inter, sans-serif', letterSpacing: '.13em', textTransform: 'uppercase',
  color: 'var(--cyan)', margin: '18px 4px 7px',
};
const SET_ROW = {
  display: 'flex', alignItems: 'center', gap: 11, padding: '13px 14px',
  borderTop: '1px solid var(--border)',
};

function SetRow({ name, desc, children, danger, onClick, first }) {
  return (
    <div onClick={onClick}
      style={{ ...SET_ROW, borderTop: first ? 'none' : SET_ROW.borderTop,
        cursor: onClick ? 'pointer' : 'default' }}>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontWeight: 600, fontSize: 13,
          color: danger ? '#b91c1c' : 'var(--ink-1)' }}>{name}</div>
        {desc ? <div style={{ fontSize: 11.5, color: 'var(--ink-3)', marginTop: 2 }}>{desc}</div> : null}
      </div>
      {children}
    </div>
  );
}

function SetSegment({ value, options, onChange }) {
  return (
    <div style={{ display: 'flex', background: 'var(--bg-tinted)', borderRadius: 8,
      padding: 2, flexShrink: 0 }}>
      {options.map(o => (
        <button key={o.value} onClick={() => onChange(o.value)} style={{
          font: '700 11px Inter, sans-serif', padding: '5px 11px', borderRadius: 6,
          border: 'none', cursor: 'pointer',
          background: value === o.value ? 'var(--bg-surface)' : 'transparent',
          color: value === o.value ? 'var(--ink-1)' : 'var(--ink-3)',
        }}>{o.label}</button>
      ))}
    </div>
  );
}

/* Push toggle — same state machine as the old NotifRow in home.jsx. */
function SetPushToggle() {
  const [state, setState] = useStateSet('loading');
  useEffectSet(() => {
    let alive = true;
    if (window.saPush) window.saPush.status().then(s => { if (alive) setState(s); });
    else setState('unsupported');
    return () => { alive = false; };
  }, []);
  const LABEL = { on: 'On', off: 'Off', pending: '…', loading: '…',
                  denied: 'Blocked', unsupported: 'N/A', unconfigured: 'Off' };
  const locked = ['unsupported', 'denied', 'loading', 'pending'].indexOf(state) !== -1;
  const on = state === 'on';
  const toggle = async () => {
    if (!window.saPush || locked) return;
    setState('pending');
    setState(on ? await window.saPush.disable() : await window.saPush.enable());
  };
  return (
    <button onClick={toggle} disabled={locked} style={{
      font: '700 11px Inter, sans-serif', padding: '6px 13px', borderRadius: 999,
      border: '1px solid var(--border)', cursor: locked ? 'default' : 'pointer',
      background: on ? 'var(--bg-tinted)' : 'transparent',
      color: on ? 'var(--cyan)' : 'var(--ink-3)', flexShrink: 0,
    }}>{LABEL[state] || state}</button>
  );
}

function SettingsPage({ onNav, theme, setTheme }) {
  const [user, setUser] = useStateSet(null);
  useEffectSet(() => {
    let alive = true;
    fetch('/auth/me').then(r => r.ok ? r.json() : null)
      .then(d => { if (alive && d) setUser(d.user); }).catch(() => {});
    return () => { alive = false; };
  }, []);

  return (
    <div style={{ minHeight: '100vh', background: 'var(--bg-base)', padding: '18px 16px 90px' }}>
      <div style={{ maxWidth: 640, margin: '0 auto' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 4 }}>
          <button onClick={() => onNav && onNav('home')} style={{ width: 36, height: 36,
            borderRadius: 10, border: '1px solid var(--border)', background: 'var(--bg-surface)',
            display: 'grid', placeItems: 'center', cursor: 'pointer' }}>
            <Icon.ChevronL size={16}/>
          </button>
          <div style={{ fontSize: 20, fontWeight: 800, color: 'var(--ink-1)' }}>Settings</div>
        </div>

        <div style={SET_GROUP}>Account</div>
        <div style={SET_CARD}>
          <SetRow first name={(user && user.display_name) || 'Signed in'}
            desc={user ? user.email + ' · ' + user.role : 'loading…'}/>
          {user && user.role === 'owner' ? (
            <SetRow name="Invite a friend" desc="Create a code someone can sign up with"
              onClick={() => onNav && onNav('settings-invites')}>
              <span style={{ color: 'var(--ink-3)' }}>›</span>
            </SetRow>
          ) : null}
        </div>

        <div style={SET_GROUP}>Notifications</div>
        <div style={SET_CARD}>
          <SetRow first name="Push on this device"
            desc="Morning brief, EOD digest, weekly review and alerts">
            <SetPushToggle/>
          </SetRow>
        </div>
        <div style={{ fontSize: 11.5, color: 'var(--ink-3)', margin: '7px 4px 0' }}>
          Push is all-or-nothing today. Per-kind control needs a server-side preference —
          it's on the backlog.
        </div>

        <div style={SET_GROUP}>Appearance</div>
        <div style={SET_CARD}>
          <SetRow first name="Theme" desc="Applies across the app">
            <SetSegment value={theme} onChange={setTheme} options={[
              { value: 'light', label: 'Light' },
              { value: 'dark', label: 'Dark' },
            ]}/>
          </SetRow>
        </div>

        <div style={SET_GROUP}>Data &amp; privacy</div>
        <div style={SET_CARD}>
          <SetRow first danger name="Delete my account"
            desc="Erases your portfolio, chats and personal data. Cannot be undone."
            onClick={() => onNav && onNav('settings-delete')}>
            <span style={{ color: 'var(--ink-3)' }}>›</span>
          </SetRow>
        </div>

        <div style={SET_GROUP}>About</div>
        <div style={SET_CARD}>
          <SetRow first name="Version" ><span style={{ fontSize: 12,
            color: 'var(--ink-3)' }}>2.0.0</span></SetRow>
          <SetRow name="Research tool — never advice"
            desc="Information only. Not a SEBI-registered adviser."/>
        </div>
      </div>
    </div>
  );
}

window.SettingsPage = SettingsPage;
