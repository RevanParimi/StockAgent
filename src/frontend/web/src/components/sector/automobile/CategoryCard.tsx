import React from 'react'
import type { CategoryItem } from '@/types/api'

interface Props {
  category: CategoryItem
  onClick:  () => void
}

export function CategoryCard({ category: c, onClick }: Props) {
  return (
    <button
      onClick={onClick}
      style={{ background: 'var(--bg-surface)', border: '1px solid var(--border)',
               borderRadius: 16, padding: 18, textAlign: 'left', cursor: 'pointer',
               transition: 'transform .15s, box-shadow .15s' }}
      onMouseEnter={e => { (e.currentTarget as HTMLElement).style.transform = 'translateY(-2px)' }}
      onMouseLeave={e => { (e.currentTarget as HTMLElement).style.transform = '' }}
    >
      <div style={{
        width: 40, height: 40, borderRadius: 10, marginBottom: 10,
        background: `color-mix(in oklab, ${c.color} 12%, transparent)`,
        color: c.color, display: 'grid', placeItems: 'center', fontSize: 20,
      }}>{c.icon}</div>
      <div style={{ fontSize: 13, fontWeight: 700 }}>{c.label}</div>
      <div style={{ fontSize: 11, color: 'var(--ink-3)', marginTop: 2 }}>{c.count} stocks</div>
    </button>
  )
}
