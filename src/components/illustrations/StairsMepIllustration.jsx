/**
 * StairsMepIllustration — left half: isometric stair stringer with
 * railing balusters. Right half: orthogonal duct trunk with a branch
 * and a register fitting. Communicates "stairs · railings · MEP".
 *
 * viewBox 320×200. Palette locked.
 */
export default function StairsMepIllustration({ className = '' }) {
  // Stair geometry — 5 treads stepping up. Each tread is a flat top with
  // a riser face. Drawn axonometrically.
  const treads = []
  const stepW = 14 // horizontal advance per step (front edge)
  const stepRise = 10 // vertical rise per step
  const treadDepth = 18 // front-to-back (axonometric)
  const treadHeight = 5 // visible tread slab thickness
  const dxIso = 9 // x-skew for back face

  const startX = 36
  const startY = 156

  for (let i = 0; i < 5; i++) {
    const x = startX + i * stepW
    const y = startY - i * stepRise
    // front face (rectangle)
    const frontPts = [
      [x, y],
      [x + stepW, y],
      [x + stepW, y - treadHeight],
      [x, y - treadHeight],
    ]
    // top face (top of tread - parallelogram into iso)
    const topPts = [
      [x, y - treadHeight],
      [x + stepW, y - treadHeight],
      [x + stepW + dxIso, y - treadHeight - treadDepth * 0.45],
      [x + dxIso, y - treadHeight - treadDepth * 0.45],
    ]
    // riser face (front of next step's body)
    const riserPts = [
      [x + stepW, y],
      [x + stepW + dxIso, y - treadDepth * 0.45],
      [x + stepW + dxIso, y - treadHeight - treadDepth * 0.45],
      [x + stepW, y - treadHeight],
    ]

    treads.push(
      <g key={i}>
        <polygon
          points={frontPts.map((p) => p.join(',')).join(' ')}
          fill="#ffd633"
          fillOpacity="0.18"
          stroke="#ffd633"
          strokeWidth="0.9"
          strokeLinejoin="round"
        />
        <polygon
          points={topPts.map((p) => p.join(',')).join(' ')}
          fill="#ffd633"
          fillOpacity="0.32"
          stroke="#ffd633"
          strokeWidth="0.9"
          strokeLinejoin="round"
        />
        <polygon
          points={riserPts.map((p) => p.join(',')).join(' ')}
          fill="#ffd633"
          fillOpacity="0.08"
          stroke="#ffd633"
          strokeWidth="0.7"
          strokeLinejoin="round"
        />
      </g>,
    )
  }

  // Railing balusters — vertical posts on the upper edge of each tread.
  const balusters = []
  for (let i = 0; i < 5; i++) {
    const x = startX + i * stepW + dxIso * 0.5 + 4
    const yTop = startY - i * stepRise - treadHeight - treadDepth * 0.45 * 0.5
    const yBot = yTop - 18
    balusters.push(
      <line
        key={`bal-${i}`}
        x1={x}
        y1={yTop}
        x2={x}
        y2={yBot}
        stroke="#8a93a6"
        strokeWidth="0.9"
        strokeLinecap="round"
      />,
    )
  }
  // top rail (sloped)
  const railStartX = startX + dxIso * 0.5 + 4
  const railStartY = startY - 0 * stepRise - treadHeight - treadDepth * 0.45 * 0.5 - 18
  const railEndX = startX + 4 * stepW + dxIso * 0.5 + 4
  const railEndY = startY - 4 * stepRise - treadHeight - treadDepth * 0.45 * 0.5 - 18

  return (
    <svg
      viewBox="0 0 320 200"
      preserveAspectRatio="xMidYMid meet"
      className={className}
      role="img"
      aria-label="An isometric stair with railing balusters on the left and an orthogonal duct trunk with a branch on the right"
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
        STAIRS · MEP
      </text>
      <line x1="22" y1="40" x2="298" y2="40" stroke="#1a1d24" strokeWidth="0.6" />

      {/* divider */}
      <line x1="160" y1="50" x2="160" y2="178" stroke="#1a1d24" strokeWidth="0.6" strokeDasharray="2 3" />

      {/* === LEFT: stair === */}
      <text
        x="28"
        y="58"
        fontSize="7"
        fontFamily="ui-monospace, monospace"
        fill="#5a6275"
        letterSpacing="1.2"
      >
        STAIR · RAILING
      </text>
      <g>{treads}</g>
      <g>{balusters}</g>
      {/* top rail (sloped) */}
      <line
        x1={railStartX}
        y1={railStartY}
        x2={railEndX}
        y2={railEndY}
        stroke="#cbd0dc"
        strokeWidth="1.3"
        strokeLinecap="round"
      />
      {/* tiny rise/run callout */}
      <g
        fontSize="6.5"
        fontFamily="ui-monospace, monospace"
        fill="#5a6275"
      >
        <text x="36" y="174">
          5 risers · 180 mm
        </text>
      </g>

      {/* === RIGHT: MEP duct === */}
      <text
        x="174"
        y="58"
        fontSize="7"
        fontFamily="ui-monospace, monospace"
        fill="#5a6275"
        letterSpacing="1.2"
      >
        MEP · DUCT
      </text>

      {/* Main horizontal duct (trunk) — drawn as two parallel lines */}
      <g stroke="#cbd0dc" strokeWidth="1.1" fill="none" strokeLinecap="round">
        <line x1="172" y1="92" x2="294" y2="92" />
        <line x1="172" y1="104" x2="294" y2="104" />
        {/* end caps */}
        <line x1="172" y1="92" x2="172" y2="104" />
      </g>
      {/* duct centerline (kerf yellow accent) */}
      <line
        x1="172"
        y1="98"
        x2="294"
        y2="98"
        stroke="#ffd633"
        strokeWidth="0.6"
        strokeDasharray="2 2"
      />

      {/* Branch duct going down (tee) at x=220 */}
      <g stroke="#cbd0dc" strokeWidth="1.1" fill="none" strokeLinecap="round">
        <line x1="214" y1="104" x2="214" y2="150" />
        <line x1="226" y1="104" x2="226" y2="150" />
        <line x1="214" y1="150" x2="226" y2="150" />
      </g>
      <line
        x1="220"
        y1="104"
        x2="220"
        y2="150"
        stroke="#ffd633"
        strokeWidth="0.6"
        strokeDasharray="2 2"
      />

      {/* Pipe (smaller diameter, parallel) below trunk on right */}
      <g stroke="#8a93a6" strokeWidth="0.9" fill="none" strokeLinecap="round">
        <line x1="240" y1="126" x2="294" y2="126" />
        <line x1="240" y1="132" x2="294" y2="132" />
        {/* elbow up */}
        <path d="M 240 132 Q 236 132 236 128 L 236 116" />
        <path d="M 240 126 Q 238 126 238 124 L 238 116" />
      </g>

      {/* Register grille at bottom of branch */}
      <g>
        <rect x="208" y="152" width="24" height="10" rx="1" fill="#0a0b0d" stroke="#ffd633" strokeWidth="0.8" />
        <line x1="212" y1="155" x2="212" y2="159" stroke="#ffd633" strokeWidth="0.6" />
        <line x1="216" y1="155" x2="216" y2="159" stroke="#ffd633" strokeWidth="0.6" />
        <line x1="220" y1="155" x2="220" y2="159" stroke="#ffd633" strokeWidth="0.6" />
        <line x1="224" y1="155" x2="224" y2="159" stroke="#ffd633" strokeWidth="0.6" />
        <line x1="228" y1="155" x2="228" y2="159" stroke="#ffd633" strokeWidth="0.6" />
      </g>
      <text
        x="220"
        y="172"
        textAnchor="middle"
        fontSize="6.5"
        fontFamily="ui-monospace, monospace"
        fill="#5a6275"
      >
        register
      </text>

      {/* duct size label */}
      <text
        x="282"
        y="88"
        textAnchor="end"
        fontSize="6.5"
        fontFamily="ui-monospace, monospace"
        fill="#ffd633"
      >
        300×100
      </text>
    </svg>
  )
}
