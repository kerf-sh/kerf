/**
 * ScriptingIllustration — Python `kerf-sdk` snippet on the left, JSON-RPC
 * envelope arrow in the middle, project file tree on the right.
 * Communicates "scriptable from your own machine."
 *
 * viewBox 320×200. Code rendered as single-line <text> rows with one fill
 * each (no token-level positioning) so monospace alignment stays clean.
 */
export default function ScriptingIllustration({ className = '' }) {
  const codeRows = [
    { y: 60, content: '$ pip install kerf-sdk', fill: '#5a6275' },
    { y: 75, content: 'from kerf import Kerf', fill: '#cbd0dc' },
    { y: 89, content: 'k = Kerf.from_env()', fill: '#cbd0dc' },
    { y: 108, content: '# sweep a parameter', fill: '#5a6275' },
    { y: 122, content: 'for d in [4, 5, 6, 8]:', fill: '#cbd0dc' },
    { y: 136, content: '  k.equations.set(', fill: '#cbd0dc' },
    { y: 148, content: '    "diameter", d)', fill: '#7BB661' },
    { y: 162, content: '  k.files.write(', fill: '#cbd0dc' },
    { y: 174, content: '    "main.jscad", src)', fill: '#7BB661' },
  ]

  const files = [
    { y: 76, name: 'main.jscad', active: true },
    { y: 90, name: '.equations' },
    { y: 104, name: 'profile.sketch' },
    { y: 118, name: 'frame.assembly' },
    { y: 132, name: 'sheet.drawing' },
    { y: 146, name: 'board.circuit' },
  ]

  return (
    <svg
      viewBox="0 0 320 200"
      preserveAspectRatio="xMidYMid meet"
      className={className}
      role="img"
      aria-label="Python kerf-sdk snippet sending a JSON-RPC call to a project file tree"
    >
      <defs>
        <marker
          id="scr-arrow"
          viewBox="0 0 10 10"
          refX="9"
          refY="5"
          markerWidth="6"
          markerHeight="6"
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
        KERF-SDK · PYTHON
      </text>
      <line x1="22" y1="40" x2="298" y2="40" stroke="#1a1d24" strokeWidth="0.6" />

      {/* === Left: Python snippet === */}
      <rect x="22" y="48" width="160" height="132" rx="4" fill="#0d0f13" stroke="#1a1d24" />
      <g fontSize="7.5" fontFamily="ui-monospace, SFMono-Regular, monospace">
        {codeRows.map((row, i) => (
          <text key={i} x="30" y={row.y} fill={row.fill}>
            {row.content}
          </text>
        ))}
      </g>

      {/* === Middle: RPC envelope === */}
      <g transform="translate(190, 92)">
        <rect width="56" height="32" rx="3" fill="#0d0f13" stroke="#ffd633" strokeOpacity="0.8" />
        <text
          x="28"
          y="14"
          textAnchor="middle"
          fontSize="7"
          fontFamily="ui-monospace, monospace"
          fill="#ffd633"
          letterSpacing="0.4"
        >
          POST
        </text>
        <text
          x="28"
          y="25"
          textAnchor="middle"
          fontSize="6.5"
          fontFamily="ui-monospace, monospace"
          fill="#cbd0dc"
        >
          /v1/rpc
        </text>
      </g>

      {/* arrows on either side of envelope */}
      <g stroke="#ffd633" strokeWidth="1" fill="none" strokeLinecap="round">
        <line x1="184" y1="108" x2="190" y2="108" />
        <line x1="246" y1="108" x2="254" y2="108" markerEnd="url(#scr-arrow)" />
      </g>

      {/* === Right: project files === */}
      <rect x="248" y="48" width="60" height="132" rx="4" fill="#0d0f13" stroke="#1a1d24" />
      <text
        x="278"
        y="62"
        textAnchor="middle"
        fontSize="7"
        fontFamily="ui-monospace, monospace"
        fill="#5a6275"
        letterSpacing="1.2"
      >
        PROJECT
      </text>
      <line x1="256" y1="68" x2="300" y2="68" stroke="#1a1d24" strokeWidth="0.5" />

      <g fontSize="7" fontFamily="ui-monospace, monospace">
        {files.map((f) => (
          <g key={f.name}>
            {f.active && (
              <rect
                x="254"
                y={f.y - 8}
                width="50"
                height="11"
                rx="2"
                fill="#ffd633"
                fillOpacity="0.12"
                stroke="#ffd633"
                strokeOpacity="0.35"
              />
            )}
            <text x="258" y={f.y} fill={f.active ? '#ffd633' : '#a8aebf'}>
              {f.name}
            </text>
          </g>
        ))}
        <line x1="256" y1="158" x2="300" y2="158" stroke="#1a1d24" strokeWidth="0.5" />
        <text x="258" y="170" fontSize="6.5" fill="#7BB661">
          ↻ revisioned
        </text>
      </g>
    </svg>
  )
}
