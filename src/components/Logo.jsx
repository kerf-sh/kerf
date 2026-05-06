/**
 * Kerf brand mark.
 *
 * The mark is a solid block bisected by a diagonal saw kerf:
 * the lower-right half is shifted perpendicular to the cut so the
 * kerf gap is visible. It is the literal thing the product is named for.
 *
 * Both halves render in `currentColor` — wrap in a text-color utility
 * (e.g. `text-kerf-300`) and the gap inherits whatever surface it sits on.
 */

export function LogoMark({ size = 28, className = '', title = 'kerf' }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 32 32"
      className={className}
      role="img"
      aria-label={title}
      shapeRendering="geometricPrecision"
    >
      <title>{title}</title>
      {/* Upper-left half of the cut block */}
      <path d="M5 5 H24 L5 24 Z" fill="currentColor" />
      {/* Lower-right half, offset (+3,+3) along the perpendicular so the kerf line is visible */}
      <path d="M27 8 V27 H8 Z" fill="currentColor" />
    </svg>
  )
}

export function LogoWordmark({ className = '', size = 22 }) {
  return (
    <span
      className={`inline-flex items-center gap-2 font-display leading-none ${className}`}
    >
      <LogoMark size={size} className="text-kerf-300" />
      <span
        className="font-semibold text-ink-100"
        style={{ fontSize: `${size * 0.95}px`, letterSpacing: '-0.02em' }}
      >
        kerf
      </span>
    </span>
  )
}
