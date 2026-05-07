// Logs — real-time server log viewer via SSE + managed ticker editor
const { useState: useLgState, useEffect: useLgEffect, useRef: useLgRef, useCallback: useLgCB } = React;

const LEVEL_ORDER  = { DEBUG: 0, INFO: 1, WARNING: 2, ERROR: 3, CRITICAL: 4 };
const LEVEL_COLORS = {
  DEBUG:    { bg: 'transparent',  text: '#94a3b8' },
  INFO:     { bg: 'transparent',  text: '#e2e8f0' },
  WARNING:  { bg: 'transparent',  text: '#fbbf24' },
  ERROR:    { bg: 'transparent',  text: '#f87171' },
  CRITICAL: { bg: '#7f1d1d',      text: '#fca5a5' },
};
const SECTORS = ['automobile', 'banking_bfsi', 'it_sector', 'renewable_energy'];

// ---------------------------------------------------------------------------
// LogsPage
// ---------------------------------------------------------------------------
function LogsPage({ onNav }) {
  const [entries,    setEntries]    = useLgState([]);
  const [filter,     setFilter]     = useLgState('INFO');
  const [search,     setSearch]     = useLgState('');
  const [autoScroll, setAutoScroll] = useLgState(true);
  const [connStatus, setConnStatus] = useLgState('connecting'); // connecting|live|error|closed
  const [tab,        setTab]        = useLgState('logs');       // logs | tickers
  const bottomRef  = useLgRef(null);
  const sourceRef  = useLgRef(null);
  const MAX_ENTRIES = 800;

  // ── SSE connection ────────────────────────────────────────────────────────
  useLgEffect(() => {
    let reconnectTimer = null;

    function connect() {
      setConnStatus('connecting');
      const src = new EventSource(`/ui/logs/stream?level=DEBUG`);
      sourceRef.current = src;

      src.onopen = () => setConnStatus('live');

      src.onmessage = (e) => {
        if (e.data.startsWith(':')) return; // keepalive comment
        try {
          const entry = JSON.parse(e.data);
          setEntries(prev => {
            const next = [...prev, entry];
            return next.length > MAX_ENTRIES ? next.slice(-MAX_ENTRIES) : next;
          });
        } catch {}
      };

      src.onerror = () => {
        src.close();
        setConnStatus('error');
        // Auto-reconnect after 5 s
        reconnectTimer = setTimeout(connect, 5000);
      };
    }

    connect();
    return () => {
      if (sourceRef.current) sourceRef.current.close();
      if (reconnectTimer) clearTimeout(reconnectTimer);
      setConnStatus('closed');
    };
  }, []);

  // ── Auto-scroll ──────────────────────────────────────────────────────────
  useLgEffect(() => {
    if (autoScroll && bottomRef.current) {
      bottomRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [entries, autoScroll]);

  // ── Filtered entries ─────────────────────────────────────────────────────
  const minOrd = LEVEL_ORDER[filter] ?? 1;
  const visible = entries.filter(e => {
    if ((LEVEL_ORDER[e.level] ?? 0) < minOrd) return false;
    if (search && !e.msg.toLowerCase().includes(search.toLowerCase()) &&
        !e.name.toLowerCase().includes(search.toLowerCase())) return false;
    return true;
  });

  const statusColor = { connecting: '#f59e0b', live: '#22c55e', error: '#ef4444', closed: '#94a3b8' };

  return (
    <div style={{ minHeight: '100vh', background: '#0f172a', color: '#e2e8f0', display: 'flex', flexDirection: 'column' }}>
      {/* Header */}
      <div style={{
        padding: '14px 20px', borderBottom: '1px solid #1e293b',
        display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap',
        background: '#0f172a',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <button onClick={() => onNav('home')} style={{
            background: 'transparent', border: 'none', cursor: 'pointer', color: '#64748b',
          }}>
            <Icon.ChevronL size={18}/>
          </button>
          <Icon.Layers size={18} c="#6366f1"/>
          <div>
            <div style={{ fontWeight: 700, fontSize: 15, fontFamily: 'monospace' }}>Server Logs</div>
            <div style={{ fontSize: 11, color: '#64748b' }}>Live stream · {entries.length} captured</div>
          </div>
        </div>

        {/* Tab switcher */}
        <div style={{ display: 'flex', gap: 4 }}>
          {['logs', 'tickers'].map(t => (
            <button key={t} onClick={() => setTab(t)} style={{
              padding: '6px 14px', borderRadius: 6, border: '1px solid #1e293b', cursor: 'pointer',
              background: tab === t ? '#1e293b' : 'transparent',
              color: tab === t ? '#e2e8f0' : '#64748b',
              fontSize: 12, fontWeight: tab === t ? 700 : 400, textTransform: 'capitalize',
            }}>{t === 'tickers' ? 'Manage Tickers' : 'Logs'}</button>
          ))}
        </div>

        {/* Log controls */}
        {tab === 'logs' && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
            {/* Connection status */}
            <span style={{ display: 'flex', alignItems: 'center', gap: 5, fontSize: 11 }}>
              <span style={{ width: 7, height: 7, borderRadius: '50%', background: statusColor[connStatus] }}/>
              <span style={{ color: statusColor[connStatus], fontFamily: 'monospace' }}>{connStatus}</span>
            </span>

            {/* Level filter */}
            <select value={filter} onChange={e => setFilter(e.target.value)} style={{
              background: '#1e293b', border: '1px solid #334155', color: '#e2e8f0',
              padding: '4px 8px', borderRadius: 6, fontSize: 12, cursor: 'pointer', fontFamily: 'monospace',
            }}>
              {['DEBUG','INFO','WARNING','ERROR'].map(l => (
                <option key={l} value={l}>{l}</option>
              ))}
            </select>

            {/* Search */}
            <input
              value={search}
              onChange={e => setSearch(e.target.value)}
              placeholder="Filter..."
              style={{
                background: '#1e293b', border: '1px solid #334155', color: '#e2e8f0',
                padding: '4px 10px', borderRadius: 6, fontSize: 12, width: 140, fontFamily: 'monospace',
              }}
            />

            {/* Auto-scroll toggle */}
            <button onClick={() => setAutoScroll(a => !a)} style={{
              padding: '4px 10px', borderRadius: 6, border: '1px solid #334155', cursor: 'pointer',
              background: autoScroll ? '#1e40af' : '#1e293b',
              color: autoScroll ? '#93c5fd' : '#64748b', fontSize: 11, fontFamily: 'monospace',
            }}>
              {autoScroll ? '⬇ Auto' : 'Manual'}
            </button>

            {/* Clear */}
            <button onClick={() => setEntries([])} style={{
              padding: '4px 10px', borderRadius: 6, border: '1px solid #334155', cursor: 'pointer',
              background: 'transparent', color: '#64748b', fontSize: 11, fontFamily: 'monospace',
            }}>Clear</button>
          </div>
        )}
      </div>

      {/* Content */}
      {tab === 'logs' ? (
        <LogTerminal visible={visible} bottomRef={bottomRef} search={search}/>
      ) : (
        <TickerManager/>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Log terminal pane
// ---------------------------------------------------------------------------
function LogTerminal({ visible, bottomRef, search }) {
  return (
    <div style={{
      flex: 1, overflowY: 'auto', padding: '8px 0',
      fontFamily: 'monospace', fontSize: 12, lineHeight: 1.6,
      background: '#0f172a',
    }}>
      {visible.length === 0 && (
        <div style={{ padding: '40px 24px', color: '#334155', textAlign: 'center' }}>
          No log entries match current filter. Waiting for server activity…
        </div>
      )}
      {visible.map((e, i) => {
        const col = LEVEL_COLORS[e.level] || LEVEL_COLORS.INFO;
        const isErr = e.level === 'ERROR' || e.level === 'CRITICAL';
        return (
          <div key={i} style={{
            display: 'flex', gap: 0, padding: '1px 16px',
            background: isErr ? 'rgba(239,68,68,0.05)' : col.bg,
            borderLeft: isErr ? '2px solid #ef4444' : '2px solid transparent',
          }}>
            <span style={{ color: '#475569', minWidth: 58, flexShrink: 0 }}>{e.ts}</span>
            <span style={{
              minWidth: 60, flexShrink: 0, fontWeight: 700,
              color: col.text,
            }}>{e.level}</span>
            <span style={{ color: '#6366f1', minWidth: 110, flexShrink: 0 }}>
              [{e.name}]
            </span>
            <span style={{ color: col.text, wordBreak: 'break-word', flex: 1 }}>{e.msg}</span>
          </div>
        );
      })}
      <div ref={bottomRef}/>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Managed ticker editor
// ---------------------------------------------------------------------------
function TickerManager() {
  const [tickers,  setTickers]  = useLgState([]);
  const [loading,  setLoading]  = useLgState(true);
  const [newSym,   setNewSym]   = useLgState('');
  const [newName,  setNewName]  = useLgState('');
  const [newSec,   setNewSec]   = useLgState('automobile');
  const [status,   setStatus]   = useLgState(null);

  useLgEffect(() => {
    fetch('/ui/tickers/managed')
      .then(r => r.json())
      .then(d => { setTickers(d.tickers || []); setLoading(false); })
      .catch(() => setLoading(false));
  }, []);

  const flash = (msg, ok = true) => {
    setStatus({ msg, ok });
    setTimeout(() => setStatus(null), 3000);
  };

  const handleToggle = async (sym) => {
    const res = await fetch(`/ui/tickers/managed/${sym}/toggle`, { method: 'PATCH' });
    const d = await res.json();
    setTickers(d.tickers || []);
  };

  const handleRemove = async (sym) => {
    const res = await fetch(`/ui/tickers/managed/${sym}`, { method: 'DELETE' });
    const d = await res.json();
    setTickers(d.tickers || []);
    flash(`${sym} removed`);
  };

  const handleAdd = async () => {
    const sym = newSym.trim().toUpperCase();
    if (!sym) return;
    const res = await fetch(`/ui/tickers/managed/${sym}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ sym, name: newName.trim(), sector: newSec, enabled: true }),
    });
    const d = await res.json();
    if (!res.ok) { flash(d.detail || 'Add failed', false); return; }
    setTickers(d.tickers || []);
    setNewSym(''); setNewName('');
    flash(`${sym} added to managed list`);
  };

  const SECTOR_LABELS = {
    automobile:      'Automobile',
    banking_bfsi:    'Banking BFSI',
    it_sector:       'IT Sector',
    renewable_energy:'Renewable Energy',
  };

  return (
    <div style={{ flex: 1, overflowY: 'auto', padding: '20px 24px', maxWidth: 700, margin: '0 auto', width: '100%' }}>
      <div style={{ marginBottom: 16 }}>
        <div style={{ fontWeight: 700, fontSize: 14, color: '#e2e8f0', marginBottom: 4 }}>Managed Tickers</div>
        <div style={{ fontSize: 12, color: '#64748b' }}>
          These tickers are tracked by the RL daily review &amp; monthly forecast scheduler.
          Enabled tickers get a new prediction envelope each month and a daily accuracy review.
        </div>
      </div>

      {status && (
        <div style={{
          padding: '8px 14px', borderRadius: 8, marginBottom: 12, fontSize: 12,
          background: status.ok ? '#064e3b' : '#7f1d1d',
          color: status.ok ? '#6ee7b7' : '#fca5a5',
          border: `1px solid ${status.ok ? '#065f46' : '#991b1b'}`,
        }}>{status.msg}</div>
      )}

      {loading ? (
        <div style={{ color: '#64748b', fontSize: 13 }}>Loading…</div>
      ) : (
        <>
          {/* Ticker list */}
          <div style={{ marginBottom: 20 }}>
            {tickers.map(t => (
              <div key={t.sym} style={{
                display: 'flex', alignItems: 'center', gap: 10, padding: '10px 14px',
                borderRadius: 8, marginBottom: 6,
                background: t.enabled ? '#0f2040' : '#1e1e2e',
                border: `1px solid ${t.enabled ? '#1e3a5f' : '#2d2d3d'}`,
              }}>
                {/* Toggle */}
                <button onClick={() => handleToggle(t.sym)} title={t.enabled ? 'Disable' : 'Enable'} style={{
                  width: 32, height: 18, borderRadius: 999, border: 'none', cursor: 'pointer',
                  background: t.enabled ? '#22c55e' : '#334155', position: 'relative', flexShrink: 0,
                }}>
                  <span style={{
                    position: 'absolute', top: 2, left: t.enabled ? 16 : 2,
                    width: 14, height: 14, borderRadius: '50%', background: '#fff',
                    transition: 'left .15s',
                  }}/>
                </button>

                {/* Info */}
                <div style={{ flex: 1 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <span style={{ fontWeight: 700, fontSize: 13, color: '#e2e8f0', fontFamily: 'monospace' }}>{t.sym}</span>
                    <span style={{
                      fontSize: 10, padding: '1px 6px', borderRadius: 4,
                      background: '#1e293b', color: '#94a3b8',
                    }}>{SECTOR_LABELS[t.sector] || t.sector}</span>
                    {!t.enabled && <span style={{ fontSize: 10, color: '#475569' }}>disabled</span>}
                  </div>
                  <div style={{ fontSize: 11, color: '#64748b', marginTop: 1 }}>{t.name || t.sym}</div>
                </div>

                {/* Remove */}
                <button onClick={() => handleRemove(t.sym)} style={{
                  background: 'transparent', border: '1px solid #334155', borderRadius: 6,
                  padding: '3px 8px', cursor: 'pointer', color: '#ef4444', fontSize: 11,
                }}>Remove</button>
              </div>
            ))}
          </div>

          {/* Add new ticker */}
          <div style={{
            padding: '14px 16px', borderRadius: 10, background: '#0f172a',
            border: '1px solid #1e293b',
          }}>
            <div style={{ fontWeight: 600, fontSize: 13, color: '#94a3b8', marginBottom: 10 }}>Add ticker</div>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              <input
                value={newSym}
                onChange={e => setNewSym(e.target.value.toUpperCase())}
                placeholder="NSE symbol e.g. HDFCBANK"
                onKeyDown={e => e.key === 'Enter' && handleAdd()}
                style={{
                  background: '#1e293b', border: '1px solid #334155', color: '#e2e8f0',
                  padding: '7px 12px', borderRadius: 7, fontSize: 13, width: 180,
                  fontFamily: 'monospace',
                }}
              />
              <input
                value={newName}
                onChange={e => setNewName(e.target.value)}
                placeholder="Display name (optional)"
                style={{
                  background: '#1e293b', border: '1px solid #334155', color: '#e2e8f0',
                  padding: '7px 12px', borderRadius: 7, fontSize: 13, flex: 1, minWidth: 160,
                }}
              />
              <select value={newSec} onChange={e => setNewSec(e.target.value)} style={{
                background: '#1e293b', border: '1px solid #334155', color: '#e2e8f0',
                padding: '7px 12px', borderRadius: 7, fontSize: 13, cursor: 'pointer',
              }}>
                {SECTORS.map(s => (
                  <option key={s} value={s}>{SECTOR_LABELS[s] || s}</option>
                ))}
              </select>
              <button onClick={handleAdd} style={{
                padding: '7px 18px', borderRadius: 7, border: 'none', cursor: 'pointer',
                background: '#6366f1', color: '#fff', fontSize: 13, fontWeight: 700,
              }}>Add</button>
            </div>
            <div style={{ fontSize: 11, color: '#475569', marginTop: 8 }}>
              Once added, this ticker is picked up by the next scheduled RL job (4:30 PM IST weekdays)
              or the next monthly forecast (1st of month). No restart needed.
            </div>
          </div>
        </>
      )}
    </div>
  );
}

window.LogsPage = LogsPage;
