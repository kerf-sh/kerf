/**
 * IesProfilePicker — inline picker for built-in IES light profiles.
 *
 * Displays the 12 IES_PRESETS grouped by category. The caller receives the
 * selected preset object via onSelect(preset). The component is fully
 * controlled: the active selection is communicated back through onSelect,
 * not held internally.
 *
 * Props:
 *   onSelect(preset)  — called with the clicked IES_PRESETS entry.
 *   selectedSlug      — slug of the currently active preset (or null/undefined).
 *   className         — extra CSS classes for the root container.
 */

import { useMemo, useState } from 'react'
import { Search } from 'lucide-react'
import { IES_PRESETS } from '../lib/iesPresets.js'

const CATEGORY_LABELS = {
  downlight: 'Downlights',
  'wall-wash': 'Wall Wash',
  spot: 'Spot',
  flood: 'Flood',
  specialty: 'Specialty',
}

// Keep a stable order that matches the spec
const CATEGORY_ORDER = ['downlight', 'wall-wash', 'spot', 'flood', 'specialty']

// ── Sub-components ─────────────────────────────────────────────────────────────

function CategoryTab({ id, label, active, onClick }) {
  return (
    <button
      type="button"
      onClick={() => onClick(id)}
      className={
        'h-7 px-2.5 rounded-full text-[11px] font-medium transition-colors whitespace-nowrap border ' +
        (active
          ? 'bg-ink-100 text-ink-950 border-ink-100'
          : 'text-ink-300 hover:text-ink-100 border-ink-800 hover:border-ink-700 bg-ink-900')
      }
    >
      {label}
    </button>
  )
}

function PresetRow({ preset, selected, onSelect }) {
  const categoryColor = {
    downlight: 'bg-blue-500/20 text-blue-300 border-blue-500/30',
    'wall-wash': 'bg-purple-500/20 text-purple-300 border-purple-500/30',
    spot: 'bg-amber-500/20 text-amber-300 border-amber-500/30',
    flood: 'bg-green-500/20 text-green-300 border-green-500/30',
    specialty: 'bg-pink-500/20 text-pink-300 border-pink-500/30',
  }[preset.category] || 'bg-ink-700 text-ink-300 border-ink-600'

  return (
    <button
      type="button"
      data-slug={preset.slug}
      onClick={() => onSelect(preset)}
      aria-pressed={selected}
      className={
        'w-full text-left px-3 py-2 rounded-md border transition-colors flex items-start gap-3 ' +
        (selected
          ? 'border-kerf-300/60 bg-kerf-300/10 ring-1 ring-kerf-300/20'
          : 'border-ink-800 bg-ink-900 hover:border-kerf-300/40 hover:bg-ink-850')
      }
    >
      {/* Category badge */}
      <span
        className={
          'mt-0.5 inline-flex h-5 items-center rounded px-1.5 text-[9px] font-semibold uppercase tracking-wide border flex-shrink-0 ' +
          categoryColor
        }
      >
        {CATEGORY_LABELS[preset.category] || preset.category}
      </span>

      {/* Name + description */}
      <div className="min-w-0 flex-1">
        <div className="flex items-center justify-between gap-2">
          <span className="text-sm font-semibold text-ink-100 truncate">
            {preset.name}
          </span>
          {selected && (
            <span className="text-[10px] text-kerf-300 flex-shrink-0">active</span>
          )}
        </div>
        <p className="text-[11px] text-ink-400 truncate mt-0.5">
          {preset.description}
        </p>
      </div>
    </button>
  )
}

// ── Main component ─────────────────────────────────────────────────────────────

export default function IesProfilePicker({ onSelect, selectedSlug, className = '' }) {
  const [search, setSearch] = useState('')
  const [activeCategory, setActiveCategory] = useState('all')

  const filteredPresets = useMemo(() => {
    let presets = IES_PRESETS
    if (activeCategory !== 'all') {
      presets = presets.filter((p) => p.category === activeCategory)
    }
    if (search.trim()) {
      const q = search.trim().toLowerCase()
      presets = presets.filter(
        (p) =>
          p.name.toLowerCase().includes(q) ||
          p.description.toLowerCase().includes(q) ||
          p.category.toLowerCase().includes(q)
      )
    }
    return presets
  }, [activeCategory, search])

  // Group by category for display (only relevant when "all" is selected)
  const grouped = useMemo(() => {
    if (activeCategory !== 'all') {
      return [{ category: activeCategory, presets: filteredPresets }]
    }
    const groups = []
    for (const cat of CATEGORY_ORDER) {
      const presets = filteredPresets.filter((p) => p.category === cat)
      if (presets.length > 0) {
        groups.push({ category: cat, presets })
      }
    }
    return groups
  }, [activeCategory, filteredPresets])

  const totalCount = filteredPresets.length

  return (
    <div className={'flex flex-col gap-3 ' + className} data-testid="ies-profile-picker">
      {/* Search */}
      <div className="relative">
        <Search
          size={13}
          className="absolute left-2.5 top-1/2 -translate-y-1/2 text-ink-500 pointer-events-none"
        />
        <input
          type="search"
          placeholder="Search profiles…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="w-full h-8 bg-ink-950 border border-ink-800 rounded-md pl-8 pr-3 text-xs text-ink-100 placeholder:text-ink-500 outline-none focus:border-kerf-300/60"
        />
      </div>

      {/* Category filter tabs */}
      <div className="flex items-center gap-1 overflow-x-auto pb-0.5">
        <CategoryTab
          id="all"
          label="All"
          active={activeCategory === 'all'}
          onClick={setActiveCategory}
        />
        {CATEGORY_ORDER.map((cat) => (
          <CategoryTab
            key={cat}
            id={cat}
            label={CATEGORY_LABELS[cat] || cat}
            active={activeCategory === cat}
            onClick={setActiveCategory}
          />
        ))}
      </div>

      {/* Results */}
      <div className="flex flex-col gap-3">
        {totalCount === 0 && (
          <p className="text-[11px] text-ink-500 py-2 text-center">No profiles match.</p>
        )}

        {grouped.map(({ category, presets }) => (
          <section key={category}>
            {activeCategory === 'all' && (
              <div className="flex items-center justify-between mb-1.5">
                <span className="text-[10px] uppercase tracking-wider text-ink-500">
                  {CATEGORY_LABELS[category] || category}
                </span>
                <span className="text-[10px] text-ink-600">
                  {presets.length}
                </span>
              </div>
            )}
            <div className="space-y-1.5">
              {presets.map((preset) => (
                <PresetRow
                  key={preset.slug}
                  preset={preset}
                  selected={preset.slug === selectedSlug}
                  onSelect={onSelect}
                />
              ))}
            </div>
          </section>
        ))}
      </div>
    </div>
  )
}
