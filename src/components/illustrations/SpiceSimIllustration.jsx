/**
 * SpiceSimIllustration — SPICE simulation card. Left panel: minimal RC
 * schematic with a V1 probe dot. Right panel: a transient sine response
 * over a time axis. ngspice mono caption bottom-right.
 *
 * viewBox 320×200. Palette locked.
 */
export default function SpiceSimIllustration({ className = '' }) {
  // Build the transient sine path. y centered at 132, peak ±18.
  const wavePoints = []
  const x0 = 178
  const x1 = 296
  const yMid = 132
  const amp = 18
  const cycles = 1.6
  const steps = 60
  for (let i = 0; i <= steps; i++) {
    const t = i / steps
    const x = x0 + t * (x1 - x0)
    // Damped sine so the trace looks "settling"
    const damping = Math.exp(-t * 0.4)
    const y = yMid - Math.sin(t * Math.PI * 2 * cycles) * amp * damping
    wavePoints.push(`${x.toFixed(2)},${y.toFixed(2)}`)
  }

  return (
    <svg
      viewBox="0 0 320 200"
      preserveAspectRatio="xMidYMid meet"
      className={className}
      role="img"
      aria-label="A minimal RC SPICE schematic with a voltage probe on the left and a transient sine response on the right"
    >
      <rect x="8" y="14" width="304" height="172" rx="8" fill="#0a0b0d" stroke="#1a1d24" />

      {/* header */}
      <text
        x="22"
        y="32"
        fontSize="9"
        fontFamily="ui-monospace, SFMono-Regular, monospace"
        fill="#6a7185"
        letterSpacing="1.4"
      >
        SPICE SIMULATION
      </text>
      <line x1="22" y1="40" x2="298" y2="40" stroke="#1a1d24" strokeWidth="0.6" />

      {/* ============ Left panel: schematic ============ */}
      <rect x="20" y="48" width="142" height="128" rx="4" fill="#0d0f13" stroke="#1a1d24" />
      <text
        x="28"
        y="60"
        fontSize="7"
        fontFamily="ui-monospace, monospace"
        fill="#5a6275"
        letterSpacing="1.2"
      >
        SCHEMATIC
      </text>

      {/* Schematic wires (rail loop) */}
      <g stroke="#8a93a6" strokeWidth="0.9" fill="none" strokeLinecap="round">
        {/* top rail: V+ → R → C → node */}
        <line x1="46" y1="84" x2="62" y2="84" />
        <line x1="92" y1="84" x2="106" y2="84" />
        <line x1="136" y1="84" x2="146" y2="84" />
        {/* right vertical down to GND */}
        <line x1="146" y1="84" x2="146" y2="148" />
        {/* bottom rail */}
        <line x1="146" y1="148" x2="46" y2="148" />
        {/* left vertical (V- to V+) */}
        <line x1="46" y1="148" x2="46" y2="116" />
        <line x1="46" y1="100" x2="46" y2="84" />
      </g>

      {/* Voltage source: circle with +/- */}
      <g>
        <circle cx="46" cy="108" r="8" fill="#0a0b0d" stroke="#ffd633" strokeWidth="1.1" />
        <text
          x="46"
          y="106"
          textAnchor="middle"
          fontSize="6.5"
          fontFamily="ui-monospace, monospace"
          fill="#ffd633"
        >
          +
        </text>
        <text
          x="46"
          y="115"
          textAnchor="middle"
          fontSize="6.5"
          fontFamily="ui-monospace, monospace"
          fill="#ffd633"
        >
          −
        </text>
        <text
          x="32"
          y="111"
          textAnchor="end"
          fontSize="7"
          fontFamily="ui-monospace, monospace"
          fill="#cbd0dc"
        >
          Vin
        </text>
      </g>

      {/* Resistor: zigzag */}
      <g stroke="#cbd0dc" strokeWidth="1.1" fill="none" strokeLinejoin="round">
        <polyline points="62,84 65,78 71,90 77,78 83,90 89,78 92,84" />
      </g>
      <text
        x="77"
        y="74"
        textAnchor="middle"
        fontSize="7"
        fontFamily="ui-monospace, monospace"
        fill="#8a93a6"
      >
        R1
      </text>

      {/* Capacitor: two parallel plates */}
      <g stroke="#cbd0dc" strokeWidth="1.1" fill="none" strokeLinecap="round">
        <line x1="115" y1="76" x2="115" y2="92" />
        <line x1="121" y1="76" x2="121" y2="92" />
      </g>
      <line x1="106" y1="84" x2="115" y2="84" stroke="#8a93a6" strokeWidth="0.9" />
      <line x1="121" y1="84" x2="136" y2="84" stroke="#8a93a6" strokeWidth="0.9" />
      <text
        x="118"
        y="102"
        textAnchor="middle"
        fontSize="7"
        fontFamily="ui-monospace, monospace"
        fill="#8a93a6"
      >
        C1
      </text>

      {/* Probe dot on the right node */}
      <g>
        <circle cx="146" cy="84" r="3" fill="#ffd633" />
        <circle cx="146" cy="84" r="5.5" fill="none" stroke="#ffd633" strokeOpacity="0.45" strokeWidth="0.8" />
        <text
          x="152"
          y="76"
          fontSize="7"
          fontFamily="ui-monospace, monospace"
          fill="#ffd633"
        >
          V1
        </text>
      </g>

      {/* GND symbol */}
      <g stroke="#8a93a6" strokeWidth="0.8" fill="none">
        <line x1="92" y1="148" x2="92" y2="156" />
        <line x1="86" y1="156" x2="98" y2="156" />
        <line x1="88" y1="159" x2="96" y2="159" />
        <line x1="90" y1="162" x2="94" y2="162" />
      </g>

      {/* ============ Right panel: transient waveform ============ */}
      <rect x="170" y="48" width="130" height="128" rx="4" fill="#0d0f13" stroke="#1a1d24" />
      <text
        x="178"
        y="60"
        fontSize="7"
        fontFamily="ui-monospace, monospace"
        fill="#5a6275"
        letterSpacing="1.2"
      >
        .TRAN V(V1)
      </text>

      {/* axis grid */}
      <g stroke="#1e2230" strokeWidth="0.5">
        <line x1="178" y1="96" x2="296" y2="96" />
        <line x1="178" y1="114" x2="296" y2="114" />
        <line x1="178" y1="132" x2="296" y2="132" />
        <line x1="178" y1="150" x2="296" y2="150" />
        <line x1="208" y1="80" x2="208" y2="162" />
        <line x1="238" y1="80" x2="238" y2="162" />
        <line x1="268" y1="80" x2="268" y2="162" />
      </g>

      {/* axes (stronger) */}
      <g stroke="#3a4150" strokeWidth="0.7">
        <line x1="178" y1="162" x2="296" y2="162" />
        <line x1="178" y1="80" x2="178" y2="162" />
      </g>

      {/* axis ticks */}
      <g
        fontSize="6"
        fontFamily="ui-monospace, monospace"
        fill="#5a6275"
      >
        <text x="178" y="172" textAnchor="middle">
          0
        </text>
        <text x="238" y="172" textAnchor="middle">
          5m
        </text>
        <text x="296" y="172" textAnchor="middle">
          10m
        </text>
      </g>

      {/* trace */}
      <polyline
        points={wavePoints.join(' ')}
        fill="none"
        stroke="#ffd633"
        strokeWidth="1.3"
        strokeLinejoin="round"
        strokeLinecap="round"
      />

      {/* footer caption */}
      <text
        x="296"
        y="58"
        textAnchor="end"
        fontSize="6.5"
        fontFamily="ui-monospace, monospace"
        fill="#5a6275"
      >
        ngspice
      </text>
    </svg>
  )
}
