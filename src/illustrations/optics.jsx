/**
 * Optics illustration — three-element lens system with ray traces.
 */
export default function OpticsIllustration({ className = '', size = 120 }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 120 120"
      fill="none"
      className={className}
      aria-hidden="true"
    >
      {/* Optical axis */}
      <line x1="8" y1="60" x2="112" y2="60" stroke="currentColor" strokeWidth="0.5" strokeDasharray="4 3" opacity="0.35" />

      {/* Lens 1 — biconvex (doublet) */}
      <path d="M28 40 C33 48 33 72 28 80" stroke="currentColor" strokeWidth="1.2" className="stroke-kerf-300" />
      <path d="M34 40 C29 48 29 72 34 80" stroke="currentColor" strokeWidth="1.2" className="stroke-kerf-300" />
      <line x1="28" y1="40" x2="34" y2="40" stroke="currentColor" strokeWidth="1.2" className="stroke-kerf-300" />
      <line x1="28" y1="80" x2="34" y2="80" stroke="currentColor" strokeWidth="1.2" className="stroke-kerf-300" />

      {/* Lens 2 — plano-convex */}
      <line x1="58" y1="36" x2="58" y2="84" stroke="currentColor" strokeWidth="1.2" className="stroke-kerf-500" />
      <path d="M58 36 C67 44 67 76 58 84" stroke="currentColor" strokeWidth="1.2" className="stroke-kerf-500" />

      {/* Lens 3 — biconcave (diverging) */}
      <path d="M85 38 C90 48 90 72 85 82" stroke="currentColor" strokeWidth="1.2" className="stroke-kerf-300" />
      <path d="M91 38 C86 48 86 72 91 82" stroke="currentColor" strokeWidth="1.2" className="stroke-kerf-300" />
      <line x1="85" y1="38" x2="91" y2="38" stroke="currentColor" strokeWidth="1.2" className="stroke-kerf-300" />
      <line x1="85" y1="82" x2="91" y2="82" stroke="currentColor" strokeWidth="1.2" className="stroke-kerf-300" />

      {/* Ray 1 — axial (marginal ray) */}
      <path d="M8 45 L28 45 L58 60 L85 52 L112 58"
        stroke="currentColor" strokeWidth="1" className="stroke-kerf-500" strokeLinecap="round" strokeLinejoin="round" />

      {/* Ray 2 — chief ray (through center) */}
      <path d="M8 60 L112 60" stroke="currentColor" strokeWidth="0.8" className="stroke-kerf-300" opacity="0.5" />

      {/* Ray 3 — marginal ray below axis */}
      <path d="M8 75 L28 75 L58 60 L85 68 L112 62"
        stroke="currentColor" strokeWidth="1" className="stroke-kerf-500" strokeLinecap="round" strokeLinejoin="round" opacity="0.7" />

      {/* Focal point indicators */}
      {/* Front focal point */}
      <circle cx="12" cy="60" r="2" stroke="currentColor" strokeWidth="0.8" className="stroke-kerf-300" opacity="0.5" />
      {/* Rear focal point */}
      <circle cx="108" cy="60" r="2.5" stroke="currentColor" strokeWidth="1" className="stroke-kerf-500" />
      <line x1="108" y1="56" x2="108" y2="64" stroke="currentColor" strokeWidth="1" className="stroke-kerf-500" opacity="0.6" />

      {/* Label: F' */}
      <text x="104" y="55" fontSize="5" fill="currentColor" opacity="0.6" fontFamily="sans-serif">F′</text>

      {/* Aperture stop indicator */}
      <line x1="58" y1="34" x2="58" y2="38" stroke="currentColor" strokeWidth="1.5" className="stroke-kerf-300" />
      <line x1="58" y1="82" x2="58" y2="86" stroke="currentColor" strokeWidth="1.5" className="stroke-kerf-300" />
      <text x="62" y="33" fontSize="4" fill="currentColor" opacity="0.6" fontFamily="sans-serif">AS</text>
    </svg>
  )
}
