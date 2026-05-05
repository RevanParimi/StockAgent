// Agents page — card grid with toggle on/off + drawer with sliders
const { useState: useStateAg, useEffect: useEffectAg } = React;

function AgentsPage({ onNav, openChat }) {
  const [agents, setAgents] = useStateAg(window.AGENTS);
  const [tasks, setTasks] = useStateAg(window.AGENT_TASKS);
  const [drawerKey, setDrawerKey] = useStateAg(null);
  const [search, setSearch] = useStateAg('');
  const [saveStatus, setSaveStatus] = useStateAg(null); // null | 'saving' | 'saved' | {error}

  const enabled = agents.filter(a => a.enabled);
  const totalWeight = enabled.reduce((s,a)=>s+a.weight, 0);
  const allTasks = Object.values(tasks).flat();
  const enabledTasks = allTasks.filter(t => t.enabled).length;

  // Persist all current weights to the backend
  const persistWeights = async (updatedAgents) => {
    setSaveStatus('saving');
    const weights = {};
    updatedAgents.forEach(a => { weights[a.key] = parseFloat(a.weight) || 0; });
    try {
      const res = await fetch('/ui/agents/weights', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ weights }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        setSaveStatus({ error: err.detail || 'Save failed' });
        setTimeout(() => setSaveStatus(null), 4000);
      } else {
        setSaveStatus('saved');
        setTimeout(() => setSaveStatus(null), 2000);
      }
    } catch {
      setSaveStatus({ error: 'Network error — weights saved locally only' });
      setTimeout(() => setSaveStatus(null), 4000);
    }
  };

  // Toggle: zero the weight when disabling, restore previous weight when enabling
  const toggle = (key) => {
    const updated = agents.map(a => {
      if (a.key !== key) return a;
      const nowEnabled = !a.enabled;
      return {
        ...a,
        enabled: nowEnabled,
        _prevWeight: a.enabled ? a.weight : a._prevWeight,
        weight: nowEnabled ? (a._prevWeight || 0.10) : 0,
      };
    });
    setAgents(updated);
    persistWeights(updated);
  };

  // Visual-only update during slider drag
  const setWeight = (key, w) =>
    setAgents(prev => prev.map(a => a.key===key ? { ...a, weight: w } : a));

  // Persist on slider release (mouseUp / touchEnd)
  const saveWeight = (key, w) => {
    const updated = agents.map(a => a.key===key ? { ...a, weight: parseFloat(w) } : a);
    setAgents(updated);
    persistWeights(updated);
  };

  const toggleTask = async (agentKey, taskKey) => {
    const updatedTasks = {
      ...tasks,
      [agentKey]: (tasks[agentKey] || []).map(t => t.key===taskKey ? { ...t, enabled: !t.enabled } : t),
    };
    setTasks(updatedTasks);
    // Persist flags to backend
    const flags = {};
    Object.entries(updatedTasks).forEach(([aKey, list]) => {
      flags[aKey] = {};
      list.forEach(t => { flags[aKey][t.key] = t.enabled; });
    });
    fetch('/ui/agents/tasks', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ flags }),
    }).catch(() => {}); // fire-and-forget; local state already updated
  };

  return (
    <div style={{ minHeight:'100vh', background:'var(--bg-base)' }}>
      <TopNav active="agents" onNav={onNav} search={search} setSearch={setSearch}/>

      <main style={{ maxWidth:1280, margin:'0 auto', padding:'24px 32px 96px' }}>
        {/* Header bar */}
        <div style={{ display:'flex', alignItems:'flex-end', justifyContent:'space-between', gap:24, marginBottom:24 }}>
          <div>
            <button onClick={()=>onNav?.('home')} style={{
              display:'inline-flex', alignItems:'center', gap:6, padding:'4px 10px 4px 6px',
              border:'1px solid var(--border)', borderRadius:8, background:'var(--bg-surface)',
              fontSize:11, fontWeight:600, color:'var(--ink-2)', marginBottom:12
            }}><Icon.ChevronL size={13}/> Back to home</button>
            <h1 style={{ fontSize:30, fontWeight:800, letterSpacing:'-0.02em', margin:'0 0 6px' }}>
              Your AI agents
            </h1>
            <p style={{ color:'var(--ink-2)', fontSize:14, margin:0, maxWidth:600 }}>
              Each agent is a specialist. Plug them in to add a viewpoint, unplug to silence one. Tap a card to tune its weight.
            </p>
          </div>

          <div style={{ display:'flex', gap:12, alignItems:'flex-start' }}>
            {/* Save status badge */}
            {saveStatus && (
              <div style={{
                padding:'8px 14px', borderRadius:8, fontSize:12, fontWeight:600,
                background: saveStatus==='saving' ? 'var(--bg-tinted)' :
                            saveStatus==='saved'  ? 'var(--buy-soft)' : 'var(--sell-soft)',
                color: saveStatus==='saving' ? 'var(--ink-3)' :
                       saveStatus==='saved'  ? 'var(--buy-strong)' : 'var(--sell-strong)',
                border: '1px solid',
                borderColor: saveStatus==='saving' ? 'var(--border)' :
                             saveStatus==='saved'  ? 'var(--buy)' : 'var(--sell)',
              }}>
                {saveStatus==='saving' ? '⟳ Saving…' :
                 saveStatus==='saved'  ? '✓ Weights saved' :
                 '⚠ ' + (saveStatus.error || 'Error')}
              </div>
            )}
            <Stat label="Plugged in"   value={enabled.length}    max={agents.length}/>
            <Stat label="Active tasks" value={enabledTasks}      max={allTasks.length} hint="Across all agents"/>
            <Stat label="Total weight" value={(totalWeight*100).toFixed(0)+'%'} hint="Should be ~100%"/>
          </div>
        </div>

        {/* Pipeline visual */}
        <Pipeline agents={enabled}/>

        {/* Agent grid */}
        <div style={{ marginTop:32 }}>
          <div style={{ display:'flex', alignItems:'center', justifyContent:'space-between', marginBottom:14 }}>
            <h2 style={{ fontSize:18, fontWeight:700, margin:0 }}>All agents</h2>
            <div style={{ fontSize:12, color:'var(--ink-3)' }}>Click any card to tune</div>
          </div>
          <div style={{ display:'grid', gridTemplateColumns:'repeat(3, 1fr)', gap:16 }}>
            {agents.map(a => (
              <AgentCard key={a.key} a={a} tasks={tasks[a.key]||[]}
                onToggle={()=>toggle(a.key)} onOpen={()=>setDrawerKey(a.key)}/>
            ))}
          </div>
        </div>
      </main>

      {drawerKey && (
        <AgentDrawer
          a={agents.find(x => x.key === drawerKey)}
          tasks={tasks[drawerKey] || []}
          onClose={()=>setDrawerKey(null)}
          onToggle={()=>toggle(drawerKey)}
          onWeight={(w)=>setWeight(drawerKey, w)}
          onWeightSave={(w)=>saveWeight(drawerKey, w)}
          onToggleTask={(taskKey)=>toggleTask(drawerKey, taskKey)}
          saveStatus={saveStatus}
        />
      )}
    </div>
  );
}

