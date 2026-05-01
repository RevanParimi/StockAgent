import { useState } from 'react'
import { ChevronDown, Plus, Pencil, Trash2, Check, X } from 'lucide-react'
import { useWatchlist } from '@/hooks/useWatchlist'

export function WatchlistManager() {
  const { lists, activeList, setActive, create, rename, destroy } = useWatchlist()

  const [dropdownOpen, setDropdownOpen] = useState(false)
  const [renaming,     setRenaming]     = useState(false)
  const [newName,      setNewName]      = useState('')
  const [creating,     setCreating]     = useState(false)
  const [createName,   setCreateName]   = useState('')

  function commitCreate() {
    const n = createName.trim()
    if (n && !lists.includes(n)) create(n)
    setCreateName('')
    setCreating(false)
  }

  function commitRename() {
    const n = newName.trim()
    if (n && n !== activeList) rename(activeList, n)
    setNewName('')
    setRenaming(false)
  }

  function handleDelete() {
    if (lists.length > 1) destroy(activeList)
  }

  return (
    <div className="flex items-center gap-2 flex-wrap">
      {/* Dropdown selector */}
      <div className="relative">
        <button
          className="flex items-center gap-2 px-3 py-1.5 rounded-lg glass-card text-sm font-semibold text-[var(--text-primary)] hover:border-[var(--border-glow)] transition-all"
          onClick={() => setDropdownOpen(d => !d)}
        >
          {activeList}
          <ChevronDown size={14} className={`transition-transform ${dropdownOpen ? 'rotate-180' : ''}`} />
        </button>

        {dropdownOpen && (
          <div className="absolute top-10 left-0 glass-card py-1 min-w-[180px] z-20 shadow-xl">
            {lists.map(name => (
              <button
                key={name}
                className={`w-full text-left px-3 py-2 text-sm transition-colors hover:bg-[rgba(255,255,255,0.05)]
                  ${name === activeList ? 'text-[var(--accent-cyan)]' : 'text-[var(--text-primary)]'}`}
                onClick={() => { setActive(name); setDropdownOpen(false) }}
              >
                {name}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Create */}
      {creating ? (
        <div className="flex items-center gap-1">
          <input
            autoFocus
            className="px-2 py-1 text-sm rounded-lg bg-[var(--bg-elevated)] border border-[var(--border-glow)] text-[var(--text-primary)] outline-none w-28"
            placeholder="List name"
            value={createName}
            onChange={e => setCreateName(e.target.value)}
            onKeyDown={e => {
              if (e.key === 'Enter') commitCreate()
              if (e.key === 'Escape') setCreating(false)
            }}
          />
          <button onClick={commitCreate} className="p-1 text-[var(--buy-strong)] hover:opacity-80"><Check size={14} /></button>
          <button onClick={() => setCreating(false)} className="p-1 text-[var(--text-muted)] hover:opacity-80"><X size={14} /></button>
        </div>
      ) : (
        <button
          onClick={() => setCreating(true)}
          className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-xs text-[var(--accent-cyan)] hover:bg-[rgba(6,182,212,0.08)] transition-colors"
        >
          <Plus size={13} /> Create
        </button>
      )}

      {/* Rename */}
      {renaming ? (
        <div className="flex items-center gap-1">
          <input
            autoFocus
            className="px-2 py-1 text-sm rounded-lg bg-[var(--bg-elevated)] border border-[var(--border-glow)] text-[var(--text-primary)] outline-none w-28"
            placeholder="New name"
            value={newName}
            onChange={e => setNewName(e.target.value)}
            onKeyDown={e => {
              if (e.key === 'Enter') commitRename()
              if (e.key === 'Escape') setRenaming(false)
            }}
          />
          <button onClick={commitRename} className="p-1 text-[var(--buy-strong)] hover:opacity-80"><Check size={14} /></button>
          <button onClick={() => setRenaming(false)} className="p-1 text-[var(--text-muted)] hover:opacity-80"><X size={14} /></button>
        </div>
      ) : (
        <button
          onClick={() => { setNewName(activeList); setRenaming(true) }}
          className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-xs text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[rgba(255,255,255,0.04)] transition-colors"
        >
          <Pencil size={13} /> Rename
        </button>
      )}

      {/* Delete */}
      <button
        onClick={handleDelete}
        disabled={lists.length <= 1}
        className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-xs text-[var(--text-muted)] hover:text-red-400 hover:bg-[rgba(239,68,68,0.07)] transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
      >
        <Trash2 size={13} /> Delete
      </button>
    </div>
  )
}
