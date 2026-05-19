/**
 * Civil engineering illustration — Pratt bridge truss + horizontal alignment.
 */
export default function CivilIllustration({ className = '', size = 120 }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 120 120"
      fill="none"
      className={className}
      aria-hidden="true"
    >
      {/* Road alignment (plan view strip) */}
      <rect x="8" y="88" width="104" height="20" rx="2" stroke="currentColor" strokeWidth="0.8" className="stroke-kerf-300" opacity="0.3" />
      {/* Centre line */}
      <line x1="8" y1="98" x2="112" y2="98" stroke="currentColor" strokeWidth="0.6" className="stroke-kerf-500" strokeDasharray="6 4" opacity="0.5" />
      {/* Lane markings */}
      {[0, 1, 2, 3, 4].map((i) => (
        <line key={i} x1={20 + i * 18} y1="93" x2={26 + i * 18} y2="93" stroke="currentColor" strokeWidth="0.6" className="stroke-kerf-300" opacity="0.35" />
      ))}

      {/* Pratt truss bridge — 4-panel */}
      {/* Bottom chord */}
      <line x1="10" y1="78" x2="110" y2="78" stroke="currentColor" strokeWidth="2" className="stroke-kerf-300" />
      {/* Top chord */}
      <line x1="10" y1="40" x2="110" y2="40" stroke="currentColor" strokeWidth="2" className="stroke-kerf-300" />

      {/* Vertical members */}
      <line x1="10" y1="40" x2="10" y2="78" stroke="currentColor" strokeWidth="1.5" className="stroke-kerf-300" />
      <line x1="35" y1="40" x2="35" y2="78" stroke="currentColor" strokeWidth="1.2" className="stroke-kerf-500" />
      <line x1="60" y1="40" x2="60" y2="78" stroke="currentColor" strokeWidth="1.2" className="stroke-kerf-500" />
      <line x1="85" y1="40" x2="85" y2="78" stroke="currentColor" strokeWidth="1.2" className="stroke-kerf-500" />
      <line x1="110" y1="40" x2="110" y2="78" stroke="currentColor" strokeWidth="1.5" className="stroke-kerf-300" />

      {/* Diagonal members — Pratt pattern (diagonals in tension point inward) */}
      <line x1="10" y1="78" x2="35" y2="40" stroke="currentColor" strokeWidth="1" className="stroke-kerf-300" opacity="0.7" />
      <line x1="35" y1="78" x2="60" y2="40" stroke="currentColor" strokeWidth="1" className="stroke-kerf-300" opacity="0.7" />
      <line x1="85" y1="78" x2="60" y2="40" stroke="currentColor" strokeWidth="1" className="stroke-kerf-300" opacity="0.7" />
      <line x1="110" y1="78" x2="85" y2="40" stroke="currentColor" strokeWidth="1" className="stroke-kerf-300" opacity="0.7" />

      {/* Abutments */}
      <polygon points="10,78 4,88 16,88" stroke="currentColor" strokeWidth="1" className="stroke-kerf-500" fill="none" />
      <polygon points="110,78 104,88 116,88" stroke="currentColor" strokeWidth="1" className="stroke-kerf-500" fill="none" />

      {/* Deck (road surface on bridge) */}
      <line x1="10" y1="82" x2="110" y2="82" stroke="currentColor" strokeWidth="1" className="stroke-kerf-300" opacity="0.5" />

      {/* Load arrows (UDL) */}
      {[25, 45, 65, 85].map((x) => (
        <g key={x}>
          <line x1={x} y1="32" x2={x} y2="40" stroke="currentColor" strokeWidth="0.8" className="stroke-kerf-500" opacity="0.6" />
          <polygon points={`${x},40 ${x - 3},34 ${x + 3},34`} fill="currentColor" className="stroke-kerf-500" opacity="0.6" />
        </g>
      ))}
      {/* UDL top line */}
      <line x1="13" y1="32" x2="107" y2="32" stroke="currentColor" strokeWidth="0.8" className="stroke-kerf-300" opacity="0.4" />

      {/* Span dimension */}
      <line x1="10" y1="20" x2="110" y2="20" stroke="currentColor" strokeWidth="0.5" className="stroke-kerf-300" opacity="0.4" />
      <line x1="10" y1="18" x2="10" y2="22" stroke="currentColor" strokeWidth="0.5" className="stroke-kerf-300" opacity="0.4" />
      <line x1="110" y1="18" x2="110" y2="22" stroke="currentColor" strokeWidth="0.5" className="stroke-kerf-300" opacity="0.4" />
    </svg>
  )
}
