/**
 * Horology illustration — escapement wheel + pallet fork + gear train.
 */
export default function HorologyIllustration({ className = '', size = 120 }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 120 120"
      fill="none"
      className={className}
      aria-hidden="true"
    >
      {/* Escape wheel */}
      <circle cx="45" cy="65" r="28" stroke="currentColor" strokeWidth="1" className="stroke-kerf-300" opacity="0.3" />
      <circle cx="45" cy="65" r="22" stroke="currentColor" strokeWidth="1" className="stroke-kerf-300" />
      {/* Escape wheel teeth — 15 teeth */}
      {Array.from({ length: 15 }, (_, i) => {
        const angle = (i * 24 * Math.PI) / 180
        const x1 = 45 + 22 * Math.cos(angle)
        const y1 = 65 + 22 * Math.sin(angle)
        const x2 = 45 + 28 * Math.cos(angle - 0.12)
        const y2 = 65 + 28 * Math.sin(angle - 0.12)
        const x3 = 45 + 28 * Math.cos(angle + 0.06)
        const y3 = 65 + 28 * Math.sin(angle + 0.06)
        return (
          <polygon
            key={i}
            points={`${x1.toFixed(1)},${y1.toFixed(1)} ${x2.toFixed(1)},${y2.toFixed(1)} ${x3.toFixed(1)},${y3.toFixed(1)}`}
            stroke="currentColor"
            strokeWidth="0.8"
            fill="none"
            className="stroke-kerf-300"
          />
        )
      })}
      {/* Hub */}
      <circle cx="45" cy="65" r="4" stroke="currentColor" strokeWidth="1" className="stroke-kerf-500" />
      <circle cx="45" cy="65" r="1.5" stroke="currentColor" strokeWidth="0.8" className="stroke-kerf-300" />

      {/* Pallet fork */}
      <line x1="72" y1="48" x2="82" y2="65" stroke="currentColor" strokeWidth="1.5" className="stroke-kerf-500" strokeLinecap="round" />
      <line x1="82" y1="65" x2="72" y2="82" stroke="currentColor" strokeWidth="1.5" className="stroke-kerf-500" strokeLinecap="round" />
      {/* Entry pallet stone */}
      <rect x="69" y="45" width="6" height="9" rx="1" stroke="currentColor" strokeWidth="1" className="stroke-kerf-300" transform="rotate(-15 72 49)" />
      {/* Exit pallet stone */}
      <rect x="69" y="79" width="6" height="9" rx="1" stroke="currentColor" strokeWidth="1" className="stroke-kerf-300" transform="rotate(15 72 83)" />
      {/* Pivot */}
      <circle cx="84" cy="65" r="3" stroke="currentColor" strokeWidth="1" className="stroke-kerf-500" />
      {/* Guard pin */}
      <line x1="84" y1="65" x2="96" y2="65" stroke="currentColor" strokeWidth="1.2" className="stroke-kerf-300" opacity="0.6" />

      {/* Balance wheel (impulse roller) */}
      <circle cx="100" cy="45" r="14" stroke="currentColor" strokeWidth="1" className="stroke-kerf-300" />
      <circle cx="100" cy="45" r="10" stroke="currentColor" strokeWidth="0.6" className="stroke-kerf-300" opacity="0.4" strokeDasharray="2 2" />
      {/* Balance spokes */}
      <line x1="100" y1="31" x2="100" y2="59" stroke="currentColor" strokeWidth="0.8" className="stroke-kerf-300" opacity="0.5" />
      <line x1="86" y1="45" x2="114" y2="45" stroke="currentColor" strokeWidth="0.8" className="stroke-kerf-300" opacity="0.5" />
      <circle cx="100" cy="45" r="2.5" stroke="currentColor" strokeWidth="0.8" className="stroke-kerf-500" />

      {/* Gear train — small gear */}
      <circle cx="95" cy="98" r="10" stroke="currentColor" strokeWidth="0.9" className="stroke-kerf-300" opacity="0.6" />
      {Array.from({ length: 10 }, (_, i) => {
        const angle = (i * 36 * Math.PI) / 180
        const x = 95 + 10 * Math.cos(angle)
        const y = 98 + 10 * Math.sin(angle)
        const x2 = 95 + 13 * Math.cos(angle)
        const y2 = 98 + 13 * Math.sin(angle)
        return <line key={i} x1={x.toFixed(1)} y1={y.toFixed(1)} x2={x2.toFixed(1)} y2={y2.toFixed(1)} stroke="currentColor" strokeWidth="0.8" className="stroke-kerf-300" opacity="0.5" />
      })}
      <circle cx="95" cy="98" r="2.5" stroke="currentColor" strokeWidth="0.8" className="stroke-kerf-500" opacity="0.6" />
    </svg>
  )
}
