/**
 * Woodworking illustration — dovetail joint (exploded view).
 */
export default function WoodworkingIllustration({ className = '', size = 120 }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 120 120"
      fill="none"
      className={className}
      aria-hidden="true"
    >
      {/* Tail board (horizontal piece) */}
      {/* Board face */}
      <rect x="60" y="35" width="50" height="30" rx="1" stroke="currentColor" strokeWidth="1.2" className="stroke-kerf-300" />
      {/* Wood grain lines on tail board */}
      {[0, 1, 2, 3].map((i) => (
        <line key={i} x1="62" y1={40 + i * 6} x2="108" y2={40 + i * 6} stroke="currentColor" strokeWidth="0.4" className="stroke-kerf-300" opacity="0.25" />
      ))}

      {/* Dovetails (tails on end of board) */}
      <polygon points="60,35 52,40 52,60 60,65" stroke="currentColor" strokeWidth="1" className="stroke-kerf-500" fill="none" />
      <polygon points="60,35 55,38 55,57 60,60" stroke="currentColor" strokeWidth="0.6" className="stroke-kerf-300" fill="none" opacity="0.4" />

      {/* Tail 1 */}
      <path d="M60 42 L54 45 L54 55 L60 58" stroke="currentColor" strokeWidth="1.2" className="stroke-kerf-300" />
      {/* Tail 2 */}
      <path d="M60 35 L55 38 L55 62 L60 65" stroke="currentColor" strokeWidth="0.8" className="stroke-kerf-300" opacity="0.5" />

      {/* Pin board (vertical piece) */}
      <rect x="10" y="10" width="30" height="100" rx="1" stroke="currentColor" strokeWidth="1.2" className="stroke-kerf-300" />
      {/* Wood grain lines on pin board */}
      {[0, 1, 2, 3, 4].map((i) => (
        <line key={i} x1={14 + i * 5} y1="12" x2={14 + i * 5} y2="108" stroke="currentColor" strokeWidth="0.4" className="stroke-kerf-300" opacity="0.2" />
      ))}

      {/* Pin sockets cut into pin board */}
      {/* Socket 1 */}
      <path d="M40 42 L46 45 L46 55 L40 58" stroke="currentColor" strokeWidth="1.2" className="stroke-kerf-500" />
      {/* Socket 2 */}
      <path d="M40 70 L46 73 L46 83 L40 86" stroke="currentColor" strokeWidth="1.2" className="stroke-kerf-500" opacity="0.7" />

      {/* Half-pin top */}
      <path d="M40 35 L46 37 L46 42 L40 42" stroke="currentColor" strokeWidth="1" className="stroke-kerf-300" fill="none" />
      {/* Half-pin bottom */}
      <path d="M40 65 L46 67 L46 70 L40 70" stroke="currentColor" strokeWidth="1" className="stroke-kerf-300" fill="none" />

      {/* Pin board right face end */}
      <path d="M40 10 L40 110" stroke="currentColor" strokeWidth="1.2" className="stroke-kerf-300" />

      {/* Assembly gap / explode arrow */}
      <line x1="52" y1="60" x2="46" y2="60" stroke="currentColor" strokeWidth="0.8" className="stroke-kerf-300" strokeDasharray="2 2" opacity="0.5" />
      <line x1="52" y1="50" x2="46" y2="50" stroke="currentColor" strokeWidth="0.8" className="stroke-kerf-300" strokeDasharray="2 2" opacity="0.5" />

      {/* Angle annotation for dovetail */}
      <path d="M60 65 A8 8 0 0 0 54 59" stroke="currentColor" strokeWidth="0.6" className="stroke-kerf-500" opacity="0.6" />
      <text x="50" y="72" fontSize="5" fill="currentColor" opacity="0.6" fontFamily="monospace">14°</text>
    </svg>
  )
}
