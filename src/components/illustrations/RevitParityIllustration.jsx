/**
 * RevitParityIllustration — left: stack of BIM authoring files
 * (.family.json, .schedule.json, .view.json, .sheet.json) with green
 * check dots. Right: small floor-plan thumbnail with a hosted door
 * symbol + a category chip ("Walls").
 *
 * viewBox 320×200. Palette locked.
 */
export default function RevitParityIllustration({ className = '' }) {
  const files = [
    { name: '.family.json', y: 70 },
    { name: '.schedule.json', y: 90 },
    { name: '.view.json', y: 110 },
    { name: '.sheet.json', y: 130 },
  ]

  return (
    <svg
      viewBox="0 0 320 200"
      preserveAspectRatio="xMidYMid meet"
      className={className}
      role="img"
      aria-label="BIM authoring files (.family, .schedule, .view, .sheet) compiled into a floor plan with a Walls category chip"
    >
      <defs>
        <marker
          id="rev-arrow"
          viewBox="0 0 10 10"
          refX="9"
          refY="5"
          markerWidth="5"
          markerHeight="5"
          orient="auto"
        >
          <path d="M0,1 L9,5 L0,9 Z" fill="#ffd633" />
        </marker>
      </defs>

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
        BIM AUTHORING
      </text>
      <line x1="22" y1="40" x2="298" y2="40" stroke="#1a1d24" strokeWidth="0.6" />

      {/* === Left: file stack === */}
      <rect x="20" y="50" width="128" height="126" rx="4" fill="#0d0f13" stroke="#1a1d24" />
      <text
        x="28"
        y="62"
        fontSize="7"
        fontFamily="ui-monospace, monospace"
        fill="#5a6275"
        letterSpacing="1.2"
      >
        PROJECT
      </text>

      {files.map((f) => (
        <g key={f.name}>
          {/* row background */}
          <rect
            x="26"
            y={f.y - 9}
            width="116"
            height="14"
            rx="2"
            fill="#0a0b0d"
            stroke="#1a1d24"
            strokeWidth="0.5"
          />
          {/* green check dot */}
          <circle cx="34" cy={f.y - 2} r="2.4" fill="#7BB661" />
          <text
            x="44"
            y={f.y + 1}
            fontSize="7.5"
            fontFamily="ui-monospace, monospace"
            fill="#cbd0dc"
          >
            {f.name}
          </text>
        </g>
      ))}

      {/* file-count footer */}
      <text
        x="28"
        y="166"
        fontSize="6.5"
        fontFamily="ui-monospace, monospace"
        fill="#5a6275"
      >
        4 / 4 parsed
      </text>

      {/* arrow → plan */}
      <g stroke="#ffd633" strokeWidth="1.1" fill="none" strokeLinecap="round">
        <line x1="152" y1="112" x2="174" y2="112" markerEnd="url(#rev-arrow)" />
      </g>

      {/* === Right: floor plan thumbnail === */}
      <rect x="180" y="50" width="120" height="126" rx="4" fill="#0d0f13" stroke="#1a1d24" />
      <text
        x="188"
        y="62"
        fontSize="7"
        fontFamily="ui-monospace, monospace"
        fill="#5a6275"
        letterSpacing="1.2"
      >
        LEVEL · L1
      </text>

      {/* plan walls — clean rectangle with a door opening on the south wall */}
      <g stroke="#cbd0dc" strokeWidth="1.4" fill="none" strokeLinecap="round" strokeLinejoin="round">
        {/* outer perimeter (broken at door) */}
        <polyline points="198,82 292,82 292,158 240,158" />
        <polyline points="216,158 198,158 198,82" />
        {/* interior wall (partition) */}
        <line x1="252" y1="82" x2="252" y2="124" />
      </g>

      {/* door swing (arc + leaf) at south opening between x=216 and x=240 */}
      <g fill="none" stroke="#ffd633" strokeWidth="1.1" strokeLinecap="round">
        {/* door leaf */}
        <line x1="216" y1="158" x2="216" y2="138" />
        {/* swing arc */}
        <path d="M 216 138 A 20 20 0 0 1 236 158" />
      </g>

      {/* room labels */}
      <text
        x="222"
        y="118"
        textAnchor="middle"
        fontSize="6.5"
        fontFamily="ui-monospace, monospace"
        fill="#6a7185"
      >
        LIVING
      </text>
      <text
        x="272"
        y="108"
        textAnchor="middle"
        fontSize="6.5"
        fontFamily="ui-monospace, monospace"
        fill="#6a7185"
      >
        KIT.
      </text>

      {/* category chip */}
      <g transform="translate(186, 163)">
        <rect width="48" height="11" rx="2" fill="#ffd633" fillOpacity="0.16" stroke="#ffd633" strokeOpacity="0.5" />
        <circle cx="6" cy="5.5" r="1.8" fill="#ffd633" />
        <text
          x="11"
          y="8.5"
          fontSize="7"
          fontFamily="ui-monospace, monospace"
          fill="#ffd633"
        >
          Walls
        </text>
      </g>
      <g transform="translate(240, 163)">
        <rect width="50" height="11" rx="2" fill="#0a0b0d" stroke="#3a4150" />
        <circle cx="6" cy="5.5" r="1.8" fill="#7BB661" />
        <text
          x="11"
          y="8.5"
          fontSize="7"
          fontFamily="ui-monospace, monospace"
          fill="#cbd0dc"
        >
          Doors
        </text>
      </g>
    </svg>
  )
}
