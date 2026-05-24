/**
 * CompareMd.jsx — renders a parsed compare .md file.
 *
 * Accepts a `meta` object (from parseCompareMd) and renders:
 *   1. Breadcrumb (← All comparisons)
 *   2. Hero (H1 title + hero_tagline + competitor info)
 *   3. Free-form markdown body via react-markdown + remark-gfm + rehype-highlight
 *      - Tables in the body become the feature-matrix style
 *      - H2/H3 headings get Section-style borders
 *   4. FairnessNote footer
 *   5. CTA strip
 *
 * Column order invariant: Kerf is ALWAYS the leftmost data column.
 * Raw .md files use | Feature | Competitor | Kerf | ordering in their source,
 * but this renderer reorders columns so Kerf appears as column 2 (immediately
 * after Feature) regardless of the source order. Detection is text-based on the
 * "Kerf" header cell.
 */

import React from 'react'
import { Link } from 'react-router-dom'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import rehypeHighlight from 'rehype-highlight'
import { ArrowLeft, ArrowRight } from 'lucide-react'
import Button from './Button.jsx'
import { ALLOWED_ELEMENTS, urlTransformer } from '../lib/markdownSanitize.js'
import CompareFeatureMatrix from './CompareFeatureMatrix.jsx'

/* -------------------------------------------------------------------------- */
/* Verdict-glyph constants (mirrors Freecad.jsx)                               */
/* -------------------------------------------------------------------------- */

const VERDICT_CLASSES = {
  '✅': 'text-emerald-400',
  '⚠️': 'text-amber-400',
  '❌': 'text-red-400',
  '➖': 'text-ink-500',
}

/* -------------------------------------------------------------------------- */
/* Custom react-markdown components                                             */
/* -------------------------------------------------------------------------- */

/**
 * Section heading — H2 gets a border-b treatment matching the JSX pages.
 */
function H2({ children }) {
  return (
    <h2 className="font-display text-xl sm:text-2xl font-semibold tracking-tight text-ink-100 mb-4 pb-2 border-b border-ink-800 mt-10">
      {children}
    </h2>
  )
}

function H3({ children }) {
  return (
    <h3 className="font-display text-base font-semibold text-ink-100 mb-2 mt-6">
      {children}
    </h3>
  )
}

function P({ children }) {
  return (
    <p className="text-sm text-ink-300 leading-relaxed mb-4">
      {children}
    </p>
  )
}

function UL({ children }) {
  return (
    <ul className="flex flex-col gap-3 mb-6">
      {children}
    </ul>
  )
}

function LI({ children }) {
  return (
    <li className="flex items-start gap-2.5 text-sm text-ink-300 leading-relaxed">
      <span className="mt-2 w-1.5 h-1.5 rounded-full bg-kerf-300 shrink-0" />
      <span>{children}</span>
    </li>
  )
}

function Strong({ children }) {
  return <strong className="text-ink-100">{children}</strong>
}

function Code({ children }) {
  return (
    <code className="font-mono text-kerf-300 text-xs bg-ink-900 px-1 py-0.5 rounded">
      {children}
    </code>
  )
}

function BlockQuote({ children }) {
  return (
    <blockquote className="border-l-2 border-kerf-300/40 pl-4 my-4 text-ink-400 italic text-sm">
      {children}
    </blockquote>
  )
}

/**
 * Feature-matrix table — renders GFM tables with the compare-page styling.
 *
 * Raw .md source uses | Feature | Competitor | Kerf | column order.
 * This renderer reorders to | Feature | Kerf | Competitor | so Kerf
 * is always the leftmost data column in the visual output.
 *
 * Kerf header gets data-testid="left-vendor" + kerf-300 accent.
 * Competitor header gets data-testid="right-vendor".
 */
function Table({ children }) {
  return (
    <div className="overflow-x-auto rounded-xl border border-ink-800 mb-6">
      <table className="min-w-[640px] w-full text-sm">
        {children}
      </table>
    </div>
  )
}

function THead({ children }) {
  return (
    <thead className="border-b border-ink-800 bg-ink-900/60">
      {children}
    </thead>
  )
}

function TBody({ children }) {
  return <tbody>{children}</tbody>
}

