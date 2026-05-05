// AppShell — MarketBar (top strip), Sidebar (left), and page frame.

const MarketBar = () => {
  const { marketIndices } = window.StockData;
  // Duplicate for infinite scroll feel
  const loop = [...marketIndices, ...marketIndices];
  return (
    <div className="w-full h-9 border-b border-[rgba(30,41,59,0.8)] bg-[rgba(5,8,16,0.95)] overflow-hidden relative"
         style={{ backdropFilter: 'blur(10px)' }}>
      <div className="flex items-center h-full gap-8 px-4 whitespace-nowrap animate-marquee">
        {loop.map((m, i) => (
          <div key={i} className="flex items-center gap-2 shrink-0">
            <span className="text-[10px] font-bold tracking-wider text-text-muted uppercase">{m.name}</span>
            <span className="font-mono text-[12px] text-text-primary tabular-nums">{m.value.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
            <span className={`font-mono text-[11px] tabular-nums flex items-center gap-0.5 ${m.change >= 0 ? 'text-buy' : 'text-sell'}`}>
              {m.change >= 0 ? <IconTrendUp size={10}/> : <IconTrendDn size={10}/>}
              {m.change >= 0 ? '+' : ''}{m.change.toFixed(2)}%
            </span>
          </div>
        ))}
      </div>
      <style>{`
        @keyframes marquee { 0% { transform: translateX(0); } 100% { transform: translateX(-50%); } }
        .animate-marquee { animation: marquee 60s linear infinite; }
      `}</style>
    </div>
  );
};

const SidebarItem = ({ icon, label, active, badge }) => (
  <button
    className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-left transition-all duration-200
      ${active
        ? 'bg-[rgba(6,182,212,0.12)] text-accent-cyan border border-[rgba(6,182,212,0.3)]'
        : 'text-text-secondary hover:text-text-primary hover:bg-[rgba(255,255,255,0.03)] border border-transparent'}`}
  >
    <span className={active ? '' : 'text-text-muted'}>{icon}</span>
    <span className="text-[13px] font-semibold flex-1">{label}</span>
    {badge && <span className="font-mono text-[10px] text-text-muted">{badge}</span>}
  </button>
);

const Sidebar = ({ current = 'analyze' }) => (
  <aside className="hidden lg:flex w-[220px] shrink-0 flex-col border-r border-[rgba(30,41,59,0.8)] bg-[rgba(5,8,16,0.85)] py-5 px-3 gap-6"
         style={{ backdropFilter: 'blur(10px)' }}>
    {/* Brand */}
    <div className="flex items-center gap-2.5 px-3">
      <div className="w-7 h-7 rounded-lg flex items-center justify-center"
           style={{ background: 'linear-gradient(135deg, #06b6d4, #3b82f6)', boxShadow: '0 0 12px rgba(6,182,212,0.4)' }}>
        <IconActivity size={15} stroke="#050810" strokeWidth="2.5"/>
      </div>
      <div>
        <div className="text-[14px] font-extrabold text-text-primary leading-none tracking-tight">StockAgent</div>
        <div className="text-[9px] font-mono text-text-muted mt-0.5 leading-none">v0.9 · beta</div>
      </div>
    </div>

    <nav className="flex flex-col gap-1">
      <div className="text-[9px] font-bold tracking-[0.15em] text-text-muted uppercase px-3 mb-1">Workspace</div>
      <SidebarItem icon={<IconHome     size={16}/>} label="Dashboard" active={current === 'dashboard'}/>
      <SidebarItem icon={<IconActivity size={16}/>} label="Analyze"   active={current === 'analyze'} badge="●"/>
      <SidebarItem icon={<IconBookmark size={16}/>} label="Watchlist" active={current === 'watch'} badge="5"/>
      <SidebarItem icon={<IconHistory  size={16}/>} label="History"   active={current === 'history'}/>
    </nav>

    <nav className="flex flex-col gap-1">
      <div className="text-[9px] font-bold tracking-[0.15em] text-text-muted uppercase px-3 mb-1">Sectors</div>
      <SidebarItem icon={<span className="text-sm">🚗</span>} label="Automobile" active badge="Live"/>
      <SidebarItem icon={<span className="text-sm">🏦</span>} label="Banking"      badge="soon"/>
      <SidebarItem icon={<span className="text-sm">💻</span>} label="IT"           badge="soon"/>
      <SidebarItem icon={<span className="text-sm">☀️</span>} label="Renewable"    badge="soon"/>
    </nav>

    <div className="mt-auto">
      <SidebarItem icon={<IconSettings size={16}/>} label="Settings"/>
      <div className="mt-3 px-3 flex items-center gap-2.5">
        <div className="w-7 h-7 rounded-full flex items-center justify-center text-[11px] font-bold"
             style={{ background: 'linear-gradient(135deg, #3b82f6, #8b5cf6)' }}>RP</div>
        <div className="min-w-0">
          <div className="text-[12px] font-semibold text-text-primary truncate">Revan P.</div>
          <div className="text-[10px] text-text-muted truncate">analyst · local</div>
        </div>
      </div>
    </div>
  </aside>
);

const Ticker = ({ children }) => <span className="font-mono font-bold tracking-wide">{children}</span>;

const TickerSearch = ({ value, onChange, onSubmit, running }) => {
  const { TICKER_NAMES } = window.StockData;
  return (
    <GlassCard className="!p-0 overflow-hidden">
      <div className="flex items-center gap-3 px-4 py-3.5 border-b border-[rgba(30,41,59,0.8)]">
        <IconSearch size={18} stroke="#94a3b8"/>
        <input
          value={value}
          onChange={e => onChange(e.target.value.toUpperCase())}
          onKeyDown={e => e.key === 'Enter' && onSubmit()}
          placeholder="Enter ticker — e.g. MARUTI, TATAMOTORS, M&M"
          className="flex-1 bg-transparent outline-none text-text-primary placeholder:text-text-muted font-mono text-[16px] font-semibold tracking-wide"
          disabled={running}
        />
        <kbd className="hidden md:inline-block font-mono text-[10px] text-text-muted bg-[rgba(255,255,255,0.04)] border border-[rgba(30,41,59,0.8)] rounded px-1.5 py-0.5">⏎</kbd>
        <GlowButton variant="cyan" size="sm" onClick={onSubmit} disabled={running || !value}>
          {running ? 'Running…' : 'Run agents'}
        </GlowButton>
      </div>
      <div className="flex items-center gap-2 px-4 py-2.5 flex-wrap">
        <span className="text-[10px] font-bold tracking-wider text-text-muted uppercase">Quick:</span>
        {Object.keys(TICKER_NAMES).slice(0, 6).map(t => (
          <button key={t}
            onClick={() => { onChange(t); }}
            className="font-mono text-[11px] font-semibold text-text-secondary hover:text-accent-cyan px-2 py-1 rounded-md hover:bg-[rgba(6,182,212,0.08)] transition-colors border border-transparent hover:border-[rgba(6,182,212,0.25)]"
          >{t}</button>
        ))}
        <span className="ml-auto text-[10px] font-mono text-text-muted">NSE auto universe · 10 tickers</span>
      </div>
    </GlassCard>
  );
};

Object.assign(window, { MarketBar, Sidebar, SidebarItem, Ticker, TickerSearch });
