import { useState, lazy, Suspense } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import { Eye, EyeOff, TrendingUp, Check } from 'lucide-react'
import { GlowButton } from '@/components/ui/GlowButton'
import { GlassCard } from '@/components/ui/GlassCard'
import { VerdictBadge } from '@/components/ui/VerdictBadge'
import { useStore } from '@/store'
import { TICKERS, TICKER_NAMES } from '@/types'
import type { User } from '@/types'

const ParticleField = lazy(() =>
  import('@/components/three/ParticleField').then(m => ({ default: m.ParticleField }))
)

// ── Password strength ─────────────────────────────────────────────────────────
function passwordStrength(p: string): { label: string; color: string; width: string } {
  if (p.length === 0) return { label: '', color: '', width: '0%' }
  let score = 0
  if (p.length >= 8) score++
  if (/[A-Z]/.test(p)) score++
  if (/[0-9]/.test(p)) score++
  if (/[^A-Za-z0-9]/.test(p)) score++
  const map = [
    { label: 'Weak',     color: 'var(--sell-strong)', width: '25%' },
    { label: 'Fair',     color: 'var(--sell)',         width: '50%' },
    { label: 'Good',     color: 'var(--neutral-color)',width: '75%' },
    { label: 'Strong',   color: 'var(--buy-strong)',   width: '100%' },
  ]
  return map[Math.min(score, 3)]
}

// ── Floating demo cards ───────────────────────────────────────────────────────
const DEMO_CARDS = [
  { ticker: 'MARUTI',     score: 0.82, verdict: 'STRONG BUY' },
  { ticker: 'M&M',        score: 0.71, verdict: 'BUY' },
  { ticker: 'BAJAJ-AUTO', score: 0.63, verdict: 'BUY' },
]

// ── Step indicators ───────────────────────────────────────────────────────────
function StepDots({ step, total }: { step: number; total: number }) {
  return (
    <div className="flex gap-2 justify-center mb-6">
      {Array.from({ length: total }).map((_, i) => (
        <div
          key={i}
          className={`h-1.5 rounded-full transition-all duration-300 ${
            i < step ? 'w-6 bg-[var(--accent-cyan)]' :
            i === step ? 'w-4 bg-[var(--accent-cyan)] opacity-60' :
            'w-2 bg-[var(--border-glow)]'
          }`}
        />
      ))}
    </div>
  )
}

// ── Input component ───────────────────────────────────────────────────────────
function Input({
  label, type = 'text', value, onChange, placeholder, rightEl,
}: {
  label: string
  type?: string
  value: string
  onChange: (v: string) => void
  placeholder?: string
  rightEl?: React.ReactNode
}) {
  return (
    <div className="mb-4">
      <label className="block text-sm text-[var(--text-secondary)] mb-1.5">{label}</label>
      <div className="relative">
        <input
          type={type}
          value={value}
          onChange={e => onChange(e.target.value)}
          placeholder={placeholder}
          className="w-full bg-[var(--bg-elevated)] border border-[var(--border-color)] rounded-xl px-4 py-3
            text-[var(--text-primary)] placeholder-[var(--text-muted)] text-sm
            focus:outline-none focus:border-[var(--accent-cyan)] focus:ring-1 focus:ring-[var(--accent-cyan)]
            transition-colors"
        />
        {rightEl && (
          <div className="absolute right-3 top-1/2 -translate-y-1/2">{rightEl}</div>
        )}
      </div>
    </div>
  )
}

// ── Sign In form ──────────────────────────────────────────────────────────────
function SignInForm({ onSwitch }: { onSwitch: () => void }) {
  const [email, setEmail]       = useState('')
  const [password, setPassword] = useState('')
  const [showPw, setShowPw]     = useState(false)
  const navigate = useNavigate()
  const login = useStore(s => s.login)

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!email || !password) return
    // Mock auth — accept any email/password
    login({ name: email.split('@')[0], email, tickers: ['MARUTI', 'TATAMOTORS'], preferences: { dailyAnalysis: true, scoreDropAlerts: true, darkMode: true } })
    navigate('/dashboard')
  }

  return (
    <form onSubmit={handleSubmit}>
      <Input label="Email" type="email" value={email} onChange={setEmail} placeholder="you@example.com" />
      <Input
        label="Password"
        type={showPw ? 'text' : 'password'}
        value={password}
        onChange={setPassword}
        placeholder="••••••••"
        rightEl={
          <button type="button" onClick={() => setShowPw(p => !p)}
            className="text-[var(--text-muted)] hover:text-[var(--text-secondary)] transition-colors">
            {showPw ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
          </button>
        }
      />
      <div className="text-right mb-4">
        <button type="button" className="text-xs text-[var(--accent-cyan)] hover:underline">
          Forgot password?
        </button>
      </div>
      <GlowButton type="submit" className="w-full mb-4">Sign In</GlowButton>

      <div className="flex items-center gap-3 mb-4">
        <div className="flex-1 h-px bg-[var(--border-color)]" />
        <span className="text-xs text-[var(--text-muted)]">or continue with</span>
        <div className="flex-1 h-px bg-[var(--border-color)]" />
      </div>

      <div className="grid grid-cols-2 gap-3 mb-6">
        {['Google', 'GitHub'].map(p => (
          <button key={p} type="button"
            onClick={() => alert('OAuth coming soon')}
            className="glass-card py-2.5 text-sm text-[var(--text-secondary)] hover:text-[var(--text-primary)]
              hover:border-[var(--border-glow)] transition-all rounded-xl">
            {p}
          </button>
        ))}
      </div>

      <p className="text-center text-sm text-[var(--text-muted)]">
        Don't have an account?{' '}
        <button type="button" onClick={onSwitch} className="text-[var(--accent-cyan)] hover:underline">
          Sign up →
        </button>
      </p>
    </form>
  )
}

