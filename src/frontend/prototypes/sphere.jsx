// Premium 3D sphere assistant.
// Two visual modes (set via tweak): "wireframe" (latitude/longitude lines + dots) and "liquid" (glassy gradient orb)
// Hero variant = large, centered, expandable to chat.
// Orb variant = floating bottom-right launcher.

const { useState, useEffect, useRef } = React;

const sphereCSS = `
.sa-sphere-stage { position: relative; perspective: 1200px; transform-style: preserve-3d; }
.sa-sphere { position: relative; transform-style: preserve-3d; animation: sa-rotate 24s linear infinite; }
.sa-sphere.paused { animation-play-state: paused; }
@keyframes sa-rotate {
  from { transform: rotateY(0deg) rotateX(-12deg); }
  to   { transform: rotateY(360deg) rotateX(-12deg); }
}
.sa-ring {
  position: absolute; inset: 0; border-radius: 50%;
  border: 1px solid rgba(8,145,178,.28);
  transform-style: preserve-3d;
}
.sa-ring.lat { border-top-color: rgba(8,145,178,.55); border-bottom-color: rgba(124,58,237,.42); }
.sa-ring.lng { border-left-color: rgba(8,145,178,.55); border-right-color: rgba(124,58,237,.42); }
.sa-glow {
  position: absolute; inset: 0; border-radius: 50%;
  background:
    radial-gradient(circle at 32% 28%, rgba(255,255,255,.95), rgba(255,255,255,0) 38%),
    radial-gradient(circle at 70% 78%, rgba(124,58,237,.42), rgba(124,58,237,0) 55%),
    radial-gradient(circle at 28% 78%, rgba(8,145,178,.55), rgba(8,145,178,0) 60%),
    radial-gradient(circle at center, #f0f9ff 0%, #e0f2fe 38%, #cffafe 60%, #a5f3fc 80%, #67e8f9 100%);
  box-shadow:
    inset -30px -40px 80px rgba(8,145,178,.45),
    inset 18px 22px 60px rgba(255,255,255,.85),
    0 30px 60px -20px rgba(8,145,178,.45),
    0 0 0 1px rgba(8,145,178,.18);
}
[data-theme="dark"] .sa-glow {
  background:
    radial-gradient(circle at 32% 28%, rgba(165,243,252,.55), rgba(165,243,252,0) 38%),
    radial-gradient(circle at 72% 76%, rgba(139,92,246,.55), rgba(139,92,246,0) 55%),
    radial-gradient(circle at center, #0e7490 0%, #155e75 40%, #0c4a6e 70%, #082f49 100%);
}
.sa-core {
  position: absolute; left: 50%; top: 50%; transform: translate(-50%,-50%);
  width: 14%; height: 14%; border-radius: 50%;
  background: radial-gradient(circle at 30% 30%, #ffffff, #67e8f9 60%, #0891b2);
  box-shadow: 0 0 24px rgba(8,145,178,.85), 0 0 64px rgba(8,145,178,.5);
  animation: sa-pulse 2.4s ease-in-out infinite;
}
@keyframes sa-pulse { 0%,100% { transform: translate(-50%,-50%) scale(1); opacity: 1; } 50% { transform: translate(-50%,-50%) scale(1.18); opacity: .85; } }
.sa-dot {
  position: absolute; width: 4px; height: 4px; border-radius: 50%;
  background: rgba(8,145,178,.95); box-shadow: 0 0 8px rgba(8,145,178,.8);
  transform: translate(-50%,-50%);
}
.sa-dot.violet { background: rgba(139,92,246,.95); box-shadow: 0 0 8px rgba(139,92,246,.8); }
.sa-base-glow {
  position: absolute; left: 50%; bottom: -8%; transform: translateX(-50%);
  width: 70%; height: 18%; border-radius: 50%;
  background: radial-gradient(ellipse at center, rgba(8,145,178,.35), transparent 70%);
  filter: blur(12px);
}
.sa-orb-button {
  width: 64px; height: 64px; border-radius: 50%; border: none;
  background: transparent; padding: 0; cursor: pointer; position: relative;
  transition: transform .25s cubic-bezier(.2,.8,.2,1);
}
.sa-orb-button:hover { transform: scale(1.06); }
`;

