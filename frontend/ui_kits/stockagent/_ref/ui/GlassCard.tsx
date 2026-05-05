import type { ReactNode } from 'react'

interface GlassCardProps {
  children: ReactNode
  className?: string
  onClick?: () => void
  hover?: boolean
}

export function GlassCard({ children, className = '', onClick, hover = false }: GlassCardProps) {
  return (
    <div
      className={`glass-card p-4 transition-all duration-300 ${
        hover ? 'hover:scale-[1.02] hover:border-[var(--border-glow)] cursor-pointer' : ''
      } ${className}`}
      onClick={onClick}
    >
      {children}
    </div>
  )
}
