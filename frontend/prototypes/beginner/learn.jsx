// Learn page — beginner-first education hub
const { useState: useStateLn } = React;

function LearnPage({ onNav, openChat }) {
  const [search, setSearch] = useStateLn('');
  const [activePath, setActivePath] = useStateLn(null);

  const totalProgress = window.LEARN_PATHS.reduce((s,p) => s + p.progress, 0) / window.LEARN_PATHS.length;
  const completedSteps = window.LEARN_PATHS.reduce((s,p) => s + Math.round(p.progress * p.steps), 0);
  const totalSteps     = window.LEARN_PATHS.reduce((s,p) => s + p.steps, 0);

  return (
    <div style={{ minHeight:'100vh', background:'var(--bg-base)' }}>
      <TopNav active="learn" onNav={onNav} search={search} setSearch={setSearch}/>

      <main style={{ maxWidth:1280, margin:'0 auto', padding:'var(--main-py) var(--main-px) 96px' }}>
        {/* Hero */}
        <section style={{
          position:'relative', overflow:'hidden', borderRadius:24, marginBottom:32,
          background:'linear-gradient(135deg, #1a4a73 0%, #0e3a4a 50%, #4a1a73 100%)',
          color:'#f1f5f9', padding:'40px 48px',
          display:'grid', gridTemplateColumns:'var(--hero-cols)', gap:32, alignItems:'center'
        }}>
          <div style={{ position:'absolute', top:'-30%', right:'10%', width:480, height:480, borderRadius:'50%',
            background:'radial-gradient(circle, rgba(167,139,250,.35), transparent 65%)', filter:'blur(40px)' }}/>

          <div style={{ position:'relative', zIndex:2 }}>
            <div style={{ fontSize:11, fontWeight:700, letterSpacing:'.18em', color:'#c4b5fd', textTransform:'uppercase', marginBottom:10 }}>
              Learn · Beginner-first
            </div>
            <h1 style={{ fontSize:32, fontWeight:800, letterSpacing:'-0.02em', lineHeight:1.15, margin:'0 0 12px' }}>
              From "what's a P/E?"<br/>
              <span style={{ background:'linear-gradient(90deg,#22d3ee,#a78bfa)', WebkitBackgroundClip:'text', WebkitTextFillColor:'transparent' }}>
                to confident moves.
              </span>
            </h1>
            <p style={{ color:'#cbd5e1', fontSize:14, lineHeight:1.6, margin:'0 0 18px', maxWidth:520 }}>
              Bite-sized paths built around how the 9 agents actually think about Indian autos. Plain English. No jargon walls.
            </p>
            <div style={{ display:'flex', alignItems:'center', gap:14 }}>
              <div style={{ flex:1, maxWidth:280, height:6, background:'rgba(255,255,255,.12)', borderRadius:999, overflow:'hidden' }}>
                <div style={{ width: (totalProgress*100)+'%', height:'100%',
                  background:'linear-gradient(90deg,#22d3ee,#a78bfa)' }}/>
              </div>
              <span className="mono" style={{ fontSize:13, fontWeight:700 }}>
                {completedSteps}/{totalSteps} steps · {Math.round(totalProgress*100)}%
              </span>
            </div>
          </div>

          <div style={{ position:'relative', zIndex:2, display:'grid', placeItems:'center' }}>
            <button onClick={openChat} style={{ background:'transparent', border:'none', cursor:'pointer' }}>
              <Sphere size={200} mode="wireframe"/>
            </button>
          </div>
        </section>

        {/* Continue learning */}
        <SectionHead title="Continue where you left off"
          subtitle="Pick a path and finish in one sitting"/>
        <div style={{ display:'grid', gridTemplateColumns:'var(--grid-paths)', gap:16, marginTop:16, marginBottom:36 }}>
          {window.LEARN_PATHS.map(p => (
            <PathCard key={p.key} p={p} onClick={()=>setActivePath(p.key)}/>
          ))}
        </div>

        {/* Two-column: Glossary + Tips */}
        <div style={{ display:'grid', gridTemplateColumns:'var(--grid-2col)', gap:20 }}>
          <GlossaryCard openChat={openChat}/>
          <TipsCard tips={window.LEARN_TIPS}/>
        </div>

        {/* Recommended next */}
        <div style={{ marginTop:36 }}>
          <SectionHead title="Recommended next"
            subtitle="Picked because you finished 'Reading a verdict'"/>
          <div style={{ display:'grid', gridTemplateColumns:'var(--grid-suggestions)', gap:16, marginTop:16 }}>
            <RecCard
              title="Watch a real verdict happen"
              body="See the 9 agents stream live for MARUTI. 12 seconds, real signals."
              cta="Run a demo analysis"
              kind="demo"/>
            <RecCard
              title="Quiz: Spot the strong buy"
              body="3 stocks. 9 agent scores each. Pick the strong-buy. See why."
              cta="Start quiz · 4 min"
              kind="quiz"/>
          </div>
        </div>
      </main>

      {activePath && <PathOverlay p={window.LEARN_PATHS.find(x => x.key === activePath)} onClose={()=>setActivePath(null)}/>}
    </div>
  );
}

