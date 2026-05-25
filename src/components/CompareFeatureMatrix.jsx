/**
 * CompareFeatureMatrix.jsx — structured feature matrix for a per-CAD compare page.
 *
 * Mode: 'by-cad' — embedded in a single /compare/:slug page.
 *
 * Props:
 *   features    — array of feature rows from the manifest item
 *   competitor  — display name of the competitor (e.g. "Autodesk Fusion 360")
 *
 * Column order is ALWAYS: Feature | Kerf | Competitor.
 * Kerf is unconditionally the first data column. The kerfFirst prop has been
 * removed — the layout does not vary.
 */

import { DOMAIN_META, STATUS_META, TONE_CLASSES, featuresByDomain } from '../lib/compareFeatures.js'

/* -------------------------------------------------------------------------- */
/* Helpers                                                                     */
/* -------------------------------------------------------------------------- */

/** @param {string} status */
function StatusPill({ status, note, linkHref, evidencePath }) {
  const s = STATUS_META[status] ?? STATUS_META.unknown
  const tone = TONE_CLASSES[s.tone]

  const pill = (
    <span
      className={[
        'inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-mono font-medium',
        'border whitespace-nowrap',
        tone.bg, tone.border, tone.text,
      ].join(' ')}
      title={note || s.label}
      data-testid={`status-pill-${status}`}
    >
      <span aria-hidden="true">{s.symbol}</span>
      <span>{s.label}</span>
    </span>
  )

  return (
    <div className="flex flex-col gap-1">
      {pill}
      {note && (
        <p className="text-[11px] text-ink-500 leading-relaxed">
          {note}
          {linkHref && (
            <>
              {' '}
              <a
                href={linkHref}
                target="_blank"
                rel="noreferrer"
                className="text-kerf-300 hover:text-kerf-200 underline underline-offset-1"
                aria-label="Source"
              >
                ↗
              </a>
            </>
          )}
        </p>
      )}
      {evidencePath && (
        <p className="text-[11px] text-ink-600 font-mono truncate max-w-[160px]" title={evidencePath}>
          {evidencePath}
        </p>
      )}
    </div>
  )
}

/* -------------------------------------------------------------------------- */
/* Domain section                                                               */
/* -------------------------------------------------------------------------- */

