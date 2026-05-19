/**
 * Firmware illustration — MCU development board with USB connector + LED indicator.
 */
export default function FirmwareIllustration({ className = '', size = 120 }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 120 120"
      fill="none"
      className={className}
      aria-hidden="true"
    >
      {/* Board outline */}
      <rect x="15" y="25" width="90" height="70" rx="4" stroke="currentColor" strokeWidth="1.4" className="stroke-kerf-300" />

      {/* MCU chip */}
      <rect x="40" y="42" width="40" height="36" rx="2" stroke="currentColor" strokeWidth="1.2" className="stroke-kerf-500" />
      {/* MCU label lines */}
      <line x1="46" y1="52" x2="74" y2="52" stroke="currentColor" strokeWidth="0.7" className="stroke-kerf-300" opacity="0.5" />
      <line x1="46" y1="58" x2="74" y2="58" stroke="currentColor" strokeWidth="0.7" className="stroke-kerf-300" opacity="0.5" />
      <line x1="46" y1="64" x2="74" y2="64" stroke="currentColor" strokeWidth="0.7" className="stroke-kerf-300" opacity="0.5" />
      {/* Pin 1 marker */}
      <circle cx="43" cy="44" r="1.5" stroke="currentColor" strokeWidth="0.6" className="stroke-kerf-300" />

      {/* MCU pins top */}
      {[0, 1, 2, 3, 4].map((i) => (
        <line key={i} x1={46 + i * 7} y1="38" x2={46 + i * 7} y2="42" stroke="currentColor" strokeWidth="1" className="stroke-kerf-500" />
      ))}
      {/* MCU pins bottom */}
      {[0, 1, 2, 3, 4].map((i) => (
        <line key={i} x1={46 + i * 7} y1="78" x2={46 + i * 7} y2="82" stroke="currentColor" strokeWidth="1" className="stroke-kerf-500" />
      ))}
      {/* MCU pins left */}
      {[0, 1, 2].map((i) => (
        <line key={i} x1="36" y1={50 + i * 8} x2="40" y2={50 + i * 8} stroke="currentColor" strokeWidth="1" className="stroke-kerf-500" />
      ))}
      {/* MCU pins right */}
      {[0, 1, 2].map((i) => (
        <line key={i} x1="80" y1={50 + i * 8} x2="84" y2={50 + i * 8} stroke="currentColor" strokeWidth="1" className="stroke-kerf-500" />
      ))}

      {/* USB connector (micro-USB shape) */}
      <rect x="15" y="54" width="10" height="12" rx="1" stroke="currentColor" strokeWidth="1.2" className="stroke-kerf-300" />
      <path d="M25 57 L27 56 L27 68 L25 67" stroke="currentColor" strokeWidth="0.8" className="stroke-kerf-300" />
      {/* USB pins */}
      <line x1="17" y1="57" x2="17" y2="65" stroke="currentColor" strokeWidth="0.5" className="stroke-kerf-300" opacity="0.5" />
      <line x1="19" y1="57" x2="19" y2="65" stroke="currentColor" strokeWidth="0.5" className="stroke-kerf-300" opacity="0.5" />
      <line x1="21" y1="57" x2="21" y2="65" stroke="currentColor" strokeWidth="0.5" className="stroke-kerf-300" opacity="0.5" />
      <line x1="23" y1="57" x2="23" y2="65" stroke="currentColor" strokeWidth="0.5" className="stroke-kerf-300" opacity="0.5" />

      {/* Crystal oscillator */}
      <rect x="87" y="42" width="14" height="8" rx="2" stroke="currentColor" strokeWidth="0.9" className="stroke-kerf-300" />
      <line x1="90" y1="38" x2="90" y2="42" stroke="currentColor" strokeWidth="0.8" className="stroke-kerf-500" />
      <line x1="98" y1="38" x2="98" y2="42" stroke="currentColor" strokeWidth="0.8" className="stroke-kerf-500" />

      {/* LED indicator */}
      <circle cx="95" cy="68" r="5" stroke="currentColor" strokeWidth="1" className="stroke-kerf-500" />
      <line x1="93" y1="64" x2="93" y2="68" stroke="currentColor" strokeWidth="0.8" className="stroke-kerf-300" />
      <line x1="97" y1="64" x2="97" y2="68" stroke="currentColor" strokeWidth="0.8" className="stroke-kerf-300" />
      {/* LED glow rays */}
      <line x1="95" y1="62" x2="95" y2="59" stroke="currentColor" strokeWidth="0.6" className="stroke-kerf-300" opacity="0.6" />
      <line x1="99" y1="63" x2="101" y2="61" stroke="currentColor" strokeWidth="0.6" className="stroke-kerf-300" opacity="0.6" />
      <line x1="91" y1="63" x2="89" y2="61" stroke="currentColor" strokeWidth="0.6" className="stroke-kerf-300" opacity="0.6" />

      {/* Header pins row */}
      {[0, 1, 2, 3, 4, 5, 6, 7].map((i) => (
        <rect key={i} x={20 + i * 9} y="87" width="5" height="5" rx="0.5" stroke="currentColor" strokeWidth="0.7" className="stroke-kerf-300" opacity="0.6" />
      ))}
    </svg>
  )
}