function PathCard({ p, onClick }) {
  const done = p.progress === 1.0;
  const stepsDone = Math.round(p.progress * p.steps);
  return (
    <button onClick={onClick} className="card" style={{
      padding:0, overflow:'hidden', cursor:'pointer', textAlign:'left',
      border:'1px solid var(--border)', transition:'transform .15s, box-shadow .15s'
    }}
      onMouseEnter={e=>{e.currentTarget.style.transform='translateY(-2px)'; e.currentTarget.style.boxShadow='var(--shadow-md)'}}
      onMouseLeave={e=>{e.currentTarget.style.transform=''; e.currentTarget.style.boxShadow='var(--shadow-sm)'}}>
      <div style={{
        height:6, background:`color-mix(in oklab, ${p.color} 18%, transparent)`,
        position:'relative'
      }}>
        <div style={{ width:(p.progress*100)+'%', height:'100%', background:p.color, transition:'width .8s' }}/>
      </div>
      <div style={{ padding:20 }}>
        <div style={{
          width:48, height:48, borderRadius:12, fontSize:22,
          background:`color-mix(in oklab, ${p.color} 14%, transparent)`,
          display:'grid', placeItems:'center', marginBottom:12
        }}>{p.icon}</div>
        <div style={{ fontSize:15, fontWeight:700, marginBottom:4, color:'var(--ink-1)' }}>{p.title}</div>
        <div style={{ fontSize:13, color:'var(--ink-2)', lineHeight:1.5, marginBottom:14 }}>{p.sub}</div>
        <div style={{ display:'flex', alignItems:'center', gap:10, fontSize:11, color:'var(--ink-3)' }}>
          <span style={{ display:'flex', alignItems:'center', gap:4 }}>
            <Icon.Layers size={12}/> {stepsDone}/{p.steps} steps
          </span>
          <span>·</span>
          <span>{p.minutes} min</span>
          {done && (
            <span style={{ marginLeft:'auto', display:'flex', alignItems:'center', gap:4,
              padding:'2px 8px', borderRadius:999, background:'var(--buy-soft)', color:'var(--buy-strong)', fontWeight:700 }}>
              <Icon.Check size={11}/> Done
            </span>
          )}
        </div>
      </div>
    </button>
  );
}

