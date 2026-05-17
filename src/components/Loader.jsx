/**
 * Loader.jsx — Kerf-branded animated SVG triangles loader.
 *
 * The word "kerf" refers to the cut/slot left by a saw blade; triangles are
 * the natural visual primitive — three equilateral triangles arranged in a
 * triadic composition, animated by CSS keyframes scoped inline at the bottom
 * of this file so the component is fully self-contained and dropping it into
 * any tree Just Works (no global Tailwind keyframe registration needed —
 * Tailwind v4 uses CSS-first `@theme`, and this loader keeps its motion
 * private).
 *
 * Public API
 * ──────────
 *   default export  Loader({ size, label, variant, className })
 *     - size: number (px); the SVG width/height. Default 48.
 *               Sizes 16/24/32/48/64 all look right (viewBox is 0 0 100 100,
 *               so geometry scales linearly with size).
 *     - label: string for screen readers + aria-label. Default 'Loading…'.
 *     - variant: 'inline' (default — flows with surrounding content; for
 *               buttons, cards, async-fetch placeholders) or 'block' (a
 *               vertically-padded centred block).
 *     - className: extra Tailwind classes appended to the wrapper.
 *
 *   named export    FullPageLoader({ label, sub })
 *     - Full-viewport Suspense fallback. Fixed overlay with backdrop, large
 *       triangles, optional `sub` line below the label.
 *
 *   named export    InlineLoader
 *     - Convenience alias of Loader with variant pinned to 'inline'.
 *
 * Accessibility
 * ─────────────
 *   - Wrapper is role="status" aria-live="polite" with the supplied label.
 *   - Visually-hidden <span className="sr-only"> repeats the label for AT.
 *   - SVG is aria-hidden so screen readers read the sr-only label, not the
 *     decorative polygons.
 *   - Respects `prefers-reduced-motion: reduce` — the inline @media block
 *     suspends the keyframes so motion-sensitive users see a static glyph.
 *
 * Performance
 * ───────────
 *   - Pure SVG + CSS keyframes. No canvas, no JS animation, no rAF, no
 *     useEffect. Cheap enough to mount on every Suspense boundary.
 *
 * Theming
 * ───────
 *   - Triangles use `stroke="currentColor"` and the wrapper defaults to
 *     `text-kerf-400`; override by passing `className="text-..."`.
 *   - Fill is also currentColor at low opacity for the "active" triangle in
 *     each animation phase, so colour is single-source.
 */

import clsx from 'clsx'

// ── triangle geometry ─────────────────────────────────────────────────────
// Three equilateral triangles in a triadic composition inside a 100x100
// viewBox. Triangles t1 (apex-up, top) and t2/t3 (apex-down, bottom-left /
// bottom-right) form a kerf-like trio: one cut, three teeth.
//
// Side length s ≈ 38 (each triangle); spacing chosen so the three centres
// describe their own larger equilateral arrangement.

const T1 = '50,12 76,58 24,58' //  apex-up,    top centre
const T2 = '12,86 38,40 64,86' //  apex-down,  bottom-left
const T3 = '38,40 64,86 90,40' //  apex-down,  bottom-right (overlaps t2 edge — feels like a kerf)

// One triangle per pulse; phase-shifted by 0 / 0.4s / 0.8s.
// CSS class names are namespaced with `kerf-loader-` so they never collide
// with anything else in the app.

/**
 * Loader — small, drop-in animated SVG triangles spinner.
 *
 * @param {object} props
 * @param {number} [props.size=48]      px width/height of the SVG
 * @param {string} [props.label='Loading…']  aria-label + sr-only text
 * @param {'inline'|'block'} [props.variant='inline']
 * @param {string} [props.className]    extra wrapper classes
 */
