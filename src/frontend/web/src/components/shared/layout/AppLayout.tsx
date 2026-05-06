import type { ReactNode } from 'react'
import { MarketBar } from './MarketBar'
import { Sidebar } from './Sidebar'
import { BottomNav } from './BottomNav'

export function AppLayout({ children }: { children: ReactNode }) {
  return (
    <>
      <MarketBar />
      {/* Sidebar: hidden on mobile (md:flex), shown on md+ */}
      <div className="hidden md:block">
        <Sidebar />
      </div>
      <main
        className="min-h-screen bg-[var(--bg-base)]"
        style={{
          // On mobile: no left margin (sidebar hidden), extra bottom padding for BottomNav
          paddingTop: 48,
        }}
      >
        {/* Desktop: push right of 72px sidebar */}
        <div className="md:ml-[72px] pb-20 md:pb-0">
          {children}
        </div>
      </main>
      {/* Mobile bottom tab bar */}
      <BottomNav />
    </>
  )
}