function TR({ children, isHeader }) {
  if (isHeader) return <tr>{children}</tr>
  return (
    <tr className="border-b border-ink-800/50 transition-colors hover:bg-ink-900/30">
      {children}
    </tr>
  )
}

/**
 * TH — header cell.
 * variant: 'feature' | 'kerf' | 'competitor'
 */
function TH({ children, variant }) {
  if (variant === 'kerf') {
    return (
      <th
        className="text-left px-4 py-3 font-mono text-xs uppercase tracking-wider text-kerf-300 w-1/3"
        data-testid="left-vendor"
      >
        {children}
      </th>
    )
  }
  if (variant === 'competitor') {
    return (
      <th
        className="text-left px-4 py-3 font-mono text-xs uppercase tracking-wider text-ink-400 w-1/3"
        data-testid="right-vendor"
      >
        {children}
      </th>
    )
  }
  // 'feature' or default
  return (
    <th className="text-left px-4 py-3 font-mono text-xs uppercase tracking-wider text-ink-400 w-1/3">
      {children}
    </th>
  )
}

function TD({ children, isFeature }) {
  return (
    <td className={`px-4 py-3 align-top ${isFeature ? 'text-ink-200 font-medium' : 'text-ink-300'}`}>
      {children}
    </td>
  )
}

/**
 * Build the custom components map.
 *
 * Column reordering: raw .md tables use | Feature | Competitor | Kerf | order.
 * We detect the Kerf column index from the header row (via node inspection),
 * then reorder every row so the visual output is always:
 *   Feature | Kerf | Competitor
 *
 * Implementation: react-markdown passes `node` (mdast/hast node) to each
 * component. For `table`, we scan the first header row to find the Kerf column
 * index, then pass that index down to `tr` via a closure-captured ref.
 *
 * The `tr` component receives `children` as already-keyed React elements; we
 * call React.Children.toArray() and reorder the array before rendering.
 */
function makeComponents() {
  // Per-table mutable state, reset on each new <table>.
  const tableState = {
    kerfColIdx: -1,
    isInHead: false,
  }

  /**
   * Extract plain text from a react-markdown mdast node's children.
   * Handles text nodes nested under inline elements.
   */
  function nodeText(node) {
    if (!node) return ''
    if (node.type === 'text') return node.value || ''
    if (Array.isArray(node.children)) {
      return node.children.map(nodeText).join('')
    }
    return ''
  }

  /**
   * Reorder a cells array so Kerf (at kerfColIdx) is at index 1 (after Feature).
   * Only operates on 3-column tables where kerfColIdx > 1.
   */
  function reorderCells(cells, kerfColIdx) {
    if (kerfColIdx <= 1 || cells.length < 3) return cells
    const result = [cells[0], cells[kerfColIdx]]
    for (let i = 1; i < cells.length; i++) {
      if (i !== kerfColIdx) result.push(cells[i])
    }
    return result
  }

  return {
    h1: ({ children }) => (
      // H1 in body is suppressed — the hero already renders the title.
      <h1 className="hidden" aria-hidden="true">{children}</h1>
    ),
    h2: H2,
    h3: H3,
    p: P,
    ul: UL,
    ol: ({ children }) => (
      <ol className="list-decimal list-inside flex flex-col gap-2 mb-4 text-sm text-ink-300">
        {children}
      </ol>
    ),
    li: LI,
    strong: Strong,
    em: ({ children }) => <em className="italic text-ink-200">{children}</em>,
    code: Code,
    blockquote: BlockQuote,
    a: ({ href, children }) => (
      <a
        href={href}
        target="_blank"
        rel="noreferrer"
        className="text-kerf-300 hover:text-kerf-200 underline underline-offset-2"
      >
        {children}
      </a>
    ),
    table: ({ children, node }) => {
      // Scan first header row to find Kerf column index before rendering.
      tableState.kerfColIdx = -1
      const thead = node?.children?.find((n) => n.tagName === 'thead')
      const headerRow = thead?.children?.find((n) => n.tagName === 'tr')
      if (headerRow?.children) {
        const thCells = headerRow.children.filter((n) => n.tagName === 'th')
        thCells.forEach((cell, idx) => {
          const text = nodeText(cell).trim().toLowerCase()
          if (text === 'kerf' || (idx > 0 && text.includes('kerf'))) {
            tableState.kerfColIdx = idx
          }
        })
      }
      return <Table>{children}</Table>
    },
    thead: ({ children }) => {
      tableState.isInHead = true
      return <THead>{children}</THead>
    },
    tbody: ({ children }) => {
      tableState.isInHead = false
      return <TBody>{children}</TBody>
    },
    tr: ({ children }) => {
      // Reorder cells so Kerf is the first data column (index 1, after Feature).
      const kerfColIdx = tableState.kerfColIdx
      if (kerfColIdx > 1) {
        const cells = Array.isArray(children)
          ? children
          : React.Children.toArray(children)
        const reordered = reorderCells(cells, kerfColIdx)
        return <TR isHeader={tableState.isInHead}>{reordered}</TR>
      }
      return <TR isHeader={tableState.isInHead}>{children}</TR>
    },
    th: ({ children, node }) => {
      // Determine which column this cell represents.
      // kerfColIdx was set in `table` by scanning the hast node.
      const kerfColIdx = tableState.kerfColIdx
      // Find this cell's index in the parent row via node position.
      // We use a simple text match: if text is "Kerf", it's the kerf column.
      const text = nodeText(node).trim().toLowerCase()
      const isKerfCell = text === 'kerf' || (text.includes('kerf') && text.length < 20)
      let variant = 'feature'
      if (isKerfCell) variant = 'kerf'
      else if (kerfColIdx >= 0) {
        // Non-kerf, non-feature: competitor
        // Feature column is always col 0 in source (text = "Feature" or similar)
        const isFeatureCol = text === 'feature' || text === ''
        if (!isFeatureCol) variant = 'competitor'
      }
      return <TH variant={variant}>{children}</TH>
    },
    td: ({ children }) => {
      return <TD>{children}</TD>
    },
  }
}

