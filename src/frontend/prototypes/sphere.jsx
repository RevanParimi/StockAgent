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

// Markdown → HTML via marked.js (loaded from CDN in index.html).
// Falls back to escaped plain text if marked isn't available.
function renderMd(text) {
  if (!text || text === '…') return text === '…' ? '…' : '';
  if (window.marked) {
    return window.marked.parse(text);
  }
  // Plain-text fallback — at least escape HTML so nothing breaks
  return text.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
             .replace(/\n/g,'<br>');
}

// Intent badge — small chip shown above the bot bubble
function IntentBadge({ intent }) {
  if (!intent) return null;
  const typeColors = {
    SINGLE_STOCK:    '#0891b2',
    STOCK_COMPARE:   '#7c3aed',
    SECTOR_OVERVIEW: '#059669',
    MULTI_SECTOR:    '#d97706',
    PRICE_QUERY:     '#dc2626',
    NEWS_QUERY:      '#2563eb',
    AGENT_QUERY:     '#9333ea',
    RL_QUERY:        '#c026d3',
    GENERAL:         '#64748b',
  };
  const color = typeColors[intent.intent_type] || '#64748b';
  const suffix = intent.display_label ? intent.display_label.replace(/^\[[A-Z_]+\]\s*/, '') : '';
  return (
    <div style={{ fontSize:10, fontWeight:700, letterSpacing:'.06em', color, marginBottom:4,
      display:'flex', alignItems:'center', gap:6, flexWrap:'wrap' }}>
      <span style={{ padding:'2px 6px', borderRadius:4,
        background:`${color}22`, border:`1px solid ${color}44` }}>
        {intent.intent_type}
      </span>
      {suffix && <span style={{ color:'var(--ink-3)', fontWeight:500 }}>{suffix}</span>}
    </div>
  );
}

// Tool trace panel — collapsible, shows each tool that ran
function ToolTracePanel({ trace }) {
  if (!trace || trace.length === 0) return null;
  return (
    <details style={{ marginTop:6, fontSize:11 }}>
      <summary style={{ cursor:'pointer', color:'var(--ink-3)', userSelect:'none', marginBottom:4 }}>
        {trace.length} tool{trace.length > 1 ? 's' : ''} used
      </summary>
      <div style={{ display:'flex', flexDirection:'column', gap:3, paddingTop:4 }}>
        {trace.map((t, i) => (
          <div key={i} style={{
            display:'flex', gap:8, alignItems:'flex-start',
            padding:'4px 8px', background:'var(--bg-tinted)', borderRadius:6,
            fontFamily:'var(--font-mono,monospace)',
          }}>
            <span style={{ color:'var(--buy)', flexShrink:0 }}>✓</span>
            <span style={{ color:'var(--cyan)', flexShrink:0 }}>{t.tool}()</span>
            <span style={{ color:'var(--ink-3)', overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap' }}>
              {t.summary}
            </span>
          </div>
        ))}
      </div>
    </details>
  );
}

// Chat overlay (slide-up panel, anchored bottom-right)
function ChatOverlay({ open, onClose, mode='wireframe' }) {
  const [msgs, setMsgs] = useState([
    { from:'bot', text:"Hi I'm your StockAgent assistant. Ask me anything about Indian markets." }
  ]);
  const [input, setInput] = useState('');
  const endRef = useRef(null);
  useEffect(() => { endRef.current?.scrollTo?.(0, 99999); }, [msgs, open]);

  const send = async (text) => {
    if (!text.trim()) return;
    setInput('');
    const history = msgs
      .filter(m => !m.loading)
      .slice(-8)
      .map(m => ({ role: m.from === 'user' ? 'user' : 'assistant', content: m.text }));

    setMsgs(m => [...m,
      { from:'user', text },
      { from:'bot', text:'', loading:true, intent:null, toolTrace:[] },
    ]);

    try {
      const resp = await fetch('/ui/chat/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: text, history }),
      });

      if (!resp.ok || !resp.body) throw new Error('Stream unavailable');

      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop();  // keep incomplete last line

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;
          try {
            const evt = JSON.parse(line.slice(6));
            if (evt.event === 'intent') {
              setMsgs(m => {
                const next = [...m];
                next[next.length - 1] = { ...next[next.length - 1], intent: evt };
                return next;
              });
            } else if (evt.event === 'tool_result') {
              setMsgs(m => {
                const next = [...m];
                const last = next[next.length - 1];
                next[next.length - 1] = {
                  ...last,
                  toolTrace: [...(last.toolTrace || []), { tool: evt.tool, summary: evt.summary }],
                };
                return next;
              });
            } else if (evt.event === 'token') {
              setMsgs(m => {
                const next = [...m];
                next[next.length - 1] = {
                  ...next[next.length - 1],
                  text: (next[next.length - 1].text || '') + evt.text,
                  loading: false,
                };
                return next;
              });
            } else if (evt.event === 'done') {
              setMsgs(m => {
                const next = [...m];
                next[next.length - 1] = { ...next[next.length - 1], loading: false };
                return next;
              });
            }
          } catch {}
        }
      }
    } catch {
      // Fallback to blocking POST if streaming fails
      try {
        const res = await fetch('/ui/chat', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ message: text, history }),
        });
        const data = res.ok ? await res.json() : {};
        setMsgs(m => [...m.slice(0, -1), { from:'bot', text: data.reply || 'Error', loading:false, toolTrace:[] }]);
      } catch {
        setMsgs(m => [...m.slice(0, -1), { from:'bot', text:'Network error — try again.', loading:false, toolTrace:[] }]);
      }
    }
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
        {msgs.map((m, i) => {
          const bubbleStyle = {
            alignSelf: m.from==='user' ? 'flex-end' : 'flex-start',
            maxWidth:'82%', padding:'10px 14px',
            background: m.from==='user' ? 'var(--cyan)' : 'var(--bg-tinted)',
            color: m.from==='user' ? '#fff' : 'var(--ink-1)',
            borderRadius: m.from==='user' ? '16px 16px 4px 16px' : '16px 16px 16px 4px',
            fontSize:13, lineHeight:1.6,
            animation: m.loading && !m.text ? 'pulse-soft 1.2s ease-in-out infinite' : 'none',
            opacity: m.loading && !m.text ? 0.7 : 1,
          };
          if (m.from === 'bot') {
            return (
              <div key={i} style={{ alignSelf:'flex-start', maxWidth:'82%' }}>
                <IntentBadge intent={m.intent}/>
                <div className="chat-md" style={bubbleStyle}
                  dangerouslySetInnerHTML={{ __html: m.loading && !m.text ? '…' : renderMd(m.text) }}/>
                <ToolTracePanel trace={m.toolTrace}/>
              </div>
            );
          }
          return <div key={i} style={bubbleStyle}>{m.text}</div>;
        })}
        {msgs.length===1 && (
          <div style={{ display:'flex', flexDirection:'column', gap:6, marginTop:8 }}>
            {(window.CHAT_SEEDS || []).map(s => (
              <button key={s} onClick={()=>send(s)} style={{
                textAlign:'left', padding:'8px 12px', borderRadius:10, border:'1px solid var(--border)',
                background:'transparent', color:'var(--ink-2)', fontSize:12
              }}>{s}</button>
            ))}
          </div>
        )}
      </div>
      <form onSubmit={e=>{e.preventDefault(); send(input);}} style={{
        padding:12, borderTop:'1px solid var(--border)', display:'flex', gap:8, alignItems:'center'
      }}>
        <input value={input} onChange={e=>setInput(e.target.value)} placeholder="Ask about a stock or sector…"
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