function DomainSection({ domainMeta, rows, competitor }) {
  const matched = rows.filter(
    (r) => r?.kerf?.status === 'yes' && r?.competitor?.status === 'yes',
  ).length

  const kerfHeader = 'Kerf'
  const compHeader = competitor

  return (
    <details
      className="group border border-ink-800 rounded-xl overflow-hidden mb-4"
      data-testid={`domain-section-${domainMeta.code}`}
    >
      <summary className="flex items-center justify-between gap-4 px-4 py-3 cursor-pointer select-none bg-ink-900/60 hover:bg-ink-900 transition-colors list-none">
        <div className="flex items-center gap-3">
          <span className="font-mono text-[10px] uppercase tracking-wider text-ink-500 w-7 shrink-0">
            {domainMeta.code}
          </span>
          <span className="font-display text-sm font-semibold text-ink-100">
            {domainMeta.title}
          </span>
        </div>
        <div className="flex items-center gap-3 shrink-0">
          <span className="text-xs font-mono text-ink-500">
            {matched} of {rows.length} matched
          </span>
          <span className="text-ink-500 group-open:rotate-90 transition-transform text-xs select-none">
            ›
          </span>
        </div>
      </summary>

      {/* ── Table (desktop) / stacked rows (mobile) ── */}
      <div className="hidden sm:block overflow-x-auto" data-testid="matrix-desktop-table">
        <table className="min-w-[560px] w-full text-sm">
          <thead className="border-b border-t border-ink-800 bg-ink-900/30">
            <tr>
              <th className="text-left px-4 py-2.5 font-mono text-[10px] uppercase tracking-wider text-ink-400 w-[40%]">
                Feature
              </th>
              {/* Kerf is ALWAYS the first data column */}
              <th className="text-left px-4 py-2.5 font-mono text-[10px] uppercase tracking-wider text-kerf-300 w-[30%]" data-testid="matrix-kerf-header">
                {kerfHeader}
              </th>
              <th className="text-left px-4 py-2.5 font-mono text-[10px] uppercase tracking-wider text-ink-400 w-[30%]">
                {compHeader}
              </th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row, idx) => (
              <tr
                key={idx}
                className="border-b border-ink-800/50 hover:bg-ink-900/30 transition-colors"
                data-testid="feature-row"
              >
                <td className="px-4 py-3 text-ink-200 font-medium align-top text-sm">
                  {row.feature}
                </td>
                {/* Kerf is ALWAYS the first data column */}
                <td className="px-4 py-3 align-top">
                  <StatusPill
                    status={row?.kerf?.status ?? 'unknown'}
                    note={row?.kerf?.note}
                    evidencePath={row?.kerf?.evidence}
                  />
                </td>
                <td className="px-4 py-3 align-top">
                  <StatusPill
                    status={row?.competitor?.status ?? 'unknown'}
                    note={row?.competitor?.note}
                    linkHref={row?.competitor?.source}
                  />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Mobile: stacked rows */}
      <div className="sm:hidden divide-y divide-ink-800/50" data-testid="matrix-mobile-cards">
        {rows.map((row, idx) => (
          <div key={idx} className="px-4 py-3 space-y-2">
            <p className="text-sm font-medium text-ink-200">{row.feature}</p>
            <div className="flex flex-wrap gap-3">
              <div>
                <p className="text-[10px] font-mono uppercase text-kerf-300 mb-1">Kerf</p>
                <StatusPill
                  status={row?.kerf?.status ?? 'unknown'}
                  note={row?.kerf?.note}
                  evidencePath={row?.kerf?.evidence}
                />
              </div>
              <div>
                <p className="text-[10px] font-mono uppercase text-ink-400 mb-1">{competitor}</p>
                <StatusPill
                  status={row?.competitor?.status ?? 'unknown'}
                  note={row?.competitor?.note}
                  linkHref={row?.competitor?.source}
                />
              </div>
            </div>
          </div>
        ))}
      </div>
    </details>
  )
}

/* -------------------------------------------------------------------------- */
/* CompareFeatureMatrix — main component                                        */
/* -------------------------------------------------------------------------- */

/**
 * @param {{
 *   features: object[] | undefined,
 *   competitor: string,
 * }} props
 */
export default function CompareFeatureMatrix({ features, competitor }) {
  if (!features || features.length === 0) return null

  // Group features by domain code
  const byDomain = featuresByDomain({ features })

  // Render only domains that have at least one row, in DOMAIN_META order
  const domainSections = DOMAIN_META
    .map((dm) => ({ domainMeta: dm, rows: byDomain.get(dm.code) ?? [] }))
    .filter(({ rows }) => rows.length > 0)

  if (domainSections.length === 0) return null

  return (
    <section
      className="mt-10"
      aria-label="Full feature matrix"
      data-testid="compare-feature-matrix"
    >
      <h2 className="font-display text-xl sm:text-2xl font-semibold tracking-tight text-ink-100 mb-4 pb-2 border-b border-ink-800">
        Full feature matrix (D1–D14)
      </h2>
      <p className="text-sm text-ink-400 mb-6 leading-relaxed">
        Domain-by-domain breakdown across {features.length} feature rows.
        Click a domain to expand.
      </p>
      <div className="space-y-1">
        {domainSections.map(({ domainMeta, rows }) => (
          <DomainSection
            key={domainMeta.code}
            domainMeta={domainMeta}
            rows={rows}
            competitor={competitor}
          />
        ))}
      </div>
    </section>
  )
}
