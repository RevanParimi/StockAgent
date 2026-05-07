// Beginner Home screen — tabbed (Today / This month / Watchlist / Trending)
const { useState: useStateHome, useMemo, useEffect: useEffectHome, useRef: useRefHome } = React;

function Home({ onNav, openChat }) {
  const [tab, setTab] = useStateHome('today');
  const [search, setSearch] = useStateHome('');
  // analyzeState: { ticker, loading, report, error, agentProgress }
  const [analyzeState, setAnalyzeState] = useStateHome({ ticker: null, loading: false, report: null, error: null, agentProgress: {} });
  const [selectedDriver, setSelectedDriver] = useStateHome(null);
  const [selectedCategory, setSelectedCategory] = useStateHome(null);

  const onAnalyze = (sym) => {
    localStorage.setItem('sa_last_ticker', sym);
    setAnalyzeState({ ticker: sym, loading: true, report: null, error: null, agentProgress: {} });

    // T2.6 — WebSocket streaming with POST fallback
    const wsProto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    let ws;
    try {
      ws = new WebSocket(`${wsProto}//${window.location.host}/ws/stream?ticker=${encodeURIComponent(sym)}`);
    } catch {
      ws = null;
    }

    const fallbackPost = () => {
      fetch('/analyse', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ticker: sym }),
      })
        .then(r => r.ok ? r.json() : r.json().then(e => Promise.reject(e.detail || 'Analysis failed')))
        .then(report => setAnalyzeState(prev => ({ ...prev, loading: false, report })))
        .catch(err  => setAnalyzeState(prev => ({ ...prev, loading: false, error: String(err) })));
    };

    if (!ws) { fallbackPost(); return; }

    ws.onmessage = (evt) => {
      try {
        const msg = JSON.parse(evt.data);
        if (msg.event === 'agent_progress') {
          setAnalyzeState(prev => ({
            ...prev,
            agentProgress: { ...prev.agentProgress, [msg.agent]: msg.score },
          }));
        } else if (msg.event === 'complete') {
          setAnalyzeState(prev => ({ ...prev, loading: false, report: msg.report }));
          ws.close(1000);
        } else if (msg.event === 'error') {
          setAnalyzeState(prev => ({ ...prev, loading: false, error: msg.detail || 'Analysis failed' }));
          ws.close(1000);
        }
      } catch {}
    };

    ws.onerror = () => {
      // WebSocket failed — fall back to plain POST
      setAnalyzeState(prev => ({ ...prev, agentProgress: {} }));
      fallbackPost();
    };
  };

  const closeAnalysis = () => setAnalyzeState({ ticker: null, loading: false, report: null, error: null });

  return (
    <div style={{ minHeight:'100vh', background:'var(--bg-base)' }}>
      <TopNav active="home" onNav={onNav} search={search} setSearch={setSearch}/>

      <main style={{ maxWidth:1280, margin:'0 auto', padding:'var(--main-py) var(--main-px) 96px' }}>
        {/* HERO */}
        <Hero openChat={openChat} onAnalyze={onAnalyze}/>

        {/* TAB BAR */}
        <div className="tab-bar" style={{
          display:'flex', gap:4, padding:4, background:'var(--bg-tinted)', borderRadius:14,
          marginBottom:24, width:'fit-content'
        }}>
          {[
            {k:'today', label:"Today's market", icon:<Icon.Trend size={15}/>},
            {k:'month', label:'This month',    icon:<Icon.Compass size={15}/>},
            {k:'watch', label:'Watchlist',      icon:<Icon.Star size={15}/>},
            {k:'trend', label:'Trending',       icon:<Icon.Sparkles size={15}/>},
          ].map(t => (
            <button key={t.k} onClick={()=>setTab(t.k)} style={{
              display:'flex', alignItems:'center', gap:8, padding:'10px 18px', borderRadius:11,
              border:'none', fontSize:13, fontWeight:600,
              background: tab===t.k ? 'var(--bg-surface)' : 'transparent',
              color: tab===t.k ? 'var(--ink-1)' : 'var(--ink-3)',
              boxShadow: tab===t.k ? 'var(--shadow-sm)' : 'none',
              transition:'all .15s'
            }}>{t.icon} {t.label}</button>
          ))}
        </div>

        {tab==='today' && <TodayPane data={window.MARKET_TODAY} onDriverClick={setSelectedDriver}/>}
        {tab==='month' && <MonthPane data={window.MARKET_MONTH} onDriverClick={setSelectedDriver}/>}
        {tab==='watch' && <WatchlistPane onAnalyze={onAnalyze}/>}
        {tab==='trend' && <TrendingPane onAnalyze={onAnalyze}/>}

        {/* CATEGORIES */}
        <div style={{ marginTop:36 }}>
          <SectionHead title="Browse by category" subtitle="Pick a slice of the auto sector"/>
          <div style={{ display:'grid', gridTemplateColumns:'var(--grid-categories)', gap:12, marginTop:16 }}>
            {window.CATEGORIES.map(c => <CategoryCard key={c.key} c={c} onClick={()=>setSelectedCategory(c)}/>)}
          </div>
        </div>

        {/* SUGGESTIONS */}
        <div style={{ marginTop:36 }}>
          <SectionHead title="Suggested for you" subtitle="Picked by your agents based on what you watch"/>
          <div style={{ display:'grid', gridTemplateColumns:'var(--grid-suggestions)', gap:16, marginTop:16 }}>
            {window.SUGGESTIONS.map(s => <SuggestCard key={s.sym} s={s} onAnalyze={onAnalyze}/>)}
          </div>
        </div>
      </main>

      {/* Analysis result drawer */}
      {analyzeState.ticker && (
        <AnalysisResultDrawer state={analyzeState} onClose={closeAnalysis}/>
      )}

      {/* Driver detail panel */}
      {selectedDriver && (
        <DriverDetailPanel driver={selectedDriver} onClose={()=>setSelectedDriver(null)} onAnalyze={onAnalyze}/>
      )}

      {/* Category drawer */}
      {selectedCategory && (
        <CategoryDrawer category={selectedCategory} onClose={()=>setSelectedCategory(null)} onAnalyze={onAnalyze}/>
      )}
    </div>
  );
}

