/**
 * CompareCardGrid.jsx — responsive card grid for the Compare landing page.
 *
 * Each card shows "Kerf vs <competitor>" with the hero_tagline and an
 * "Open →" affordance. Cards link to /compare/<slug>.
 *
 * Props:
 *   items   Array<{slug, competitor, category, hero_tagline}>
 */
import { Link } from 'react-router-dom'
import { ArrowRight } from 'lucide-react'

/** Category accent colours keyed by category id. */
const CATEGORY_ACCENT = {
  'cad-mechanical':   'text-sky-400 bg-sky-400/10 border-sky-400/25',
  'cad-electronics':  'text-emerald-400 bg-emerald-400/10 border-emerald-400/25',
  'cad-architecture': 'text-violet-400 bg-violet-400/10 border-violet-400/25',
  'cad-sim':          'text-orange-400 bg-orange-400/10 border-orange-400/25',
  'cad-silicon':      'text-rose-400 bg-rose-400/10 border-rose-400/25',
  'cad-firmware':     'text-yellow-400 bg-yellow-400/10 border-yellow-400/25',
  'cad-creative':     'text-pink-400 bg-pink-400/10 border-pink-400/25',
}

const CATEGORY_LABEL = {
  'cad-mechanical':   'Mechanical',
  'cad-electronics':  'Electronics',
  'cad-architecture': 'Architecture',
  'cad-sim':          'Simulation',
  'cad-silicon':      'Silicon',
  'cad-firmware':     'Firmware',
  'cad-creative':     'Creative',
}

/**
 * @param {{ items: Array<{slug: string, competitor: string, category: string, hero_tagline: string}> }} props
 */
export default function CompareCardGrid({ items }) {
  if (!items || items.length === 0) {
    return (
      <p className="text-ink-500 text-sm text-center py-12">
        No comparisons match your search.
      </p>
    )
  }

  return (
    <div
      className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4"
      data-testid="compare-card-grid"
    >
      {items.map((item) => (
        <CompareCard key={item.slug} item={item} />
      ))}
    </div>
  )
}

/** Individual comparison card. */
function CompareCard({ item }) {
  const { slug, competitor, category, hero_tagline } = item
  const accent = CATEGORY_ACCENT[category] ?? 'text-kerf-300 bg-kerf-300/10 border-kerf-300/25'
  const catLabel = CATEGORY_LABEL[category] ?? category

  return (
    <Link
      to={`/compare/${slug}`}
      className="group relative flex flex-col rounded-2xl border border-ink-800 bg-ink-900/40 p-5 sm:p-6 hover:border-ink-700 hover:bg-ink-900/70 transition-colors"
      aria-label={`Read full Kerf vs ${competitor} comparison`}
      data-testid="compare-card"
    >
      {/* Category badge */}
      <span
        className={[
          'self-start mb-3 rounded-full px-2.5 py-0.5 text-[10px] font-mono font-medium',
          'border tracking-wide uppercase',
          accent,
        ].join(' ')}
        aria-label={`Category: ${catLabel}`}
      >
        {catLabel}
      </span>

      {/* Heading */}
      <div className="flex items-start justify-between gap-3 mb-2">
        <h3 className="font-display text-base font-semibold tracking-tight text-ink-100 leading-snug">
          Kerf vs {competitor}
        </h3>
        <ArrowRight
          size={15}
          className="shrink-0 mt-0.5 text-ink-500 group-hover:text-kerf-300 group-hover:translate-x-0.5 transition-all"
          aria-hidden="true"
        />
      </div>

      {/* Tagline */}
      <p className="text-xs text-ink-400 font-mono leading-relaxed flex-1">
        {hero_tagline}
      </p>

      {/* Open CTA */}
      <p className="mt-4 text-xs font-medium text-kerf-300 group-hover:text-kerf-200 transition-colors">
        Open →
      </p>
    </Link>
  )
}
