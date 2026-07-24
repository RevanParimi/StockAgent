// Login + Signup screen — toggled tabs on one card
const { useState: useStateAuth } = React;

function AuthScreen({ onAuthed }) {
  const [tab, setTab] = useStateAuth('login');
  const [showPw, setShowPw] = useStateAuth(false);
  const [email, setEmail] = useStateAuth('');
  const [name, setName] = useStateAuth('');
  const [pw, setPw] = useStateAuth('');
  const [remember, setRemember] = useStateAuth(true);

  const submit = (e) => { e.preventDefault(); onAuthed(remember); };

  return (
    <div className="auth-layout" style={{
      minHeight:'100vh', display:'grid', gridTemplateColumns:'1.05fr 1fr',
      background:'var(--bg-base)'
    }}>
      <style>{`
        @keyframes auth-grad { 0%,100% { background-position: 0% 50%; } 50% { background-position: 100% 50%; } }
        .auth-input:focus { border-color: var(--cyan); box-shadow: 0 0 0 4px rgba(8,145,178,.12); }
      `}</style>

      {/* LEFT — brand panel */}
      <div className="auth-brand" style={{
        position:'relative', overflow:'hidden',
        background: 'linear-gradient(135deg,#0a1628 0%, #0e3a4a 35%, #134e5c 60%, #1a4a73 100%)',
        backgroundSize:'200% 200%', animation:'auth-grad 18s ease infinite',
        color:'#f1f5f9', padding:'48px 56px', display:'flex', flexDirection:'column'
      }}>
        {/* glow blobs */}
        <div style={{ position:'absolute', top:'-10%', left:'-10%', width:480, height:480, borderRadius:'50%',
          background:'radial-gradient(circle, rgba(8,145,178,.45), transparent 70%)', filter:'blur(60px)' }}/>
        <div style={{ position:'absolute', bottom:'-15%', right:'-10%', width:520, height:520, borderRadius:'50%',
          background:'radial-gradient(circle, rgba(124,58,237,.4), transparent 70%)', filter:'blur(60px)' }}/>

        {/* logo */}
        <div style={{ display:'flex', alignItems:'center', gap:12, position:'relative', zIndex:2 }}>
          <div style={{
            width:36, height:36, borderRadius:10,
            background:'linear-gradient(135deg,#22d3ee,#7c3aed)',
            display:'grid', placeItems:'center', boxShadow:'0 6px 20px rgba(34,211,238,.45)'
          }}>
            <Icon.Sparkles size={20} c="#fff"/>
          </div>
          <div>
            <div style={{ fontWeight:800, fontSize:18, letterSpacing:'-0.01em' }}>StockAgent</div>
            <div style={{ fontSize:11, color:'#94a3b8', letterSpacing:'.18em', textTransform:'uppercase' }}>9 specialists · 1 verdict</div>
          </div>
        </div>

        {/* sphere hero */}
        <div style={{ flex:1, display:'grid', placeItems:'center', position:'relative', zIndex:1 }}>
          <Sphere size={360} mode="wireframe"/>
        </div>

        {/* copy */}
        <div style={{ position:'relative', zIndex:2, maxWidth:460 }}>
          <h1 style={{ fontSize:36, fontWeight:800, letterSpacing:'-0.02em', lineHeight:1.1, margin:'0 0 12px' }}>
            Nine specialist agents.<br/>
            <span style={{ background:'linear-gradient(90deg,#22d3ee,#a78bfa)', WebkitBackgroundClip:'text', WebkitTextFillColor:'transparent' }}>
              One clear answer.
            </span>
          </h1>
          <p style={{ color:'#cbd5e1', fontSize:15, lineHeight:1.6, margin:'0 0 24px' }}>
            Built for Indian autos. Fundamentals, technicals, news, policy, macro — fused into a verdict you can act on.
          </p>
          <div style={{ display:'flex', gap:24, fontSize:12, color:'#94a3b8' }}>
            <div><div className="mono" style={{ fontSize:22, color:'#fff', fontWeight:700 }}>9</div>agents</div>
            <div><div className="mono" style={{ fontSize:22, color:'#fff', fontWeight:700 }}>~12s</div>full analysis</div>
            <div><div className="mono" style={{ fontSize:22, color:'#fff', fontWeight:700 }}>NSE</div>+ BSE coverage</div>
          </div>
        </div>
      </div>

      {/* RIGHT — auth card */}
      <div className="auth-form-col" style={{ display:'grid', placeItems:'center', padding:48 }}>
        <div style={{ width:'100%', maxWidth:420 }}>
          <div style={{ marginBottom:32 }}>
            <h2 style={{ fontSize:28, fontWeight:800, letterSpacing:'-0.02em', margin:'0 0 6px' }}>
              {tab==='login' ? 'Welcome back' : 'Create your account'}
            </h2>
            <p style={{ color:'var(--ink-2)', fontSize:14, margin:0 }}>
              {tab==='login' ? 'Pick up where you left off.' : 'Start with 5 free analyses every week.'}
            </p>
          </div>

          {/* tabs */}
          <div style={{
            display:'grid', gridTemplateColumns:'1fr 1fr', padding:4, background:'var(--bg-tinted)',
            borderRadius:12, marginBottom:24, position:'relative'
          }}>
            <div style={{
              position:'absolute', top:4, bottom:4, width:'calc(50% - 4px)',
              left: tab==='login' ? 4 : 'calc(50% + 0px)',
              background:'var(--bg-surface)', borderRadius:9, boxShadow:'var(--shadow-sm)',
              transition:'left .25s cubic-bezier(.2,.8,.2,1)'
            }}/>
            {['login','signup'].map(k => (
              <button key={k} onClick={()=>setTab(k)} style={{
                position:'relative', zIndex:1, background:'transparent', border:'none',
                padding:'10px', fontSize:13, fontWeight:600,
                color: tab===k ? 'var(--ink-1)' : 'var(--ink-3)'
              }}>{k==='login' ? 'Log in' : 'Sign up'}</button>
            ))}
          </div>

          <form onSubmit={submit} style={{ display:'flex', flexDirection:'column', gap:14 }}>
            {tab==='signup' && (
              <Field icon={<Icon.User size={16}/>} label="Full name">
                <input value={name} onChange={e=>setName(e.target.value)} placeholder="Aditi Sharma" className="auth-input"
                  style={inputStyle}/>
              </Field>
            )}
            <Field icon={<Icon.Mail size={16}/>} label="Email">
              <input type="email" value={email} onChange={e=>setEmail(e.target.value)} placeholder="you@example.com" className="auth-input"
                style={inputStyle}/>
            </Field>
            <Field icon={<Icon.Lock size={16}/>} label="Password">
              <input type={showPw?'text':'password'} value={pw} onChange={e=>setPw(e.target.value)} placeholder="••••••••" className="auth-input"
                style={inputStyle}/>
              <button type="button" onClick={()=>setShowPw(!showPw)} style={{
                position:'absolute', right:10, top:'50%', transform:'translateY(-50%)',
                background:'transparent', border:'none', color:'var(--ink-3)', padding:4
              }}>{showPw ? <Icon.EyeOff size={16}/> : <Icon.Eye size={16}/>}</button>
            </Field>

            {tab==='login' && (
              <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', fontSize:12 }}>
                <label style={{ display:'flex', alignItems:'center', gap:6, color:'var(--ink-2)', cursor:'pointer' }}>
                  <input type="checkbox" checked={remember} onChange={e=>setRemember(e.target.checked)}/> Remember me
                </label>
                <a href="#" style={{ color:'var(--cyan)', textDecoration:'none', fontWeight:600 }}>Forgot?</a>
              </div>
            )}

            <button type="submit" style={{
              marginTop:8, padding:'14px 16px', border:'none', borderRadius:12,
              background:'linear-gradient(135deg,#0891b2,#7c3aed)', color:'#fff',
              fontSize:14, fontWeight:700, letterSpacing:'.01em',
              boxShadow:'0 8px 24px rgba(8,145,178,.3)', cursor:'pointer'
            }}>{tab==='login' ? 'Log in' : 'Create account'} →</button>
          </form>

          <div style={{ display:'flex', alignItems:'center', gap:12, margin:'24px 0', color:'var(--ink-3)', fontSize:11 }}>
            <span style={{ flex:1, height:1, background:'var(--border)' }}/>
            OR CONTINUE WITH
            <span style={{ flex:1, height:1, background:'var(--border)' }}/>
          </div>

          <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:10 }}>
            <SocialBtn onClick={()=>onAuthed(remember)} icon={<Icon.Google size={18}/>} label="Google"/>
            <SocialBtn onClick={()=>onAuthed(remember)} icon={<Icon.Apple size={18}/>} label="Apple"/>
          </div>

          <p style={{ marginTop:24, fontSize:12, color:'var(--ink-3)', textAlign:'center' }}>
            By continuing you agree to our <a href="#" style={{ color:'var(--ink-2)' }}>Terms</a> & <a href="#" style={{ color:'var(--ink-2)' }}>Privacy</a>.
          </p>
        </div>
      </div>
    </div>
  );
}

const inputStyle = {
  width:'100%', padding:'12px 12px 12px 38px', border:'1px solid var(--border)', borderRadius:10,
  background:'var(--bg-surface)', color:'var(--ink-1)', fontSize:14, outline:'none',
  transition:'border-color .15s, box-shadow .15s'
};

function Field({ icon, label, children }) {
  return (
    <div>
      <label style={{ display:'block', fontSize:12, fontWeight:600, color:'var(--ink-2)', marginBottom:6 }}>{label}</label>
      <div style={{ position:'relative' }}>
        <span style={{ position:'absolute', left:12, top:'50%', transform:'translateY(-50%)', color:'var(--ink-3)' }}>{icon}</span>
        {children}
      </div>
    </div>
  );
}

function SocialBtn({ icon, label, onClick }) {
  return (
    <button type="button" onClick={onClick} style={{
      padding:'11px', border:'1px solid var(--border)', borderRadius:10, background:'var(--bg-surface)',
      display:'flex', alignItems:'center', justifyContent:'center', gap:8, fontSize:13, fontWeight:600,
      color:'var(--ink-1)'
    }}>{icon} {label}</button>
  );
}

window.AuthScreen = AuthScreen;
