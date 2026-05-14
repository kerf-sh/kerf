/**
 * SketchShortcutsIllustration — single sketch profile on the left flowing into
 * three FreeCAD-parity "sketch → 3D" shortcut outcomes on the right. Visual
 * communicates the shape of the new feature ops; tool names live in the card
 * body text, not in the illustration, so layout stays clean at small sizes.
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
        <pattern id="sks-grid" width="14" height="14" patternUnits="userSpaceOnUse">
          <path d="M 14 0 L 0 0 0 14" fill="none" stroke="#14171c" strokeWidth="0.5" />
        </pattern>
        <marker
          id="sks-arrow"
          viewBox="0 0 10 10"
          refX="9"
          refY="5"
          markerWidth="6"
          markerHeight="6"
          orient="auto"
        >
          <path d="M0,1 L9,5 L0,9 Z" fill="#ffd633" />
        </marker>
      </defs>

      {/* outer panel */}
      <rect x="8" y="14" width="304" height="172" rx="8" fill="#0a0b0d" stroke="#1a1d24" />

      {/* header strip */}
      <text x="22" y="32" fontSize="9" fontFamily="ui-monospace, SFMono-Regular, monospace" fill="#6a7185" letterSpacing="1.4">
        SKETCH → 3D SHORTCUTS
      </text>
      <line x1="22" y1="40" x2="298" y2="40" stroke="#1a1d24" strokeWidth="0.6" />

      {/* === Left: sketch source === */}
      <g>
        <rect x="22" y="52" width="108" height="120" rx="4" fill="#0a0b0d" stroke="#1a1d24" />
        <rect x="22" y="52" width="108" height="120" fill="url(#sks-grid)" />

        {/* origin axes */}
        <line x1="32" y1="112" x2="120" y2="112" stroke="#3a4150" strokeWidth="0.5" strokeDasharray="2 3" />
        <line x1="48" y1="62" x2="48" y2="162" stroke="#3a4150" strokeWidth="0.5" strokeDasharray="2 3" />

        {/* fully-constrained profile (green = solved) */}
        <g stroke="#7BB661" strokeWidth="1.4" fill="none">
          <rect x="58" y="78" width="60" height="68" rx="6" />
        </g>

        {/* solved chip */}
        <g transform="translate(28, 58)">
          <rect width="46" height="14" rx="2.5" fill="#7BB661" fillOpacity="0.12" stroke="#7BB661" strokeOpacity="0.45" />
          <circle cx="7" cy="7" r="2" fill="#7BB661" />
          <text x="13" y="10" fontSize="8" fontFamily="ui-monospace, monospace" fill="#7BB661">
            solved
          </text>
        </g>

        <text x="76" y="166" textAnchor="middle" fontSize="8" fontFamily="ui-monospace, monospace" fill="#5a6275">
          .sketch
        </text>
      </g>

      {/* arrow stem from sketch → shortcuts */}
      <g stroke="#ffd633" strokeWidth="1.2" fill="none" strokeLinecap="round">
        <line x1="132" y1="112" x2="156" y2="112" markerEnd="url(#sks-arrow)" />
      </g>

      {/* === Right: three outcome thumbnails stacked === */}
      <g transform="translate(164, 50)">
        <OutcomeRow y={0} title="Boss + draft" sub="extrude + 3° taper" accent active>
          <BossDraftGlyph />
        </OutcomeRow>
        <OutcomeRow y={44} title="Cut from sketch" sub="pocket through face">
          <CutGlyph />
        </OutcomeRow>
        <OutcomeRow y={88} title="Hole pattern" sub="ø3.2 · 4× through">
          <HolePatternGlyph />
        </OutcomeRow>
      </g>
    </svg>
  )
}

function OutcomeRow({ y, title, sub, active, children }) {
  return (
    <g transform={`translate(0, ${y})`}>
      <rect
        x="0"
        y="0"
        width="142"
        height="38"
        rx="5"
        fill={active ? '#ffd633' : '#0f1115'}
        fillOpacity={active ? 0.07 : 1}
        stroke={active ? '#ffd633' : '#1a1d24'}
        strokeOpacity={active ? 0.5 : 1}
      />
      {/* glyph slot */}
      <rect x="6" y="6" width="26" height="26" rx="3" fill="#0a0b0d" stroke="#1a1d24" strokeWidth="0.6" />
      <g transform="translate(6, 6)">{children}</g>

      {/* title — capped width, short labels avoid wrap */}
      <text
        x="40"
        y="17"
        fontSize="10"
        fontFamily="ui-sans-serif, system-ui, sans-serif"
        fill={active ? '#ffd633' : '#e2e6ee'}
        fontWeight="600"
      >
        {title}
      </text>
      <text
        x="40"
        y="30"
        fontSize="8.5"
        fontFamily="ui-monospace, monospace"
        fill="#6a7185"
      >
        {sub}
      </text>
    </g>
  )
}

/* Glyphs sized to fit a 26×26 slot. */

function BossDraftGlyph() {
  return (
    <g stroke="#ffd633" strokeWidth="1.1" fill="none" strokeLinejoin="round">
      {/* trapezoidal boss seen in isometric */}
      <polygon points="4,18 22,18 19,7 7,7" />
      <polygon points="4,18 7,7 12,5 9,16" fill="#ffd633" fillOpacity="0.12" />
      <line x1="12" y1="5" x2="19" y2="7" />
      <line x1="9" y1="16" x2="22" y2="18" />
      {/* draft angle arc */}
      <path d="M 4 18 A 4 4 0 0 0 7 14.5" strokeWidth="0.8" />
    </g>
  )
}

function CutGlyph() {
  return (
    <g stroke="#8a93a6" strokeWidth="1" fill="none" strokeLinejoin="round">
      {/* base block */}
      <polygon points="3,18 18,18 22,14 7,14" />
      <polygon points="3,18 3,6 7,4 7,14" />
      <polygon points="3,6 7,4 22,4 18,6 18,14 22,14" />
      <line x1="7" y1="14" x2="18" y2="14" />
      <line x1="18" y1="14" x2="18" y2="6" opacity="0.6" />
      {/* pocket cutout in pink */}
      <g stroke="#ff6bd4" strokeWidth="1">
        <rect x="9" y="6" width="7" height="6" fill="#0a0b0d" />
        <line x1="9" y1="6" x2="11" y2="4" />
        <line x1="16" y1="6" x2="18" y2="4" />
        <line x1="11" y1="4" x2="18" y2="4" />
      </g>
    </g>
  )
}

function HolePatternGlyph() {
  return (
    <g stroke="#8a93a6" strokeWidth="1" fill="none">
      <rect x="3" y="3" width="20" height="20" rx="1.5" />
      <g stroke="#ff6bd4" strokeWidth="1.1">
        <circle cx="9" cy="9" r="1.8" />
        <circle cx="17" cy="9" r="1.8" />
        <circle cx="9" cy="17" r="1.8" />
        <circle cx="17" cy="17" r="1.8" />
      </g>
      <g stroke="#ff6bd4" strokeWidth="0.4" strokeDasharray="1 1.2" opacity="0.7">
        <line x1="6" y1="9" x2="12" y2="9" />
        <line x1="9" y1="6" x2="9" y2="12" />
        <line x1="14" y1="9" x2="20" y2="9" />
        <line x1="17" y1="6" x2="17" y2="12" />
      </g>
    </g>
  )
}