function TopNav({ active, onNav, search, setSearch }) {
  const [results, setResults] = useStateHome([]);
  const [dropOpen, setDropOpen] = useStateHome(false);
  const [menuOpen, setMenuOpen] = useStateHome(false);
  const timerRef = useRefHome(null);

  const handleSearch = (val) => {
    setSearch(val);
    clearTimeout(timerRef.current);
    if (val.length < 2) { setResults([]); setDropOpen(false); return; }
    timerRef.current = setTimeout(async () => {
      try {
        const res = await fetch(`/ui/search?q=${encodeURIComponent(val)}`);
        if (res.ok) {
          const d = await res.json();
          setResults(d.results || []);
          setDropOpen((d.results || []).length > 0);
        }
      } catch {}
    }, 350);
  };

  const navLinks = [
    { screen:'home',      label:'Home',      icon:<Icon.Home size={17}/> },
    { screen:'agents',    label:'Agents',    icon:<Icon.Cpu size={17}/> },
    { screen:'portfolio', label:'Portfolio', icon:<Icon.Briefcase size={17}/> },
    { screen:'learn',     label:'Learn',     icon:<Icon.Book size={17}/> },
  ];

  return (
    <>
      {/* ── Full-screen mobile menu ── */}
      {menuOpen && (
        <div className="mobile-menu">
          <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:28 }}>
            <div style={{ display:'flex', alignItems:'center', gap:10 }}>
              <div style={{ width:32, height:32, borderRadius:9, background:'linear-gradient(135deg,#22d3ee,#7c3aed)', display:'grid', placeItems:'center' }}>
                <Icon.Sparkles size={16} c="#fff"/>
              </div>
              <div style={{ fontWeight:800 }}>StockAgent</div>
            </div>
            <button onClick={()=>setMenuOpen(false)} style={{ width:36, height:36, borderRadius:9, border:'1px solid var(--border)', background:'transparent', display:'grid', placeItems:'center' }}>
              <Icon.X size={18}/>
            </button>
          </div>
          {navLinks.map(l => (
            <button key={l.screen} onClick={()=>{ onNav?.(l.screen); setMenuOpen(false); }} style={{
              display:'flex', alignItems:'center', gap:14, padding:'16px 14px', borderRadius:12, width:'100%',
              border:'none', background: active===l.screen ? 'var(--bg-tinted)' : 'transparent',
              color: active===l.screen ? 'var(--cyan)' : 'var(--ink-1)',
              fontSize:16, fontWeight:600, textAlign:'left', marginBottom:4
            }}>{l.icon} {l.label}</button>
          ))}
          <div style={{ flex:1 }}/>
          <button onClick={()=>{ onNav?.('auth'); setMenuOpen(false); }} style={{
            display:'flex', alignItems:'center', gap:10, padding:'14px', borderRadius:12, width:'100%',
            border:'1px solid var(--border)', background:'transparent', fontSize:14, fontWeight:600,
            color:'var(--ink-2)', marginTop:20
          }}><Icon.User size={16}/> Sign out</button>
        </div>
      )}

      {/* ── Mobile bottom nav bar ── */}
      <nav className="mobile-bottom-nav">
        {navLinks.map(l => (
          <button
            key={l.screen}
            onClick={()=>onNav?.(l.screen)}
            className={'mobile-bottom-btn' + (active===l.screen ? ' active' : '')}
          >
            <span className="mobile-bottom-icon">{l.icon}</span>
            <span className="mobile-bottom-label">{l.label}</span>
          </button>
        ))}
      </nav>

      <header style={{
        position:'sticky', top:0, zIndex:30, background:'rgba(255,255,255,.85)',
        backdropFilter:'blur(12px)', borderBottom:'1px solid var(--border)'
      }}>
        <div style={{ maxWidth:1280, margin:'0 auto', padding:'12px var(--main-px)',
          display:'flex', alignItems:'center', gap:16 }}>

          {/* Logo */}
          <div style={{ display:'flex', alignItems:'center', gap:10, cursor:'pointer', flexShrink:0 }} onClick={()=>onNav?.('home')}>
            <div style={{ width:32, height:32, borderRadius:9, background:'linear-gradient(135deg,#22d3ee,#7c3aed)', display:'grid', placeItems:'center' }}>
              <Icon.Sparkles size={16} c="#fff"/>
            </div>
            <div style={{ fontWeight:800, letterSpacing:'-0.01em' }}>StockAgent</div>
          </div>

          {/* Desktop nav links — pill bar */}
          <nav className="nav-desktop nav-top-pill" style={{
            marginLeft:16, display:'flex', gap:3, padding:'5px 6px',
            background:'linear-gradient(135deg, rgba(34,211,238,.09) 0%, rgba(99,102,241,.07) 100%)',
            border:'1px solid rgba(34,211,238,.2)',
            borderRadius:999,
            boxShadow:'0 1px 4px rgba(34,211,238,.1), inset 0 1px 0 rgba(255,255,255,.55)',
            backdropFilter:'blur(6px)',
          }}>
            {navLinks.map(l => (
              <NavLink key={l.screen} onClick={()=>onNav?.(l.screen)} active={active===l.screen} icon={l.icon}>
                {l.label}
              </NavLink>
            ))}
          </nav>

          {/* Desktop search */}
          <div className="nav-desktop" style={{ flex:1, position:'relative', maxWidth:400, marginLeft:'auto' }}
            onBlur={e => { if (!e.currentTarget.contains(e.relatedTarget)) setDropOpen(false); }}>
            <Icon.Search size={16} style={{ position:'absolute', left:12, top:'50%', transform:'translateY(-50%)', color:'var(--ink-3)', pointerEvents:'none' }}/>
            <input value={search} onChange={e=>handleSearch(e.target.value)}
              onFocus={()=>results.length > 0 && setDropOpen(true)}
              placeholder="Search MARUTI, Tata Motors..." style={{
                width:'100%', padding:'9px 12px 9px 36px', border:'1px solid var(--border)', borderRadius:10,
                background:'var(--bg-base)', fontSize:13, outline:'none'
              }}/>
            {dropOpen && results.length > 0 && (
              <div style={{ position:'absolute', top:'calc(100% + 6px)', left:0, right:0, zIndex:50,
                background:'var(--bg-surface)', border:'1px solid var(--border)', borderRadius:12,
                boxShadow:'var(--shadow-lg)', overflow:'hidden' }}>
                {results.map((r, i) => (
                  <button key={i} onClick={()=>{setSearch(''); setDropOpen(false);}} style={{
                    display:'flex', alignItems:'center', gap:10, width:'100%',
                    padding:'10px 14px', border:'none', background:'transparent', textAlign:'left',
                    borderBottom: i < results.length-1 ? '1px solid var(--border)' : 'none', cursor:'pointer'
                  }}
                    onMouseEnter={e=>e.currentTarget.style.background='var(--bg-tinted)'}
                    onMouseLeave={e=>e.currentTarget.style.background='transparent'}>
                    <div style={{ width:30, height:30, borderRadius:8, background:'linear-gradient(135deg,var(--cyan-soft),var(--violet-soft))', display:'grid', placeItems:'center', fontWeight:800, color:'var(--cyan)', fontSize:12, flexShrink:0 }}>{r.sym[0]}</div>
                    <div style={{ flex:1, minWidth:0 }}>
                      <div className="mono" style={{ fontWeight:700, fontSize:12 }}>{r.sym}</div>
                      <div style={{ fontSize:11, color:'var(--ink-3)', overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap' }}>{r.snippet || r.name}</div>
                    </div>
                    <span style={{ fontSize:10, color:'var(--ink-3)', flexShrink:0, padding:'2px 6px', borderRadius:4, background:'var(--bg-tinted)' }}>{r.type}</span>
                  </button>
                ))}
              </div>
            )}
          </div>

          {/* Theme toggle + bell + avatar — desktop */}
          <ThemeToggle className="nav-desktop"/>
          <button className="nav-desktop" style={{ width:36, height:36, borderRadius:'50%', border:'1px solid var(--border)', background:'var(--bg-surface)', display:'grid', placeItems:'center', position:'relative', flexShrink:0 }}>
            <Icon.Bell size={16} c="var(--ink-2)"/>
            <span style={{ position:'absolute', top:6, right:6, width:8, height:8, borderRadius:'50%', background:'var(--sell-strong)' }}/>
          </button>
          <div className="nav-desktop" style={{ width:36, height:36, borderRadius:'50%', background:'linear-gradient(135deg,#22d3ee,#a78bfa)', display:'grid', placeItems:'center', color:'#fff', fontWeight:700, fontSize:13, flexShrink:0 }}>AS</div>

          {/* Mobile: theme toggle + hamburger */}
          <div className="nav-hamburger" style={{ marginLeft:'auto', gap:8 }}>
            <ThemeToggle/>
            <div style={{ width:32, height:32, borderRadius:'50%', background:'linear-gradient(135deg,#22d3ee,#a78bfa)', display:'grid', placeItems:'center', color:'#fff', fontWeight:700, fontSize:12 }}>AS</div>
            <button onClick={()=>setMenuOpen(true)} style={{ width:36, height:36, borderRadius:9, border:'1px solid var(--border)', background:'var(--bg-surface)', display:'grid', placeItems:'center' }}>
              <svg width="18" height="18" viewBox="0 0 18 18" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
                <line x1="2" y1="4" x2="16" y2="4"/><line x1="2" y1="9" x2="16" y2="9"/><line x1="2" y1="14" x2="16" y2="14"/>
              </svg>
            </button>
          </div>
        </div>
      </header>
    </>
  );
}

function NavLink({ children, icon, active, onClick }) {
  return (
    <button onClick={onClick} style={{
      display:'flex', alignItems:'center', gap:6, padding:'7px 13px', borderRadius:999,
      border:'none',
      background: active ? 'var(--bg-surface)' : 'transparent',
      boxShadow: active ? '0 1px 5px rgba(34,211,238,.2)' : 'none',
      color: active ? 'var(--ink-1)' : 'var(--ink-2)',
      fontSize:13, fontWeight:600, cursor:'pointer', transition:'background .15s, color .15s',
    }}>{icon} {children}</button>
  );
}

// Fully self-contained — no props needed except optional className.
// Reads/writes data-theme directly so it works instantly without waiting for React re-renders.
function ThemeToggle({ className }) {
  const [isDark, setIsDark] = useStateHome(
    () => document.documentElement.getAttribute('data-theme') === 'dark'
  );

  // Stay in sync if TweaksPanel changes the attribute externally
  useEffectHome(() => {
    const obs = new MutationObserver(() => {
      setIsDark(document.documentElement.getAttribute('data-theme') === 'dark');
    });
    obs.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
    return () => obs.disconnect();
  }, []);

  const toggle = () => {
    const next = !isDark;
    // Set DOM attribute directly — CSS responds instantly, no React state dependency
    document.documentElement.setAttribute('data-theme', next ? 'dark' : 'light');
    // Sync App's tweaks state (prevents TweaksPanel going out of sync)
    if (window.__setTheme) window.__setTheme(next ? 'dark' : 'light');
    // setIsDark called by MutationObserver above
  };

  return (
    <button
      onClick={toggle}
      className={className}
      title={isDark ? 'Switch to light' : 'Switch to dark'}
      style={{
        width:36, height:36, borderRadius:'50%', flexShrink:0,
        border:'1px solid rgba(34,211,238,.4)',
        background: isDark
          ? 'linear-gradient(135deg,#1e3d60,#0d2240)'
          : 'linear-gradient(135deg,rgba(34,211,238,.18),rgba(99,102,241,.12))',
        display:'grid', placeItems:'center', cursor:'pointer',
        boxShadow:'0 0 0 2px rgba(34,211,238,.15)',
        transition:'background .25s',
      }}
    >
      {isDark
        ? <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="#fde047" strokeWidth="2.2" strokeLinecap="round"><circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/></svg>
        : <svg width="15" height="15" viewBox="0 0 24 24" fill="rgba(34,211,238,.3)" stroke="#0891b2" strokeWidth="2.2" strokeLinecap="round"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>
      }
    </button>
  );
}

function Hero({ openChat, onAnalyze }) {
  return (
    <section style={{
      position:'relative', overflow:'hidden', borderRadius:24,
      background:'linear-gradient(135deg, #0a1628 0%, #134e5c 50%, #1a4a73 100%)',
      color:'#f1f5f9', padding:'32px var(--main-px)', marginBottom:32,
      display:'grid', gridTemplateColumns:'var(--hero-cols)', gap:32, alignItems:'center'
    }}>
      <div style={{ position:'absolute', top:'-30%', right:'-10%', width:600, height:600, borderRadius:'50%',
        background:'radial-gradient(circle, rgba(124,58,237,.35), transparent 65%)', filter:'blur(40px)' }}/>
      <div style={{ position:'absolute', bottom:'-40%', left:'-10%', width:520, height:520, borderRadius:'50%',
        background:'radial-gradient(circle, rgba(8,145,178,.4), transparent 65%)', filter:'blur(40px)' }}/>

      <div style={{ position:'relative', zIndex:2 }}>
        <div style={{ display:'inline-flex', alignItems:'center', gap:8, padding:'6px 12px', borderRadius:999,
          background:'rgba(34,211,238,.15)', border:'1px solid rgba(34,211,238,.3)', fontSize:11, fontWeight:600,
          color:'#67e8f9', marginBottom:16, letterSpacing:'.05em' }}>
          <span style={{ width:6, height:6, borderRadius:'50%', background:'#22d3ee', display:'inline-block', animation:'pulse-soft 2s ease-in-out infinite' }}/>
          LIVE · {new Date().toLocaleString('en-IN', { hour:'2-digit', minute:'2-digit', day:'numeric', month:'short' })} IST
        </div>
        <h1 style={{ fontSize:34, fontWeight:800, letterSpacing:'-0.02em', lineHeight:1.15, margin:'0 0 12px' }}>
          Good afternoon, Aditi.<br/>
          <span style={{ color:'#94a3b8', fontWeight:600 }}>Auto sector</span> <span style={{ color:'#22c55e' }}>+1.24%</span> <span style={{ color:'#94a3b8', fontWeight:600 }}>today.</span>
        </h1>
        <p style={{ color:'#cbd5e1', fontSize:15, lineHeight:1.6, margin:'0 0 20px', maxWidth:520 }}>
          {window.MARKET_TODAY.oneLiner} Ask the assistant anything — or jump to a tab below.
        </p>
        <div style={{ display:'flex', gap:10, flexWrap:'wrap' }}>
          <button onClick={openChat} style={{
            padding:'10px 18px', borderRadius:10, border:'none',
            background:'linear-gradient(135deg,#22d3ee,#a78bfa)', color:'#0a1628',
            fontSize:13, fontWeight:700, display:'flex', alignItems:'center', gap:8, cursor:'pointer'
          }}><Icon.Sparkles size={15}/> Ask the assistant</button>
          <button onClick={()=>onAnalyze('MARUTI')} style={{
            padding:'10px 18px', borderRadius:10, border:'1px solid rgba(255,255,255,.18)',
            background:'rgba(255,255,255,.06)', color:'#f1f5f9',
            fontSize:13, fontWeight:600, display:'flex', alignItems:'center', gap:8, cursor:'pointer'
          }}><Icon.Star size={15}/> Run on MARUTI</button>
        </div>
      </div>

      <div style={{ position:'relative', zIndex:2, display:'grid', placeItems:'center' }}>
        <button onClick={openChat} style={{ background:'transparent', border:'none', cursor:'pointer' }}
          aria-label="Open assistant">
          <Sphere size={260} mode="wireframe"/>
        </button>
      </div>
    </section>
  );
}

