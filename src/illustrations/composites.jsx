/**
 * Composites illustration — ply stack-up with fiber direction arrows.
 */
export default function CompositesIllustration({ className = '', size = 120 }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 120 120"
      fill="none"
      className={className}
      aria-hidden="true"
    >
      {/* Stack of plies — isometric-ish stack */}
      {/* Ply 5 (bottom) — 90° */}
      <path d="M15 90 L105 90 L105 98 L15 98 Z" stroke="currentColor" strokeWidth="1" className="stroke-kerf-300" opacity="0.4" />
      {[0,1,2,3,4,5,6,7].map((i) => (
        <line key={i} x1={15} y1={91 + i} x2={105} y2={91 + i} stroke="currentColor" strokeWidth="0.4" className="stroke-kerf-300" opacity="0.2" />
      ))}

      {/* Ply 4 — 45° */}
      <path d="M15 80 L105 80 L105 88 L15 88 Z" stroke="currentColor" strokeWidth="1" className="stroke-kerf-500" opacity="0.5" />
      {[0,1,2,3,4,5,6].map((i) => (
        <line key={i} x1={15 + i * 14} y1="80" x2={15 + i * 14 - 8} y2="88" stroke="currentColor" strokeWidth="0.6" className="stroke-kerf-300" opacity="0.4" />
      ))}

      {/* Ply 3 — 0° */}
      <path d="M15 70 L105 70 L105 78 L15 78 Z" stroke="currentColor" strokeWidth="1.2" className="stroke-kerf-300" />
      {[0,1,2,3,4].map((i) => (
        <line key={i} x1="15" y1={71 + i * 1.5} x2="105" y2={71 + i * 1.5} stroke="currentColor" strokeWidth="0.8" className="stroke-kerf-500" opacity="0.5" />
      ))}

      {/* Ply 2 — -45° */}
      <path d="M15 60 L105 60 L105 68 L15 68 Z" stroke="currentColor" strokeWidth="1" className="stroke-kerf-500" opacity="0.5" />
      {[0,1,2,3,4,5,6].map((i) => (
        <line key={i} x1={15 + i * 14} y1="68" x2={15 + i * 14 + 8} y2="60" stroke="currentColor" strokeWidth="0.6" className="stroke-kerf-300" opacity="0.4" />
      ))}

      {/* Ply 1 (top) — 0° */}
      <path d="M15 50 L105 50 L105 58 L15 58 Z" stroke="currentColor" strokeWidth="1.2" className="stroke-kerf-300" />
      {[0,1,2,3,4].map((i) => (
        <line key={i} x1="15" y1={51 + i * 1.5} x2="105" y2={51 + i * 1.5} stroke="currentColor" strokeWidth="0.8" className="stroke-kerf-500" opacity="0.5" />
      ))}

      {/* Fiber direction annotations */}
      {/* 0° arrow */}
      <path d="M18 44 L30 44" stroke="currentColor" strokeWidth="1" className="stroke-kerf-300" strokeLinecap="round" />
      <polygon points="30,44 26,42 26,46" fill="currentColor" className="stroke-kerf-300" />
      <text x="14" y="43" fontSize="5" fill="currentColor" opacity="0.7" fontFamily="monospace">0°</text>

      {/* 45° arrow */}
      <path d="M18 34 L26 27" stroke="currentColor" strokeWidth="1" className="stroke-kerf-500" strokeLinecap="round" />
      <polygon points="26,27 22,29 24,33" fill="currentColor" className="stroke-kerf-500" opacity="0.8" />
      <text x="14" y="33" fontSize="5" fill="currentColor" opacity="0.7" fontFamily="monospace">45°</text>

      {/* -45° arrow */}
      <path d="M44 34 L52 27" stroke="currentColor" strokeWidth="1" className="stroke-kerf-500" strokeLinecap="round" transform="scale(1,-1) translate(0,-60)" />
      <path d="M44 34 L52 41" stroke="currentColor" strokeWidth="1" className="stroke-kerf-500" strokeLinecap="round" opacity="0.7" />
      <polygon points="52,41 47,39 49,43" fill="currentColor" className="stroke-kerf-500" opacity="0.6" />
      <text x="38" y="33" fontSize="5" fill="currentColor" opacity="0.7" fontFamily="monospace">-45°</text>

      {/* 90° arrow */}
      <path d="M75 44 L75 33" stroke="currentColor" strokeWidth="1" className="stroke-kerf-300" strokeLinecap="round" />
      <polygon points="75,33 73,37 77,37" fill="currentColor" className="stroke-kerf-300" />
      <text x="70" y="43" fontSize="5" fill="currentColor" opacity="0.7" fontFamily="monospace">90°</text>

      {/* Ply count label */}
      <line x1="108" y1="50" x2="108" y2="98" stroke="currentColor" strokeWidth="0.7" className="stroke-kerf-300" opacity="0.5" />
      <line x1="106" y1="50" x2="110" y2="50" stroke="currentColor" strokeWidth="0.7" className="stroke-kerf-300" opacity="0.5" />
      <line x1="106" y1="98" x2="110" y2="98" stroke="currentColor" strokeWidth="0.7" className="stroke-kerf-300" opacity="0.5" />
    </svg>
  )
}
