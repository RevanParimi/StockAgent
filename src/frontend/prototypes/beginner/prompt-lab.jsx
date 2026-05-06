// Prompt Lab — read, edit, and deploy agent prompts via the backend API
const { useState: usePLState, useEffect: usePLEffect, useCallback: usePLCallback } = React;

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

function StatusPill({ status }) {
  if (!status) return null;
  const styles = {
    saving:  { bg: '#1d4ed8', text: 'Saving…' },
    saved:   { bg: '#16a34a', text: 'Saved to disk' },
    deploying: { bg: '#7c3aed', text: 'Pushing to GitHub…' },
    deployed:  { bg: '#0891b2', text: 'Deployed — Railway rebuilding…' },
    error:   { bg: '#dc2626', text: status.error || 'Error' },
  };
  const s = styles[status] || styles.error;
  return (
    <span style={{
      padding: '3px 10px', borderRadius: 999, fontSize: 12, fontWeight: 600,
      background: s.bg, color: '#fff',
    }}>{s.text || status.error}</span>
  );
}

// ---------------------------------------------------------------------------
// Main PromptLabPage component
// ---------------------------------------------------------------------------

function PromptLabPage({ onNav }) {
  const [catalogue, setCatalogue] = usePLState([]);
  const [sector,    setSector]    = usePLState('');
  const [agent,     setAgent]     = usePLState('');

  const [systemPrompt,   setSystemPrompt]   = usePLState('');
  const [analysisPrompt, setAnalysisPrompt] = usePLState('');
  const [queriesText,    setQueriesText]    = usePLState('');  // newline-separated

  const [loading,    setLoading]    = usePLState(false);
  const [saveStatus, setSaveStatus] = usePLState(null);
  const [deployResult, setDeployResult] = usePLState(null);
  const [pending,    setPending]    = usePLState([]);

  // Load catalogue once on mount
  usePLEffect(() => {
    fetch('/ui/prompts/catalogue')
      .then(r => r.json())
      .then(d => {
        setCatalogue(d.catalogue || []);
        if (d.catalogue && d.catalogue[0]) {
          const first = d.catalogue[0];
          setSector(first.sector);
          if (first.agents && first.agents[0]) setAgent(first.agents[0].key);
        }
      })
      .catch(() => setCatalogue([]));

    fetch('/ui/prompts/pending')
      .then(r => r.json())
      .then(d => setPending(d.pending || []))
      .catch(() => {});
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
      .catch(() => {
        setSystemPrompt('');
        setAnalysisPrompt('');
        setQueriesText('');
        setLoading(false);
      });
  }, [sector, agent]);

  const currentSectorMeta = catalogue.find(c => c.sector === sector);
  const agents = currentSectorMeta ? currentSectorMeta.agents : [];

  const handleSectorChange = (s) => {
    setSector(s);
    const meta = catalogue.find(c => c.sector === s);
    if (meta && meta.agents && meta.agents[0]) setAgent(meta.agents[0].key);
    setSaveStatus(null);
    setDeployResult(null);
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
          system_prompt: systemPrompt,
          analysis_prompt: analysisPrompt,
          context_search_queries: queries,
        }),
      });
      const data = await res.json();
      if (!res.ok) {
        setSaveStatus({ error: data.detail || 'Save failed' });
      } else {
        setSaveStatus('saved');
        setPending(data.pending || []);
        setTimeout(() => setSaveStatus(null), 3000);
      }
    } catch {
      setSaveStatus({ error: 'Network error' });
      setTimeout(() => setSaveStatus(null), 4000);
    }
  };

  const handleDeploy = async () => {
    setSaveStatus('deploying');
    setDeployResult(null);
    try {
      const res = await fetch('/ui/prompts/deploy', { method: 'POST' });
      const data = await res.json();
      if (!res.ok) {
        setSaveStatus({ error: data.detail || 'Deploy failed' });
        setDeployResult({ error: data.detail });
      } else {
        setSaveStatus('deployed');
        setDeployResult(data);
        setPending([]);
        setTimeout(() => setSaveStatus(null), 6000);
      }
    } catch {
      setSaveStatus({ error: 'Network error during deploy' });
      setTimeout(() => setSaveStatus(null), 5000);
    }
  };

  const totalTokens = tokenEstimate(systemPrompt) + tokenEstimate(analysisPrompt) + tokenEstimate(queriesText);

  return (
    <div style={{ minHeight: '100vh', background: 'var(--bg-base)', color: 'var(--ink-1)', paddingBottom: 100 }}>
      {/* Header */}
      <div style={{
        padding: '18px 24px', borderBottom: '1px solid var(--border)',
        background: 'var(--bg-surface)',
        display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <button onClick={() => onNav('home')} style={{
            background: 'transparent', border: 'none', cursor: 'pointer',
            color: 'var(--ink-3)', display: 'flex', alignItems: 'center',
          }}>
            <Icon.ChevronL size={18}/>
          </button>
          <Icon.Settings size={20} c="var(--accent)"/>
          <div>
            <div style={{ fontWeight: 700, fontSize: 16 }}>Prompt Lab</div>
            <div style={{ fontSize: 12, color: 'var(--ink-3)' }}>Edit agent prompts • Save to disk • Deploy to GitHub</div>
          </div>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <StatusPill status={saveStatus}/>
          <button onClick={handleSave} disabled={loading} style={{
            padding: '8px 18px', borderRadius: 8, border: '1px solid var(--border)',
            background: 'var(--bg-tinted)', color: 'var(--ink-1)', fontSize: 13, fontWeight: 600, cursor: 'pointer',
          }}>Save</button>
          <button onClick={handleDeploy} disabled={loading || pending.length === 0} style={{
            padding: '8px 18px', borderRadius: 8, border: 'none',
            background: pending.length > 0 ? 'var(--accent)' : 'var(--bg-tinted)',
            color: pending.length > 0 ? '#fff' : 'var(--ink-3)',
            fontSize: 13, fontWeight: 600, cursor: pending.length > 0 ? 'pointer' : 'default',
          }}>
            Deploy {pending.length > 0 ? `(${pending.length})` : ''}
          </button>
        </div>
      </div>

      <div style={{ maxWidth: 900, margin: '0 auto', padding: '24px 16px' }}>

        {/* Selector row */}
        <div style={{
          display: 'flex', gap: 12, marginBottom: 24, flexWrap: 'wrap', alignItems: 'flex-end',
        }}>
          <div>
            <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--ink-3)', marginBottom: 4, textTransform: 'uppercase', letterSpacing: 1 }}>Sector</div>
            <select value={sector} onChange={e => handleSectorChange(e.target.value)} style={{
              padding: '8px 12px', borderRadius: 8, border: '1px solid var(--border)',
              background: 'var(--bg-surface)', color: 'var(--ink-1)', fontSize: 14, cursor: 'pointer',
            }}>
              {catalogue.map(c => (
                <option key={c.sector} value={c.sector}>{c.display}</option>
              ))}
            </select>
          </div>
          <div>
            <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--ink-3)', marginBottom: 4, textTransform: 'uppercase', letterSpacing: 1 }}>Agent</div>
            <select value={agent} onChange={e => setAgent(e.target.value)} style={{
              padding: '8px 12px', borderRadius: 8, border: '1px solid var(--border)',
              background: 'var(--bg-surface)', color: 'var(--ink-1)', fontSize: 14, cursor: 'pointer',
            }}>
              {agents.map(a => (
                <option key={a.key} value={a.key}>{a.display}</option>
              ))}
            </select>
          </div>
          <div style={{ marginLeft: 'auto', textAlign: 'right' }}>
            <div style={{ fontSize: 11, color: 'var(--ink-3)', marginBottom: 2 }}>Total estimate</div>
            <span style={{ fontWeight: 700, fontSize: 15, color: totalTokens > 2500 ? '#ef4444' : 'var(--ink-1)' }}>
              ~{totalTokens.toLocaleString()} tokens
            </span>
          </div>
        </div>

        {loading && (
          <div style={{ textAlign: 'center', padding: '60px 0', color: 'var(--ink-3)' }}>
            Loading prompt…
          </div>
        )}

        {!loading && (
          <>
            {/* System Prompt */}
            <PromptSection
              label="System Prompt"
              hint="Defines the agent's role, expertise, and scoring rubric. Shorter = cheaper per call."
              value={systemPrompt}
              onChange={setSystemPrompt}
            />

            {/* Analysis Prompt */}
            <PromptSection
              label="Analysis Prompt"
              hint="The per-request template sent to the LLM with {ticker}, {company_name}, {context} injected."
              value={analysisPrompt}
              onChange={setAnalysisPrompt}
            />

            {/* Context Queries */}
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

            {/* Pending files */}
            {pending.length > 0 && (
              <div style={{
                padding: 14, borderRadius: 10, background: 'var(--bg-tinted)',
                border: '1px solid var(--border)', marginBottom: 20,
              }}>
                <div style={{ fontWeight: 600, fontSize: 13, marginBottom: 8 }}>
                  {pending.length} file{pending.length > 1 ? 's' : ''} pending deploy
                </div>
                {pending.map(p => (
                  <div key={p} style={{ fontSize: 12, color: 'var(--ink-3)', fontFamily: 'var(--font-mono, monospace)', marginBottom: 2 }}>
                    {p}
                  </div>
                ))}
                <div style={{ fontSize: 12, color: 'var(--ink-3)', marginTop: 8 }}>
                  Click <strong>Deploy</strong> to push to GitHub → Railway auto-deploys on push.
                </div>
              </div>
            )}

            {/* Deploy result */}
            {deployResult && !deployResult.error && (
              <DeployResultCard result={deployResult}/>
            )}
            {deployResult && deployResult.error && (
              <div style={{
                padding: 14, borderRadius: 10, background: '#fef2f2',
                border: '1px solid #fecaca', color: '#991b1b', fontSize: 13, marginBottom: 20,
              }}>
                Deploy failed: {deployResult.error}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// PromptSection — reusable labelled textarea with token count
// ---------------------------------------------------------------------------

function PromptSection({ label, hint, value, onChange }) {
  const [expanded, setExpanded] = usePLState(true);

  return (
    <div style={{ marginBottom: 24 }}>
      <div style={{
        display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 6,
      }}>
        <div>
          <button
            onClick={() => setExpanded(e => !e)}
            style={{
              fontWeight: 600, fontSize: 14, background: 'none', border: 'none',
              cursor: 'pointer', color: 'var(--ink-1)', padding: 0, display: 'flex', alignItems: 'center', gap: 5,
            }}
          >
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
          rows={label === 'System Prompt' ? 8 : 14}
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

// ---------------------------------------------------------------------------
// DeployResultCard
// ---------------------------------------------------------------------------

function DeployResultCard({ result }) {
  const ok = result.deployed && result.deployed.length > 0;
  return (
    <div style={{
      padding: 16, borderRadius: 10,
      background: ok ? '#f0fdf4' : '#fefce8',
      border: `1px solid ${ok ? '#bbf7d0' : '#fde68a'}`,
      marginBottom: 20,
    }}>
      <div style={{ fontWeight: 700, fontSize: 14, marginBottom: 8, color: ok ? '#166534' : '#78350f' }}>
        {ok ? `Deployed ${result.deployed.length} file${result.deployed.length > 1 ? 's' : ''} to GitHub` : 'Nothing deployed'}
      </div>
      {result.deployed.map(p => (
        <div key={p} style={{ fontSize: 12, color: '#166534', fontFamily: 'monospace', marginBottom: 2 }}>
          ✓ {p}
        </div>
      ))}
      {result.errors && result.errors.map(e => (
        <div key={e} style={{ fontSize: 12, color: '#991b1b', marginBottom: 2 }}>✗ {e}</div>
      ))}
      {result.commit_sha && result.commit_sha !== 'unknown' && (
        <div style={{ marginTop: 8, fontSize: 11, color: '#166534', fontFamily: 'monospace' }}>
          commit {result.commit_sha.slice(0, 7)}
        </div>
      )}
      <div style={{ fontSize: 11, color: 'var(--ink-3)', marginTop: 6 }}>
        Railway will detect the push and start a new deployment. Changes are live in ~2 min.
      </div>
    </div>
  );
}

window.PromptLabPage = PromptLabPage;
