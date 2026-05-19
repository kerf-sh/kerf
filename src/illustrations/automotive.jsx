/**
 * Automotive illustration — class-A surface with zebra stripe analysis lines.
 */
export default function AutomotiveIllustration({ className = '', size = 120 }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 120 120"
      fill="none"
      className={className}
      aria-hidden="true"
    >
      {/* Body surface silhouette — side profile spline */}
      <path
        d="M10 80 C10 80 20 78 35 72 C50 66 55 55 65 48 C75 41 90 38 105 40 C108 41 110 45 110 50 L110 80 Z"
        stroke="currentColor"
        strokeWidth="1.5"
        className="stroke-kerf-300"
      />

      {/* Zebra stripes (reflection lines for class-A quality) */}
      <clipPath id="body-clip">
        <path d="M10 80 C10 80 20 78 35 72 C50 66 55 55 65 48 C75 41 90 38 105 40 C108 41 110 45 110 50 L110 80 Z" />
      </clipPath>
      <g clipPath="url(#body-clip)">
        <path d="M15 48 C35 44 55 44 75 46 C90 47 100 52 110 56" stroke="currentColor" strokeWidth="2.5" className="stroke-kerf-500" opacity="0.4" />
        <path d="M12 56 C32 52 52 52 72 54 C87 55 100 60 110 64" stroke="currentColor" strokeWidth="2.5" className="stroke-kerf-300" opacity="0.25" />
        <path d="M10 64 C30 60 50 60 70 62 C85 63 98 68 110 72" stroke="currentColor" strokeWidth="2.5" className="stroke-kerf-500" opacity="0.4" />
        <path d="M10 72 C30 68 50 68 70 70 C85 71 98 75 110 80" stroke="currentColor" strokeWidth="2.5" className="stroke-kerf-300" opacity="0.25" />
        <path d="M18 40 C40 36 62 36 80 40 C92 43 102 48 110 52" stroke="currentColor" strokeWidth="2.5" className="stroke-kerf-500" opacity="0.4" />
      </g>

      {/* Wheel arches */}
      <path d="M30 80 A14 10 0 0 0 58 80" stroke="currentColor" strokeWidth="1.2" className="stroke-kerf-300" />
      <path d="M75 80 A14 10 0 0 0 103 80" stroke="currentColor" strokeWidth="1.2" className="stroke-kerf-300" />

      {/* Wheels */}
      <circle cx="44" cy="84" r="10" stroke="currentColor" strokeWidth="1" className="stroke-kerf-500" />
      <circle cx="44" cy="84" r="5" stroke="currentColor" strokeWidth="0.8" className="stroke-kerf-300" />
      <circle cx="89" cy="84" r="10" stroke="currentColor" strokeWidth="1" className="stroke-kerf-500" />
      <circle cx="89" cy="84" r="5" stroke="currentColor" strokeWidth="0.8" className="stroke-kerf-300" />

      {/* Windscreen */}
      <path d="M65 48 C70 44 80 42 90 42 L95 48" stroke="currentColor" strokeWidth="0.9" className="stroke-kerf-300" opacity="0.6" />

      {/* Curvature comb ticks on roof line */}
      {[0, 0.2, 0.4, 0.6, 0.8, 1.0].map((t) => {
        const x = 35 + t * 70
        const y = 72 - t * 24 + Math.sin(t * Math.PI) * 4
        return (
          <line
            key={t}
            x1={x}
            y1={y}
            x2={x}
            y2={y - 8 - Math.sin(t * Math.PI) * 6}
            stroke="currentColor"
            strokeWidth="0.6"
            className="stroke-kerf-300"
            opacity="0.5"
          />
        )
      })}
    </svg>
  )
}
