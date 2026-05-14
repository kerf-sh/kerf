/**
 * CamIllustration — toolpath simulator over a pocketed plate, with
 * G-code stream above. Suggests "model → CAM → CNC" without copy.
 *
 * viewBox 320×200.
 */
export default function CamIllustration({ className = '' }) {
  // Concentric-offset pocket toolpath inside a 120×60 rectangle.
  // Outer rect at (110,90,230,150). Concentric offsets inset by 6/12/18.
  const passes = [
    { x: 112, y: 92, w: 116, h: 56 },
    { x: 118, y: 98, w: 104, h: 44 },
    { x: 124, y: 104, w: 92, h: 32 },
    { x: 130, y: 110, w: 80, h: 20 },
  ]

  return (
    <svg
      viewBox="0 0 320 200"
      preserveAspectRatio="xMidYMid meet"
      className={className}
      role="img"
      aria-label="CAM toolpath of a pocketing op with a G-code stream above the stock"
    >
      <rect x="8" y="14" width="304" height="172" rx="8" fill="#0a0b0d" stroke="#1a1d24" />
      <text x="22" y="32" fontSize="8" fontFamily="ui-monospace, monospace" fill="#5a6275" letterSpacing="1.4">
        CAM · 2.5D POCKET
      </text>

      {/* G-code panel (top) */}
      <rect x="20" y="40" width="280" height="36" rx="4" fill="#0f1115" stroke="#1a1d24" />
      <text x="28" y="52" fontSize="7" fontFamily="ui-monospace, monospace" fill="#5a6275">
        G-code · LinuxCNC post
      </text>
      <g fontSize="6.5" fontFamily="ui-monospace, monospace" fill="#b8bfcc">
        <text x="28" y="62">G21 G17 G90 G94</text>
        <text x="118" y="62">G0 Z5</text>
        <text x="158" y="62">T1 M6</text>
        <text x="200" y="62">S12000 M3</text>
        <text x="28" y="72" fill="#ffd633">G1 X12 Y6 F800</text>
        <text x="118" y="72">G1 Z-1.5</text>
        <text x="158" y="72" fill="#ffd633">G2 X18 Y0 I6 J0</text>
        <text x="232" y="72">…</text>
      </g>

      {/* stock plate */}
      <g>
        <rect x="100" y="84" width="140" height="78" rx="2" fill="#14171c" stroke="#5a6275" strokeWidth="0.6" />
        <rect x="110" y="90" width="120" height="60" rx="2" fill="#0a0b0d" stroke="#3a4150" strokeWidth="0.6" />
      </g>

      {/* concentric offset toolpath inside pocket */}
      <g fill="none" stroke="#ffd633" strokeWidth="0.7" strokeLinejoin="round">
        {passes.map((p) => (
          <rect key={`${p.x}-${p.y}`} x={p.x} y={p.y} width={p.w} height={p.h} rx="2" />
        ))}
      </g>

      {/* rapid retract dashed lines between passes */}
      <g stroke="#6bd4ff" strokeWidth="0.5" strokeDasharray="2 2" fill="none">
        <line x1="112" y1="92" x2="118" y2="98" />
        <line x1="118" y1="98" x2="124" y2="104" />
        <line x1="124" y1="104" x2="130" y2="110" />
      </g>

      {/* current tool position with cutter circle */}
      <g>
        <circle cx="170" cy="120" r="6" fill="none" stroke="#ff6b9b" strokeWidth="1.2" />
        <circle cx="170" cy="120" r="2" fill="#ff6b9b" />
        <line x1="170" y1="78" x2="170" y2="114" stroke="#ff6b9b" strokeWidth="0.6" strokeDasharray="1.5 1.5" />
      </g>

      {/* dimension callout */}
      <g stroke="#5a6275" strokeWidth="0.6" fill="none">
        <line x1="100" y1="170" x2="240" y2="170" />
        <line x1="100" y1="166" x2="100" y2="174" />
        <line x1="240" y1="166" x2="240" y2="174" />
      </g>
      <text x="170" y="178" textAnchor="middle" fontSize="7" fontFamily="ui-monospace, monospace" fill="#ffd633">
        140 mm
      </text>

      <text x="296" y="32" textAnchor="end" fontSize="7" fontFamily="ui-monospace, monospace" fill="#5a6275">
        OpenCAMlib
      </text>
    </svg>
  )
}
