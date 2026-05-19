/**
 * Mechanical illustration — wireframe gear + sketch construction line + extrude arrow.
 */
export default function MechanicalIllustration({ className = '', size = 120 }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 120 120"
      fill="none"
      className={className}
      aria-hidden="true"
    >
      {/* Sketch construction lines */}
      <line x1="10" y1="10" x2="60" y2="10" stroke="currentColor" strokeWidth="0.5" strokeDasharray="3 2" className="stroke-kerf-300" opacity="0.5" />
      <line x1="10" y1="10" x2="10" y2="60" stroke="currentColor" strokeWidth="0.5" strokeDasharray="3 2" className="stroke-kerf-300" opacity="0.5" />
      <line x1="60" y1="10" x2="60" y2="60" stroke="currentColor" strokeWidth="0.5" strokeDasharray="3 2" opacity="0.3" />
      <line x1="10" y1="60" x2="60" y2="60" stroke="currentColor" strokeWidth="0.5" strokeDasharray="3 2" opacity="0.3" />

      {/* Extrude arrow */}
      <line x1="60" y1="60" x2="90" y2="30" stroke="currentColor" strokeWidth="1" className="stroke-kerf-500" opacity="0.7" />
      <polygon points="90,30 84,34 86,28" fill="currentColor" className="stroke-kerf-500" opacity="0.7" />
      <line x1="10" y1="60" x2="40" y2="30" stroke="currentColor" strokeWidth="0.7" opacity="0.4" />
      <line x1="40" y1="30" x2="90" y2="30" stroke="currentColor" strokeWidth="0.7" opacity="0.4" />

      {/* Gear body (outer) */}
      <circle cx="80" cy="82" r="22" stroke="currentColor" strokeWidth="1.5" className="stroke-kerf-300" />
      {/* Gear teeth — 8 teeth */}
      {[0, 45, 90, 135, 180, 225, 270, 315].map((deg) => {
        const rad = (deg * Math.PI) / 180
        const x1 = 80 + 22 * Math.cos(rad)
        const y1 = 82 + 22 * Math.sin(rad)
        const x2 = 80 + 29 * Math.cos(rad - 0.18)
        const y2 = 82 + 29 * Math.sin(rad - 0.18)
        const x3 = 80 + 29 * Math.cos(rad + 0.18)
        const y3 = 82 + 29 * Math.sin(rad + 0.18)
        return (
          <polygon
            key={deg}
            points={`${x1.toFixed(1)},${y1.toFixed(1)} ${x2.toFixed(1)},${y2.toFixed(1)} ${x3.toFixed(1)},${y3.toFixed(1)}`}
            stroke="currentColor"
            strokeWidth="1"
            fill="none"
            className="stroke-kerf-300"
          />
        )
      })}
      {/* Gear hub */}
      <circle cx="80" cy="82" r="8" stroke="currentColor" strokeWidth="1.2" className="stroke-kerf-500" />
      <circle cx="80" cy="82" r="3" stroke="currentColor" strokeWidth="1" className="stroke-kerf-300" />

      {/* Dimension line */}
      <line x1="56" y1="108" x2="104" y2="108" stroke="currentColor" strokeWidth="0.6" opacity="0.5" />
      <line x1="56" y1="105" x2="56" y2="111" stroke="currentColor" strokeWidth="0.6" opacity="0.5" />
      <line x1="104" y1="105" x2="104" y2="111" stroke="currentColor" strokeWidth="0.6" opacity="0.5" />
    </svg>
  )
}