/* -------------------------------------------------------------------------- */
/* Shared sub-components                                                        */
/* -------------------------------------------------------------------------- */

function Breadcrumb() {
  return (
    <Link
      to="/compare"
      className="inline-flex items-center gap-1.5 text-sm text-ink-400 hover:text-ink-100 transition-colors mb-8"
    >
      <ArrowLeft size={13} />
      All comparisons
    </Link>
  )
}

function FairnessNote() {
  return (
    <div className="mt-12 rounded-xl border border-ink-700 bg-ink-900/50 px-5 py-4 space-y-3">
      <p className="text-sm text-ink-300 leading-relaxed">
        <span className="font-semibold text-ink-100">
          We try hard to keep these comparisons fair and current.
        </span>{' '}
        Software moves fast and we will get things wrong. Think something here
        is inaccurate or unfair to a competitor (or to Kerf)? Please{' '}
        <a
          href="https://github.com/kerf-sh/kerf/issues"
          target="_blank"
          rel="noreferrer"
          className="text-kerf-300 hover:text-kerf-200 underline underline-offset-2 font-medium"
        >
          open an issue on GitHub
        </a>{' '}
        and we will fix it.
      </p>
      <p className="text-xs text-ink-500 leading-relaxed">
        Product and company names referenced on this page are trademarks of
        their respective owners. Comparisons are for informational purposes
        and do not imply endorsement. Pricing and feature claims reflect
        publicly available information at the time of the last review shown
        above and may have changed since.
      </p>
    </div>
  )
}

function CTAStrip() {
  return (
    <div className="mt-10 rounded-2xl border border-ink-800 bg-gradient-to-br from-ink-900 via-ink-900 to-ink-950 p-6 sm:p-8 relative overflow-hidden">
      <div
        aria-hidden
        className="absolute -right-16 -top-16 w-64 h-64 rounded-full bg-kerf-300/10 blur-3xl pointer-events-none"
      />
      <div className="relative flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h2 className="font-display text-xl sm:text-2xl font-semibold tracking-tight text-ink-100">
            Try Kerf for yourself
          </h2>
          <p className="mt-1 text-sm text-ink-300">
            Free to sign up. No card required. Runs in your browser or locally.
          </p>
        </div>
        <div className="flex flex-wrap gap-3 shrink-0">
          <Button as={Link} to="/signup" variant="primary" size="md">
            Try Kerf free
            <ArrowRight size={14} />
          </Button>
          <Button as={Link} to="/docs" variant="outline" size="md">
            Read docs
          </Button>
        </div>
      </div>
    </div>
  )
}