export default function Loader({
  size = 48,
  label = 'Loading…',
  variant = 'inline',
  className,
}) {
  const wrapperBase =
    variant === 'block'
      ? 'flex flex-col items-center justify-center gap-2 py-6 text-kerf-400'
      : 'inline-flex items-center justify-center text-kerf-400'

  return (
    <div
      role="status"
      aria-live="polite"
      aria-label={label}
      className={clsx(wrapperBase, className)}
    >
      <svg
        width={size}
        height={size}
        viewBox="0 0 100 100"
        fill="none"
        stroke="currentColor"
        strokeWidth="3"
        strokeLinejoin="round"
        strokeLinecap="round"
        aria-hidden="true"
        className="kerf-loader-svg"
      >
        <polygon points={T1} className="kerf-loader-tri kerf-loader-tri-1" />
        <polygon points={T2} className="kerf-loader-tri kerf-loader-tri-2" />
        <polygon points={T3} className="kerf-loader-tri kerf-loader-tri-3" />
      </svg>
      <span className="sr-only">{label}</span>
      <LoaderStyles />
    </div>
  )
}

/**
 * FullPageLoader — Suspense fallback overlay covering the viewport.
 *
 * @param {object} props
 * @param {string} [props.label='Loading…']  primary text + aria-label
 * @param {string} [props.sub]               optional secondary line
 */
export function FullPageLoader({ label = 'Loading…', sub }) {
  return (
    <div
      role="status"
      aria-live="polite"
      aria-label={label}
      className="fixed inset-0 grid place-items-center bg-ink-950/95 z-50 text-kerf-400"
    >
      <div className="flex flex-col items-center gap-4">
        <svg
          width={96}
          height={96}
          viewBox="0 0 100 100"
          fill="none"
          stroke="currentColor"
          strokeWidth="3"
          strokeLinejoin="round"
          strokeLinecap="round"
          aria-hidden="true"
          className="kerf-loader-svg"
        >
          <polygon points={T1} className="kerf-loader-tri kerf-loader-tri-1" />
          <polygon points={T2} className="kerf-loader-tri kerf-loader-tri-2" />
          <polygon points={T3} className="kerf-loader-tri kerf-loader-tri-3" />
        </svg>
        <div className="flex flex-col items-center gap-1 text-center">
          <div className="text-sm font-medium text-ink-100">{label}</div>
          {sub ? <div className="text-xs text-ink-400">{sub}</div> : null}
        </div>
      </div>
      <span className="sr-only">{label}</span>
      <LoaderStyles />
    </div>
  )
}

/**
 * InlineLoader — convenience alias for Loader with variant='inline'.
 * Provided so callers can `import { InlineLoader }` for self-documenting
 * usage inside buttons / table rows / etc.
 */
export function InlineLoader(props) {
  return <Loader {...props} variant="inline" />
}

// ── inline scoped styles ──────────────────────────────────────────────────
// Self-contained so the component drops in anywhere without touching global
// CSS. Triangles fade their fill from transparent to a soft currentColor wash
// while the stroke holds steady — gives a "lit kerf" feel as light walks the
// three teeth in sequence. prefers-reduced-motion freezes everything at full
// opacity so the glyph is still legible without motion.

function LoaderStyles() {
  return (
    <style>{`
      .kerf-loader-tri {
        fill: currentColor;
        fill-opacity: 0;
        animation: kerf-loader-pulse 1.2s ease-in-out infinite;
        transform-origin: 50px 50px;
      }
      .kerf-loader-tri-1 { animation-delay: 0s; }
      .kerf-loader-tri-2 { animation-delay: 0.4s; }
      .kerf-loader-tri-3 { animation-delay: 0.8s; }

      @keyframes kerf-loader-pulse {
        0%, 100% {
          fill-opacity: 0;
          stroke-opacity: 0.55;
        }
        40% {
          fill-opacity: 0.35;
          stroke-opacity: 1;
        }
        60% {
          fill-opacity: 0.35;
          stroke-opacity: 1;
        }
      }

      @media (prefers-reduced-motion: reduce) {
        .kerf-loader-tri {
          animation: none;
          fill-opacity: 0.2;
          stroke-opacity: 1;
        }
      }
    `}</style>
  )
}