function Stat({ label, value, max, hint }) {
  return (
    <div style={{ padding:'10px 16px', background:'var(--bg-surface)', border:'1px solid var(--border)',
      borderRadius:12, minWidth:120 }}>
      <div className="eyebrow" style={{ fontSize:9, marginBottom:4 }}>{label}</div>
      <div style={{ display:'flex', alignItems:'baseline', gap:4 }}>
        <span className="mono" style={{ fontSize:20, fontWeight:700, color:'var(--ink-1)' }}>{value}</span>
        {max && <span className="mono" style={{ fontSize:13, color:'var(--ink-3)' }}>/ {max}</span>}
      </div>
      {hint && <div style={{ fontSize:10, color:'var(--ink-3)', marginTop:2 }}>{hint}</div>}
    </div>
  );
}

function Pipeline({ agents }) {
  return (
    <div className="card" style={{ padding:24, position:'relative', overflow:'hidden' }}>
      <div style={{ display:'flex', alignItems:'center', gap:12, marginBottom:18 }}>
        <div className="eyebrow">Live pipeline</div>
        <span style={{ fontSize:11, color:'var(--ink-3)' }}>How a ticker flows through your agents</span>
      </div>
      <div style={{ display:'grid', gridTemplateColumns:'auto 1fr auto', alignItems:'center', gap:24 }}>
        <PipelineNode icon={<Icon.Search size={18}/>} title="Ticker" sub="MARUTI" color="var(--ink-2)"/>
        <div style={{ position:'relative', minHeight:120 }}>
          <div style={{ display:'grid', gridTemplateColumns:`repeat(${Math.max(agents.length,1)}, 1fr)`, gap:8 }}>
            {agents.map((a,i) => (
              <div key={a.key} style={{
                padding:'10px 8px', borderRadius:10,
                background:'linear-gradient(180deg, var(--bg-surface), var(--bg-tinted))',
                border:'1px solid var(--border)', textAlign:'center',
                animation: `float-soft 3s ease-in-out infinite ${i*.15}s`
              }}>
                <div style={{ fontSize:18 }}>{a.icon}</div>
                <div style={{ fontSize:10, color:'var(--ink-2)', fontWeight:600, marginTop:4, lineHeight:1.2 }}>
                  {a.name.split(' ')[0]}
                </div>
              </div>
            ))}
          </div>
          <div style={{ position:'absolute', left:-24, top:'50%', transform:'translateY(-50%)', color:'var(--border-strong)' }}>
            <Icon.ChevronR size={14}/>
          </div>
          <div style={{ position:'absolute', right:-24, top:'50%', transform:'translateY(-50%)', color:'var(--border-strong)' }}>
            <Icon.ChevronR size={14}/>
          </div>
        </div>
        <PipelineNode icon={<Icon.Sparkles size={18}/>} title="Verdict" sub="Aggregator" color="var(--cyan)" highlight/>
      </div>
    </div>
  );
}

