import { motion, type Variants } from 'framer-motion'
import { CheckCircle2, XCircle } from 'lucide-react'

interface ConvictionPanelProps {
  drivers: string[]
  risks: string[]
}

const containerVariants: Variants = {
  hidden: {},
  visible: { transition: { staggerChildren: 0.08 } },
}

const itemVariants: Variants = {
  hidden: { opacity: 0, x: -12 },
  visible: { opacity: 1, x: 0, transition: { duration: 0.35 } },
}

export function ConvictionPanel({ drivers, risks }: ConvictionPanelProps) {
  return (
    <div className="glass-card p-5 space-y-6 h-full">
      {/* Drivers */}
      <div>
        <div className="flex items-center gap-2 mb-3">
          <CheckCircle2 size={18} className="text-[#22c55e]" />
          <h3 className="font-semibold text-[var(--text-primary)]">Conviction Drivers</h3>
        </div>
        <motion.ul
          className="space-y-3"
          variants={containerVariants}
          initial="hidden"
          animate="visible"
        >
          {drivers.map((d, i) => (
            <motion.li key={i} variants={itemVariants} className="flex gap-2">
              <span className="text-[#22c55e] font-bold mt-0.5 shrink-0">✓</span>
              <span className="text-[var(--text-secondary)] text-sm leading-relaxed">{d}</span>
            </motion.li>
          ))}
        </motion.ul>
      </div>

      {/* Divider */}
      <div className="border-t border-[var(--border-color)]" />

      {/* Risks */}
      <div>
        <div className="flex items-center gap-2 mb-3">
          <XCircle size={18} className="text-[#ef4444]" />
          <h3 className="font-semibold text-[var(--text-primary)]">Top Risks</h3>
        </div>
        <motion.ul
          className="space-y-3"
          variants={containerVariants}
          initial="hidden"
          animate="visible"
        >
          {risks.map((r, i) => (
            <motion.li key={i} variants={itemVariants} className="flex gap-2">
              <span className="text-[#ef4444] font-bold mt-0.5 shrink-0">✗</span>
              <span className="text-[var(--text-secondary)] text-sm leading-relaxed">{r}</span>
            </motion.li>
          ))}
        </motion.ul>
      </div>
    </div>
  )
}
