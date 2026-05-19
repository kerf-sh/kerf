/**
 * Silicon illustration — IC die floorplan + standard-cell rows.
 */
export default function SiliconIllustration({ className = '', size = 120 }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 120 120"
      fill="none"
      className={className}
      aria-hidden="true"
    >
      {/* Die outline */}
      <rect x="10" y="10" width="100" height="100" rx="2" stroke="currentColor" strokeWidth="1.5" className="stroke-kerf-300" />

      {/* Scribe lane */}
      <rect x="14" y="14" width="92" height="92" rx="1" stroke="currentColor" strokeWidth="0.5" className="stroke-kerf-300" opacity="0.4" strokeDasharray="2 2" />

      {/* Core logic block */}
      <rect x="18" y="18" width="50" height="44" rx="1" stroke="currentColor" strokeWidth="1" className="stroke-kerf-500" />
      {/* Standard cell rows inside core */}
      {[0, 1, 2, 3, 4, 5].map((i) => (
        <line
          key={i}
          x1="18"
          y1={25 + i * 6}
          x2="68"
          y2={25 + i * 6}
          stroke="currentColor"
          strokeWidth="0.4"
          className="stroke-kerf-300"
          opacity="0.4"
        />
      ))}
      {/* Standard cells — alternating widths */}
      {[0, 1, 2, 3, 4, 5].map((row) =>
        [0, 1, 2, 3, 4].map((col) => (
          <rect
            key={`${row}-${col}`}
            x={20 + col * 9}
            y={20 + row * 6}
            width={col % 2 === 0 ? 5 : 7}
            height="4"
            rx="0.3"
            stroke="currentColor"
            strokeWidth="0.5"
            className="stroke-kerf-300"
            opacity="0.6"
          />
        ))
      )}

      {/* SRAM block */}
      <rect x="72" y="18" width="34" height="44" rx="1" stroke="currentColor" strokeWidth="1" className="stroke-kerf-500" />
      {/* Bit-cell array lines */}
      {[0, 1, 2, 3, 4, 5, 6].map((i) => (
        <line key={i} x1="72" y1={22 + i * 5} x2="106" y2={22 + i * 5} stroke="currentColor" strokeWidth="0.4" className="stroke-kerf-300" opacity="0.35" />
      ))}
      {[0, 1, 2, 3, 4].map((i) => (
        <line key={i} x1={76 + i * 6} y1="18" x2={76 + i * 6} y2="62" stroke="currentColor" strokeWidth="0.4" className="stroke-kerf-300" opacity="0.35" />
      ))}

      {/* I/O ring — bond pads */}
      <rect x="72" y="66" width="34" height="34" rx="1" stroke="currentColor" strokeWidth="1" className="stroke-kerf-300" opacity="0.7" />
      {[0, 1, 2, 3].map((i) => (
        <rect key={i} x={74 + i * 8} y="68" width="5" height="5" rx="0.5" stroke="currentColor" strokeWidth="0.6" className="stroke-kerf-500" />
      ))}

      {/* Power domain */}
      <rect x="18" y="66" width="50" height="34" rx="1" stroke="currentColor" strokeWidth="1" className="stroke-kerf-300" opacity="0.7" />
      <line x1="18" y1="78" x2="68" y2="78" stroke="currentColor" strokeWidth="1.2" className="stroke-kerf-500" opacity="0.5" />
      <line x1="18" y1="88" x2="68" y2="88" stroke="currentColor" strokeWidth="1.2" className="stroke-kerf-500" opacity="0.5" />

      {/* Metal routing layers (horizontal stripes top portion) */}
      {[0, 1].map((i) => (
        <line key={i} x1="14" y1={50 + i * 6} x2="106" y2={50 + i * 6} stroke="currentColor" strokeWidth="0.6" className="stroke-kerf-300" opacity="0.25" />
      ))}
    </svg>
  )
}
