/**
 * ViewportScaleIllustration — axonometric grid of cubes representing
 * instanced rendering. A frustum cone overlays the front rows;
 * cubes inside the frustum are bright (rendered), cubes outside are
 * dim (culled).
 *
 * viewBox 320×200. Palette locked.
 */
export default function ViewportScaleIllustration({ className = '' }) {
  // Grid: 6 cols × 4 rows. Each cube drawn as a tiny axonometric.
  const cols = 6
  const rows = 4
  const cellW = 32
  const cellH = 26
  const x0 = 38
  const y0 = 72

  // Frustum projection: apex at the bottom-center, fans out toward top
  // covering ~front 2 rows and center 4 cols.
  const apexX = 160
  const apexY = 178
  // The frustum is the triangular region from apex out to the back-left
  // and back-right of the visible "view." We'll define it as a polygon.
  const frustumPoly = `${apexX},${apexY} 56,90 264,90`

  // Determine which cube is "inside" the frustum (rows 2–3, cols 1–4)
  // i.e. front rows, middle cols.
  function isInside(r, c) {
    return r >= 2 && c >= 1 && c <= 4
  }

  const cubes = []
  for (let r = 0; r < rows; r++) {
    for (let c = 0; c < cols; c++) {
      const inside = isInside(r, c)
      const cx = x0 + c * cellW + (rows - 1 - r) * 6
      const cy = y0 + r * cellH
      cubes.push(
        <MiniCube
          key={`${r}-${c}`}
          cx={cx}
          cy={cy}
          bright={inside}
        />,
      )
    }
  }

  return (
    <svg
      viewBox="0 0 320 200"
      preserveAspectRatio="xMidYMid meet"
      className={className}
      role="img"
      aria-label="An axonometric grid of cubes with a camera frustum overlay; cubes inside the frustum are bright (rendered), cubes outside are dim (culled)"
    >
      <rect x="8" y="14" width="304" height="172" rx="8" fill="#0a0b0d" stroke="#1a1d24" />

      {/* header */}
      <text
        x="22"
        y="32"
        fontSize="9"
        fontFamily="ui-monospace, SFMono-Regular, monospace"
        fill="#6a7185"
        letterSpacing="1.4"
      >
        VIEWPORT · INSTANCED
      </text>
      <line x1="22" y1="40" x2="298" y2="40" stroke="#1a1d24" strokeWidth="0.6" />

      {/* === cubes (back rows first, drawn dim) === */}
      <g>{cubes}</g>

      {/* === frustum overlay === */}
      <polygon
        points={frustumPoly}
        fill="#ffd633"
        fillOpacity="0.06"
        stroke="#ffd633"
        strokeOpacity="0.7"
        strokeWidth="1"
        strokeDasharray="3 2"
      />
      {/* camera body at apex */}
      <g transform={`translate(${apexX}, ${apexY})`}>
        <rect x="-7" y="-6" width="14" height="9" rx="1.5" fill="#0a0b0d" stroke="#ffd633" strokeWidth="1" />
        <rect x="-3" y="-9" width="6" height="3" rx="0.5" fill="#0a0b0d" stroke="#ffd633" strokeWidth="0.8" />
        <circle cx="0" cy="-1.5" r="2" fill="#ffd633" />
      </g>

      {/* === info chips === */}
      <g transform="translate(22, 168)">
        <rect width="80" height="12" rx="2" fill="#ffd633" fillOpacity="0.12" stroke="#ffd633" strokeOpacity="0.5" />
        <text x="40" y="8.5" textAnchor="middle" fontSize="7" fontFamily="ui-monospace, monospace" fill="#ffd633">
          instances: 240
        </text>
      </g>
      <g transform="translate(108, 168)">
        <rect width="64" height="12" rx="2" fill="#0a0b0d" stroke="#3a4150" />
        <text x="32" y="8.5" textAnchor="middle" fontSize="7" fontFamily="ui-monospace, monospace" fill="#7BB661">
          drawcalls: 1
        </text>
      </g>
      <g transform="translate(178, 168)">
        <rect width="60" height="12" rx="2" fill="#0a0b0d" stroke="#3a4150" />
        <text x="30" y="8.5" textAnchor="middle" fontSize="7" fontFamily="ui-monospace, monospace" fill="#cbd0dc">
          60 fps
        </text>
      </g>

      {/* small label near frustum */}
      <text
        x="244"
        y="62"
        textAnchor="end"
        fontSize="6.5"
        fontFamily="ui-monospace, monospace"
        fill="#5a6275"
        letterSpacing="1.1"
      >
        FRUSTUM S1 · INSTANCEDMESH S2
      </text>
    </svg>
  )
}

/** Tiny axonometric cube. 12×12 footprint with a 4-unit iso skew. */
function MiniCube({ cx, cy, bright }) {
  const s = 7 // half-side of the cube square
  const dx = 4 // iso skew x
  const dy = 3 // iso skew y (negative for upward)
  // Front face (square)
  const frontPts = [
    [cx - s, cy + s],
    [cx + s, cy + s],
    [cx + s, cy - s],
    [cx - s, cy - s],
  ]
  // Top face (parallelogram)
  const topPts = [
    [cx - s, cy - s],
    [cx + s, cy - s],
    [cx + s + dx, cy - s - dy],
    [cx - s + dx, cy - s - dy],
  ]
  // Right face (parallelogram)
  const rightPts = [
    [cx + s, cy + s],
    [cx + s, cy - s],
    [cx + s + dx, cy - s - dy],
    [cx + s + dx, cy + s - dy],
  ]

  const strokeC = bright ? '#ffd633' : '#3a4150'
  const opF = bright ? 0.22 : 0.08
  const opT = bright ? 0.4 : 0.14
  const opR = bright ? 0.14 : 0.06

  return (
    <g strokeLinejoin="round">
      <polygon
        points={frontPts.map((p) => p.join(',')).join(' ')}
        fill="#ffd633"
        fillOpacity={opF}
        stroke={strokeC}
        strokeWidth="0.7"
      />
      <polygon
        points={topPts.map((p) => p.join(',')).join(' ')}
        fill="#ffd633"
        fillOpacity={opT}
        stroke={strokeC}
        strokeWidth="0.7"
      />
      <polygon
        points={rightPts.map((p) => p.join(',')).join(' ')}
        fill="#ffd633"
        fillOpacity={opR}
        stroke={strokeC}
        strokeWidth="0.7"
      />
    </g>
  )
}