function SectionHead({ title, subtitle, action }) {
  return (
    <div style={{ display:'flex', alignItems:'flex-end', justifyContent:'space-between', gap:16 }}>
      <div>
        <h2 style={{ fontSize:20, fontWeight:700, letterSpacing:'-0.01em', margin:'0 0 4px' }}>{title}</h2>
        {subtitle && <p style={{ color:'var(--ink-3)', fontSize:13, margin:0 }}>{subtitle}</p>}
      </div>
      {action}
    </div>
  );
}

// ---------- TODAY pane ----------
function TodayPane({ data, onDriverClick }) {
  const [range, setRange] = useStateHome('1M');
  // T2.1 — fetched range data overrides mock NIFTY_AUTO_RANGES for non-1M tabs
  const [fetchedRange, setFetchedRange] = useStateHome(null);
  const [rangeFetching, setRangeFetching] = useStateHome(false);

  const handleRangeChange = async (newRange) => {
    setRange(newRange);
    if (newRange === '1M') { setFetchedRange(null); return; } // 1M already in bootstrap
    setRangeFetching(true);
    try {
      const res = await fetch(`/ui/nifty-ranges?range=${newRange}`);
      if (res.ok) setFetchedRange(await res.json()); // {range, points, label, change}
    } catch {}
    setRangeFetching(false);
  };

  const r = fetchedRange || window.NIFTY_AUTO_RANGES[range];

  return (
    <div style={{ display:'grid', gridTemplateColumns:'var(--grid-2col)', gap:20 }}>
      {/* Market pulse + drivers */}
      <div className="card" style={{ padding:24 }}>
        <div style={{ display:'flex', alignItems:'center', gap:12, marginBottom:16 }}>
          <PulseDot kind="good"/>
          <div>
            <div className="eyebrow" style={{ marginBottom:4 }}>Market pulse · today</div>
            <div style={{ fontSize:18, fontWeight:700 }}>{data.pulse}</div>
          </div>
          <div style={{ marginLeft:'auto', fontSize:12,
            color: data.freshness?.isStale ? 'var(--neutral)' : 'var(--ink-3)',
            display:'flex', alignItems:'center', gap:5 }}>
            {data.freshness?.isStale && <span style={{ width:6, height:6, borderRadius:'50%', background:'var(--neutral)', display:'inline-block' }}/>}
            {data.freshness?.label || 'Updated recently'}
          </div>
        </div>

        <p style={{ color:'var(--ink-2)', fontSize:14, lineHeight:1.6, margin:'0 0 20px' }}>
          {data.oneLiner}
        </p>

        <div className="eyebrow" style={{ marginBottom:10 }}>What's moving the market</div>
        <div style={{ display:'flex', flexDirection:'column', gap:10 }}>
          {data.drivers.map((d,i) => <DriverRow key={i} d={d} onClick={onDriverClick}/>)}
        </div>
      </div>

      {/* Sector heatmap + Nifty Auto sparkline */}
      <div style={{ display:'flex', flexDirection:'column', gap:20 }}>
        <div className="card" style={{ padding:20 }}>
          <div style={{ display:'flex', justifyContent:'space-between', alignItems:'flex-start', marginBottom:14, gap:10 }}>
            <div>
              <div className="eyebrow" style={{ marginBottom:4 }}>Nifty Auto</div>
              <div style={{ display:'flex', alignItems:'baseline', gap:8 }}>
                <span className="mono" style={{ fontSize:24, fontWeight:700 }}>22,847</span>
                <span style={{ color: r.change >= 0 ? 'var(--buy-strong)' : 'var(--sell-strong)', fontWeight:700, fontSize:13 }}>
                  {r.change >= 0 ? '+' : ''}{r.change.toFixed(2)}%
                </span>
              </div>
              <div style={{ fontSize:11, color:'var(--ink-3)', marginTop:2 }}>over {r.label}</div>
            </div>
            <RangeTabs value={range} onChange={handleRangeChange}/>
          </div>
          <Sparkline values={r.points} height={70} color="var(--cyan)"/>
        </div>

        <div className="card" style={{ padding:20 }}>
          <div className="eyebrow" style={{ marginBottom:12 }}>Sectors today</div>
          <div style={{ display:'flex', flexDirection:'column', gap:8 }}>
            {data.sectorChange.map(s => <SectorRow key={s.name} s={s}/>)}
          </div>
        </div>
      </div>
    </div>
  );
}

