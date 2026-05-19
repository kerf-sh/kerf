/**
 * DomainSwitcher — shared horizontal tab strip for the CAD domain pages.
 *
 * Rendered near the top of every /domains/<slug> page so a visitor can
 * jump between disciplines (Jewelry · Mechanical · Electronics ·
 * Architecture · Automotive) in a single click. The active domain is
 * highlighted; the strip scrolls horizontally on narrow screens
 * (overflow-x-auto) so it never wraps or clips on mobile.
 *
 * Palette: ink-* / kerf-* / cyan-edge from src/index.css. No new tokens,
 * no raster assets.
 */
import { Link } from 'react-router-dom'

/* All domains that have a dedicated /domains/<slug> page. */
export const DOMAIN_TABS = [
  { slug: 'jewelry', label: 'Jewelry' },
  { slug: 'mechanical', label: 'Mechanical' },
  { slug: 'electronics', label: 'Electronics' },
  { slug: 'architecture', label: 'Architecture' },
  { slug: 'automotive', label: 'Automotive' },
  { slug: 'civil', label: 'Civil' },
  { slug: 'composites', label: 'Composites' },
  { slug: 'dental', label: 'Dental' },
  { slug: 'optics', label: 'Optics' },
  { slug: 'horology', label: 'Horology' },
  { slug: 'piping', label: 'Piping' },
  { slug: 'packaging', label: 'Packaging' },
  { slug: 'mold', label: 'Mold' },
  { slug: 'woodworking', label: 'Woodworking' },
  { slug: 'marine', label: 'Marine' },
  { slug: 'silicon', label: 'Silicon' },
  { slug: 'firmware', label: 'Firmware' },
  { slug: 'aerospace', label: 'Aerospace' },
]

/**
 * @param {{ active?: string }} props
 *   active — slug of the current domain (e.g. "jewelry"). The matching
 *   tab is rendered as a non-link, highlighted current item.
 */
export default function DomainSwitcher({ active }) {
  return (
    <nav
      aria-label="CAD domains"
      className="relative border-y border-ink-900 bg-ink-950/60 backdrop-blur"
    >
      <div className="mx-auto max-w-7xl px-4 sm:px-6">
        <div className="flex items-center gap-1 overflow-x-auto py-2.5 [scrollbar-width:none] [-ms-overflow-style:none] [&::-webkit-scrollbar]:hidden">
          <span className="shrink-0 pr-2 text-[10px] font-mono uppercase tracking-[0.18em] text-ink-500 hidden sm:inline">
            Domains
          </span>
          {DOMAIN_TABS.map((tab) => {
            const isActive = tab.slug === active
            if (isActive) {
              return (
                <span
                  key={tab.slug}
                  aria-current="page"
                  className="shrink-0 rounded-full border border-cyan-edge/40 bg-cyan-edge/10 px-3.5 py-1.5 text-sm font-medium text-cyan-edge"
                >
                  {tab.label}
                </span>
              )
            }
            return (
              <Link
                key={tab.slug}
                to={`/domains/${tab.slug}`}
                className="shrink-0 rounded-full border border-transparent px-3.5 py-1.5 text-sm text-ink-300 hover:text-ink-100 hover:border-ink-700 hover:bg-ink-900/60 transition-colors"
              >
                {tab.label}
              </Link>
            )
          })}
          <Link
            to="/domains"
            className="shrink-0 ml-auto rounded-full border border-transparent px-3.5 py-1.5 text-sm text-ink-400 hover:text-ink-100 hover:border-ink-700 hover:bg-ink-900/60 transition-colors"
          >
            All domains
          </Link>
        </div>
      </div>
    </nav>
  )
}
