/**
 * FineGrainedUndoIllustration — horizontal timeline of 8 file_revisions.
 * The 6th dot is "current" (highlighted yellow ring); a curving back-arrow
 * from current to revision 3 represents Cmd+Z. Below the timeline, a thin
 * diff bar shows colored segments (green added, pink removed, gray
 * unchanged) — the Phase 4 diff-storage view.
 *
 * viewBox 320×200. Palette locked.
 */
export default function FineGrainedUndoIllustration({ className = '' }) {
  // 8 revisions evenly spaced along the timeline.
  const dotCount = 8
  const x0 = 40
  const x1 = 282
  const yTimeline = 90
  const dots = []
  for (let i = 0; i < dotCount; i++) {
    dots.push(x0 + (i / (dotCount - 1)) * (x1 - x0))
  }
  const currentIdx = 5 // 6th dot (zero-indexed 5)
  const targetIdx = 2 // back to rev 3

  // Diff bar segments — each represents a contiguous slice of the diff.
  // Colors: green = added, pink = removed, gray = unchanged.
  const segments = [
    { w: 28, color: '#3a4150' }, // unchanged
    { w: 18, color: '#7BB661' }, // added
    { w: 36, color: '#3a4150' }, // unchanged
    { w: 14, color: '#ff6bd4' }, // removed
    { w: 22, color: '#7BB661' }, // added
    { w: 30, color: '#3a4150' }, // unchanged
    { w: 12, color: '#ff6bd4' }, // removed
    { w: 26, color: '#3a4150' }, // unchanged
    { w: 16, color: '#7BB661' }, // added
    { w: 40, color: '#3a4150' }, // unchanged
  ]
  // Compute starting x for diff bar to fit within 22..298 = 276px wide.
  const diffStartX = 22
  const diffY = 138
  const diffH = 10

  // Build cubic back-arrow path from current → target.
  const cx = dots[currentIdx]
  const tx = dots[targetIdx]
  const arcPath = `M ${cx - 1} ${yTimeline - 8} C ${cx - 6} ${yTimeline - 40}, ${tx + 6} ${yTimeline - 40}, ${tx + 1} ${yTimeline - 8}`

  return (
    <svg
      viewBox="0 0 320 200"
      preserveAspectRatio="xMidYMid meet"
      className={className}
      role="img"
      aria-label="A timeline of 8 file revisions with the 6th marked current; a back-arrow returns to revision 3; below it, a diff bar shows added, removed, and unchanged segments"
    >
      <defs>
        <marker
          id="undo-arrow"
          viewBox="0 0 10 10"
          refX="9"
          refY="5"
          markerWidth="6"
          markerHeight="6"
          orient="auto"
        >
          <path d="M0,1 L9,5 L0,9 Z" fill="#ffd633" />
        </marker>
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
        FILE REVISIONS
      </text>
      <line x1="22" y1="40" x2="298" y2="40" stroke="#1a1d24" strokeWidth="0.6" />

      {/* timeline axis */}
      <line
        x1={x0 - 6}
        y1={yTimeline}
        x2={x1 + 6}
        y2={yTimeline}
        stroke="#3a4150"
        strokeWidth="0.9"
      />

      {/* === Back arrow (under-curve, drawn before dots so dots sit on top) === */}
      <path
        d={arcPath}
        fill="none"
        stroke="#ffd633"
        strokeWidth="1.3"
        strokeLinecap="round"
        markerEnd="url(#undo-arrow)"
      />
      <text
        x={(cx + tx) / 2}
        y={yTimeline - 44}
        textAnchor="middle"
        fontSize="7.5"
        fontFamily="ui-monospace, monospace"
        fill="#ffd633"
      >
        Cmd+Z
      </text>

      {/* dots */}
      {dots.map((dx, i) => {
        const isCurrent = i === currentIdx
        const isTarget = i === targetIdx
        return (
          <g key={i}>
            {isCurrent && (
              <circle
                cx={dx}
                cy={yTimeline}
                r="7"
                fill="none"
                stroke="#ffd633"
                strokeOpacity="0.5"
                strokeWidth="0.9"
              />
            )}
            <circle
              cx={dx}
              cy={yTimeline}
              r="3.2"
              fill={isCurrent ? '#ffd633' : '#0a0b0d'}
              stroke={isCurrent ? '#ffd633' : isTarget ? '#cbd0dc' : '#5a6275'}
              strokeWidth="1"
            />
            <text
              x={dx}
              y={yTimeline + 16}
              textAnchor="middle"
              fontSize="6.5"
              fontFamily="ui-monospace, monospace"
              fill={isCurrent ? '#ffd633' : isTarget ? '#cbd0dc' : '#5a6275'}
            >
              r{i + 1}
            </text>
          </g>
        )
      })}

      {/* === Diff bar === */}
      <text
        x="22"
        y="128"
        fontSize="7"
        fontFamily="ui-monospace, monospace"
        fill="#5a6275"
        letterSpacing="1.2"
      >
        DIFF · PHASE 4
      </text>
      {/* diff bar background */}
      <rect
        x={diffStartX}
        y={diffY}
        width="276"
        height={diffH}
        rx="1.5"
        fill="#0d0f13"
        stroke="#1a1d24"
        strokeWidth="0.6"
      />
      {/* diff segments */}
      <g>
        {(() => {
          let cursor = diffStartX
          // Normalize segments to fit 276px total width.
          const total = segments.reduce((s, seg) => s + seg.w, 0)
          const scale = 274 / total
          cursor = diffStartX + 1
          return segments.map((seg, i) => {
            const w = seg.w * scale
            const rect = (
              <rect
                key={i}
                x={cursor}
                y={diffY + 1}
                width={w}
                height={diffH - 2}
                fill={seg.color}
                fillOpacity={seg.color === '#3a4150' ? 0.55 : 0.7}
              />
            )
            cursor += w
            return rect
          })
        })()}
      </g>

      {/* diff legend */}
      <g transform="translate(22, 158)" fontSize="6.5" fontFamily="ui-monospace, monospace">
        <g>
          <rect width="8" height="4" y="2" fill="#7BB661" fillOpacity="0.7" />
          <text x="12" y="8" fill="#cbd0dc">
            added
          </text>
        </g>
        <g transform="translate(54, 0)">
          <rect width="8" height="4" y="2" fill="#ff6bd4" fillOpacity="0.7" />
          <text x="12" y="8" fill="#cbd0dc">
            removed
          </text>
        </g>
        <g transform="translate(118, 0)">
          <rect width="8" height="4" y="2" fill="#3a4150" />
          <text x="12" y="8" fill="#cbd0dc">
            unchanged
          </text>
        </g>
      </g>

      {/* shrink caption */}
      <text
        x="296"
        y="166"
        textAnchor="end"
        fontSize="7"
        fontFamily="ui-monospace, monospace"
        fill="#ffd633"
      >
        ~82× shrink
      </text>
      <text
        x="296"
        y="178"
        textAnchor="end"
        fontSize="6.5"
        fontFamily="ui-monospace, monospace"
        fill="#5a6275"
      >
        SHA-256 dedup
      </text>
    </svg>
  )
}
