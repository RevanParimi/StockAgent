// Prompt Lab — edit agent prompts, auto-deploys nightly via scheduler
const { useState: usePLState, useEffect: usePLEffect } = React;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function tokenEstimate(text) {
  return Math.ceil((text || '').length / 4);
}

function TokenBadge({ text, label }) {
  const n = tokenEstimate(text);
  const color = n > 1500 ? '#ef4444' : n > 800 ? '#f59e0b' : '#22c55e';
  return (
    <span style={{ fontSize: 11, color, fontWeight: 600, fontFamily: 'var(--font-mono, monospace)' }}>
      ~{n} tokens {label && <span style={{ color: 'var(--ink-3)', fontWeight: 400 }}>· {label}</span>}
    </span>
  );
}

function SavePill({ status }) {
  if (!status) return null;
  const MAP = {
    saving:    { bg: '#1d4ed8', label: 'Saving…' },
    saved:     { bg: '#16a34a', label: '✓ Saved — active immediately' },
    deploying: { bg: '#7c3aed', label: 'Pushing to GitHub…' },
    deployed:  { bg: '#0891b2', label: 'Pushed — Railway rebuilding (~2 min)' },
  };
  const s = MAP[status] || { bg: '#dc2626', label: status.error || 'Error' };
  return (
    <span style={{
      padding: '3px 12px', borderRadius: 999, fontSize: 12, fontWeight: 600,
      background: s.bg, color: '#fff',
    }}>{s.label}</span>
  );
}

/** Format ISO → "today at HH:MM" or "tomorrow at midnight" */
function fmtNextDeploy(iso) {
  if (!iso) return 'midnight IST';
  try {
    const d = new Date(iso);
    const now = new Date();
    const diffH = (d - now) / 3600000;
    const timeStr = d.toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', timeZone: 'Asia/Kolkata' });
    if (diffH < 20) return `today at ${timeStr} IST`;
    return `tomorrow at ${timeStr} IST`;
  } catch {
    return 'midnight IST';
  }
}

