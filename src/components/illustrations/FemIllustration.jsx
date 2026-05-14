/**
 * FemIllustration — cantilever beam under load with a coarse triangular
 * FEM mesh and a deformed-shape overlay. Stress colours map cool → hot
 * along the beam length using the ink/kerf/red accent palette.
 *
 * viewBox 320×200, panel inset 8..312 × 14..186.
 */
export default function FemIllustration({ className = '' }) {
  // Colour ramp: cool (cyan-edge) at fixed end, kerf-yellow mid,
  // warm (orange) at the free end where stress is highest.
  const ramp = ['#3a4150', '#4f6378', '#6bd4ff', '#9cd97a', '#ffd633', '#ff944d', '#e85a3c']

  // Coarse triangular mesh of a 200×40 rectangle in 4 rows × 10 cols
  // produces 80 tris. Top edge is loaded (down arrows); left edge is
  // clamped (hatching).
  const rows = 4
  const cols = 10
  const x0 = 56
  const y0 = 60
  const w = 200
  const h = 80
  const cw = w / cols
  const rh = h / rows

  const tris = []
  for (let r = 0; r < rows; r++) {
    for (let c = 0; c < cols; c++) {
      const ax = x0 + c * cw
      const ay = y0 + r * rh
      const bx = ax + cw
      const by = ay
      const cx = ax
      const cy = ay + rh
      const dx = bx
      const dy = cy
      // Stress proxy: grows with distance from clamped (left) end and
      // with distance from the neutral axis (top/bottom rows hotter
      // than middle). Cantilever-bending-ish.
      const distFromClamp = (c + 0.5) / cols
      const distFromAxis = Math.abs((r + 0.5) / rows - 0.5) * 2
      const stress = Math.min(1, 0.3 * distFromClamp + 0.7 * distFromClamp * distFromAxis)
      const idx = Math.min(ramp.length - 1, Math.floor(stress * (ramp.length - 1)))
      tris.push(
        <polygon
          key={`t1-${r}-${c}`}
          points={`${ax},${ay} ${bx},${by} ${cx},${cy}`}
          fill={ramp[idx]}
          fillOpacity="0.65"
          stroke="#0a0b0d"
          strokeWidth="0.4"
        />,
        <polygon
          key={`t2-${r}-${c}`}
          points={`${bx},${by} ${dx},${dy} ${cx},${cy}`}
          fill={ramp[idx]}
          fillOpacity="0.65"
          stroke="#0a0b0d"
          strokeWidth="0.4"
        />,
      )
    }
  }

  // Deformed-shape overlay: a cubic-ish curve along the beam centerline
  // shifted downward, communicating displacement.
  const def = []
  for (let c = 0; c <= cols; c++) {
    const t = c / cols
    const y = y0 + h / 2 + t * t * 14 // quadratic-ish deflection
    def.push(`${x0 + c * cw},${y}`)
  }

  return (
    <svg
      viewBox="0 0 320 200"
      preserveAspectRatio="xMidYMid meet"
      className={className}
      role="img"
      aria-label="Cantilever beam with FEM mesh, fixed at the left, loaded on top, deformed shape overlaid"
    >
      <rect x="8" y="14" width="304" height="172" rx="8" fill="#0a0b0d" stroke="#1a1d24" />
      <text x="22" y="32" fontSize="8" fontFamily="ui-monospace, monospace" fill="#5a6275" letterSpacing="1.4">
        FEM · LINEAR STATIC
      </text>

      {/* clamped wall hatching */}
      <g stroke="#5a6275" strokeWidth="0.8" strokeLinecap="round">
        <line x1="48" y1="50" x2="56" y2="42" />
        <line x1="48" y1="62" x2="56" y2="54" />
        <line x1="48" y1="74" x2="56" y2="66" />
        <line x1="48" y1="86" x2="56" y2="78" />
        <line x1="48" y1="98" x2="56" y2="90" />
        <line x1="48" y1="110" x2="56" y2="102" />
        <line x1="48" y1="122" x2="56" y2="114" />
        <line x1="48" y1="134" x2="56" y2="126" />
        <line x1="48" y1="146" x2="56" y2="138" />
        <line x1="48" y1="158" x2="56" y2="150" />
        <line x1="56" y1="50" x2="56" y2="160" />
      </g>

      {/* mesh tris */}
      <g>{tris}</g>

      {/* beam outline on top */}
      <rect x={x0} y={y0} width={w} height={h} fill="none" stroke="#5a6275" strokeWidth="0.8" />

      {/* load arrows on top edge */}
      <g stroke="#ff6b9b" strokeWidth="1.2" fill="none" strokeLinecap="round">
        {[80, 120, 160, 200, 240].map((x) => (
          <g key={x}>
            <line x1={x} y1="44" x2={x} y2="58" />
            <line x1={x - 3} y1="54" x2={x} y2="58" />
            <line x1={x + 3} y1="54" x2={x} y2="58" />
          </g>
        ))}
      </g>
      <text x="160" y="40" textAnchor="middle" fontSize="7" fontFamily="ui-monospace, monospace" fill="#ff6b9b">
        F = 250 N
      </text>

      {/* deformed-shape overlay */}
      <polyline
        points={def.join(' ')}
        fill="none"
        stroke="#ffd633"
        strokeWidth="1.4"
        strokeDasharray="3 2"
      />
      <text x="256" y="158" fontSize="7" fontFamily="ui-monospace, monospace" fill="#ffd633">
        δ 0.42 mm
      </text>

      {/* colour bar legend */}
      <g transform="translate(22, 168)">
        {ramp.map((c, i) => (
          <rect key={c} x={i * 18} y="0" width="18" height="6" fill={c} fillOpacity="0.85" />
        ))}
        <text x="0" y="14" fontSize="6.5" fontFamily="ui-monospace, monospace" fill="#5a6275">
          0
        </text>
        <text x={ramp.length * 18} y="14" textAnchor="end" fontSize="6.5" fontFamily="ui-monospace, monospace" fill="#5a6275">
          σ_y
        </text>
      </g>

      <text x="296" y="178" textAnchor="end" fontSize="7" fontFamily="ui-monospace, monospace" fill="#5a6275">
        FoS 2.8 · dolfinx
      </text>
    </svg>
  )
}
