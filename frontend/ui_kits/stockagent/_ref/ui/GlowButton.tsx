import type { ReactNode, ButtonHTMLAttributes } from 'react'

interface GlowButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  children: ReactNode
  variant?: 'cyan' | 'blue' | 'violet' | 'outline'
  size?: 'sm' | 'md' | 'lg'
}

const VARIANT_STYLES = {
  cyan:    'bg-[var(--accent-cyan)] text-[var(--bg-base)] hover:shadow-[0_0_24px_rgba(6,182,212,0.5)] hover:brightness-110',
  blue:    'bg-[var(--accent-blue)] text-white hover:shadow-[0_0_24px_rgba(59,130,246,0.5)] hover:brightness-110',
  violet:  'bg-[var(--accent-violet)] text-white hover:shadow-[0_0_24px_rgba(139,92,246,0.5)] hover:brightness-110',
  outline: 'bg-transparent border border-[var(--accent-cyan)] text-[var(--accent-cyan)] hover:bg-[rgba(6,182,212,0.1)] hover:shadow-[0_0_16px_rgba(6,182,212,0.3)]',
}

const SIZE_STYLES = {
  sm: 'px-4 py-2 text-sm',
  md: 'px-6 py-2.5 text-base',
  lg: 'px-8 py-3.5 text-lg',
}

export function GlowButton({
  children,
  variant = 'cyan',
  size = 'md',
  className = '',
  disabled,
  ...props
}: GlowButtonProps) {
  return (
    <button
      className={`
        inline-flex items-center justify-center gap-2 font-semibold rounded-xl
        transition-all duration-200 cursor-pointer select-none
        disabled:opacity-50 disabled:cursor-not-allowed disabled:shadow-none
        ${VARIANT_STYLES[variant]} ${SIZE_STYLES[size]} ${className}
      `}
      disabled={disabled}
      {...props}
    >
      {children}
    </button>
  )
}
