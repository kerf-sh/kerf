/**
 * BimIllustration — axonometric building (walls, slabs, openings) on
 * the right with a `.bim` source snippet on the left. Conveys
 * "text-DSL compiles to IFC".
 *
 * viewBox 320×200.
 */
export default function BimIllustration({ className = '' }) {
  return (
    <svg
      viewBox="0 0 320 200"
      preserveAspectRatio="xMidYMid meet"
      className={className}
      role="img"
      aria-label=".bim source on the left compiling to an axonometric two-storey building on the right"
    >
      <rect x="8" y="14" width="304" height="172" rx="8" fill="#0a0b0d" stroke="#1a1d24" />
      <text x="22" y="32" fontSize="8" fontFamily="ui-monospace, monospace" fill="#5a6275" letterSpacing="1.4">
        BIM · .bim → IFC4
      </text>

      {/* source panel */}
      <rect x="20" y="44" width="124" height="132" rx="4" fill="#0f1115" stroke="#1a1d24" />
      <g fontSize="7" fontFamily="ui-monospace, monospace" fill="#b8bfcc">
        <text x="28" y="58" fill="#5a6275">level L1 elevation=0</text>
        <text x="28" y="70" fill="#5a6275">level L2 elevation=3.0</text>
        <text x="28" y="84" fill="#ffd633">wall</text>
        <text x="50" y="84"> A 0,0 8,0</text>
        <text x="28" y="94" fill="#5a6275">  height 3.0</text>
        <text x="28" y="104" fill="#5a6275">  thickness 0.2</text>
        <text x="28" y="116" fill="#ffd633">wall</text>
        <text x="50" y="116"> B 8,0 8,6</text>
        <text x="28" y="128" fill="#ffd633">slab</text>
        <text x="50" y="128"> 0,0 8,6 L1</text>
        <text x="28" y="140" fill="#ffd633">opening</text>
        <text x="64" y="140"> A 3,1 1.2,2</text>
        <text x="28" y="156" fill="#5a6275">space LIVING</text>
        <text x="28" y="170" fill="#7BB661"># 12 entities</text>
      </g>

      {/* building axonometric (right) */}
      <g transform="translate(220, 110)">
        {/* ground slab */}
        <polygon points="-60,30 30,42 60,28 -30,16" fill="#1a1d24" stroke="#5a6275" strokeWidth="0.6" />

        {/* L1 — front wall A (longest) */}
        <polygon points="-60,30 30,42 30,4 -60,-8" fill="#232730" stroke="#6bd4ff" strokeWidth="0.7" />
        {/* L1 — side wall B */}
        <polygon points="30,42 60,28 60,-10 30,4" fill="#1a1d24" stroke="#6bd4ff" strokeWidth="0.7" />

        {/* window cut in front wall (opening A) */}
        <rect x="-32" y="-2" width="22" height="20" fill="#0a0b0d" stroke="#6bd4ff" strokeWidth="0.6" />
        <line x1="-32" y1="8" x2="-10" y2="8" stroke="#6bd4ff" strokeWidth="0.4" />
        <line x1="-21" y1="-2" x2="-21" y2="18" stroke="#6bd4ff" strokeWidth="0.4" />

        {/* mid slab (L2 floor) */}
        <polygon points="-60,-8 30,4 60,-10 -30,-22" fill="#2d323d" stroke="#7BB661" strokeWidth="0.6" />

        {/* L2 — front wall */}
        <polygon points="-60,-8 30,4 30,-32 -60,-44" fill="#232730" stroke="#7BB661" strokeWidth="0.7" />
        {/* L2 — side wall */}
        <polygon points="30,4 60,-10 60,-46 30,-32" fill="#1a1d24" stroke="#7BB661" strokeWidth="0.7" />

        {/* L2 window */}
        <rect x="-6" y="-22" width="18" height="14" fill="#0a0b0d" stroke="#7BB661" strokeWidth="0.6" />

        {/* roof slab */}
        <polygon points="-60,-44 30,-32 60,-46 -30,-58" fill="#3a4150" stroke="#7BB661" strokeWidth="0.6" />

        {/* level lines on side */}
        <line x1="60" y1="28" x2="68" y2="32" stroke="#5a6275" strokeDasharray="2 1" strokeWidth="0.5" />
        <line x1="60" y1="-10" x2="68" y2="-6" stroke="#5a6275" strokeDasharray="2 1" strokeWidth="0.5" />
        <line x1="60" y1="-46" x2="68" y2="-42" stroke="#5a6275" strokeDasharray="2 1" strokeWidth="0.5" />
        <text x="70" y="34" fontSize="6" fontFamily="ui-monospace, monospace" fill="#5a6275">L1</text>
        <text x="70" y="-4" fontSize="6" fontFamily="ui-monospace, monospace" fill="#5a6275">L2</text>
        <text x="70" y="-40" fontSize="6" fontFamily="ui-monospace, monospace" fill="#5a6275">ROOF</text>
      </g>

      {/* compile arrow between source and building */}
      <g stroke="#ffd633" strokeWidth="0.8" fill="none" strokeLinecap="round">
        <line x1="146" y1="92" x2="166" y2="92" />
        <polygon points="166,92 161,89 161,95" fill="#ffd633" />
      </g>
      <text x="156" y="86" textAnchor="middle" fontSize="6.5" fontFamily="ui-monospace, monospace" fill="#ffd633">
        compile
      </text>

      <text x="296" y="32" textAnchor="end" fontSize="7" fontFamily="ui-monospace, monospace" fill="#5a6275">
        IfcOpenShell
      </text>
    </svg>
  )
}
