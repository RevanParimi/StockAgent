// App — wires the whole Analyze page together with a simulated WebSocket stream.

const { sampleReport, sampleHistory, AGENT_KEYS, AGENT_LABELS, AGENT_ICONS, TICKER_NAMES } = window.StockData;

function useSimStream() {
  const [ticker, setTicker] = useState('MARUTI');
  const [input, setInput] = useState('MARUTI');
  const [phase, setPhase] = useState('idle'); // idle | running | done
  const [elapsed, setElapsed] = useState(0);
  const [states, setStates] = useState(() => Object.fromEntries(AGENT_KEYS.map(k => [k, 'pending'])));
  const [current, setCurrent] = useState(null);
  const timers = useRef([]);

  // Start in "done" state showing the sample report, so the UI-kit page
  // looks fully populated on first load.
  const [report, setReport] = useState(sampleReport);

  useEffect(() => {
    // On mount: pretend we just finished.
    setPhase('done');
    setStates(Object.fromEntries(AGENT_KEYS.map(k => [k, 'complete'])));
    setElapsed(sampleReport.elapsed_seconds);
  }, []);

  const reset = useCallback(() => {
    timers.current.forEach(clearTimeout);
    timers.current = [];
    setStates(Object.fromEntries(AGENT_KEYS.map(k => [k, 'pending'])));
    setElapsed(0);
    setCurrent(null);
  }, []);

  const run = useCallback((targetTicker) => {
    const t = (targetTicker || input || 'MARUTI').toUpperCase();
    setTicker(t);
    setInput(t);
    reset();
    setPhase('running');

    // simulate agents completing at staggered intervals
    const interval = 800; // ms per agent
    AGENT_KEYS.forEach((k, i) => {
      // mark as running ~200ms before complete
      timers.current.push(setTimeout(() => {
        setStates(s => ({ ...s, [k]: 'analyzing' }));
        setCurrent(k);
      }, i * interval));
      timers.current.push(setTimeout(() => {
        setStates(s => ({ ...s, [k]: 'complete' }));
      }, i * interval + interval - 80));
    });
    // Elapsed counter
    const t0 = Date.now();
    const tick = setInterval(() => {
      setElapsed(Math.floor((Date.now() - t0) / 1000));
    }, 500);
    timers.current.push({ type: 'interval', handle: tick });

    // Finish
    timers.current.push(setTimeout(() => {
      clearInterval(tick);
      setPhase('done');
      setCurrent(null);
      // Randomize the report slightly for the new ticker
      setReport({
        ...sampleReport,
        ticker: t,
        company_name: TICKER_NAMES[t] || sampleReport.company_name,
        elapsed_seconds: Math.max(8, Math.floor((Date.now() - t0) / 1000)),
        report_date: new Date().toISOString().split('T')[0],
      });
    }, AGENT_KEYS.length * interval + 400));
  }, [input, reset]);

  const completeCount = Object.values(states).filter(s => s === 'complete').length;

  return { ticker, input, setInput, phase, run, states, current, elapsed, completeCount, report };
}

const App = () => {
  const sim = useSimStream();
  const { report } = sim;

  return (
    <div className="min-h-screen flex flex-col" style={{ background: '#050810' }}>
      <MarketBar/>
      <div className="flex flex-1">
        <Sidebar current="analyze"/>

        <main className="flex-1 min-w-0 overflow-x-hidden">
          <div className="max-w-[1120px] mx-auto px-5 md:px-8 py-8">

            {/* Page header */}
            <div className="flex items-end justify-between gap-4 mb-6 flex-wrap">
              <div>
                <div className="flex items-center gap-2 mb-1.5">
                  <span className="text-[10px] font-bold tracking-[0.2em] text-accent-cyan uppercase">Analyze</span>
                  <span className="text-text-muted">·</span>
                  <span className="text-[10px] font-bold tracking-[0.2em] text-text-muted uppercase">Automobile sector</span>
                </div>
                <h1 className="text-[28px] md:text-[34px] font-extrabold text-text-primary leading-tight tracking-tight">
                  Ask 8 specialists. Get one verdict.
                </h1>
                <p className="text-[13px] text-text-secondary mt-1 max-w-xl">
                  Enter an NSE ticker. Every agent runs in parallel against live data, then the Signal Aggregator weights their scores into a composite conviction read.
                </p>
              </div>
              <div className="text-right">
                <div className="text-[10px] font-bold tracking-[0.15em] text-text-muted uppercase">Connection</div>
                <div className="flex items-center gap-1.5 justify-end mt-1">
                  <span className="w-2 h-2 rounded-full bg-buy-strong pulse-ring"/>
                  <span className="font-mono text-[12px] text-text-primary">ws://localhost:8000</span>
                </div>
                <div className="font-mono text-[10px] text-text-muted mt-0.5">/ws/stream · demo mode</div>
              </div>
            </div>

            {/* Search */}
            <div className="mb-4">
              <TickerSearch
                value={sim.input}
                onChange={sim.setInput}
                onSubmit={() => sim.run()}
                running={sim.phase === 'running'}
              />
            </div>

            {/* Stream progress */}
            <div className="mb-4">
              <StreamProgress
                total={8}
                complete={sim.completeCount}
                elapsed={sim.elapsed}
                running={sim.phase === 'running'}
                currentAgent={sim.current}
              />
            </div>

            {/* Agent grid */}
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 mb-8">
              {AGENT_KEYS.map(k => (
                <AgentCard
                  key={k}
                  agentKey={k}
                  label={AGENT_LABELS[k]}
                  icon={AGENT_ICONS[k]}
                  state={sim.states[k]}
                  score={report.weighted_agent_scores[k]?.raw ?? 0}
                  weight={report.weighted_agent_scores[k]?.weight ?? 0}
                />
              ))}
            </div>

            {/* Verdict reveal — only after done */}
            {sim.phase === 'done' && (
              <div className="mb-8">
                <VerdictReveal
                  ticker={report.ticker}
                  companyName={report.company_name}
                  score={report.final_score}
                  reportDate={report.report_date}
                  elapsedSeconds={report.elapsed_seconds}
                  agentsCount={8}
                  conflicts={report.conflicts_resolved.length}
                />
              </div>
            )}

            {/* Radar + table */}
            {sim.phase === 'done' && (
              <div className="grid grid-cols-1 lg:grid-cols-[1fr_1.1fr] gap-4 mb-8">
                <AgentRadar scores={report.weighted_agent_scores}/>
                <ScoreTable scores={report.weighted_agent_scores}/>
              </div>
            )}

            {/* Conviction + thesis */}
            {sim.phase === 'done' && (
              <div className="grid grid-cols-1 gap-4 mb-8">
                <ConvictionPanel
                  drivers={report.conviction_drivers}
                  risks={report.top_risks}
                  conflicts={report.conflicts_resolved}
                />
                <ThesisCard ticker={report.ticker} thesis={report.investment_thesis}/>
              </div>
            )}

            {/* History */}
            {sim.phase === 'done' && (
              <div className="mb-10">
                <HistoryLine history={sampleHistory}/>
              </div>
            )}

            <footer className="py-6 border-t border-[rgba(30,41,59,0.6)] flex items-center justify-between text-[11px] font-mono text-text-muted flex-wrap gap-3">
              <div>StockAgent · design system preview · NSE data delayed 15m</div>
              <div>/ws/stream · orchestrator v0.9 · 8 agents live</div>
            </footer>
          </div>
        </main>
      </div>
    </div>
  );
};

ReactDOM.createRoot(document.getElementById('root')).render(<App/>);
