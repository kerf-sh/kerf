/**
 * SketchToJscadIllustration — three-pane flow showing the planned (and
 * partly shipped) mesh-side analog of `.sketch → .feature`:
 *
 *   1. constrained 2D sketch profile  →
 *   2. generated JSCAD code (extrudeLinear of the imported sketch)  →
 *   3. resulting 3D part rendered in axonometric.
 *
 * Communicates "source of truth = sketch; JSCAD is just the wrapper".
 *
 * viewBox 320×200. Palette locked to ink-* / kerf-* (#ffd633 accent).
 */
export default function SketchToJscadIllustration({ className = '' }) {
  return (
    <svg
      viewBox="0 0 320 200"
      preserveAspectRatio="xMidYMid meet"
      className={className}
      role="img"
      aria-label="A 2D sketch profile generating a JSCAD program that extrudes it into a 3D part"
    >
      <defs>
        <pattern id="s2j-grid" width="12" height="12" patternUnits="userSpaceOnUse">
          <path d="M 12 0 L 0 0 0 12" fill="none" stroke="#14171c" strokeWidth="0.5" />
        </pattern>
      </defs>

      {/* outer panel */}
      <rect x="8" y="14" width="304" height="172" rx="8" fill="#0a0b0d" stroke="#1a1d24" />

      {/* header strip */}
      <text x="22" y="30" fontSize="8" fontFamily="ui-monospace, monospace" fill="#5a6275" letterSpacing="1.4">
        SKETCH → JSCAD
      </text>
      <text x="298" y="30" textAnchor="end" fontSize="8" fontFamily="ui-monospace, monospace" fill="#3a4150" letterSpacing="1.2">
        reactive · revisioned
      </text>
      <line x1="22" y1="36" x2="298" y2="36" stroke="#1a1d24" strokeWidth="0.6" />

      {/* === Pane 1: sketch === */}
      <g>
        <rect x="20" y="44" width="86" height="128" rx="4" fill="#0a0b0d" stroke="#1a1d24" />
        <rect x="20" y="44" width="86" height="128" fill="url(#s2j-grid)" />

        {/* axes */}
        <line x1="30" y1="108" x2="98" y2="108" stroke="#3a4150" strokeWidth="0.6" strokeDasharray="2 3" />
        <line x1="38" y1="54" x2="38" y2="162" stroke="#3a4150" strokeWidth="0.6" strokeDasharray="2 3" />

        {/* L-shaped profile (green = solved) */}
        <g stroke="#7BB661" strokeWidth="1.5" fill="none" strokeLinejoin="round">
          <polygon points="46,74 88,74 88,98 66,98 66,142 46,142" />
        </g>
        {/* vertices */}
        {[
          [46, 74],
          [88, 74],
          [88, 98],
          [66, 98],
          [66, 142],
          [46, 142],
        ].map(([x, y]) => (
          <circle key={`${x}-${y}`} cx={x} cy={y} r="1.8" fill="#0a0b0d" stroke="#7BB661" strokeWidth="0.9" />
        ))}

        {/* one dim chip */}
        <g>
          <line x1="46" y1="160" x2="88" y2="160" stroke="#5a6275" strokeWidth="0.6" />
          <polygon points="46,160 50,158 50,162" fill="#5a6275" />
          <polygon points="88,160 84,158 84,162" fill="#5a6275" />
          <rect x="59" y="153" width="16" height="11" rx="2" fill="#0a0b0d" stroke="#1a1d24" />
          <text x="67" y="161" textAnchor="middle" fontSize="7" fontFamily="ui-monospace, monospace" fill="#ffd633">
            40
          </text>
        </g>

        <text x="63" y="52" textAnchor="middle" fontSize="7" fontFamily="ui-monospace, monospace" fill="#5a6275">
          bracket.sketch
        </text>
      </g>

      {/* arrow 1 → JSCAD */}
      <g stroke="#ffd633" strokeWidth="0.9" fill="none" strokeLinecap="round">
        <line x1="108" y1="108" x2="118" y2="108" />
        <polygon points="118,108 114,105.5 114,110.5" fill="#ffd633" stroke="none" />
      </g>

      {/* === Pane 2: JSCAD code === */}
      <g>
        <rect x="120" y="44" width="112" height="128" rx="4" fill="#0f1115" stroke="#1a1d24" />
        <text x="128" y="56" fontSize="7" fontFamily="ui-monospace, monospace" fill="#5a6275">
          bracket.jscad
        </text>
        <line x1="124" y1="60" x2="228" y2="60" stroke="#1a1d24" strokeWidth="0.6" />
        <g fontSize="7" fontFamily="ui-monospace, monospace">
          <text x="128" y="72" fill="#ff6bd4">import</text>
          <text x="156" y="72" fill="#b8bfcc"> {'{'} extrudeLinear </text>
          <text x="128" y="82" fill="#b8bfcc">{'}'} = </text>
          <text x="148" y="82" fill="#7BB661">'@jscad/...'</text>

          <text x="128" y="98" fill="#ff6bd4">import</text>
          <text x="156" y="98" fill="#b8bfcc"> profile </text>
          <text x="128" y="108" fill="#ff6bd4">from </text>
          <text x="148" y="108" fill="#7BB661">'./bracket.sketch'</text>

          <text x="128" y="124" fill="#6bd4ff">export const</text>
          <text x="180" y="124" fill="#b8bfcc">main = ()=&gt;</text>
          <text x="136" y="136" fill="#b8bfcc">extrudeLinear(</text>
          <text x="136" y="146" fill="#b8bfcc">  {'{'} height: </text>
          <text x="190" y="146" fill="#ffd633">20</text>
          <text x="200" y="146" fill="#b8bfcc">{'}'},</text>
          <text x="136" y="156" fill="#b8bfcc">  profile</text>
          <text x="136" y="166" fill="#b8bfcc">)</text>
        </g>
        {/* re-eval badge */}
        <g transform="translate(184, 48)">
          <rect width="40" height="11" rx="2" fill="#ffd633" fillOpacity="0.16" stroke="#ffd633" strokeOpacity="0.45" />
          <text x="20" y="8.5" textAnchor="middle" fontSize="6.5" fontFamily="ui-monospace, monospace" fill="#ffd633">
            reactive
          </text>
        </g>
      </g>

      {/* arrow 2 → 3D */}
      <g stroke="#ffd633" strokeWidth="0.9" fill="none" strokeLinecap="round">
        <line x1="234" y1="108" x2="244" y2="108" />
        <polygon points="244,108 240,105.5 240,110.5" fill="#ffd633" stroke="none" />
      </g>

      {/* === Pane 3: 3D result (axonometric L-bracket) === */}
      <g>
        <rect x="246" y="44" width="62" height="128" rx="4" fill="#0a0b0d" stroke="#1a1d24" />
        {/* mini axonometric isometric L-shape */}
        <g transform="translate(252, 96)" strokeLinejoin="round">
          {/* front face (L-profile) */}
          <polygon
            points="0,8 28,8 28,22 14,22 14,46 0,46"
            fill="#ffd633"
            fillOpacity="0.12"
            stroke="#ffd633"
            strokeWidth="1.1"
          />
          {/* top edge (extrusion offset) */}
          <polygon
            points="0,8 8,0 36,0 28,8"
            fill="#ffd633"
            fillOpacity="0.22"
            stroke="#ffd633"
            strokeWidth="1.1"
          />
          {/* right edge */}
          <polygon
            points="28,8 36,0 36,14 28,22"
            fill="#ffd633"
            fillOpacity="0.06"
            stroke="#ffd633"
            strokeWidth="1.1"
          />
          {/* lower right offset */}
          <polygon
            points="14,22 22,14 22,38 14,46"
            fill="#ffd633"
            fillOpacity="0.06"
            stroke="#ffd633"
            strokeWidth="0.9"
          />
          {/* inner hidden lines for L-step */}
          <line x1="14" y1="22" x2="22" y2="14" stroke="#ffd633" strokeWidth="0.9" />
          <line x1="22" y1="14" x2="36" y2="14" stroke="#ffd633" strokeWidth="0.9" />
        </g>

        {/* hint label */}
        <text x="277" y="60" textAnchor="middle" fontSize="7" fontFamily="ui-monospace, monospace" fill="#5a6275">
          @jscad mesh
        </text>
        <text x="277" y="160" textAnchor="middle" fontSize="6.5" fontFamily="ui-monospace, monospace" fill="#5a6275">
          IndexedDB-cached
        </text>
      </g>
    </svg>
  )
}
