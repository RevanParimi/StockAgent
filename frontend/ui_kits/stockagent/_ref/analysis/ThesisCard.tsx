import { useState } from 'react'
import { Copy, Check } from 'lucide-react'

interface ThesisCardProps {
  thesis: string
}

export function ThesisCard({ thesis }: ThesisCardProps) {
  const [copied, setCopied] = useState(false)

  async function handleCopy() {
    try {
      await navigator.clipboard.writeText(thesis)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      // clipboard not available
    }
  }

  const paragraphs = thesis.split('\n').filter((p) => p.trim())

  return (
    <div className="glass-card p-6">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-semibold text-[var(--text-primary)]">
          Investment Thesis
        </h3>
        <button
          onClick={handleCopy}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium
            text-[var(--text-muted)] hover:text-[var(--text-primary)]
            bg-[rgba(255,255,255,0.05)] hover:bg-[rgba(255,255,255,0.09)]
            border border-[var(--border-color)] transition-all duration-150 cursor-pointer"
        >
          {copied ? (
            <>
              <Check size={13} className="text-[#22c55e]" />
              Copied
            </>
          ) : (
            <>
              <Copy size={13} />
              Copy
            </>
          )}
        </button>
      </div>

      <div className="space-y-4">
        {paragraphs.map((p, i) => (
          <p
            key={i}
            className="text-[var(--text-secondary)] text-base leading-[1.8]"
          >
            {p}
          </p>
        ))}
      </div>
    </div>
  )
}
