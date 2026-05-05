import { NavLink } from 'react-router-dom'
import { LayoutDashboard, Search, Star, History, Settings } from 'lucide-react'

const NAV_ITEMS = [
  { to: '/dashboard', icon: LayoutDashboard, label: 'Dashboard' },
  { to: '/analyze',   icon: Search,          label: 'Analyze'   },
  { to: '/watchlist', icon: Star,            label: 'Watchlist' },
  { to: '/history',   icon: History,         label: 'History'   },
  { to: '/settings',  icon: Settings,        label: 'Settings'  },
]

export function BottomNav() {
  return (
    <nav
      className="fixed bottom-0 left-0 right-0 z-50 flex md:hidden"
      style={{
        background: 'rgba(5,8,16,0.97)',
        backdropFilter: 'blur(20px)',
        WebkitBackdropFilter: 'blur(20px)',
        borderTop: '1px solid rgba(30,41,59,0.8)',
        paddingBottom: 'env(safe-area-inset-bottom)',
      }}
      aria-label="Mobile navigation"
    >
      {NAV_ITEMS.map(({ to, icon: Icon, label }) => (
        <NavLink
          key={to}
          to={to}
          className={({ isActive }) =>
            `flex-1 flex flex-col items-center justify-center gap-1 py-2 text-[10px] font-medium
             transition-colors duration-150
             ${isActive
               ? 'text-[var(--accent-cyan)]'
               : 'text-[var(--text-muted)] hover:text-[var(--text-secondary)]'
             }`
          }
          aria-label={label}
        >
          {({ isActive }) => (
            <>
              <Icon
                size={20}
                strokeWidth={isActive ? 2.5 : 1.75}
              />
              <span>{label}</span>
            </>
          )}
        </NavLink>
      ))}
    </nav>
  )
}