function PipelineNode({ icon, title, sub, color, highlight }) {
  return (
    <div style={{
      padding:'14px 18px', borderRadius:12,
      background: highlight ? 'linear-gradient(135deg, var(--cyan-soft), var(--violet-soft))' : 'var(--bg-tinted)',
      border:'1px solid var(--border)', minWidth:140, textAlign:'center'
    }}>
      <div style={{
        width:36, height:36, borderRadius:9,
        background: highlight ? 'linear-gradient(135deg,#22d3ee,#a78bfa)' : 'var(--bg-surface)',
        color: highlight ? '#fff' : color,
        display:'grid', placeItems:'center', margin:'0 auto 8px',
        boxShadow: highlight ? '0 4px 14px rgba(8,145,178,.3)' : 'none'
      }}>{icon}</div>
      <div style={{ fontSize:12, fontWeight:700 }}>{title}</div>
      <div style={{ fontSize:10, color:'var(--ink-3)', marginTop:2 }}>{sub}</div>
    </div>
  );
}

function AgentCard({ a, tasks=[], onToggle, onOpen }) {
  const activeTasks = tasks.filter(t => t.enabled).length;
  return (
    <div className="card" style={{
      padding:0, overflow:'hidden', cursor:'pointer',
      opacity: a.enabled ? 1 : 0.6,
      transition:'transform .15s, box-shadow .15s'
    }}
      onClick={onOpen}
      onMouseEnter={e=>{e.currentTarget.style.transform='translateY(-2px)'; e.currentTarget.style.boxShadow='var(--shadow-md)'}}
      onMouseLeave={e=>{e.currentTarget.style.transform=''; e.currentTarget.style.boxShadow='var(--shadow-sm)'}}>
      <div style={{
        padding:'12px 18px', display:'flex', alignItems:'center', gap:10,
        borderBottom:'1px solid var(--border)',
        background: a.enabled ? 'linear-gradient(90deg, var(--cyan-soft), transparent)' : 'transparent'
      }}>
        <span style={{
          width:8, height:8, borderRadius:'50%',
          background: a.enabled ? 'var(--buy)' : 'var(--ink-3)'
        }}/>
        <span style={{ fontSize:11, fontWeight:700, letterSpacing:'.08em', textTransform:'uppercase',
          color: a.enabled ? 'var(--buy-strong)' : 'var(--ink-3)' }}>
          {a.enabled ? 'Plugged in' : 'Unplugged'}
        </span>
        <button onClick={(e)=>{e.stopPropagation(); onToggle();}} style={{
          marginLeft:'auto', width:36, height:20, borderRadius:999, border:'none', padding:0,
          background: a.enabled ? 'var(--cyan)' : 'var(--border-strong)',
          position:'relative', cursor:'pointer', transition:'background .2s'
        }}>
          <span style={{
            position:'absolute', top:2, left: a.enabled ? 18 : 2, width:16, height:16,
            background:'#fff', borderRadius:'50%', boxShadow:'0 1px 3px rgba(0,0,0,.2)',
            transition:'left .2s'
          }}/>
        </button>
      </div>

      <div style={{ padding:18 }}>
        <div style={{ display:'flex', alignItems:'flex-start', gap:14, marginBottom:14 }}>
          <div style={{
            width:48, height:48, borderRadius:12,
            background: 'linear-gradient(135deg, var(--cyan-soft), var(--violet-soft))',
            display:'grid', placeItems:'center', fontSize:24, flexShrink:0
          }}>{a.icon}</div>
          <div style={{ flex:1, minWidth:0 }}>
            <div style={{ fontSize:14, fontWeight:700, marginBottom:2 }}>{a.name}</div>
            <div style={{ fontSize:11, color:'var(--ink-3)' }} className="mono">{a.key}</div>
          </div>
        </div>

        <div style={{ fontSize:13, color:'var(--ink-2)', lineHeight:1.5, marginBottom:12, minHeight:38 }}>
          {a.beginner}
        </div>

        {tasks.length > 0 && (
          <div style={{ display:'flex', flexWrap:'wrap', gap:4, marginBottom:12, minHeight:24 }}>
            {tasks.slice(0,3).map(t => (
              <span key={t.key} style={{
                padding:'3px 8px', borderRadius:6, fontSize:10, fontWeight:600,
                background: t.enabled ? 'var(--cyan-soft)' : 'var(--bg-tinted)',
                color: t.enabled ? 'var(--cyan)' : 'var(--ink-3)'
              }}>
                {t.enabled ? '●' : '○'} {t.label.length > 18 ? t.label.slice(0,16)+'…' : t.label}
              </span>
            ))}
            {tasks.length > 3 && (
              <span style={{ padding:'3px 8px', fontSize:10, color:'var(--ink-3)', fontWeight:600 }}>+{tasks.length - 3}</span>
            )}
          </div>
        )}

        <div style={{ display:'flex', alignItems:'center', gap:6, marginBottom:10, fontSize:11, color:'var(--ink-3)' }}>
          <Icon.Check size={12} c="var(--buy)"/>
          <span><strong style={{ color:'var(--ink-2)' }}>{activeTasks}/{tasks.length}</strong> tasks active</span>
        </div>

        <div style={{ display:'flex', alignItems:'center', gap:10, marginBottom:6 }}>
          <span style={{ fontSize:11, color:'var(--ink-3)', fontWeight:600 }}>Weight</span>
          <div style={{ flex:1, height:5, background:'var(--bg-tinted)', borderRadius:999, overflow:'hidden' }}>
            <div style={{ width: (a.weight*100/0.25)+'%', height:'100%',
              background:'linear-gradient(90deg, var(--cyan), var(--violet))',
              borderRadius:999 }}/>
          </div>
          <span className="mono" style={{ fontSize:12, fontWeight:700, color:'var(--ink-1)' }}>{(a.weight*100).toFixed(0)}%</span>
        </div>
      </div>
    </div>
  );
}