// ---------------------------------------------------------------------------
// DeployScheduleCard — shows next run, pending count, last result
// ---------------------------------------------------------------------------
function DeployScheduleCard({ deployStatus, onOverride, overriding }) {
  if (!deployStatus) return null;

  const { pending_count, next_deploy_at, last_deploy, scheduler_configured } = deployStatus;
  const lastOk = last_deploy?.status === 'deployed';
  const lastTs = last_deploy?.deployed_at
    ? new Date(last_deploy.deployed_at).toLocaleString('en-IN', { timeZone: 'Asia/Kolkata', dateStyle: 'short', timeStyle: 'short' })
    : null;

  return (
    <div style={{
      padding: '12px 16px', borderRadius: 10, marginBottom: 20,
      background: 'var(--bg-tinted)', border: '1px solid var(--border)',
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: 8 }}>

        {/* Schedule info */}
        <div>
          <div style={{ fontWeight: 600, fontSize: 13, marginBottom: 4 }}>
            {!scheduler_configured ? (
              <span style={{ color: '#f59e0b' }}>⚠ GITHUB_TOKEN / GITHUB_REPO not set — deploy disabled</span>
            ) : pending_count > 0 ? (
              <span>
                <span style={{ color: 'var(--accent)' }}>{pending_count} change{pending_count > 1 ? 's' : ''}</span>
                <span style={{ color: 'var(--ink-2)' }}> → scheduled deploy {fmtNextDeploy(next_deploy_at)}</span>
              </span>
            ) : (
              <span style={{ color: 'var(--ink-3)' }}>No pending changes · next check {fmtNextDeploy(next_deploy_at)}</span>
            )}
          </div>

          {/* Pending file list */}
          {deployStatus.pending && deployStatus.pending.length > 0 && (
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, marginBottom: 6 }}>
              {deployStatus.pending.map(p => {
                const parts = p.split('/');
                const label = `${parts[3]}/${parts[5]?.replace('.py', '')}`;
                return (
                  <span key={p} style={{
                    fontSize: 11, padding: '2px 8px', borderRadius: 4,
                    background: 'var(--bg-surface)', border: '1px solid var(--border)',
                    color: 'var(--ink-2)', fontFamily: 'monospace',
                  }}>{label}</span>
                );
              })}
            </div>
          )}

          {/* Last deploy result */}
          {last_deploy && lastTs && (
            <div style={{ fontSize: 11, color: 'var(--ink-3)' }}>
              Last deploy {lastTs} —{' '}
              <span style={{ color: lastOk ? '#22c55e' : '#f87171' }}>
                {lastOk
                  ? `${last_deploy.deployed?.length || 0} file(s) pushed`
                  : last_deploy.errors?.[0] || last_deploy.reason || 'failed'}
              </span>
              {last_deploy.commit_sha && (
                <span style={{ marginLeft: 6, fontFamily: 'monospace', color: '#6366f1' }}>
                  {last_deploy.commit_sha.slice(0, 7)}
                </span>
              )}
              <span style={{ marginLeft: 6, color: '#64748b' }}>
                via {last_deploy.triggered_by || 'scheduler'}
              </span>
            </div>
          )}
        </div>

        {/* Deploy Now override button */}
        {scheduler_configured && pending_count > 0 && (
          <button
            onClick={onOverride}
            disabled={overriding}
            title="Push to GitHub now instead of waiting for midnight"
            style={{
              padding: '6px 14px', borderRadius: 7, border: '1px solid var(--border)',
              background: 'var(--bg-surface)', color: 'var(--ink-2)',
              fontSize: 12, fontWeight: 600, cursor: overriding ? 'default' : 'pointer',
              opacity: overriding ? 0.6 : 1, flexShrink: 0,
            }}
          >
            {overriding ? 'Pushing…' : 'Deploy now ↑'}
          </button>
        )}
      </div>

      {/* How it works explainer — collapsed hint */}
      <details style={{ marginTop: 8 }}>
        <summary style={{ fontSize: 11, color: 'var(--ink-3)', cursor: 'pointer', userSelect: 'none' }}>
          How this works
        </summary>
        <div style={{ fontSize: 11, color: 'var(--ink-3)', marginTop: 6, lineHeight: 1.6 }}>
          <strong>Save</strong> → writes .py file to container disk + patches live module in memory →
          <span style={{ color: '#22c55e' }}> new prompt active instantly</span> (next analysis uses it, no restart).<br/>
          <strong>Scheduled deploy (midnight IST)</strong> → batches all saved changes into one GitHub commit →
          Railway rebuilds → change survives future restarts.<br/>
          <strong>Deploy now</strong> → same as midnight but triggered immediately (use for urgent prod fixes).
        </div>
      </details>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main PromptLabPage
