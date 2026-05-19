/**
 * Architecture illustration — isometric wall section with door + window.
 */
export default function ArchitectureIllustration({ className = '', size = 120 }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 120 120"
      fill="none"
      className={className}
      aria-hidden="true"
    >
      {/* Isometric floor plane */}
      <path d="M60 90 L10 65 L60 40 L110 65 Z" stroke="currentColor" strokeWidth="0.8" opacity="0.2" />

      {/* Left wall face */}
      <path d="M10 65 L10 20 L60 45 L60 90 Z" stroke="currentColor" strokeWidth="1.2" className="stroke-kerf-300" fill="none" />
      {/* Right wall face */}
      <path d="M60 45 L110 20 L110 65 L60 90 Z" stroke="currentColor" strokeWidth="1.2" className="stroke-kerf-300" fill="none" opacity="0.6" />
      {/* Roof top edge */}
      <line x1="10" y1="20" x2="60" y2="45" stroke="currentColor" strokeWidth="1.2" className="stroke-kerf-500" />
      <line x1="60" y1="45" x2="110" y2="20" stroke="currentColor" strokeWidth="1.2" className="stroke-kerf-500" />

      {/* Window on left wall */}
      <path d="M18 38 L18 52 L34 59 L34 45 Z" stroke="currentColor" strokeWidth="0.9" className="stroke-kerf-300" />
      {/* Window cross */}
      <line x1="18" y1="46" x2="34" y2="52" stroke="currentColor" strokeWidth="0.6" className="stroke-kerf-300" opacity="0.6" />
      <line x1="26" y1="41" x2="26" y2="56" stroke="currentColor" strokeWidth="0.6" className="stroke-kerf-300" opacity="0.6" />

      {/* Door on left wall */}
      <path d="M44 55 L44 75 L56 80 L56 60 Z" stroke="currentColor" strokeWidth="0.9" className="stroke-kerf-500" />
      {/* Door arch */}
      <path d="M44 55 Q50 50 56 60" stroke="currentColor" strokeWidth="0.9" className="stroke-kerf-500" fill="none" />
      {/* Door knob */}
      <circle cx="46" cy="68" r="1.2" stroke="currentColor" strokeWidth="0.8" className="stroke-kerf-300" />

      {/* Window on right wall */}
      <path d="M70 30 L70 44 L86 37 L86 23 Z" stroke="currentColor" strokeWidth="0.9" className="stroke-kerf-300" opacity="0.7" />
      <line x1="70" y1="37" x2="86" y2="30" stroke="currentColor" strokeWidth="0.6" className="stroke-kerf-300" opacity="0.5" />

      {/* Ground shadow line */}
      <line x1="10" y1="90" x2="110" y2="90" stroke="currentColor" strokeWidth="0.6" opacity="0.2" strokeDasharray="4 3" />

      {/* Dimension annotation */}
      <line x1="10" y1="95" x2="60" y2="95" stroke="currentColor" strokeWidth="0.5" opacity="0.4" />
      <line x1="10" y1="93" x2="10" y2="97" stroke="currentColor" strokeWidth="0.5" opacity="0.4" />
      <line x1="60" y1="93" x2="60" y2="97" stroke="currentColor" strokeWidth="0.5" opacity="0.4" />
    </svg>
  )
}
