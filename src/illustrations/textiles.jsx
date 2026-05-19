/**
 * Textiles illustration — plain weave fabric pattern + sewing needle.
 */
export default function TextilesIllustration({ className = '', size = 120 }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 120 120"
      fill="none"
      className={className}
      aria-hidden="true"
    >
      {/* Woven fabric grid — plain weave pattern */}
      {/* Warp threads (vertical) */}
      {[0, 1, 2, 3, 4, 5, 6, 7].map((col) => {
        const x = 12 + col * 12
        return (
          <line
            key={`warp-${col}`}
            x1={x}
            y1="12"
            x2={x}
            y2="88"
            stroke="currentColor"
            strokeWidth="2"
            className="stroke-kerf-300"
            opacity="0.5"
          />
        )
      })}

      {/* Weft threads (horizontal) with over-under weave */}
      {[0, 1, 2, 3, 4, 5, 6].map((row) => {
        const y = 18 + row * 11
        const offset = row % 2 === 0 ? 0 : 6
        return (
          <g key={`weft-${row}`}>
            {/* Continuous weft line */}
            <line x1="12" y1={y} x2="96" y2={y} stroke="currentColor" strokeWidth="2" className="stroke-kerf-500" opacity="0.3" />
            {/* Over-crossings (weft over warp) */}
            {[0, 1, 2, 3, 4, 5, 6, 7].map((col) => {
              const x = 12 + col * 12
              const isOver = (col + row) % 2 === 0
              if (!isOver) return null
              return (
                <line
                  key={`cross-${col}`}
                  x1={x - 1}
                  y1={y - 2}
                  x2={x + 1}
                  y2={y + 2}
                  stroke="currentColor"
                  strokeWidth="3"
                  className="stroke-kerf-500"
                  opacity="0.6"
                  strokeLinecap="round"
                />
              )
            })}
          </g>
        )
      })}

      {/* Fabric border */}
      <rect x="12" y="12" width="84" height="76" stroke="currentColor" strokeWidth="1" className="stroke-kerf-300" opacity="0.6" />

      {/* Needle */}
      <path d="M95 95 L108 18" stroke="currentColor" strokeWidth="1.8" className="stroke-kerf-300" strokeLinecap="round" />
      {/* Needle eye */}
      <ellipse cx="107" cy="20" rx="2" ry="4" stroke="currentColor" strokeWidth="1.2" className="stroke-kerf-500" transform="rotate(-8 107 20)" />
      {/* Needle point */}
      <circle cx="96" cy="93" r="1" stroke="currentColor" strokeWidth="0.8" className="stroke-kerf-300" />

      {/* Thread through eye and stitch */}
      <path d="M108 18 C112 22 112 30 108 35 C104 40 96 95" stroke="currentColor" strokeWidth="0.7" className="stroke-kerf-300" strokeDasharray="3 2" opacity="0.5" />
      {/* Thread tail */}
      <path d="M96 95 C90 100 85 105 78 108" stroke="currentColor" strokeWidth="0.7" className="stroke-kerf-300" strokeDasharray="3 2" opacity="0.5" />
    </svg>
  )
}
