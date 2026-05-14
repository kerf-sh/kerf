/**
 * TopoIllustration — SIMP-style density field becoming an organic
 * topology-optimised bracket. Left: density heatmap over a design domain
 * with load + supports. Right: the marching-cubes lattice that the
 * solver produces.
 *
 * viewBox 320×200.
 */
export default function TopoIllustration({ className = '' }) {
  // Design domain: 90×90 cells split into a 9×9 grid. Density values
  // chosen to evoke the canonical MBB-bracket result — a diagonal truss
  // forming under the load.
  const grid = [
    [0.0, 0.0, 0.1, 0.4, 0.7, 0.9, 0.8, 0.5, 0.0],
    [0.0, 0.1, 0.5, 0.8, 0.9, 0.9, 0.6, 0.2, 0.0],
    [0.1, 0.4, 0.9, 0.9, 0.7, 0.5, 0.3, 0.0, 0.0],
    [0.3, 0.8, 0.9, 0.6, 0.3, 0.2, 0.1, 0.0, 0.0],
    [0.6, 0.9, 0.7, 0.3, 0.2, 0.4, 0.6, 0.5, 0.2],
    [0.9, 0.8, 0.3, 0.1, 0.3, 0.6, 0.9, 0.9, 0.6],
    [0.9, 0.5, 0.1, 0.0, 0.2, 0.5, 0.9, 0.9, 0.8],
    [0.7, 0.2, 0.0, 0.0, 0.1, 0.3, 0.7, 0.9, 0.9],
    [0.3, 0.0, 0.0, 0.0, 0.0, 0.1, 0.4, 0.7, 0.9],
  ]

  const cell = 10
  const x0 = 20
  const y0 = 50

  return (
    <svg
      viewBox="0 0 320 200"
      preserveAspectRatio="xMidYMid meet"
      className={className}
      role="img"
      aria-label="Topology optimization density field on the left, generated organic bracket on the right"
    >
      <rect x="8" y="14" width="304" height="172" rx="8" fill="#0a0b0d" stroke="#1a1d24" />
      <text x="22" y="32" fontSize="8" fontFamily="ui-monospace, monospace" fill="#5a6275" letterSpacing="1.4">
        TOPOLOGY · SIMP
      </text>

      {/* density heatmap */}
      <g>
        {grid.map((row, r) =>
          row.map((d, c) => (
            <rect
              key={`${r}-${c}`}
              x={x0 + c * cell}
              y={y0 + r * cell}
              width={cell}
              height={cell}
              fill="#ffd633"
              fillOpacity={d * 0.85}
            />
          )),
        )}
        {/* domain border */}
        <rect
          x={x0}
          y={y0}
          width={cell * 9}
          height={cell * 9}
          fill="none"
          stroke="#3a4150"
          strokeWidth="0.6"
        />
      </g>

      {/* left support pinning */}
      <g stroke="#6bd4ff" strokeWidth="0.8" strokeLinecap="round">
        <polygon points="14,68 20,62 20,74" fill="#6bd4ff" fillOpacity="0.25" />
        <polygon points="14,128 20,122 20,134" fill="#6bd4ff" fillOpacity="0.25" />
        <line x1="10" y1="62" x2="14" y2="62" />
        <line x1="10" y1="74" x2="14" y2="74" />
        <line x1="10" y1="122" x2="14" y2="122" />
        <line x1="10" y1="134" x2="14" y2="134" />
      </g>

      {/* applied load (top-right corner of domain) */}
      <g stroke="#ff6b9b" strokeWidth="1.2" fill="none" strokeLinecap="round">
        <line x1="106" y1="38" x2="106" y2="50" />
        <line x1="102" y1="46" x2="106" y2="50" />
        <line x1="110" y1="46" x2="106" y2="50" />
      </g>
      <text x="112" y="42" fontSize="6.5" fontFamily="ui-monospace, monospace" fill="#ff6b9b">
        F
      </text>

      {/* arrow between domain and result */}
      <g stroke="#5a6275" strokeWidth="0.8" fill="none" strokeLinecap="round">
        <line x1="116" y1="92" x2="154" y2="92" strokeDasharray="2 2" />
        <polygon points="154,92 148,89 148,95" fill="#5a6275" />
      </g>
      <text x="136" y="86" textAnchor="middle" fontSize="6.5" fontFamily="ui-monospace, monospace" fill="#5a6275">
        OC + filter
      </text>

      {/* output bracket: organic truss with two pinned holes at left
          and a loaded eye at the upper right. Body is a single rounded
          path with two circular holes punched. */}
      <g transform="translate(168, 36)">
        <text x="56" y="6" textAnchor="middle" fontSize="7" fontFamily="ui-monospace, monospace" fill="#5a6275">
          NURBS BREP OUTPUT
        </text>
        <path
          d="
            M 10 26
            C 4 30, 4 54, 10 58
            C 18 64, 30 60, 38 60
            C 50 60, 56 92, 70 96
            C 86 100, 110 96, 106 78
            C 102 64, 86 60, 70 58
            C 58 56, 48 38, 50 28
            C 52 18, 64 12, 78 14
            C 92 16, 106 26, 102 18
            C 96 6, 56 0, 30 8
            C 18 12, 14 22, 10 26
            Z
          "
          fill="#ffd633"
          fillOpacity="0.18"
          stroke="#ffd633"
          strokeWidth="1"
        />
        {/* pin holes (left) */}
        <circle cx="14" cy="34" r="4" fill="#0a0b0d" stroke="#ffd633" strokeWidth="0.9" />
        <circle cx="14" cy="50" r="4" fill="#0a0b0d" stroke="#ffd633" strokeWidth="0.9" />
        {/* loaded eye (upper-right) */}
        <circle cx="92" cy="80" r="6" fill="#0a0b0d" stroke="#ffd633" strokeWidth="1" />
        {/* load arrow on the eye */}
        <g stroke="#ff6b9b" strokeWidth="1.2" fill="none" strokeLinecap="round">
          <line x1="92" y1="60" x2="92" y2="74" />
          <line x1="88" y1="70" x2="92" y2="74" />
          <line x1="96" y1="70" x2="92" y2="74" />
        </g>
      </g>

      {/* status */}
      <text x="22" y="178" fontSize="7" fontFamily="ui-monospace, monospace" fill="#5a6275">
        vol_frac 0.35
      </text>
      <text x="296" y="178" textAnchor="end" fontSize="7" fontFamily="ui-monospace, monospace" fill="#5a6275">
        50 iter · compliance ↓ 74%
      </text>
    </svg>
  )
}
