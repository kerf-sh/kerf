/**
 * Electronics illustration — PCB trace routing + IC + resistor + capacitor components.
 */
export default function ElectronicsIllustration({ className = '', size = 120 }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 120 120"
      fill="none"
      className={className}
      aria-hidden="true"
    >
      {/* PCB board outline */}
      <rect x="8" y="8" width="104" height="104" rx="4" stroke="currentColor" strokeWidth="1.2" opacity="0.3" />

      {/* Copper traces */}
      <path d="M20 60 H45 V35 H75" stroke="currentColor" strokeWidth="1.5" className="stroke-kerf-300" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M75 35 H95 V55" stroke="currentColor" strokeWidth="1.5" className="stroke-kerf-300" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M20 80 H35 V90 H85 V75 H95" stroke="currentColor" strokeWidth="1.5" className="stroke-kerf-500" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M55 60 V80" stroke="currentColor" strokeWidth="1" className="stroke-kerf-300" strokeLinecap="round" opacity="0.6" />

      {/* IC package */}
      <rect x="42" y="22" width="36" height="26" rx="2" stroke="currentColor" strokeWidth="1.2" className="stroke-kerf-300" />
      {/* IC pins left */}
      <line x1="36" y1="29" x2="42" y2="29" stroke="currentColor" strokeWidth="1" className="stroke-kerf-500" />
      <line x1="36" y1="35" x2="42" y2="35" stroke="currentColor" strokeWidth="1" className="stroke-kerf-500" />
      <line x1="36" y1="41" x2="42" y2="41" stroke="currentColor" strokeWidth="1" className="stroke-kerf-500" />
      {/* IC pins right */}
      <line x1="78" y1="29" x2="84" y2="29" stroke="currentColor" strokeWidth="1" className="stroke-kerf-500" />
      <line x1="78" y1="35" x2="84" y2="35" stroke="currentColor" strokeWidth="1" className="stroke-kerf-500" />
      <line x1="78" y1="41" x2="84" y2="41" stroke="currentColor" strokeWidth="1" className="stroke-kerf-500" />
      {/* IC notch */}
      <path d="M58 22 A4 4 0 0 1 62 22" stroke="currentColor" strokeWidth="1" className="stroke-kerf-300" />

      {/* Resistor */}
      <line x1="14" y1="60" x2="20" y2="60" stroke="currentColor" strokeWidth="1.2" className="stroke-kerf-300" />
      <rect x="20" y="57" width="10" height="6" rx="1" stroke="currentColor" strokeWidth="1" className="stroke-kerf-500" />
      <line x1="30" y1="60" x2="36" y2="60" stroke="currentColor" strokeWidth="1.2" className="stroke-kerf-300" />
      <line x1="22" y1="57" x2="22" y2="63" stroke="currentColor" strokeWidth="0.8" className="stroke-kerf-300" opacity="0.6" />
      <line x1="25" y1="57" x2="25" y2="63" stroke="currentColor" strokeWidth="0.8" className="stroke-kerf-300" opacity="0.6" />

      {/* Capacitor */}
      <line x1="92" y1="45" x2="92" y2="55" stroke="currentColor" strokeWidth="1.2" className="stroke-kerf-300" />
      <line x1="88" y1="50" x2="96" y2="50" stroke="currentColor" strokeWidth="0.8" className="stroke-kerf-300" opacity="0.6" />
      <line x1="88" y1="53" x2="96" y2="53" stroke="currentColor" strokeWidth="1.5" className="stroke-kerf-500" />
      <line x1="88" y1="57" x2="96" y2="57" stroke="currentColor" strokeWidth="1.5" className="stroke-kerf-500" />
      <line x1="92" y1="57" x2="92" y2="65" stroke="currentColor" strokeWidth="1.2" className="stroke-kerf-300" />

      {/* Via pads */}
      <circle cx="55" cy="60" r="3" stroke="currentColor" strokeWidth="1" className="stroke-kerf-300" />
      <circle cx="55" cy="60" r="1.2" stroke="currentColor" strokeWidth="0.8" className="stroke-kerf-500" />
      <circle cx="55" cy="80" r="3" stroke="currentColor" strokeWidth="1" className="stroke-kerf-300" />
      <circle cx="55" cy="80" r="1.2" stroke="currentColor" strokeWidth="0.8" className="stroke-kerf-500" />
    </svg>
  )
}
