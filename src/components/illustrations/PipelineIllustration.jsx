/**
 * PipelineIllustration — wide section divider showing the data flow:
 *   sketch → .feature → assembly → drawing / BOM / G-code / IFC / gerber.
 * Sits between the capability tour and the recently-shipped strip;
 * intended to be displayed at full width with no border.
 *
 * viewBox 720×120. Kept thin so it doesn't add vertical weight.
 */
export default function PipelineIllustration({ className = '' }) {
  const nodes = [
    { x: 60, label: '.sketch', sub: '2D + constraints', glyph: 'sketch' },
    { x: 180, label: '.feature', sub: 'OCCT B-rep', glyph: 'feature' },
    { x: 300, label: '.assembly', sub: 'mates + BOM', glyph: 'assembly' },
    { x: 460, label: '.drawing', sub: 'TechDraw', glyph: 'drawing' },
    { x: 620, label: '.cam', sub: 'G-code', glyph: 'gcode' },
  ]

  return (
    <svg
      viewBox="0 0 720 120"
      preserveAspectRatio="xMidYMid meet"
      className={className}
      role="img"
      aria-label="Sketch flowing through feature, assembly, drawing, and CAM stages"
    >
      <defs>
        <marker id="pipe-arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto">
          <path d="M0,0 L10,5 L0,10 z" fill="#3a4150" />
        </marker>
      </defs>

      {/* horizontal flow line */}
      <line x1="40" y1="60" x2="680" y2="60" stroke="#1a1d24" strokeWidth="1" />

      {nodes.map((n, i) => (
        <g key={n.label}>
          {/* connector */}
          {i > 0 && (
            <line
              x1={nodes[i - 1].x + 36}
              y1="60"
              x2={n.x - 36}
              y2="60"
              stroke="#3a4150"
              strokeWidth="1"
              markerEnd="url(#pipe-arrow)"
              strokeDasharray="3 3"
            />
          )}

          {/* node */}
          <circle cx={n.x} cy="60" r="22" fill="#0f1115" stroke="#3a4150" strokeWidth="1" />
          <NodeGlyph kind={n.glyph} cx={n.x} cy="60" />

          {/* label above */}
          <text x={n.x} y="28" textAnchor="middle" fontSize="9" fontFamily="ui-monospace, monospace" fill="#ffd633">
            {n.label}
          </text>
          {/* sub label below */}
          <text x={n.x} y="100" textAnchor="middle" fontSize="8" fontFamily="ui-monospace, monospace" fill="#5a6275">
            {n.sub}
          </text>
        </g>
      ))}
    </svg>
  )
}

function NodeGlyph({ kind, cx, cy }) {
  const color = '#ffd633'
  if (kind === 'sketch') {
    return (
      <g stroke={color} strokeWidth="1.2" fill="none" strokeLinecap="round">
        <line x1={cx - 10} y1={cy + 4} x2={cx + 10} y2={cy + 4} />
        <line x1={cx - 10} y1={cy + 4} x2={cx - 10} y2={cy - 6} />
        <circle cx={cx + 10} cy={cy - 6} r="4" />
      </g>
    )
  }
  if (kind === 'feature') {
    return (
      <g>
        <polygon points={`${cx - 10},${cy + 6} ${cx},${cy + 9} ${cx + 10},${cy + 3} ${cx},${cy}`} fill="none" stroke={color} strokeWidth="1" />
        <polygon points={`${cx - 10},${cy + 6} ${cx},${cy + 9} ${cx},${cy - 6} ${cx - 10},${cy - 9}`} fill="none" stroke={color} strokeWidth="1" />
        <polygon points={`${cx},${cy + 9} ${cx + 10},${cy + 3} ${cx + 10},${cy - 12} ${cx},${cy - 6}`} fill="none" stroke={color} strokeWidth="1" />
      </g>
    )
  }
  if (kind === 'assembly') {
    return (
      <g fill="none" stroke={color} strokeWidth="1">
        <circle cx={cx - 6} cy={cy - 4} r="4" />
        <circle cx={cx + 6} cy={cy + 4} r="4" />
        <line x1={cx - 4} y1={cy - 2} x2={cx + 4} y2={cy + 2} />
      </g>
    )
  }
  if (kind === 'drawing') {
    return (
      <g stroke={color} strokeWidth="1" fill="none" strokeLinecap="round">
        <rect x={cx - 10} y={cy - 8} width="20" height="16" />
        <line x1={cx - 10} y1={cy - 4} x2={cx + 10} y2={cy - 4} />
        <line x1={cx - 7} y1={cy} x2={cx + 5} y2={cy} />
        <line x1={cx - 7} y1={cy + 4} x2={cx + 2} y2={cy + 4} />
      </g>
    )
  }
  if (kind === 'gcode') {
    return (
      <g stroke={color} strokeWidth="1" fill="none" strokeLinecap="round">
        <rect x={cx - 10} y={cy - 6} width="20" height="12" rx="1" />
        <path d={`M ${cx - 8} ${cy - 2} L ${cx - 4} ${cy + 2} L ${cx} ${cy - 2} L ${cx + 4} ${cy + 2} L ${cx + 8} ${cy - 2}`} />
      </g>
    )
  }
  return null
}
