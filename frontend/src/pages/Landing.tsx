import { useEffect, useRef, useState, lazy, Suspense } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion, useInView } from 'framer-motion'
import { gsap } from 'gsap'
import { ScrollTrigger } from 'gsap/ScrollTrigger'
import {
  TrendingUp, BarChart2, Activity, Package, Newspaper,
  Shield, Zap, Globe, ChevronDown, ArrowRight,
} from 'lucide-react'
import { GlowButton } from '@/components/ui/GlowButton'
import { VerdictBadge } from '@/components/ui/VerdictBadge'
import { AnimatedCounter } from '@/components/ui/AnimatedCounter'
import { sampleReport } from '@/mocks/sampleReport'

gsap.registerPlugin(ScrollTrigger)

const Globe3D = lazy(() => import('@/components/three/Globe3D').then(m => ({ default: m.Globe3D })))

// ─── Agent card data ───────────────────────────────────────────────────────────
const AGENTS = [
  { name: 'Sales & Demand',     weight: 18, icon: TrendingUp, desc: 'FADA dispatches, EV Vahan data, dealer inventory signals' },
  { name: 'Fundamentals',       weight: 20, icon: BarChart2,  desc: 'Revenue/EBITDA, margins vs peers, FII/DII flow analysis' },
  { name: 'Pattern Analysis',   weight: 13, icon: Activity,   desc: 'RSI/MACD/Bollinger, support/resistance, 10yr seasonal cycles' },
  { name: 'Raw Materials',      weight: 10, icon: Package,    desc: 'Steel, aluminium, crude, polymers & commodity basket' },
  { name: 'Sentiment',          weight:  4, icon: Newspaper,  desc: 'News NLP, earnings call tone, social media signal scoring' },
  { name: 'Policy & Regulatory',weight: 10, icon: Shield,     desc: 'FAME EV subsidy, BS7/CAFE emission norms, PLI scheme impact' },
  { name: 'Competitive Intel',  weight: 10, icon: Zap,        desc: 'EV market share, new model pipeline, ADAS technology ratings' },
  { name: 'Risk & Macro',       weight: 15, icon: Globe,      desc: 'INR/USD exposure, RBI rate outlook, China supply chain risk' },
]

// ─── OEM data ─────────────────────────────────────────────────────────────────
const OEMS = [
  { ticker: 'MARUTI',     name: 'Maruti Suzuki',    score: 0.82, verdict: 'STRONG BUY' },
  { ticker: 'TATAMOTORS', name: 'Tata Motors',      score: 0.71, verdict: 'BUY' },
  { ticker: 'M&M',        name: 'Mahindra & Mahindra', score: 0.68, verdict: 'BUY' },
  { ticker: 'HEROMOTOCO', name: 'Hero MotoCorp',    score: 0.55, verdict: 'NEUTRAL' },
  { ticker: 'BAJAJ-AUTO', name: 'Bajaj Auto',       score: 0.63, verdict: 'BUY' },
  { ticker: 'EICHERMOT',  name: 'Eicher Motors',   score: 0.74, verdict: 'BUY' },
  { ticker: 'TVSMOTORS',  name: 'TVS Motor',        score: 0.60, verdict: 'BUY' },
  { ticker: 'ASHOKLEY',   name: 'Ashok Leyland',    score: 0.48, verdict: 'NEUTRAL' },
  { ticker: 'ESCORTS',    name: 'Escorts Kubota',   score: 0.42, verdict: 'SELL' },
  { ticker: 'FORCEMOT',   name: 'Force Motors',     score: 0.35, verdict: 'SELL' },
]

