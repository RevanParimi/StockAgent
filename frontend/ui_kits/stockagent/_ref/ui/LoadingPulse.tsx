interface LoadingPulseProps {
  lines?: number
  className?: string
}

export function LoadingPulse({ lines = 3, className = '' }: LoadingPulseProps) {
  return (
    <div className={`space-y-3 ${className}`}>
      {Array.from({ length: lines }).map((_, i) => (
        <div
          key={i}
          className={`shimmer rounded-lg h-4 ${i === lines - 1 ? 'w-2/3' : 'w-full'}`}
        />
      ))}
    </div>
  )
}

export function CardSkeleton({ className = '' }: { className?: string }) {
  return (
    <div className={`glass-card p-4 ${className}`}>
      <div className="shimmer rounded h-5 w-1/3 mb-3" />
      <div className="shimmer rounded h-4 w-full mb-2" />
      <div className="shimmer rounded h-4 w-5/6 mb-2" />
      <div className="shimmer rounded h-4 w-2/3" />
    </div>
  )
}