function MonthPane({ data, onDriverClick }) {
  return (
    <div style={{ display:'grid', gridTemplateColumns:'var(--grid-2col)', gap:20 }}>
      <div className="card" style={{ padding:24 }}>
        <div style={{ display:'flex', alignItems:'center', gap:12, marginBottom:16 }}>
          <PulseDot kind="good"/>
          <div>
            <div className="eyebrow" style={{ marginBottom:4 }}>Market pulse · this month</div>
            <div style={{ fontSize:18, fontWeight:700 }}>{data.pulse}</div>
          </div>
          <div style={{ marginLeft:'auto', fontSize:12, color:'var(--ink-3)' }}>
            {new Date().toLocaleString('en-IN', { month:'long', year:'numeric' })}
          </div>
        </div>
        <p style={{ color:'var(--ink-2)', fontSize:14, lineHeight:1.6, margin:'0 0 20px' }}>{data.oneLiner}</p>
        <div className="eyebrow" style={{ marginBottom:10 }}>Themes shaping this month</div>
        <div style={{ display:'flex', flexDirection:'column', gap:10 }}>
          {data.drivers.map((d,i) => <DriverRow key={i} d={d} onClick={onDriverClick}/>)}
        </div>
      </div>

      <div className="card" style={{ padding:20 }}>
        <div className="eyebrow" style={{ marginBottom:14 }}>How agents are voting</div>
        <div style={{ display:'flex', flexDirection:'column', gap:10 }}>
          {(data.agentVotes || [
            {n:'Sales & Demand',      v:0.78, k:'good'},
            {n:'Fundamentals',        v:0.72, k:'good'},
            {n:'Pattern Analysis',    v:0.65, k:'good'},
            {n:'Sentiment',           v:0.61, k:'good'},
            {n:'Policy & Regulatory', v:0.58, k:'mid'},
            {n:'Raw Materials',       v:0.55, k:'mid'},
            {n:'Competitive Intel',   v:0.52, k:'mid'},
            {n:'Risk & Macro',        v:0.42, k:'bad'},
          ]).map(a => (
            <div key={a.n} style={{ display:'grid', gridTemplateColumns:'1fr 80px 50px', alignItems:'center', gap:10 }}>
              <span style={{ fontSize:13, color:'var(--ink-2)' }}>{a.n}</span>
              <div style={{ height:6, background:'var(--bg-tinted)', borderRadius:999, overflow:'hidden' }}>
                <div style={{ width: (a.v*100)+'%', height:'100%',
                  background: a.k==='good' ? 'var(--buy)' : a.k==='mid' ? 'var(--neutral)' : 'var(--sell)',
                  borderRadius:999, transition:'width .8s' }}/>
              </div>
              <span className="mono" style={{ fontSize:12, color:'var(--ink-2)', textAlign:'right' }}>{a.v.toFixed(2)}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function WatchlistPane({ onAnalyze }) {
  const [watchlist, setWatchlist] = useStateHome(window.WATCHLIST);
  const [liveTickers, setLiveTickers] = useStateHome(null); // null = not yet fetched
  const [addOpen, setAddOpen] = useStateHome(false);
  const [addVal, setAddVal] = useStateHome('');
  const [addError, setAddError] = useStateHome('');
  const [addBusy, setAddBusy] = useStateHome(false);

  // Fetch live prices from GET /ui/watchlist on mount
  useEffectHome(() => {
    fetch('/ui/watchlist')
      .then(r => r.ok ? r.json() : null)
      .then(d => { if (d?.tickers) setLiveTickers(d.tickers); })
      .catch(() => {});
  }, []);

  // Use live ticker data if available, fall back to bootstrap window.TICKERS
  const tickers = liveTickers
    ? watchlist.map(s => liveTickers.find(t => t.sym === s)).filter(Boolean)
    : watchlist.map(s => window.TICKERS.find(t => t.sym === s)).filter(Boolean);
  const allSyms = (window.TICKERS || []).map(t => t.sym);

  const handleAdd = async () => {
    const sym = addVal.trim().toUpperCase();
    if (!sym) { setAddError('Enter a ticker symbol'); return; }
    if (!allSyms.includes(sym)) { setAddError(`${sym} not in supported list: ${allSyms.join(', ')}`); return; }
    if (watchlist.includes(sym)) { setAddError(`${sym} already in watchlist`); return; }
    setAddBusy(true);
    const newList = [...watchlist, sym];
    try {
      const res = await fetch('/ui/watchlist', {
        method: 'PUT',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ watchlist: newList }),
      });
      if (res.ok) {
        const d = await res.json();
        window.WATCHLIST = d.watchlist;
        setWatchlist(d.watchlist);
        setAddOpen(false); setAddVal(''); setAddError('');
        // Refresh live prices for new watchlist
        fetch('/ui/watchlist').then(r => r.ok ? r.json() : null).then(d2 => { if (d2?.tickers) setLiveTickers(d2.tickers); }).catch(()=>{});
      } else {
        setAddError('Server error — try again');
      }
    } catch { setAddError('Network error'); }
    setAddBusy(false);
  };

  const handleRemove = async (sym) => {
    const newList = watchlist.filter(s => s !== sym);
    try {
      const res = await fetch('/ui/watchlist', {
        method: 'PUT',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ watchlist: newList }),
      });
      if (res.ok) {
        window.WATCHLIST = newList; setWatchlist(newList);
        fetch('/ui/watchlist').then(r => r.ok ? r.json() : null).then(d2 => { if (d2?.tickers) setLiveTickers(d2.tickers); }).catch(()=>{});
      }
    } catch {}
  };

  return (
    <div className="card" style={{ overflow:'hidden' }}>
      <div style={{ padding:'18px 24px', borderBottom:'1px solid var(--border)', display:'flex', alignItems:'center', gap:12 }}>
        <div className="eyebrow">Your watchlist · {tickers.length} stocks</div>
        <button onClick={()=>setAddOpen(o=>!o)} style={{ marginLeft:'auto', padding:'6px 12px',
          border:'1px dashed var(--border-strong)', borderRadius:8,
          background:'transparent', fontSize:12, fontWeight:600, color:'var(--ink-2)',
          display:'flex', alignItems:'center', gap:6, cursor:'pointer' }}>
          <Icon.Plus size={13}/> Add ticker
        </button>
      </div>

      {/* Inline add-ticker form */}
      {addOpen && (
        <div style={{ padding:'14px 24px', borderBottom:'1px solid var(--border)', background:'var(--bg-base)',
          display:'flex', gap:10, alignItems:'center', flexWrap:'wrap' }}>
          <input value={addVal} onChange={e=>{setAddVal(e.target.value); setAddError('');}}
            onKeyDown={e=>e.key==='Enter' && handleAdd()}
            placeholder="e.g. TVSMOTORS" style={{
              padding:'8px 12px', border:'1px solid var(--border)', borderRadius:8,
              fontSize:13, background:'var(--bg-surface)', outline:'none', minWidth:180
            }}/>
          <button onClick={handleAdd} disabled={addBusy} style={{
            padding:'8px 14px', border:'none', borderRadius:8,
            background:'var(--cyan)', color:'#fff', fontSize:12, fontWeight:700, cursor:'pointer'
          }}>{addBusy ? '…' : 'Add'}</button>
          <button onClick={()=>{setAddOpen(false); setAddVal(''); setAddError('');}} style={{
            padding:'8px 12px', border:'1px solid var(--border)', borderRadius:8,
            background:'transparent', fontSize:12, color:'var(--ink-2)', cursor:'pointer'
          }}>Cancel</button>
          {addError && <span style={{ fontSize:12, color:'var(--sell-strong)' }}>{addError}</span>}
          <span style={{ fontSize:11, color:'var(--ink-3)', marginLeft:'auto' }}>
            Supported: {allSyms.join(' · ')}
          </span>
        </div>
      )}

      {/* Desktop — full table */}
      <div className="ticker-table-wrap">
        <table style={{ width:'100%', borderCollapse:'collapse' }}>
          <thead>
            <tr style={{ fontSize:11, textTransform:'uppercase', color:'var(--ink-3)', letterSpacing:'.1em' }}>
              <th style={th}>Ticker</th><th style={th}>Price</th><th style={th}>Change</th>
              <th style={th}>Score</th><th style={th}>Verdict</th><th style={{...th, textAlign:'right'}}>Action</th>
            </tr>
          </thead>
          <tbody>
            {tickers.map(t => (
              <TickerRow key={t.sym} t={t}
                onAnalyze={()=>onAnalyze(t.sym)}
                onRemove={()=>handleRemove(t.sym)}/>
            ))}
          </tbody>
        </table>
      </div>
      {/* Mobile — card list */}
      <div className="ticker-cards-wrap">
        {tickers.map(t => {
          const verdictColor = {'STRONG BUY':'var(--buy-strong)','BUY':'var(--buy)','NEUTRAL':'var(--neutral)','SELL':'var(--sell)','STRONG SELL':'var(--sell-strong)'}[t.verdict];
          return (
            <div key={t.sym} style={{ padding:'14px 16px', background:'var(--bg-base)', borderRadius:12, border:'1px solid var(--border)' }}>
              <div style={{ display:'flex', alignItems:'center', gap:12, marginBottom:10 }}>
                <div style={{ width:36, height:36, borderRadius:9, background:'linear-gradient(135deg,var(--cyan-soft),var(--violet-soft))', display:'grid', placeItems:'center', fontWeight:800, color:'var(--cyan)', fontSize:14, flexShrink:0 }}>{t.sym[0]}</div>
                <div style={{ flex:1, minWidth:0 }}>
                  <div className="mono" style={{ fontWeight:700, fontSize:14 }}>{t.sym}</div>
                  <div style={{ fontSize:11, color:'var(--ink-3)', overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap' }}>{t.name}</div>
                </div>
                <span style={{ fontSize:11, fontWeight:700, padding:'3px 8px', borderRadius:999, background:`color-mix(in oklab,${verdictColor} 14%,transparent)`, color:verdictColor }}>{t.verdict}</span>
              </div>
              <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', fontSize:13 }}>
                <span className="mono">₹{t.price.toLocaleString('en-IN',{minimumFractionDigits:2})}</span>
                <span style={{ color: t.change >= 0 ? 'var(--buy-strong)' : 'var(--sell-strong)', fontWeight:700 }}>{t.change >= 0 ? '+' : ''}{t.change.toFixed(2)}%</span>
                <div style={{ display:'flex', alignItems:'center', gap:6 }}><ScoreDot v={t.score}/><span className="mono" style={{ fontWeight:700 }}>{t.score.toFixed(2)}</span></div>
                <div style={{ display:'flex', gap:6 }}>
                  <button onClick={()=>onAnalyze(t.sym)} style={{ padding:'6px 12px', border:'none', borderRadius:8, background:'linear-gradient(135deg,var(--cyan),var(--violet))', color:'#fff', fontSize:12, fontWeight:700, cursor:'pointer' }}>Analyze</button>
                  <button onClick={()=>handleRemove(t.sym)} style={{ width:30, height:30, border:'1px solid var(--border)', borderRadius:7, background:'transparent', display:'grid', placeItems:'center', color:'var(--ink-3)', fontSize:14, cursor:'pointer' }}>×</button>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function TrendingPane({ onAnalyze }) {
  const [items, setItems] = useStateHome(null); // null = loading
  const [fetchError, setFetchError] = useStateHome(false);

  useEffectHome(() => {
    fetch('/ui/trending')
      .then(r => r.ok ? r.json() : Promise.reject())
      .then(d => setItems(d.trending || []))
      .catch(() => {
        // fall back to bootstrap window.TRENDING on network error
        setItems(window.TRENDING || []);
        setFetchError(true);
      });
  }, []);

  if (items === null) {
    return (
      <div className="card" style={{ padding:32, display:'flex', alignItems:'center', gap:12, color:'var(--ink-3)' }}>
        <div style={{ width:18, height:18, border:'2px solid var(--cyan)', borderTopColor:'transparent', borderRadius:'50%', animation:'spin-ring 1s linear infinite', flexShrink:0 }}/>
        <span style={{ fontSize:13 }}>Loading score momentum…</span>
      </div>
    );
  }

  if (items.length === 0) {
    return (
      <div className="card" style={{ padding:40, textAlign:'center' }}>
        <div style={{ fontSize:32, marginBottom:12 }}>📊</div>
        <div style={{ fontSize:16, fontWeight:700, color:'var(--ink-1)', marginBottom:8 }}>No trending data yet</div>
        <div style={{ fontSize:13, color:'var(--ink-3)', maxWidth:360, margin:'0 auto 20px', lineHeight:1.6 }}>
          Run your first analysis on any ticker to start seeing which stocks are moving on agent signals.
        </div>
        <button onClick={()=>onAnalyze('MARUTI')} style={{
          padding:'10px 20px', border:'none', borderRadius:10,
          background:'linear-gradient(135deg,var(--cyan),var(--violet))', color:'#fff',
          fontSize:13, fontWeight:700, cursor:'pointer'
        }}>Run analysis on MARUTI</button>
      </div>
    );
  }

  return (
    <div>
      {fetchError && (
        <div style={{ fontSize:11, color:'var(--ink-3)', marginBottom:10, padding:'6px 12px', background:'var(--bg-tinted)', borderRadius:8 }}>
          Using cached data — live trending unavailable
        </div>
      )}
      <div style={{ display:'grid', gridTemplateColumns:'var(--grid-trending)', gap:16 }}>
        {items.map(t => {
          const ticker = window.TICKERS.find(x => x.sym === t.sym);
          const score = t.score ?? ticker?.score ?? 0.5;
          const delta = typeof t.delta === 'number' ? t.delta : parseFloat(t.delta) || 0;
          const isUp = t.direction === 'up' || delta > 0;
          const isDown = t.direction === 'down' || delta < 0;
          const deltaLabel = typeof t.delta === 'number'
            ? `${delta >= 0 ? '+' : ''}${(delta * 100).toFixed(1)} pts`
            : t.delta;

          return (
            <div key={t.sym} className="card" style={{ padding:20 }}>
              <div style={{ display:'flex', alignItems:'flex-start', gap:14 }}>
                <div style={{
                  width:48, height:48, borderRadius:12, flexShrink:0,
                  background:'linear-gradient(135deg, var(--cyan-soft), var(--violet-soft))',
                  display:'grid', placeItems:'center', fontSize:18, fontWeight:800, color:'var(--cyan)'
                }}>{t.sym[0]}</div>
                <div style={{ flex:1, minWidth:0 }}>
                  <div style={{ display:'flex', alignItems:'center', gap:8 }}>
                    <span className="mono" style={{ fontWeight:700 }}>{t.sym}</span>
                    <span style={{ fontSize:11, fontWeight:700,
                      color: isUp ? 'var(--buy-strong)' : isDown ? 'var(--sell-strong)' : 'var(--neutral)' }}>
                      {isUp ? '▲' : isDown ? '▼' : '–'} {deltaLabel}
                    </span>
                  </div>
                  {t.verdict && (
                    <div style={{ fontSize:11, color:'var(--ink-3)', marginTop:2 }}>
                      Verdict: <strong style={{ color:'var(--ink-2)' }}>{t.verdict}</strong>
                      {t.runAt && <span style={{ marginLeft:8 }}>· {new Date(t.runAt).toLocaleDateString('en-IN',{day:'numeric',month:'short'})}</span>}
                    </div>
                  )}
                  <div style={{ fontSize:13, color:'var(--ink-2)', marginTop:6, lineHeight:1.5 }}>{t.why}</div>
                  <div style={{ display:'flex', gap:8, marginTop:10, flexWrap:'wrap' }}>
                    <Pill kind="good">Score {score.toFixed(2)}</Pill>
                    <button onClick={()=>onAnalyze(t.sym)} style={{
                      padding:'3px 10px', border:'1px solid var(--border)', borderRadius:6,
                      background:'var(--bg-surface)', fontSize:11, fontWeight:600, color:'var(--ink-1)', cursor:'pointer'
                    }}>Analyze</button>
                  </div>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

const th = { textAlign:'left', padding:'12px 24px', fontSize:11, fontWeight:600, borderBottom:'1px solid var(--border)' };
const td = { padding:'14px 24px', fontSize:13, borderBottom:'1px solid var(--border)' };

function TickerRow({ t, onAnalyze, onRemove }) {
  const [busy, setBusy] = useStateHome(false);
  const verdictColor = {
    'STRONG BUY':'var(--buy-strong)', 'BUY':'var(--buy)', 'NEUTRAL':'var(--neutral)',
    'SELL':'var(--sell)', 'STRONG SELL':'var(--sell-strong)'
  }[t.verdict];

  const handleAnalyze = () => {
    if (busy) return;
    setBusy(true);
    onAnalyze();
    // reset busy after the outer state has taken over (drawer shows)
    setTimeout(() => setBusy(false), 1500);
  };

  return (
    <tr style={{ transition:'background .15s' }} onMouseEnter={e=>e.currentTarget.style.background='var(--bg-tinted)'} onMouseLeave={e=>e.currentTarget.style.background=''}>
      <td style={td}>
        <div style={{ display:'flex', alignItems:'center', gap:10 }}>
          <div style={{ width:32, height:32, borderRadius:8,
            background:'linear-gradient(135deg, var(--cyan-soft), var(--violet-soft))',
            display:'grid', placeItems:'center', fontWeight:800, color:'var(--cyan)', fontSize:13 }}>{t.sym[0]}</div>
          <div>
            <div className="mono" style={{ fontWeight:700 }}>{t.sym}</div>
            <div style={{ fontSize:11, color:'var(--ink-3)' }}>{t.name}</div>
          </div>
        </div>
      </td>
      <td style={td}><span className="mono">₹{t.price.toLocaleString('en-IN', {minimumFractionDigits:2})}</span></td>
      <td style={{...td, color: t.change >= 0 ? 'var(--buy-strong)' : 'var(--sell-strong)', fontWeight:700 }}>
        {t.change >= 0 ? '+' : ''}{t.change.toFixed(2)}%
      </td>
      <td style={td}>
        <div style={{ display:'flex', alignItems:'center', gap:8 }}>
          <ScoreDot v={t.score}/>
          <span className="mono" style={{ fontWeight:700 }}>{t.score.toFixed(2)}</span>
        </div>
      </td>
      <td style={td}>
        <span style={{ display:'inline-block', padding:'4px 10px', borderRadius:999, fontSize:11, fontWeight:700,
          background:`color-mix(in oklab, ${verdictColor} 14%, transparent)`, color: verdictColor, letterSpacing:'.04em' }}>
          {t.verdict}
        </span>
      </td>
      <td style={{...td, textAlign:'right'}}>
        <div style={{ display:'flex', gap:6, justifyContent:'flex-end' }}>
          <button onClick={handleAnalyze} disabled={busy} style={{
            padding:'6px 14px', border:'none', borderRadius:8,
            background: busy ? 'var(--bg-tinted)' : 'linear-gradient(135deg,var(--cyan),var(--violet))',
            color: busy ? 'var(--ink-3)' : '#fff',
            fontSize:12, fontWeight:700, cursor: busy ? 'default' : 'pointer',
            transition:'all .15s'
          }}>{busy ? '⟳' : 'Analyze'}</button>
          {onRemove && (
            <button onClick={onRemove} title="Remove from watchlist" style={{
              width:28, height:28, border:'1px solid var(--border)', borderRadius:7,
              background:'transparent', display:'grid', placeItems:'center',
              color:'var(--ink-3)', cursor:'pointer', fontSize:14
            }}>×</button>
          )}
        </div>
      </td>
    </tr>
  );
}

function ScoreDot({ v }) {
  const color = v >= 0.75 ? 'var(--buy-strong)' : v >= 0.55 ? 'var(--buy)' : v >= 0.40 ? 'var(--neutral)' : v >= 0.20 ? 'var(--sell)' : 'var(--sell-strong)';
  return <span style={{ width:8, height:8, borderRadius:'50%', background: color, display:'inline-block' }}/>;
}

function PulseDot({ kind='good' }) {
  const c = kind==='good' ? 'var(--buy)' : kind==='bad' ? 'var(--sell)' : 'var(--neutral)';
  return (
    <span style={{ position:'relative', width:10, height:10 }}>
      <span style={{ position:'absolute', inset:0, borderRadius:'50%', background:c }}/>
      <span style={{ position:'absolute', inset:-4, borderRadius:'50%', background:c, opacity:.3, animation:'pulse-soft 2s ease-in-out infinite' }}/>
    </span>
  );
}

function DriverRow({ d, onClick }) {
  const colorMap = { good:'var(--buy)', bad:'var(--sell)', mid:'var(--neutral)' };
  const bgMap    = { good:'var(--buy-soft)', bad:'var(--sell-soft)', mid:'var(--neutral-soft)' };
  return (
    <div onClick={()=>onClick?.(d)} style={{
      padding:'12px 14px', borderRadius:12, background:'var(--bg-base)',
      border:'1px solid var(--border)', display:'grid', gridTemplateColumns:'auto 1fr auto', gap:14, alignItems:'center',
      cursor: onClick ? 'pointer' : 'default', transition:'background .15s',
    }}
      onMouseEnter={e=>{ if(onClick) e.currentTarget.style.background='var(--bg-tinted)'; }}
      onMouseLeave={e=>{ e.currentTarget.style.background='var(--bg-base)'; }}>
      <span style={{
        width:32, height:32, borderRadius:9, background: bgMap[d.kind], color: colorMap[d.kind],
        display:'grid', placeItems:'center'
      }}>
        {d.kind==='good' ? <Icon.Trend size={16}/> : d.kind==='bad' ? <Icon.TrendDown size={16}/> : <Icon.Compass size={16}/>}
      </span>
      <div style={{ minWidth:0 }}>
        <div style={{ fontSize:13, fontWeight:600, color:'var(--ink-1)' }}>{d.label}</div>
        <div style={{ fontSize:12, color:'var(--ink-3)', marginTop:2, display:'flex', alignItems:'center', gap:8, flexWrap:'wrap' }}>
          <span>Affects: <strong style={{ color:'var(--ink-2)' }}>{d.impact}</strong></span>
          <span style={{ color:'var(--border-strong)' }}>·</span>
          <span style={{ display:'flex', gap:4 }}>
            {(d.tickers||[]).slice(0,3).map(t => (
              <span key={t} className="mono" style={{ padding:'1px 6px', borderRadius:4, background:'var(--bg-tinted)', fontSize:10, fontWeight:700, color:'var(--ink-2)' }}>{t}</span>
            ))}
          </span>
        </div>
      </div>
      {onClick && <button onClick={e=>{e.stopPropagation(); onClick(d);}} style={{ background:'transparent', border:'none', color:'var(--ink-3)', padding:6 }}>
        <Icon.ChevronR size={16}/>
      </button>}
    </div>
  );
}

function SectorRow({ s }) {
  const positive = s.pct >= 0;
  const w = Math.min(Math.abs(s.pct) * 50, 100);
  return (
    <div style={{ display:'grid', gridTemplateColumns:'70px 1fr 60px', alignItems:'center', gap:10, fontSize:13 }}>
      <span style={{ color:'var(--ink-2)', fontWeight:600 }}>{s.name}</span>
      <div style={{ display:'flex', justifyContent:'center', height:6, background:'var(--bg-tinted)', borderRadius:999, position:'relative' }}>
        <span style={{
          position:'absolute', left: positive ? '50%' : `calc(50% - ${w/2}%)`,
          top:0, bottom:0, width: w/2 + '%', borderRadius:999,
          background: positive ? 'var(--buy)' : 'var(--sell)'
        }}/>
        <span style={{ position:'absolute', top:-2, bottom:-2, left:'50%', width:1, background:'var(--border-strong)' }}/>
      </div>
      <span className="mono" style={{ fontWeight:700, color: positive ? 'var(--buy-strong)' : 'var(--sell-strong)', textAlign:'right' }}>
        {positive ? '+':''}{s.pct.toFixed(2)}%
      </span>
    </div>
  );
}

function CategoryCard({ c, onClick }) {
  return (
    <button className="card" onClick={onClick} style={{
      padding:18, textAlign:'left', cursor:'pointer', border:'1px solid var(--border)',
      transition:'transform .15s, box-shadow .15s'
    }}
      onMouseEnter={e=>{e.currentTarget.style.transform='translateY(-2px)'; e.currentTarget.style.boxShadow='var(--shadow-md)'}}
      onMouseLeave={e=>{e.currentTarget.style.transform=''; e.currentTarget.style.boxShadow='var(--shadow-sm)'}}>
      <div style={{
        width:40, height:40, borderRadius:10,
        background: `color-mix(in oklab, ${c.color} 12%, transparent)`,
        color: c.color, display:'grid', placeItems:'center', fontSize:20, marginBottom:10
      }}>{c.icon}</div>
      <div style={{ fontSize:13, fontWeight:700, color:'var(--ink-1)' }}>{c.label}</div>
      <div style={{ fontSize:11, color:'var(--ink-3)', marginTop:2 }}>{c.count} stocks</div>
    </button>
  );
}

function SuggestCard({ s, onAnalyze }) {
  const ticker = window.TICKERS.find(x => x.sym === s.sym);
  return (
    <div className="card" style={{ padding:20 }}>
      <div style={{ display:'flex', alignItems:'center', gap:10, marginBottom:10 }}>
        <div style={{ width:36, height:36, borderRadius:9,
          background:'linear-gradient(135deg, var(--cyan-soft), var(--violet-soft))',
          display:'grid', placeItems:'center', fontWeight:800, color:'var(--cyan)' }}>{s.sym[0]}</div>
        <div style={{ flex:1, minWidth:0 }}>
          <div className="mono" style={{ fontWeight:700, fontSize:13 }}>{s.sym}</div>
          <div style={{ fontSize:11, color:'var(--ink-3)' }}>{ticker?.name}</div>
        </div>
        <span style={{ fontSize:11, fontWeight:700, padding:'3px 8px', borderRadius:999,
          background:'var(--cyan-soft)', color:'var(--cyan)' }}>For you</span>
      </div>
      <div style={{ fontSize:13, color:'var(--ink-2)', lineHeight:1.5, marginBottom:14 }}>{s.reason}</div>
      <div style={{ display:'flex', gap:8, alignItems:'center' }}>
        <div style={{ flex:1, padding:10, background:'var(--bg-base)', borderRadius:10, fontSize:11, color:'var(--ink-3)',
          display:'flex', alignItems:'center', gap:6 }}>
          <Icon.Sparkles size={12} c="var(--violet)"/>
          {s.why}
        </div>
        <button onClick={()=>onAnalyze(s.sym)} style={{
          padding:'8px 12px', border:'none', borderRadius:8,
          background:'linear-gradient(135deg,var(--cyan),var(--violet))', color:'#fff',
          fontSize:11, fontWeight:700, cursor:'pointer', flexShrink:0
        }}>Analyze</button>
      </div>
    </div>
  );
}

function Pill({ children, kind='neutral' }) {
  const styles = {
    neutral: { bg:'var(--bg-tinted)', fg:'var(--ink-2)' },
    good:    { bg:'var(--buy-soft)',  fg:'var(--buy-strong)' },
  }[kind];
  return <span style={{ padding:'3px 8px', borderRadius:6, background: styles.bg, color: styles.fg, fontSize:11, fontWeight:600 }}>{children}</span>;
}

function Sparkline({ values, height=60, color='var(--cyan)' }) {
  if (!values || values.length < 2) return null;
  const min = Math.min(...values), max = Math.max(...values);
  const range = max - min || 1;
  const w = 100;
  const pts = values.map((v,i) => `${(i/(values.length-1))*w},${height - ((v - min)/range)*height}`).join(' ');
  const area = `0,${height} ${pts} ${w},${height}`;
  return (
    <svg width="100%" height={height} viewBox={`0 0 ${w} ${height}`} preserveAspectRatio="none">
      <defs><linearGradient id="spark-grad" x1="0" x2="0" y1="0" y2="1">
        <stop offset="0%" stopColor={color} stopOpacity=".25"/>
        <stop offset="100%" stopColor={color} stopOpacity="0"/>
      </linearGradient></defs>
      <polygon points={area} fill="url(#spark-grad)"/>
      <polyline points={pts} fill="none" stroke={color} strokeWidth="1.6" vectorEffect="non-scaling-stroke"/>
    </svg>
  );
}

function RangeTabs({ value, onChange, options=['1W','1M','3M','6M','1Y'] }) {
  return (
    <div style={{
      display:'flex', gap:2, padding:3, background:'var(--bg-tinted)', borderRadius:8
    }}>
      {options.map(o => (
        <button key={o} onClick={()=>onChange(o)} style={{
          padding:'4px 8px', borderRadius:6, border:'none',
          fontSize:11, fontWeight:700, letterSpacing:'.02em',
          fontFamily:'var(--font-mono, ui-monospace, monospace)',
          background: value===o ? 'var(--bg-surface)' : 'transparent',
          color: value===o ? 'var(--ink-1)' : 'var(--ink-3)',
          boxShadow: value===o ? 'var(--shadow-sm)' : 'none',
          cursor:'pointer', transition:'all .15s'
        }}>{o}</button>
      ))}
    </div>
  );
}

// ── Analysis Result Drawer ─────────────────────────────────────────────────
function AnalysisResultDrawer({ state, onClose }) {
  const { ticker, loading, report, error } = state;
  const VERDICT_COLOR = {
    'STRONG BUY': 'var(--buy-strong)', 'BUY': 'var(--buy)',
    'NEUTRAL': 'var(--neutral)', 'SELL': 'var(--sell)', 'STRONG SELL': 'var(--sell-strong)',
  };
  const vColor = report ? (VERDICT_COLOR[report.verdict] || 'var(--neutral)') : 'var(--ink-3)';

  return (
    <>
      <div onClick={onClose} style={{
        position:'fixed', inset:0, background:'rgba(15,23,42,.5)',
        backdropFilter:'blur(6px)', zIndex:60, animation:'fade-in .2s'
      }}/>
      <style>{`
        @keyframes fade-in  { from{opacity:0} to{opacity:1} }
        @keyframes slide-in { from{transform:translateX(100%)} to{transform:translateX(0)} }
        @keyframes spin-ring { to { transform:rotate(360deg) } }
      `}</style>

      <aside className="drawer-panel" style={{ width:600, zIndex:65 }}>
        <div className="drawer-handle"/>
        {/* Header */}
        <div style={{ padding:'20px 24px', borderBottom:'1px solid var(--border)', display:'flex', alignItems:'center', gap:14 }}>
          <div style={{
            width:44, height:44, borderRadius:11,
            background:'linear-gradient(135deg, var(--cyan-soft), var(--violet-soft))',
            display:'grid', placeItems:'center', fontWeight:800, fontSize:18, color:'var(--cyan)', flexShrink:0
          }}>{ticker[0]}</div>
          <div style={{ flex:1, minWidth:0 }}>
            <div className="eyebrow" style={{ marginBottom:2 }}>Analysis result</div>
            <div style={{ fontSize:19, fontWeight:800 }}>{ticker}</div>
          </div>
          {report && (
            <span style={{
              padding:'6px 14px', borderRadius:999, fontSize:12, fontWeight:800, letterSpacing:'.04em',
              background:`color-mix(in oklab, ${vColor} 15%, transparent)`, color:vColor
            }}>{report.verdict}</span>
          )}
          <button onClick={onClose} style={{
            width:32, height:32, borderRadius:8, border:'1px solid var(--border)',
            background:'transparent', display:'grid', placeItems:'center', color:'var(--ink-2)', cursor:'pointer'
          }}><Icon.X size={16}/></button>
        </div>

        {/* Body */}
        <div style={{ flex:1, overflowY:'auto', padding:24, display:'flex', flexDirection:'column', gap:24 }}>

          {/* ── Loading state — live WebSocket progress ── */}
          {loading && (
            <div style={{ display:'flex', flexDirection:'column', alignItems:'center', gap:20, paddingTop:40 }}>
              <Sphere size={100} mode="liquid"/>
              <div>
                <div style={{ fontSize:17, fontWeight:700, textAlign:'center', marginBottom:6 }}>Analyzing {ticker}…</div>
                <div style={{ fontSize:13, color:'var(--ink-3)', textAlign:'center' }}>
                  {Object.keys(state.agentProgress || {}).length > 0
                    ? `${Object.keys(state.agentProgress).length} / ${(window.AGENTS||[]).length} agents complete`
                    : '9 agents running concurrently · typically 1–2 min'}
                </div>
              </div>
              <div style={{ width:'100%' }}>
                {(window.AGENTS||[]).map((a,i) => {
                  const score = (state.agentProgress || {})[a.key];
                  const done  = score !== undefined;
                  const barColor = done
                    ? (score >= 0.70 ? 'var(--buy)' : score >= 0.50 ? 'var(--neutral)' : 'var(--sell)')
                    : 'var(--cyan)';
                  return (
                    <div key={a.key} style={{ display:'flex', alignItems:'center', gap:10, marginBottom:10 }}>
                      <span style={{ fontSize:18, width:24, textAlign:'center', flexShrink:0 }}>{a.icon}</span>
                      <div style={{ flex:1, height:6, background:'var(--bg-tinted)', borderRadius:999, overflow:'hidden', position:'relative' }}>
                        {done ? (
                          <div style={{ width:(score*100)+'%', height:'100%', background:barColor, borderRadius:999, transition:'width .5s ease' }}/>
                        ) : (
                          <div style={{
                            position:'absolute', inset:0,
                            background:`linear-gradient(90deg, transparent, ${barColor}, transparent)`,
                            backgroundSize:'200% 100%',
                            animation:`shimmer-move 1.6s ease-in-out infinite ${i*.12}s`
                          }}/>
                        )}
                      </div>
                      <span className="mono" style={{ fontSize:11, width:34, textAlign:'right', flexShrink:0,
                        color: done ? 'var(--ink-1)' : 'var(--ink-3)', fontWeight: done ? 700 : 400 }}>
                        {done ? (score*100).toFixed(0) : '…'}
                      </span>
                      <span style={{ fontSize:11, color:'var(--ink-3)', width:110, flexShrink:0, overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap' }}>
                        {done ? '✓ ' : ''}{a.name}
                      </span>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* ── Error state ── */}
          {error && !loading && (
            <div style={{ padding:20, background:'var(--sell-soft)', borderRadius:12, border:'1px solid var(--sell)' }}>
              <div style={{ fontSize:14, fontWeight:700, color:'var(--sell-strong)', marginBottom:6 }}>Analysis failed</div>
              <div style={{ fontSize:13, color:'var(--sell)', lineHeight:1.5 }}>{error}</div>
              <div style={{ fontSize:11, color:'var(--ink-3)', marginTop:10 }}>Check /docs to test the API directly, or verify your API keys in Railway Variables.</div>
            </div>
          )}

          {/* ── Success state ── */}
          {report && !loading && (
            <>
              {/* Executive summary — plain English for beginners */}
              {report.executive_summary && (
                <div style={{
                  padding:'14px 16px', background:'var(--bg-tinted)', borderRadius:12,
                  border:'1px solid var(--border)', fontSize:14, color:'var(--ink-1)', lineHeight:1.65,
                  fontWeight:500
                }}>
                  {report.executive_summary}
                </div>
              )}

              {/* Score + verdict card */}
              <div style={{
                display:'flex', gap:20, alignItems:'center', padding:20,
                background:'var(--bg-base)', borderRadius:16, border:'1px solid var(--border)'
              }}>
                {/* Conic gauge */}
                <div style={{ flexShrink:0, textAlign:'center' }}>
                  <div style={{
                    width:84, height:84, borderRadius:'50%', margin:'0 auto 8px',
                    background:`conic-gradient(${vColor} ${report.final_score*360}deg, var(--bg-tinted) 0deg)`,
                    display:'grid', placeItems:'center',
                    boxShadow:`0 0 0 4px var(--bg-surface), 0 4px 20px rgba(0,0,0,.08)`
                  }}>
                    <div style={{
                      width:62, height:62, borderRadius:'50%', background:'var(--bg-surface)',
                      display:'grid', placeItems:'center', fontWeight:800, fontSize:18,
                      fontFamily:'var(--font-mono,ui-monospace,monospace)', color:'var(--ink-1)'
                    }}>{(report.final_score*100).toFixed(0)}</div>
                  </div>
                  <div style={{ fontSize:10, color:'var(--ink-3)' }}>/ 100</div>
                </div>
                <div style={{ flex:1, minWidth:0 }}>
                  <div style={{ fontSize:13, color:'var(--ink-2)', marginBottom:4 }}>{report.company_name}</div>
                  <div style={{ fontSize:15, fontWeight:700, color: vColor, marginBottom:8 }}>{report.verdict}</div>
                  {report.price_target && (
                    <div style={{ display:'flex', gap:12, fontSize:12, flexWrap:'wrap' }}>
                      <span style={{ color:'var(--ink-3)' }}>Target: <strong style={{ color:'var(--ink-1)' }}>₹{report.price_target.toLocaleString('en-IN')}</strong></span>
                      {report.undervalued_by_pct != null && (
                        <span style={{ color:'var(--buy-strong)' }}>Upside {report.undervalued_by_pct.toFixed(1)}%</span>
                      )}
                      {report.recovery_timeline_quarters && (
                        <span style={{ color:'var(--ink-3)' }}>{report.recovery_timeline_quarters}Q horizon</span>
                      )}
                    </div>
                  )}
                </div>
              </div>

              {/* Thesis */}
              {report.investment_thesis && (
                <div>
                  <div className="eyebrow" style={{ marginBottom:8 }}>Investment thesis</div>
                  <p style={{ fontSize:13, color:'var(--ink-2)', lineHeight:1.7, margin:0,
                    padding:'14px 16px', background:'var(--bg-base)', borderRadius:12, border:'1px solid var(--border)' }}>
                    {report.investment_thesis}
                  </p>
                </div>
              )}

              {/* Conviction drivers + top risks */}
              <div className="analysis-2col" style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:16 }}>
                <div>
                  <div className="eyebrow" style={{ marginBottom:8, color:'var(--buy-strong)' }}>Conviction drivers</div>
                  <div style={{ display:'flex', flexDirection:'column', gap:6 }}>
                    {(report.conviction_drivers||[]).slice(0,4).map((d,i) => (
                      <div key={i} style={{ display:'flex', gap:8, alignItems:'flex-start',
                        padding:'8px 10px', background:'var(--buy-soft)', borderRadius:8 }}>
                        <span style={{ color:'var(--buy-strong)', fontSize:12, marginTop:1, flexShrink:0 }}>✓</span>
                        <span style={{ fontSize:12, color:'var(--ink-1)', lineHeight:1.5 }}>{d}</span>
                      </div>
                    ))}
                    {!report.conviction_drivers?.length && (
                      <div style={{ fontSize:12, color:'var(--ink-3)' }}>None flagged</div>
                    )}
                  </div>
                </div>
                <div>
                  <div className="eyebrow" style={{ marginBottom:8, color:'var(--sell-strong)' }}>Top risks</div>
                  <div style={{ display:'flex', flexDirection:'column', gap:6 }}>
                    {(report.top_risks||[]).slice(0,4).map((r,i) => (
                      <div key={i} style={{ display:'flex', gap:8, alignItems:'flex-start',
                        padding:'8px 10px', background:'var(--sell-soft)', borderRadius:8 }}>
                        <span style={{ color:'var(--sell-strong)', fontSize:12, marginTop:1, flexShrink:0 }}>⚠</span>
                        <span style={{ fontSize:12, color:'var(--ink-1)', lineHeight:1.5 }}>{r}</span>
                      </div>
                    ))}
                    {!report.top_risks?.length && (
                      <div style={{ fontSize:12, color:'var(--ink-3)' }}>None flagged</div>
                    )}
                  </div>
                </div>
              </div>

              {/* Agent score bars */}
              {report.weighted_agent_scores && Object.keys(report.weighted_agent_scores).length > 0 && (
                <div>
                  <div className="eyebrow" style={{ marginBottom:12 }}>Agent breakdown</div>
                  <div style={{ display:'flex', flexDirection:'column', gap:10 }}>
                    {Object.entries(report.weighted_agent_scores).map(([key, val]) => {
                      const meta = (window.AGENTS||[]).find(a => a.key === key);
                      const score = typeof val === 'object' ? (val.raw || 0) : (val || 0);
                      const color = score >= 0.70 ? 'var(--buy)' : score >= 0.50 ? 'var(--neutral)' : 'var(--sell)';
                      return (
                        <div key={key} style={{ display:'grid', gridTemplateColumns:'28px 1fr 40px', gap:10, alignItems:'center' }}>
                          <span style={{ fontSize:17, textAlign:'center' }}>{meta?.icon || '•'}</span>
                          <div style={{ height:7, background:'var(--bg-tinted)', borderRadius:999, overflow:'hidden' }}>
                            <div style={{ width:(score*100)+'%', height:'100%', background:color, borderRadius:999, transition:'width .8s ease' }}/>
                          </div>
                          <span className="mono" style={{ fontSize:12, fontWeight:700, color:'var(--ink-2)', textAlign:'right' }}>
                            {(score*100).toFixed(0)}
                          </span>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}

              {/* Conflicts */}
              {report.conflicts_resolved?.length > 0 && (
                <div>
                  <div className="eyebrow" style={{ marginBottom:8 }}>Conflicts resolved</div>
                  <div style={{ display:'flex', flexDirection:'column', gap:4 }}>
                    {report.conflicts_resolved.map((c,i) => (
                      <div key={i} style={{ fontSize:12, color:'var(--ink-2)', padding:'6px 10px',
                        background:'var(--neutral-soft)', borderRadius:8, lineHeight:1.5 }}>⟷ {c}</div>
                    ))}
                  </div>
                </div>
              )}
            </>
          )}
        </div>

        {/* Footer shimmer animation style */}
        <style>{`
          @keyframes shimmer-move {
            0%   { background-position: -200% 0; }
            100% { background-position:  200% 0; }
          }
        `}</style>
      </aside>
    </>
  );
}

// ── Driver Detail Panel ────────────────────────────────────────────────────
function DriverDetailPanel({ driver: d, onClose, onAnalyze }) {
  const colorMap = { good:'var(--buy)', bad:'var(--sell)', mid:'var(--neutral)' };
  const bgMap    = { good:'var(--buy-soft)', bad:'var(--sell-soft)', mid:'var(--neutral-soft)' };
  const affected = (d.tickers || []).map(sym => window.TICKERS.find(t => t.sym === sym)).filter(Boolean);

  return (
    <>
      <div onClick={onClose} style={{ position:'fixed', inset:0, background:'rgba(15,23,42,.45)', backdropFilter:'blur(4px)', zIndex:60, animation:'fade-in .2s' }}/>
      <aside className="drawer-panel" style={{ width:420, zIndex:65 }}>
        <div className="drawer-handle"/>
        <div style={{ padding:'20px 24px', borderBottom:'1px solid var(--border)', display:'flex', alignItems:'center', gap:14 }}>
          <span style={{ width:40, height:40, borderRadius:10, background: bgMap[d.kind], color: colorMap[d.kind], display:'grid', placeItems:'center', flexShrink:0 }}>
            {d.kind==='good' ? <Icon.Trend size={18}/> : d.kind==='bad' ? <Icon.TrendDown size={18}/> : <Icon.Compass size={18}/>}
          </span>
          <div style={{ flex:1, minWidth:0 }}>
            <div className="eyebrow" style={{ marginBottom:2 }}>Market driver</div>
            <div style={{ fontSize:15, fontWeight:700, lineHeight:1.3 }}>{d.label}</div>
          </div>
          <button onClick={onClose} style={{ width:32, height:32, borderRadius:8, border:'1px solid var(--border)', background:'transparent', display:'grid', placeItems:'center', color:'var(--ink-2)', cursor:'pointer' }}><Icon.X size={16}/></button>
        </div>
        <div style={{ flex:1, overflowY:'auto', padding:24, display:'flex', flexDirection:'column', gap:20 }}>
          <div style={{ padding:'12px 14px', background: bgMap[d.kind], borderRadius:10, fontSize:13, color:'var(--ink-1)', lineHeight:1.6 }}>
            <strong>Affects:</strong> {d.impact}
          </div>

          {affected.length > 0 ? (
            <div>
              <div className="eyebrow" style={{ marginBottom:12 }}>Stocks in this move</div>
              <div style={{ display:'flex', flexDirection:'column', gap:10 }}>
                {affected.map(t => {
                  const verdictColor = {'STRONG BUY':'var(--buy-strong)','BUY':'var(--buy)','NEUTRAL':'var(--neutral)','SELL':'var(--sell)','STRONG SELL':'var(--sell-strong)'}[t.verdict] || 'var(--neutral)';
                  return (
                    <div key={t.sym} style={{ padding:'14px 16px', borderRadius:12, border:'1px solid var(--border)', background:'var(--bg-base)', display:'flex', alignItems:'center', gap:12 }}>
                      <div style={{ width:36, height:36, borderRadius:9, background:'linear-gradient(135deg,var(--cyan-soft),var(--violet-soft))', display:'grid', placeItems:'center', fontWeight:800, color:'var(--cyan)', fontSize:13, flexShrink:0 }}>{t.sym[0]}</div>
                      <div style={{ flex:1, minWidth:0 }}>
                        <div style={{ display:'flex', alignItems:'center', gap:8 }}>
                          <span className="mono" style={{ fontWeight:700, fontSize:13 }}>{t.sym}</span>
                          <span style={{ fontSize:11, padding:'2px 7px', borderRadius:999, background:`color-mix(in oklab,${verdictColor} 14%,transparent)`, color:verdictColor, fontWeight:700 }}>{t.verdict}</span>
                        </div>
                        <div style={{ fontSize:12, color:'var(--ink-3)', marginTop:2 }}>Score {t.score.toFixed(2)} · ₹{t.price.toLocaleString('en-IN',{minimumFractionDigits:2})}</div>
                      </div>
                      <button onClick={()=>{onClose(); onAnalyze(t.sym);}} style={{ padding:'6px 12px', border:'none', borderRadius:8, background:'linear-gradient(135deg,var(--cyan),var(--violet))', color:'#fff', fontSize:11, fontWeight:700, cursor:'pointer', flexShrink:0 }}>Analyze</button>
                    </div>
                  );
                })}
              </div>
            </div>
          ) : (
            <div style={{ fontSize:13, color:'var(--ink-3)', textAlign:'center', padding:20 }}>
              Run analyses on affected tickers to see their scores here.
            </div>
          )}
        </div>
      </aside>
    </>
  );
}

// ── Category Drawer ────────────────────────────────────────────────────────
function CategoryDrawer({ category: initialCat, onClose, onAnalyze }) {
  const [cat, setCat] = useStateHome(initialCat);
  const [editOpen, setEditOpen] = useStateHome(false);
  const [addVal, setAddVal] = useStateHome('');
  const [editBusy, setEditBusy] = useStateHome(false);
  const [editError, setEditError] = useStateHome('');

  const tickers = (cat.tickers || []).map(sym => {
    const t = window.TICKERS.find(x => x.sym === sym);
    return t || { sym, name: sym, price: 0, change: 0, score: 0.5, verdict: 'NEUTRAL', hasData: false };
  });

  const mutate = async (add = [], remove = []) => {
    setEditBusy(true); setEditError('');
    try {
      const res = await fetch(`/ui/categories/${cat.key}/tickers`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ add, remove }),
      });
      const d = await res.json();
      if (!res.ok) { setEditError(d.detail || 'Server error'); }
      else {
        if (d.invalid_syms?.length) setEditError(`Not in supported list: ${d.invalid_syms.join(', ')}`);
        if (d.category) {
          setCat(d.category);
          // reflect in window.CATEGORIES so other parts of the UI stay in sync
          window.CATEGORIES = window.CATEGORIES.map(c => c.key === cat.key ? d.category : c);
        }
        setAddVal('');
      }
    } catch { setEditError('Network error'); }
    setEditBusy(false);
  };

  return (
    <>
      <div onClick={onClose} style={{ position:'fixed', inset:0, background:'rgba(15,23,42,.45)', backdropFilter:'blur(4px)', zIndex:60, animation:'fade-in .2s' }}/>
      <aside className="drawer-panel" style={{ width:460, zIndex:65 }}>
        <div className="drawer-handle"/>
        <div style={{ padding:'20px 24px', borderBottom:'1px solid var(--border)', display:'flex', alignItems:'center', gap:14 }}>
          <div style={{ width:44, height:44, borderRadius:11, background:`color-mix(in oklab,${cat.color} 12%,transparent)`, color:cat.color, display:'grid', placeItems:'center', fontSize:22, flexShrink:0 }}>{cat.icon}</div>
          <div style={{ flex:1 }}>
            <div className="eyebrow" style={{ marginBottom:2 }}>Category · {tickers.length} stocks</div>
            <div style={{ fontSize:17, fontWeight:800 }}>{cat.label}</div>
          </div>
          <button onClick={()=>setEditOpen(o=>!o)} style={{
            padding:'6px 12px', border:'1px dashed var(--border-strong)', borderRadius:8,
            background:'transparent', fontSize:11, fontWeight:600, color:'var(--ink-2)', cursor:'pointer'
          }}>{editOpen ? 'Done' : 'Edit list'}</button>
          <button onClick={onClose} style={{ width:32, height:32, borderRadius:8, border:'1px solid var(--border)', background:'transparent', display:'grid', placeItems:'center', color:'var(--ink-2)', cursor:'pointer' }}><Icon.X size={16}/></button>
        </div>

        {/* Inline add-ticker form */}
        {editOpen && (
          <div style={{ padding:'12px 24px', borderBottom:'1px solid var(--border)', background:'var(--bg-base)', display:'flex', gap:8, flexWrap:'wrap', alignItems:'center' }}>
            <input value={addVal} onChange={e=>{setAddVal(e.target.value.toUpperCase()); setEditError('');}}
              onKeyDown={e=>e.key==='Enter' && mutate([addVal.trim()], [])}
              placeholder="Add ticker e.g. ESCORTS" style={{
                padding:'7px 11px', border:'1px solid var(--border)', borderRadius:8,
                fontSize:12, background:'var(--bg-surface)', outline:'none', minWidth:160
              }}/>
            <button onClick={()=>mutate([addVal.trim()], [])} disabled={editBusy || !addVal.trim()} style={{
              padding:'7px 12px', border:'none', borderRadius:8, background:'var(--cyan)',
              color:'#fff', fontSize:11, fontWeight:700, cursor:'pointer'
            }}>{editBusy ? '…' : 'Add'}</button>
            {editError && <span style={{ fontSize:11, color:'var(--sell-strong)' }}>{editError}</span>}
            <span style={{ fontSize:10, color:'var(--ink-3)', marginLeft:'auto' }}>Supported tickers only</span>
          </div>
        )}

        <div style={{ flex:1, overflowY:'auto', padding:24, display:'flex', flexDirection:'column', gap:10 }}>
          {tickers.map(t => {
            const verdictColor = {'STRONG BUY':'var(--buy-strong)','BUY':'var(--buy)','NEUTRAL':'var(--neutral)','SELL':'var(--sell)','STRONG SELL':'var(--sell-strong)'}[t.verdict] || 'var(--neutral)';
            return (
              <div key={t.sym} style={{ padding:'14px 16px', borderRadius:12, border:'1px solid var(--border)', background:'var(--bg-base)', display:'flex', alignItems:'center', gap:12 }}>
                <div style={{ width:38, height:38, borderRadius:9, background:'linear-gradient(135deg,var(--cyan-soft),var(--violet-soft))', display:'grid', placeItems:'center', fontWeight:800, color:'var(--cyan)', fontSize:14, flexShrink:0 }}>{t.sym[0]}</div>
                <div style={{ flex:1, minWidth:0 }}>
                  <div style={{ display:'flex', alignItems:'center', gap:8 }}>
                    <span className="mono" style={{ fontWeight:700, fontSize:13 }}>{t.sym}</span>
                    {t.hasData !== false ? (
                      <span style={{ fontSize:11, padding:'2px 7px', borderRadius:999, background:`color-mix(in oklab,${verdictColor} 14%,transparent)`, color:verdictColor, fontWeight:700 }}>{t.verdict}</span>
                    ) : (
                      <span style={{ fontSize:10, padding:'2px 7px', borderRadius:999, background:'var(--bg-tinted)', color:'var(--ink-3)', fontWeight:600 }}>Not analyzed</span>
                    )}
                  </div>
                  <div style={{ fontSize:12, color:'var(--ink-3)', marginTop:2 }}>
                    {t.hasData !== false ? `Score ${t.score.toFixed(2)} · ₹${t.price.toLocaleString('en-IN',{minimumFractionDigits:2})}` : t.name}
                  </div>
                </div>
                <div style={{ display:'flex', gap:6, flexShrink:0 }}>
                  <button onClick={()=>{onClose(); onAnalyze(t.sym);}} style={{ padding:'6px 12px', border:'none', borderRadius:8, background:'linear-gradient(135deg,var(--cyan),var(--violet))', color:'#fff', fontSize:11, fontWeight:700, cursor:'pointer' }}>Analyze</button>
                  {editOpen && (
                    <button onClick={()=>mutate([], [t.sym])} disabled={editBusy} title="Remove from category" style={{ width:28, height:28, border:'1px solid var(--border)', borderRadius:7, background:'transparent', display:'grid', placeItems:'center', color:'var(--ink-3)', cursor:'pointer', fontSize:14 }}>×</button>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </aside>
    </>
  );
}

window.Home = Home;
window.TopNav = TopNav;
window.RangeTabs = RangeTabs;
window.Sparkline = Sparkline;
