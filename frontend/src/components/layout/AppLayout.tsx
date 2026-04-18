import type { ReactNode } from 'react'
import { MarketBar } from './MarketBar'
import { Sidebar } from './Sidebar'

export function AppLayout({ children }: { children: ReactNode }) {
  return (
    <>
      <MarketBar />
      <Sidebar />
      <main
        className="min-h-screen bg-[var(--bg-base)]"
        style={{ marginLeft: 72, paddingTop: 48 }}
      >
        {children}
      </main>
    </>
  )
}