function Sphere({ size = 320, mode = 'wireframe', paused = false }) {
  // Generate dot constellation in 3D, projected by transform: translateZ + rotateY/X
  const dots = [];
  if (mode === 'wireframe') {
    const N = 60;
    for (let i = 0; i < N; i++) {
      const theta = Math.acos(1 - 2 * (i + 0.5) / N);
      const phi = Math.PI * (1 + Math.sqrt(5)) * i;
      const x = Math.sin(theta) * Math.cos(phi);
      const y = Math.sin(theta) * Math.sin(phi);
      const z = Math.cos(theta);
      const r = size / 2;
      const violet = i % 3 === 0;
      dots.push(
        <span key={i}
          className={"sa-dot " + (violet ? 'violet' : '')}
          style={{
            left: '50%', top: '50%',
            transform: `translate3d(${x*r}px, ${y*r}px, ${z*r}px)`,
          }}/>
      );
    }
  }
  const lats = [-60,-40,-20,0,20,40,60];
  const lngs = [0,30,60,90,120,150];

  return (
    <div className="sa-sphere-stage" style={{ width: size, height: size }}>
      <style>{sphereCSS}</style>
      <div className={"sa-sphere " + (paused?'paused':'')} style={{ width: size, height: size }}>
        {mode === 'liquid' && <div className="sa-glow"/>}
        {mode === 'wireframe' && <>
          {lats.map(d => (
            <div key={'la'+d} className="sa-ring lat"
              style={{ transform: `rotateX(90deg) translateZ(${Math.sin(d*Math.PI/180)*size/2}px) scale(${Math.cos(d*Math.PI/180)})` }}/>
          ))}
          {lngs.map(d => (
            <div key={'ln'+d} className="sa-ring lng"
              style={{ transform: `rotateY(${d}deg)` }}/>
          ))}
          {dots}
          <div className="sa-core"/>
        </>}
        {mode === 'liquid' && <>
          <div className="sa-core" style={{ width: '8%', height: '8%' }}/>
        </>}
      </div>
      <div className="sa-base-glow"/>
    </div>
  );
}

window.Sphere = Sphere;

// Floating orb launcher (bottom-right). Click → opens chat overlay.
function SphereOrb({ onOpen, mode='wireframe' }) {
  return (
    <button className="sa-orb-button sphere-orb"
      style={{ position:'fixed', right:24, bottom:24, zIndex:60, width:64, height:64 }}
      onClick={onOpen} aria-label="Open AI assistant">
      <Sphere size={64} mode={mode}/>
    </button>
  );
}
window.SphereOrb = SphereOrb;

