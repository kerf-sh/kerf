/**
 * RfAnalysisIllustration — Smith chart with an S11 trace curving toward
 * the center. VSWR readout in the corner.
 *
 * viewBox 320×200. Palette locked.
 */
export default function RfAnalysisIllustration({ className = '' }) {
  // Smith chart geometry: outer unit circle radius R centered at (CX, CY).
  // Constant-resistance circles are tangent to the right edge of the
  // outer circle. For normalized resistance r, the circle has
  //   center = (CX + R*r/(1+r), CY)
  //   radius = R / (1+r)
  // Constant-reactance circles (arcs) have center (CX + R, CY ± R/|x|)
  // and radius R/|x|, but only the portion inside the unit circle is
  // drawn (we approximate with a clipPath against the outer circle).
  const CX = 160
  const CY = 118
  const R = 60

  const rCircles = [0.2, 0.5, 1, 2, 5]
  const xArcs = [0.5, 1, 2]

  // Trace from outer-right (high return loss) curving toward center.
  // Parameterize a spiral from theta=0 at radius R to theta=π at radius ~R*0.2.
  const tracePoints = []
  const steps = 48
  for (let i = 0; i <= steps; i++) {
    const t = i / steps
    const radius = R * (1 - 0.78 * t)
    const theta = -Math.PI * 0.85 * t // sweep counter-clockwise into upper-left
    const x = CX + radius * Math.cos(theta)
    const y = CY + radius * Math.sin(theta)
    tracePoints.push(`${x.toFixed(2)},${y.toFixed(2)}`)
  }

  // Marker on the trace (chosen frequency)
  const markerIdx = Math.floor(steps * 0.7)
  const markerParts = tracePoints[markerIdx].split(',')
  const markerX = parseFloat(markerParts[0])
  const markerY = parseFloat(markerParts[1])

  return (
    <svg
      viewBox="0 0 320 200"
      preserveAspectRatio="xMidYMid meet"
      className={className}
      role="img"
      aria-label="Smith chart with an S11 trace curving from the outer edge toward the center, with VSWR readout"
    >
      <defs>
        <clipPath id="rf-smith-clip">
          <circle cx={CX} cy={CY} r={R} />
        </clipPath>
      </defs>

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
        S-PARAMETERS · SMITH
      </text>
      <line x1="22" y1="40" x2="298" y2="40" stroke="#1a1d24" strokeWidth="0.6" />

      {/* === Smith chart === */}
      {/* outer unit circle */}
      <circle cx={CX} cy={CY} r={R} fill="#0d0f13" stroke="#5a6275" strokeWidth="0.9" />
      {/* horizontal axis (real line) */}
      <line
        x1={CX - R}
        y1={CY}
        x2={CX + R}
        y2={CY}
        stroke="#5a6275"
        strokeWidth="0.6"
      />

      {/* constant-resistance circles */}
      <g
        clipPath="url(#rf-smith-clip)"
        stroke="#3a4150"
        strokeWidth="0.5"
        fill="none"
      >
        {rCircles.map((r) => {
          const cx = CX + (R * r) / (1 + r)
          const radius = R / (1 + r)
          return <circle key={`r-${r}`} cx={cx} cy={CY} r={radius} />
        })}
      </g>

      {/* constant-reactance arcs (upper and lower) */}
      <g
        clipPath="url(#rf-smith-clip)"
        stroke="#3a4150"
        strokeWidth="0.5"
        fill="none"
      >
        {xArcs.map((x) => {
          const radius = R / x
          // upper arc center
          const cy1 = CY - R / x
          // lower arc center
          const cy2 = CY + R / x
          return (
            <g key={`x-${x}`}>
              <circle cx={CX + R} cy={cy1} r={radius} />
              <circle cx={CX + R} cy={cy2} r={radius} />
            </g>
          )
        })}
      </g>

      {/* center dot (match point) */}
      <circle cx={CX} cy={CY} r="1.5" fill="#5a6275" />

      {/* S11 trace */}
      <polyline
        points={tracePoints.join(' ')}
        fill="none"
        stroke="#ffd633"
        strokeWidth="1.4"
        strokeLinejoin="round"
        strokeLinecap="round"
      />
      {/* trace endpoint marker (start) */}
      <circle
        cx={parseFloat(tracePoints[0].split(',')[0])}
        cy={parseFloat(tracePoints[0].split(',')[1])}
        r="2"
        fill="#ffd633"
        fillOpacity="0.5"
      />
      {/* marker dot at selected frequency */}
      <g>
        <circle cx={markerX} cy={markerY} r="3" fill="#ffd633" />
        <circle cx={markerX} cy={markerY} r="5.5" fill="none" stroke="#ffd633" strokeOpacity="0.5" strokeWidth="0.8" />
      </g>

      {/* Γ label near center */}
      <text
        x={CX + 6}
        y={CY - 4}
        fontSize="8"
        fontFamily="ui-monospace, monospace"
        fill="#cbd0dc"
      >
        Γ
      </text>

      {/* === Side readouts === */}
      <g transform="translate(238, 56)">
        <text
          x="0"
          y="0"
          fontSize="7"
          fontFamily="ui-monospace, monospace"
          fill="#5a6275"
          letterSpacing="1.2"
        >
          READOUT
        </text>
        <text x="0" y="14" fontSize="7.5" fontFamily="ui-monospace, monospace" fill="#cbd0dc">
          |S11|
        </text>
        <text x="56" y="14" textAnchor="end" fontSize="7.5" fontFamily="ui-monospace, monospace" fill="#ffd633">
          −12.4 dB
        </text>
        <text x="0" y="26" fontSize="7.5" fontFamily="ui-monospace, monospace" fill="#cbd0dc">
          VSWR
        </text>
        <text x="56" y="26" textAnchor="end" fontSize="7.5" fontFamily="ui-monospace, monospace" fill="#ffd633">
          1.62
        </text>
        <text x="0" y="38" fontSize="7.5" fontFamily="ui-monospace, monospace" fill="#cbd0dc">
          K
        </text>
        <text x="56" y="38" textAnchor="end" fontSize="7.5" fontFamily="ui-monospace, monospace" fill="#7BB661">
          1.18
        </text>
        <text x="0" y="50" fontSize="7.5" fontFamily="ui-monospace, monospace" fill="#cbd0dc">
          Gmax
        </text>
        <text x="56" y="50" textAnchor="end" fontSize="7.5" fontFamily="ui-monospace, monospace" fill="#ffd633">
          14.2 dB
        </text>
      </g>

      {/* sweep range caption */}
      <text
        x={CX}
        y="186"
        textAnchor="middle"
        fontSize="6.5"
        fontFamily="ui-monospace, monospace"
        fill="#5a6275"
      >
        2.4 – 5.8 GHz · scikit-rf
      </text>

      {/* small chip label */}
      <g transform="translate(22, 168)">
        <rect width="62" height="12" rx="2" fill="#ffd633" fillOpacity="0.12" stroke="#ffd633" strokeOpacity="0.45" />
        <text x="31" y="8.5" textAnchor="middle" fontSize="7" fontFamily="ui-monospace, monospace" fill="#ffd633">
          .s2p import
        </text>
      </g>
    </svg>
  )
}
