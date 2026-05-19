/**
 * PLC illustration — ladder logic diagram with rungs, contacts, and coil.
 */
export default function PLCIllustration({ className = '', size = 120 }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 120 120"
      fill="none"
      className={className}
      aria-hidden="true"
    >
      {/* Left power rail */}
      <line x1="15" y1="15" x2="15" y2="105" stroke="currentColor" strokeWidth="2.5" className="stroke-kerf-300" />
      {/* Right power rail */}
      <line x1="105" y1="15" x2="105" y2="105" stroke="currentColor" strokeWidth="2.5" className="stroke-kerf-300" />

      {/* Rung 1 */}
      <line x1="15" y1="35" x2="35" y2="35" stroke="currentColor" strokeWidth="1.2" className="stroke-kerf-300" />
      {/* Contact 1 (normally open) */}
      <line x1="35" y1="30" x2="35" y2="40" stroke="currentColor" strokeWidth="1.2" className="stroke-kerf-500" />
      <line x1="45" y1="30" x2="45" y2="40" stroke="currentColor" strokeWidth="1.2" className="stroke-kerf-500" />
      <line x1="35" y1="35" x2="45" y2="35" stroke="currentColor" strokeWidth="1" className="stroke-kerf-300" opacity="0.4" />
      <line x1="45" y1="35" x2="65" y2="35" stroke="currentColor" strokeWidth="1.2" className="stroke-kerf-300" />
      {/* Contact 2 (normally closed) */}
      <line x1="65" y1="30" x2="65" y2="40" stroke="currentColor" strokeWidth="1.2" className="stroke-kerf-500" />
      <line x1="75" y1="30" x2="75" y2="40" stroke="currentColor" strokeWidth="1.2" className="stroke-kerf-500" />
      {/* NC diagonal slash */}
      <line x1="65" y1="40" x2="75" y2="30" stroke="currentColor" strokeWidth="1" className="stroke-kerf-300" opacity="0.6" />
      <line x1="75" y1="35" x2="85" y2="35" stroke="currentColor" strokeWidth="1.2" className="stroke-kerf-300" />
      {/* Coil 1 */}
      <circle cx="93" cy="35" r="8" stroke="currentColor" strokeWidth="1.2" className="stroke-kerf-300" />
      <line x1="85" y1="35" x2="85" y2="35" stroke="currentColor" strokeWidth="1.2" className="stroke-kerf-300" />
      <line x1="101" y1="35" x2="105" y2="35" stroke="currentColor" strokeWidth="1.2" className="stroke-kerf-300" />
      {/* Contact label */}
      <text x="37" y="27" fontSize="5" fill="currentColor" opacity="0.7" fontFamily="monospace">I0.0</text>
      <text x="67" y="27" fontSize="5" fill="currentColor" opacity="0.7" fontFamily="monospace">I0.1</text>
      <text x="88" y="27" fontSize="5" fill="currentColor" opacity="0.7" fontFamily="monospace">Q0.0</text>

      {/* Rung 2 */}
      <line x1="15" y1="65" x2="35" y2="65" stroke="currentColor" strokeWidth="1.2" className="stroke-kerf-300" />
      {/* Timer block */}
      <rect x="35" y="55" width="30" height="20" rx="1" stroke="currentColor" strokeWidth="1" className="stroke-kerf-500" />
      <text x="38" y="64" fontSize="5" fill="currentColor" opacity="0.8" fontFamily="monospace">TON</text>
      <line x1="50" y1="62" x2="62" y2="62" stroke="currentColor" strokeWidth="0.6" className="stroke-kerf-300" opacity="0.5" />
      <line x1="35" y1="65" x2="35" y2="65" stroke="currentColor" strokeWidth="1.2" className="stroke-kerf-300" />
      <line x1="65" y1="65" x2="85" y2="65" stroke="currentColor" strokeWidth="1.2" className="stroke-kerf-300" />
      {/* Coil 2 */}
      <circle cx="93" cy="65" r="8" stroke="currentColor" strokeWidth="1.2" className="stroke-kerf-300" />
      <line x1="101" y1="65" x2="105" y2="65" stroke="currentColor" strokeWidth="1.2" className="stroke-kerf-300" />
      <text x="88" y="57" fontSize="5" fill="currentColor" opacity="0.7" fontFamily="monospace">Q0.1</text>

      {/* Rung 3 */}
      <line x1="15" y1="90" x2="35" y2="90" stroke="currentColor" strokeWidth="1.2" className="stroke-kerf-300" />
      {/* Contact parallel branch */}
      <line x1="35" y1="85" x2="35" y2="95" stroke="currentColor" strokeWidth="1.2" className="stroke-kerf-500" />
      <line x1="45" y1="85" x2="45" y2="95" stroke="currentColor" strokeWidth="1.2" className="stroke-kerf-500" />
      <line x1="45" y1="90" x2="55" y2="90" stroke="currentColor" strokeWidth="1.2" className="stroke-kerf-300" />
      {/* OR branch lines */}
      <line x1="35" y1="85" x2="35" y2="80" stroke="currentColor" strokeWidth="0.8" className="stroke-kerf-300" opacity="0.5" />
      <line x1="45" y1="80" x2="35" y2="80" stroke="currentColor" strokeWidth="0.8" className="stroke-kerf-300" opacity="0.5" />
      <line x1="35" y1="95" x2="35" y2="100" stroke="currentColor" strokeWidth="0.8" className="stroke-kerf-300" opacity="0.5" />
      <line x1="45" y1="100" x2="35" y2="100" stroke="currentColor" strokeWidth="0.8" className="stroke-kerf-300" opacity="0.5" />
      <line x1="55" y1="80" x2="55" y2="100" stroke="currentColor" strokeWidth="0.8" className="stroke-kerf-300" opacity="0.5" />
      <line x1="55" y1="90" x2="85" y2="90" stroke="currentColor" strokeWidth="1.2" className="stroke-kerf-300" />
      {/* Output coil set */}
      <circle cx="93" cy="90" r="8" stroke="currentColor" strokeWidth="1.2" className="stroke-kerf-500" />
      <line x1="90" y1="87" x2="96" y2="93" stroke="currentColor" strokeWidth="0.8" className="stroke-kerf-500" opacity="0.5" />
      <line x1="96" y1="87" x2="90" y2="93" stroke="currentColor" strokeWidth="0.8" className="stroke-kerf-500" opacity="0.5" />
      <line x1="101" y1="90" x2="105" y2="90" stroke="currentColor" strokeWidth="1.2" className="stroke-kerf-300" />
      <text x="88" y="82" fontSize="5" fill="currentColor" opacity="0.7" fontFamily="monospace">Q0.2</text>
    </svg>
  )
}
