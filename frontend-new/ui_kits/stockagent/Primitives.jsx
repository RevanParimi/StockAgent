// Primitives — GlassCard, VerdictBadge, GlowButton, AnimatedCounter, helpers.

const { useState, useEffect, useRef, useMemo, useCallback } = React;

/* ── Verdict helpers ────────────────────────────────────────── */
function scoreToVerdict(s) {
  if (s >= 0.75) return 'STRONG BUY';
  if (s >= 0.60) return 'BUY';
  if (s >= 0.45) return 'NEUTRAL';
  if (s >= 0.30) return 'SELL';
  return 'STRONG SELL';
}
function scoreColor(s) {
  if (s >= 0.75) return '#22c55e';
  if (s >= 0.60) return '#4ade80';
  if (s >= 0.45) return '#f59e0b';
  if (s >= 0.30) return '#f97316';
  return '#ef4444';
}
function scoreToGlow(s) {
  const c = scoreColor(s);
  const strong = s >= 0.75 || s < 0.30;
  const r = strong ? 20 : 12;
  const a = strong ? 0.40 : 0.30;
  // Convert hex to rgba with alpha
  const hex = c.replace('#', '');
  const rr = parseInt(hex.slice(0,2),16);
  const gg = parseInt(hex.slice(2,4),16);
  const bb = parseInt(hex.slice(4,6),16);
  return `0 0 ${r}px rgba(${rr},${gg},${bb},${a})`;
}

const VERDICT_STYLE = {
  'STRONG BUY':  { fg: '#22c55e', bg: 'rgba(34,197,94,0.15)',  bd: 'rgba(34,197,94,0.4)'  },
  'BUY':         { fg: '#4ade80', bg: 'rgba(74,222,128,0.12)', bd: 'rgba(74,222,128,0.3)' },
  'NEUTRAL':     { fg: '#f59e0b', bg: 'rgba(245,158,11,0.12)', bd: 'rgba(245,158,11,0.3)' },
  'SELL':        { fg: '#f97316', bg: 'rgba(249,115,22,0.12)', bd: 'rgba(249,115,22,0.3)' },
  'STRONG SELL': { fg: '#ef4444', bg: 'rgba(239,68,68,0.15)',  bd: 'rgba(239,68,68,0.4)'  },
};

/* ── GlassCard ──────────────────────────────────────────────── */
const GlassCard = ({ children, className = '', style, onClick, hover }) => (
  <div
    onClick={onClick}
    className={`
      relative border border-[rgba(30,41,59,0.8)] rounded-[16px] p-5
      transition-all duration-300
      ${hover ? 'hover:border-[#334155] hover:-translate-y-0.5 cursor-pointer' : ''}
      ${className}
    `}
    style={{
      background: 'rgba(12,17,32,0.7)',
      backdropFilter: 'blur(20px)',
      WebkitBackdropFilter: 'blur(20px)',
      ...style,
    }}
  >{children}</div>
);

/* ── VerdictBadge ───────────────────────────────────────────── */
const VerdictBadge = ({ verdict, size = 'md', glow = false }) => {
  const v = (verdict || 'NEUTRAL').toUpperCase();
  const s = VERDICT_STYLE[v] || VERDICT_STYLE['NEUTRAL'];
  const padding = size === 'sm' ? 'text-[10px] px-2 py-0.5' :
                  size === 'lg' ? 'text-base px-4 py-1.5 font-bold' :
                                  'text-xs px-2.5 py-1';
  const boxShadow = glow ? scoreToGlow(
    v === 'STRONG BUY' ? 0.9 : v === 'BUY' ? 0.65 :
    v === 'NEUTRAL' ? 0.5 : v === 'SELL' ? 0.4 : 0.1
  ) : undefined;
  return (
    <span
      className={`inline-flex items-center rounded-full border font-semibold tracking-wider whitespace-nowrap ${padding}`}
      style={{ color: s.fg, background: s.bg, borderColor: s.bd, boxShadow }}
    >{v}</span>
  );
};

/* ── GlowButton ─────────────────────────────────────────────── */
const GlowButton = ({ children, variant = 'cyan', size = 'md', className = '', ...rest }) => {
  const variants = {
    cyan:    { bg: '#06b6d4', fg: '#050810', shadow: 'rgba(6,182,212,0.5)' },
    blue:    { bg: '#3b82f6', fg: '#ffffff', shadow: 'rgba(59,130,246,0.5)' },
    violet:  { bg: '#8b5cf6', fg: '#ffffff', shadow: 'rgba(139,92,246,0.5)' },
    outline: { bg: 'transparent', fg: '#06b6d4', shadow: 'rgba(6,182,212,0.3)' },
  };
  const sz = { sm: 'px-3 py-1.5 text-xs', md: 'px-5 py-2.5 text-sm', lg: 'px-7 py-3.5 text-base' }[size];
  const v = variants[variant];
  const isOutline = variant === 'outline';
  return (
    <button
      {...rest}
      className={`inline-flex items-center justify-center gap-2 font-semibold rounded-xl transition-all duration-200 cursor-pointer select-none ${sz} ${className}
        ${isOutline ? 'border border-[#06b6d4] hover:bg-[rgba(6,182,212,0.1)]' : 'hover:brightness-110'}
        disabled:opacity-50 disabled:cursor-not-allowed`}
      style={{
        background: v.bg, color: v.fg,
        boxShadow: isOutline ? undefined : 'none',
      }}
      onMouseEnter={e => e.currentTarget.style.boxShadow = `0 0 24px ${v.shadow}`}
      onMouseLeave={e => e.currentTarget.style.boxShadow = ''}
    >{children}</button>
  );
};

/* ── AnimatedCounter ───────────────────────────────────────── */
function useEased(target, duration, trigger, decimals = 2) {
  const [val, setVal] = useState(0);
  const rafRef = useRef(0);
  useEffect(() => {
    if (!trigger) { setVal(0); return; }
    const t0 = performance.now();
    const step = (now) => {
      const t = Math.min((now - t0) / duration, 1);
      const eased = 1 - Math.pow(1 - t, 3);
      setVal(eased * target);
      if (t < 1) rafRef.current = requestAnimationFrame(step);
    };
    rafRef.current = requestAnimationFrame(step);
    return () => cancelAnimationFrame(rafRef.current);
  }, [target, duration, trigger]);
  return Number(val.toFixed(decimals));
}

const AnimatedCounter = ({ target, duration = 1500, decimals = 2, trigger = true, prefix = '', suffix = '', className = '' }) => {
  const v = useEased(target, duration, trigger, decimals);
  return <span className={`font-mono tabular-nums ${className}`}>{prefix}{v.toFixed(decimals)}{suffix}</span>;
};

/* ── Skeleton / shimmer ─────────────────────────────────────── */
const Shimmer = ({ className = '' }) => (
  <div className={`rounded-md ${className}`}
       style={{
         background: 'linear-gradient(90deg, rgba(30,41,59,0.5) 25%, rgba(51,65,85,0.5) 50%, rgba(30,41,59,0.5) 75%)',
         backgroundSize: '200% 100%',
         animation: 'shimmer 1.5s infinite',
       }}/>
);

Object.assign(window, {
  scoreToVerdict, scoreColor, scoreToGlow, VERDICT_STYLE,
  GlassCard, VerdictBadge, GlowButton, AnimatedCounter, Shimmer,
});
