/**
 * Jewelry illustration — gemstone facets (brilliant cut) + ring shank profile.
 */
export default function JewelryIllustration({ className = '', size = 120 }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 120 120"
      fill="none"
      className={className}
      aria-hidden="true"
    >
      {/* Ring shank — elliptical cross-section */}
      <ellipse cx="60" cy="92" rx="28" ry="12" stroke="currentColor" strokeWidth="1.3" className="stroke-kerf-300" />
      <ellipse cx="60" cy="82" rx="28" ry="12" stroke="currentColor" strokeWidth="1.3" className="stroke-kerf-300" />
      <line x1="32" y1="82" x2="32" y2="92" stroke="currentColor" strokeWidth="1.3" className="stroke-kerf-300" />
      <line x1="88" y1="82" x2="88" y2="92" stroke="currentColor" strokeWidth="1.3" className="stroke-kerf-300" />

      {/* Prong setting stems */}
      <line x1="50" y1="75" x2="47" y2="60" stroke="currentColor" strokeWidth="1" className="stroke-kerf-500" opacity="0.7" />
      <line x1="70" y1="75" x2="73" y2="60" stroke="currentColor" strokeWidth="1" className="stroke-kerf-500" opacity="0.7" />
      <line x1="60" y1="72" x2="60" y2="58" stroke="currentColor" strokeWidth="1" className="stroke-kerf-500" opacity="0.7" />

      {/* Gemstone — brilliant cut top view */}
      {/* Table (top octagon) */}
      <polygon
        points="60,22 70,26 74,36 70,46 60,50 50,46 46,36 50,26"
        stroke="currentColor"
        strokeWidth="1.2"
        className="stroke-kerf-300"
      />
      {/* Star facets */}
      <line x1="60" y1="22" x2="60" y2="50" stroke="currentColor" strokeWidth="0.6" className="stroke-kerf-300" opacity="0.5" />
      <line x1="46" y1="36" x2="74" y2="36" stroke="currentColor" strokeWidth="0.6" className="stroke-kerf-300" opacity="0.5" />
      <line x1="50" y1="26" x2="70" y2="46" stroke="currentColor" strokeWidth="0.6" className="stroke-kerf-300" opacity="0.5" />
      <line x1="70" y1="26" x2="50" y2="46" stroke="currentColor" strokeWidth="0.6" className="stroke-kerf-300" opacity="0.5" />
      {/* Girdle */}
      <polygon
        points="60,15 73,20 80,36 73,52 60,57 47,52 40,36 47,20"
        stroke="currentColor"
        strokeWidth="1"
        className="stroke-kerf-500"
      />
      {/* Upper-half facets (kite) */}
      <line x1="60" y1="15" x2="46" y2="36" stroke="currentColor" strokeWidth="0.5" className="stroke-kerf-300" opacity="0.4" />
      <line x1="60" y1="15" x2="74" y2="36" stroke="currentColor" strokeWidth="0.5" className="stroke-kerf-300" opacity="0.4" />
      <line x1="60" y1="57" x2="46" y2="36" stroke="currentColor" strokeWidth="0.5" className="stroke-kerf-300" opacity="0.4" />
      <line x1="60" y1="57" x2="74" y2="36" stroke="currentColor" strokeWidth="0.5" className="stroke-kerf-300" opacity="0.4" />
      {/* Culet point */}
      <circle cx="60" cy="36" r="2" stroke="currentColor" strokeWidth="0.8" className="stroke-kerf-500" />
    </svg>
  )
}