// ─── Demo typewriter ─────────────────────────────────────────────────────────
function DemoSection() {
  const [typedTicker, setTypedTicker] = useState('')
  const [agents, setAgents] = useState<string[]>([])
  const [showGauge, setShowGauge] = useState(false)
  const ref = useRef<HTMLDivElement>(null)
  const inView = useInView(ref, { once: true, amount: 0.4 })

  useEffect(() => {
    if (!inView) return
    let i = 0
    const target = 'MARUTI'
    const type = () => {
      if (i <= target.length) {
        setTypedTicker(target.slice(0, i++))
        setTimeout(type, 80)
      } else {
        // Reveal agents one by one
        let idx = 0
        const agentNames = AGENTS.map(a => a.name)
        const reveal = () => {
          if (idx < agentNames.length) {
            setAgents(prev => [...prev, agentNames[idx++]])
            setTimeout(reveal, 250)
          } else {
            setTimeout(() => setShowGauge(true), 400)
          }
        }
        reveal()
      }
    }
    type()
  }, [inView])

  return (
    <div ref={ref} className="grid grid-cols-1 lg:grid-cols-2 gap-12 items-center">
      {/* Left: typewriter */}
      <div className="glass-card p-6 font-mono text-sm">
        <div className="text-[var(--text-muted)] mb-4">$ stockagent analyze</div>
        <div className="mb-3">
          <span className="text-[var(--accent-cyan)]">ticker:</span>{' '}
          <span className="text-[var(--text-primary)]">{typedTicker}</span>
          {typedTicker.length < 6 && <span className="typewriter" />}
        </div>
        <div className="space-y-1">
          {agents.map((a, i) => (
            <motion.div
              key={a}
              initial={{ opacity: 0, x: -10 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: i * 0.05 }}
              className="text-[var(--text-secondary)] flex items-center gap-2"
            >
              <span className="text-[var(--accent-cyan)]">▶</span>
              <span>{a}...</span>
              {i < agents.length - 1 && (
                <span className="text-[var(--buy-strong)] ml-auto">✓ done</span>
              )}
            </motion.div>
          ))}
        </div>
      </div>
      {/* Right: gauge + verdict */}
      <div className="flex flex-col items-center gap-4">
        {showGauge && (
          <motion.div
            initial={{ opacity: 0, scale: 0.8 }}
            animate={{ opacity: 1, scale: 1 }}
            className="text-center"
          >
            <div className="text-6xl font-bold font-mono text-[var(--buy-strong)] mb-2">
              <AnimatedCounter target={sampleReport.final_score} decimals={2} trigger={showGauge} />
            </div>
            <div className="mb-4">
              <VerdictBadge verdict="STRONG BUY" size="lg" glow />
            </div>
            <div className="space-y-2 text-left">
              {sampleReport.conviction_drivers.slice(0, 3).map((d, i) => (
                <motion.div
                  key={i}
                  initial={{ opacity: 0, x: 20 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: 0.2 + i * 0.1 }}
                  className="flex gap-2 text-sm text-[var(--text-secondary)]"
                >
                  <span className="text-[var(--buy-strong)] flex-shrink-0">✓</span>
                  {d}
                </motion.div>
              ))}
            </div>
          </motion.div>
        )}
      </div>
    </div>
  )
}