function _timeAgo(isoStr) {
  if (!isoStr) return '—';
  const diff = Date.now() - new Date(isoStr).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return 'Just now';
  if (mins < 60) return `${mins} min ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs} hr${hrs > 1 ? 's' : ''} ago`;
  const days = Math.floor(hrs / 24);
  return `${days} day${days > 1 ? 's' : ''} ago`;
}

function AgentDrawer({ a, tasks=[], onClose, onToggle, onWeight, onWeightSave, onToggleTask, saveStatus }) {
  const activeCount = tasks.filter(t => t.enabled).length;
  const [recentRuns, setRecentRuns] = useStateAg([]);
  const [runsLoading, setRunsLoading] = useStateAg(true);

  // Fetch history for all watchlist tickers on mount / agent change
  useEffectAg(() => {
    setRunsLoading(true);
    const tickers = window.WATCHLIST || ['MARUTI','TATAMOTORS','M&M','BAJAJ-AUTO','EICHERMOT'];
    Promise.all(
      tickers.map(sym =>
        fetch(`/history/${sym}?limit=5`)
          .then(r => r.ok ? r.json() : [])
          .catch(() => [])
      )
    ).then(results => {
      const runs = results
        .flat()
        .map(row => {
          let agentScore = null;
          try {
            const scores = typeof row.agent_scores === 'string'
              ? JSON.parse(row.agent_scores)
              : (row.agent_scores || {});
            agentScore = scores[a.key];
          } catch {}
          return { ticker: row.ticker, score: agentScore, runAt: row.run_at };
        })
        .filter(r => r.score != null)
        .sort((x, y) => new Date(y.runAt) - new Date(x.runAt))
        .slice(0, 5);
      setRecentRuns(runs);
      setRunsLoading(false);
    });
  }, [a.key]);

  return (
    <>
      <div onClick={onClose} style={{
        position:'fixed', inset:0, background:'rgba(15,23,42,.4)', backdropFilter:'blur(4px)', zIndex:50,
        animation:'fade-in .2s'
      }}/>
      <style>{`
        @keyframes fade-in { from { opacity:0; } to { opacity:1; } }
        @keyframes slide-in { from { transform: translateX(100%); } to { transform: translateX(0); } }
      `}</style>
      <aside style={{
        position:'fixed', top:0, right:0, bottom:0, width:520, zIndex:55,
        background:'var(--bg-surface)', boxShadow:'-20px 0 60px rgba(15,23,42,.15)',
        animation:'slide-in .3s cubic-bezier(.2,.8,.2,1)',
        display:'flex', flexDirection:'column', overflow:'hidden'
      }}>
        {/* header */}
        <div style={{ padding:'20px 24px', borderBottom:'1px solid var(--border)',
          display:'flex', alignItems:'flex-start', gap:14 }}>
          <div style={{ width:52, height:52, borderRadius:13,
            background:'linear-gradient(135deg, var(--cyan-soft), var(--violet-soft))',
            display:'grid', placeItems:'center', fontSize:26 }}>{a.icon}</div>
          <div style={{ flex:1, minWidth:0 }}>
            <div style={{ fontSize:18, fontWeight:700 }}>{a.name}</div>
            <div className="mono" style={{ fontSize:11, color:'var(--ink-3)' }}>{a.key}</div>
          </div>
          <button onClick={onClose} style={{
            width:32, height:32, borderRadius:8, border:'1px solid var(--border)',
            background:'transparent', display:'grid', placeItems:'center', color:'var(--ink-2)' }}>
            <Icon.X size={16}/>
          </button>
        </div>

        <div style={{ padding:24, overflowY:'auto', flex:1, display:'flex', flexDirection:'column', gap:24 }}>
          {/* Plug toggle */}
          <div style={{
            padding:'14px 16px', border:'1px solid var(--border)', borderRadius:12,
            display:'flex', alignItems:'center', gap:14,
            background: a.enabled ? 'var(--cyan-soft)' : 'var(--bg-base)'
          }}>
            <Icon.Plug size={20} c={a.enabled ? 'var(--cyan)' : 'var(--ink-3)'}/>
            <div style={{ flex:1 }}>
              <div style={{ fontSize:13, fontWeight:700 }}>{a.enabled ? 'This agent is plugged in' : 'This agent is unplugged'}</div>
              <div style={{ fontSize:12, color:'var(--ink-3)', marginTop:2 }}>
                {a.enabled ? 'It contributes to every verdict.' : 'Verdicts ignore this agent until plugged in.'}
              </div>
            </div>
            <button onClick={onToggle} style={{
              padding:'8px 14px', borderRadius:8, border:'1px solid var(--border-strong)',
              background:'var(--bg-surface)', fontSize:12, fontWeight:600, color:'var(--ink-1)'
            }}>{a.enabled ? 'Unplug' : 'Plug in'}</button>
          </div>

          {/* Tasks */}
          <Section title={`Tasks · ${activeCount} of ${tasks.length} active`}>
            <p style={{ fontSize:12, color:'var(--ink-3)', lineHeight:1.5, margin:'0 0 14px' }}>
              Each task is one specific signal this agent watches. Toggle off any you don't care about — the agent skips them on its next run.
            </p>
            <div style={{ display:'flex', flexDirection:'column', gap:8 }}>
              {tasks.map(t => (
                <TaskRow key={t.key} t={t} disabled={!a.enabled} onToggle={()=>onToggleTask(t.key)}/>
              ))}
            </div>
          </Section>

          {/* What it watches */}
          <Section title="What it watches">
            <p style={{ fontSize:13, color:'var(--ink-2)', lineHeight:1.6, margin:'0 0 10px' }}>
              {a.beginner}
            </p>
            <p style={{ fontSize:12, color:'var(--ink-3)', lineHeight:1.6, margin:0, fontStyle:'italic' }}>
              Technical: {a.desc}
            </p>
          </Section>

          {/* Weight slider */}
          <Section title="Weight in the verdict">
            <p style={{ fontSize:12, color:'var(--ink-3)', lineHeight:1.5, margin:'0 0 16px' }}>
              How much this agent's view counts in the final score. Drag and release to save — all weights must sum to ~100%.
            </p>
            <div style={{ display:'flex', alignItems:'center', gap:14 }}>
              <input type="range" min="0" max="0.30" step="0.01" value={a.weight}
                onChange={e => onWeight(parseFloat(e.target.value))}
                onMouseUp={e => onWeightSave(parseFloat(e.target.value))}
                onTouchEnd={e => onWeightSave(parseFloat(e.target.value))}
                disabled={!a.enabled}
                style={{ flex:1, accentColor:'var(--cyan)' }}/>
              <div style={{
                minWidth:64, padding:'6px 10px', borderRadius:8, background:'var(--bg-tinted)',
                textAlign:'center'
              }}>
                <span className="mono" style={{ fontWeight:700, fontSize:14 }}>{(a.weight*100).toFixed(0)}%</span>
              </div>
            </div>
            <div style={{ display:'flex', justifyContent:'space-between', fontSize:10, color:'var(--ink-3)', marginTop:6 }}>
              <span>Off</span><span>Default</span><span>Heavy</span>
            </div>
            {/* Save status inline */}
            {saveStatus && (
              <div style={{
                marginTop:10, padding:'6px 10px', borderRadius:8, fontSize:11, fontWeight:600,
                background: saveStatus==='saving' ? 'var(--bg-tinted)' :
                            saveStatus==='saved'  ? 'var(--buy-soft)'  : 'var(--sell-soft)',
                color: saveStatus==='saving' ? 'var(--ink-3)' :
                       saveStatus==='saved'  ? 'var(--buy-strong)' : 'var(--sell-strong)',
              }}>
                {saveStatus==='saving' ? '⟳ Saving weights…' :
                 saveStatus==='saved'  ? '✓ Weights saved to server' :
                 '⚠ ' + (saveStatus.error || 'Error saving')}
              </div>
            )}
          </Section>

          {/* Recent runs — live from /history/{ticker} */}
          <Section title="Recent runs">
            {runsLoading ? (
              <div style={{ color:'var(--ink-3)', fontSize:12, padding:'10px 0' }}>Loading history…</div>
            ) : recentRuns.length === 0 ? (
              <div style={{ color:'var(--ink-3)', fontSize:12, padding:'10px 0' }}>
                No analysis runs found yet. Run an analysis from the Home page.
              </div>
            ) : (
              <div style={{ display:'flex', flexDirection:'column', gap:6 }}>
                {recentRuns.map((r, i) => (
                  <div key={i} style={{
                    display:'grid', gridTemplateColumns:'1fr auto auto', gap:12, alignItems:'center',
                    padding:'10px 12px', background:'var(--bg-base)', borderRadius:8
                  }}>
                    <span className="mono" style={{ fontSize:12, fontWeight:700 }}>{r.ticker}</span>
                    <span className="mono" style={{
                      fontSize:12, fontWeight:700,
                      color: r.score >= 0.7 ? 'var(--buy-strong)' : r.score >= 0.5 ? 'var(--neutral)' : 'var(--sell-strong)'
                    }}>{r.score.toFixed(2)}</span>
                    <span style={{ fontSize:11, color:'var(--ink-3)' }}>{_timeAgo(r.runAt)}</span>
                  </div>
                ))}
              </div>
            )}
          </Section>

          {/* Data sources */}
          <Section title="Data sources">
            <div style={{ display:'flex', gap:6, flexWrap:'wrap' }}>
              {(window.AGENT_SOURCES?.[a.key] || ['LLM knowledge','Serper news','yfinance']).map(s => (
                <span key={s} style={{
                  padding:'4px 10px', borderRadius:999, background:'var(--bg-tinted)',
                  fontSize:11, color:'var(--ink-2)', fontWeight:600
                }}>{s}</span>
              ))}
            </div>
          </Section>
        </div>
      </aside>
    </>
  );
}