// ── Sign Up form ──────────────────────────────────────────────────────────────
function SignUpForm({ onSwitch }: { onSwitch: () => void }) {
  const [step, setStep] = useState(0)
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [showPw, setShowPw] = useState(false)
  const [selectedTickers, setSelectedTickers] = useState<string[]>([])
  const [prefs, setPrefs] = useState({ dailyAnalysis: true, scoreDropAlerts: true, darkMode: true })
  const navigate = useNavigate()
  const login = useStore(s => s.login)

  const pw = passwordStrength(password)

  const toggleTicker = (t: string) =>
    setSelectedTickers(prev => prev.includes(t) ? prev.filter(x => x !== t) : [...prev, t])

  const togglePref = (key: keyof typeof prefs) =>
    setPrefs(p => ({ ...p, [key]: !p[key] }))

  const handleCreate = () => {
    const user: User = {
      name, email,
      tickers: selectedTickers.length ? selectedTickers : ['MARUTI'],
      preferences: prefs,
    }
    login(user)
    navigate('/dashboard')
  }

  const STEPS = [
    // Step 0 — Account
    <div key="account">
      <Input label="Full name" value={name} onChange={setName} placeholder="Ravi Kumar" />
      <Input label="Email" type="email" value={email} onChange={setEmail} placeholder="you@example.com" />
      <Input
        label="Password"
        type={showPw ? 'text' : 'password'}
        value={password}
        onChange={setPassword}
        placeholder="At least 8 characters"
        rightEl={
          <button type="button" onClick={() => setShowPw(p => !p)}
            className="text-[var(--text-muted)] hover:text-[var(--text-secondary)] transition-colors">
            {showPw ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
          </button>
        }
      />
      {password && (
        <div className="mb-4 -mt-2">
          <div className="h-1 bg-[var(--border-color)] rounded-full overflow-hidden mb-1">
            <div className="h-full rounded-full transition-all duration-500"
              style={{ width: pw.width, background: pw.color }} />
          </div>
          <span className="text-xs" style={{ color: pw.color }}>{pw.label}</span>
        </div>
      )}
      <Input label="Confirm password" type="password" value={confirm} onChange={setConfirm} />
      <GlowButton
        onClick={() => setStep(1)}
        disabled={!name || !email || !password || password !== confirm}
        className="w-full"
      >
        Next →
      </GlowButton>
    </div>,

    // Step 1 — Pick tickers
    <div key="tickers">
      <p className="text-[var(--text-secondary)] text-sm mb-4">Which stocks do you want to watch?</p>
      <div className="grid grid-cols-2 gap-2 mb-6">
        {TICKERS.map(t => (
          <button
            key={t}
            type="button"
            onClick={() => toggleTicker(t)}
            className={`flex items-center gap-2 p-3 rounded-xl border text-sm transition-all ${
              selectedTickers.includes(t)
                ? 'border-[var(--accent-cyan)] bg-[rgba(6,182,212,0.1)] text-[var(--text-primary)]'
                : 'border-[var(--border-color)] text-[var(--text-muted)] hover:border-[var(--border-glow)]'
            }`}
          >
            {selectedTickers.includes(t) && <Check className="w-3 h-3 text-[var(--accent-cyan)] flex-shrink-0" />}
            <div className="text-left">
              <div className="font-mono font-bold text-xs">{t}</div>
              <div className="text-xs opacity-70 truncate">{TICKER_NAMES[t]?.split(' ').slice(0,2).join(' ')}</div>
            </div>
          </button>
        ))}
      </div>
      <div className="flex gap-3">
        <GlowButton variant="outline" onClick={() => setStep(0)} className="flex-1">← Back</GlowButton>
        <GlowButton onClick={() => setStep(2)} className="flex-1">Next →</GlowButton>
      </div>
    </div>,

    // Step 2 — Preferences
    <div key="prefs">
      <p className="text-[var(--text-secondary)] text-sm mb-4">Customize your experience</p>
      <div className="space-y-4 mb-6">
        {(Object.entries(prefs) as [keyof typeof prefs, boolean][]).map(([key, val]) => {
          const labels: Record<keyof typeof prefs, string> = {
            dailyAnalysis: 'Enable daily scheduled analysis (8:30am IST)',
            scoreDropAlerts: 'Score drop alerts (when score falls >0.10)',
            darkMode: 'Dark mode',
          }
          return (
            <label key={key} className="flex items-center justify-between cursor-pointer">
              <span className="text-sm text-[var(--text-secondary)]">{labels[key]}</span>
              <button
                type="button"
                onClick={() => togglePref(key)}
                className={`relative w-10 h-5 rounded-full transition-colors ${
                  val ? 'bg-[var(--accent-cyan)]' : 'bg-[var(--border-glow)]'
                }`}
              >
                <span
                  className={`absolute top-0.5 w-4 h-4 bg-white rounded-full shadow transition-transform ${
                    val ? 'translate-x-5' : 'translate-x-0.5'
                  }`}
                />
              </button>
            </label>
          )
        })}
      </div>
      <div className="flex gap-3">
        <GlowButton variant="outline" onClick={() => setStep(1)} className="flex-1">← Back</GlowButton>
        <GlowButton onClick={handleCreate} className="flex-1">Create Account →</GlowButton>
      </div>
    </div>,
  ]

  return (
    <div>
      <StepDots step={step} total={3} />
      <AnimatePresence mode="wait">
        <motion.div
          key={step}
          initial={{ opacity: 0, x: 20 }}
          animate={{ opacity: 1, x: 0 }}
          exit={{ opacity: 0, x: -20 }}
          transition={{ duration: 0.2 }}
        >
          {STEPS[step]}
        </motion.div>
      </AnimatePresence>
      <p className="text-center text-sm text-[var(--text-muted)] mt-4">
        Already have an account?{' '}
        <button type="button" onClick={onSwitch} className="text-[var(--accent-cyan)] hover:underline">
          Sign in →
        </button>
      </p>
    </div>
  )
}

// ── Main Auth page ────────────────────────────────────────────────────────────
export function Auth() {
  const [tab, setTab] = useState<'signin' | 'signup'>('signin')

  return (
    <div className="h-screen flex overflow-hidden bg-[var(--bg-base)]">

      {/* Left panel */}
      <div className="hidden lg:flex lg:w-2/5 relative flex-col items-center justify-center overflow-hidden">
        <div className="absolute inset-0">
          <Suspense fallback={<div className="w-full h-full" />}>
            <ParticleField />
          </Suspense>
        </div>
        <div className="absolute inset-0 bg-gradient-to-r from-transparent to-[var(--bg-base)]" />
        <div className="relative z-10 text-center px-8">
          <div className="flex items-center justify-center gap-2 mb-4">
            <div className="w-10 h-10 rounded-xl bg-[var(--accent-cyan)] flex items-center justify-center">
              <TrendingUp className="w-6 h-6 text-[var(--bg-base)]" />
            </div>
            <span className="text-2xl font-black">StockAgent</span>
          </div>
          <p className="text-[var(--text-secondary)] text-sm mb-8">
            AI-Powered Indian Auto Stock Intelligence
          </p>
          {/* Floating demo cards */}
          <div className="space-y-3">
            {DEMO_CARDS.map((c, i) => (
              <motion.div
                key={c.ticker}
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.5 + i * 0.2 }}
                className="glass-card px-4 py-2.5 flex items-center justify-between text-sm float"
                style={{ animationDelay: `${i * 0.5}s` }}
              >
                <span className="font-mono font-bold text-[var(--accent-cyan)]">{c.ticker}</span>
                <span className="font-mono text-[var(--text-primary)]">{c.score.toFixed(2)}</span>
                <VerdictBadge verdict={c.verdict} size="sm" glow />
              </motion.div>
            ))}
          </div>
        </div>
      </div>

      {/* Right panel */}
      <div className="flex-1 flex items-center justify-center px-4 sm:px-8 overflow-y-auto py-8">
        <div className="w-full max-w-md">
          <GlassCard className="p-8">
            {/* Tabs */}
            <div className="flex gap-1 mb-8 glass-card p-1">
              {(['signin', 'signup'] as const).map(t => (
                <button
                  key={t}
                  onClick={() => setTab(t)}
                  className={`flex-1 py-2 text-sm font-semibold rounded-xl transition-all ${
                    tab === t
                      ? 'bg-[var(--accent-cyan)] text-[var(--bg-base)]'
                      : 'text-[var(--text-muted)] hover:text-[var(--text-secondary)]'
                  }`}
                >
                  {t === 'signin' ? 'Sign In' : 'Sign Up'}
                </button>
              ))}
            </div>

            <AnimatePresence mode="wait">
              <motion.div
                key={tab}
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.15 }}
              >
                {tab === 'signin'
                  ? <SignInForm onSwitch={() => setTab('signup')} />
                  : <SignUpForm onSwitch={() => setTab('signin')} />
                }
              </motion.div>
            </AnimatePresence>
          </GlassCard>
        </div>
      </div>
    </div>
  )
}
