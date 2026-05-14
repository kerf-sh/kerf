/**
 * SketchShortcutsIllustration — single sketch profile on the left, three
 * FreeCAD-parity "sketch → 3D" shortcuts on the right (boss-with-draft,
 * cut-from-sketch, hole-pattern-from-sketch). Communicates the parametric
 * shortcut surface that lands a 2D profile straight into a B-rep feature.
 *
 * viewBox 320×200. Palette locked to ink-* / kerf-* (#ffd633 accent).
 */
export default function SketchShortcutsIllustration({ className = '' }) {
  return (
    <svg
      viewBox="0 0 320 200"
      preserveAspectRatio="xMidYMid meet"
      className={className}
      role="img"
      aria-label="A sketch profile feeding three FreeCAD-parity shortcuts: boss with draft, cut from sketch, hole pattern from sketch"
    >
      <defs>
        <pattern id="sks-grid" width="12" height="12" patternUnits="userSpaceOnUse">
          <path d="M 12 0 L 0 0 0 12" fill="none" stroke="#14171c" strokeWidth="0.5" />
        </pattern>
      </defs>

      {/* outer panel */}
      <rect x="8" y="14" width="304" height="172" rx="8" fill="#0a0b0d" stroke="#1a1d24" />

      {/* header strip */}
      <text x="22" y="30" fontSize="8" fontFamily="ui-monospace, monospace" fill="#5a6275" letterSpacing="1.4">
        SKETCH → 3D SHORTCUTS
      </text>
      <text x="298" y="30" textAnchor="end" fontSize="8" fontFamily="ui-monospace, monospace" fill="#3a4150" letterSpacing="1.2">
        PartDesign parity
      </text>
      <line x1="22" y1="36" x2="298" y2="36" stroke="#1a1d24" strokeWidth="0.6" />

      {/* === Left: sketch profile === */}
      <g>
        <rect x="22" y="44" width="100" height="128" rx="4" fill="#0a0b0d" stroke="#1a1d24" />
        <rect x="22" y="44" width="100" height="128" fill="url(#sks-grid)" />

        {/* origin axes */}
        <line x1="32" y1="108" x2="112" y2="108" stroke="#3a4150" strokeWidth="0.6" strokeDasharray="2 3" />
        <line x1="44" y1="54" x2="44" y2="162" stroke="#3a4150" strokeWidth="0.6" strokeDasharray="2 3" />
        <circle cx="44" cy="108" r="2" fill="#0a0b0d" stroke="#5a6275" strokeWidth="0.8" />

        {/* fully-constrained profile (green = solved) — rounded rect with hole pattern */}
        <g stroke="#7BB661" strokeWidth="1.4" fill="none">
          <rect x="52" y="70" width="60" height="76" rx="6" />
          <circle cx="68" cy="86" r="3.5" />
          <circle cx="96" cy="86" r="3.5" />
          <circle cx="68" cy="130" r="3.5" />
          <circle cx="96" cy="130" r="3.5" />
        </g>

        {/* solved badge */}
        <g transform="translate(28, 50)">
          <rect width="40" height="13" rx="2" fill="#7BB661" fillOpacity="0.12" stroke="#7BB661" strokeOpacity="0.4" />
          <circle cx="6" cy="6.5" r="1.8" fill="#7BB661" />
          <text x="11" y="9" fontSize="8" fontFamily="ui-monospace, monospace" fill="#7BB661">
            solved
          </text>
        </g>

        {/* file label */}
        <text x="72" y="166" textAnchor="middle" fontSize="7" fontFamily="ui-monospace, monospace" fill="#5a6275">
          mount.sketch
        </text>
      </g>

      {/* arrow stem from sketch → shortcuts */}
      <g stroke="#ffd633" strokeWidth="0.9" fill="none" strokeLinecap="round">
        <line x1="124" y1="108" x2="138" y2="108" />
        <polygon points="138,108 134,105.5 134,110.5" fill="#ffd633" stroke="none" />
      </g>

      {/* === Right: three shortcut rows === */}
      <g transform="translate(144, 44)">
        {/* boss with draft */}
        <ShortcutRow y={0} label="feature_boss_with_draft" sub="extrude + 3° draft" active>
          <BossDraftGlyph x={4} y={6} />
        </ShortcutRow>
        {/* cut from sketch */}
        <ShortcutRow y={44} label="feature_cut_from_sketch" sub="pocket through faces">
          <CutGlyph x={4} y={6} />
        </ShortcutRow>
        {/* hole pattern */}
        <ShortcutRow y={88} label="feature_hole_pattern_from_sketch" sub="ø3.2 · 4× through" small>
          <HolePatternGlyph x={4} y={6} />
        </ShortcutRow>
      </g>
    </svg>
  )
}

