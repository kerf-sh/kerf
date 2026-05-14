/**
 * PipelineIllustration — wide section divider showing the data flow:
 *   sketch → .feature → assembly → drawing → .cam.
 * Sits between the capability tour and the recently-shipped strip;
 * displays full width with no border.
 */
export default function PipelineIllustration({ className = '' }) {
  const nodes = [
    { x: 80, label: '.sketch', sub: '2D + constraints', glyph: 'sketch' },
    { x: 220, label: '.feature', sub: 'OCCT B-rep', glyph: 'feature' },
    { x: 360, label: '.assembly', sub: 'mates + BOM', glyph: 'assembly' },
    { x: 500, label: '.drawing', sub: 'TechDraw', glyph: 'drawing' },
    { x: 640, label: '.cam', sub: 'G-code', glyph: 'gcode' },
  ]

  const NODE_R = 28
  const Y = 80

  return (
    <svg
      viewBox="0 0 720 140"
      preserveAspectRatio="xMidYMid meet"
      className={className}
      role="img"
      aria-label="Sketch flowing through feature, assembly, drawing, and CAM stages"
    >
      <defs>
        <marker
          id="pipe-arrow"
          viewBox="0 0 10 10"
          refX="9"
          refY="5"
          markerWidth="5"
          markerHeight="5"
          orient="auto"
        >
          <path d="M0,1 L9,5 L0,9 Z" fill="#4a5161" />
        </marker>
      </defs>

      {nodes.map((n, i) => {
        const prev = nodes[i - 1]
        return (
          <g key={n.label}>
            {i > 0 && (
              <line
                x1={prev.x + NODE_R + 4}
                y1={Y}
                x2={n.x - NODE_R - 6}
                y2={Y}
                stroke="#4a5161"
                strokeWidth="1.25"
                markerEnd="url(#pipe-arrow)"
              />
            )}

            {/* label above */}
            <text
              x={n.x}
              y={Y - NODE_R - 12}
              textAnchor="middle"
              fontSize="10"
              fontFamily="ui-monospace, SFMono-Regular, monospace"
              fill="#ffd633"
              fontWeight="500"
            >
              {n.label}
            </text>

            {/* outer ring (subtle glow) */}
            <circle
              cx={n.x}
              cy={Y}
              r={NODE_R}
              fill="#0f1115"
              stroke="#2a2f3a"
              strokeWidth="1"
            />
            {/* inner stroke */}
            <circle
              cx={n.x}
              cy={Y}
              r={NODE_R - 4}
              fill="none"
              stroke="#1e2230"
              strokeWidth="1"
            />

            <NodeGlyph kind={n.glyph} cx={n.x} cy={Y} />

            {/* sub label below */}
            <text
              x={n.x}
              y={Y + NODE_R + 18}
              textAnchor="middle"
              fontSize="9"
              fontFamily="ui-monospace, SFMono-Regular, monospace"
              fill="#6a7185"
            >
              {n.sub}
            </text>
          </g>
        )
      })}
    </svg>
  )
}

function NodeGlyph({ kind, cx, cy }) {
  const stroke = '#ffd633'

  if (kind === 'sketch') {
    // L-shape with a dimension tick + a small circle (constraint marker)
    return (
      <g stroke={stroke} strokeWidth="1.4" fill="none" strokeLinecap="round" strokeLinejoin="round">
        <path d={`M ${cx - 10} ${cy + 7} L ${cx - 10} ${cy - 5} L ${cx + 8} ${cy - 5}`} />
        {/* dimension tick */}
        <line x1={cx - 10} y1={cy + 10} x2={cx + 8} y2={cy + 10} strokeDasharray="1.5 1.5" opacity="0.5" />
        <line x1={cx - 10} y1={cy + 9} x2={cx - 10} y2={cy + 11} />
        <line x1={cx + 8} y1={cy + 9} x2={cx + 8} y2={cy + 11} />
        {/* constraint dot */}
        <circle cx={cx + 8} cy={cy - 5} r="1.5" fill={stroke} stroke="none" />
      </g>
    )
  }

  if (kind === 'feature') {
    // clean axonometric cube, contained
    const s = 9
    return (
      <g stroke={stroke} strokeWidth="1.2" fill="none" strokeLinejoin="round">
        {/* front face */}
        <path d={`M ${cx - s} ${cy - s/2} L ${cx} ${cy + s/2} L ${cx + s} ${cy - s/2} L ${cx} ${cy - s * 1.5} Z`} />
        {/* left face */}
        <path d={`M ${cx - s} ${cy - s/2} L ${cx - s} ${cy + s/2} L ${cx} ${cy + s * 1.5} L ${cx} ${cy + s/2} Z`} />
        {/* right face */}
        <path d={`M ${cx + s} ${cy - s/2} L ${cx + s} ${cy + s/2} L ${cx} ${cy + s * 1.5} L ${cx} ${cy + s/2} Z`} />
      </g>
    )
  }

  if (kind === 'assembly') {
    // 3 interlocking dots representing components
    return (
      <g stroke={stroke} strokeWidth="1.2" fill="none">
        <circle cx={cx - 6} cy={cy - 5} r="5" />
        <circle cx={cx + 6} cy={cy - 5} r="5" />
        <circle cx={cx} cy={cy + 5} r="5" />
      </g>
    )
  }

  if (kind === 'drawing') {
    // page with title block + lines
    return (
      <g stroke={stroke} strokeWidth="1.2" fill="none" strokeLinejoin="round">
        <rect x={cx - 11} y={cy - 10} width="22" height="20" rx="1" />
        <line x1={cx - 11} y1={cy - 3} x2={cx + 11} y2={cy - 3} />
        <line x1={cx - 8} y1={cy + 2} x2={cx + 4} y2={cy + 2} opacity="0.7" />
        <line x1={cx - 8} y1={cy + 6} x2={cx + 6} y2={cy + 6} opacity="0.7" />
      </g>
    )
  }

  if (kind === 'gcode') {
    // tool path zigzag with a cutter circle
    return (
      <g stroke={stroke} strokeWidth="1.2" fill="none" strokeLinecap="round" strokeLinejoin="round">
        <path d={`M ${cx - 11} ${cy + 5} L ${cx - 5} ${cy - 4} L ${cx + 1} ${cy + 5} L ${cx + 7} ${cy - 4}`} />
        <circle cx={cx + 7} cy={cy - 4} r="2.5" fill="#0f1115" />
      </g>
    )
  }

  return null
}
