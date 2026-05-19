/**
 * Aerospace illustration — airfoil cross-section + orbit ellipse.
 */
export default function AerospaceIllustration({ className = '', size = 120 }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 120 120"
      fill="none"
      className={className}
      aria-hidden="true"
    >
      {/* Orbit ellipse */}
      <ellipse cx="60" cy="62" rx="48" ry="28" stroke="currentColor" strokeWidth="0.8" className="stroke-kerf-300" opacity="0.4" strokeDasharray="4 3" />

      {/* Satellite / spacecraft on orbit */}
      <rect x="96" y="57" width="8" height="5" rx="1" stroke="currentColor" strokeWidth="1" className="stroke-kerf-500" />
      {/* Solar panels */}
      <rect x="86" y="55" width="8" height="9" rx="0.5" stroke="currentColor" strokeWidth="0.8" className="stroke-kerf-300" />
      <rect x="106" y="55" width="8" height="9" rx="0.5" stroke="currentColor" strokeWidth="0.8" className="stroke-kerf-300" />
      <line x1="90" y1="55" x2="90" y2="64" stroke="currentColor" strokeWidth="0.4" className="stroke-kerf-300" opacity="0.5" />
      <line x1="108" y1="55" x2="108" y2="64" stroke="currentColor" strokeWidth="0.4" className="stroke-kerf-300" opacity="0.5" />

      {/* Airfoil cross-section — NACA-style profile */}
      <path
        d="M15 65 C25 62 40 52 65 50 C80 49 92 54 105 60 C92 66 80 71 65 70 C40 78 25 68 15 65 Z"
        stroke="currentColor"
        strokeWidth="1.4"
        className="stroke-kerf-300"
        fill="none"
      />

      {/* Chord line */}
      <line x1="15" y1="65" x2="105" y2="60" stroke="currentColor" strokeWidth="0.6" className="stroke-kerf-500" strokeDasharray="5 3" opacity="0.6" />

      {/* Camber line (mean line) */}
      <path d="M15 65 C40 61 70 58 105 60" stroke="currentColor" strokeWidth="0.6" className="stroke-kerf-300" strokeDasharray="2 2" opacity="0.5" />

      {/* Airflow streamlines above */}
      <path d="M8 42 C25 40 45 40 65 42 C78 43 90 47 106 52" stroke="currentColor" strokeWidth="0.7" className="stroke-kerf-300" opacity="0.35" strokeLinecap="round" />
      <path d="M8 36 C25 34 45 34 65 36 C78 37 90 42 106 47" stroke="currentColor" strokeWidth="0.7" className="stroke-kerf-300" opacity="0.25" strokeLinecap="round" />
      {/* Airflow streamlines below */}
      <path d="M8 88 C25 90 45 90 65 88 C78 87 90 83 106 78" stroke="currentColor" strokeWidth="0.7" className="stroke-kerf-300" opacity="0.35" strokeLinecap="round" />

      {/* Leading-edge radius annotation */}
      <circle cx="15" cy="65" r="3" stroke="currentColor" strokeWidth="0.8" className="stroke-kerf-500" opacity="0.6" />

      {/* Angle of attack arrow */}
      <path d="M8 72 L14 65" stroke="currentColor" strokeWidth="1" className="stroke-kerf-500" strokeLinecap="round" />
      <polygon points="14,65 10,66 13,62" fill="currentColor" className="stroke-kerf-500" opacity="0.8" />
    </svg>
  )
}
