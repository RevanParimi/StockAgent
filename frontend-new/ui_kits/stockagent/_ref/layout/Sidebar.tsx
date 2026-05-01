import { useState } from 'react'
import { NavLink, useNavigate } from 'react-router-dom'
import { LayoutDashboard, Search, Star, History, Settings, LogOut } from 'lucide-react'
import { useStore } from '@/store'

const NAV_ITEMS = [
  { to: '/dashboard', icon: LayoutDashboard, label: 'Dashboard' },
  { to: '/analyze',   icon: Search,          label: 'Analyze'   },
  { to: '/watchlist', icon: Star,            label: 'Watchlist' },
  { to: '/history',   icon: History,         label: 'History'   },
  { to: '/settings',  icon: Settings,        label: 'Settings'  },
]

export function Sidebar() {
  const [expanded, setExpanded] = useState(false)
  const user     = useStore(s => s.user)
  const logout   = useStore(s => s.logout)
  const navigate = useNavigate()

  const initials = user?.name
    ? user.name.split(' ').map(w => w[0]).join('').slice(0, 2).toUpperCase()
    : 'SA'

  function handleLogout() {
    logout()
    navigate('/auth')
  }

  return (
    <aside
      className="fixed left-0 top-[48px] bottom-0 z-40 flex flex-col"
      style={{
        width: expanded ? 220 : 72,
        transition: 'width 300ms ease',
        background: 'rgba(5,8,16,0.96)',
        backdropFilter: 'blur(20px)',
        WebkitBackdropFilter: 'blur(20px)',
        borderRight: '1px solid rgba(30,41,59,0.8)',
      }}
      onMouseEnter={() => setExpanded(true)}
      onMouseLeave={() => setExpanded(false)}
    >
      {/* Logo */}
      <div
        className="flex items-center gap-3 px-4 border-b border-[var(--border-color)] flex-shrink-0"
        style={{ height: 56 }}
      >
        <div
          className="w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0 font-bold text-sm"
          style={{ background: 'var(--accent-cyan)', color: 'var(--bg-base)' }}
        >
          S
        </div>
        <span
          className="font-bold text-[var(--text-primary)] whitespace-nowrap overflow-hidden"
          style={{
            maxWidth: expanded ? 140 : 0,
            opacity: expanded ? 1 : 0,
            transition: 'max-width 300ms ease, opacity 250ms ease',
          }}
        >
          StockAgent
        </span>
      </div>

      {/* Nav */}
      <nav className="flex-1 py-3 flex flex-col gap-0.5 overflow-hidden">
        {NAV_ITEMS.map(({ to, icon: Icon, label }) => (
          <NavLink
            key={to}
            to={to}
            className={({ isActive }) =>
              `flex items-center gap-3 px-[22px] py-3 relative transition-all duration-150
               ${isActive
                 ? 'text-[var(--accent-cyan)]'
                 : 'text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[rgba(255,255,255,0.04)]'
               }`
            }
          >
            {({ isActive }) => (
              <>
                {isActive && (
                  <span
                    className="absolute left-0 top-1/2 -translate-y-1/2 w-[3px] h-6 rounded-r"
                    style={{
                      background: 'var(--accent-cyan)',
                      boxShadow: '0 0 8px rgba(6,182,212,0.7)',
                    }}
                  />
                )}
                <Icon size={20} className="flex-shrink-0" />
                <span
                  className="text-sm font-medium whitespace-nowrap overflow-hidden"
                  style={{
                    maxWidth: expanded ? 140 : 0,
                    opacity: expanded ? 1 : 0,
                    transition: 'max-width 300ms ease, opacity 250ms ease',
                  }}
                >
                  {label}
                </span>
              </>
            )}
          </NavLink>
        ))}
      </nav>

      {/* User + Logout */}
      <div className="border-t border-[var(--border-color)] py-3 flex-shrink-0">
        <div className="flex items-center gap-3 px-[18px] py-2">
          <div
            className="w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0 font-bold text-xs"
            style={{
              background: 'linear-gradient(135deg, var(--accent-cyan), var(--accent-violet))',
              color: 'var(--bg-base)',
            }}
          >
            {initials}
          </div>
          <div
            className="overflow-hidden"
            style={{
              maxWidth: expanded ? 120 : 0,
              opacity: expanded ? 1 : 0,
              transition: 'max-width 300ms ease, opacity 250ms ease',
            }}
          >
            <div className="text-xs font-semibold text-[var(--text-primary)] whitespace-nowrap truncate">
              {user?.name ?? 'Guest'}
            </div>
            <div className="text-[10px] text-[var(--text-muted)] whitespace-nowrap truncate">
              {user?.email ?? ''}
            </div>
          </div>
        </div>

        <button
          onClick={handleLogout}
          className="flex items-center gap-3 px-[22px] py-2.5 w-full text-[var(--text-muted)] hover:text-red-400 hover:bg-[rgba(239,68,68,0.07)] transition-all duration-150"
        >
          <LogOut size={18} className="flex-shrink-0" />
          <span
            className="text-sm whitespace-nowrap overflow-hidden"
            style={{
              maxWidth: expanded ? 100 : 0,
              opacity: expanded ? 1 : 0,
              transition: 'max-width 300ms ease, opacity 250ms ease',
            }}
          >
            Logout
          </span>
        </button>
      </div>
    </aside>
  )
}
