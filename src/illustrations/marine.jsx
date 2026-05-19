/**
 * Marine illustration — hull cross-section with waterline and frame stations.
 */
export default function MarineIllustration({ className = '', size = 120 }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 120 120"
      fill="none"
      className={className}
      aria-hidden="true"
    >
      {/* Hull cross-section (midship frame) */}
      <path
        d="M20 30 C20 30 18 55 18 70 C18 88 35 100 60 102 C85 100 102 88 102 70 C102 55 100 30 100 30"
        stroke="currentColor"
        strokeWidth="1.5"
        className="stroke-kerf-300"
        fill="none"
      />

      {/* Deck line */}
      <line x1="20" y1="30" x2="100" y2="30" stroke="currentColor" strokeWidth="1.2" className="stroke-kerf-300" />

      {/* Waterline */}
      <line x1="10" y1="68" x2="110" y2="68" stroke="currentColor" strokeWidth="1.2" className="stroke-kerf-500" strokeDasharray="6 3" />
      {/* Wave undulation on waterline */}
      <path d="M10 72 C20 70 30 74 40 72 C50 70 60 74 70 72 C80 70 90 74 100 72 C105 71 108 72 110 72" stroke="currentColor" strokeWidth="0.7" className="stroke-kerf-300" opacity="0.4" />

      {/* Frame station lines (cross-sections) */}
      {[30, 45, 60, 75, 90].map((x) => {
        const y1 = 30
        const yBot = 30 + Math.sqrt(Math.max(0, 1 - ((x - 60) / 42) ** 2)) * 72
        return (
          <line
            key={x}
            x1={x}
            y1={y1}
            x2={x}
            y2={yBot}
            stroke="currentColor"
            strokeWidth="0.6"
            className="stroke-kerf-300"
            strokeDasharray="3 2"
            opacity="0.4"
          />
        )
      })}

      {/* Keel */}
      <line x1="57" y1="100" x2="63" y2="100" stroke="currentColor" strokeWidth="2" className="stroke-kerf-500" />
      <line x1="60" y1="100" x2="60" y2="115" stroke="currentColor" strokeWidth="1.5" className="stroke-kerf-500" />

      {/* Bilge keel */}
      <path d="M30 90 L24 96 L24 100" stroke="currentColor" strokeWidth="1" className="stroke-kerf-300" opacity="0.6" strokeLinecap="round" />
      <path d="M90 90 L96 96 L96 100" stroke="currentColor" strokeWidth="1" className="stroke-kerf-300" opacity="0.6" strokeLinecap="round" />

      {/* Draft marks */}
      {[0, 1, 2].map((i) => (
        <line key={i} x1="106" y1={60 + i * 8} x2="112" y2={60 + i * 8} stroke="currentColor" strokeWidth="0.6" className="stroke-kerf-300" opacity="0.5" />
      ))}
      {[0, 1, 2].map((i) => (
        <line key={i} x1="8" y1={60 + i * 8} x2="14" y2={60 + i * 8} stroke="currentColor" strokeWidth="0.6" className="stroke-kerf-300" opacity="0.5" />
      ))}

      {/* Beam dimension */}
      <line x1="20" y1="22" x2="100" y2="22" stroke="currentColor" strokeWidth="0.5" className="stroke-kerf-300" opacity="0.4" />
      <line x1="20" y1="20" x2="20" y2="24" stroke="currentColor" strokeWidth="0.5" className="stroke-kerf-300" opacity="0.4" />
      <line x1="100" y1="20" x2="100" y2="24" stroke="currentColor" strokeWidth="0.5" className="stroke-kerf-300" opacity="0.4" />
    </svg>
  )
}