// Chat overlay (slide-up panel, anchored bottom-right)
function ChatOverlay({ open, onClose, mode='wireframe' }) {
  const [msgs, setMsgs] = useState([
    { from:'bot', text:"Hi 👋 I'm your StockAgent assistant. Ask me anything about Indian autos." }
  ]);
  const [input, setInput] = useState('');
  const endRef = useRef(null);
  useEffect(() => { endRef.current?.scrollTo?.(0, 99999); }, [msgs, open]);

  const send = async (text) => {
    if (!text.trim()) return;
    setInput('');
    // Build conversation history from current messages (exclude loading states, last 8 turns)
    const history = msgs
      .filter(m => !m.loading)
      .slice(-8)
      .map(m => ({ role: m.from === 'user' ? 'user' : 'assistant', content: m.text }));
    // Append user message + thinking placeholder immediately
    setMsgs(m => [...m, {from:'user', text}, {from:'bot', text:'…', loading:true}]);
    let reply;
    try {
      const res = await fetch('/ui/chat', {
        method: 'POST',
        headers: {'Content-Type':'application/json'},
        body: JSON.stringify({ message: text, history }),
      });
      reply = res.ok ? (await res.json()).reply : mockReply(text);
    } catch {
      reply = mockReply(text);
    }
    // Replace loading placeholder with actual reply
    setMsgs(m => [...m.slice(0, -1), {from:'bot', text: reply}]);
  };

  if (!open) return null;
  return (
    <div className="chat-overlay" style={{
      background:'var(--bg-surface)', border:'1px solid var(--border)',
      display:'flex', flexDirection:'column'
    }}>
      <div className="drawer-handle"/>
      <style>{`@keyframes chat-in { from { opacity:0; transform: translateY(12px) scale(.98); } to { opacity:1; transform:none; } }`}</style>
      <div style={{ padding:'14px 16px', borderBottom:'1px solid var(--border)', display:'flex', alignItems:'center', gap:12 }}>
        <Sphere size={36} mode={mode}/>
        <div style={{ flex:1 }}>
          <div style={{ fontWeight:700, fontSize:14, color:'var(--ink-1)' }}>StockAgent AI</div>
          <div style={{ fontSize:11, color:'var(--ink-3)', display:'flex', alignItems:'center', gap:6 }}>
            <span style={{ width:6, height:6, borderRadius:'50%', background:'var(--buy)', display:'inline-block' }}/>
            9 agents online · live
          </div>
        </div>
        <button onClick={onClose} style={{ background:'transparent', border:'none', color:'var(--ink-3)', padding:4 }}><Icon.X size={18}/></button>
      </div>
      <div ref={endRef} style={{ flex:1, padding:16, overflowY:'auto', display:'flex', flexDirection:'column', gap:10 }}>
        {msgs.map((m,i) => (
          <div key={i} style={{
            alignSelf: m.from==='user' ? 'flex-end' : 'flex-start',
            maxWidth:'82%', padding:'10px 14px',
            background: m.from==='user' ? 'var(--cyan)' : 'var(--bg-tinted)',
            color: m.from==='user' ? '#fff' : 'var(--ink-1)',
            borderRadius: m.from==='user' ? '16px 16px 4px 16px' : '16px 16px 16px 4px',
            fontSize:13, lineHeight:1.55,
            animation: m.loading ? 'pulse-soft 1.2s ease-in-out infinite' : 'none',
            opacity: m.loading ? 0.7 : 1,
          }}>{m.text}</div>
        ))}
        {msgs.length===1 && <div style={{ display:'flex', flexDirection:'column', gap:6, marginTop:8 }}>
          {window.CHAT_SEEDS.map(s => (
            <button key={s} onClick={()=>send(s)} style={{
              textAlign:'left', padding:'8px 12px', borderRadius:10, border:'1px solid var(--border)',
              background:'transparent', color:'var(--ink-2)', fontSize:12
            }}>{s}</button>
          ))}
        </div>}
      </div>
      <form onSubmit={e=>{e.preventDefault(); send(input);}} style={{
        padding:12, borderTop:'1px solid var(--border)', display:'flex', gap:8, alignItems:'center'
      }}>
        <input value={input} onChange={e=>setInput(e.target.value)} placeholder="Ask about a stock or agent…"
          style={{ flex:1, border:'1px solid var(--border)', borderRadius:999, padding:'10px 14px',
                   background:'var(--bg-base)', color:'var(--ink-1)', fontSize:13, outline:'none' }}/>
        <button type="submit" style={{
          width:36, height:36, borderRadius:'50%', border:'none', background:'var(--cyan)', color:'#fff',
          display:'grid', placeItems:'center'
        }}><Icon.Send size={16}/></button>
      </form>
    </div>
  );
}
window.ChatOverlay = ChatOverlay;

function mockReply(q) {
  const ql = q.toLowerCase();
  if (ql.includes('maruti')) return "MARUTI is STRONG BUY (0.82). Sales & Demand and Fundamentals are most positive — April dispatches +14% YoY and steel prices easing. Risk & Macro is the lone caution due to a slightly weaker INR.";
  if (ql.includes('tata')) return "TATAMOTORS is BUY (0.74). The EV order book is the standout — JLR margins recovering. Watch the China supply chain risk flagged by Risk & Macro.";
  if (ql.includes('agent') && ql.includes('trust')) return "For short-term moves, Pattern Analysis (technicals) and Sentiment tend to lead. For 3-6 month horizons, Fundamentals + Sales & Demand carry more weight — they currently make up 38% of the composite score.";
  if (ql.includes('compare')) return "TATAMOTORS leads on EV pure-play exposure (Tiago.ev, Punch.ev). M&M has the diversified moat (SUV + tractors + Thar.e). Both BUY-rated; M&M has lower beta.";
  return "Got it. I'd route this to the relevant agents — try one of the suggestions above, or ask me about a specific ticker like MARUTI or BAJAJ-AUTO.";
}