function ShortcutRow({ y, label, sub, active, small, children }) {
  const labelColor = active ? '#ffd633' : '#e2e6ee'
  return (
    <g transform={`translate(0, ${y})`}>
      <rect
        x="0"
        y="0"
        width="158"
        height="38"
        rx="4"
        fill={active ? '#ffd633' : '#0f1115'}
        fillOpacity={active ? 0.06 : 1}
        stroke={active ? '#ffd633' : '#1a1d24'}
        strokeOpacity={active ? 0.45 : 1}
      />
      {/* glyph slot */}
      <rect x="6" y="6" width="26" height="26" rx="3" fill="#0a0b0d" stroke="#1a1d24" strokeWidth="0.6" />
      <g transform="translate(6, 6)">{children}</g>
      {/* label */}
      <text
        x="40"
        y={small ? 16 : 17}
        fontSize={small ? 8 : 9}
        fontFamily="ui-monospace, monospace"
        fill={labelColor}
        fontWeight="500"
      >
        {label}
      </text>
      <text
        x="40"
        y="28"
        fontSize="7.5"
        fontFamily="ui-monospace, monospace"
        fill="#5a6275"
      >
        {sub}
      </text>
      {active && (
        <g transform="translate(132, 14)">
          <rect width="22" height="11" rx="2" fill="#ffd633" fillOpacity="0.18" stroke="#ffd633" strokeOpacity="0.5" />
          <text x="11" y="8.5" textAnchor="middle" fontSize="7" fontFamily="ui-monospace, monospace" fill="#ffd633">
            new
          </text>
        </g>
      )}
    </g>
  )
}

/* Glyphs sized to fit a 26×26 slot. */

function BossDraftGlyph({ x = 0, y = 0 }) {
  // Trapezoidal solid (boss with positive draft) — front face + side trapezoid.
  return (
    <g transform={`translate(${x}, ${y})`} stroke="#ffd633" strokeWidth="1" fill="none" strokeLinejoin="round">
      <polygon points="3,16 19,16 17,4 5,4" />
      <polygon points="3,16 5,4 11,2 9,14" fill="#ffd633" fillOpacity="0.1" />
      <line x1="11" y1="2" x2="17" y2="4" />
      <line x1="9" y1="14" x2="19" y2="16" />
      {/* draft angle indicator */}
      <path d="M 3 16 A 4 4 0 0 0 5 12" stroke="#ffd633" strokeWidth="0.7" fill="none" />
    </g>
  )
}

function CutGlyph({ x = 0, y = 0 }) {
  // Solid block with a cut pocket from above.
  return (
    <g transform={`translate(${x}, ${y})`} stroke="#8a93a6" strokeWidth="1" fill="none" strokeLinejoin="round">
      <polygon points="2,15 16,15 19,11 5,11" />
      <polygon points="2,15 2,5 5,3 5,11" />
      <polygon points="2,5 5,3 19,3 16,5" />
      {/* pocket (cut from sketch) */}
      <polygon points="7,5 13,5 14,4 8,4" fill="#0a0b0d" />
      <polygon points="7,5 7,9 8,8 8,4" fill="#0a0b0d" />
      <polygon points="7,9 13,9 14,8 8,8" stroke="#ff6bd4" />
      <line x1="7" y1="5" x2="7" y2="9" stroke="#ff6bd4" />
      <line x1="13" y1="5" x2="13" y2="9" stroke="#ff6bd4" />
      <line x1="13" y1="9" x2="14" y2="8" stroke="#ff6bd4" />
    </g>
  )
}

function HolePatternGlyph({ x = 0, y = 0 }) {
  // 2x2 hole pattern as seen top-down on a plate.
  return (
    <g transform={`translate(${x}, ${y})`} stroke="#8a93a6" strokeWidth="1" fill="none">
      <rect x="2" y="2" width="18" height="18" rx="1.5" />
      <g stroke="#ff6bd4" strokeWidth="1.1">
        <circle cx="7" cy="7" r="1.6" />
        <circle cx="15" cy="7" r="1.6" />
        <circle cx="7" cy="15" r="1.6" />
        <circle cx="15" cy="15" r="1.6" />
      </g>
      {/* tiny cross hairs */}
      <g stroke="#ff6bd4" strokeWidth="0.4" strokeDasharray="1 1">
        <line x1="5" y1="7" x2="9" y2="7" />
        <line x1="7" y1="5" x2="7" y2="9" />
        <line x1="13" y1="7" x2="17" y2="7" />
        <line x1="15" y1="5" x2="15" y2="9" />
      </g>
    </g>
  )
}