// ---------------------------------------------------------------------------
function PromptLabPage({ onNav }) {
  const [catalogue,      setCatalogue]      = usePLState([]);
  const [sector,         setSector]         = usePLState('');
  const [agent,          setAgent]          = usePLState('');
  const [systemPrompt,   setSystemPrompt]   = usePLState('');
  const [analysisPrompt, setAnalysisPrompt] = usePLState('');
  const [queriesText,    setQueriesText]    = usePLState('');
  const [loading,        setLoading]        = usePLState(false);
  const [saveStatus,     setSaveStatus]     = usePLState(null);
  const [deployStatus,   setDeployStatus]   = usePLState(null);
  const [overriding,     setOverriding]     = usePLState(false);

  const refreshDeployStatus = () =>
    fetch('/ui/prompts/status')
      .then(r => r.json())
      .then(setDeployStatus)
      .catch(() => {});

  // Load catalogue + deploy status on mount
  usePLEffect(() => {
    fetch('/ui/prompts/catalogue')
      .then(r => r.json())
      .then(d => {
        setCatalogue(d.catalogue || []);
        if (d.catalogue?.[0]) {
          const first = d.catalogue[0];
          setSector(first.sector);
          if (first.agents?.[0]) setAgent(first.agents[0].key);
        }
      })
      .catch(() => {});

    refreshDeployStatus();
  }, []);

  // Load prompt when sector/agent changes
  usePLEffect(() => {
    if (!sector || !agent) return;
    setLoading(true);
    fetch(`/ui/prompts/${sector}/${agent}`)
      .then(r => r.json())
      .then(d => {
        setSystemPrompt(d.system_prompt || '');
        setAnalysisPrompt(d.analysis_prompt || '');
        setQueriesText((d.context_search_queries || []).join('\n'));
        setLoading(false);
      })
      .catch(() => { setLoading(false); });
  }, [sector, agent]);

  const currentSectorMeta = catalogue.find(c => c.sector === sector);
  const agents = currentSectorMeta ? currentSectorMeta.agents : [];

  const handleSectorChange = (s) => {
    setSector(s);
    const meta = catalogue.find(c => c.sector === s);
    if (meta?.agents?.[0]) setAgent(meta.agents[0].key);
    setSaveStatus(null);
  };

  const handleSave = async () => {
    if (!sector || !agent) return;
    setSaveStatus('saving');
    const queries = queriesText.split('\n').map(q => q.trim()).filter(Boolean);
    try {
      const res = await fetch(`/ui/prompts/${sector}/${agent}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          system_prompt:          systemPrompt,
          analysis_prompt:        analysisPrompt,
          context_search_queries: queries,
        }),
      });
      const data = await res.json();
      if (!res.ok) {
        setSaveStatus({ error: data.detail || 'Save failed' });
        setTimeout(() => setSaveStatus(null), 4000);
      } else {
        setSaveStatus('saved');
        setTimeout(() => setSaveStatus(null), 3500);
        refreshDeployStatus();
      }
    } catch {
      setSaveStatus({ error: 'Network error' });
      setTimeout(() => setSaveStatus(null), 4000);
    }
  };

  const handleOverride = async () => {
    setOverriding(true);
    setSaveStatus('deploying');
    try {
      const res = await fetch('/ui/prompts/deploy', { method: 'POST' });
      const data = await res.json();
      setSaveStatus(res.ok ? 'deployed' : { error: data.detail || 'Deploy failed' });
      setTimeout(() => setSaveStatus(null), 6000);
      refreshDeployStatus();
    } catch {
      setSaveStatus({ error: 'Network error during deploy' });
      setTimeout(() => setSaveStatus(null), 5000);
    } finally {
      setOverriding(false);
    }
  };

  const totalTokens = tokenEstimate(systemPrompt) + tokenEstimate(analysisPrompt) + tokenEstimate(queriesText);

  return (
    <div className="proto-screen" style={{ minHeight: '100vh', background: 'var(--bg-base)', color: 'var(--ink-1)', paddingBottom: 100 }}>
      <TopNav active="prompt-lab" onNav={onNav} search="" setSearch={()=>{}}/>

      {/* Header — title + Save; back-nav now lives in TopNav */}
      <div style={{
        padding: '18px 24px', borderBottom: '1px solid var(--border)', background: 'var(--bg-surface)',
        display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <Icon.Settings size={20} c="var(--accent)"/>
          <div>
            <div style={{ fontWeight: 700, fontSize: 16 }}>Prompt Lab</div>
            <div style={{ fontSize: 12, color: 'var(--ink-3)' }}>
              Edit prompts · active instantly · auto-deploys to GitHub at midnight IST
            </div>
          </div>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <SavePill status={saveStatus}/>
          <button onClick={handleSave} disabled={loading} style={{
            padding: '8px 18px', borderRadius: 8, border: '1px solid var(--border)',
            background: 'var(--bg-tinted)', color: 'var(--ink-1)', fontSize: 13,
            fontWeight: 600, cursor: 'pointer',
          }}>Save</button>
        </div>
      </div>

      <div style={{ maxWidth: 900, margin: '0 auto', padding: '24px 16px' }}>

        {/* Selector row */}
        <div style={{ display: 'flex', gap: 12, marginBottom: 20, flexWrap: 'wrap', alignItems: 'flex-end' }}>
          <div>
            <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--ink-3)', marginBottom: 4, textTransform: 'uppercase', letterSpacing: 1 }}>Sector</div>
            <select value={sector} onChange={e => handleSectorChange(e.target.value)} style={{
              padding: '8px 12px', borderRadius: 8, border: '1px solid var(--border)',
              background: 'var(--bg-surface)', color: 'var(--ink-1)', fontSize: 14, cursor: 'pointer',
            }}>
              {catalogue.map(c => <option key={c.sector} value={c.sector}>{c.display}</option>)}
            </select>
          </div>
          <div>
            <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--ink-3)', marginBottom: 4, textTransform: 'uppercase', letterSpacing: 1 }}>Agent</div>
            <select value={agent} onChange={e => setAgent(e.target.value)} style={{
              padding: '8px 12px', borderRadius: 8, border: '1px solid var(--border)',
              background: 'var(--bg-surface)', color: 'var(--ink-1)', fontSize: 14, cursor: 'pointer',
            }}>
              {agents.map(a => <option key={a.key} value={a.key}>{a.display}</option>)}
            </select>
          </div>
          <div style={{ marginLeft: 'auto', textAlign: 'right' }}>
            <div style={{ fontSize: 11, color: 'var(--ink-3)', marginBottom: 2 }}>Total estimate</div>
            <span style={{ fontWeight: 700, fontSize: 15, color: totalTokens > 2500 ? '#ef4444' : 'var(--ink-1)' }}>
              ~{totalTokens.toLocaleString()} tokens
            </span>
          </div>
        </div>

        {/* Deploy schedule card */}
        <DeployScheduleCard
          deployStatus={deployStatus}
          onOverride={handleOverride}
          overriding={overriding}
        />

        {loading ? (
          <div style={{ textAlign: 'center', padding: '60px 0', color: 'var(--ink-3)' }}>Loading prompt…</div>
        ) : (
          <>
            <PromptSection
              label="System Prompt"
              hint="Defines the agent's role, expertise, and scoring rubric."
              value={systemPrompt}
              onChange={setSystemPrompt}
            />
            <PromptSection
              label="Analysis Prompt"
              hint="Per-request template with {ticker}, {company_name}, {context} injected."
              value={analysisPrompt}
              onChange={setAnalysisPrompt}
              rows={14}
            />
            <div style={{ marginBottom: 24 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 6 }}>
                <div>
                  <span style={{ fontWeight: 600, fontSize: 14 }}>Context Search Queries</span>
                  <div style={{ fontSize: 12, color: 'var(--ink-3)', marginTop: 2 }}>
                    One per line. Use {'{ticker}'}, {'{company_name}'}, {'{quarter}'}, {'{year}'} as placeholders.
                  </div>
                </div>
                <TokenBadge text={queriesText} label={`${queriesText.split('\n').filter(Boolean).length} queries`}/>
              </div>
              <textarea
                value={queriesText}
                onChange={e => setQueriesText(e.target.value)}
                rows={6}
                spellCheck={false}
                style={{
                  width: '100%', padding: '10px 12px', borderRadius: 8,
                  border: '1px solid var(--border)', background: 'var(--bg-surface)',
                  color: 'var(--ink-1)', fontSize: 13, fontFamily: 'var(--font-mono, monospace)',
                  resize: 'vertical', lineHeight: 1.6, boxSizing: 'border-box',
                }}
              />
            </div>
          </>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// PromptSection
// ---------------------------------------------------------------------------
function PromptSection({ label, hint, value, onChange, rows = 8 }) {
  const [expanded, setExpanded] = usePLState(true);
  return (
    <div style={{ marginBottom: 24 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 6 }}>
        <div>
          <button onClick={() => setExpanded(e => !e)} style={{
            fontWeight: 600, fontSize: 14, background: 'none', border: 'none',
            cursor: 'pointer', color: 'var(--ink-1)', padding: 0,
            display: 'flex', alignItems: 'center', gap: 5,
          }}>
            <Icon.ChevronD size={14} style={{ transform: expanded ? 'rotate(0deg)' : 'rotate(-90deg)', transition: 'transform .15s' }}/>
            {label}
          </button>
          {hint && <div style={{ fontSize: 12, color: 'var(--ink-3)', marginTop: 2, marginLeft: 19 }}>{hint}</div>}
        </div>
        <TokenBadge text={value}/>
      </div>
      {expanded && (
        <textarea
          value={value}
          onChange={e => onChange(e.target.value)}
          rows={rows}
          spellCheck={false}
          style={{
            width: '100%', padding: '10px 12px', borderRadius: 8,
            border: '1px solid var(--border)', background: 'var(--bg-surface)',
            color: 'var(--ink-1)', fontSize: 13, fontFamily: 'var(--font-mono, monospace)',
            resize: 'vertical', lineHeight: 1.6, boxSizing: 'border-box',
          }}
        />
      )}
    </div>
  );
}

window.PromptLabPage = PromptLabPage;
