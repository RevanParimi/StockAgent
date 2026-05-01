import { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Zap, ChevronDown } from 'lucide-react'

interface ConflictsPanelProps {
  conflicts: string[]
}

export function ConflictsPanel({ conflicts }: ConflictsPanelProps) {
  const [open, setOpen] = useState(false)

  if (!conflicts.length) return null

  return (
    <div className="glass-card overflow-hidden">
      {/* Header */}
      <button
        onClick={() => setOpen((o) => !o)}
        className="w-full flex items-center justify-between px-5 py-4 text-left cursor-pointer hover:bg-[rgba(245,158,11,0.05)] transition-colors"
      >
        <div className="flex items-center gap-2">
          <Zap size={16} className="text-[#f59e0b]" />
          <span className="font-semibold text-[#f59e0b]">
            {conflicts.length} Conflict{conflicts.length > 1 ? 's' : ''} Resolved
          </span>
        </div>
        <motion.div
          animate={{ rotate: open ? 180 : 0 }}
          transition={{ duration: 0.2 }}
        >
          <ChevronDown size={16} className="text-[var(--text-muted)]" />
        </motion.div>
      </button>

      {/* Content */}
      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.25, ease: 'easeInOut' }}
            className="overflow-hidden"
          >
            <ul className="px-5 pb-4 space-y-3 border-t border-[rgba(245,158,11,0.2)]">
              {conflicts.map((c, i) => (
                <li
                  key={i}
                  className="flex gap-2 pt-3 text-sm text-[var(--text-secondary)] leading-relaxed"
                >
                  <span className="text-[#f59e0b] font-bold shrink-0">{i + 1}.</span>
                  <span>{c}</span>
                </li>
              ))}
            </ul>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