function GlossaryCard({ openChat }) {
  return (
    <div className="card" style={{ padding:24 }}>
      <div style={{ display:'flex', alignItems:'center', gap:10, marginBottom:14 }}>
        <div className="eyebrow">Glossary · for the impatient</div>
        <button onClick={openChat} style={{ marginLeft:'auto', fontSize:11, fontWeight:600, color:'var(--cyan)',
          background:'transparent', border:'none', display:'flex', alignItems:'center', gap:4 }}>
          Ask anything <Icon.ChevronR size={11}/>
        </button>
      </div>
      <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:10 }}>
        {window.GLOSSARY.map(g => (
          <div key={g.term} style={{
            padding:'14px 16px', borderRadius:12, background:'var(--bg-base)', border:'1px solid var(--border)'
          }}>
            <div style={{ display:'flex', alignItems:'baseline', gap:8, marginBottom:6 }}>
              <span style={{ fontSize:13, fontWeight:700 }}>{g.term}</span>
              <span style={{ fontSize:10, color:'var(--ink-3)', textTransform:'uppercase', letterSpacing:'.08em' }}>{g.short}</span>
            </div>
            <div style={{ fontSize:12, color:'var(--ink-2)', lineHeight:1.5 }}>{g.defn}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

function TipsCard({ tips }) {
  return (
    <div className="card" style={{ padding:24, position:'relative', overflow:'hidden' }}>
      <div style={{ position:'absolute', top:-30, right:-20, width:140, height:140, borderRadius:'50%',
        background:'radial-gradient(circle, var(--cyan-soft), transparent 70%)' }}/>
      <div className="eyebrow" style={{ marginBottom:16, position:'relative' }}>3 things every beginner gets wrong</div>
      <div style={{ display:'flex', flexDirection:'column', gap:14, position:'relative' }}>
        {tips.map((t, i) => (
          <div key={i} style={{ display:'grid', gridTemplateColumns:'auto 1fr', gap:14 }}>
            <span className="mono" style={{
              width:28, height:28, borderRadius:8, fontSize:13, fontWeight:800,
              background:'linear-gradient(135deg, var(--cyan), var(--violet))',
              color:'#fff', display:'grid', placeItems:'center', flexShrink:0
            }}>{i+1}</span>
            <div>
              <div style={{ fontSize:13, fontWeight:700, marginBottom:4 }}>{t.title}</div>
              <div style={{ fontSize:12, color:'var(--ink-2)', lineHeight:1.5 }}>{t.body}</div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function RecCard({ title, body, cta, kind }) {
  const isDemo = kind === 'demo';
  return (
    <div className="card" style={{ padding:24, display:'grid', gridTemplateColumns:'1fr auto', gap:20, alignItems:'center' }}>
      <div>
        <div className="eyebrow" style={{ marginBottom:8, color: isDemo ? 'var(--cyan)' : 'var(--violet)' }}>
          {isDemo ? 'Live demo' : 'Quiz'}
        </div>
        <div style={{ fontSize:15, fontWeight:700, marginBottom:6 }}>{title}</div>
        <div style={{ fontSize:13, color:'var(--ink-2)', lineHeight:1.5, marginBottom:14 }}>{body}</div>
        <button style={{
          padding:'9px 14px', borderRadius:10, border:'none',
          background: isDemo ? 'var(--cyan)' : 'var(--violet)',
          color:'#fff', fontSize:12, fontWeight:700,
          display:'flex', alignItems:'center', gap:6
        }}>{cta} <Icon.ChevronR size={13}/></button>
      </div>
      <div style={{
        width:96, height:96, borderRadius:18, fontSize:40,
        background: isDemo
          ? 'linear-gradient(135deg, var(--cyan-soft), var(--violet-soft))'
          : 'linear-gradient(135deg, var(--violet-soft), var(--cyan-soft))',
        display:'grid', placeItems:'center'
      }}>{isDemo ? '⚡' : '🎲'}</div>
    </div>
  );
}

function PathOverlay({ p, onClose }) {
  const stepsDone = Math.round(p.progress * p.steps);
  // Mock the step content
  const steps = Array.from({ length: p.steps }, (_, i) => ({
    title: getStepTitle(p.key, i),
    duration: Math.ceil(p.minutes / p.steps),
    done: i < stepsDone,
  }));

  return (
    <>
      <div onClick={onClose} style={{
        position:'fixed', inset:0, background:'rgba(15,23,42,.5)', backdropFilter:'blur(6px)', zIndex:50,
        animation:'fade-in .2s'
      }}/>
      <aside style={{
        position:'fixed', top:0, right:0, bottom:0, width:560, zIndex:55,
        background:'var(--bg-surface)', boxShadow:'-20px 0 60px rgba(15,23,42,.15)',
        animation:'slide-in .3s cubic-bezier(.2,.8,.2,1)',
        display:'flex', flexDirection:'column', overflow:'hidden'
      }}>
        <div style={{
          padding:'24px 28px 20px', position:'relative', overflow:'hidden',
          background:`linear-gradient(135deg, color-mix(in oklab, ${p.color} 16%, var(--bg-surface)), var(--bg-surface))`
        }}>
          <button onClick={onClose} style={{
            position:'absolute', top:20, right:20, width:32, height:32, borderRadius:8,
            border:'1px solid var(--border)', background:'var(--bg-surface)',
            display:'grid', placeItems:'center', color:'var(--ink-2)' }}>
            <Icon.X size={16}/>
          </button>
          <div style={{
            width:56, height:56, borderRadius:14, fontSize:28,
            background:`color-mix(in oklab, ${p.color} 18%, transparent)`,
            display:'grid', placeItems:'center', marginBottom:14
          }}>{p.icon}</div>
          <h2 style={{ fontSize:22, fontWeight:800, letterSpacing:'-0.01em', margin:'0 0 6px' }}>{p.title}</h2>
          <p style={{ color:'var(--ink-2)', fontSize:13, margin:'0 0 14px' }}>{p.sub}</p>
          <div style={{ display:'flex', alignItems:'center', gap:14 }}>
            <div style={{ flex:1, height:6, background:'var(--bg-tinted)', borderRadius:999, overflow:'hidden' }}>
              <div style={{ width:(p.progress*100)+'%', height:'100%', background:p.color, transition:'width .8s' }}/>
            </div>
            <span className="mono" style={{ fontSize:12, fontWeight:700 }}>{stepsDone}/{p.steps}</span>
          </div>
        </div>

        <div style={{ flex:1, overflowY:'auto', padding:'20px 28px' }}>
          <div className="eyebrow" style={{ marginBottom:14 }}>Path · {p.steps} steps</div>
          <div style={{ display:'flex', flexDirection:'column', gap:10 }}>
            {steps.map((s, i) => (
              <div key={i} style={{
                display:'grid', gridTemplateColumns:'auto 1fr auto', gap:14, alignItems:'center',
                padding:'14px 16px', border:'1px solid var(--border)', borderRadius:12,
                background: s.done ? `color-mix(in oklab, ${p.color} 6%, transparent)` : 'var(--bg-surface)'
              }}>
                <span style={{
                  width:32, height:32, borderRadius:'50%', display:'grid', placeItems:'center',
                  background: s.done ? p.color : 'var(--bg-tinted)',
                  color: s.done ? '#fff' : 'var(--ink-3)',
                  fontWeight:700, fontSize:13
                }}>
                  {s.done ? <Icon.Check size={14}/> : i+1}
                </span>
                <div>
                  <div style={{ fontSize:13, fontWeight:600, color: s.done ? 'var(--ink-2)' : 'var(--ink-1)',
                    textDecoration: s.done ? 'line-through' : 'none' }}>{s.title}</div>
                  <div style={{ fontSize:11, color:'var(--ink-3)', marginTop:2 }}>{s.duration} min</div>
                </div>
                <button style={{
                  padding:'6px 12px', borderRadius:8,
                  border: s.done ? '1px solid var(--border)' : 'none',
                  background: s.done ? 'transparent' : p.color,
                  color: s.done ? 'var(--ink-2)' : '#fff',
                  fontSize:12, fontWeight:600
                }}>{s.done ? 'Review' : 'Start'}</button>
              </div>
            ))}
          </div>
        </div>

        <div style={{ padding:'16px 28px', borderTop:'1px solid var(--border)' }}>
          <button style={{
            width:'100%', padding:'12px 16px', borderRadius:10, border:'none',
            background: p.color, color:'#fff', fontSize:13, fontWeight:700,
            display:'flex', alignItems:'center', justifyContent:'center', gap:8
          }}>
            {stepsDone === p.steps ? 'Path complete · 🎉' : `Continue from step ${stepsDone+1}`}
            <Icon.ChevronR size={14}/>
          </button>
        </div>
      </aside>
    </>
  );
}

function getStepTitle(pathKey, i) {
  const titles = {
    agents: ['What is an AI agent?','Meet the 9 specialists','How they work in parallel','How votes get fused','Conflicts & how the verdict resolves'],
    verdict: ['The 5-tier verdict scale','Reading the score','When to trust STRONG BUY','When NEUTRAL is the smart call'],
    metrics: ['What P/E really tells you','EBITDA in plain English','Revenue vs EBITDA growth','Margins & why they matter','Promoter / FII / DII flows','Putting it together'],
    macro: ['Why INR matters for autos','Crude oil → input cost','RBI repo & EMI math','Putting it together'],
    ev: ['FAME II in 2 minutes','PLI scheme & who qualifies','Vahan registration data','Reading EV market share','Picking the EV winners'],
    risk: ['How much per trade?','Stop-loss basics','Cutting losers','Letting winners run'],
  };
  return titles[pathKey]?.[i] || `Step ${i+1}`;
}

window.LearnPage = LearnPage;
