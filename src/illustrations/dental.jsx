/**
 * Dental illustration — tooth cross-section with crown overlay.
 */
export default function DentalIllustration({ className = '', size = 120 }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 120 120"
      fill="none"
      className={className}
      aria-hidden="true"
    >
      {/* Tooth body — molar cross-section */}
      {/* Crown (enamel outline) */}
      <path
        d="M35 55 C35 35 42 18 60 16 C78 18 85 35 85 55 C85 62 82 68 78 72 L42 72 C38 68 35 62 35 55 Z"
        stroke="currentColor"
        strokeWidth="1.4"
        className="stroke-kerf-300"
        fill="none"
      />
      {/* Cusps */}
      <path d="M45 55 C43 48 46 38 52 35 C54 34 56 34 58 36" stroke="currentColor" strokeWidth="0.8" className="stroke-kerf-300" opacity="0.5" />
      <path d="M62 35 C65 32 70 34 72 38 C74 43 74 50 72 55" stroke="currentColor" strokeWidth="0.8" className="stroke-kerf-300" opacity="0.5" />

      {/* Dentin layer */}
      <path
        d="M40 58 C40 42 46 28 60 26 C74 28 80 42 80 58 C80 63 78 67 75 70 L45 70 C42 67 40 63 40 58 Z"
        stroke="currentColor"
        strokeWidth="0.7"
        className="stroke-kerf-500"
        strokeDasharray="3 2"
        opacity="0.5"
      />

      {/* Pulp chamber */}
      <path
        d="M50 60 C50 50 54 40 60 38 C66 40 70 50 70 60 C70 64 68 67 65 68 L55 68 C52 67 50 64 50 60 Z"
        stroke="currentColor"
        strokeWidth="0.8"
        className="stroke-kerf-300"
        opacity="0.4"
      />

      {/* Roots */}
      <path d="M45 72 C44 82 43 92 44 102 C45 108 50 110 55 108 C57 107 58 102 58 96 L58 72" stroke="currentColor" strokeWidth="1.2" className="stroke-kerf-300" />
      <path d="M75 72 C76 82 77 92 76 102 C75 108 70 110 65 108 C63 107 62 102 62 96 L62 72" stroke="currentColor" strokeWidth="1.2" className="stroke-kerf-300" />

      {/* Root canal */}
      <line x1="55" y1="68" x2="54" y2="104" stroke="currentColor" strokeWidth="0.7" className="stroke-kerf-500" strokeDasharray="2 2" opacity="0.5" />
      <line x1="65" y1="68" x2="66" y2="104" stroke="currentColor" strokeWidth="0.7" className="stroke-kerf-500" strokeDasharray="2 2" opacity="0.5" />

      {/* Crown prosthetic overlay (highlighted) */}
      <path
        d="M34 55 C33 34 41 15 60 13 C79 15 87 34 86 55 C86 63 83 70 79 74 L41 74 C37 70 34 63 34 55 Z"
        stroke="currentColor"
        strokeWidth="1.8"
        className="stroke-kerf-500"
        fill="none"
        opacity="0.6"
      />

      {/* CEJ (cement-enamel junction) */}
      <line x1="38" y1="72" x2="82" y2="72" stroke="currentColor" strokeWidth="0.6" className="stroke-kerf-300" strokeDasharray="2 1" opacity="0.6" />
    </svg>
  )
}