function TaskRow({ t, disabled, onToggle }) {
  return (
    <div style={{
      display:'grid', gridTemplateColumns:'1fr auto', gap:12, alignItems:'center',
      padding:'12px 14px', borderRadius:10,
      background: t.enabled ? 'var(--bg-base)' : 'transparent',
      border:'1px solid var(--border)',
      opacity: disabled ? 0.5 : 1,
      transition:'background .15s'
    }}>
      <div style={{ minWidth:0 }}>
        <div style={{ fontSize:13, fontWeight:600, color: t.enabled ? 'var(--ink-1)' : 'var(--ink-3)' }}>{t.label}</div>
        <div style={{ fontSize:11, color:'var(--ink-3)', marginTop:2, lineHeight:1.4 }}>{t.beginner}</div>
        <div className="mono" style={{ fontSize:10, color:'var(--ink-3)', marginTop:6 }}>{t.source}</div>
      </div>
      <button onClick={onToggle} disabled={disabled} style={{
        width:34, height:20, borderRadius:999, border:'none', padding:0,
        background: t.enabled ? 'var(--cyan)' : 'var(--border-strong)',
        position:'relative', cursor: disabled ? 'not-allowed' : 'pointer', transition:'background .2s'
      }}>
        <span style={{
          position:'absolute', top:2, left: t.enabled ? 16 : 2, width:16, height:16,
          background:'#fff', borderRadius:'50%', boxShadow:'0 1px 3px rgba(0,0,0,.2)',
          transition:'left .2s'
        }}/>
      </button>
    </div>
  );
}

function Section({ title, children }) {
  return (
    <div>
      <div className="eyebrow" style={{ marginBottom:10 }}>{title}</div>
      {children}
    </div>
  );
}

window.AGENT_SOURCES = {
  sales_demand:      ['Serper news','FADA','SIAM','Vahan'],
  fundamentals:      ['yfinance','Serper news','NSE filings'],
  pattern_analysis:  ['yfinance OHLCV','RSI/MACD/BB (C++)'],
  raw_materials:     ['yfinance commodities','Serper news'],
  sentiment:         ['Serper news','Twitter/Reddit','YouTube'],
  policy_regulatory: ['Tavily','Serper','gov circulars'],
  competitive_intel: ['Serper news','peer baskets'],
  risk_macro:        ['yfinance INR/crude','macro cache'],
  valuation_catalyst:['LLM knowledge','peer P/E','price targets'],
};

window.AgentsPage = AgentsPage;