// ─── Main Landing component ───────────────────────────────────────────────────
export function Landing() {
  const navigate = useNavigate()
  const agentsRef = useRef<HTMLDivElement>(null)
  const [mousePos, setMousePos] = useState({ x: 0, y: 0 })

  useEffect(() => {
    const onMove = (e: MouseEvent) => setMousePos({ x: e.clientX, y: e.clientY })
    window.addEventListener('mousemove', onMove)
    return () => window.removeEventListener('mousemove', onMove)
  }, [])

  useEffect(() => {
    if (!agentsRef.current) return
    const cards = agentsRef.current.querySelectorAll('.agent-card')
    cards.forEach((card, i) => {
      gsap.fromTo(
        card,
        { opacity: 0, x: i % 2 === 0 ? -60 : 60, y: 20 },
        {
          opacity: 1, x: 0, y: 0,
          duration: 0.6,
          delay: i * 0.05,
          ease: 'power3.out',
          scrollTrigger: { trigger: card, start: 'top 85%' },
        }
      )
    })
    return () => { ScrollTrigger.getAll().forEach(t => t.kill()) }
  }, [])

  return (
    <div className="min-h-screen bg-[var(--bg-base)] text-[var(--text-primary)]">

      {/* ── Top Nav ── */}
      <nav className="fixed top-0 inset-x-0 z-50 flex items-center justify-between px-6 py-4">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 rounded-lg bg-[var(--accent-cyan)] flex items-center justify-center">
            <TrendingUp className="w-5 h-5 text-[var(--bg-base)]" />
          </div>
          <span className="font-bold text-lg tracking-tight">StockAgent</span>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={() => navigate('/auth')}
            className="text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition-colors px-4 py-2 text-sm"
          >
            Sign In
          </button>
          <GlowButton onClick={() => navigate('/auth')} size="sm">
            Get Started →
          </GlowButton>
        </div>
      </nav>

      {/* ── SECTION A: Hero ── */}
      <section className="relative h-screen flex items-center justify-center overflow-hidden">
        {/* Globe background */}
        <div className="absolute inset-0">
          <Suspense fallback={<div className="w-full h-full bg-[var(--bg-base)]" />}>
            <Globe3D mousePos={mousePos} />
          </Suspense>
        </div>
        {/* Dark overlay */}
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_center,transparent_30%,var(--bg-base)_75%)]" />

        {/* Hero text */}
        <div className="relative z-10 text-center px-4 max-w-4xl mx-auto">
          <motion.div
            initial={{ opacity: 0, y: 30 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.8, delay: 0.2 }}
          >
            <div className="inline-flex items-center gap-2 glass-card px-4 py-2 mb-6 text-sm text-[var(--accent-cyan)]">
              <span className="w-2 h-2 rounded-full bg-[var(--buy-strong)] animate-pulse" />
              Live · 10 NSE/BSE Automobile Stocks
            </div>
            <h1 className="text-5xl sm:text-6xl lg:text-7xl font-black leading-tight mb-4">
              8 AI Agents.
              <br />
              <span className="text-[var(--accent-cyan)]">One Verdict.</span>
            </h1>
            <p className="text-lg sm:text-xl text-[var(--text-secondary)] mb-8 max-w-2xl mx-auto">
              AI-powered automobile stock intelligence for India's market.
              Sales, fundamentals, macro, sentiment — fused in seconds.
            </p>
            <div className="flex flex-col sm:flex-row gap-4 justify-center">
              <GlowButton onClick={() => navigate('/auth')} size="lg">
                Analyze a Stock Free <ArrowRight className="w-5 h-5" />
              </GlowButton>
              <GlowButton
                variant="outline"
                size="lg"
                onClick={() => document.getElementById('agents')?.scrollIntoView({ behavior: 'smooth' })}
              >
                See How It Works
              </GlowButton>
            </div>
          </motion.div>
        </div>

        {/* Scroll indicator */}
        <motion.div
          className="absolute bottom-8 left-1/2 -translate-x-1/2 flex flex-col items-center gap-2 text-[var(--text-muted)] text-sm"
          animate={{ y: [0, 8, 0] }}
          transition={{ repeat: Infinity, duration: 1.5 }}
        >
          <ChevronDown className="w-5 h-5" />
          <span>Scroll to explore</span>
        </motion.div>
      </section>

      {/* ── SECTION B: 8 Agents ── */}
      <section id="agents" className="py-24 px-4 sm:px-6 lg:px-12">
        <div className="max-w-6xl mx-auto">
          <div className="text-center mb-16">
            <h2 className="text-3xl sm:text-4xl font-black mb-4">
              8 Specialist Agents. <span className="text-[var(--accent-cyan)]">Zero Guesswork.</span>
            </h2>
            <p className="text-[var(--text-secondary)] max-w-2xl mx-auto">
              Each agent is tuned to a specific domain of automobile stock analysis.
              They run in parallel and vote — weighted by predictive power.
            </p>
          </div>
          <div ref={agentsRef} className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            {AGENTS.map((agent) => {
              const Icon = agent.icon
              return (
                <div
                  key={agent.name}
                  className="agent-card glass-card p-5 hover:scale-[1.03] transition-all duration-300 hover:border-[var(--border-glow)] group"
                >
                  {/* Weight bar at top */}
                  <div className="h-0.5 w-full bg-[var(--border-color)] rounded-full mb-4 overflow-hidden">
                    <div
                      className="h-full bg-[var(--accent-cyan)] rounded-full"
                      style={{ width: `${agent.weight * 3}%` }}
                    />
                  </div>
                  <div className="flex items-start justify-between mb-3">
                    <Icon className="w-6 h-6 text-[var(--accent-cyan)] group-hover:scale-110 transition-transform" />
                    <span className="text-xs font-mono font-bold text-[var(--accent-cyan)] bg-[rgba(6,182,212,0.1)] px-2 py-0.5 rounded-full">
                      {agent.weight}%
                    </span>
                  </div>
                  <h3 className="font-bold text-[var(--text-primary)] mb-2">{agent.name}</h3>
                  <p className="text-xs text-[var(--text-muted)] leading-relaxed">{agent.desc}</p>
                </div>
              )
            })}
          </div>
        </div>
      </section>

      {/* ── SECTION C: Live Demo ── */}
      <section className="py-24 px-4 sm:px-6 lg:px-12 bg-[rgba(6,182,212,0.02)]">
        <div className="max-w-6xl mx-auto">
          <div className="text-center mb-16">
            <h2 className="text-3xl sm:text-4xl font-black mb-4">
              See It <span className="text-[var(--accent-cyan)]">In Action</span>
            </h2>
            <p className="text-[var(--text-secondary)]">
              Watch 8 agents analyze Maruti Suzuki in real-time
            </p>
          </div>
          <DemoSection />
        </div>
      </section>

      {/* ── SECTION D: OEM Marquee ── */}
      <section className="py-24 overflow-hidden">
        <div className="max-w-6xl mx-auto px-4 text-center mb-12">
          <h2 className="text-3xl sm:text-4xl font-black mb-4">
            <span className="text-[var(--accent-cyan)]">10 Automobile OEMs</span> Covered
          </h2>
          <p className="text-[var(--text-secondary)]">All major NSE/BSE listed automobile manufacturers</p>
        </div>

        {/* Row 1 — left */}
        <div className="relative overflow-hidden mb-4">
          <div className="marquee-left flex gap-4 w-max">
            {[...OEMS, ...OEMS].map((oem, i) => (
              <OemBadge key={`${oem.ticker}-${i}`} oem={oem} />
            ))}
          </div>
        </div>
        {/* Row 2 — right */}
        <div className="relative overflow-hidden">
          <div className="marquee-right flex gap-4 w-max">
            {[...OEMS.slice().reverse(), ...OEMS.slice().reverse()].map((oem, i) => (
              <OemBadge key={`rev-${oem.ticker}-${i}`} oem={oem} />
            ))}
          </div>
        </div>
      </section>

      {/* ── SECTION E: CTA Footer ── */}
      <section className="py-24 px-4 text-center">
        <div className="max-w-2xl mx-auto">
          <h2 className="text-3xl sm:text-4xl font-black mb-4">
            Start analyzing in seconds.{' '}
            <span className="text-[var(--text-muted)]">No card required.</span>
          </h2>
          <p className="text-[var(--text-secondary)] mb-8">
            Free tier includes 10 analyses/month. No API keys needed.
          </p>
          <div className="flex flex-col sm:flex-row gap-4 justify-center">
            <GlowButton onClick={() => navigate('/auth')} size="lg">
              Create Free Account
            </GlowButton>
            <GlowButton variant="outline" size="lg" onClick={() => navigate('/auth')}>
              Sign In
            </GlowButton>
          </div>
        </div>
        <div className="mt-16 pt-8 border-t border-[var(--border-color)] text-[var(--text-muted)] text-sm flex items-center justify-center gap-6">
          <span>© 2026 StockAgent</span>
          <a href="https://github.com/RevanParimi/StockAgent" target="_blank" rel="noreferrer"
             className="hover:text-[var(--accent-cyan)] transition-colors">GitHub</a>
          <span>Built on NSE/BSE data</span>
        </div>
      </section>
    </div>
  )
}

function OemBadge({ oem }: { oem: (typeof OEMS)[0] }) {
  return (
    <div className="glass-card px-5 py-3 flex items-center gap-3 flex-shrink-0 hover:scale-105 transition-transform group">
      <div className="w-9 h-9 rounded-full bg-[rgba(6,182,212,0.15)] flex items-center justify-center font-bold text-sm text-[var(--accent-cyan)]">
        {oem.ticker.slice(0, 2)}
      </div>
      <div>
        <div className="text-sm font-semibold text-[var(--text-primary)]">{oem.name}</div>
        <div className="text-xs text-[var(--text-muted)]">{oem.ticker}</div>
      </div>
      <div className="ml-2 opacity-0 group-hover:opacity-100 transition-opacity text-right">
        <div className="text-xs font-mono text-[var(--text-secondary)]">{oem.score.toFixed(2)}</div>
        <VerdictBadge verdict={oem.verdict} size="sm" />
      </div>
    </div>
  )
}