/* -------------------------------------------------------------------------- */
/* CompareMd — main component                                                  */
/* -------------------------------------------------------------------------- */

/**
 * CompareMd — renders a compare page from parsed markdown metadata.
 *
 * @param {object} props
 * @param {object|null} props.meta - CompareMeta from parseCompareMd(); may be null/empty
 * @param {boolean} [props.loading] - show skeleton while fetching
 * @param {string} [props.error] - error message to display
 */
export default function CompareMd({ meta, loading, error }) {
  if (loading) {
    return (
      <div className="min-h-screen bg-ink-950 text-ink-100 flex items-center justify-center">
        <p className="text-ink-400 text-sm font-mono animate-pulse">Loading comparison…</p>
      </div>
    )
  }

  if (error) {
    return (
      <div className="min-h-screen bg-ink-950 text-ink-100 flex items-center justify-center">
        <div className="text-center">
          <p className="text-ink-300 mb-4">{error}</p>
          <Link to="/compare" className="text-kerf-300 hover:text-kerf-200 underline text-sm">
            ← Back to comparisons
          </Link>
        </div>
      </div>
    )
  }

  if (!meta) {
    return (
      <div className="min-h-screen bg-ink-950 text-ink-100 flex items-center justify-center">
        <p className="text-ink-400 text-sm">No comparison data available.</p>
      </div>
    )
  }

  // Kerf is always the left (primary/preferred) side.
  // meta.left is always 'kerf' (enforced by parseCompareMd).
  const leftVendor = 'Kerf'
  const rightVendor = meta.competitor || meta.right || meta.slug || 'Competitor'

  const components = makeComponents()

  return (
    <div className="min-h-screen bg-ink-950 text-ink-100">
      <main
        className="mx-auto max-w-4xl px-6 pt-12 pb-20"
        aria-label={`Kerf vs ${rightVendor} comparison`}
      >
        <Breadcrumb />

        {/* ── Hero ─────────────────────────────────────────────────────── */}
        <header className="mb-10">
          <p
            className="font-mono text-xs uppercase tracking-[0.2em] text-kerf-300 mb-2"
            aria-hidden="true"
          >
            Compare
          </p>
          <h1 className="font-display text-3xl sm:text-4xl lg:text-5xl font-semibold tracking-[-0.02em] leading-tight">
            {meta.title || `${leftVendor} vs ${rightVendor}`}
          </h1>
          {meta.hero_tagline && (
            <p className="mt-4 text-ink-300 leading-relaxed max-w-2xl italic">
              {meta.hero_tagline}
            </p>
          )}
          {/* Vendor labels — Kerf always on the left */}
          <div className="mt-4 flex items-center gap-3 text-xs font-mono text-ink-400">
            <span
              className="px-2 py-0.5 rounded bg-kerf-300/10 border border-kerf-300/30 text-kerf-300"
              data-testid="left-vendor"
            >
              {leftVendor}
            </span>
            <span>vs</span>
            <span
              className="px-2 py-0.5 rounded bg-ink-800 border border-ink-700 text-ink-300"
              data-testid="right-vendor"
            >
              {rightVendor}
            </span>
          </div>
          {meta.reviewed_at && (
            <p className="mt-2 text-xs text-ink-500 font-mono">
              Last reviewed: {meta.reviewed_at}
            </p>
          )}
        </header>

        {/* ── Body (free-form markdown) ─────────────────────────────────── */}
        <div className="compare-md-body">
          <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            rehypePlugins={[[rehypeHighlight, { detect: true, ignoreMissing: true }]]}
            components={components}
            allowedElements={ALLOWED_ELEMENTS}
            urlTransform={urlTransformer}
          >
            {meta.body || ''}
          </ReactMarkdown>
        </div>

        {/* ── Structured feature matrix (only when features are available) ── */}
        {meta.features?.length > 0 && (
          <CompareFeatureMatrix
            features={meta.features}
            competitor={rightVendor}
          />
        )}

        <FairnessNote />
        <CTAStrip />
      </main>
    </div>
  )
}
